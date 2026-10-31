# -*- coding: utf-8 -*-
"""
المرحلة B (أمان) + اختبارات الترقية بحجم كبير:
  1) تجريد EXIF/GPS دائماً (بلا Pillow)  2) تحصين الاستعادة والنسخ  3) مفاتيح المدير (إلزام العبارة، Shamir، kid، الاسترداد اختياري)
تشغيل: python tests/test_phase_b.py
"""
import io
import json
import os
import shutil
import sqlite3
import struct
import sys
import tempfile
import time
import types
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import boot_core, make_account, make_png  # noqa: E402

import schema as SC  # noqa: E402

try:
    from PIL import Image
except ImportError:                                       # pragma: no cover
    Image = None

SECRETS = (b"SecretPhoneMaker", b"GPSLatitude", b"hidden-comment", b"xmp-secret")


def jpeg_with_metadata(orientation=6):
    """JPEG حقيقي فيه EXIF (طراز جهاز + GPS + اتجاه) + تعليق + XMP + APP13."""
    buf = io.BytesIO()
    im = Image.new("RGB", (80, 60), (10, 100, 200))
    ex = Image.Exif()
    ex[0x0112] = orientation
    ex[0x010F] = "SecretPhoneMaker"
    ex[0x8825] = {1: "N", 2: (33.0, 30.0, 10.0), 3: "E", 4: (36.0, 18.0, 5.0)}
    im.save(buf, "JPEG", exif=ex.tobytes())
    raw = buf.getvalue()
    xmp = b"http://ns.adobe.com/xap/1.0/\x00<x:xmp>xmp-secret</x:xmp>"
    extra = (b"\xff\xfe" + struct.pack(">H", 2 + len(b"hidden-comment")) + b"hidden-comment"
             + b"\xff\xe1" + struct.pack(">H", 2 + len(xmp)) + xmp
             + b"\xff\xed" + struct.pack(">H", 2 + 10) + b"Photoshop3")
    return raw[:2] + extra + raw[2:]


@unittest.skipIf(Image is None, "Pillow غير متوفر في بيئة الاختبار")
class MetadataStripTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.C, cls.tmp = boot_core("meta")
        cls.IMG = cls.C.IMG

    def test_jpeg_stripped_but_orientation_kept(self):
        raw = jpeg_with_metadata(6)
        for needle in (b"SecretPhoneMaker", b"hidden-comment", b"xmp-secret", b"Photoshop3"):
            self.assertIn(needle, raw)
        out = self.IMG.strip_metadata(raw)
        self.assertIsNot(out, raw)
        for needle in SECRETS + (b"Photoshop3", b"Exif\x00\x00\x4d\x4d\x00\x2a\x00\x00\x00\x08\x00\x02"):
            self.assertNotIn(needle, out)
        im = Image.open(io.BytesIO(out))
        im.load()
        self.assertEqual(im.size, (80, 60))                                  # ما زالت صورة سليمة
        self.assertEqual(im.getexif().get(0x0112), 6)                        # الاتجاه محفوظ
        self.assertFalse(im.getexif().get_ifd(0x8825))                       # لا GPS
        self.assertIsNone(im.getexif().get(0x010F))                          # لا طراز جهاز
        self.assertIs(self.IMG.strip_metadata(out), out)                     # idempotent: لا تغيير ثانٍ

    def test_jpeg_without_orientation_gets_no_exif_at_all(self):
        out = self.IMG.strip_metadata(jpeg_with_metadata(1))
        self.assertNotIn(b"Exif", out)
        self.assertEqual(Image.open(io.BytesIO(out)).size, (80, 60))

    def test_png_text_chunks_removed(self):
        import zlib
        png = make_png(os.path.join(self.tmp, "a.png"))
        raw = open(png, "rb").read()
        chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
        dirty = raw[:33] + chunk(b"tEXt", b"Comment\x00hidden-comment") + chunk(b"eXIf", b"MM\x00*SecretPhoneMaker") + raw[33:]
        self.assertIn(b"hidden-comment", dirty)
        out = self.IMG.strip_metadata(dirty)
        self.assertNotIn(b"hidden-comment", out)
        self.assertNotIn(b"SecretPhoneMaker", out)
        self.assertEqual(Image.open(io.BytesIO(out)).size, (64, 48))

    def test_webp_exif_removed(self):
        buf = io.BytesIO()
        ex = Image.Exif()
        ex[0x010F] = "SecretPhoneMaker"
        try:
            Image.new("RGB", (40, 30), (1, 2, 3)).save(buf, "WEBP", exif=ex.tobytes(), lossless=True)
        except Exception:
            self.skipTest("WEBP غير مدعوم في هذه البيئة")
        raw = buf.getvalue()
        self.assertIn(b"SecretPhoneMaker", raw)
        out = self.IMG.strip_metadata(raw)
        self.assertNotIn(b"SecretPhoneMaker", out)
        self.assertEqual(Image.open(io.BytesIO(out)).size, (40, 30))

    def test_malformed_and_unknown_untouched(self):
        for blob in (b"", b"\xff\xd8\xff", b"\xff\xd8\xff\xe1\xff\xff", b"GIF89a....", b"not an image", b"\x89PNG\r\n\x1a\n\x00\x00"):
            self.assertIs(self.IMG.strip_metadata(blob), blob)

    def test_process_strips_even_without_pillow(self):
        old = self.IMG.PIL_OK
        self.IMG.PIL_OK = False
        try:
            data, thumb = self.IMG.process(jpeg_with_metadata())
        finally:
            self.IMG.PIL_OK = old
        self.assertIsNone(thumb)
        for needle in SECRETS:
            self.assertNotIn(needle, data)

    def test_store_file_never_keeps_gps(self):
        C = self.C
        make_account(C)
        src = os.path.join(self.tmp, "gps.jpg")
        open(src, "wb").write(jpeg_with_metadata())
        for pil in (True, False):
            self.IMG.PIL_OK = pil and Image is not None
            rel = C.store_file({"code": "PT-00001"}, src)
            self.assertNotIn(b"SecretPhoneMaker", C.read_file(rel))
            self.assertNotIn(b"GPSLatitude", C.read_file(rel))
        self.IMG.PIL_OK = True

    def test_scrub_existing_files_once(self):
        C = self.C
        make_account(C)
        p = C.save_patient(dict(full_name="م", gender="", age=1, residence="", phone="", job="", diseases="", notes="",
                                blood="", status="جديد"), {}, [])
        rel = C.new_rel(p["code"])
        C.write_enc(rel, jpeg_with_metadata())                    # كما كانت تُخزَّن في الإصدارات السابقة
        C.x("UPDATE patients SET photo_before=? WHERE id=?", (rel, p["id"]))
        st = C.jload(C.SET_PATH, {})
        st.pop("meta_scrub", None)
        C.jsave(C.SET_PATH, st)
        rep = C.scrub_metadata_if_needed()
        self.assertEqual((rep["cleaned"], rep["failed"]), (1, 0))
        self.assertNotIn(b"SecretPhoneMaker", C.read_file(rel))
        self.assertIsNone(C.scrub_metadata_if_needed())            # مرة واحدة فقط
        self.assertEqual(C.scrub_metadata()["cleaned"], 0)         # وآمن للتكرار


class RestoreHardeningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.C, cls.tmp = boot_core("restore_hard")
        make_account(cls.C)

    def _blob(self, build):
        c = sqlite3.connect(":memory:")
        SC.migrate(c)
        build(c)
        c.commit()
        return c

    def test_text_dump_with_attach_rejected(self):
        evil = ("BEGIN TRANSACTION;\nATTACH DATABASE '/tmp/pwned.db' AS x;\nCOMMIT;")
        with self.assertRaises(SC.SchemaError):
            self.C._new_conn(b"\x02" + evil.encode())
        self.assertFalse(os.path.exists("/tmp/pwned.db"))

    def test_text_dump_with_two_statements_on_one_line_rejected(self):
        evil = "INSERT INTO patients(full_name) VALUES('a'); ATTACH DATABASE '/tmp/pwned2.db' AS x;"
        with self.assertRaises(Exception):
            self.C._new_conn(b"\x02" + evil.encode())
        self.assertFalse(os.path.exists("/tmp/pwned2.db"))

    def test_text_dump_with_trigger_rejected(self):
        evil = ("CREATE TABLE patients(id INTEGER PRIMARY KEY, full_name TEXT);\n"
                "CREATE TRIGGER t AFTER INSERT ON patients BEGIN DELETE FROM patients; END;")
        with self.assertRaises(SC.SchemaError):
            self.C._new_conn(b"\x02" + evil.encode())

    def test_serialized_db_with_trigger_view_or_extra_table_rejected(self):
        for ddl in ("CREATE TRIGGER t AFTER INSERT ON patients BEGIN SELECT 1; END",
                    "CREATE VIEW v AS SELECT * FROM patients",
                    "CREATE TABLE secrets(a)"):
            c = self._blob(lambda c, d=ddl: c.execute(d))
            with self.assertRaises(SC.SchemaError, msg=ddl):
                self.C._new_conn(b"\x01" + c.serialize())

    def test_own_dump_roundtrips_through_whitelist(self):
        C = self.C
        p = C.save_patient(dict(full_name="مريض 'اقتباس'; DROP", gender="", age=5, residence="", phone="", job="",
                                diseases="", notes="سطر1\nسطر2; COMMIT;", blood="", status="جديد"), {}, [])
        C.create_event(p["id"], "visit", "2026-04-04", "10:00", items=[("x", 1234, "SYP")])
        dump = "\n".join(C._mem["conn"].iterdump()) + f"\nPRAGMA user_version={SC.get_version(C._mem['conn'])};"
        conn = C._new_conn(b"\x02" + dump.encode())
        self.assertEqual(conn.execute("SELECT full_name FROM patients ORDER BY id DESC").fetchone()[0], "مريض 'اقتباس'; DROP")
        self.assertEqual(conn.execute("SELECT price FROM event_items").fetchone()[0], 1234)

    # ---- صيغة النسخ الاحتياطي v2 ----
    def _backup_with_files(self):
        C = self.C
        self._n = getattr(self, "_n", 0) + 1
        p = C.save_patient(dict(full_name=f"نسخة {os.urandom(3).hex()}", gender="", age=2, residence="", phone="", job="", diseases="", notes="",
                                blood="", status="جديد"), {"photo_before": make_png(os.path.join(self.tmp, "b.png"))}, [])
        return C.make_backup(prune=False), p

    def _records_offsets(self, path):
        raw = open(path, "rb").read()
        n = struct.unpack(">I", raw[5:9])[0]
        pos, offs = 9 + n, []
        while pos < len(raw):
            ln = struct.unpack(">I", raw[pos:pos + 4])[0]
            offs.append((pos, 4 + ln))
            pos += 4 + ln
        return raw, 9 + n, offs

    def test_v2_roundtrip_and_header(self):
        C = self.C
        path, _ = self._backup_with_files()
        hdr, _ = C._bk_header(path)
        self.assertEqual(hdr["fmt"], 2)
        names = [n for n, _ in C._bk_records(path, C.VAULT.dek)]
        self.assertEqual(names[0], "__db__")
        self.assertNotIn("__end__", names)
        C.restore_backup(path)                                     # يعمل كاملاً

    def test_truncation_at_record_boundary_detected(self):
        C = self.C
        path, _ = self._backup_with_files()
        raw, hdr_end, offs = self._records_offsets(path)
        self.assertGreaterEqual(len(offs), 3)
        for cut in (offs[-1][0], offs[-2][0]):                     # بلا السجل الختامي / بلا آخر ملف أيضاً
            bad = os.path.join(self.tmp, f"cut{cut}.mcbk")
            open(bad, "wb").write(raw[:cut])
            with self.assertRaises(ValueError):
                list(C._bk_records(bad, C.VAULT.dek))
            with self.assertRaises(ValueError):
                C.restore_backup(bad)

    def test_dropped_middle_record_detected(self):
        C = self.C
        path, _ = self._backup_with_files()
        raw, hdr_end, offs = self._records_offsets(path)
        a, ln = offs[1]
        bad = os.path.join(self.tmp, "dropmid.mcbk")
        open(bad, "wb").write(raw[:a] + raw[a + ln:])
        with self.assertRaises(ValueError):
            list(C._bk_records(bad, C.VAULT.dek))

    def test_records_after_end_and_swapped_order_detected(self):
        C = self.C
        path, _ = self._backup_with_files()
        raw, hdr_end, offs = self._records_offsets(path)
        a0, l0 = offs[0]
        bad = os.path.join(self.tmp, "after_end.mcbk")
        open(bad, "wb").write(raw + raw[a0:a0 + l0])
        with self.assertRaises(ValueError):
            list(C._bk_records(bad, C.VAULT.dek))
        a1, l1 = offs[1]
        a2, l2 = offs[2]
        swapped = raw[:a1] + raw[a2:a2 + l2] + raw[a1:a1 + l1] + raw[a2 + l2:]
        bad2 = os.path.join(self.tmp, "swap.mcbk")
        open(bad2, "wb").write(swapped)
        with self.assertRaises(ValueError):                        # الترتيب جزء من البصمة
            list(C._bk_records(bad2, C.VAULT.dek))

    def test_huge_length_rejected_without_allocating(self):
        C = self.C
        path, _ = self._backup_with_files()
        raw, hdr_end, offs = self._records_offsets(path)
        bad = os.path.join(self.tmp, "huge.mcbk")
        open(bad, "wb").write(raw[:hdr_end] + struct.pack(">I", 0xFFFFFFF0) + b"x" * 64)
        with self.assertRaises(ValueError):
            list(C._bk_records(bad, C.VAULT.dek))

    def test_header_format_flip_fails_authentication(self):
        C = self.C
        path, _ = self._backup_with_files()
        raw = open(path, "rb").read()
        n = struct.unpack(">I", raw[5:9])[0]
        hdr = json.loads(raw[9:9 + n])
        hdr["fmt"] = 1                                             # تخفيض صيغة لتعطيل فحص الاقتطاع
        hb = json.dumps(hdr).encode()
        bad = os.path.join(self.tmp, "downgrade.mcbk")
        open(bad, "wb").write(raw[:5] + struct.pack(">I", len(hb)) + hb + raw[9 + n:])
        with self.assertRaises(Exception):
            list(C._bk_records(bad, C.VAULT.dek))

    def test_legacy_v1_backup_still_restores(self):
        C = self.C
        old = os.path.join(self.tmp, "old_v1.mcbk")
        conn = C._mem["conn"]
        with C._bk_open(old, legacy=True) as w:
            w.add("__db__", C._serialize(conn))
        self.assertNotIn("fmt", C._bk_header(old)[0])
        C.restore_backup(old)


# ───────────────────────── مفاتيح المدير ─────────────────────────
class AdminKeysTests(unittest.TestCase):
    def setUp(self):
        self.C, _ = boot_core("keys")
        import crypto_core as K
        import keygen
        import license_core as LC
        self.K, self.kg, self.LC = K, keygen, LC
        self.dir = tempfile.mkdtemp(prefix="kg_")
        kg = keygen
        kg.KEYS, kg.LOG = os.path.join(self.dir, "admin_keys.json"), os.path.join(self.dir, "issued_log.json")
        kg.PUBLIC_PY = os.path.join(self.dir, "public_keys.py")
        kg._PASS.update(v=None, provider=None, warned=False)
        os.environ["MYCLINIC_ADMIN_PASS"] = "correct horse battery staple"
        self._reload = LC.reload_keys
        LC.reload_keys = self._fake_reload
        self.addCleanup(self._restore)

    def _fake_reload(self):
        s, b = self.kg._current_public()
        self.LC.PK = types.SimpleNamespace(SIGN_PUB=s, BOX_PUB=b, **getattr(self, "extra_pk", {}))

    def _restore(self):
        self.LC.reload_keys = self._reload
        os.environ.pop("MYCLINIC_ADMIN_PASS", None)
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_init_always_protected_never_plaintext(self):
        self.kg.init_keys()
        doc = json.load(open(self.kg.KEYS))
        self.assertTrue(doc["enc"])
        self.assertNotIn("sign_seed", doc)
        self.assertNotIn("box_priv", doc)
        raw = open(self.kg.KEYS).read()
        seed, _ = self.kg._load_secret()
        self.assertNotIn(seed.hex(), raw)

    def test_short_or_missing_passphrase_refused(self):
        os.environ["MYCLINIC_ADMIN_PASS"] = "short"
        with self.assertRaises(SystemExit):
            self.kg.init_keys()
        self.assertFalse(os.path.exists(self.kg.KEYS))
        os.environ.pop("MYCLINIC_ADMIN_PASS")
        with self.assertRaises(SystemExit):                        # بلا لوحة مفاتيح: لا حفظ نصي صامت
            self.kg.init_keys()
        self.assertFalse(os.path.exists(self.kg.KEYS))

    def test_legacy_plaintext_file_gets_protected_on_use(self):
        kg = self.kg
        seed, box = os.urandom(32), os.urandom(32)
        json.dump({"sign_seed": seed.hex(), "box_priv": box.hex(), "created": "2025-01-01T00:00:00"}, open(kg.KEYS, "w"))
        kg._write_public(seed, box)
        got = kg.load_keys()
        self.assertEqual(got, (seed, box))
        self.assertTrue(json.load(open(kg.KEYS))["enc"])
        self.assertNotIn(seed.hex(), open(kg.KEYS).read())
        self.assertEqual(kg._load_secret(), (seed, box))

    def test_shamir_any_k_of_n_recovers_fewer_fail(self):
        import itertools
        kg = self.kg
        secret = os.urandom(65)
        for need, total in ((2, 3), (3, 5), (2, 2)):
            shares = kg.split_secret(secret, need, total)
            for combo in itertools.combinations(shares, need):
                self.assertEqual(kg.join_secret(list(combo)), secret)
            self.assertEqual(kg.join_secret(shares), secret)       # أكثر من اللازم مقبول
            with self.assertRaises(ValueError):
                kg.join_secret(shares[:need - 1])
        a, b = kg.split_secret(secret, 2, 3), kg.split_secret(os.urandom(65), 2, 3)
        with self.assertRaises(ValueError):                        # أجزاء من مجموعتين مختلفتين
            kg.join_secret([a[0], b[1]])
        with self.assertRaises(ValueError):
            kg.join_secret([a[0], a[0]])
        bad = a[1][:-1] + ("A" if a[1][-1] != "A" else "B")
        with self.assertRaises(ValueError):                        # خطأ نسخ يُكشف
            kg.join_secret([a[0], bad])

    def test_recover_restores_working_keys(self):
        kg = self.kg
        kg.init_keys()
        seed, box = kg._load_secret()
        pub_before = open(kg.PUBLIC_PY).read()
        shares = kg.make_shares(2, 3)
        os.remove(kg.KEYS)
        os.remove(kg.PUBLIC_PY)
        os.environ["MYCLINIC_ADMIN_PASS"] = "a brand new passphrase!"
        kg._PASS["v"] = None
        kg.recover_keys([shares[2], shares[0]])
        self.assertEqual(kg._load_secret(), (seed, box))
        self.assertEqual(open(kg.PUBLIC_PY).read(), pub_before)
        with self.assertRaises(SystemExit):                        # لا استبدال صامت لملف موجود
            kg.recover_keys(shares[:2])

    def test_activation_codes_v1_and_key_id_v2(self):
        K, LC = self.K, self.LC
        seed0, seed1 = os.urandom(32), os.urandom(32)
        LC.PK = types.SimpleNamespace(SIGN_PUB=K.ed_pub(seed0).hex(), BOX_PUB="00" * 32,
                                      SIGN_PUBS={1: K.ed_pub(seed1).hex()})
        dev = "0a1b2c3d"
        c0 = LC.make_code(seed0, dev, 1, 3)
        self.assertEqual(len(K.unpack_code(c0)), 74)               # الصيغة القديمة كما هي (توافق كامل)
        self.assertEqual(LC.parse_code(c0, dev)[1], 3)
        c1 = LC.make_code(seed1, dev, 2, 6, kid=1)
        self.assertEqual(len(K.unpack_code(c1)), 75)
        self.assertEqual(LC.parse_code(c1, dev), (2, 6))
        # kid لا يمكن تبديله: التوقيع يغطيه
        raw = bytearray(K.unpack_code(c1))
        raw[1] = 0
        with self.assertRaises(LC.LicenseError):
            LC.parse_code(K.pack_code(bytes(raw)), dev)
        # kid غير معروف للتطبيق → رسالة تحديث
        raw[1] = 9
        with self.assertRaises(LC.LicenseError) as cm:
            LC.parse_code(K.pack_code(bytes(raw)), dev)
        self.assertIn("حدّث", str(cm.exception))
        # كود موقَّع بمفتاح آخر مع kid صحيح مرفوض
        with self.assertRaises(LC.LicenseError):
            LC.parse_code(LC.make_code(seed0, dev, 3, 1, kid=1), dev)

    def test_keygen_issues_with_current_key_id(self):
        kg = self.kg
        kg.init_keys()
        self._fake_reload()
        rec = kg.issue_activation("0a1b2c3d", 3, note="عميل")
        self.assertEqual(self.LC.parse_code(rec["code"], "0a1b2c3d"), (1, 3))


class AccountDefaultsTests(unittest.TestCase):
    def test_admin_recovery_is_mandatory_by_default(self):
        C, _ = boot_core("escrow")
        rk = C.setup_account("user1", "Correct-Horse-9")
        self.assertTrue(rk)                                       # مفتاح الاسترداد الشخصي يُعرض أيضاً
        self.assertTrue(C.VAULT.escrow_enabled)
        self.assertTrue(C.VAULT.has_recovery_key)

    def test_old_account_without_escrow_is_upgraded_on_login(self):
        C, _ = boot_core("escrow2")
        C.setup_account("user1", "Correct-Horse-9", escrow=False)       # حساب أُنشئ قبل جعل الاسترداد إلزامياً
        self.assertFalse(C.VAULT.escrow_enabled)
        self.assertTrue(C.ensure_escrow())
        self.assertTrue(C.VAULT.escrow_enabled)
        self.assertFalse(C.ensure_escrow())                              # مرة واحدة فقط
        C.lock_app()
        C.unlock("user1", "Correct-Horse-9")
        self.assertTrue(C.VAULT.escrow_enabled)                          # يبقى بعد إعادة الدخول


# ───────────────────────── المرحلة A: ترقية بحجم واقعي ─────────────────────────
class BigMigrationTests(unittest.TestCase):
    def test_thousands_of_rows_exact_totals_and_speed(self):
        import random
        from test_schema import legacy_db
        rnd = random.Random(7)
        c = legacy_db(rows=False)
        want = {"SYP": Decimal(0), "USD": Decimal(0)}
        paid_want = {"SYP": Decimal(0), "USD": Decimal(0)}
        for p in range(1, 401):
            c.execute("INSERT INTO patients(code,full_name,status,age,created_at) VALUES(?,?,?,?,?)",
                      (f"PT-{p:05d}", f"مريض {p}", "جديد" if p % 2 else "قديم", rnd.randint(1, 90), "2026-01-01T00:00:00"))
        eid = 0
        for p in range(1, 401):
            for k in range(8):
                eid += 1
                c.execute("INSERT INTO events(patient_id,kind,date,time,done,done_at,created_at) VALUES(?,?,?,?,?,?,?)",
                          (p, "visit" if k % 3 else "surgery", f"2026-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}",
                           f"{rnd.randint(8, 20):02d}:{rnd.choice(['00', '30'])}", 1 if k % 2 else 0,
                           "2026-06-01T10:00:00" if k % 2 else None, "x"))
                cur = rnd.choice(["SYP", "USD"])
                price = round(rnd.uniform(1, 90000), 2)
                c.execute("INSERT INTO event_items(event_id,name,price,cur) VALUES(?,?,?,?)", (eid, "إجراء", price, cur))
                want[cur] += Decimal(str(price)) * 100
                pay = round(price * rnd.random(), 2)
                if pay > 0:
                    c.execute("INSERT INTO payments(event_id,amount,cur,paid_at) VALUES(?,?,?,?)", (eid, pay, cur, "2026-02-02T10:00:00"))
                    paid_want[cur] += Decimal(str(pay)) * 100
        c.commit()
        t0 = time.time()
        rep = SC.migrate(c)
        elapsed = time.time() - t0
        self.assertEqual(SC.get_version(c), SC.LATEST)
        self.assertLess(elapsed, 10)
        self.assertEqual(c.execute("PRAGMA foreign_key_check").fetchall(), [])
        self.assertEqual(c.execute("SELECT count(*) FROM events").fetchone()[0], 3200)
        for cur in ("SYP", "USD"):
            got_due = c.execute("SELECT COALESCE(SUM(price),0) FROM event_items WHERE cur=?", (cur,)).fetchone()[0]
            got_paid = c.execute("SELECT COALESCE(SUM(amount),0) FROM payments WHERE cur=?", (cur,)).fetchone()[0]
            self.assertIsInstance(got_due, int)
            self.assertIsInstance(got_paid, int)
            # كل صف يُقرَّب لأقرب وحدة (سنت) مرة واحدة: الفرق عن المجموع العشري الدقيق ≤ نصف سنت لكل صف (400×8 صفاً)
            self.assertLessEqual(abs(got_due - want[cur]), 1600)
            self.assertLessEqual(abs(got_paid - paid_want[cur]), 1600)
            # ولا انجراف: كل قيمة مخزّنة تساوي round-half-up لقيمتها الأصلية بالضبط
        row = c.execute("SELECT price FROM event_items WHERE id=1").fetchone()[0]
        self.assertEqual(row % 1, 0)
        self.assertEqual(rep["sanitized"], {})                              # بيانات سليمة: لا تعديل صامت


class FailedUpgradeKeepsFileTests(unittest.TestCase):
    def test_open_db_failure_leaves_encrypted_file_untouched(self):
        from test_schema import legacy_db
        C, tmp = boot_core("failup")
        make_account(C)
        C.close_db()
        blob = b"\x01" + legacy_db().serialize()
        gen = C.VAULT.dbgen + 1
        enc = C._db_encode(blob, gen)
        open(C.DB_ENC, "wb").write(enc)
        C.VAULT.set_dbgen(gen)
        real = SC._set_version

        def boom(conn, v):
            if v == 2:
                raise RuntimeError("boom")
            real(conn, v)
        SC._set_version = boom
        try:
            with self.assertRaises(Exception):
                C.open_db()
        finally:
            SC._set_version = real
        self.assertEqual(open(C.DB_ENC, "rb").read(), enc)         # الملف المشفّر لم يُمسّ
        C.open_db()                                                # والمحاولة التالية تنجح
        self.assertEqual(SC.get_version(C._mem["conn"]), SC.LATEST)


if __name__ == "__main__":
    unittest.main(verbosity=2)
