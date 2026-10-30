# -*- coding: utf-8 -*-
"""
accounts.py — الحساب: إنشاء الحساب وتسجيل الدخول والقفل واستعادة كلمة المرور ومفتاح الاسترداد.
"""

import applog as LOG
import license_core as LC
import schema as SC

from backup import _migrate_all_legacy
from db import RollbackError, close_db, open_db
from licensing import lic_load
from share import _stop_server
from storage import SET_PATH, VAULT, VaultError, _mem, jload, jsave


# ───────────────────────── إدارة الحساب ─────────────────────────
def need_setup() -> bool:
    return not VAULT.exists()


def keys_ready() -> bool:
    return LC.keys_ready()


def setup_account(user, password, escrow=True):
    """ينشئ الحساب (اسم مستخدم + كلمة مرور) ويشفّر أي بيانات من إصدارات سابقة.
    الاسترداد عبر مدير البرنامج إلزامي (escrow=True دائماً في الواجهة). يعيد مفتاح الاسترداد للعرض مرة واحدة."""
    if not LC.keys_ready():
        raise VaultError("مفاتيح المطوّر غير مضبوطة في هذه النسخة (public_keys.py). شغّل: python keygen.py init")
    rkey = VAULT.create(user, password, LC.box_pub(), escrow=escrow)
    open_db()
    _migrate_all_legacy()
    return rkey


def unlock(user, password, accept_rollback=False) -> str:
    """'ok' | 'bad' | 'wait' (فترة انتظار بعد محاولات خاطئة؛ VAULT.wait_seconds).
    يرفع RollbackError إن بدا أن db.enc أقدم من آخر حفظ، ويُعاد الاستدعاء بـ accept_rollback=True بقرار المستخدم."""
    r = VAULT.login(user, password)
    if r == "ok":
        _mem["accept_rollback"] = bool(accept_rollback)
        try:
            open_db()
            _migrate_all_legacy()
        except RollbackError:
            lock_app()
            raise
        except SC.SchemaError as ex:
            lock_app()
            raise VaultError(str(ex))
        except Exception as ex:
            lock_app()
            LOG.log_exc("unlock_open_db", ex)
            raise VaultError(f"تعذّر فتح قاعدة البيانات المشفّرة ({type(ex).__name__}). "
                             f"إن كان الملف تالفاً فاستعد آخر نسخة احتياطية.")
        finally:
            _mem["accept_rollback"] = False
    return r


# ───────────────────────── القفل التلقائي ─────────────────────────
LOCK_CHOICES = (0, 30, 60, 180, 600)          # ثوانٍ: 0 = فور الخروج من التطبيق


LOCK_DEFAULT = 0


def lock_policy() -> int:
    """مهلة القفل عند الذهاب للخلفية بالثواني (0 = فوراً)."""
    v = jload(SET_PATH, {}).get("lock_after")
    return int(v) if v in LOCK_CHOICES else LOCK_DEFAULT


def set_lock_policy(seconds: int):
    if seconds not in LOCK_CHOICES:
        raise ValueError("قيمة غير مدعومة")
    st = jload(SET_PATH, {})
    st["lock_after"] = int(seconds)
    jsave(SET_PATH, st)


def lock_app():
    close_db()
    VAULT.lock()
    _stop_server()                      # يمسح أي ملفات مؤقتة (تقارير/مرفقات مفتوحة)


def reset_request_code() -> str:
    return VAULT.begin_reset(lic_load()["device_id"])


def reset_with_code(reply_code, new_password):
    VAULT.finish_reset(reply_code, new_password, lic_load()["device_id"], LC.box_pub())
    open_db()
    _migrate_all_legacy()


def reset_with_recovery_key(text, new_password):
    """استرداد كلمة المرور بمفتاح الاسترداد الذي يحتفظ به صاحب العيادة (دون المدير)."""
    VAULT.reset_with_recovery_key(text, new_password)
    open_db()
    _migrate_all_legacy()


def create_recovery_key() -> str:
    return VAULT.create_recovery_key()


def set_escrow(enabled: bool):
    VAULT.set_escrow(enabled, LC.box_pub() if enabled else None)


def ensure_escrow() -> bool:
    """الاسترداد عبر مدير البرنامج **إلزامي**: يُغلَّف مفتاح البيانات لمفتاح المدير العام لكل حساب (جديد أو قديم).
    يُستدعى بعد كل دخول؛ للحسابات القديمة التي أُنشئت بلا استرداد يُفعَّل تلقائياً. يعيد True إن غيّر شيئاً."""
    if not VAULT.unlocked or VAULT.escrow_enabled or not LC.keys_ready():
        return False
    VAULT.set_escrow(True, LC.box_pub())
    LOG.log("escrow_enforced")
    return True
