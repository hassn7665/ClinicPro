# -*- coding: utf-8 -*-
"""
schema.py — مخطط قاعدة البيانات وترقياتها عبر ‎PRAGMA user_version‎ (بلا أي اعتماد على بقية التطبيق).

القاعدة:
  • كل تغيير في المخطط = خطوة جديدة في MIGRATIONS (رقمها = رقم الإصدار الذي تُنتجه) + رفع LATEST.
  • الخطوة تُنفَّذ داخل معاملة واحدة: إمّا تكتمل وتُرفع user_version معها، أو تُلغى كلها.
  • قاعدة أحدث من التطبيق (user_version > LATEST) تُرفض صراحةً بدل أن تُفسَد بصمت.

الإصدارات:
  0 → 1  «تطبيع قديم»: ما كان يفعله init_db سابقاً (إنشاء الجداول وإضافة الأعمدة الناقصة بفحص الأعمدة).
  1 → 2  «مخطط صارم»: إعادة بناء الجداول بقيود CHECK، وتحويل المبالغ من REAL إلى أعداد صحيحة بأصغر وحدة
          (MINOR = 100 لكل من ل.س و$؛ أي 1500.50 ← 150050).
  2 → 3  «حالة موعد واحدة»: الأعمدة done/cancelled/no_show ← عمود status ('pending'|'done'|'cancelled'|'no_show')
          فتستحيل التركيبات المتناقضة بالتصميم، مع قيود تربط الحالة بتاريخ الإنجاز/الإلغاء.
  3 → 4  «تاريخ الميلاد»: العمود age (يتقادم) ← birth_date ('YYYY-MM-DD' أو 'YYYY' لعمر قديم لا نعرف يوم ميلاده).

المبالغ: كل مبلغ في القاعدة وفي core.py عدد صحيح بأصغر وحدة. التحويل من/إلى نص يتم في core.money/parse_money فقط.
"""
import re
import sqlite3

LATEST = 4
MINOR = 100                       # أصغر وحدة: 1 ل.س أو 1 $ = 100 وحدة (قرش/سنت)
CURRENCIES = ("SYP", "USD")
KINDS = ("surgery", "visit")
STATUSES = ("جديد", "قديم")
EVENT_STATUSES = ("pending", "done", "cancelled", "no_show")
FALLBACK_DATE = "1970-01-01"


class SchemaError(Exception):
    """قاعدة غير قابلة للاستخدام (أحدث من التطبيق، أو فشل التحقق بعد الترقية)."""


# ───────────────────────── مساعدات ─────────────────────────
def get_version(conn) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def _set_version(conn, v: int):
    conn.execute(f"PRAGMA user_version={int(v)}")            # الأمر لا يقبل معاملات؛ v عدد صحيح مُتحقَّق منه


def _cols(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


def _col_type(conn, table, col):
    for r in conn.execute(f"PRAGMA table_info({table})"):
        if r[1] == col:
            return (r[2] or "").upper()
    return None


def _has_table(conn, table) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def to_minor(v) -> int:
    """REAL (وحدات رئيسية) ← عدد صحيح (أصغر وحدة) بتقريب نصف-للأعلى بعيداً عن أخطاء الفاصلة العائمة."""
    if v is None:
        return 0
    from decimal import Decimal, ROUND_HALF_UP
    try:
        d = Decimal(str(v)) * MINOR
    except Exception:
        return 0
    return int(d.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def canon_date(s):
    """YYYY-MM-DD صارم (يقبل 2026-1-5 ويطبّعه) أو None."""
    from datetime import datetime
    try:
        return datetime.strptime(str(s).strip()[:10] if s else "", "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        return None


def canon_time(s):
    """HH:MM صارم (يقبل 9:05 ويطبّعه) أو None."""
    from datetime import datetime
    if s in (None, ""):
        return None
    try:
        return datetime.strptime(str(s).strip()[:5], "%H:%M").strftime("%H:%M")
    except ValueError:
        return None


# ───────────────────────── 0 → 1: تطبيع المخطط القديم ─────────────────────────
def _m1_legacy(conn, legacy_currency="SYP", **_):
    """يُنتج المخطط القديم كاملاً (يعمل على قاعدة جديدة فارغة وعلى كل الإصدارات السابقة). متكرر الأمان."""
    stmts = ["""CREATE TABLE IF NOT EXISTS patients(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT, full_name TEXT NOT NULL, gender TEXT, age INTEGER,
            residence TEXT, phone TEXT, job TEXT, diseases TEXT, notes TEXT,
            blood TEXT, status TEXT, folder TEXT,
            photo_before TEXT, photo_after TEXT, photo_lab TEXT,
            created_at TEXT, updated_at TEXT)""",
             """CREATE TABLE IF NOT EXISTS attachments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
            path TEXT, name TEXT)""",
             """CREATE TABLE IF NOT EXISTS events(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
            kind TEXT NOT NULL, date TEXT NOT NULL,
            done INTEGER DEFAULT 0, done_at TEXT, notes TEXT, created_at TEXT)"""]
    for s in stmts:
        conn.execute(s)
    cols = _cols(conn, "events")
    for col, ddl in (("time", "TEXT"), ("photo_before", "TEXT"), ("photo_after", "TEXT"),
                     ("in_report", "INTEGER DEFAULT 0"), ("amount_due", "REAL DEFAULT 0"),
                     ("cancelled", "INTEGER DEFAULT 0"), ("cancelled_at", "TEXT"), ("cancel_reason", "TEXT"),
                     ("duration_min", "INTEGER"), ("no_show", "INTEGER DEFAULT 0")):
        if col not in cols:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col} {ddl}")
    pcols = _cols(conn, "patients")
    for col in ("allergies", "medications", "diagnosis"):
        if col not in pcols:
            conn.execute(f"ALTER TABLE patients ADD COLUMN {col} TEXT")
    for s in ["""CREATE TABLE IF NOT EXISTS event_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            name TEXT NOT NULL, price REAL NOT NULL DEFAULT 0, cur TEXT NOT NULL DEFAULT 'SYP')""",
              """CREATE TABLE IF NOT EXISTS payments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
            amount REAL NOT NULL, paid_at TEXT, note TEXT, cur TEXT NOT NULL DEFAULT 'SYP')"""]:
        conn.execute(s)
    for tbl in ("event_items", "payments"):                    # عمود العملة: القديم يُعدّ بالعملة التي كانت مضبوطة
        if "cur" not in _cols(conn, tbl):
            conn.execute(f"ALTER TABLE {tbl} ADD COLUMN cur TEXT NOT NULL DEFAULT 'SYP'")
            if legacy_currency == "USD":
                conn.execute(f"UPDATE {tbl} SET cur='USD'")


# ───────────────────────── 1 → 2: مخطط صارم + مبالغ صحيحة ─────────────────────────
_TABLES_V2 = {
    "patients": """CREATE TABLE patients_new(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT,
        full_name TEXT NOT NULL CHECK(length(trim(full_name)) > 0),
        gender TEXT,
        age INTEGER CHECK(age IS NULL OR age BETWEEN 0 AND 150),
        residence TEXT, phone TEXT, job TEXT, diseases TEXT, notes TEXT, blood TEXT,
        status TEXT CHECK(status IS NULL OR status IN ('جديد', 'قديم')),
        folder TEXT, photo_before TEXT, photo_after TEXT, photo_lab TEXT,
        created_at TEXT, updated_at TEXT,
        allergies TEXT, medications TEXT, diagnosis TEXT)""",
    "attachments": """CREATE TABLE attachments_new(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        path TEXT, name TEXT)""",
    "events": """CREATE TABLE events_new(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('surgery', 'visit')),
        date TEXT NOT NULL CHECK(date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
        time TEXT CHECK(time IS NULL OR time GLOB '[0-9][0-9]:[0-9][0-9]'),
        duration_min INTEGER CHECK(duration_min IS NULL OR duration_min BETWEEN 5 AND 720),
        done INTEGER NOT NULL DEFAULT 0 CHECK(done IN (0, 1)),
        done_at TEXT, notes TEXT, created_at TEXT,
        photo_before TEXT, photo_after TEXT,
        in_report INTEGER NOT NULL DEFAULT 0 CHECK(in_report IN (0, 1)),
        amount_due INTEGER NOT NULL DEFAULT 0 CHECK(amount_due >= 0),
        cancelled INTEGER NOT NULL DEFAULT 0 CHECK(cancelled IN (0, 1)),
        cancelled_at TEXT, cancel_reason TEXT,
        no_show INTEGER NOT NULL DEFAULT 0 CHECK(no_show IN (0, 1)),
        CHECK(NOT (done = 1 AND cancelled = 1)),
        CHECK(no_show = 0 OR cancelled = 1))""",
    "event_items": """CREATE TABLE event_items_new(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        price INTEGER NOT NULL DEFAULT 0 CHECK(price >= 0),
        cur TEXT NOT NULL DEFAULT 'SYP' CHECK(cur IN ('SYP', 'USD')))""",
    "payments": """CREATE TABLE payments_new(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
        amount INTEGER NOT NULL CHECK(amount > 0),
        paid_at TEXT, note TEXT,
        cur TEXT NOT NULL DEFAULT 'SYP' CHECK(cur IN ('SYP', 'USD')))""",
}
_ORDER = ("patients", "attachments", "events", "event_items", "payments")          # الآباء قبل الأبناء
_INDEXES = ("CREATE INDEX IF NOT EXISTS ix_pat_code ON patients(code)",
            "CREATE INDEX IF NOT EXISTS ix_att_pat ON attachments(patient_id)",
            "CREATE INDEX IF NOT EXISTS ix_ev_pat ON events(patient_id, date)",
            "CREATE INDEX IF NOT EXISTS ix_ev_date ON events(date)",
            "CREATE INDEX IF NOT EXISTS ix_items_ev ON event_items(event_id)",
            "CREATE INDEX IF NOT EXISTS ix_pay_ev ON payments(event_id)")
_P_COLS = ("id", "code", "full_name", "gender", "age", "residence", "phone", "job", "diseases", "notes", "blood",
           "status", "folder", "photo_before", "photo_after", "photo_lab", "created_at", "updated_at",
           "allergies", "medications", "diagnosis")
_E_COLS = ("id", "patient_id", "kind", "date", "time", "duration_min", "done", "done_at", "notes", "created_at",
           "photo_before", "photo_after", "in_report", "amount_due", "cancelled", "cancelled_at", "cancel_reason",
           "no_show")


def _m2_strict(conn, report=None, **_):
    """يعيد بناء الجداول الخمسة. يُنفَّذ والمفاتيح الأجنبية معطّلة (وصفة SQLite الرسمية)، داخل معاملة المستدعي."""
    bump = (lambda k, n=1: report["sanitized"].__setitem__(k, report["sanitized"].get(k, 0) + n)) \
        if report is not None else (lambda k, n=1: None)
    if _col_type(conn, "payments", "amount") == "INTEGER":      # أُعيد بناؤها سابقاً (مثلاً تحميل من نسخة نصية فقدت user_version)
        return
    seqs = {r[0]: r[1] for r in conn.execute("SELECT name, seq FROM sqlite_sequence")} \
        if _has_table(conn, "sqlite_sequence") else {}
    for t in _ORDER:
        conn.execute(_TABLES_V2[t])

    # ── patients ──
    pids = set()
    rows = conn.execute(f"SELECT {', '.join(_P_COLS)} FROM patients ORDER BY id").fetchall()
    for r in rows:
        r = list(r)
        d = dict(zip(_P_COLS, r))
        if not (d["full_name"] or "").strip():
            d["full_name"] = "(بلا اسم)"
            bump("patients.empty_name")
        if d["age"] is not None:
            try:
                d["age"] = int(d["age"])
            except (TypeError, ValueError):
                d["age"] = None
            if d["age"] is not None and not 0 <= d["age"] <= 150:
                d["age"] = None
                bump("patients.bad_age")
        if d["status"] not in (None,) + STATUSES:
            d["status"] = "جديد"
            bump("patients.bad_status")
        conn.execute(f"INSERT INTO patients_new({', '.join(_P_COLS)}) VALUES({', '.join('?' * len(_P_COLS))})",
                     [d[k] for k in _P_COLS])
        pids.add(d["id"])

    # ── attachments ──
    for r in conn.execute("SELECT id, patient_id, path, name FROM attachments ORDER BY id").fetchall():
        if r[1] not in pids:
            bump("attachments.orphan")
            continue
        conn.execute("INSERT INTO attachments_new(id, patient_id, path, name) VALUES(?,?,?,?)", tuple(r))

    # ── events ──
    eids = set()
    for r in conn.execute(f"SELECT {', '.join(_E_COLS)} FROM events ORDER BY id").fetchall():
        d = dict(zip(_E_COLS, tuple(r)))
        if d["patient_id"] not in pids:
            bump("events.orphan")
            continue
        if d["kind"] not in KINDS:
            d["kind"] = "visit"
            bump("events.bad_kind")
        nd = canon_date(d["date"])
        if nd is None:
            nd = canon_date(d["created_at"]) or FALLBACK_DATE
            bump("events.bad_date")
        d["date"] = nd
        nt = canon_time(d["time"])
        if d["time"] not in (None, "") and nt is None:
            bump("events.bad_time")
        d["time"] = nt
        dm = d["duration_min"]
        if dm is not None:
            try:
                dm = int(dm)
            except (TypeError, ValueError):
                dm = None
            if dm is not None and not 5 <= dm <= 720:
                dm = None
                bump("events.bad_duration")
        d["duration_min"] = dm
        for k in ("done", "in_report", "cancelled", "no_show"):
            d[k] = 1 if d[k] else 0
        if d["done"] and d["cancelled"]:                         # حالتان متناقضتان: المنجز هو الأقوى
            d["cancelled"], d["no_show"] = 0, 0
            bump("events.done_and_cancelled")
        if d["no_show"] and not d["cancelled"]:
            d["no_show"] = 0
            bump("events.no_show_without_cancel")
        d["amount_due"] = max(to_minor(d["amount_due"]), 0)
        conn.execute(f"INSERT INTO events_new({', '.join(_E_COLS)}) VALUES({', '.join('?' * len(_E_COLS))})",
                     [d[k] for k in _E_COLS])
        eids.add(d["id"])

    # ── event_items / payments (REAL → INTEGER) ──
    for r in conn.execute("SELECT id, event_id, name, price, cur FROM event_items ORDER BY id").fetchall():
        id_, ev, name, price, cur = tuple(r)
        if ev not in eids:
            bump("event_items.orphan")
            continue
        if cur not in CURRENCIES:
            cur = "SYP"
            bump("event_items.bad_currency")
        conn.execute("INSERT INTO event_items_new(id, event_id, name, price, cur) VALUES(?,?,?,?,?)",
                     (id_, ev, (name or "").strip() or "إجراء", max(to_minor(price), 0), cur))
    for r in conn.execute("SELECT id, event_id, amount, paid_at, note, cur FROM payments ORDER BY id").fetchall():
        id_, ev, amount, paid_at, note, cur = tuple(r)
        if ev not in eids:
            bump("payments.orphan")
            continue
        amt = to_minor(amount)
        if amt <= 0:
            bump("payments.non_positive")
            continue
        if cur not in CURRENCIES:
            cur = "SYP"
            bump("payments.bad_currency")
        conn.execute("INSERT INTO payments_new(id, event_id, amount, paid_at, note, cur) VALUES(?,?,?,?,?,?)",
                     (id_, ev, amt, paid_at, note, cur))

    # ── استبدال الجداول ──
    for t in reversed(_ORDER):
        conn.execute(f"DROP TABLE {t}")
    for t in _ORDER:
        conn.execute(f"ALTER TABLE {t}_new RENAME TO {t}")
    for t in _ORDER:                                            # لا نُعيد استعمال أرقام محذوفة (أكواد PT-xxxxx ومجلدات المرضى)
        s = seqs.get(t)
        if s is not None:
            if conn.execute("UPDATE sqlite_sequence SET seq=MAX(seq, ?) WHERE name=?", (s, t)).rowcount == 0:
                conn.execute("INSERT INTO sqlite_sequence(name, seq) VALUES(?, ?)", (t, s))
    for s in _INDEXES:
        conn.execute(s)
    bad = conn.execute("PRAGMA foreign_key_check").fetchall()
    if bad:
        raise SchemaError(f"فشل التحقق من المفاتيح الأجنبية بعد الترقية ({len(bad)} مخالفة)")


_EVENTS_V3 = """CREATE TABLE events_new(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
        kind TEXT NOT NULL CHECK(kind IN ('surgery', 'visit')),
        date TEXT NOT NULL CHECK(date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
        time TEXT CHECK(time IS NULL OR time GLOB '[0-9][0-9]:[0-9][0-9]'),
        duration_min INTEGER CHECK(duration_min IS NULL OR duration_min BETWEEN 5 AND 720),
        status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'done', 'cancelled', 'no_show')),
        done_at TEXT, notes TEXT, created_at TEXT,
        photo_before TEXT, photo_after TEXT,
        in_report INTEGER NOT NULL DEFAULT 0 CHECK(in_report IN (0, 1)),
        amount_due INTEGER NOT NULL DEFAULT 0 CHECK(amount_due >= 0),
        cancelled_at TEXT, cancel_reason TEXT,
        CHECK(status <> 'done' OR done_at IS NOT NULL),
        CHECK(status NOT IN ('cancelled', 'no_show') OR cancelled_at IS NOT NULL))"""
_E3_COLS = ("id", "patient_id", "kind", "date", "time", "duration_min", "status", "done_at", "notes", "created_at",
            "photo_before", "photo_after", "in_report", "amount_due", "cancelled_at", "cancel_reason")

_PATIENTS_V4 = """CREATE TABLE patients_new(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT,
        full_name TEXT NOT NULL CHECK(length(trim(full_name)) > 0),
        gender TEXT,
        birth_date TEXT CHECK(birth_date IS NULL
                              OR birth_date GLOB '[0-9][0-9][0-9][0-9]'
                              OR birth_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'),
        residence TEXT, phone TEXT, job TEXT, diseases TEXT, notes TEXT, blood TEXT,
        status TEXT CHECK(status IS NULL OR status IN ('جديد', 'قديم')),
        folder TEXT, photo_before TEXT, photo_after TEXT, photo_lab TEXT,
        created_at TEXT, updated_at TEXT,
        allergies TEXT, medications TEXT, diagnosis TEXT)"""
_P4_COLS = tuple("birth_date" if c == "age" else c for c in _P_COLS)


def _seqs(conn):
    return {r[0]: r[1] for r in conn.execute("SELECT name, seq FROM sqlite_sequence")} \
        if _has_table(conn, "sqlite_sequence") else {}


def _restore_seq(conn, table, seq):
    if seq is not None and conn.execute("UPDATE sqlite_sequence SET seq=MAX(seq, ?) WHERE name=?", (seq, table)).rowcount == 0:
        conn.execute("INSERT INTO sqlite_sequence(name, seq) VALUES(?, ?)", (table, seq))


def _finish_rebuild(conn, table, seq):
    conn.execute(f"DROP TABLE {table}")
    conn.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
    _restore_seq(conn, table, seq)
    for s in _INDEXES:
        conn.execute(s)
    bad = conn.execute("PRAGMA foreign_key_check").fetchall()
    if bad:
        raise SchemaError(f"فشل التحقق من المفاتيح الأجنبية بعد إعادة بناء {table} ({len(bad)} مخالفة)")


def _bumper(report):
    if report is None:
        return lambda k, n=1: None
    return lambda k, n=1: report["sanitized"].__setitem__(k, report["sanitized"].get(k, 0) + n)


def _m3_event_status(conn, report=None, **_):
    """done/cancelled/no_show ← status. تناقضات القديم حُسمت في الخطوة 2 (المنجز أقوى)."""
    if "status" in _cols(conn, "events"):
        return
    bump = _bumper(report)
    seq = _seqs(conn).get("events")
    conn.execute(_EVENTS_V3)
    old = ("id", "patient_id", "kind", "date", "time", "duration_min", "done", "done_at", "notes", "created_at",
           "photo_before", "photo_after", "in_report", "amount_due", "cancelled", "cancelled_at", "cancel_reason", "no_show")
    for r in conn.execute(f"SELECT {', '.join(old)} FROM events ORDER BY id").fetchall():
        d = dict(zip(old, tuple(r)))
        status = "done" if d["done"] else ("no_show" if d["no_show"] else "cancelled" if d["cancelled"] else "pending")
        done_at, cancelled_at = d["done_at"], d["cancelled_at"]
        if status == "done" and not done_at:
            done_at = f"{d['date']}T00:00:00"
            bump("events.done_without_time")
        if status in ("cancelled", "no_show") and not cancelled_at:
            cancelled_at = d["created_at"] or f"{d['date']}T00:00:00"
            bump("events.cancelled_without_time")
        if status == "pending":
            done_at = None if not done_at else done_at
        row = dict(d, status=status, done_at=done_at, cancelled_at=cancelled_at)
        conn.execute(f"INSERT INTO events_new({', '.join(_E3_COLS)}) VALUES({', '.join('?' * len(_E3_COLS))})",
                     [row[k] for k in _E3_COLS])
    _finish_rebuild(conn, "events", seq)


def _m4_birth_date(conn, report=None, **_):
    """age ← birth_date. العمر القديم يصير سنة ميلاد تقريبية (سنة الإنشاء − العمر) بصيغة 'YYYY'."""
    if "birth_date" in _cols(conn, "patients"):
        return
    from datetime import date as _d
    seq = _seqs(conn).get("patients")
    conn.execute(_PATIENTS_V4)
    for r in conn.execute(f"SELECT {', '.join(_P_COLS)} FROM patients ORDER BY id").fetchall():
        d = dict(zip(_P_COLS, tuple(r)))
        age = d.pop("age")
        year = (str(d["created_at"] or "")[:4])
        year = int(year) if year.isdigit() and int(year) > 1900 else _d.today().year
        d["birth_date"] = str(year - int(age)) if age is not None and 0 <= int(age) <= 150 else None
        conn.execute(f"INSERT INTO patients_new({', '.join(_P4_COLS)}) VALUES({', '.join('?' * len(_P4_COLS))})",
                     [d[k] for k in _P4_COLS])
    _finish_rebuild(conn, "patients", seq)


def birth_year(birth_date):
    s = str(birth_date or "")
    return int(s[:4]) if len(s) >= 4 and s[:4].isdigit() else None


def age_on(birth_date, today=None):
    """العمر بالسنوات من birth_date ('YYYY-MM-DD' بالضبط، أو 'YYYY' تقريبي). None إن لم يُعرف."""
    from datetime import date as _d
    today = today or _d.today()
    y = birth_year(birth_date)
    if y is None:
        return None
    s = str(birth_date)
    if len(s) == 10:
        try:
            m, d = int(s[5:7]), int(s[8:10])
        except ValueError:
            return today.year - y
        return today.year - y - ((today.month, today.day) < (m, d))
    return today.year - y


MIGRATIONS = {1: _m1_legacy, 2: _m2_strict, 3: _m3_event_status, 4: _m4_birth_date}

# ───────────────────────── المنفّذ ─────────────────────────
def migrate(conn, legacy_currency: str = "SYP") -> dict:
    """يرقّي القاعدة إلى LATEST. يعيد {'from','to','applied','sanitized'}. كل خطوة ذرّية.
    يترك المفاتيح الأجنبية مفعّلة عند الانتهاء (سواء نجحت الترقية أم فشلت)."""
    old_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    v0 = get_version(conn)
    report = {"from": v0, "to": v0, "applied": [], "sanitized": {}}
    try:
        if v0 > LATEST:
            raise SchemaError(f"قاعدة البيانات (إصدار {v0}) أحدث من هذا التطبيق (يدعم حتى {LATEST}). حدّث التطبيق.")
        if v0 == LATEST:
            conn.execute("PRAGMA foreign_keys=ON")
            for s in _INDEXES:                                  # فهارس مفقودة لا تضرّ؛ تُنشأ إن غابت
                conn.execute(s)
            return report
        conn.commit()
        conn.execute("PRAGMA foreign_keys=OFF")                 # لا يعمل داخل معاملة
        for v in range(v0 + 1, LATEST + 1):
            conn.execute("BEGIN")
            try:
                MIGRATIONS[v](conn, legacy_currency=legacy_currency, report=report)
                _set_version(conn, v)
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            report["applied"].append(v)
            report["to"] = v
        return report
    finally:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = old_factory


# ───────────────────────── التحقق من قاعدة قادمة من خارج التطبيق ─────────────────────────
# النسخ الاحتياطية وملفات القاعدة تُعدّ مدخلات غير موثوقة: قد يصنع مهاجم نسخة بكلمة مرور يعرفها ويقنع المستخدم باستعادتها.
# لذلك: (1) لا نُنفّذ إلا عبارات من قائمة بيضاء، (2) نرفض أي كائن غير الجداول والفهارس المعروفة (triggers/views/virtual).
APP_TABLES = frozenset(_ORDER)
_SAFE_STMT = re.compile(
    r"""^\s*(?:
        BEGIN(?:\s+TRANSACTION)? |
        COMMIT |
        PRAGMA\s+user_version\s*=\s*\d+ |
        DELETE\s+FROM\s+["`\[]?sqlite_sequence["`\]]? |
        INSERT\s+INTO\s+["`\[]?(?:sqlite_sequence|patients|attachments|events|event_items|payments)["`\]]?[\s(] |
        CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?\S+\s+ON\s+["`\[]?(?:patients|attachments|events|event_items|payments)["`\]]?\s*\( |
        CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`\[]?(?:patients|attachments|events|event_items|payments)["`\]]?\s*\(
    )""", re.I | re.X)


def run_dump(conn, text: str):
    """ينفّذ نص iterdump عبارةً عبارة ويرفض أي عبارة خارج القائمة البيضاء (بدل executescript على نص غير موثوق)."""
    buf = ""
    for line in text.split("\n"):
        buf += line + "\n"
        if sqlite3.complete_statement(buf):
            if not _SAFE_STMT.match(buf):
                raise SchemaError("القاعدة تحوي عبارة غير مسموحة؛ رُفضت لأسباب أمنية.")
            conn.execute(buf)                                   # execute (لا executescript) يرفض أكثر من عبارة واحدة
            buf = ""
    if buf.strip():
        raise SchemaError("نص القاعدة غير مكتمل.")


def validate_structure(conn):
    """يرفع SchemaError إن احتوت القاعدة على شيء غير جداولنا وفهارسنا (trigger/view/virtual table/جدول غريب)،
    أو فشل integrity_check."""
    for typ, name, tbl, sql in conn.execute("SELECT type, name, tbl_name, sql FROM sqlite_master"):
        if typ == "table":
            if name not in APP_TABLES and name != "sqlite_sequence" and not name.startswith("sqlite_stat"):
                raise SchemaError(f"جدول غير معروف داخل القاعدة: {name}")
            if sql and re.match(r"\s*CREATE\s+VIRTUAL", sql, re.I):
                raise SchemaError("جداول افتراضية غير مسموحة.")
        elif typ == "index":
            if tbl not in APP_TABLES:
                raise SchemaError(f"فهرس على جدول غير معروف: {tbl}")
        else:                                                   # trigger / view
            raise SchemaError(f"كائن غير مسموح داخل القاعدة ({typ}).")
    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise SchemaError("قاعدة البيانات تالفة.")


def harden(conn):
    """يضيّق ما يستطيعه SQL غير الموثوق: لا دوال مخطط، ووضع دفاعي (SQLite ≥ 3.26 / بايثون ≥ 3.12 حيث يتوفر)."""
    conn.execute("PRAGMA trusted_schema=OFF")
    cfg, flag = getattr(conn, "setconfig", None), getattr(sqlite3, "SQLITE_DBCONFIG_DEFENSIVE", None)
    if cfg and flag is not None:
        cfg(flag, True)
