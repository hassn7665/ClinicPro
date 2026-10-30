# -*- coding: utf-8 -*-
"""
license_core.py — أكواد التفعيل الموقّعة (Ed25519) لتطبيق My Clinic.

• الكود موقَّع بمفتاح المدير الخاص؛ التطبيق يحمل المفتاح العام فقط، فلا يمكن تزوير كود حتى لو فُكّت حزمة APK.
• الكود مرتبط بمعرّف الجهاز (Device ID)، ويحمل رقماً تسلسلياً (يمنع إعادة استخدام كود قديم) ومدة الاشتراك.
• المدد المتاحة: شهر، 3 أشهر، 6 أشهر، سنة.
• صلاحية التسليم: الكود يجب تفعيله خلال MAX_CODE_AGE_DAYS يوماً من إصداره.

الاستعمال من المدير:  python keygen.py        (واجهة رسومية)  أو  python keygen.py activate <DEVICE_ID> --plan 3
"""
import struct
from datetime import date, timedelta

import crypto_core as K

try:
    import public_keys as PK
except ImportError:          # ملف المفاتيح غير موجود
    PK = None

PLANS = {1: "شهر", 3: "3 أشهر", 6: "6 أشهر", 12: "سنة"}     # الأشهر → اسم الخطة
CLOCK_FIX = 0      # «مدة» خاصة: كود فك قفل التاريخ (لا يمدّد الاشتراك). يحمل تاريخ الإصدار الحقيقي موقّعاً.
LIC_VER = 1            # صيغة الكود بمفتاح رقم 0 (التوافق الكامل مع الأكواد الصادرة سابقاً)
LIC_VER_KID = 2        # صيغة بمعرّف مفتاح (kid): تُستعمل فقط حين يكون kid > 0، أي بعد تدوير مفتاح التوقيع
BUILD = "2.7.0"        # يجب أن يطابق core.APP_VERSION (يكشف خلط ملفات من إصدارات مختلفة)
EPOCH = date(2025, 1, 1)
MAX_CODE_AGE_DAYS = 60
_MSG = b"MYCLINIC-LIC1"
_MSG2 = b"MYCLINIC-LIC2"                # فصل نطاق التوقيع للصيغة 2 (kid داخل الحمولة الموقّعة)
_LEN = 1 + 4 + 2 + 1 + 2 + 64        # إصدار + جهاز + تسلسلي + مدة + تاريخ الإصدار + توقيع
_LEN2 = _LEN + 1                     # + kid


class LicenseError(Exception):
    """رسالة عربية جاهزة للعرض للمستخدم."""


def reload_keys():
    """يعيد قراءة public_keys.py (بعد أن يولّدها keygen تلقائياً على حاسوب المطوّر)."""
    global PK
    import importlib
    importlib.invalidate_caches()
    try:
        import public_keys as _pk
        PK = importlib.reload(_pk)
    except ImportError:
        PK = None


def _hex_key(name):
    v = getattr(PK, name, "") if PK else ""
    try:
        b = bytes.fromhex(v)
    except ValueError:
        return None
    return b if len(b) == 32 else None


def sign_pub(kid: int = 0):
    """المفتاح العام للتحقق. kid=0 هو SIGN_PUB؛ بعد تدوير المفتاح يُضاف القديم/الجديد في SIGN_PUBS = {kid: hex}."""
    if kid == 0:
        return _hex_key("SIGN_PUB")
    v = (getattr(PK, "SIGN_PUBS", None) or {}).get(kid) if PK else None
    try:
        b = bytes.fromhex(v or "")
    except ValueError:
        return None
    return b if len(b) == 32 else None


def box_pub():
    return _hex_key("BOX_PUB")


def keys_ready() -> bool:
    return sign_pub() is not None and box_pub() is not None


# ───────────── جهة المدير ─────────────
def make_code(sign_seed: bytes, device_id_hex: str, serial: int, months: int, issued: date | None = None,
              kid: int = 0) -> str:
    if months not in PLANS and months != CLOCK_FIX:
        raise ValueError(f"مدة غير مدعومة: {months}")
    dev = bytes.fromhex(device_id_hex)
    if len(dev) != 4:
        raise ValueError("معرّف الجهاز يجب أن يكون 8 خانات hex")
    if not 1 <= serial <= 65535:
        raise ValueError("الرقم التسلسلي خارج النطاق")
    if not 0 <= kid <= 255:
        raise ValueError("معرّف المفتاح خارج النطاق")
    days = ((issued or date.today()) - EPOCH).days
    body = dev + struct.pack(">HBH", serial, months, days)
    if kid == 0:
        payload, msg = bytes([LIC_VER]) + body, _MSG
    else:
        payload, msg = bytes([LIC_VER_KID, kid]) + body, _MSG2
    return K.pack_code(payload + K.ed_sign(sign_seed, msg + payload))


# ───────────── جهة التطبيق ─────────────
def parse_code_ex(code: str, device_id_hex: str, today: date | None = None):
    """يعيد (serial, months, تاريخ_الإصدار) أو يرفع LicenseError. months == CLOCK_FIX لكود فك قفل التاريخ."""
    if sign_pub() is None:
        raise LicenseError("لم تُضبط مفاتيح التفعيل في هذه النسخة (public_keys.py). تواصل مع المطوّر.")
    try:
        raw = K.unpack_code(code)
    except K.CryptoError as ex:
        raise LicenseError(f"كود التفعيل غير صحيح: {ex}")
    if len(raw) == _LEN and raw[0] == LIC_VER:
        kid, msg, head = 0, _MSG, 1
    elif len(raw) == _LEN2 and raw[0] == LIC_VER_KID:
        kid, msg, head = raw[1], _MSG2, 2
    else:
        raise LicenseError("هذا ليس كود تفعيل (ربما هو رمز آخر).")
    pub = sign_pub(kid)
    if pub is None:
        raise LicenseError("كود التفعيل صادر بمفتاح غير معروف لهذه النسخة. حدّث التطبيق إلى آخر إصدار.")
    payload, sig = raw[:-64], raw[-64:]
    if not K.ed_verify(pub, msg + payload, sig):
        raise LicenseError("كود التفعيل غير صحيح أو غير صادر من المطوّر.")
    if payload[head:head + 4] != bytes.fromhex(device_id_hex):
        raise LicenseError("هذا الكود مخصّص لجهاز آخر. تأكد من معرّف الجهاز المرسل.")
    serial, months, days = struct.unpack(">HBH", payload[head + 4:])
    if months not in PLANS and months != CLOCK_FIX:
        raise LicenseError("مدة الاشتراك في الكود غير معروفة.")
    age = ((today or date.today()) - EPOCH).days - days
    if age > MAX_CODE_AGE_DAYS:
        raise LicenseError("انتهت مهلة تفعيل هذا الكود. اطلب كوداً جديداً.")
    return serial, months, EPOCH + timedelta(days=days)


def parse_code(code: str, device_id_hex: str, today: date | None = None):
    """يعيد (serial, months) لكود اشتراك، أو يرفع LicenseError برسالة عربية."""
    serial, months, _ = parse_code_ex(code, device_id_hex, today)
    if months == CLOCK_FIX:
        raise LicenseError("هذا كود فك قفل التاريخ وليس كود اشتراك.")
    return serial, months
