# -*- coding: utf-8 -*-
"""
test_migrations.py — ترقيات القاعدة (PRAGMA user_version)، المبالغ الصحيحة، وقيود CHECK.
تعمل على migrations.py وحده بقواعد في الذاكرة (لا تمسّ بياناتك).      python tests/test_migrations.py
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import migrations as MG                                # noqa: E402

FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        FAILS.append(name)


def raises(fn, exc=Exception):
    try:
        fn()
    except exc:
        return True
    return False


def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c


def legacy_26(c, with_clinical=True):
    """مخطط 2.5/2.6 كما أنتجه init_db القديم: مبالغ REAL وبلا قيود."""
    c.executescript("""
    CREATE TABLE patients(id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, full_name TEXT NOT NULL, gender TEXT, age INTEGER,
        residence TEXT, phone TEXT, job TEXT, diseases TEXT, notes TEXT, blood TEXT, status TEXT, folder TEXT,
        photo_before TEXT, photo_after TEXT, photo_lab TEXT, created_at TEXT, updated_at TEXT);
    CREATE TABLE attachments(id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE, path TEXT, name TEXT);
    CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        kind TEXT NOT NULL, date TEXT NOT NULL, done INTEGER DEFAULT 0, done_at TEXT, notes TEXT, created_at TEXT);
    CREATE TABLE event_items(id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        name TEXT NOT NULL, price REAL NOT NULL DEFAULT 0, cur TEXT NOT NULL DEFAULT 'SYP');
    CREATE TABLE payments(id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        amount REAL NOT NULL, paid_at TEXT, note TEXT, cur TEXT NOT NULL DEFAULT 'SYP');
    CREATE INDEX ix_pat_code ON patients(code);
    """)
    for col, d in (("time", "TEXT"), ("photo_before", "TEXT"), ("photo_after", "TEXT"), ("in_report", "INTEGER DEFAULT 0"),
                   ("amount_due", "REAL DEFAULT 0"), ("cancelled", "INTEGER DEFAULT 0"), ("cancelled_at", "TEXT"),
                   ("cancel_reason", "TEXT")):
        c.execute(f"ALTER TABLE events ADD COLUMN {col} {d}")
    if with_clinical:
        for col in ("allergies", "medications", "diagnosis"):
            c.execute(f"ALTER TABLE patients ADD COLUMN {col} TEXT")
        c.execute("ALTER TABLE events ADD COLUMN duration_min INTEGER")
        c.execute("ALTER TABLE events ADD COLUMN no_show INTEGER DEFAULT 0")
    c.commit()


def populate(c):
    c.execute("INSERT INTO patients(code,full_name,age,phone) VALUES('PT-00001','سارة أحمد خليل',28,'0944')")
    c.execute("INSERT INTO patients(code,full_name,age) VALUES('PT-00002','ليلى حسن عمر',41)")
    c.execute("INSERT INTO patients(code,full_name) VALUES('PT-00003','مريض محذوف لاحقاً')")
    c.execute("INSERT INTO events(patient_id,kind,date,time,done,cancelled,no_show,duration_min) VALUES(1,'surgery','2026-05-01','10:00',1,0,0,120)")
    c.execute("INSERT INTO events(patient_id,kind,date,time,done,cancelled,no_show) VALUES(1,'visit','2026-05-09','09:30',0,1,1)")
    c.execute("INSERT INTO events(patient_id,kind,date,time) VALUES(2,'visit','2026-05-10','11:15')")
    # مبالغ بكسور سنتات وأعداد كبيرة بالليرة
    for ev, name, price, cur in ((1, "عملية", 1250.35, "USD"), (1, "تخدير", 99.99, "USD"), (1, "مستلزمات", 3_750_000.0, "SYP"),
                                 (3, "كشف", 0.1 + 0.2, "USD"), (3, "فحص", 2.675, "USD"), (3, "أشعة", 15000.0, "SYP")):
        c.execute("INSERT INTO event_items(event_id,name,price,cur) VALUES(?,?,?,?)", (ev, name, price, cur))
    for ev, amt, cur in ((1, 500.10, "USD"), (1, 750.25, "USD"), (1, 1_000_000.0, "SYP"), (3, 0.1, "USD")):
        c.execute("INSERT INTO payments(event_id,amount,cur,paid_at) VALUES(?,?,?,'2026-05-02T10:00:00')", (ev, amt, cur))
    c.execute("DELETE FROM patients WHERE id=3")                      # يترك فجوة في sqlite_sequence
    c.commit()


def sums(c, items_col, pays_col):
    f = lambda sql: {r[0]: r[1] for r in c.execute(sql)}
    return (f(f"SELECT cur, SUM({items_col}) FROM event_items GROUP BY cur"), f(f"SELECT cur, SUM({pays_col}) FROM payments GROUP BY cur"))


def t_fresh():
    c = conn()
    info = MG.migrate(c)
    check("قاعدة جديدة: تُنشأ بآخر مخطط", info["created"] and MG.user_version(c) == MG.LATEST == 3 and set(MG.TABLES) <= MG.tables(c))
    c.execute("INSERT INTO patients(full_name) VALUES('مريض')")
    ok = lambda sql, *a: not raises(lambda: c.execute(sql, a), sqlite3.IntegrityError)
    check("قيد العمر", not ok("INSERT INTO patients(full_name,age) VALUES('x',200)") and ok("INSERT INTO patients(full_name,age) VALUES('x',30)"))
    check("قيد الاسم غير الفارغ", not ok("INSERT INTO patients(full_name) VALUES('   ')"))
    check("قيد نوع الموعد", not ok("INSERT INTO events(patient_id,kind,date) VALUES(1,'consult','2026-01-01')"))
    check("قيد صيغة التاريخ والوقت", not ok("INSERT INTO events(patient_id,kind,date) VALUES(1,'visit','غدا')") and
          not ok("INSERT INTO events(patient_id,kind,date,time) VALUES(1,'visit','2026-01-01','25:00')") and
          ok("INSERT INTO events(patient_id,kind,date,time) VALUES(1,'visit','2026-01-01','09:30')"))
    check("قيد المدة", not ok("INSERT INTO events(patient_id,kind,date,duration_min) VALUES(1,'visit','2026-01-01',2)"))
    check("«لم يحضر» يتطلب إلغاءً", not ok("INSERT INTO events(patient_id,kind,date,no_show) VALUES(1,'visit','2026-01-01',1)") and
          ok("INSERT INTO events(patient_id,kind,date,no_show,cancelled) VALUES(1,'visit','2026-01-02',1,1)"))
    check("لا موعد منجز وملغى معاً", not ok("INSERT INTO events(patient_id,kind,date,done,cancelled) VALUES(1,'visit','2026-01-03',1,1)"))
    check("قيد السعر والدفعة والعملة", not ok("INSERT INTO event_items(event_id,name,price_minor) VALUES(1,'x',-1)") and
          not ok("INSERT INTO payments(event_id,amount_minor) VALUES(1,0)") and
          not ok("INSERT INTO event_items(event_id,name,price_minor,cur) VALUES(1,'x',5,'EUR')"))
    check("الأعمدة الجديدة موجودة والقديمة (REAL) غائبة", "price_minor" in MG._cols(c, "event_items") and
          "price" not in MG._cols(c, "event_items") and "amount_minor" in MG._cols(c, "payments"))
    check("الفهارس منشأة", {"ix_pat_code", "ix_ev_pat", "ix_ev_date", "ix_items_ev", "ix_pay_ev", "ix_att_pat"} <=
          {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='index'")})
    check("ترقية ثانية: لا شيء", MG.migrate(c)["from"] == 3 and not MG.migrate(c)["fixed"])
    check("المفاتيح الأجنبية مفعّلة", raises(lambda: c.execute("INSERT INTO events(patient_id,kind,date) VALUES(999,'visit','2026-01-01')"),
                                              sqlite3.IntegrityError))


def t_legacy_26():
    c = conn()
    legacy_26(c)
    populate(c)
    before = sums(c, "price", "amount")
    info = MG.migrate(c)
    after_i, after_p = sums(c, "price_minor", "amount_minor")
    check("v0 → v3 (ترقية قاعدة 2.6 الفعلية)", info["from"] == 0 and MG.user_version(c) == 3 and not info["created"])
    check("المبالغ صحيحة: USD تكاليف", after_i["USD"] == round(1250.35 * 100) + round(99.99 * 100) + 30 + 268, str(after_i))
    check("0.1+0.2 → 30 سنتاً، و2.675 → 268 (نصف لأعلى)", c.execute("SELECT price_minor FROM event_items WHERE name='كشف'").fetchone()[0] == 30
          and c.execute("SELECT price_minor FROM event_items WHERE name='فحص'").fetchone()[0] in (267, 268))
    check("الليرة: أعداد كبيرة دقيقة", after_i["SYP"] == 3_750_000 * 100 + 15000 * 100 and after_p["SYP"] == 1_000_000 * 100)
    check("مجموع الدفعات بالدولار = 1250.35 بلا كسور عائمة", after_p["USD"] == 50010 + 75025 + 10)
    check("لا بيانات ضاعت (عدد الصفوف)", c.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 2 and
          c.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 3 and c.execute("SELECT COUNT(*) FROM event_items").fetchone()[0] == 6
          and c.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 4)
    check("لا شيء احتاج إصلاحاً في بيانات سليمة", info["fixed"] == {}, str(info["fixed"]))
    ev2 = c.execute("SELECT * FROM events WHERE id=2").fetchone()
    check("حالة «لم يحضر» والمدة بقيتا", ev2["cancelled"] == 1 and ev2["no_show"] == 1 and
          c.execute("SELECT duration_min FROM events WHERE id=1").fetchone()[0] == 120)
    c.execute("INSERT INTO patients(full_name) VALUES('جديد')")
    check("المعرّفات لا تُعاد (sqlite_sequence حُفظ بعد حذف مريض)", c.execute("SELECT MAX(id) FROM patients").fetchone()[0] == 4)
    check("الحذف المتسلسل يعمل بعد إعادة البناء", (c.execute("DELETE FROM patients WHERE id=1"), c.execute(
        "SELECT COUNT(*) FROM event_items").fetchone()[0])[1] == 3)
    check("ترقية ثانية بلا أثر", MG.migrate(c)["from"] == 3)


def t_very_old():
    c = conn()
    c.executescript("""
    CREATE TABLE patients(id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, full_name TEXT NOT NULL);
    CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL, kind TEXT NOT NULL, date TEXT NOT NULL,
        done INTEGER DEFAULT 0, done_at TEXT, notes TEXT, created_at TEXT);
    CREATE TABLE event_items(id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL, name TEXT NOT NULL, price REAL NOT NULL DEFAULT 0);
    CREATE TABLE payments(id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL, amount REAL NOT NULL, paid_at TEXT, note TEXT);
    INSERT INTO patients(code,full_name) VALUES('PT-00001','قديم جداً');
    INSERT INTO events(patient_id,kind,date) VALUES(1,'visit','2025-01-01');
    INSERT INTO event_items(event_id,name,price) VALUES(1,'كشف',25.5);
    INSERT INTO payments(event_id,amount) VALUES(1,10);
    """)
    c.commit()
    info = MG.migrate(c, legacy_currency="USD")
    check("قاعدة قديمة جداً (بلا عمود عملة ولا وقت) تُرقّى", MG.user_version(c) == 3 and info["from"] == 0)
    check("عملة البيانات القديمة من الإعداد القديم (USD)", c.execute("SELECT cur, price_minor FROM event_items").fetchone()[:] == ("USD", 2550) and
          c.execute("SELECT cur, amount_minor FROM payments").fetchone()[:] == ("USD", 1000))


def t_dirty():
    c = conn()
    legacy_26(c)
    c.executescript("""
    INSERT INTO patients(id,code,full_name,age) VALUES(1,'A','سليم',30),(2,'B','   ',200),(3,'C','عمر سالب',-5);
    INSERT INTO events(id,patient_id,kind,date,time,done,cancelled,no_show,duration_min,created_at) VALUES
      (1,1,'consult','2026-01-01','9:30',0,0,0,2,'2025-12-30T10:00:00'),
      (2,1,'visit','غير تاريخ','25:61',1,1,0,NULL,'2025-12-31T10:00:00'),
      (3,1,'visit','2026-01-03',NULL,0,0,1,NULL,NULL),
      (4,2,'surgery','2026-01-04','08:00',NULL,NULL,NULL,90,NULL);
    INSERT INTO event_items(id,event_id,name,price,cur) VALUES (1,1,'سالب',-50,'SYP'),(2,1,'عملة غريبة',10,'EUR'),(3,4,'سليم',20,'USD'),
        (4,1,'  ',5,'SYP');
    INSERT INTO payments(id,event_id,amount,cur) VALUES (1,1,0,'SYP'),(2,1,-3,'SYP'),(3,4,5,'GBP'),(4,4,2.5,'USD');
    """)
    c.execute("PRAGMA foreign_keys=OFF")
    c.execute("INSERT INTO events(id,patient_id,kind,date) VALUES(9,77,'visit','2026-01-09')")          # يتيم: مريض غير موجود
    c.execute("INSERT INTO event_items(event_id,name,price) VALUES(9,'يتيم',1)")
    c.execute("INSERT INTO event_items(event_id,name,price) VALUES(123,'يتيم2',1)")
    c.execute("INSERT INTO payments(event_id,amount) VALUES(123,1)")
    c.commit()
    c.execute("PRAGMA foreign_keys=ON")
    info = MG.migrate(c)
    f = info["fixed"]
    check("الترقية تنجح رغم البيانات المخالفة", MG.user_version(c) == 3)
    check("تُحصى الإصلاحات", f.get("patients.age") == 2 and f.get("patients.name") == 1 and f.get("events.kind") == 1 and
          f.get("events.date") == 1 and f.get("events.time") == 1 and f.get("events.duration") == 1 and f.get("events.orphan") == 1 and
          f.get("items.price") == 1 and f.get("items.cur") == 1 and f.get("payments.nonpositive") == 2 and f.get("payments.cur") == 1, str(f))
    row = lambda sql: c.execute(sql).fetchone()
    check("اسم فارغ وعمر خارج النطاق", row("SELECT full_name, age FROM patients WHERE id=2")[:] == ("(بلا اسم)", None) and
          row("SELECT age FROM patients WHERE id=3")[0] is None and row("SELECT age FROM patients WHERE id=1")[0] == 30)
    e1 = row("SELECT * FROM events WHERE id=1")
    check("نوع غير معروف → مراجعة، ووقت 9:30 → 09:30، ومدة خارج النطاق → NULL", e1["kind"] == "visit" and e1["time"] == "09:30" and e1["duration_min"] is None)
    e2 = row("SELECT * FROM events WHERE id=2")
    check("تاريخ فاسد يُستبدل بتاريخ الإنشاء، ووقت فاسد → NULL، ومنجز+ملغى → منجز", e2["date"] == "2025-12-31" and e2["time"] is None
          and e2["done"] == 1 and e2["cancelled"] == 0)
    e3 = row("SELECT * FROM events WHERE id=3")
    check("«لم يحضر» بلا إلغاء → يُصفَّر، وتاريخ بلا created_at سليم يبقى", e3["no_show"] == 0 and e3["cancelled"] == 0 and e3["date"] == "2026-01-03")
    e4 = row("SELECT * FROM events WHERE id=4")
    check("القيم الفارغة (NULL) تصبح 0", (e4["done"], e4["cancelled"], e4["no_show"], e4["in_report"]) == (0, 0, 0, 0) and e4["duration_min"] == 90)
    check("اليتيم يُحذف مع توابعه (لا مفاتيح مكسورة)", not c.execute("SELECT 1 FROM events WHERE id=9").fetchone() and
          not c.execute("SELECT 1 FROM event_items WHERE event_id IN (9,123)").fetchone() and not c.execute("PRAGMA foreign_key_check").fetchall())
    check("السعر السالب → 0، وعملة غريبة → SYP، واسم فارغ → «إجراء»", row("SELECT price_minor FROM event_items WHERE id=1")[0] == 0 and
          row("SELECT cur FROM event_items WHERE id=2")[0] == "SYP" and row("SELECT name FROM event_items WHERE id=4")[0] == "إجراء")
    check("الدفعات غير الموجبة تُحذف، والصالحة تبقى", [tuple(r) for r in c.execute("SELECT id, amount_minor, cur FROM payments ORDER BY id")] ==
          [(3, 500, "SYP"), (4, 250, "USD")])


def t_failure_and_versions():
    c = conn()
    legacy_26(c)
    populate(c)
    c.execute("CREATE TABLE patients_new(x)")                       # يمنع إنشاء الجدول المؤقت → فشل في منتصف الخطوة 3
    c.commit()
    ok = raises(lambda: MG.migrate(c), sqlite3.OperationalError)
    check("فشل منتصف الترقية يرفع الخطأ", ok)
    check("…ويُرجع كل شيء: الإصدار 2 والمبالغ REAL والبيانات كاملة", MG.user_version(c) == 2 and "price" in MG._cols(c, "event_items")
          and c.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 4 and c.execute("SELECT COUNT(*) FROM patients").fetchone()[0] == 2)
    check("…والمفاتيح الأجنبية أُعيد تفعيلها بعد الفشل", c.execute("PRAGMA foreign_keys").fetchone()[0] == 1)
    c.execute("DROP TABLE patients_new")
    c.commit()
    MG.migrate(c)
    check("بعد إزالة العائق تنجح الترقية من الإصدار 2", MG.user_version(c) == 3)
    d = conn()
    d.execute("PRAGMA user_version=99")
    check("إصدار أحدث من المدعوم → SchemaTooNew", raises(lambda: MG.migrate(d), MG.SchemaTooNew))
    e = conn()
    legacy_26(e, with_clinical=False)
    MG.migrate(e)
    check("قاعدة 2.5 (بلا حقول 2.6) تصل v3 بالأعمدة الجديدة", MG.user_version(e) == 3 and "allergies" in MG._cols(e, "patients")
          and "no_show" in MG._cols(e, "events"))
    f = conn()
    legacy_26(f)
    f.execute("PRAGMA user_version=1")
    MG.migrate(f)
    check("الاستئناف من إصدار وسيط (1 → 3)", MG.user_version(f) == 3)


def main():
    t_fresh()
    t_legacy_26()
    t_very_old()
    t_dirty()
    t_failure_and_versions()
    print("\n" + ("ALL PASSED" if not FAILS else f"FAILED: {FAILS}"))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
