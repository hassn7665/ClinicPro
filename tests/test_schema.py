# -*- coding: utf-8 -*-
"""اختبارات الترقيات (PRAGMA user_version) وقيود CHECK والمبالغ الصحيحة. تشغيل: python tests/test_schema.py"""
import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import boot_core, make_account  # noqa: E402

import schema as SC  # noqa: E402


def legacy_db(rows=True):
    """قاعدة بالمخطط القديم (user_version=0، مبالغ REAL) كما أنتجها الإصدار 2.6."""
    c = sqlite3.connect(":memory:")
    c.execute("PRAGMA foreign_keys=ON")
    SC._m1_legacy(c)
    c.commit()
    if rows:
        c.execute("INSERT INTO patients(code,full_name,status,age,created_at) VALUES('PT-00001','أحمد','جديد',30,'2026-01-01T10:00:00')")
        c.execute("INSERT INTO patients(code,full_name,status,age,created_at) VALUES('PT-00002','سلمى','قديم',210,'2026-01-02T10:00:00')")
        c.execute("INSERT INTO events(patient_id,kind,date,time,done,cancelled,no_show,duration_min,amount_due,created_at) "
                  "VALUES(1,'visit','2026-1-5','9:05',0,0,0,30,12.345,'x')")
        c.execute("INSERT INTO events(patient_id,kind,date,done,cancelled,no_show,created_at) VALUES(1,'surgery','2026-02-01',1,1,0,'x')")
        c.execute("INSERT INTO event_items(event_id,name,price,cur) VALUES(1,'كشف',1500.5,'SYP')")
        c.execute("INSERT INTO event_items(event_id,name,price,cur) VALUES(1,'تحاليل',0.1,'USD')")
        c.execute("INSERT INTO event_items(event_id,name,price,cur) VALUES(1,'تحاليل 2',0.2,'USD')")
        c.execute("INSERT INTO payments(event_id,amount,cur,paid_at) VALUES(1,1000.25,'SYP','2026-01-05T10:00:00')")
        c.execute("INSERT INTO payments(event_id,amount,cur,paid_at) VALUES(1,0.30000000000000004,'USD','2026-01-05T10:00:00')")
        c.execute("INSERT INTO attachments(patient_id,path,name) VALUES(1,'patients/PT-00001/a.bin','a.jpg')")
        # رقم تسلسلي أكبر من max(id) الحالي: يجب ألا يُعاد استعماله بعد الترقية
        c.execute("UPDATE sqlite_sequence SET seq=50 WHERE name='patients'")
        c.commit()
    return c


class MigrationTests(unittest.TestCase):
    def test_fresh_db_reaches_latest(self):
        c = sqlite3.connect(":memory:")
        rep = SC.migrate(c)
        self.assertEqual(SC.get_version(c), SC.LATEST)
        self.assertEqual(rep["applied"], [1, 2, 3, 4])
        self.assertEqual(c.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_idempotent(self):
        c = sqlite3.connect(":memory:")
        SC.migrate(c)
        self.assertEqual(SC.migrate(c)["applied"], [])

    def test_legacy_data_converted_exactly(self):
        c = legacy_db()
        self.assertEqual(SC.get_version(c), 0)
        rep = SC.migrate(c, "SYP")
        self.assertEqual(SC.get_version(c), SC.LATEST)
        q = lambda sql: c.execute(sql).fetchall()
        self.assertEqual(q("SELECT price FROM event_items ORDER BY id"), [(150050,), (10,), (20,)])
        self.assertEqual(q("SELECT amount FROM payments ORDER BY id"), [(100025,), (30,)])      # 0.30000000000000004 → 30 بلا انجراف
        self.assertEqual(q("SELECT amount_due FROM events WHERE id=1"), [(1235,)])               # 12.345 → 12.35 (نصف للأعلى)
        self.assertEqual(q("SELECT typeof(price) FROM event_items")[0][0], "integer")
        self.assertEqual(q("SELECT date, time FROM events WHERE id=1"), [("2026-01-05", "09:05")])  # تطبيع الصيغة
        # متناقضة: منجز + ملغى ← المنجز
        self.assertEqual(q("SELECT status, done_at IS NOT NULL FROM events WHERE id=2"), [("done", 1)])
        self.assertEqual(q("SELECT status FROM events WHERE id=1"), [("pending",)])
        # عمر → سنة ميلاد تقريبية (سنة الإنشاء − العمر)؛ عمر غير معقول ← NULL مع تسجيله في التقرير
        self.assertEqual(q("SELECT birth_date FROM patients ORDER BY id"), [("1996",), (None,)])
        self.assertEqual(rep["sanitized"]["patients.bad_age"], 1)
        self.assertEqual(rep["sanitized"]["events.done_and_cancelled"], 1)
        # العلاقات والفهارس سليمة
        self.assertEqual(q("PRAGMA foreign_key_check"), [])
        self.assertEqual(q("PRAGMA integrity_check"), [("ok",)])
        names = {r[0] for r in q("SELECT name FROM sqlite_master WHERE type='index'")}
        self.assertTrue({"ix_pat_code", "ix_ev_pat", "ix_pay_ev"} <= names)

    def test_autoincrement_sequence_preserved(self):
        c = legacy_db()
        SC.migrate(c)
        c.execute("INSERT INTO patients(full_name, status) VALUES('جديد كلياً','جديد')")
        self.assertEqual(c.execute("SELECT max(id) FROM patients").fetchone()[0], 51)

    def test_legacy_usd_currency_flag(self):
        c = legacy_db(rows=False)
        c.execute("INSERT INTO patients(full_name,status) VALUES('x','جديد')")
        c.execute("INSERT INTO events(patient_id,kind,date) VALUES(1,'visit','2026-01-01')")
        c.execute("INSERT INTO event_items(event_id,name,price) VALUES(1,'a',5)")
        c.execute("ALTER TABLE event_items DROP COLUMN cur")           # يحاكي قاعدة سبقت عمود العملة
        c.commit()
        SC.migrate(c, "USD")
        self.assertEqual(c.execute("SELECT cur, price FROM event_items").fetchall(), [("USD", 500)])

    def test_failed_migration_rolls_back(self):
        c = legacy_db()
        real = SC._set_version

        def boom(conn, v):
            if v == 2:
                raise RuntimeError("boom")
            real(conn, v)
        SC._set_version = boom
        try:
            with self.assertRaises(RuntimeError):
                SC.migrate(c)
        finally:
            SC._set_version = real
        self.assertEqual(SC.get_version(c), 1)                          # الخطوة 1 ثبتت، والخطوة 2 أُلغيت كلياً
        self.assertEqual(c.execute("SELECT typeof(price) FROM event_items LIMIT 1").fetchone()[0], "real")
        self.assertEqual(c.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(c.execute("SELECT count(*) FROM patients").fetchone()[0], 2)
        SC.migrate(c)                                                   # وإعادة المحاولة تنجح
        self.assertEqual(SC.get_version(c), SC.LATEST)

    def test_newer_database_refused(self):
        c = sqlite3.connect(":memory:")
        c.execute(f"PRAGMA user_version={SC.LATEST + 1}")
        with self.assertRaises(SC.SchemaError):
            SC.migrate(c)

    def test_already_strict_tables_without_version_not_reconverted(self):
        """قاعدة محمَّلة من نسخة نصية فقدت user_version: لا تُضرب المبالغ ×100 مرة ثانية."""
        c = legacy_db()
        SC.migrate(c)
        c.execute("PRAGMA user_version=0")
        c.commit()
        SC.migrate(c)
        self.assertEqual(c.execute("SELECT price FROM event_items WHERE id=1").fetchone()[0], 150050)


class V3V4Tests(unittest.TestCase):
    def test_database_already_at_v3_upgrades_to_v4_only(self):
        """هاتف اختبار سبق أن رُقّي إلى v3 (ظهر في سجل التشخيص: frm=0 to=3) يتابع من v3 دون إعادة ما سبق."""
        c = legacy_db()
        SC.migrate(c)
        c.execute("ALTER TABLE patients ADD COLUMN age INTEGER")        # يحاكي مخطط v3: age بدل birth_date
        c.execute("UPDATE patients SET age=33")
        c.execute("ALTER TABLE patients DROP COLUMN birth_date")
        c.execute("PRAGMA user_version=3")
        c.commit()
        rep = SC.migrate(c)
        self.assertEqual((rep["from"], rep["applied"]), (3, [4]))
        self.assertEqual(SC.get_version(c), 4)
        self.assertEqual(c.execute("SELECT count(*) FROM patients WHERE birth_date IS NOT NULL").fetchone()[0], 2)


    def test_status_mapping_from_every_flag_combination(self):
        c = legacy_db(rows=False)
        c.execute("INSERT INTO patients(full_name,status,created_at) VALUES('p','جديد','2025-03-01T00:00:00')")
        combos = [(0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 1, 1), (1, 1, 0), (0, 0, 1)]
        for i, (d, ca, ns) in enumerate(combos, 1):
            c.execute("INSERT INTO events(patient_id,kind,date,done,cancelled,no_show,done_at,cancelled_at,created_at) "
                      "VALUES(1,'visit','2026-01-%02d',?,?,?,NULL,NULL,'2026-01-01T09:00:00')" % i, (d, ca, ns))
        c.commit()
        rep = SC.migrate(c)
        got = [r[0] for r in c.execute("SELECT status FROM events ORDER BY id")]
        self.assertEqual(got, ["pending", "done", "cancelled", "no_show", "done", "pending"])
        self.assertEqual(c.execute("SELECT count(*) FROM events WHERE status='done' AND done_at IS NULL").fetchone()[0], 0)
        self.assertEqual(c.execute("SELECT count(*) FROM events WHERE status IN ('cancelled','no_show') AND cancelled_at IS NULL").fetchone()[0], 0)
        self.assertGreaterEqual(rep["sanitized"].get("events.done_without_time", 0), 2)
        cols = [r[1] for r in c.execute("PRAGMA table_info(events)")]
        self.assertNotIn("done", cols)
        self.assertNotIn("cancelled", cols)
        self.assertNotIn("no_show", cols)

    def test_children_survive_event_table_rebuild(self):
        c = legacy_db()
        SC.migrate(c)
        self.assertEqual(c.execute("SELECT count(*) FROM event_items").fetchone()[0], 3)
        self.assertEqual(c.execute("SELECT count(*) FROM payments").fetchone()[0], 2)
        c.execute("DELETE FROM events WHERE id=1")                         # الحذف المتسلسل ما زال يعمل
        self.assertEqual(c.execute("SELECT count(*) FROM payments").fetchone()[0], 0)

    def test_birth_date_and_age(self):
        from datetime import date
        self.assertEqual(SC.age_on("1990-05-23", date(2026, 5, 22)), 35)
        self.assertEqual(SC.age_on("1990-05-23", date(2026, 5, 23)), 36)
        self.assertEqual(SC.age_on("1990", date(2026, 1, 1)), 36)
        self.assertIsNone(SC.age_on(None))
        self.assertIsNone(SC.age_on("garbage"))


class ConstraintTests(unittest.TestCase):
    def setUp(self):
        self.c = sqlite3.connect(":memory:")
        SC.migrate(self.c)
        self.c.execute("PRAGMA foreign_keys=ON")
        self.c.execute("INSERT INTO patients(full_name,status) VALUES('م','جديد')")
        self.c.execute("INSERT INTO events(patient_id,kind,date) VALUES(1,'visit','2026-01-01')")

    def bad(self, sql, *a):
        with self.assertRaises(sqlite3.IntegrityError):
            self.c.execute(sql, a)

    def test_checks(self):
        self.bad("INSERT INTO patients(full_name) VALUES('   ')")
        self.bad("INSERT INTO patients(full_name,birth_date) VALUES('x','90-1-1')")
        self.bad("INSERT INTO patients(full_name,birth_date) VALUES('x','abcd')")
        self.bad("INSERT INTO patients(full_name,status) VALUES('x','غريب')")
        self.bad("INSERT INTO events(patient_id,kind,date) VALUES(1,'other','2026-01-01')")
        self.bad("INSERT INTO events(patient_id,kind,date) VALUES(1,'visit','2026-1-1')")
        self.bad("INSERT INTO events(patient_id,kind,date,time) VALUES(1,'visit','2026-01-01','9:5')")
        self.bad("INSERT INTO events(patient_id,kind,date,duration_min) VALUES(1,'visit','2026-01-01',1)")
        self.bad("INSERT INTO events(patient_id,kind,date,status) VALUES(1,'visit','2026-01-01','weird')")
        self.bad("INSERT INTO events(patient_id,kind,date,status) VALUES(1,'visit','2026-01-01','done')")            # بلا done_at
        self.bad("INSERT INTO events(patient_id,kind,date,status) VALUES(1,'visit','2026-01-01','cancelled')")      # بلا cancelled_at
        self.bad("INSERT INTO events(patient_id,kind,date,status) VALUES(1,'visit','2026-01-01','no_show')")
        self.bad("INSERT INTO event_items(event_id,name,price,cur) VALUES(1,'a',-5,'SYP')")
        self.bad("INSERT INTO event_items(event_id,name,price,cur) VALUES(1,'a',5,'EUR')")
        self.bad("INSERT INTO payments(event_id,amount,cur) VALUES(1,0,'SYP')")
        self.bad("INSERT INTO payments(event_id,amount,cur) VALUES(1,5,'EUR')")
        self.bad("INSERT INTO payments(event_id,amount,cur) VALUES(99,5,'SYP')")          # مفتاح أجنبي

    def test_valid_states_accepted(self):
        self.c.execute("INSERT INTO events(patient_id,kind,date,status,done_at) VALUES(1,'visit','2026-01-01','done','2026-01-01T10:00:00')")
        self.c.execute("INSERT INTO events(patient_id,kind,date,status,cancelled_at) VALUES(1,'visit','2026-01-01','no_show','2026-01-02T10:00:00')")
        self.c.execute("INSERT INTO patients(full_name,birth_date) VALUES('y','1990')")
        self.c.execute("INSERT INTO patients(full_name,birth_date) VALUES('z','1990-05-23')")

    def test_cascade_still_works(self):
        self.c.execute("INSERT INTO event_items(event_id,name,price,cur) VALUES(1,'a',5,'SYP')")
        self.c.execute("DELETE FROM patients WHERE id=1")
        self.assertEqual(self.c.execute("SELECT count(*) FROM event_items").fetchone()[0], 0)


class MoneyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.C, _ = boot_core("money")

    def test_parse_and_format_roundtrip(self):
        C = self.C
        for text, minor, shown in (("1500", 150000, "1,500"), ("1,500.5", 150050, "1,500.50"), ("٢٥٠٠٫٧٥", 250075, "2,500.75"),
                                   ("0.1", 10, "0.10"), ("0.005", 1, "0.01"), ("0", 0, "0"), ("1000000", 100000000, "1,000,000")):
            v = C.parse_money(text)
            self.assertIsInstance(v, int)
            self.assertEqual(v, minor, text)
            self.assertEqual(C.money(v), shown, text)
            self.assertEqual(C.parse_money(C.money(v)), v)             # ما يُعرض يُقرأ نفسه (حقول التعديل)

    def test_rejects_bad_input(self):
        for bad in ("", "abc", "-5", "nan", "inf", "1e400", "13000000000000"):
            with self.assertRaises(ValueError, msg=bad):
                self.C.parse_money(bad)

    def test_no_float_drift(self):
        C = self.C
        total = sum(C.parse_money("0.1") for _ in range(10))
        self.assertEqual(total, C.parse_money("1"))                    # بالـfloat كان 0.9999999999999999

    def test_floats_rejected_loudly(self):
        for bad in (1500.0, "1500", True):
            with self.assertRaises(TypeError):
                self.C.minor(bad)

    def test_money_multi(self):
        C = self.C
        self.assertEqual(C.money_multi({"SYP": 150000, "USD": 0}), "1,500 ل.س")
        self.assertEqual(C.money_multi({"SYP": 0, "USD": 0}), "0")
        self.assertEqual(C.money(-250), "-2.50")


class EndToEndTests(unittest.TestCase):
    """تدفق مالي كامل عبر core على قاعدة مشفّرة حقيقية (ويُعاد فتحها لإثبات أن الحفظ والترقية يعملان)."""

    @classmethod
    def setUpClass(cls):
        cls.C, cls.tmp = boot_core("e2e")
        make_account(cls.C)

    def test_flow(self):
        C = self.C
        self.assertEqual(SC.get_version(C._mem["conn"]), SC.LATEST)
        p = C.save_patient(dict(full_name="مريض اختبار", gender="ذكر", age=40, residence="", phone="0944111222", job="",
                                diseases="", notes="", blood="", status="جديد"), {}, [])
        eid = C.create_event(p["id"], "visit", "2026-3-4", "9:30",
                             items=[("كشف", C.parse_money("1500.50"), "SYP"), ("دواء", C.parse_money("12.25"), "USD")])
        ev = C.q("SELECT date, time FROM events WHERE id=?", (eid,), one=True)
        self.assertEqual((ev["date"], ev["time"]), ("2026-03-04", "09:30"))
        C.add_payments(eid, [(C.parse_money("500.25"), "SYP"), (C.parse_money("12.25"), "USD")])
        due, paid, rem = C.amounts(C.ev_fin(eid))
        self.assertEqual((due["SYP"], paid["SYP"], rem["SYP"]), (150050, 50025, 100025))
        self.assertEqual(rem["USD"], 0)
        with self.assertRaises(ValueError):
            C.add_payments(eid, [(C.parse_money("1000.26"), "SYP")])        # أكبر من المتبقي بسنت واحد
        C.add_payments(eid, [(C.parse_money("1000.25"), "SYP")])            # بالضبط المتبقي
        self.assertEqual(C.amounts(C.ev_fin(eid))[2]["SYP"], 0)
        with self.assertRaises(TypeError):
            C.add_payments(eid, [(5.0, "SYP")])
        with self.assertRaises(ValueError):
            C.update_items(eid, [("كشف", C.parse_money("1"), "SYP")])       # أقل من المدفوع
        st = C.fin_stats()
        self.assertEqual(st["paid"]["SYP"], 150050)
        self.assertEqual(st["outstanding"]["SYP"], 0)
        summary = C.patient_delete_summary(p["id"])
        self.assertEqual(summary["paid"]["USD"], 1225)
        # حفظ ثم إعادة فتح الملف المشفّر: المخطط يبقى v2 والأرقام كما هي
        C.lock_app()
        self.assertEqual(C.unlock("tester", "Correct-Horse-9"), "ok")
        self.assertEqual(SC.get_version(C._mem["conn"]), SC.LATEST)
        self.assertEqual(C.fin_stats()["paid"]["SYP"], 150050)
        self.assertIn("150,050".replace("150,050", "1,500.50"), C.money(150050))

    def test_ui_repo_functions(self):
        C = self.C
        p = C.save_patient(dict(full_name="مريض ثان", gender="", age=None, residence="", phone="", job="", diseases="",
                                notes="", blood="", status="قديم"), {}, [])
        self.assertEqual(C.get_patient(p["id"])["full_name"], "مريض ثان")
        self.assertIsNone(C.get_patient(99999))
        eid = C.create_event(p["id"], "visit", "2026-05-05", "10:00")
        self.assertEqual(len(C.patient_events(p["id"])), 1)
        C.set_event_in_report(eid, True)
        self.assertEqual(C.patient_events(p["id"])[0]["in_report"], 1)
        self.assertEqual(C.patient_attachments(p["id"]), [])


class LegacyEncryptedUpgradeTests(unittest.TestCase):
    """قاعدة 2.6 مشفّرة على القرص (user_version=0 وREAL) تُفتح وترقّى وتُحفظ، مع نسخة أمان قبل الترقية."""

    def test_open_legacy_encrypted_db(self):
        C, tmp = boot_core("legacy")
        make_account(C)
        C.close_db()
        # نبني ملف db.enc بالمخطط القديم ونعيد تشفيره بمفتاح الحساب نفسه
        old = legacy_db()
        blob = b"\x01" + old.serialize()
        C._mem["conn"] = None
        gen = C.VAULT.dbgen + 1
        with open(C.DB_ENC, "wb") as f:
            f.write(C._db_encode(blob, gen))
        C.VAULT.set_dbgen(gen)
        C.open_db()
        self.assertEqual(SC.get_version(C._mem["conn"]), SC.LATEST)
        self.assertEqual(C.q("SELECT price FROM event_items WHERE id=1", one=True)[0], 150050)
        self.assertTrue(os.path.exists(C.DB_ENC + f".pre-v{SC.LATEST}"), "نسخة أمان قبل الترقية")
        C.lock_app()
        self.assertEqual(C.unlock("tester", "Correct-Horse-9"), "ok")
        self.assertEqual(C.q("SELECT price FROM event_items WHERE id=1", one=True)[0], 150050)

    def test_restore_old_backup(self):
        """نسخة احتياطية أُخذت بالإصدار القديم (REAL) تُستعاد وتُرقّى."""
        C, tmp = boot_core("restore")
        make_account(C)
        C.save_patient(dict(full_name="x", gender="", age=1, residence="", phone="", job="", diseases="", notes="",
                            blood="", status="جديد"), {}, [])
        path = os.path.join(tmp, "old.mcbk")
        old = legacy_db()
        with C._bk_open(path) as w:
            w.add("__db__", b"\x01" + old.serialize())
        C.restore_backup(path)
        self.assertEqual(SC.get_version(C._mem["conn"]), SC.LATEST)
        self.assertEqual(C.q("SELECT amount FROM payments ORDER BY id")[0][0], 100025)

    def test_text_dump_keeps_version(self):
        C, _ = boot_core("dump")
        make_account(C)
        blob = b"\x02" + ("\n".join(C._mem["conn"].iterdump()) + f"\nPRAGMA user_version={SC.LATEST};").encode()
        conn = C._new_conn(blob)
        self.assertEqual(SC.get_version(conn), SC.LATEST)


if __name__ == "__main__":
    unittest.main(verbosity=2)
