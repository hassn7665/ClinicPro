# -*- coding: utf-8 -*-
"""
diagnostics.py — التشخيص لدعم العملاء والتعافي عند الإقلاع وفحص تطابق ملفات الإصدار.
"""
import os
import sqlite3
import sys
import time
from datetime import datetime

import applog as LOG
import images as IMG
import license_core as LC
import schema as SC
import vault as VT

from backup import BK_EXT, backup_report, list_backups, recover_interrupted_restore
from db import _db_encode, _serialize
from licensing import lic_load, lic_status
from media import images_to_optimize
from storage import APP_NAME, APP_VERSION, BASE, BK_DIR, DB_ENC, PAT_DIR, SET_PATH, VAULT, _lock, _mem, jload


# ───────────────────────── التشخيص ─────────────────────────
def diagnostics() -> str:
    """تقرير نصّي لدعم العملاء: إصدارات، فحوص ذاتية وأزمنة على هذا الجهاز، حالة الترخيص والنسخ، آخر سطور السجل.
    لا يحوي أسماء مرضى ولا أرقاماً ولا اسم المستخدم."""
    import platform
    import selftest
    lines = [f"{APP_NAME} {APP_VERSION} — تقرير تشخيص {datetime.now():%Y-%m-%d %H:%M}",
             f"النظام: {sys.platform} {platform.machine()} | بايثون {platform.python_version()}"]
    fv = "?"
    try:
        from importlib.metadata import version as _ver
        fv = _ver("flet")
    except (ImportError, LookupError):                # PackageNotFoundError ⊂ LookupError
        try:
            import flet.version as _fv
            fv = _fv.version
        except (ImportError, AttributeError):
            pass
    lines.append(f"Flet: {fv}")
    lines.append(f"معالجة الصور: {'Pillow ' + IMG.PIL_VERSION if IMG.PIL_OK else 'غير متوفرة'}")
    try:
        lines.append(f"مخطط القاعدة: v{SC.get_version(_mem['conn'])} (الأحدث v{SC.LATEST})" if _mem["conn"] is not None
                     else f"مخطط القاعدة: مقفلة (الأحدث v{SC.LATEST})")
    except sqlite3.Error as ex:
        LOG.log_exc("diag_schema", ex)
    st, days = lic_status()
    d = lic_load()
    lines += ["", "── الحالة ──", f"الترخيص: {st} ({days} يوم) | معرّف الجهاز: {d['device_id'].upper()}"]
    h = VAULT.h or {}
    lines.append(f"الحساب: دورات الاشتقاق={h.get('iter')} | مفتاح استرداد={'نعم' if VAULT.has_recovery_key else 'لا'} | "
                 f"اعتماد المدير={'نعم' if VAULT.escrow_enabled else 'لا'} | قفل={'نعم' if VAULT.locked_out else 'لا'}")
    sset = jload(SET_PATH, {})
    rep = backup_report()
    lines.append(f"آخر نسخة: {sset.get('last_backup', '—')[:19]}"
                 + ("" if list_backups() else " (لا ملف نسخة فعلياً بعد: لا مرضى لنسخهم)")
                 + f" | ملفات={rep['files']} متخطّاة={rep['skipped']} | "
                 f"آخر تصدير: {sset.get('last_export', '—')[:10]} | نسخ داخل الجهاز: {len(list_backups())}")
    n_files = sum(len(f) for _, _, f in os.walk(PAT_DIR))
    size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(PAT_DIR) for f in fs)
    lines.append(f"التخزين: db.enc={os.path.getsize(DB_ENC) if os.path.exists(DB_ENC) else 0} بايت | "
                 f"ملفات المرضى={n_files} ({size // 1024} كيلوبايت) | صور بلا مصغّرة تستحق التحسين: {len(images_to_optimize())}")
    try:
        t0 = time.perf_counter()
        with _lock:
            blob = _db_encode(_serialize(_mem["conn"]), _mem["gen"] + 1)
        lines.append(f"زمن حفظ القاعدة المشفّرة (تسلسل + تشفير): {(time.perf_counter() - t0) * 1000:.0f} مللي ثانية "
                     f"({len(blob) // 1024} كيلوبايت)")
    except Exception as ex:                           # تشخيص: يُعرض النوع للعميل ويُسجَّل
        LOG.log_exc("diag_persist_time", ex)
        lines.append(f"زمن حفظ القاعدة: تعذّر ({type(ex).__name__})")
    lines += ["", "── الفحوص الذاتية على هذا الجهاز ──"]
    for name, ok, detail in selftest.run(BASE, VT.PBKDF2_ITER):
        lines.append(f"{'✓' if ok else '✗'} {name}" + (f" — {detail}" if detail else ""))
    lines += ["", "── آخر أحداث السجل (بلا رسائل ولا بيانات مرضى) ──", LOG.tail(80) or "(فارغ)"]
    return "\n".join(lines)


# ───────────────────────── تعافٍ عند الإقلاع ─────────────────────────
def module_mismatch() -> list:
    """أسماء الملفات التي من إصدار مختلف عن core.py (يحدث عند نسخ بعض ملفات الحزمة دون بقيتها)."""
    return [name for name, mod in (("vault.py", VT), ("license_core.py", LC))
            if getattr(mod, "BUILD", None) != APP_VERSION]


def _startup_recovery():
    try:
        recover_interrupted_restore()
    except Exception as ex:
        LOG.log_exc("startup_recovery", ex)
    try:                                                    # نسخ احتياطية مقطوعة (انقطع التطبيق أثناء كتابتها)
        for fn in os.listdir(BK_DIR):
            if fn.endswith(BK_EXT + ".tmp"):
                os.remove(os.path.join(BK_DIR, fn))
    except OSError:
        pass
