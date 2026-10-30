# -*- coding: utf-8 -*-
"""
backup.py — النسخ الاحتياطي المشفّر (صيغة v2 بسجل ختامي) والاستعادة الذرّية والتعافي من الانقطاع وترحيل الملفات القديمة.
"""
import hashlib
import json
import os
import re
import shutil
import struct
import time
import zipfile
from contextlib import closing
from datetime import datetime, timedelta

import applog as LOG
import crypto_core as K
import schema as SC
import vault as VT

from db import _new_conn, _persist, _serialize, db, init_db, q
from storage import (
    BACKUP_EVERY_DAYS, BASE, BK_DIR, DB_ENC, DB_PATH,
    EXPORT_REMIND_DAYS, JOURNAL, KEEP_BACKUPS, NotUnlocked, PAT_DIR,
    SET_PATH, VAULT, _atomic_write, _faad, _lock,
    _mem, _wipe_file, ap, jload, jsave,
    new_rel, read_file, thumb_rel, write_enc)


# ───────────────────────── ترحيل بيانات الإصدارات السابقة ─────────────────────────
_OPAQUE = re.compile(r"patients/[^/]+/[0-9a-f]{16}\.bin$")


def _migrate_legacy_files():
    """يشفّر الصور/المرفقات القديمة ويعيد تسميتها بأسماء معتمة، ثم يمحو القديم وأي ملف غير مُشار إليه."""
    keep, old = set(), []
    with closing(db()) as c, c:
        codes = {r["id"]: r["code"] for r in c.execute("SELECT id, code FROM patients")}

        def move(rel, code):
            if not rel or not os.path.isfile(ap(rel)):
                return rel
            with open(ap(rel), "rb") as f:
                already = K.is_encrypted(f.read(4))
            if already and _OPAQUE.fullmatch(rel):
                keep.add(rel)
                return rel
            new = new_rel(code)
            write_enc(new, read_file(rel))
            keep.add(new)
            old.append(ap(rel))
            return new
        for pid, code in codes.items():
            row = c.execute("SELECT photo_before, photo_after, photo_lab FROM patients WHERE id=?", (pid,)).fetchone()
            for key in ("photo_before", "photo_after", "photo_lab"):
                new = move(row[key], code)
                if new != row[key]:
                    c.execute(f"UPDATE patients SET {key}=? WHERE id=?", (new, pid))
            c.execute("UPDATE patients SET folder=? WHERE id=?", (code, pid))
            for a in c.execute("SELECT id, path FROM attachments WHERE patient_id=?", (pid,)).fetchall():
                new = move(a["path"], code)
                if new != a["path"]:
                    c.execute("UPDATE attachments SET path=? WHERE id=?", (new, a["id"]))
        for ev in c.execute("SELECT id, patient_id, photo_before, photo_after FROM events").fetchall():
            for key in ("photo_before", "photo_after"):
                new = move(ev[key], codes.get(ev["patient_id"], "PT-00000"))
                if new != ev[key]:
                    c.execute(f"UPDATE events SET {key}=? WHERE id=?", (new, ev["id"]))
    for path in old:                     # بعد نجاح الحفظ فقط
        _wipe_file(path)
    for rel in list(keep):                           # مصغّرات الصور المحتفظ بها ليست يتيمة
        if os.path.isfile(ap(thumb_rel(rel))):
            keep.add(thumb_rel(rel))
    for root, _, files in os.walk(PAT_DIR):          # أي ملف غير مُشار إليه = يتيم
        for fn in files:
            full = os.path.join(root, fn)
            if os.path.relpath(full, BASE).replace(os.sep, "/") not in keep:
                _wipe_file(full)
    for root, dirs, _ in os.walk(PAT_DIR, topdown=False):
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except OSError:
                pass


def _migrate_legacy_backups():
    for fn in os.listdir(BK_DIR):
        if not fn.endswith(".zip"):
            continue
        zp = os.path.join(BK_DIR, fn)
        try:
            with zipfile.ZipFile(zp) as z, _bk_open(zp[:-4] + BK_EXT) as w:
                if "myclinic.db" not in z.namelist():
                    raise ValueError("not a backup")
                w.add("__db__", b"\x01" + z.read("myclinic.db"))
                for m in z.namelist():
                    if m.startswith("patients/") and not m.endswith("/") and ".." not in m:
                        w.add(m, z.read(m))
            os.remove(zp)
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as ex:   # الأرشيف القديم يبقى كما هو ويُعاد المحاولة لاحقاً
            LOG.log_exc("migrate_legacy_backup", ex)
            try:
                os.remove(zp[:-4] + BK_EXT)                                  # لا نترك نسخة جديدة ناقصة
            except OSError as ex2:
                LOG.log_exc("migrate_legacy_backup_cleanup", ex2)


def _migrate_all_legacy():
    st = jload(SET_PATH, {})
    if st.get("enc_v") == 2:
        return
    if os.path.exists(DB_ENC):
        for suffix in ("", "-wal", "-shm", "-journal"):
            if os.path.exists(DB_PATH + suffix):
                _wipe_file(DB_PATH + suffix)
    _migrate_legacy_files()
    _migrate_legacy_backups()
    st = jload(SET_PATH, {})
    st["enc_v"] = 2
    jsave(SET_PATH, st)


# ───────────────────────── النسخ الاحتياطي (مشفّر) ─────────────────────────
# النسخة = حاوية .shbk: ترويسة الحساب (ملح + DEK مغلَّف) ثم سجلات (قاعدة البيانات + الملفات)، كل سجل مشفّر
# ومصادَق على حدة. استعادتها على جهاز آخر تتطلب كلمة مرور الحساب الذي أُخذت منه النسخة.
BK_EXT = ".shbk"


_BK_MAGIC = b"SHBK1"


_BK_FMT = 2                      # 2: aad="bk2" + سجل ختامي مصادَق (عدد + بصمة) يكشف الاقتطاع وحذف/إعادة ترتيب السجلات


_BK_END = "__end__"


_BK_MAX_REC = 200 * 1024 * 1024  # سقف حجم السجل الواحد (ملف تالف قد يدّعي 4 جيجابايت فيُنهك الذاكرة)


def _bk_aad(fmt):
    return b"bk2" if fmt >= 2 else b"bk"


class _bk_open:
    """كاتب حاوية نسخة احتياطية (بثّ تدريجي إلى القرص). legacy=True ينتج الصيغة 1 (للاختبار فقط)."""

    def __init__(self, path, legacy=False):
        self.path, self.tmp, self.fmt = path, path + ".tmp", (1 if legacy else _BK_FMT)

    def __enter__(self):
        self.f = open(self.tmp, "wb")
        self.n, self.h = 0, hashlib.sha256()
        hdr = dict(VAULT.public_header())
        if self.fmt >= 2:
            hdr["fmt"] = self.fmt
        hb = json.dumps(hdr).encode()
        self.f.write(_BK_MAGIC + struct.pack(">I", len(hb)) + hb)
        return self

    def _write(self, name, data):
        nb = name.encode("utf-8")
        sealed = K.seal(VAULT.dek, struct.pack(">H", len(nb)) + nb + data, aad=_bk_aad(self.fmt))
        self.f.write(struct.pack(">I", len(sealed)) + sealed)

    def add(self, name, data: bytes):
        self._write(name, data)
        self.n += 1
        self.h.update(name.encode("utf-8") + b"\x00" + hashlib.sha256(data).digest())

    def __exit__(self, et, ev, tb):
        if et is None and self.fmt >= 2:
            self._write(_BK_END, json.dumps({"n": self.n, "h": self.h.hexdigest()}).encode())
        self.f.flush()
        os.fsync(self.f.fileno())
        self.f.close()
        if et is None:
            os.replace(self.tmp, self.path)
        else:
            try:
                os.remove(self.tmp)
            except OSError:
                pass
        return False


def _bk_header(path):
    with open(path, "rb") as f:
        if f.read(5) != _BK_MAGIC:
            raise ValueError("ملف النسخة الاحتياطية غير صالح")
        n = struct.unpack(">I", f.read(4))[0]
        if n > 1 << 20:
            raise ValueError("ملف النسخة الاحتياطية غير صالح")
        return json.loads(f.read(n)), f.tell()


def _bk_records(path, key):
    """يقرأ سجلات النسخة. الصيغة 2: يتحقق من السجل الختامي (العدد والبصمة) وإلا يرفع ValueError (نسخة مقتطعة/معدّلة).
    الصيغة 1 (نسخ قديمة): بلا سجل ختامي، فلا يمكن كشف الاقتطاع؛ يُسجَّل ذلك في السجل."""
    hdr, off = _bk_header(path)
    fmt = int(hdr.get("fmt", 1))
    if fmt not in (1, 2):
        raise ValueError("صيغة النسخة الاحتياطية أحدث من هذا التطبيق. حدّث التطبيق.")
    aad, size = _bk_aad(fmt), os.path.getsize(path)
    n, h, ended = 0, hashlib.sha256(), False
    with open(path, "rb") as f:
        f.seek(off)
        while True:
            lb = f.read(4)
            if not lb:
                break
            if len(lb) < 4:
                raise ValueError("النسخة الاحتياطية مقتطعة أو تالفة")
            ln = struct.unpack(">I", lb)[0]
            if ln > _BK_MAX_REC or ln > size - f.tell():
                raise ValueError("النسخة الاحتياطية مقتطعة أو تالفة")
            if ended:
                raise ValueError("النسخة الاحتياطية تحوي بيانات بعد نهايتها (معدّلة)")
            rec = K.open_sealed(key, f.read(ln), aad=aad)
            nl = struct.unpack(">H", rec[:2])[0]
            name, data = rec[2:2 + nl].decode("utf-8"), rec[2 + nl:]
            if fmt >= 2 and name == _BK_END:
                end = json.loads(data)
                if end.get("n") != n or end.get("h") != h.hexdigest():
                    raise ValueError("النسخة الاحتياطية ناقصة أو مُعدَّلة (عدد السجلات لا يطابق)")
                ended = True
                continue
            n += 1
            h.update(name.encode("utf-8") + b"\x00" + hashlib.sha256(data).digest())
            yield name, data
    if fmt >= 2 and not ended:
        raise ValueError("النسخة الاحتياطية مقتطعة (لا سجل ختامي)")
    if fmt == 1:
        LOG.log("backup_unverified", fmt=1)


def _bk_key(f):
    """ترتيب زمني حقيقي: وقت إنشاء الملف أولاً، ثم الطابع/اللاحقة _N رقمياً عند التساوي
    (الاسم وحده لا يكفي: _10 تسبق _2 أبجدياً، ويُعاد استخدام لاحقة محذوفة فتبدو الجديدة أقدم)."""
    m = re.match(r"myclinic_backup_(\d{8}_\d{6})(?:_(\d+))?", f)
    try:
        mt = os.stat(os.path.join(BK_DIR, f)).st_mtime_ns
    except OSError:
        mt = 0
    return (mt, m.group(1) if m else "", int(m.group(2) or 1) if m else 0, f)


def list_backups():
    os.makedirs(BK_DIR, exist_ok=True)
    return sorted([f for f in os.listdir(BK_DIR) if f.endswith(BK_EXT)], key=_bk_key, reverse=True)


def _prune_backups(keep=None, protect=None):
    """يحتفظ بأحدث `keep` نسخة داخل الجهاز ويحذف الأقدم. `protect`: مسار نسخة لا تُحذف أبداً (التي أُنشئت للتو)."""
    for f in list_backups()[(keep or KEEP_BACKUPS):]:
        if protect and os.path.abspath(os.path.join(BK_DIR, f)) == os.path.abspath(protect):
            continue
        try:
            os.remove(os.path.join(BK_DIR, f))
        except OSError:
            pass


def mark_exported():
    """يسجّل أن المستخدم صدّر نسخة إلى خارج مجلد التطبيق (يُفتح الملف في المتصفح للتنزيل)."""
    st = jload(SET_PATH, {})
    st["last_export"] = datetime.now().isoformat()
    jsave(SET_PATH, st)


def export_due():
    """(مستحق؟, عدد الأيام منذ آخر تصدير أو None). لا تذكير إن لم يوجد مرضى بعد."""
    if not q("SELECT 1 FROM patients LIMIT 1"):
        return False, None
    last = jload(SET_PATH, {}).get("last_export")
    if not last:
        return True, None
    try:
        days = (datetime.now() - datetime.fromisoformat(last)).days
    except ValueError:
        return True, None
    return days >= EXPORT_REMIND_DAYS, days


def make_backup(prune=True):
    if not VAULT.unlocked:
        raise NotUnlocked("سجّل الدخول أولاً")
    os.makedirs(BK_DIR, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    path, n = os.path.join(BK_DIR, f"myclinic_backup_{stamp}{BK_EXT}"), 1
    while os.path.exists(path):                       # لا نكتب فوق نسخة موجودة أبداً (قد تكون هي المصدر)
        n += 1
        path = os.path.join(BK_DIR, f"myclinic_backup_{stamp}_{n}{BK_EXT}")
    with _lock:
        db_blob = _serialize(_mem["conn"])
    total, skipped = 0, 0
    with _bk_open(path) as w:
        w.add("__db__", db_blob)
        for root, _, files in os.walk(PAT_DIR):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, BASE).replace(os.sep, "/")
                total += 1
                try:
                    w.add(rel, read_file(rel))
                except Exception as ex:               # ملف تالف/غير مقروء: لا نُسقط النسخة كلها لكن نُبلغ بوضوح
                    skipped += 1
                    LOG.log_exc("backup_skip", ex, file=os.path.basename(rel))
    st = jload(SET_PATH, {})
    st["last_backup"] = datetime.now().isoformat()
    st["last_backup_report"] = {"files": total, "skipped": skipped}
    jsave(SET_PATH, st)
    LOG.log("backup_done", files=total, skipped=skipped)
    if prune:
        _prune_backups(protect=path)
    return path


def backup_report() -> dict:
    """نتيجة آخر نسخة: {'files': عدد الملفات, 'skipped': ما تعذّر نسخه}. skipped > 0 يستوجب تنبيه المستخدم."""
    return jload(SET_PATH, {}).get("last_backup_report") or {"files": 0, "skipped": 0}


def auto_backup_if_due():
    st = jload(SET_PATH, {})
    last = st.get("last_backup")
    if not last:
        if q("SELECT 1 FROM patients LIMIT 1"):
            make_backup()
        else:
            st["last_backup"] = datetime.now().isoformat()
            jsave(SET_PATH, st)
        return
    if datetime.now() - datetime.fromisoformat(last) >= timedelta(days=BACKUP_EVERY_DAYS):
        make_backup()


def backup_needs_password(path) -> bool:
    """هل النسخة من حساب/مفتاح مختلف عن الحالي (فتحتاج كلمة مرور الحساب الأصلي)؟"""
    hdr, _ = _bk_header(path)
    try:
        K.open_sealed(VAULT.dek, bytes.fromhex(hdr["check"]), aad=b"check")
        return False
    except (K.CryptoError, KeyError, ValueError):
        return True


def restore_backup(path, password=None):
    """يستبدل كل البيانات بمحتوى النسخة (يُعاد تشفيرها بمفتاح هذا الحساب). تُؤخذ نسخة أمان قبل الاستبدال."""
    if backup_needs_password(path):
        hdr, _ = _bk_header(path)
        dek_b = VT.unwrap_with_password(hdr, password or "") or VT.unwrap_with_recovery_key(hdr, password or "")
        if dek_b is None:
            raise ValueError("كلمة المرور أو مفتاح الاسترداد غير صحيح (المطلوب: كلمة مرور الحساب وقت أخذ النسخة)")
    else:
        dek_b = VAULT.dek
    if q("SELECT 1 FROM patients LIMIT 1"):
        make_backup(prune=False)          # لا نحذف شيئاً قبل نجاح الاستعادة: قد يكون الملف المُستعاد من هذا المجلد
    new_dir = PAT_DIR + ".restore"
    shutil.rmtree(new_dir, ignore_errors=True)
    os.makedirs(new_dir)
    db_blob = None
    try:
        for name, data in _bk_records(path, dek_b):
            if name == "__db__":
                db_blob = data
                continue
            parts = name.split("/")
            if len(parts) < 3 or parts[0] != "patients" or any(p in ("", "..", ".") for p in parts):
                continue                                   # يمنع الخروج من المجلد (path traversal)
            target = os.path.join(new_dir, *parts[1:])
            os.makedirs(os.path.dirname(target), exist_ok=True)
            _atomic_write(target, K.encrypt_blob(VAULT.dek, data, aad=_faad("/".join(parts))))
        if db_blob is None:
            raise ValueError("النسخة لا تحوي قاعدة بيانات")
        new_conn = _new_conn(db_blob)
        ok = new_conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and \
            new_conn.execute("SELECT 1 FROM sqlite_master WHERE name='patients'").fetchone()
        if not ok:
            raise ValueError("قاعدة البيانات داخل النسخة تالفة")
        if SC.get_version(new_conn) > SC.LATEST:
            raise ValueError("هذه النسخة من إصدار أحدث من التطبيق الحالي. حدّث التطبيق ثم أعد الاستعادة.")
    except K.CryptoError:
        shutil.rmtree(new_dir, ignore_errors=True)
        raise ValueError("النسخة تالفة أو عُدّلت بعد إنشائها")
    except Exception:
        shutil.rmtree(new_dir, ignore_errors=True)
        raise
    with _lock:
        old = PAT_DIR + ".old"
        shutil.rmtree(old, ignore_errors=True)
        old_conn = _mem["conn"]
        # سجلّ التعافي: بصمة القاعدة الحالية؛ فإن انقطع التطبيق أُعيد الوضع السابق كاملاً عند الإقلاع التالي
        _atomic_write(JOURNAL, json.dumps({"db_sig": _file_sig(DB_ENC), "at": datetime.now().isoformat()}).encode())
        try:
            os.replace(PAT_DIR, old)
            os.replace(new_dir, PAT_DIR)
            _mem["conn"] = new_conn
            init_db()
            _persist()
        except BaseException as ex:
            LOG.log_exc("restore_swap", ex)
            res = recover_interrupted_restore()
            if res == "rolled_back":
                _mem["conn"] = old_conn
                new_conn.close()
            raise
    if old_conn is not None:
        old_conn.close()
    shutil.rmtree(old, ignore_errors=True)
    try:
        os.remove(JOURNAL)
    except OSError:
        pass
    _migrate_legacy_files()                                 # أسماء معتمة لأي ملفات من نسخ قديمة
    _prune_backups()


def _file_sig(path) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""


def recover_interrupted_restore():
    """يُستدعى عند الإقلاع (وعند فشل الاستعادة): إن وُجد سجلّ استعادة غير مكتمل يحسم الحالة بلا فقد بيانات:
       • قاعدة db.enc لم تتغيّر منذ بدء الاستبدال  → تُرجَع الصور القديمة (rolled_back)
       • القاعدة الجديدة حُفظت                     → يُكمَل التنظيف (committed)
    ويحذف بقايا مجلدات الاستعادة المؤقتة. يعيد None إن لم يكن هناك شيء."""
    new_dir, old = PAT_DIR + ".restore", PAT_DIR + ".old"
    try:
        with open(JOURNAL, encoding="utf-8") as f:
            j = json.load(f)
    except (OSError, ValueError):
        shutil.rmtree(new_dir, ignore_errors=True)
        return None
    if _file_sig(DB_ENC) != j.get("db_sig", ""):
        shutil.rmtree(old, ignore_errors=True)
        res = "committed"
    else:
        if os.path.isdir(old):
            shutil.rmtree(PAT_DIR, ignore_errors=True)
            os.replace(old, PAT_DIR)
        res = "rolled_back"
    shutil.rmtree(new_dir, ignore_errors=True)
    try:
        os.remove(JOURNAL)
    except OSError:
        pass
    LOG.log("restore_recovered", result=res)
    return res


# ───────────────────────── تعديل وحذف ─────────────────────────
def ensure_recent_backup(max_hours=24):
    """قبل أي حذف نهائي: نسخة احتياطية حديثة (آخر 24 ساعة) أو تُؤخذ الآن. يعيد مسارها أو None إن كانت حديثة."""
    names = list_backups()
    if names and time.time() - os.path.getmtime(os.path.join(BK_DIR, names[0])) < max_hours * 3600:
        return None
    return make_backup()
