# -*- coding: utf-8 -*-
"""
crypto_core.py — عمليات التشفير لتطبيق Clinic Pro (مكتبة بايثون القياسية فقط، بلا أي حزم خارجية).

لماذا بلا حزم خارجية؟ لأن التطبيق يُبنى لأندرويد عبر Flet، وحزم مثل `cryptography` قد لا تتوفر
لكل بنية. كل ما هنا مبني على hashlib/hmac/secrets، ومُتحقَّق منه بمتجهات RFC الرسمية.

المكوّنات:
  • seal / open_sealed : تشفير مُصادَق (SHAKE-256 كمولّد تدفق + HMAC-SHA256، "encrypt-then-MAC").
  • kdf_password       : اشتقاق مفتاح من كلمة المرور (PBKDF2-HMAC-SHA256).
  • x25519             : تبادل مفاتيح (RFC 7748) — يُستخدم لرموز إعادة التعيين.
  • ed_sign / ed_verify: توقيع (RFC 8032, Ed25519) — يُستخدم لأكواد التفعيل.
  • pack_code / unpack_code : تحويل بيانات ثنائية إلى رمز نصي (Base32 + CRC) سهل النسخ.

ملاحظة أمان: الشيفرات هنا مكتوبة للاستخدام دون اتصال على جهاز المستخدم، وليست مقاومة لهجمات
التوقيت الجانبية (side-channel) كمكتبات الخادم. لا تستخدمها لحماية مفاتيح على خادم عام.
"""
import base64
import hashlib
import hmac
import secrets
import struct
import zlib


class CryptoError(Exception):
    """فشل التحقق أو فك التشفير (مفتاح خاطئ أو بيانات معبوث بها)."""


# ═══════════════════════ أدوات أساسية ═══════════════════════
def sha256(*parts: bytes) -> bytes:
    h = hashlib.sha256()
    for p in parts:
        h.update(p)
    return h.digest()


def _xor(a: bytes, b: bytes) -> bytes:
    n = len(a)
    if not n:
        return b""
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(n, "big")


def kdf_password(password: str, salt: bytes, iterations: int, label: str = "") -> bytes:
    """يشتق مفتاحاً 32 بايت من كلمة المرور (label = اسم المستخدم لربط المفتاح به)."""
    pw = (label + "\x00" + password).encode("utf-8")
    return hashlib.pbkdf2_hmac("sha256", pw, salt, iterations, 32)


# ═══════════════════════ التشفير المُصادَق ═══════════════════════
_CHUNK = 1 << 20          # 1 ميغابايت لكل كتلة تدفق
_NONCE = 12
_TAG = 16


def _subkeys(key: bytes):
    if len(key) != 32:
        raise CryptoError("طول المفتاح غير صحيح")
    return (hmac.new(key, b"shifa-enc", hashlib.sha256).digest(),
            hmac.new(key, b"shifa-mac", hashlib.sha256).digest())


def _stream_xor(enc_key: bytes, nonce: bytes, data: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(data), _CHUNK):
        chunk = data[i:i + _CHUNK]
        ks = hashlib.shake_256(enc_key + nonce + struct.pack(">I", i // _CHUNK)).digest(len(chunk))
        out += _xor(chunk, ks)
    return bytes(out)


def seal(key: bytes, plaintext: bytes, aad: bytes = b"") -> bytes:
    """nonce(12) ‖ ciphertext ‖ tag(16).  يُرمَّز aad ضمن الوسم دون تضمينه في الناتج."""
    enc, mac = _subkeys(key)
    nonce = secrets.token_bytes(_NONCE)
    ct = _stream_xor(enc, nonce, plaintext)
    tag = hmac.new(mac, struct.pack(">Q", len(aad)) + aad + nonce + ct, hashlib.sha256).digest()[:_TAG]
    return nonce + ct + tag


def open_sealed(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    if len(blob) < _NONCE + _TAG:
        raise CryptoError("بيانات مشفّرة قصيرة")
    enc, mac = _subkeys(key)
    nonce, ct, tag = blob[:_NONCE], blob[_NONCE:-_TAG], blob[-_TAG:]
    good = hmac.new(mac, struct.pack(">Q", len(aad)) + aad + nonce + ct, hashlib.sha256).digest()[:_TAG]
    if not hmac.compare_digest(tag, good):
        raise CryptoError("فشل التحقق: مفتاح خاطئ أو بيانات تالفة")
    return _stream_xor(enc, nonce, ct)


FILE_MAGIC = b"SHF1"


def encrypt_blob(key: bytes, data: bytes, aad: bytes = b"") -> bytes:
    """حاوية ملف: MAGIC ‖ sealed."""
    return FILE_MAGIC + seal(key, data, aad)


def is_encrypted(head: bytes) -> bool:
    return head[:4] == FILE_MAGIC


def decrypt_blob(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    if not is_encrypted(blob):
        raise CryptoError("الملف غير مشفّر بصيغة التطبيق")
    return open_sealed(key, blob[4:], aad)


# ═══════════════════════ X25519 (RFC 7748) ═══════════════════════
_P = 2 ** 255 - 19
_A24 = 121665


def x25519(k: bytes, u: bytes) -> bytes:
    if len(k) != 32 or len(u) != 32:
        raise CryptoError("x25519: طول غير صحيح")
    kb = bytearray(k)
    kb[0] &= 248
    kb[31] &= 127
    kb[31] |= 64
    kn = int.from_bytes(kb, "little")
    x1 = int.from_bytes(u, "little") & ((1 << 255) - 1)
    x2, z2, x3, z3, swap = 1, 0, x1, 1, 0
    for t in range(254, -1, -1):
        kt = (kn >> t) & 1
        swap ^= kt
        if swap:
            x2, x3, z2, z3 = x3, x2, z3, z2
        swap = kt
        a = (x2 + z2) % _P
        aa = a * a % _P
        b = (x2 - z2) % _P
        bb = b * b % _P
        e = (aa - bb) % _P
        c = (x3 + z3) % _P
        d = (x3 - z3) % _P
        da = d * a % _P
        cb = c * b % _P
        x3 = (da + cb) ** 2 % _P
        z3 = x1 * ((da - cb) ** 2) % _P
        x2 = aa * bb % _P
        z2 = e * (aa + _A24 * e) % _P
    if swap:
        x2, x3, z2, z3 = x3, x2, z3, z2
    out = x2 * pow(z2, _P - 2, _P) % _P
    if out == 0:                     # نقطة ضعيفة (رتبة صغيرة، ومنها u=0) → ناتج صفري: يُرفض دائماً (RFC 7748 §6.1)
        raise CryptoError("x25519: مفتاح عام غير صالح")
    return out.to_bytes(32, "little")


_BASE9 = (9).to_bytes(32, "little")


def x25519_pub(priv: bytes) -> bytes:
    return x25519(priv, _BASE9)


def x25519_keypair():
    priv = secrets.token_bytes(32)
    return priv, x25519_pub(priv)


# ═══════════════════════ Ed25519 (RFC 8032) ═══════════════════════
_Q = 2 ** 252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P
_SQRT_M1 = pow(2, (_P - 1) // 4, _P)


def _recover_x(y, sign):
    if y >= _P:
        return None
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    if x2 == 0:
        return None if sign else 0
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P:
        x = x * _SQRT_M1 % _P
    if (x * x - x2) % _P:
        return None
    if (x & 1) != sign:
        x = _P - x
    return x


_GY = 4 * pow(5, _P - 2, _P) % _P
_GX = _recover_x(_GY, 0)
_G = (_GX, _GY, 1, _GX * _GY % _P)
_ID = (0, 1, 1, 0)


def _add(p1, p2):
    a = (p1[1] - p1[0]) * (p2[1] - p2[0]) % _P
    b = (p1[1] + p1[0]) * (p2[1] + p2[0]) % _P
    c = 2 * p1[3] * p2[3] * _D % _P
    d = 2 * p1[2] * p2[2] % _P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % _P, g * h % _P, f * g % _P, e * h % _P)


def _mul(s, pt):
    r = _ID
    while s > 0:
        if s & 1:
            r = _add(r, pt)
        pt = _add(pt, pt)
        s >>= 1
    return r


def _eq(p1, p2):
    if (p1[0] * p2[2] - p2[0] * p1[2]) % _P:
        return False
    return (p1[1] * p2[2] - p2[1] * p1[2]) % _P == 0


def _compress(pt):
    zi = pow(pt[2], _P - 2, _P)
    x, y = pt[0] * zi % _P, pt[1] * zi % _P
    return (y | ((x & 1) << 255)).to_bytes(32, "little")


def _decompress(s):
    if len(s) != 32:
        return None
    y = int.from_bytes(s, "little")
    sign = y >> 255
    y &= (1 << 255) - 1
    x = _recover_x(y, sign)
    return None if x is None else (x, y, 1, x * y % _P)


def _expand(seed):
    h = hashlib.sha512(seed).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def ed_pub(seed: bytes) -> bytes:
    a, _ = _expand(seed)
    return _compress(_mul(a, _G))


def ed_sign(seed: bytes, msg: bytes) -> bytes:
    a, prefix = _expand(seed)
    pub = _compress(_mul(a, _G))
    r = int.from_bytes(hashlib.sha512(prefix + msg).digest(), "little") % _Q
    rs = _compress(_mul(r, _G))
    h = int.from_bytes(hashlib.sha512(rs + pub + msg).digest(), "little") % _Q
    s = (r + h * a) % _Q
    return rs + s.to_bytes(32, "little")


def ed_verify(pub: bytes, msg: bytes, sig: bytes) -> bool:
    if len(pub) != 32 or len(sig) != 64:
        return False
    a_pt = _decompress(pub)
    r_pt = _decompress(sig[:32])
    if a_pt is None or r_pt is None:
        return False
    s = int.from_bytes(sig[32:], "little")
    if s >= _Q:
        return False
    h = int.from_bytes(hashlib.sha512(sig[:32] + pub + msg).digest(), "little") % _Q
    return _eq(_mul(s, _G), _add(r_pt, _mul(h, a_pt)))


# ═══════════════════════ رموز نصية (Base32 + CRC) ═══════════════════════
def pack_code(data: bytes, group: int = 5) -> str:
    """بيانات → نص Base32 مُجمَّع (XXXXX-XXXXX-…) مع CRC32 للكشف عن أخطاء النسخ."""
    raw = data + struct.pack(">I", zlib.crc32(data) & 0xFFFFFFFF)
    s = base64.b32encode(raw).decode().rstrip("=")
    return "-".join(s[i:i + group] for i in range(0, len(s), group))


def unpack_code(text: str) -> bytes:
    """يتسامح مع المسافات والأسطر الجديدة والشرطات وحالة الأحرف. يرفع CryptoError عند أي خلل."""
    s = "".join(ch for ch in (text or "").upper() if ch.isalnum())
    # أخطاء إملائية شائعة: 0→O ، 1→I(غير مستخدمة في Base32) — نُبقي الصارم ونرفض ما سواه
    try:
        raw = base64.b32decode(s + "=" * ((8 - len(s) % 8) % 8))
    except Exception:
        raise CryptoError("الرمز يحتوي أحرفاً غير صالحة")
    if len(raw) < 5:
        raise CryptoError("الرمز قصير")
    data, crc = raw[:-4], raw[-4:]
    if struct.pack(">I", zlib.crc32(data) & 0xFFFFFFFF) != crc:
        raise CryptoError("الرمز غير مكتمل أو فيه خطأ في النسخ")
    return data


# ═══════════════════════ استرداد كلمة المرور (طلب ← رد) ═══════════════════════
# الفكرة: عند إنشاء الحساب يُغلَّف مفتاح البيانات (DEK) بمفتاح عام للمدير (X25519). التطبيق لا يحمل أي سرّ
# يفتح البيانات. عند النسيان يرسل المستخدم «رمز الطلب» (يحوي الغلاف) للمدير، فيفك المدير الغلاف بمفتاحه
# الخاص ويرد «رمز الإعادة» مشفّراً بمفتاح لا يستطيع اشتقاقه إلا هذا الجهاز (مفتاح طلب لمرة واحدة).
REC_VER = 1


def recovery_wrap(dek: bytes, admin_box_pub: bytes) -> bytes:
    """(عند إنشاء الحساب) يعيد: E(32) ‖ sealed(DEK).  المفتاح المؤقت الخاص يُتلف فور الاستخدام."""
    e_priv, e_pub = x25519_keypair()
    shared = x25519(e_priv, admin_box_pub)
    rk = sha256(b"shifa-rec1", shared, e_pub, admin_box_pub)
    return e_pub + seal(rk, dek, aad=b"recovery")


def reset_request(device_id: bytes, recovery_blob: bytes, r_pub: bytes) -> str:
    return pack_code(bytes([REC_VER]) + device_id + recovery_blob + r_pub)


def admin_reset_respond(admin_box_priv: bytes, admin_box_pub: bytes, request_code: str):
    """(لدى المدير) يفك رمز الطلب ويعيد (رمز الرد, معرّف الجهاز hex)."""
    raw = unpack_code(request_code)
    if len(raw) < 1 + 4 + 32 + _NONCE + 32 + _TAG + 32 or raw[0] != REC_VER:
        raise CryptoError("هذا ليس رمز طلب إعادة تعيين صالحاً")
    device = raw[1:5]
    r_pub = raw[-32:]
    rec = raw[5:-32]
    e_pub, sealed = rec[:32], rec[32:]
    rk = sha256(b"shifa-rec1", x25519(admin_box_priv, e_pub), e_pub, admin_box_pub)
    dek = open_sealed(rk, sealed, aad=b"recovery")          # يفشل إن لم يكن الغلاف لهذا المفتاح
    k2 = sha256(b"shifa-reset1", x25519(admin_box_priv, r_pub), r_pub, admin_box_pub)
    reply = seal(k2, dek, aad=device + r_pub)
    return pack_code(bytes([REC_VER]) + device + reply), device.hex()


def reset_open(r_priv: bytes, admin_box_pub: bytes, device_id: bytes, reply_code: str) -> bytes:
    """(في التطبيق) يفتح رمز الرد ويعيد DEK."""
    raw = unpack_code(reply_code)
    if len(raw) < 1 + 4 + _NONCE + 32 + _TAG or raw[0] != REC_VER:
        raise CryptoError("هذا ليس رمز إعادة تعيين صالحاً")
    if raw[1:5] != device_id:
        raise CryptoError("هذا الرمز مخصّص لجهاز آخر")
    r_pub = x25519_pub(r_priv)
    k2 = sha256(b"shifa-reset1", x25519(r_priv, admin_box_pub), r_pub, admin_box_pub)
    return open_sealed(k2, raw[5:], aad=device_id + r_pub)
