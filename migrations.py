# -*- coding: utf-8 -*-
"""
migrations.py — مخطط قاعدة البيانات وترقياته عبر PRAGMA user_version.

الإصدارات:
  1  مخطط 2.5 (أعمدة المواعيد، العملات)           — يلحق أي قاعدة قديمة جداً بالمخطط الأساسي
  2  حقول 2.6 (الحساسية/الأدوية/التشخيص، مدة الموعد، «لم يحضر»)
  3  المبالغ أعداداً صحيحة (أصغر وحدة = 1/100) + قيود CHECK (إعادة بناء الجداول بتحويل البيانات)

القواعد:
  • قاعدة جديدة (لا جداول) تُنشأ مباشرة بآخر مخطط وبإصدار LATEST.
  • قاعدة قديمة (user_version=0 مع جداول — كل ما أنتجته الإصدارات حتى 2.6) تُرقَّى خطوة خطوة، وكل خطوة معاملة
    مستقلة تنتهي بضبط user_version؛ فشل أي خطوة يُرجعها كاملةً ولا يمسّ القاعدة.
  • إصدار أحدث مما يعرفه التطبيق → SchemaTooNew (لا نفتح قاعدة قد نُتلفها).
  • الترقية 3 تُصلح البيانات المخالفة للقيود بدل أن تفشل (وتعيد عدّاد ما أُصلح للسجل)، وتتحقق أن مجاميع المبالغ
    لم تتغير، وتفحص المفاتيح الأجنبية وسلامة القاعدة قبل التثبيت.
"""
import sqlite3

LATEST = 3
# تحقق من صلاحية التاريخ/الوقت فعلاً (2026-02-30 و25:00 مرفوضان) لا مجرد الشكل
DATE_OK = "COALESCE(date(date), '') = date"            # COALESCE: CHECK يمرّر NULL، فنحوّل «غير صالح» إلى نص فارغ
TIME_OK = "COALESCE(strftime('%H:%M', time), '') = time"
TABLES = ("patients", "attachments", "events", "event_items", "payments")


class SchemaTooNew(Exception):
    def __init__(self, found, supported):
        super().__init__(f"مخطط القاعدة (v{found}) أحدث مما يدعمه هذا الإصدار من التطبيق (v{supported}). حدّث التطبيق.")
        self.found, self.supported = found, supported


def user_version(conn) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def tables(conn) -> set:
    return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}


def _cols(conn, table) -> list:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


# ───────────── مخطط آخر إصدار (v3): مصدر الحقيقة الوحيد ─────────────
def ddl(suffix: str = "") -> str:
    """CREATE TABLE بآخر مخطط. suffix لبناء جداول مؤقتة أثناء الترقية (المراجع تبقى بالأسماء النهائية)."""
    s = suffix
    return f"""
CREATE TABLE patients{s}(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    full_name TEXT NOT NULL CHECK (length(trim(full_name)) > 0),
    gender TEXT,
    age INTEGER CHECK (age IS NULL OR age BETWEEN 0 AND 130),
    residence TEXT, phone TEXT, job TEXT, diseases TEXT, notes TEXT,
    blood TEXT, status TEXT, folder TEXT,
    photo_before TEXT, photo_after TEXT, photo_lab TEXT,
    created_at TEXT, updated_at TEXT,
    allergies TEXT, medications TEXT, diagnosis TEXT);
CREATE TABLE events{s}(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('surgery','visit')),
    date TEXT NOT NULL CHECK ({DATE_OK}),
    time TEXT CHECK (time IS NULL OR {TIME_OK}),
    done INTEGER NOT NULL DEFAULT 0 CHECK (done IN (0,1)),
    done_at TEXT, notes TEXT, created_at TEXT,
    photo_before TEXT, photo_after TEXT,
    in_report INTEGER NOT NULL DEFAULT 0 CHECK (in_report IN (0,1)),
    amount_due REAL DEFAULT 0,
    cancelled INTEGER NOT NULL DEFAULT 0 CHECK (cancelled IN (0,1)),
    cancelled_at TEXT, cancel_reason TEXT,
    duration_min INTEGER CHECK (duration_min IS NULL OR duration_min BETWEEN 5 AND 720),
    no_show INTEGER NOT NULL DEFAULT 0 CHECK (no_show IN (0,1)),
    CHECK (no_show = 0 OR cancelled = 1),
    CHECK (NOT (done = 1 AND cancelled = 1)));
CREATE TABLE event_items{s}(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    price_minor INTEGER NOT NULL DEFAULT 0 CHECK (price_minor >= 0),
    cur TEXT NOT NULL DEFAULT 'SYP' CHECK (cur IN ('SYP','USD')));
CREATE TABLE payments{s}(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    paid_at TEXT, note TEXT,
    cur TEXT NOT NULL DEFAULT 'SYP' CHECK (cur IN ('SYP','USD')));
"""


ATTACHMENTS_DDL = """CREATE TABLE IF NOT EXISTS attachments(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    path TEXT, name TEXT);"""

INDEXES = """
CREATE INDEX IF NOT EXISTS ix_pat_code ON patients(code);
CREATE INDEX IF NOT EXISTS ix_ev_pat ON events(patient_id, date);
CREATE INDEX IF NOT EXISTS ix_ev_date ON events(date);
CREATE INDEX IF NOT EXISTS ix_items_ev ON event_items(event_id);
CREATE INDEX IF NOT EXISTS ix_pay_ev ON payments(event_id);
CREATE INDEX IF NOT EXISTS ix_att_pat ON attachments(patient_id);
"""


class _Tx:
    """معاملة يدوية (BEGIN IMMEDIATE) لخطوة ترقية؛ fk_off لإعادة بناء الجداول (PRAGMA خارج المعاملة)."""

    def __init__(self, conn, fk_off=False):
        self.conn, self.fk_off = conn, fk_off

    def __enter__(self):
        self.conn.commit()
        self.prev = self.conn.isolation_level
        self.conn.isolation_level = None
        if self.fk_off:
            self.conn.execute("PRAGMA foreign_keys=OFF")
        self.conn.execute("BEGIN IMMEDIATE")
        return self.conn

    def __exit__(self, et, ev, tb):
        try:
            self.conn.execute("ROLLBACK" if et else "COMMIT")
        finally:
            if self.fk_off:
                self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.isolation_level = self.prev
        return False


# ───────────── الخطوات ─────────────
def _m1_legacy(conn, info, legacy_currency):
    """يلحق القواعد القديمة بمخطط 2.5 (بالأنواع القديمة REAL): جداول ناقصة وأعمدة ناقصة وعمود العملة."""
    with _Tx(conn):
        for stmt in (
            """CREATE TABLE IF NOT EXISTS patients(
                id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, full_name TEXT NOT NULL, gender TEXT, age INTEGER,
                residence TEXT, phone TEXT, job TEXT, diseases TEXT, notes TEXT, blood TEXT, status TEXT, folder TEXT,
                photo_before TEXT, photo_after TEXT, photo_lab TEXT, created_at TEXT, updated_at TEXT)""",
            ATTACHMENTS_DDL,
            """CREATE TABLE IF NOT EXISTS events(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                kind TEXT NOT NULL, date TEXT NOT NULL, done INTEGER DEFAULT 0, done_at TEXT, notes TEXT, created_at TEXT)""",
            """CREATE TABLE IF NOT EXISTS event_items(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                name TEXT NOT NULL, price REAL NOT NULL DEFAULT 0)""",
            """CREATE TABLE IF NOT EXISTS payments(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
                amount REAL NOT NULL, paid_at TEXT, note TEXT)"""):
            conn.execute(stmt)
        have_p = set(_cols(conn, "patients"))
        for col, d in (("code", "TEXT"), ("gender", "TEXT"), ("age", "INTEGER"), ("residence", "TEXT"), ("phone", "TEXT"),
                       ("job", "TEXT"), ("diseases", "TEXT"), ("notes", "TEXT"), ("blood", "TEXT"), ("status", "TEXT"),
                       ("folder", "TEXT"), ("photo_before", "TEXT"), ("photo_after", "TEXT"), ("photo_lab", "TEXT"),
                       ("created_at", "TEXT"), ("updated_at", "TEXT")):
            if col not in have_p:
                conn.execute(f"ALTER TABLE patients ADD COLUMN {col} {d}")
        have = set(_cols(conn, "events"))
        for col, d in (("done", "INTEGER DEFAULT 0"), ("done_at", "TEXT"), ("notes", "TEXT"), ("created_at", "TEXT"),
                       ("time", "TEXT"), ("photo_before", "TEXT"), ("photo_after", "TEXT"), ("in_report", "INTEGER DEFAULT 0"),
                       ("amount_due", "REAL DEFAULT 0"), ("cancelled", "INTEGER DEFAULT 0"), ("cancelled_at", "TEXT"),
                       ("cancel_reason", "TEXT")):
            if col not in have:
                conn.execute(f"ALTER TABLE events ADD COLUMN {col} {d}")
        for tbl in ("event_items", "payments"):                      # عمود العملة: البيانات السابقة بالعملة المضبوطة وقتها
            if "cur" not in _cols(conn, tbl):
                conn.execute(f"ALTER TABLE {tbl} ADD COLUMN cur TEXT NOT NULL DEFAULT 'SYP'")
                if legacy_currency == "USD":
                    conn.execute(f"UPDATE {tbl} SET cur='USD'")
        conn.execute("PRAGMA user_version=1")


def _m2_clinical(conn, info, _):
    with _Tx(conn):
        have = set(_cols(conn, "patients"))
        for col in ("allergies", "medications", "diagnosis"):
            if col not in have:
                conn.execute(f"ALTER TABLE patients ADD COLUMN {col} TEXT")
        have = set(_cols(conn, "events"))
        for col, d in (("duration_min", "INTEGER"), ("no_show", "INTEGER DEFAULT 0")):
            if col not in have:
                conn.execute(f"ALTER TABLE events ADD COLUMN {col} {d}")
        conn.execute("PRAGMA user_version=2")


def _count(conn, sql, args=()):
    return conn.execute(sql, args).fetchone()[0]


def _m3_money_and_checks(conn, info, _):
    """إعادة بناء الجداول بمخطط v3: مبالغ صحيحة (×100) وقيود CHECK، مع إصلاح ما يخالفها وفحص المجاميع."""
    fixed = info.setdefault("fixed", {})
    with _Tx(conn, fk_off=True):
        seq = {}
        if "sqlite_sequence" in tables(conn) or _count(conn, "SELECT COUNT(*) FROM sqlite_master WHERE name='sqlite_sequence'"):
            seq = {n: s for n, s in conn.execute("SELECT name, seq FROM sqlite_sequence")}

        def note(key, sql, args=()):
            n = _count(conn, sql, args)
            if n:
                fixed[key] = fixed.get(key, 0) + n

        # ── ما سيُصلح (يُحصى قبل النسخ) ──
        note("patients.age", "SELECT COUNT(*) FROM patients WHERE age IS NOT NULL AND NOT (typeof(age)='integer' AND age BETWEEN 0 AND 130)"
             " AND NOT (typeof(age)='real' AND age BETWEEN 0 AND 130)")
        note("patients.name", "SELECT COUNT(*) FROM patients WHERE length(trim(COALESCE(full_name,'')))=0")
        note("events.kind", "SELECT COUNT(*) FROM events WHERE kind NOT IN ('surgery','visit')")
        note("events.date", "SELECT COUNT(*) FROM events WHERE COALESCE(date(date),'') <> date")
        note("events.time", "SELECT COUNT(*) FROM events WHERE time IS NOT NULL AND COALESCE(strftime('%H:%M', time),'') <> time "
             "AND COALESCE(strftime('%H:%M', '0'||time),'') <> '0'||time")
        note("events.state", "SELECT COUNT(*) FROM events WHERE (COALESCE(done,0)<>0 AND COALESCE(cancelled,0)<>0) "
             "OR (COALESCE(no_show,0)<>0 AND COALESCE(cancelled,0)=0)")
        note("events.duration", "SELECT COUNT(*) FROM events WHERE duration_min IS NOT NULL AND NOT (duration_min BETWEEN 5 AND 720)")
        note("events.orphan", "SELECT COUNT(*) FROM events WHERE patient_id NOT IN (SELECT id FROM patients)")
        note("items.price", "SELECT COUNT(*) FROM event_items WHERE price IS NULL OR price < 0")
        note("items.cur", "SELECT COUNT(*) FROM event_items WHERE cur NOT IN ('SYP','USD')")
        note("items.orphan", "SELECT COUNT(*) FROM event_items WHERE event_id NOT IN (SELECT id FROM events)")
        note("payments.nonpositive", "SELECT COUNT(*) FROM payments WHERE amount IS NULL OR CAST(ROUND(amount*100) AS INTEGER) <= 0")
        note("payments.cur", "SELECT COUNT(*) FROM payments WHERE cur NOT IN ('SYP','USD')")
        note("payments.orphan", "SELECT COUNT(*) FROM payments WHERE event_id NOT IN (SELECT id FROM events)")

        # ── مجاميع قبل التحويل (للتحقق) ──
        old_items = {r[0]: r[1] for r in conn.execute(
            "SELECT CASE WHEN cur IN ('SYP','USD') THEN cur ELSE 'SYP' END, SUM(MAX(COALESCE(price,0),0)) FROM event_items "
            "WHERE event_id IN (SELECT id FROM events WHERE patient_id IN (SELECT id FROM patients)) GROUP BY 1")}
        old_pays = {r[0]: (r[1], r[2]) for r in conn.execute(
            "SELECT CASE WHEN cur IN ('SYP','USD') THEN cur ELSE 'SYP' END, SUM(amount), COUNT(*) FROM payments "
            "WHERE CAST(ROUND(COALESCE(amount,0)*100) AS INTEGER) > 0 "
            "AND event_id IN (SELECT id FROM events WHERE patient_id IN (SELECT id FROM patients)) GROUP BY 1")}

        for stmt in ddl("_new").strip().split(";\n"):
            if stmt.strip():
                conn.execute(stmt)
        conn.execute("""INSERT INTO patients_new(id,code,full_name,gender,age,residence,phone,job,diseases,notes,blood,status,
                folder,photo_before,photo_after,photo_lab,created_at,updated_at,allergies,medications,diagnosis)
            SELECT id, code,
                   CASE WHEN length(trim(COALESCE(full_name,'')))=0 THEN '(بلا اسم)' ELSE full_name END,
                   gender,
                   CASE WHEN typeof(age) IN ('integer','real') AND age BETWEEN 0 AND 130 THEN CAST(age AS INTEGER) ELSE NULL END,
                   residence, phone, job, diseases, notes, blood, status, folder, photo_before, photo_after, photo_lab,
                   created_at, updated_at, allergies, medications, diagnosis
            FROM patients""")
        conn.execute("""INSERT INTO events_new(id,patient_id,kind,date,time,done,done_at,notes,created_at,photo_before,photo_after,
                in_report,amount_due,cancelled,cancelled_at,cancel_reason,duration_min,no_show)
            SELECT id, patient_id,
                   CASE WHEN kind IN ('surgery','visit') THEN kind ELSE 'visit' END,
                   CASE WHEN date(date) = date THEN date
                        WHEN date(substr(COALESCE(created_at,''),1,10)) = substr(COALESCE(created_at,''),1,10) THEN substr(created_at,1,10)
                        ELSE '1970-01-01' END,
                   CASE WHEN strftime('%H:%M', time) = time THEN time
                        WHEN strftime('%H:%M', '0'||time) = '0'||time THEN '0'||time ELSE NULL END,
                   CASE WHEN COALESCE(done,0)<>0 THEN 1 ELSE 0 END,
                   done_at, notes, created_at, photo_before, photo_after,
                   CASE WHEN COALESCE(in_report,0)<>0 THEN 1 ELSE 0 END,
                   COALESCE(amount_due,0),
                   CASE WHEN COALESCE(done,0)<>0 THEN 0 WHEN COALESCE(cancelled,0)<>0 THEN 1 ELSE 0 END,
                   cancelled_at, cancel_reason,
                   CASE WHEN duration_min BETWEEN 5 AND 720 THEN CAST(duration_min AS INTEGER) ELSE NULL END,
                   CASE WHEN COALESCE(done,0)=0 AND COALESCE(cancelled,0)<>0 AND COALESCE(no_show,0)<>0 THEN 1 ELSE 0 END
            FROM events WHERE patient_id IN (SELECT id FROM patients)""")
        conn.execute("""INSERT INTO event_items_new(id,event_id,name,price_minor,cur)
            SELECT id, event_id, COALESCE(NULLIF(trim(name),''),'إجراء'),
                   CAST(ROUND(MAX(COALESCE(price,0),0)*100) AS INTEGER),
                   CASE WHEN cur IN ('SYP','USD') THEN cur ELSE 'SYP' END
            FROM event_items WHERE event_id IN (SELECT id FROM events_new)""")
        conn.execute("""INSERT INTO payments_new(id,event_id,amount_minor,paid_at,note,cur)
            SELECT id, event_id, CAST(ROUND(amount*100) AS INTEGER), paid_at, note,
                   CASE WHEN cur IN ('SYP','USD') THEN cur ELSE 'SYP' END
            FROM payments WHERE CAST(ROUND(COALESCE(amount,0)*100) AS INTEGER) > 0
              AND event_id IN (SELECT id FROM events_new)""")

        # ── تحقق: المجاميع لم تتغير (بفارق تقريب أقل من نصف وحدة لكل صف) ──
        for cur_, tot in old_items.items():
            n = _count(conn, "SELECT COUNT(*) FROM event_items_new WHERE cur=?", (cur_,))
            new = _count(conn, "SELECT COALESCE(SUM(price_minor),0) FROM event_items_new WHERE cur=?", (cur_,))
            if abs(tot * 100 - new) > 0.5 * n + 1e-6:
                raise sqlite3.IntegrityError(f"تحويل التكاليف غيّر المجموع ({cur_}): {tot} → {new / 100}")
        for cur_, (tot, n) in old_pays.items():
            new = _count(conn, "SELECT COALESCE(SUM(amount_minor),0) FROM payments_new WHERE cur=?", (cur_,))
            if abs(tot * 100 - new) > 0.5 * n + 1e-6:
                raise sqlite3.IntegrityError(f"تحويل الدفعات غيّر المجموع ({cur_}): {tot} → {new / 100}")

        for t in ("payments", "event_items", "events", "patients"):
            conn.execute(f"DROP TABLE {t}")
        for t in ("patients", "events", "event_items", "payments"):
            conn.execute(f"ALTER TABLE {t}_new RENAME TO {t}")
        conn.execute(ATTACHMENTS_DDL)
        for stmt in INDEXES.strip().split(";\n"):
            if stmt.strip():
                conn.execute(stmt)
        for name, s in seq.items():                                # لا نُعيد استعمال أرقام صفوف محذوفة (أكواد المرضى)
            if name in ("patients", "events", "event_items", "payments", "attachments"):
                if conn.execute("UPDATE sqlite_sequence SET seq=MAX(seq, ?) WHERE name=?", (s, name)).rowcount == 0:
                    conn.execute("INSERT INTO sqlite_sequence(name, seq) VALUES(?, ?)", (name, s))
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise sqlite3.IntegrityError(f"مفاتيح أجنبية مكسورة بعد الترقية: {len(bad)}")
        ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if ic != "ok":
            raise sqlite3.IntegrityError(f"فشل فحص سلامة القاعدة بعد الترقية: {ic}")
        conn.execute("PRAGMA user_version=3")


_STEPS = ((1, _m1_legacy), (2, _m2_clinical), (3, _m3_money_and_checks))


def migrate(conn, legacy_currency: str = "SYP") -> dict:
    """يضمن أن المخطط بآخر إصدار. يعيد {'from': v0, 'to': LATEST, 'fixed': {...}, 'created': bool}."""
    uv = user_version(conn)
    info = {"from": uv, "to": LATEST, "fixed": {}, "created": False}
    if uv > LATEST:
        raise SchemaTooNew(uv, LATEST)
    if uv == LATEST:
        return info
    if not tables(conn):                                       # قاعدة جديدة
        with _Tx(conn):
            for stmt in ddl().strip().split(";\n"):
                if stmt.strip():
                    conn.execute(stmt)
            conn.execute(ATTACHMENTS_DDL)
            for stmt in INDEXES.strip().split(";\n"):
                if stmt.strip():
                    conn.execute(stmt)
            conn.execute(f"PRAGMA user_version={LATEST}")
        info["created"] = True
        return info
    for v, fn in _STEPS:
        if uv < v:
            fn(conn, info, legacy_currency)
            uv = v
    return info
