# -*- coding: utf-8 -*-
"""
test_vectors.py — اختبارات التشفير بمتجهات رسمية (RFC 7748 / RFC 8032 / RFC 7914 / NIST SHAKE) وخصائص الأمان.
تشغَّل على crypto_core.py وحده (بلا Flet ولا بيانات). إن توفّرت مكتبة `cryptography` تُجرى مقارنة عشوائية مع مرجع مستقل.
التشغيل:   python tests/test_vectors.py
"""
import hashlib
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import crypto_core as K                               # noqa: E402

FAILS = []
H = bytes.fromhex


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        FAILS.append(name)


def raises(fn, exc=K.CryptoError):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


# ───────────── X25519 — RFC 7748 ─────────────
def t_x25519():
    for i, (k, u, out) in enumerate((
        ("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4",
         "e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c",
         "c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552"),
        ("4b66e9d4d1b4673c5ad22691957d6af5c11b6421e0ea01d42ca4169e7918ba0d",
         "e5210f12786811d3f4b7959d0538ae2c31dbe7106fc03c3efc4cd549c715a493",
         "95cbde9476e8907d7aade45cb4b873f88b595a68799fa152e6f8f7647aac7957")), 1):
        check(f"X25519 RFC 7748 §5.2 المتجه {i}", K.x25519(H(k), H(u)).hex() == out)
    k = u = H("09" + "00" * 31)
    for n in range(1, 1001):
        k, u = K.x25519(k, u), k
        if n == 1:
            check("X25519 RFC 7748 §5.2 تكرار 1", k.hex() == "422c8e7a6227d7bca1350b3e2bb7279f7897b87bb6854b783c60e80311ae3079")
    check("X25519 RFC 7748 §5.2 تكرار 1000", k.hex() == "684cf59ba83309552800ef566f2f4d3c1c3887c49360e3875f2eb94d99532c51")
    a_sk = H("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
    b_sk = H("5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb")
    a_pk = "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a"
    b_pk = "de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f"
    shared = "4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742"
    check("RFC 7748 §6.1: المفاتيح العامة لـ Alice و Bob", K.x25519_pub(a_sk).hex() == a_pk and K.x25519_pub(b_sk).hex() == b_pk)
    check("RFC 7748 §6.1: السرّ المشترك متطابق من الطرفين",
          K.x25519(a_sk, H(b_pk)).hex() == shared == K.x25519(b_sk, H(a_pk)).hex())
    sk = secrets.token_bytes(32)
    check("نقطة ضعيفة u=0 مرفوضة", raises(lambda: K.x25519(sk, bytes(32))))
    check("نقطة ضعيفة u=1 مرفوضة", raises(lambda: K.x25519(sk, H("01" + "00" * 31))))
    check("نقطة رتبتها 8 مرفوضة", raises(lambda: K.x25519(sk, H("e0eb7a7c3b41b8ae1656e3faf19fc46ada098deb9c32b1fd866205165f49b800"))))
    check("أطوال خاطئة مرفوضة", raises(lambda: K.x25519(b"x" * 31, bytes(32))) and raises(lambda: K.x25519(bytes(32), b"x" * 33)))


# ───────────── Ed25519 — RFC 8032 §7.1 ─────────────
ED = [("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
       "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a", "",
       "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"),
      ("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
       "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", "72",
       "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"),
      ("c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
       "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025", "af82",
       "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a")]


def t_ed25519():
    for i, (sk, pk, msg, sig) in enumerate(ED, 1):
        check(f"Ed25519 RFC 8032 TEST {i}: المفتاح العام", K.ed_pub(H(sk)).hex() == pk)
        check(f"Ed25519 RFC 8032 TEST {i}: التوقيع (حتمي)", K.ed_sign(H(sk), H(msg)).hex() == sig)
        check(f"Ed25519 RFC 8032 TEST {i}: التحقق", K.ed_verify(H(pk), H(msg), H(sig)))
    sk, pk, msg, sig = ED[1]
    pk_b, msg_b, sig_b = H(pk), H(msg), bytearray(H(sig))
    check("رسالة معدّلة مرفوضة", not K.ed_verify(pk_b, msg_b + b"x", bytes(sig_b)))
    bad = bytearray(sig_b)
    bad[0] ^= 1
    check("جزء R معدّل مرفوض", not K.ed_verify(pk_b, msg_b, bytes(bad)))
    bad = bytearray(sig_b)
    bad[40] ^= 1
    check("جزء S معدّل مرفوض", not K.ed_verify(pk_b, msg_b, bytes(bad)))
    other = K.ed_pub(H(ED[0][0]))
    check("مفتاح عام مختلف مرفوض", not K.ed_verify(other, msg_b, bytes(sig_b)))
    s_plus_l = (int.from_bytes(sig_b[32:], "little") + K._Q).to_bytes(32, "little")
    check("تزوير مرن (S+L) مرفوض", not K.ed_verify(pk_b, msg_b, bytes(sig_b[:32]) + s_plus_l))
    check("أطوال خاطئة مرفوضة", not K.ed_verify(pk_b[:31], msg_b, bytes(sig_b)) and not K.ed_verify(pk_b, msg_b, bytes(sig_b[:63])))


# ───────────── PBKDF2 / SHAKE / التشفير المصادَق ─────────────
def t_kdf_and_seal():
    check("PBKDF2-SHA256 RFC 7914 §11 (c=1)", hashlib.pbkdf2_hmac("sha256", b"passwd", b"salt", 1, 64).hex() ==
          "55ac046e56e3089fec1691c22544b605f94185216dde0465e68b9d57c20dacbc49ca9cccf179b645991664b39d77ef317c71b845b1e30bd509112041d3a19783")
    check("PBKDF2-SHA256 RFC 7914 §11 (c=80000)", hashlib.pbkdf2_hmac("sha256", b"Password", b"NaCl", 80000, 64).hex() ==
          "4ddcd8f60b98be21830cee5ef22701f9641a4418d04c0414aeff08876b34ab56a1d425a1225833549adb841b51c9b3176a272bdebba1d078478f62b397f33c8d")
    check("SHAKE-256 (NIST) للرسالة الفارغة", hashlib.shake_256(b"").digest(64).hex() ==
          "46b9dd2b0ba88d13233b3feb743eeb243fcd52ea62b81b82b50c27646ed5762fd75dc4ddd8c0f200cb05019d67b592f6fc821c49479ab48640292eacb3b7c4be")
    salt = secrets.token_bytes(16)
    check("kdf_password = PBKDF2(label‖0‖password) بطول 32",
          K.kdf_password("كلمة", salt, 1000, "user") == hashlib.pbkdf2_hmac("sha256", "user\x00كلمة".encode(), salt, 1000, 32))
    check("اسم مستخدم مختلف = مفتاح مختلف", K.kdf_password("p", salt, 1000, "a") != K.kdf_password("p", salt, 1000, "b"))
    key = secrets.token_bytes(32)
    for n in (0, 1, 15, 16, (1 << 20) - 1, 1 << 20, (1 << 20) + 3, 2 * (1 << 20) + 5):      # حدود كتل التدفق
        data = os.urandom(n)
        blob = K.seal(key, data, aad=b"x")
        if K.open_sealed(key, blob, aad=b"x") != data:
            check(f"seal/open للطول {n}", False)
            break
    else:
        check("seal/open عبر حدود الكتل (0..2MB+5)", True)
    blob = K.seal(key, b"secret data here", aad=b"ctx")
    n_, t_ = 12, 16
    for label, idx in (("nonce", 3), ("نص مشفّر", n_ + 2), ("وسم", len(blob) - 3)):
        bad = bytearray(blob)
        bad[idx] ^= 1
        check(f"تعديل {label} يُكتشف", raises(lambda: K.open_sealed(key, bytes(bad), aad=b"ctx")))
    check("aad مختلف يُرفض", raises(lambda: K.open_sealed(key, blob, aad=b"other")))
    check("مفتاح مختلف يُرفض", raises(lambda: K.open_sealed(secrets.token_bytes(32), blob, aad=b"ctx")))
    check("قصّ الوسم يُرفض", raises(lambda: K.open_sealed(key, blob[:-1], aad=b"ctx")))
    check("نفس النص مرتين = ناتجان مختلفان (nonce عشوائي)", K.seal(key, b"a") != K.seal(key, b"a"))
    check("طول مفتاح خاطئ يُرفض", raises(lambda: K.seal(b"short", b"x")))
    enc = K.encrypt_blob(key, b"file-data", aad=b"file:p/1.bin")
    check("encrypt_blob/decrypt_blob تربط المسار", K.decrypt_blob(key, enc, aad=b"file:p/1.bin") == b"file-data" and
          raises(lambda: K.decrypt_blob(key, enc, aad=b"file:p/2.bin")))
    # رموز نصية
    raw = os.urandom(20)
    code = K.pack_code(raw)
    check("pack/unpack: تسامح مع حالة الأحرف والشرطات والمسافات", K.unpack_code(code.lower().replace("-", " ")) == raw)
    bad = code.replace(code[0], "A" if code[0] != "A" else "B", 1)
    check("خطأ نسخ واحد يُكتشف بـ CRC", raises(lambda: K.unpack_code(bad)))
    check("رمز قصير/فارغ مرفوض", raises(lambda: K.unpack_code("")) and raises(lambda: K.unpack_code("AB")))


# ───────────── مقارنة عشوائية مع مرجع مستقل (إن توفّر) ─────────────
def t_oracle():
    try:
        from cryptography.hazmat.primitives import serialization as S
        from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
    except Exception:
        return print("SKIP المقارنة مع مكتبة cryptography (غير مثبّتة)")
    raw = lambda k: k.public_bytes(S.Encoding.Raw, S.PublicFormat.Raw)
    ok_x = ok_e = True
    for _ in range(25):
        a, b = secrets.token_bytes(32), secrets.token_bytes(32)
        A, B = x25519.X25519PrivateKey.from_private_bytes(a), x25519.X25519PrivateKey.from_private_bytes(b)
        ok_x &= K.x25519_pub(a) == raw(A.public_key())
        ok_x &= K.x25519(a, K.x25519_pub(b)) == A.exchange(B.public_key())
        seed, msg = secrets.token_bytes(32), os.urandom(secrets.randbelow(300))
        E = ed25519.Ed25519PrivateKey.from_private_bytes(seed)
        ok_e &= K.ed_pub(seed) == raw(E.public_key()) and K.ed_sign(seed, msg) == E.sign(msg)
        ok_e &= K.ed_verify(raw(E.public_key()), msg, E.sign(msg))
    check("X25519: 25 مفتاحاً عشوائياً تطابق المرجع", ok_x)
    check("Ed25519: 25 توقيعاً عشوائياً (حتمي) يطابق المرجع", ok_e)


def main():
    t_x25519()
    t_ed25519()
    t_kdf_and_seal()
    t_oracle()
    print("\n" + ("ALL PASSED" if not FAILS else f"FAILED: {FAILS}"))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
