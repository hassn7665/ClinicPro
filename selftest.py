# -*- coding: utf-8 -*-
"""
selftest.py — فحوص ذاتية تُنفَّذ **على الجهاز نفسه** (وعلى الحاسوب: python selftest.py):
تتأكد أن بايثون على أندرويد يوفّر ما يعتمد عليه التشفير والتخزين، وأن التشفير يعطي نفس نتائج متجهات RFC الرسمية،
وتقيس الأزمنة الفعلية (الاشتقاق من كلمة المرور، تشفير 1 ميغابايت). لا تمسّ بيانات المستخدم.
"""
import hashlib
import os
import secrets
import shutil
import sqlite3
import sys
import time

import crypto_core as K

# متجهات رسمية
_X25519 = ("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4",      # RFC 7748 §5.2
           "e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c",
           "c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552")
_ED_SEED = "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"      # RFC 8032 TEST 1
_ED_PUB = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
_ED_SIG = ("e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e065224901555fb8821590a33bacc61e39701cf9b46"
           "bd25bf5f0595bbe24655141438e7a100b")
_PBKDF2 = "55ac046e56e3089fec1691c22544b605f94185216dde0465e68b9d57c20dacbc49ca9cccf179b645991664b39d77ef317c71b845b1e30bd509112041d3a19783"


def _t(fn):
    t0 = time.perf_counter()
    r = fn()
    return r, (time.perf_counter() - t0) * 1000


def run(base_dir: str | None = None, kdf_iter: int = 600_000):
    """يعيد قائمة (الاسم, نجح؟, تفاصيل). لا يرفع استثناءً."""
    out = []

    def check(name, fn):
        try:
            ok, detail = fn()
        except Exception as ex:
            ok, detail = False, f"{type(ex).__name__}"
        out.append((name, bool(ok), detail))

    check("SHAKE-256 (مولّد التدفق)", lambda: (len(hashlib.shake_256(b"x").digest(40)) == 40, ""))
    check("PBKDF2-SHA256 يطابق المتجه الرسمي",
          lambda: (hashlib.pbkdf2_hmac("sha256", b"passwd", b"salt", 1, 64).hex() == _PBKDF2, ""))
    check("X25519 يطابق RFC 7748",
          lambda: (K.x25519(bytes.fromhex(_X25519[0]), bytes.fromhex(_X25519[1])).hex() == _X25519[2], ""))

    def ed():
        seed = bytes.fromhex(_ED_SEED)
        sig = K.ed_sign(seed, b"")
        return (K.ed_pub(seed).hex() == _ED_PUB and sig.hex() == _ED_SIG and
                K.ed_verify(bytes.fromhex(_ED_PUB), b"", sig) and not K.ed_verify(bytes.fromhex(_ED_PUB), b"x", sig)), ""
    check("Ed25519 يطابق RFC 8032 (توقيع وتحقق)", ed)

    def seal():
        k = secrets.token_bytes(32)
        blob = K.seal(k, b"hello", aad=b"a")
        bad = bytearray(blob)
        bad[15] ^= 1
        try:
            K.open_sealed(k, bytes(bad), aad=b"a")
            return False, "التلاعب لم يُكتشف"
        except K.CryptoError:
            pass
        return K.open_sealed(k, blob, aad=b"a") == b"hello", ""
    check("التشفير المصادَق يكشف التلاعب", seal)

    def sq():
        c = sqlite3.connect(":memory:")
        c.execute("create table t(a)")
        c.execute("insert into t values(1)")
        c.commit()
        has = hasattr(c, "serialize") and hasattr(c, "deserialize")
        return has, f"sqlite {sqlite3.sqlite_version}" + ("" if has else " — بلا serialize (سيُستعمل المسار البديل الأبطأ)")
    check("SQLite serialize/deserialize", sq)

    def disk():
        d = base_dir or os.getcwd()
        p = os.path.join(d, f".selftest_{secrets.token_hex(4)}")
        try:
            with open(p, "wb") as f:
                f.write(b"1234")
                f.flush()
                os.fsync(f.fileno())
            os.replace(p, p + ".2")
            ok = open(p + ".2", "rb").read() == b"1234"
        finally:
            for x in (p, p + ".2"):
                try:
                    os.remove(x)
                except OSError:
                    pass
        free = shutil.disk_usage(d).free // (1024 * 1024)
        return ok and free >= 100, f"مساحة حرة {free} ميغابايت" + ("" if free >= 100 else " — قليلة!")
    check("الكتابة الذرّية (fsync + replace) والمساحة", disk)

    try:
        import images
        out.append(("معالجة الصور (Pillow)", images.PIL_OK,
                    images.PIL_VERSION if images.PIL_OK else "غير متوفرة — الصور تُخزَّن بحجمها الكامل ويُحمَّل العرض كسولاً"))
    except Exception:
        out.append(("معالجة الصور (Pillow)", False, "غير متوفرة"))

    kdf, ms_kdf = _t(lambda: K.kdf_password("benchmark", b"0" * 16, kdf_iter, "t"))
    out.append((f"زمن اشتقاق كلمة المرور ({kdf_iter // 1000} ألف دورة)", ms_kdf < 4000,
                f"{ms_kdf:.0f} مللي ثانية" + ("" if ms_kdf < 4000 else " — بطيء جداً: فكّر بخفض الدورات")))
    key, blob = secrets.token_bytes(32), os.urandom(1 << 20)
    enc, ms_enc = _t(lambda: K.encrypt_blob(key, blob))
    _, ms_dec = _t(lambda: K.decrypt_blob(key, enc))
    out.append(("تشفير/فك 1 ميغابايت", ms_enc + ms_dec < 3000, f"{ms_enc:.0f} / {ms_dec:.0f} مللي ثانية"))
    return out


if __name__ == "__main__":
    bad = 0
    for name, ok, detail in run():
        print(("PASS " if ok else "FAIL ") + name + (f"  {detail}" if detail else ""))
        bad += not ok
    print(f"python {sys.version.split()[0]} / {sys.platform}")
    sys.exit(1 if bad else 0)
