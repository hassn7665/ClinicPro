# -*- coding: utf-8 -*-
"""
vault.py — حساب المستخدم، كلمة المرور، ومفتاح تشفير البيانات.

التصميم (envelope encryption):
  • مفتاح البيانات DEK (32 بايت عشوائي) يشفّر قاعدة البيانات والصور والمرفقات والنسخ الاحتياطية.
  • DEK نفسه لا يُخزَّن إلا «مغلَّفاً»:
       1) بمفتاح مشتق من (اسم المستخدم + كلمة المرور) عبر PBKDF2          → الدخول العادي
       2) بالمفتاح العام للمدير (X25519)                                       → الاسترداد عند النسيان
  • بعد 5 محاولات خاطئة يُقفل الدخول ولا يُفتح إلا برمز يصدره المدير.
  • تغيير كلمة المرور أو إعادة تعيينها يُعيد تغليف DEK فقط، فلا حاجة لإعادة تشفير البيانات.

تنبيه صريح: عدّاد المحاولات يحمي من التخمين عبر واجهة التطبيق. أمّا من ينسخ ملفات التطبيق خارج الجهاز فيعتمد
أمان بياناته على قوة كلمة المرور (PBKDF2). لذلك يُفرض حدّ أدنى لطولها، ويُنصح بجملة مرور.
"""
import json
import math
import os
import secrets
import time

import crypto_core as K

BUILD = "2.7.0"                   # يجب أن يطابق core.APP_VERSION (يكشف خلط ملفات من إصدارات مختلفة)
FREE_ATTEMPTS = 3                 # محاولات خاطئة بلا تأخير؛ بعدها يبدأ التأخير المتصاعد (لا قفل نهائي)
_DELAYS = {3: 15, 4: 30, 5: 60, 6: 300, 7: 900}      # عدد المحاولات الخاطئة المتتالية → ثوانٍ قبل المحاولة التالية
MAX_DELAY = 3600                  # السقف: ساعة


def delay_for(n: int) -> int:
    return 0 if n < FREE_ATTEMPTS else _DELAYS.get(n, MAX_DELAY)


def _now() -> float:
    return time.time()
MIN_PASSWORD = 10                 # كان 6: الحدّ الأدنى لحساب جديد أو عند تغيير كلمة المرور (الحسابات القديمة تدخل كما هي)
PBKDF2_ITER = 600_000             # كان 300_000: يُرفع تلقائياً للحسابات القديمة عند أول دخول ناجح
MAX_ITER = 5_000_000              # سقف لقيمة iter القادمة من ترويسة غير موثّقة (نسخة احتياطية) كي لا تُجمّد التطبيق
RKEY_ITER = 200_000               # مفتاح الاسترداد عشوائي (96 بت) فلا يحتاج تمطيطاً ثقيلاً


class VaultError(Exception):
    pass


def norm_user(u: str) -> str:
    return " ".join((u or "").split()).lower()


_COMMON = {"1234567890", "0123456789", "0987654321", "12345678910", "password12", "password123", "passw0rd12",
           "qwertyuiop", "qwerty1234", "1q2w3e4r5t", "abcdefghij", "0000000000", "1111111111", "admin12345",
           "administrator", "clinic1234", "clinicpro1", "clinicpro12", "iloveyou12", "welcome123"}
_ROWS = "qwertyuiopasdfghjklzxcvbnm"


def _guessable(low: str) -> bool:
    """كلمات شائعة، تسلسلات (12345… / abcde…)، وصفوف لوحة المفاتيح."""
    if low in _COMMON:
        return True
    if len(low) >= 2 and all(abs(ord(b) - ord(a)) == 1 for a, b in zip(low, low[1:])):
        return True
    return len(low) >= 8 and (low in _ROWS or low in _ROWS[::-1])


def password_problem(pw: str, user: str = "") -> str | None:
    """يعيد نص المشكلة (بالعربية) أو None إن كانت كلمة المرور مقبولة. تُطبَّق على الإنشاء والتغيير والإعادة."""
    pw = pw or ""
    if len(pw) < MIN_PASSWORD:
        return f"كلمة المرور قصيرة (الحد الأدنى {MIN_PASSWORD} خانات — الأفضل جملة مرور)"
    if len(set(pw)) < 5:
        return "كلمة المرور ضعيفة جداً (أحرف متكررة)"
    low = pw.lower()
    if _guessable(low):
        return "كلمة المرور شائعة وسهلة التخمين، اختر غيرها"
    u = norm_user(user).replace(" ", "")
    if len(u) >= 3 and u in low.replace(" ", ""):
        return "لا تضع اسم المستخدم داخل كلمة المرور"
    classes = sum((any(c.isalpha() for c in pw), any(c.isdigit() for c in pw),
                   any(not c.isalnum() for c in pw)))
    if len(pw) < 14 and classes < 2:
        return "اخلط الحروف بالأرقام أو الرموز، أو استخدم جملة مرور من 14 خانة فأكثر"
    return None


def unwrap_with_password(header: dict, password: str) -> bytes | None:
    """يعيد DEK من ترويسة (محفوظة أو من نسخة احتياطية) أو None إن كانت كلمة المرور خاطئة."""
    try:
        it = int(header["iter"])
        if not 1 <= it <= MAX_ITER:
            return None
        kek = K.kdf_password(password, bytes.fromhex(header["salt"]), it, norm_user(header["user"]))
        return K.open_sealed(kek, bytes.fromhex(header["wrap"]), aad=b"dek")
    except (K.CryptoError, KeyError, ValueError, TypeError):
        return None


def unwrap_with_recovery_key(header: dict, text: str) -> bytes | None:
    """يعيد DEK بمفتاح الاسترداد الذي يملكه صاحب العيادة (بلا حاجة للمدير) أو None."""
    try:
        rk = header["rk"]
        it = int(rk["iter"])
        if not 1 <= it <= MAX_ITER:
            return None
        raw = K.unpack_code(text)                       # يتسامح مع الشرطات والمسافات وحالة الأحرف ويتحقق من CRC
        kek = K.kdf_password(raw.hex(), bytes.fromhex(rk["salt"]), it, "rkey")
        return K.open_sealed(kek, bytes.fromhex(rk["wrap"]), aad=b"rkey")
    except (K.CryptoError, KeyError, ValueError, TypeError):
        return None


class Vault:
    def __init__(self, base: str):
        self.path = os.path.join(base, "vault.json")
        self.dek: bytes | None = None
        self.h: dict | None = None
        if self.exists():
            self._load()

    # ── ملف الترويسة ──
    def exists(self) -> bool:
        return os.path.exists(self.path)

    def _load(self):
        with open(self.path, encoding="utf-8") as f:
            self.h = json.load(f)
        if self.h.get("locked"):                     # قفل صلب من إصدار قديم ← تأخير متصاعد (لا حاجة للمدير)
            n = max(int(self.h.get("attempts", 0)), 5)
            now = _now()
            self.h.update(locked=False, attempts=n, last_try=now, next_try=now + delay_for(n))
            try:
                self._save()
            except OSError:
                pass

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.h, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    # ── حالة ──
    @property
    def unlocked(self) -> bool:
        return self.dek is not None

    @property
    def user(self) -> str:
        return (self.h or {}).get("user", "")

    @property
    def wait_seconds(self) -> int:
        """الثواني المتبقية قبل السماح بمحاولة دخول (0 = مسموح). رجوع ساعة الجهاز للوراء لا يختصر الانتظار."""
        h = self.h or {}
        nt, lt = float(h.get("next_try") or 0), float(h.get("last_try") or 0)
        if nt <= 0:
            return 0
        now = _now()
        if now < lt - 5:
            return delay_for(int(h.get("attempts", 0)))
        return max(int(math.ceil(nt - now)), 0)

    @property
    def locked_out(self) -> bool:
        """في فترة انتظار بعد محاولات خاطئة (ليس قفلاً نهائياً)."""
        return self.wait_seconds > 0

    @property
    def attempts_left(self) -> int:
        """محاولات خاطئة متبقية قبل أن يبدأ التأخير."""
        return max(FREE_ATTEMPTS - int((self.h or {}).get("attempts", 0)), 0)

    @property
    def dbgen(self) -> int:
        """آخر «جيل» حُفظ للقاعدة المشفّرة (لكشف إرجاع db.enc إلى نسخة أقدم)."""
        return int((self.h or {}).get("dbgen", 0) or 0)

    def set_dbgen(self, n: int):
        self.h["dbgen"] = int(n)
        self._save()

    @property
    def escrow_enabled(self) -> bool:
        """هل يستطيع مدير البرنامج المساعدة في استرجاع كلمة المرور لهذا الحساب؟"""
        return bool(self.h and self.h.get("recovery"))

    @property
    def has_recovery_key(self) -> bool:
        return bool(self.h and self.h.get("rk"))

    def lock(self):
        self.dek = None

    def public_header(self) -> dict:
        """الجزء الذي يُنسَخ داخل النسخ الاحتياطية (لا يحوي عدّاد المحاولات ولا الحالة المؤقتة)."""
        return {k: self.h[k] for k in ("user", "salt", "iter", "wrap", "recovery", "check", "rk") if k in self.h}

    # ── إنشاء الحساب ──
    def create(self, user: str, password: str, admin_box_pub: bytes, escrow: bool = False) -> str:
        """ينشئ الحساب ويعيد «مفتاح الاسترداد» (يُعرض لصاحب الحساب مرة واحدة ليحفظه)."""
        user = " ".join((user or "").split())
        if len(user) < 3:
            raise VaultError("اسم المستخدم قصير (3 أحرف على الأقل)")
        bad = password_problem(password, user)
        if bad:
            raise VaultError(bad)
        dek = secrets.token_bytes(32)
        salt = secrets.token_bytes(16)
        kek = K.kdf_password(password, salt, PBKDF2_ITER, norm_user(user))
        self.h = {
            "v": 1, "user": user, "salt": salt.hex(), "iter": PBKDF2_ITER,
            "wrap": K.seal(kek, dek, aad=b"dek").hex(),
            "recovery": K.recovery_wrap(dek, admin_box_pub).hex() if escrow else "",
            "check": K.seal(dek, b"myclinic-ok", aad=b"check").hex(),
            "attempts": 0, "locked": False, "pending": None, "next_try": 0, "last_try": 0, "dbgen": 0,
        }
        self.dek = dek
        rkey = self._set_rk()
        self._save()
        return rkey

    # ── الدخول ──
    def login(self, user: str, password: str) -> str:
        """'ok' | 'bad' | 'wait' (في فترة انتظار؛ لا تُحتسب محاولة). كل محاولة فاشلة (اسم أو كلمة) تُحتسب
        والتأخير يتصاعد: 3 مجاناً ثم 15 ث، 30 ث، دقيقة، 5 د، 15 د، ثم ساعة كحدّ أقصى."""
        if self.wait_seconds > 0:
            return "wait"
        probe = dict(self.h, user=user or "")
        dek = unwrap_with_password(probe, password or "")
        if dek is None or norm_user(user) != norm_user(self.h["user"]):
            n, now = int(self.h.get("attempts", 0)) + 1, _now()
            d = delay_for(n)
            self.h.update(attempts=n, last_try=now, next_try=(now + d) if d else 0)
            self._save()
            return "bad"
        if self.h.get("attempts") or self.h.get("next_try"):
            self.h.update(attempts=0, next_try=0, last_try=0)
            self._save()
        self.dek = dek
        if int(self.h.get("iter", 0)) < PBKDF2_ITER:      # ترقية صامتة لقوة الاشتقاق (كلمة المرور معنا الآن)
            try:
                self._rewrap(password)
            except OSError:
                pass
        return "ok"

    def change_password(self, old: str, new: str):
        if unwrap_with_password(self.h, old) is None:
            raise VaultError("كلمة المرور الحالية غير صحيحة")
        bad = password_problem(new, self.h["user"])
        if bad:
            raise VaultError(bad)
        self._rewrap(new)

    def _rewrap(self, password: str):
        salt = secrets.token_bytes(16)
        kek = K.kdf_password(password, salt, PBKDF2_ITER, norm_user(self.h["user"]))
        self.h.update(salt=salt.hex(), iter=PBKDF2_ITER, wrap=K.seal(kek, self.dek, aad=b"dek").hex())
        self._save()

    # ── استرداد كلمة المرور بكود المدير ──
    def begin_reset(self, device_id_hex: str) -> str:
        """يعيد «رمز الطلب» الذي يُرسَل للمدير. يبقى ثابتاً حتى اكتمال الإعادة."""
        if not self.escrow_enabled:
            raise VaultError("الاسترداد عبر مدير البرنامج غير مفعّل لهذا الحساب. استخدم مفتاح الاسترداد.")
        pend = self.h.get("pending")
        if not pend:
            r_priv, _ = K.x25519_keypair()
            pend = self.h["pending"] = {"r": r_priv.hex()}
            self._save()
        r_pub = K.x25519_pub(bytes.fromhex(pend["r"]))
        return K.reset_request(bytes.fromhex(device_id_hex), bytes.fromhex(self.h["recovery"]), r_pub)

    def finish_reset(self, reply_code: str, new_password: str, device_id_hex: str, admin_box_pub: bytes):
        pend = self.h.get("pending")
        if not pend:
            raise VaultError("لا يوجد طلب إعادة تعيين مفتوح. اضغط «إنشاء رمز الطلب» أولاً.")
        bad = password_problem(new_password, self.h["user"])
        if bad:
            raise VaultError(bad)
        try:
            dek = K.reset_open(bytes.fromhex(pend["r"]), admin_box_pub, bytes.fromhex(device_id_hex), reply_code)
            K.open_sealed(dek, bytes.fromhex(self.h["check"]), aad=b"check")      # تأكيد أنه مفتاح هذا الحساب
        except K.CryptoError as ex:
            raise VaultError(f"رمز الإعادة غير صالح: {ex}")
        self.dek = dek
        self._rewrap(new_password)
        self.h.update(attempts=0, locked=False, pending=None, next_try=0, last_try=0)
        self._save()

    # ── مفتاح الاسترداد (بيد صاحب العيادة، بلا مدير) ──
    def _set_rk(self) -> str:
        """يولّد مفتاحاً جديداً ويغلّف به DEK (يستبدل القديم). يعيد النص المعروض للمستخدم."""
        text = K.pack_code(secrets.token_bytes(12))       # 96 بت + CRC، مجمّع XXXXX-XXXXX-…
        raw = K.unpack_code(text)
        salt = secrets.token_bytes(16)
        kek = K.kdf_password(raw.hex(), salt, RKEY_ITER, "rkey")
        self.h["rk"] = {"salt": salt.hex(), "iter": RKEY_ITER, "wrap": K.seal(kek, self.dek, aad=b"rkey").hex()}
        return text

    def create_recovery_key(self) -> str:
        """إنشاء/تجديد مفتاح الاسترداد (يتطلب أن يكون الحساب مفتوحاً). المفتاح السابق يتوقف."""
        if not self.unlocked:
            raise VaultError("سجّل الدخول أولاً")
        text = self._set_rk()
        self._save()
        return text

    def reset_with_recovery_key(self, text: str, new_password: str):
        """نسيان كلمة المرور: يفتح الحساب بمفتاح الاسترداد ويضبط كلمة جديدة. يمسح القفل وعدّاد المحاولات."""
        if not self.has_recovery_key:
            raise VaultError("لا يوجد مفتاح استرداد لهذا الحساب.")
        bad = password_problem(new_password, self.h["user"])
        if bad:
            raise VaultError(bad)
        dek = unwrap_with_recovery_key(self.h, text)
        if dek is None:
            raise VaultError("مفتاح الاسترداد غير صحيح — تأكد من نسخه كاملاً.")
        try:
            K.open_sealed(dek, bytes.fromhex(self.h["check"]), aad=b"check")
        except K.CryptoError:
            raise VaultError("مفتاح الاسترداد لا يطابق هذا الحساب")
        self.dek = dek
        self._rewrap(new_password)
        self.h.update(attempts=0, locked=False, pending=None, next_try=0, last_try=0)
        self._save()

    # ── الاسترداد عبر مدير البرنامج (اختياري) ──
    def set_escrow(self, enabled: bool, admin_box_pub: bytes | None = None):
        if not self.unlocked:
            raise VaultError("سجّل الدخول أولاً")
        if enabled:
            if not admin_box_pub:
                raise VaultError("مفاتيح المطوّر غير مضبوطة في هذه النسخة")
            self.h["recovery"] = K.recovery_wrap(self.dek, admin_box_pub).hex()
        else:
            if not self.has_recovery_key:
                raise VaultError("أنشئ مفتاح الاسترداد أولاً، فبدونه لن تملك أي طريقة لاسترجاع كلمة المرور.")
            self.h["recovery"] = ""
            self.h["pending"] = None
        self._save()
