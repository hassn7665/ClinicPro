# -*- coding: utf-8 -*-
"""
core.py — المنطق الخلفي لتطبيق Clinic Pro (قاعدة البيانات، الترخيص، النسخ الاحتياطي،
الإحصائيات، تقرير الطباعة، خادم المشاركة المحلي). لا يعتمد على Flet.
"""
import base64
import calendar
import functools
import hashlib
import hmac
import html
import http.server
import json
import os
import re
import secrets
import shutil
import sqlite3
import struct
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import threading
import time
import urllib.parse
import zipfile
from contextlib import closing
from datetime import datetime, timedelta

import applog as LOG
import crypto_core as K
import images as IMG
import migrations as MG
import license_core as LC
import vault as VT
import theme as TH

APP_NAME = "Clinic Pro"
APP_VERSION = "2.7.0"

BASE = os.getenv("FLET_APP_STORAGE_DATA") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "shifa_data")
DB_PATH = os.path.join(BASE, "shifa.db")        # قاعدة قديمة غير مشفّرة (تُرحَّل عند إنشاء الحساب)
DB_ENC = os.path.join(BASE, "db.enc")           # القاعدة المشفّرة
PAT_DIR = os.path.join(BASE, "patients")
BK_DIR = os.path.join(BASE, "backups")
SHARE_DIR = os.path.join(BASE, "share")
LIC_PATH = os.path.join(BASE, "license.json")
SET_PATH = os.path.join(BASE, "settings.json")
JOURNAL = os.path.join(BASE, "restore.journal")   # يوثّق استبدال البيانات أثناء الاستعادة (للتعافي من انقطاع مفاجئ)
for _d in (BASE, PAT_DIR, BK_DIR):
    os.makedirs(_d, exist_ok=True)
LOG.init(os.path.join(BASE, "logs"))
shutil.rmtree(os.path.join(BASE, "share"), ignore_errors=True)      # بقايا ملفات مؤقتة من جلسة سابقة

BACKUP_EVERY_DAYS = 7            # نسخة تلقائية أسبوعية (تُفحص عند كل دخول)
KEEP_BACKUPS = 8                 # عدد النسخ المحفوظة داخل الجهاز؛ الأقدم تُحذف تلقائياً
EXPORT_REMIND_DAYS = 14          # تذكير بتصدير نسخة خارج الجهاز إن مرّت هذه المدة
KIND_AR = {"surgery": "عملية", "visit": "مراجعة"}
DEFAULT_TIME = "09:00"
DEFAULT_DURATION = {"visit": 30, "surgery": 120}        # دقائق، تُستعمل عند عدم تحديد مدة
DURATIONS = (15, 30, 45, 60, 90, 120, 180)             # خيارات الواجهة


# ───────────────────────── أدوات عامة ─────────────────────────
def safe(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', "", (s or "").strip())
    return re.sub(r"\s+", "_", s)[:60] or "patient"


def ap(rel: str) -> str:
    """مسار مطلق من مسار نسبي مخزّن في القاعدة (النسبي = قابل للنقل بين الأجهزة)."""
    return os.path.join(BASE, *rel.split("/"))


def norm(s: str) -> str:
    s = re.sub(r"[\u064B-\u0652\u0640]", "", s or "")
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        s = s.replace(a, b)
    return s.lower().strip()


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


_jlock = threading.Lock()


def jload(path, default):
    """يقرأ JSON؛ إن كان الملف تالفاً يقرأ آخر نسخة سليمة (.bak) بدل الرجوع للقيمة الافتراضية فوراً."""
    for p in (path, path + ".bak"):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            continue
    return default


def jsave(path, data):
    """كتابة ذرّية (ملف مؤقت ← fsync ← استبدال) مع الاحتفاظ بآخر نسخة سليمة في .bak.
    انقطاع الكهرباء أثناء الكتابة لا يترك ملفاً مقطوعاً أبداً."""
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    with _jlock:
        try:
            with open(path, "rb") as f:
                old = f.read()
            json.loads(old.decode("utf-8"))              # لا نحفظ نسخة تالفة فوق نسخة سليمة
            _atomic_write(path + ".bak", old)
        except (OSError, ValueError):
            pass
        _atomic_write(path, payload)


def add_months(d: datetime, n: int) -> datetime:
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return d.replace(year=y, month=m, day=min(d.day, calendar.monthrange(y, m)[1]))


# ───────────────────────── الحساب والتشفير ─────────────────────────
VAULT = VT.Vault(BASE)
VaultError = VT.VaultError


class NotUnlocked(Exception):
    """محاولة الوصول للبيانات قبل تسجيل الدخول."""


def _wipe_file(path):
    """حذف ملف مع محاولة طمس محتواه أولاً (best-effort)."""
    try:
        n = os.path.getsize(path)
        with open(path, "r+b") as f:
            f.write(b"\x00" * n)
            f.flush()
            os.fsync(f.fileno())
    except OSError:
        pass
    try:
        os.remove(path)
    except OSError:
        pass


def _atomic_write(path, data: bytes):
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


# ───────────────────────── قاعدة البيانات (في الذاكرة + ملف مشفّر) ─────────────────────────
# القاعدة لا توجد على القرص إلا مشفّرة (db.enc). أثناء الاستخدام تعيش في الذاكرة فقط،
# وتُحفَظ مشفّرة بعد كل عملية كتابة، فلا يبقى أي ملف عادي إن أُغلق التطبيق فجأة.
_lock = threading.RLock()
_mem = {"conn": None, "gen": 0, "aad_legacy": True, "accept_rollback": False}


def _new_conn(blob: bytes | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    if blob:
        kind, body = blob[:1], blob[1:]
        if kind == b"\x01":
            if hasattr(conn, "deserialize"):
                conn.deserialize(body)
            else:                                   # بايثون أقدم: عبر ملف مؤقت يُطمَس فوراً
                tmp = os.path.join(BASE, "_tmp_load.db")
                with open(tmp, "wb") as f:
                    f.write(body)
                try:
                    with closing(sqlite3.connect(tmp)) as src:
                        src.backup(conn)
                finally:
                    _wipe_file(tmp)
        elif kind == b"\x02":
            conn.executescript(body.decode("utf-8"))
        else:
            raise ValueError("صيغة قاعدة بيانات غير معروفة")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _serialize(conn) -> bytes:
    if hasattr(conn, "serialize"):
        return b"\x01" + conn.serialize()
    return b"\x02" + "\n".join(conn.iterdump()).encode("utf-8")


DB_MAGIC = b"SHD1"


class RollbackError(VaultError):
    """db.enc أقدم من آخر حفظ مسجّل: احتمال استبدال القاعدة بنسخة قديمة (أو استرجاع جزئي لملفات التطبيق)."""

    def __init__(self, got, expected):
        super().__init__("قاعدة البيانات أقدم من آخر حفظ مسجّل على هذا الجهاز (احتمال استبدالها بنسخة قديمة).")
        self.got, self.expected = got, expected


def _db_encode(plain: bytes, gen: int) -> bytes:
    """SHD1 ‖ gen(8) ‖ sealed(aad="db|"+gen): الجيل ظاهر لكنه مربوط بالمصادقة فلا يمكن تعديله دون كشف."""
    g = struct.pack(">Q", gen)
    return DB_MAGIC + g + K.seal(VAULT.dek, plain, aad=b"db|" + g)


def _db_decode(blob: bytes):
    """(الجيل, القاعدة). يقرأ الصيغة القديمة (SHF1, aad=db) كجيل 0."""
    if blob[:4] == DB_MAGIC:
        g = blob[4:12]
        return struct.unpack(">Q", g)[0], K.open_sealed(VAULT.dek, blob[12:], aad=b"db|" + g)
    return 0, K.decrypt_blob(VAULT.dek, blob, aad=b"db")


def _persist():
    conn = _mem["conn"]
    if conn is None or not VAULT.unlocked:
        return
    gen = max(_mem["gen"], VAULT.dbgen) + 1
    _atomic_write(DB_ENC, _db_encode(_serialize(conn), gen))
    _mem["gen"] = gen
    try:
        VAULT.set_dbgen(gen)                 # بعد نجاح كتابة القاعدة: الأحدث دائماً ≥ المسجَّل
    except OSError as ex:
        LOG.log_exc("dbgen_save", ex)


def _plain_user_version(plain: bytes) -> int:
    """user_version من الترويسة (الإزاحة 60) لبيانات _serialize: بايت النوع ثم ملف SQLite (النوع 1). النص (2) = قديم جداً → 0."""
    return struct.unpack(">I", plain[61:65])[0] if plain[:1] == b"\x01" and len(plain) >= 65 else 0


def open_db():
    """يفتح القاعدة المشفّرة بعد تسجيل الدخول (أو يهيّئ قاعدة جديدة، أو يرحّل قاعدة قديمة)."""
    if not VAULT.unlocked:
        raise NotUnlocked("سجّل الدخول أولاً")
    with _lock:
        if _mem["conn"] is not None:
            return
        if os.path.exists(DB_ENC):
            with open(DB_ENC, "rb") as f:
                gen, plain = _db_decode(f.read())
            if gen < VAULT.dbgen:
                if not _mem["accept_rollback"]:
                    raise RollbackError(gen, VAULT.dbgen)
                LOG.log("rollback_accepted", got=gen, expected=VAULT.dbgen)
                VAULT.set_dbgen(gen)         # قرار المستخدم الصريح: نعتمد القاعدة الحالية أساساً جديداً
            _mem["gen"] = gen
            uv = _plain_user_version(plain)
            if uv < MG.LATEST:                                      # سنرقّي المخطط: نبقي نسخة من الملف قبل الكتابة فوقه
                try:
                    shutil.copyfile(DB_ENC, f"{DB_ENC}.pre_v{uv}")
                except OSError as ex:
                    LOG.log_exc("pre_migration_copy", ex)
            _mem["conn"] = _new_conn(plain)
        else:
            _mem["conn"] = _new_conn()
            if os.path.exists(DB_PATH):             # ترحيل قاعدة الإصدارات السابقة
                with closing(sqlite3.connect(DB_PATH)) as src:
                    src.backup(_mem["conn"])
                _mem["conn"].row_factory = sqlite3.Row
                _mem["conn"].execute("PRAGMA foreign_keys=ON")
        init_db()
        _persist()
        _migrate_file_aad()


def close_db():
    with _lock:
        if _mem["conn"] is not None:
            try:
                _persist()
                _mem["conn"].close()
            except Exception:
                pass
        _mem["conn"] = None


class _Handle:
    """واجهة شبيهة باتصال sqlite تحمل القفل طوال استخدامها (تُستعمل مع closing(...))."""

    def __init__(self):
        _lock.acquire()
        self._held = True
        self.c = _mem["conn"]
        if self.c is None:
            self.close()
            raise NotUnlocked("البيانات مقفلة. سجّل الدخول.")

    def execute(self, *a):
        return self.c.execute(*a)

    def executemany(self, *a):
        return self.c.executemany(*a)

    def executescript(self, *a):
        return self.c.executescript(*a)

    def commit(self):
        self.c.commit()
        _persist()

    def commit_mem(self):
        """يثبّت المعاملة في الذاكرة فقط؛ على المستدعي أن يستدعي _persist() بنفسه (حفظ واحد لعدة عمليات)."""
        self.c.commit()

    def rollback(self):
        self.c.rollback()

    def close(self):
        if self._held:
            self._held = False
            _lock.release()

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if et is None:
            self.commit()
        else:
            self.rollback()
        return False


def db():
    return _Handle()


def q(sql, args=(), one=False):
    with closing(db()) as c:
        rows = c.execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def x(sql, args=()):
    with closing(db()) as c:
        cur = c.execute(sql, args)
        c.commit()
        return cur.lastrowid


def init_db():
    """يضمن مخطط القاعدة المفتوحة بآخر إصدار عبر migrations.py (PRAGMA user_version). يُستدعى بعد كل فتح أو استعادة.
    يرفع migrations.SchemaTooNew إن كانت القاعدة من إصدار أحدث من التطبيق."""
    legacy = "USD" if str(jload(SET_PATH, {}).get("currency") or "").strip().upper() in ("$", "USD", "دولار") else "SYP"
    with _lock:
        info = MG.migrate(_mem["conn"], legacy)
    if info["from"] != info["to"]:
        LOG.log("schema_migrated", frm=info["from"], to=info["to"], created=info["created"],
                **{k.replace(".", "_"): v for k, v in info["fixed"].items()})


# ───────────────────────── واجهة قراءة للشاشات (الواجهة لا تكتب SQL) ─────────────────────────
def patient_get(pid):
    """صف مريض أو None."""
    return q("SELECT * FROM patients WHERE id=?", (pid,), one=True)


def patient_events(pid):
    """مواعيد المريض مرتبة بالتاريخ ثم الوقت (كلها: المعلّقة والمنجزة والملغاة)."""
    return q("SELECT * FROM events WHERE patient_id=? ORDER BY date,time", (pid,))


def patient_attachments(pid):
    return q("SELECT * FROM attachments WHERE patient_id=?", (pid,))


def set_event_in_report(event_id, flag):
    """إدراج صور الموعد (قبل/بعد) في الملف المطبوع."""
    x("UPDATE events SET in_report=? WHERE id=?", (1 if flag else 0, event_id))


def last_backup_time():
    return jload(SET_PATH, {}).get("last_backup")


def last_export_time():
    return jload(SET_PATH, {}).get("last_export")


def has_legacy_plain_db() -> bool:
    """قاعدة قديمة غير مشفّرة (إصدارات قبل التشفير) تنتظر الترحيل عند إنشاء الحساب."""
    return os.path.exists(DB_PATH)


def backup_info(name):
    """(المسار الكامل, الحجم بالبايت) لنسخة احتياطية داخل الجهاز."""
    full = os.path.join(BK_DIR, name)
    return full, os.path.getsize(full)


def thumb_exists(rel) -> bool:
    return os.path.isfile(ap(thumb_rel(rel)))


def file_exists(rel) -> bool:
    return bool(rel) and os.path.exists(ap(rel))


def ev_dt(ev) -> datetime:
    """تاريخ ووقت الموعد (الوقت الافتراضي 09:00 للمواعيد القديمة)."""
    t = ev["time"] or DEFAULT_TIME
    try:
        return datetime.strptime(f"{ev['date']} {t}", "%Y-%m-%d %H:%M")
    except ValueError:
        return datetime.strptime(ev["date"], "%Y-%m-%d")


def _ar_n(n, one, two, few, many):
    if n == 1:
        return f"بعد {one}"
    if n == 2:
        return f"بعد {two}"
    return f"بعد {n} {few}" if 3 <= n <= 10 else f"بعد {n} {many}"


def rel_label(dt: datetime) -> str:
    secs = (dt - datetime.now()).total_seconds()
    if secs < 0:
        return "متأخر"
    if secs < 3600:
        return _ar_n(max(1, int(secs // 60)), "دقيقة", "دقيقتين", "دقائق", "دقيقة")
    if secs < 86400:
        return _ar_n(int(secs // 3600), "ساعة", "ساعتين", "ساعات", "ساعة")
    return _ar_n(int(secs // 86400), "يوم", "يومين", "أيام", "يوماً")


def upcoming_events(window_days):
    """(المتأخرة, القادمة خلال window_days×24 ساعة) للمواعيد غير المؤكدة."""
    now = datetime.now()
    limit = now + timedelta(days=window_days)
    rows = q("""SELECT e.*, p.full_name, p.code FROM events e
                JOIN patients p ON p.id=e.patient_id
                WHERE e.done=0 AND COALESCE(e.cancelled,0)=0""")
    late, soon = [], []
    for r in rows:
        dt = ev_dt(r)
        if dt < now:
            late.append((dt, r))
        elif dt <= limit:
            soon.append((dt, r))
    late.sort(key=lambda z: z[0])
    soon.sort(key=lambda z: z[0])
    return late, soon


IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")


def is_image_name(name: str) -> bool:
    return (name or "").lower().endswith(IMG_EXT)


def _sniff_ext(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"GIF8":
        return ".gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".jpg"


def new_rel(code: str) -> str:
    """مسار نسبي معتم: لا اسم مريض ولا نوع ملف في الاسم."""
    return f"patients/{code}/{secrets.token_hex(8)}.bin"


def _faad(rel: str) -> bytes:
    """AAD الملف = مساره النسبي: ملف منسوخ إلى مسار آخر (تبديل صورة مريض بأخرى) يفشل التحقق منه."""
    return b"file:" + rel.encode("utf-8")


def write_enc(rel: str, data: bytes):
    path = ap(rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _atomic_write(path, K.encrypt_blob(VAULT.dek, data, aad=_faad(rel)))


def read_file(rel: str) -> bytes:
    """يقرأ ملفاً مخزّناً ويفكّ تشفيره. (ملف قديم غير مشفّر يُقرأ كما هو إلى أن يُرحَّل.)"""
    if not VAULT.unlocked:
        raise NotUnlocked("سجّل الدخول أولاً")
    with open(ap(rel), "rb") as f:
        raw = f.read()
    if not K.is_encrypted(raw[:4]):
        return raw
    try:
        return K.decrypt_blob(VAULT.dek, raw, aad=_faad(rel))
    except K.CryptoError:
        if _mem["aad_legacy"]:               # ملفات إصدارات قبل 2.6 (aad="file") إلى أن يكتمل الترحيل
            return K.decrypt_blob(VAULT.dek, raw, aad=b"file")
        raise


def _migrate_file_aad():
    """مرة واحدة: يعيد تشفير ملفات المرضى القديمة (aad="file") بـAAD المسار. بعد نجاحها كلها يُغلَق مسار القراءة القديم."""
    st = jload(SET_PATH, {})
    if st.get("aad_v") == 2:
        _mem["aad_legacy"] = False
        return
    _mem["aad_legacy"] = True
    failed = 0
    for root, _, files in os.walk(PAT_DIR):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), BASE).replace(os.sep, "/")
            try:
                with open(ap(rel), "rb") as f:
                    raw = f.read()
                if not K.is_encrypted(raw[:4]):
                    continue                                   # غير مشفّر: يتولاه _migrate_legacy_files
                try:
                    K.decrypt_blob(VAULT.dek, raw, aad=_faad(rel))
                    continue
                except K.CryptoError:
                    pass
                try:
                    data = K.decrypt_blob(VAULT.dek, raw, aad=b"file")
                except K.CryptoError as ex:
                    LOG.log_exc("aad_corrupt", ex, file=fn)     # تالف أو مبدَّل: لا يصلح بإبقاء المسار القديم مفتوحاً
                    continue
                _atomic_write(ap(rel), K.encrypt_blob(VAULT.dek, data, aad=_faad(rel)))
            except Exception as ex:                             # خطأ إدخال/إخراج عابر: نُبقي الترحيل مفتوحاً للمحاولة التالية
                failed += 1
                LOG.log_exc("aad_migrate", ex, file=fn)
    if failed == 0:
        st["aad_v"] = 2
        jsave(SET_PATH, st)
        _mem["aad_legacy"] = False


def file_b64(rel: str) -> str:
    """للعرض داخل التطبيق دون كتابة نسخة عادية على القرص (ft.Image(src_base64=...))."""
    return base64.b64encode(read_file(rel)).decode()


def thumb_rel(rel: str) -> str:
    """مسار المصغّرة المشفّرة المرافقة لصورة (يُنشأ عند الحفظ إن توفّرت مكتبة الصور)."""
    return (rel[:-4] if rel.endswith(".bin") else rel) + "_t.bin"


def file_size(rel: str) -> int:
    try:
        return os.path.getsize(ap(rel))
    except OSError:
        return 0


def thumb_b64(rel: str):
    """(base64, هل_هي_مصغّرة). تعود للأصل إن لم توجد مصغّرة."""
    t = thumb_rel(rel)
    if os.path.isfile(ap(t)):
        try:
            return base64.b64encode(read_file(t)).decode(), True
        except Exception as ex:
            LOG.log_exc("thumb_read", ex)
    return file_b64(rel), False


def _wipe_rel(rel):
    """يمحو ملفاً مخزّناً ومصغّرته."""
    if rel:
        _wipe_file(ap(rel))
        _wipe_file(ap(thumb_rel(rel)))


def store_file(p, src, tag=None):
    """يقرأ ملفاً من المصدر ويحفظه مشفّراً باسم معتم داخل مجلد المريض، ويعيد المسار النسبي.
    الصور تُصغَّر وتُجرَّد من EXIF وتُنشأ لها مصغّرة (إن توفّرت Pillow)؛ غير الصور تُحفظ كما هي."""
    with open(src, "rb") as f:
        data = f.read()
    thumb = None
    if IMG.sniff(data):
        try:
            data, thumb = IMG.process(data)
        except Exception as ex:                       # لا نُفشل الحفظ بسبب معالجة الصورة
            LOG.log_exc("img_process", ex)
    rel = new_rel(p["code"])
    write_enc(rel, data)
    if thumb:
        try:
            write_enc(thumb_rel(rel), thumb)
        except OSError as ex:
            LOG.log_exc("thumb_write", ex)
    return rel


class DuplicatePatient(ValueError):
    """مريض مشابه موجود. .matches = قائمة {id, code, full_name, phone, age, reason: 'name'|'phone'}."""

    def __init__(self, matches):
        super().__init__("يوجد مريض مشابه")
        self.matches = matches


def digits(s) -> str:
    """الأرقام فقط (يحوّل الأرقام العربية والهندية)."""
    return re.sub(r"\D", "", (s or "").translate(_DIGITS)) if isinstance(s, str) else ""


def phone_key(s) -> str:
    """مفتاح مقارنة للهاتف: آخر 9 أرقام (يطابق 0944123456 مع +963944123456 و00963944123456)."""
    d = digits(s)
    return d[-9:] if len(d) >= 9 else d


def search_patients(term, limit=50):
    """بحث بالاسم (مطبَّع) أو الكود أو **رقم الهاتف** (جزء من الرقم، 3 أرقام فأكثر، يتجاهل الصفر البادئ ورمز الدولة)."""
    t, td = norm(term), digits(term)
    if not t and not td:
        return []
    tz = td.lstrip("0")
    out = []
    for r in q("SELECT id, code, full_name, status, phone, age FROM patients ORDER BY full_name"):
        hit = bool(t) and (t in norm(r["full_name"]) or t in (r["code"] or "").lower())
        if not hit and len(td) >= 3:
            pd = digits(r["phone"])
            hit = td in pd or (len(tz) >= 3 and tz in pd)
        if hit:
            out.append(r)
            if len(out) >= limit:
                break
    return out


def find_duplicates(name, phone, age=None, exclude_id=None):
    """مرضى يحتمل أنهم الشخص نفسه:
       • reason='name'  : الاسم نفسه (مطبَّعاً) مع تطابق الهاتف أو غيابه أو تقارب العمر (±2)
       • reason='phone' : الهاتف نفسه باسم مختلف (قد يكونون من العائلة) — يُنبَّه فقط."""
    nn, pk = norm(name), phone_key(phone)
    out = []
    for r in q("SELECT id, code, full_name, phone, age FROM patients"):
        if exclude_id and r["id"] == exclude_id:
            continue
        rk = phone_key(r["phone"])
        same_phone = len(pk) >= 7 and pk == rk
        if nn and norm(r["full_name"]) == nn and (same_phone or not pk or not rk or age is None or r["age"] is None
                                                   or abs(int(age) - int(r["age"])) <= 2):
            out.append(dict(r, reason="name"))
        elif same_phone:
            out.append(dict(r, reason="phone"))
    return out


def save_patient(f, photos, atts, pid=None, allow_duplicate=False):
    """يحفظ المريض وصوره ومرفقاته في **معاملة واحدة** وبحفظ واحد للقاعدة المشفّرة.
    الفشل في أي خطوة يُرجع كل شيء (لا مريض بكود فارغ ولا ملفات يتيمة)، والصور القديمة المستبدَلة لا تُمحى
    إلا بعد نجاح الحفظ."""
    if not allow_duplicate:                           # منع التكرار: عند مريض جديد أو تغيير الاسم/الهاتف فقط
        cur = q("SELECT full_name, phone FROM patients WHERE id=?", (pid,), one=True) if pid else None
        if cur is None or norm(cur["full_name"]) != norm(f["full_name"]) or phone_key(cur["phone"]) != phone_key(f.get("phone")):
            dups = find_duplicates(f["full_name"], f.get("phone"), f.get("age"), pid)
            if dups:
                raise DuplicatePatient(dups)
    now = datetime.now().isoformat(timespec="seconds")
    new_rels, old_rels, committed = [], [], False
    c = db()                                          # يمسك القفل حتى النهاية
    try:
        if pid is None:
            pid = c.execute("INSERT INTO patients(code,full_name,status,created_at,updated_at) VALUES('',?,?,?,?)",
                            (f["full_name"], f["status"], now, now)).lastrowid
            code = f"PT-{pid:05d}"
            c.execute("UPDATE patients SET code=?, folder=? WHERE id=?", (code, code, pid))
        c.execute("""UPDATE patients SET full_name=?, gender=?, age=?, residence=?, phone=?, job=?,
             diseases=?, notes=?, blood=?, status=?, allergies=?, medications=?, diagnosis=?, updated_at=?
             WHERE id=?""",
                  (f["full_name"], f["gender"], f["age"], f["residence"], f["phone"], f["job"],
                   f["diseases"], f["notes"], f["blood"], f["status"], f.get("allergies") or "",
                   f.get("medications") or "", f.get("diagnosis") or "", now, pid))
        p = c.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
        for key, src in photos.items():
            if key not in ("photo_before", "photo_after", "photo_lab"):   # حماية: أسماء الأعمدة من قائمة ثابتة فقط
                continue
            if src and os.path.exists(src):
                rel = store_file(p, src, key.replace("photo_", ""))
                new_rels.append(rel)
                c.execute(f"UPDATE patients SET {key}=? WHERE id=?", (rel, pid))
                if p[key] and p[key] != rel:
                    old_rels.append(p[key])
        for i, src in enumerate(atts):
            if os.path.exists(src):
                rel = store_file(p, src, f"att_{int(time.time() * 1000)}_{i}")
                new_rels.append(rel)
                c.execute("INSERT INTO attachments(patient_id,path,name) VALUES(?,?,?)",
                          (pid, rel, os.path.basename(src)))
        c.commit_mem()
        committed = True
        _persist()
        for rel in old_rels:                          # بعد نجاح الحفظ فقط
            _wipe_rel(rel)
        return c.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    except BaseException as ex:
        if not committed:                             # لم يُثبَّت شيء: نُرجع القاعدة ونمحو الملفات الجديدة
            c.rollback()
            for rel in new_rels:
                _wipe_rel(rel)
        LOG.log_exc("save_patient", ex, committed=committed)
        raise
    finally:
        c.close()


# ───────────────────────── الإحصائيات ─────────────────────────
def stats(start: str | None = None, end: str | None = None) -> dict:
    """إحصائيات ضمن نطاق تواريخ YYYY-MM-DD (شامل). None = بلا حد."""
    lo, hi = start or "0000-01-01", end or "9999-12-31"
    one = lambda sql, a=(): q(sql, a, one=True)[0]
    return {
        "patients": one("SELECT COUNT(*) FROM patients WHERE substr(created_at,1,10) BETWEEN ? AND ?", (lo, hi)),
        "new": one("SELECT COUNT(*) FROM patients WHERE status='جديد' AND substr(created_at,1,10) BETWEEN ? AND ?", (lo, hi)),
        "old": one("SELECT COUNT(*) FROM patients WHERE status='قديم' AND substr(created_at,1,10) BETWEEN ? AND ?", (lo, hi)),
        "surgeries": one("SELECT COUNT(*) FROM events WHERE kind='surgery' AND done=1 AND substr(done_at,1,10) BETWEEN ? AND ?", (lo, hi)),
        "visits": one("SELECT COUNT(*) FROM events WHERE kind='visit' AND done=1 AND substr(done_at,1,10) BETWEEN ? AND ?", (lo, hi)),
        "pending": one("SELECT COUNT(*) FROM events WHERE done=0 AND COALESCE(cancelled,0)=0 AND date BETWEEN ? AND ?", (lo, hi)),
        "cancelled": one("SELECT COUNT(*) FROM events WHERE COALESCE(cancelled,0)=1 AND COALESCE(no_show,0)=0 AND substr(cancelled_at,1,10) BETWEEN ? AND ?", (lo, hi)),
        "no_show": one("SELECT COUNT(*) FROM events WHERE COALESCE(no_show,0)=1 AND date BETWEEN ? AND ?", (lo, hi)),
        "total_patients": one("SELECT COUNT(*) FROM patients"),
    }


# ───────────────────────── المالية والمواعيد ─────────────────────────
# عملتان مستقلتان (ليرة سورية / دولار): لكل إجراء ولكل دفعة عملتها، ولا يوجد تحويل بينهما.
CURS = ("SYP", "USD")
CUR_SYM = {"SYP": "ل.س", "USD": "$"}
CUR_NAME = {"SYP": "الليرة السورية", "USD": "الدولار"}
CUR_BI = {"SYP": "بالليرة السورية", "USD": "بالدولار"}
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬،", "01234567890123456789.,,")


MINOR = 100                                  # أصغر وحدة: كل المبالغ تُخزَّن وتُجمَع أعداداً صحيحة (×100)، لا كسور عائمة


def to_minor(v) -> int:
    """مبلغ (رقم أو نص) → عدد صحيح بأصغر وحدة، بتقريب نصف لأعلى. يرفض السالب وغير المنتهي وما فوق 1e12."""
    try:
        d = Decimal(str(v).replace(",", "").strip())
    except InvalidOperation:
        raise ValueError("مبلغ غير صالح")
    if not d.is_finite() or d < 0 or d > Decimal("1e12"):
        raise ValueError("مبلغ خارج النطاق")
    return int((d * MINOR).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def from_minor(n) -> float:
    """عدد صحيح بأصغر وحدة → مبلغ للعرض (يُقرَّب لخانتين)."""
    return round(int(n or 0) / MINOR, 2)


def money(v, cur=None) -> str:
    """تنسيق مبلغ؛ مع رمز العملة إن مُرّرت cur ('SYP'/'USD')."""
    v = round(float(v or 0), 2)
    s = f"{v:,.0f}" if v == int(v) else f"{v:,.2f}"
    return f"{s} {CUR_SYM[cur]}" if cur else s


def money_multi(d, sep=" + ") -> str:
    """مبالغ بالعملتين في نص واحد (يُخفي العملة الصفرية)."""
    parts = [money(d.get(c), c) for c in CURS if round(d.get(c) or 0, 2) != 0]
    return sep.join(parts) if parts else "0"


def zero():
    return {c: 0.0 for c in CURS}


def parse_money(s) -> float:
    """يقبل الأرقام العربية والفواصل. يرفع ValueError لقيمة فارغة/سالبة/غير رقمية."""
    t = (s or "").translate(_DIGITS).replace(",", "").replace(" ", "").strip()
    v = float(t)                       # ValueError إن لم يكن رقماً
    if not 0 <= v <= 1e12:             # يرفض السالب و NaN و inf
        raise ValueError("amount out of range")
    return round(v, 2)


_FIN = """SELECT e.*, p.full_name, p.code,
  COALESCE((SELECT SUM(price_minor) FROM event_items WHERE event_id=e.id AND cur='SYP'),0) * (1 - COALESCE(e.cancelled,0)) AS due_syp,
  COALESCE((SELECT SUM(price_minor) FROM event_items WHERE event_id=e.id AND cur='USD'),0) * (1 - COALESCE(e.cancelled,0)) AS due_usd,
  COALESCE((SELECT SUM(amount_minor) FROM payments WHERE event_id=e.id AND cur='SYP'),0) AS paid_syp,
  COALESCE((SELECT SUM(amount_minor) FROM payments WHERE event_id=e.id AND cur='USD'),0) AS paid_usd
  FROM events e JOIN patients p ON p.id=e.patient_id"""        # كل أعمدة المبالغ هنا بأصغر وحدة (أعداد صحيحة)


def amounts_minor(r):
    """(المستحق, المدفوع, المتبقي) لصف من _FIN بأصغر وحدة (أعداد صحيحة) كقواميس {SYP, USD}."""
    due = {"SYP": r["due_syp"], "USD": r["due_usd"]}
    paid = {"SYP": r["paid_syp"], "USD": r["paid_usd"]}
    return due, paid, {c: due[c] - paid[c] for c in CURS}


def amounts(r):
    """(المستحق, المدفوع, المتبقي) لصف من _FIN للعرض (عشري بخانتين)."""
    return tuple({c: from_minor(v) for c, v in d.items()} for d in amounts_minor(r))


def ev_fin(event_id):
    return q(_FIN + " WHERE e.id=?", (event_id,), one=True)


def ev_items(event_id):
    """إجراءات الموعد: price (للعرض) و price_minor (أصغر وحدة)."""
    return q("SELECT id, event_id, name, price_minor, price_minor / 100.0 AS price, cur FROM event_items "
             "WHERE event_id=? ORDER BY id", (event_id,))


def ev_payments(event_id):
    """دفعات الموعد: amount (للعرض) و amount_minor (أصغر وحدة)."""
    return q("SELECT id, event_id, amount_minor, amount_minor / 100.0 AS amount, paid_at, note, cur FROM payments "
             "WHERE event_id=? ORDER BY id", (event_id,))


def _sum(c, table, col, event_id, cur):
    """مجموع عمود مبالغ (بأصغر وحدة) لموعد وعملة."""
    return c.execute(f"SELECT COALESCE(SUM({col}),0) FROM {table} WHERE event_id=? AND cur=?",
                     (event_id, cur)).fetchone()[0]


def _write_items(c, event_id, items):
    """يستبدل إجراءات الموعد (name, price, cur) ضمن معاملة المستدعي. يعيد الإجمالي لكل عملة (للعرض)."""
    clean = []
    for n, pr, cur in items:
        if cur not in CURS:
            raise ValueError("عملة غير معروفة")
        clean.append(((n or "").strip() or "إجراء", to_minor(pr), cur))
    totals = {cur: sum(pr for _, pr, k in clean if k == cur) for cur in CURS}
    for cur in CURS:
        paid = _sum(c, "payments", "amount_minor", event_id, cur)
        if totals[cur] < paid:
            raise ValueError(f"التكلفة {CUR_BI[cur]} ({money(from_minor(totals[cur]), cur)}) "
                             f"أقل من المبلغ المدفوع ({money(from_minor(paid), cur)})")
    c.execute("DELETE FROM event_items WHERE event_id=?", (event_id,))
    c.executemany("INSERT INTO event_items(event_id,name,price_minor,cur) VALUES(?,?,?,?)",
                  [(event_id, n, pr, cur) for n, pr, cur in clean])
    return {cur: from_minor(v) for cur, v in totals.items()}


def _check_pay(c, event_id, amount_m, cur, exclude_m=0):
    """يتحقق أن الدفعة (بأصغر وحدة) لا تتجاوز المتبقي بنفس العملة (exclude_m = قيمة دفعة سابقة يجري تعديلها)."""
    if cur not in CURS:
        raise ValueError("عملة غير معروفة")
    if amount_m <= 0:
        raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
    ev = c.execute("SELECT COALESCE(cancelled,0) FROM events WHERE id=?", (event_id,)).fetchone()
    if ev is None:
        raise ValueError("الموعد غير موجود")
    if ev[0]:
        raise ValueError("هذا الموعد ملغى — أعد تفعيله أولاً لتسجيل دفعة")
    due = _sum(c, "event_items", "price_minor", event_id, cur)
    remaining = due - (_sum(c, "payments", "amount_minor", event_id, cur) - exclude_m)
    if amount_m > remaining:
        if due == 0:
            raise ValueError(f"لا يوجد مستحق {CUR_BI[cur]} على هذا الموعد — "
                             f"عدّل الإجراءات لتسعيرها بهذه العملة أولاً")
        raise ValueError(f"المبلغ أكبر من المتبقي {CUR_BI[cur]} ({money(from_minor(max(remaining, 0)), cur)})")


def _insert_payment(c, event_id, amount, cur, note=""):
    amount_m = to_minor(amount)
    _check_pay(c, event_id, amount_m, cur)
    c.execute("INSERT INTO payments(event_id,amount_minor,cur,paid_at,note) VALUES(?,?,?,?,?)",
              (event_id, amount_m, cur, datetime.now().isoformat(timespec="seconds"), note or ""))


def _check_when(date_s, time_s, duration):
    """يتحقق من التاريخ والوقت والمدة ويعيد المدة النهائية (دقائق)."""
    try:
        datetime.strptime(f"{date_s} {time_s or DEFAULT_TIME}", "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        raise ValueError("تاريخ أو وقت غير صحيح")
    d = int(duration)
    if not 5 <= d <= 720:
        raise ValueError("مدة الموعد يجب أن تكون بين 5 دقائق و12 ساعة")
    return d


def create_event(pid, kind, date_s, time_s, items=(), duration=None):
    if kind not in KIND_AR:
        raise ValueError("نوع غير معروف")
    dur = _check_when(date_s, time_s, duration or DEFAULT_DURATION.get(kind, 30))
    now = datetime.now().isoformat(timespec="seconds")
    with closing(db()) as c, c:
        eid = c.execute("INSERT INTO events(patient_id,kind,date,time,duration_min,created_at) VALUES(?,?,?,?,?,?)",
                        (pid, kind, date_s, time_s, dur, now)).lastrowid
        if items:
            _write_items(c, eid, items)
    return eid


def update_event(event_id, kind, date_s, time_s, items, duration=None):
    """تعديل موعد قبل تأكيده: النوع والتاريخ والوقت والمدة والإجراءات وتكاليفها."""
    if kind not in KIND_AR:
        raise ValueError("نوع غير معروف")
    cur_dur = q("SELECT duration_min FROM events WHERE id=?", (event_id,), one=True)
    dur = _check_when(date_s, time_s, duration or (cur_dur[0] if cur_dur and cur_dur[0] else DEFAULT_DURATION.get(kind, 30)))
    with closing(db()) as c, c:
        row = c.execute("SELECT done, COALESCE(cancelled,0) FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise ValueError("الموعد غير موجود")
        if row[0]:
            raise ValueError("لا يمكن تعديل موعد مؤكَّد")
        if row[1]:
            raise ValueError("هذا الموعد ملغى — أعد تفعيله أولاً لتعديله")
        c.execute("UPDATE events SET kind=?, date=?, time=?, duration_min=? WHERE id=?",
                  (kind, date_s, time_s, dur, event_id))
        return _write_items(c, event_id, items)


def update_items(event_id, items):
    with closing(db()) as c, c:
        row = c.execute("SELECT COALESCE(cancelled,0) FROM events WHERE id=?", (event_id,)).fetchone()
        if row and row[0]:
            raise ValueError("هذا الموعد ملغى — أعد تفعيله أولاً لتعديل إجراءاته")
        return _write_items(c, event_id, items)


def add_payments(event_id, pays, note=""):
    """تسجيل دفعة أو أكثر (amount, cur) — مثلاً بالعملتين معاً — بمعاملة واحدة."""
    if not pays:
        raise ValueError("أدخل مبلغاً مدفوعاً")
    with closing(db()) as c, c:
        for amount, cur in pays:
            _insert_payment(c, event_id, amount, cur, note)


def edit_payment(pay_id, amount, cur, note=None):
    amount_m = to_minor(amount)
    with closing(db()) as c, c:
        row = c.execute("SELECT event_id, amount_minor, cur FROM payments WHERE id=?", (pay_id,)).fetchone()
        if row is None:
            raise ValueError("الدفعة غير موجودة")
        _check_pay(c, row[0], amount_m, cur, exclude_m=row[1] if row[2] == cur else 0)
        if note is None:
            c.execute("UPDATE payments SET amount_minor=?, cur=? WHERE id=?", (amount_m, cur, pay_id))
        else:
            c.execute("UPDATE payments SET amount_minor=?, cur=?, note=? WHERE id=?", (amount_m, cur, note, pay_id))


def delete_payment(pay_id):
    x("DELETE FROM payments WHERE id=?", (pay_id,))


def confirm_event(event_id, notes, items=None, pays=(), nxt=None):
    """تأكيد إنجاز موعد + (اختياري) تحديث الإجراءات + تسجيل المدفوع بالعملتين + موعد مراجعة قادم، بمعاملة واحدة."""
    now = datetime.now().isoformat(timespec="seconds")
    with closing(db()) as c, c:
        row = c.execute("SELECT patient_id, COALESCE(cancelled,0) FROM events WHERE id=? AND done=0",
                        (event_id,)).fetchone()
        if not row:
            raise ValueError("تم تأكيد هذا الموعد سابقاً")
        if row[1]:
            raise ValueError("هذا الموعد ملغى — أعد تفعيله أولاً لتأكيده")
        c.execute("UPDATE events SET done=1, done_at=?, notes=? WHERE id=?", (now, notes, event_id))
        if items is not None:
            _write_items(c, event_id, items)
        for amount, cur in pays:
            _insert_payment(c, event_id, amount, cur, "عند التأكيد")
        if nxt:
            c.execute("INSERT INTO events(patient_id,kind,date,time,created_at) VALUES(?,?,?,?,?)",
                      (row[0], "visit", nxt[0], nxt[1], now))


def cancel_event(event_id, reason=""):
    """إلغاء موعد معلّق (لا يُحذف: يبقى في السجل بحالة «ملغى» ويمكن استعادته).
    يُرفض إن كان مؤكَّد الإنجاز أو مُلغى سابقاً أو عليه دفعات مسجّلة (لئلا تضيع أموال مستلمة)."""
    now = datetime.now().isoformat(timespec="seconds")
    with closing(db()) as c, c:
        row = c.execute("SELECT done, COALESCE(cancelled,0) FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise ValueError("الموعد غير موجود")
        if row[0]:
            raise ValueError("لا يمكن إلغاء موعد مؤكَّد الإنجاز")
        if row[1]:
            raise ValueError("هذا الموعد ملغى سابقاً")
        if c.execute("SELECT 1 FROM payments WHERE event_id=? LIMIT 1", (event_id,)).fetchone():
            raise ValueError("على هذا الموعد دفعات مسجّلة. احذفها أو عدّلها أولاً من «الحسابات» ثم ألغِ الموعد.")
        c.execute("UPDATE events SET cancelled=1, cancelled_at=?, cancel_reason=? WHERE id=? AND done=0",
                  (now, (reason or "").strip(), event_id))


def reinstate_event(event_id):
    """استعادة موعد ملغى ليعود معلّقاً."""
    with closing(db()) as c, c:
        cur = c.execute("UPDATE events SET cancelled=0, no_show=0, cancelled_at=NULL, cancel_reason=NULL "
                        "WHERE id=? AND COALESCE(cancelled,0)=1", (event_id,))
        if cur.rowcount == 0:
            raise ValueError("هذا الموعد ليس ملغى")


def set_event_photo(event_id, which, src):
    """صورة قبل/بعد لموعد محدد (تُحفظ في مجلد المريض وتحل محل السابقة)."""
    if which not in ("before", "after"):
        raise ValueError("which")
    ev = q("SELECT * FROM events WHERE id=?", (event_id,), one=True)
    p = q("SELECT * FROM patients WHERE id=?", (ev["patient_id"],), one=True)
    rel = store_file(p, src, f"ev{event_id}_{which}_{int(time.time())}")
    old = ev[f"photo_{which}"]
    try:
        x(f"UPDATE events SET photo_{which}=? WHERE id=?", (rel, event_id))
    except Exception:
        _wipe_rel(rel)                                # لا نترك الملف الجديد يتيماً إن فشل الحفظ
        raise
    if old and old != rel:
        _wipe_rel(old)
    return rel


def fin_stats(lo=None, hi=None) -> dict:
    """إحصائية مالية بالعملتين ضمن [lo, hi] (الجمع بأعداد صحيحة؛ العرض بخانتين).
    المدفوع  = الدفعات المستلمة فعلاً خلال الفترة (حسب تاريخ الدفع).
    المستحق  = المتبقي غير المسدّد على مواعيد الفترة (حسب تاريخ الموعد).  المسجّل = إجمالي تكلفة مواعيد الفترة."""
    lo_, hi_ = lo or "0000-01-01", hi or "9999-12-31"
    pays = q("""SELECT amount_minor, cur, substr(paid_at,1,10) AS d FROM payments
                WHERE substr(paid_at,1,10) BETWEEN ? AND ? ORDER BY paid_at""", (lo_, hi_))
    evs = q(_FIN + " WHERE e.date BETWEEN ? AND ?", (lo_, hi_))
    by_month = True
    if lo and hi:
        by_month = (datetime.strptime(hi, "%Y-%m-%d") - datetime.strptime(lo, "%Y-%m-%d")).days > 92
    zero_m = lambda: {c: 0 for c in CURS}
    paid, groups = zero_m(), {}
    for r in pays:
        paid[r["cur"]] += r["amount_minor"]
        g = groups.setdefault(r["d"][:7] if by_month else r["d"], dict(zero_m(), n=0))
        g[r["cur"]] += r["amount_minor"]
        g["n"] += 1
    registered, outstanding, n_events = zero_m(), zero_m(), 0
    for r in evs:
        due, _, rem = amounts_minor(r)
        if not any(due.values()):
            continue
        n_events += 1
        for c in CURS:
            registered[c] += due[c]
            outstanding[c] += max(rem[c], 0)
    disp = lambda d: {k: from_minor(v) for k, v in d.items()}
    return dict(paid=disp(paid), registered=disp(registered), outstanding=disp(outstanding),
                n_pays=len(pays), n_events=n_events, by_month=by_month,
                groups=[(k, disp({c: v for c, v in g.items() if c != "n"}) | {"n": g["n"]})
                        for k, g in sorted(groups.items(), reverse=True)])


def fin_totals(pid):
    """إجمالي المستحق والمدفوع والمتبقي لمريض، لكل عملة (الجمع بأعداد صحيحة)."""
    due, paid = {c: 0 for c in CURS}, {c: 0 for c in CURS}
    for r in q(_FIN + " WHERE e.patient_id=?", (pid,)):
        d, p_, _ = amounts_minor(r)
        for c in CURS:
            due[c] += d[c]
            paid[c] += p_[c]
    return ({c: from_minor(v) for c, v in due.items()}, {c: from_minor(v) for c, v in paid.items()},
            {c: from_minor(due[c] - paid[c]) for c in CURS})


def fin_patients(term: str, limit=50):
    """بحث مالي عن مريض بالاسم أو الكود، مع إجمالي المستحق والمدفوع والمتبقي لكل عملة."""
    out = []
    for r in search_patients(term, limit):
        due, paid, rem = fin_totals(r["id"])
        out.append(dict(id=r["id"], code=r["code"], full_name=r["full_name"], due=due, paid=paid, rem=rem))
    return out


def fin_file(pid):
    """الملف المالي للمريض: [{ev, items, pays, due, paid, rem}], ثم إجمالي المستحق والمدفوع والمتبقي."""
    out = []
    for ev in q(_FIN + " WHERE e.patient_id=? ORDER BY e.date DESC, e.time DESC", (pid,)):
        due, paid, rem = amounts(ev)
        out.append(dict(ev=ev, items=ev_items(ev["id"]), pays=ev_payments(ev["id"]), due=due, paid=paid, rem=rem))
    return (out,) + fin_totals(pid)


# ───────────────────────── الترخيص ─────────────────────────
# سجل الحالة (license.json) موثَّق بـ HMAC مرتبط بمعرّف الجهاز لكشف العبث العابر. الأكواد نفسها موقّعة
# توقيعاً غير متماثل (لا يمكن تزويرها). وبما أن التطبيق يعمل دون اتصال، فالتحقق من التاريخ «جهد معقول»
# وليس حماية مطلقة ضد من يملك صلاحية جذر على الجهاز.
def _lic_mac(d) -> str:
    key = K.sha256(b"shifa-lic-state", bytes.fromhex(d["device_id"]))
    msg = f'{d["device_id"]}|{d["last_serial"]}|{d.get("expires")}|{d["last_seen"]}|{d.get("plan", 0)}'.encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:20]


def _lic_save(d):
    d["v"] = 2
    d["mac"] = _lic_mac(d)
    jsave(LIC_PATH, d)


def lic_load():
    d = jload(LIC_PATH, None)
    if not isinstance(d, dict) or "device_id" not in d:
        if os.path.exists(LIC_PATH):                      # ملف تالف فعلاً (لا نتخلص منه بصمت): نحفظه للفحص
            try:
                os.replace(LIC_PATH, LIC_PATH + ".corrupt")
            except OSError:
                pass
        d = {"device_id": secrets.token_hex(4), "last_serial": 0, "expires": None,
             "last_seen": datetime.now().isoformat(), "plan": 0}
        _lic_save(d)
    return d


def lic_status():
    """يعيد (الحالة, الأيام المتبقية). الحالة: ok | none | expired | tampered (ملف الترخيص معدّل)
    | clock (تاريخ الجهاز أقدم من آخر استخدام مسجّل — يُفكّ بكود من المطوّر)"""
    d = lic_load()
    now = datetime.now()
    if d.get("v") != 2:          # ترخيص من إصدار قديم: يُرحَّل مرة واحدة بسقف 400 يوم
        d.setdefault("plan", 0)
        d["last_serial"] = 0     # الأكواد القديمة بصيغة مختلفة ولا تُقبل أصلاً، فيبدأ العدّ من جديد
        if d.get("expires") and datetime.fromisoformat(d["expires"]) > now + timedelta(days=400):
            d["expires"] = (now + timedelta(days=400)).isoformat()
        _lic_save(d)
    elif d.get("mac") != _lic_mac(d):
        return "tampered", 0
    seen = datetime.fromisoformat(d["last_seen"])
    if now < seen - timedelta(days=1):
        return "clock", 0
    if now - seen >= timedelta(minutes=10):          # لا نعيد كتابة الملف عند كل استدعاء (تقليل خطر التلف)
        d["last_seen"] = now.isoformat()
        _lic_save(d)
    if not d["expires"]:
        return "none", 0
    exp = datetime.fromisoformat(d["expires"])
    if now > exp:
        return "expired", 0
    return "ok", (exp - now).days


def lic_activate(code):
    """يعيد (نجاح, رسالة). يقبل كود اشتراك أو كود فك قفل التاريخ."""
    d = lic_load()
    st, _ = lic_status()
    try:
        serial, months, issued = LC.parse_code_ex(code, d["device_id"])
    except LC.LicenseError as ex:
        return False, str(ex)
    if serial <= d["last_serial"]:
        return False, "هذا الكود مستخدم سابقاً. اطلب كوداً جديداً."
    now = datetime.now()
    if months == LC.CLOCK_FIX and st != "clock":
        return False, ("لا يوجد قفل تاريخ على هذا الجهاز، لم يُستهلك الكود." if st != "tampered" else
                       "ملف الترخيص نفسه معدّل أو تالف: اطلب كود تفعيل جديداً.")
    if st == "clock":
        # تاريخ الإصدار داخل الكود موقّع من المطوّر = مرجع زمني حقيقي: لا نقبل الفك إن كان تاريخ الجهاز أقدم منه
        if now.date() < issued - timedelta(days=1):
            return False, "تاريخ هذا الجهاز أقدم من تاريخ إصدار الكود. صحّح تاريخ الجهاز والوقت ثم أعد المحاولة."
        d["last_seen"] = now.isoformat()
        if months == LC.CLOCK_FIX:
            d["last_serial"] = serial
            _lic_save(d)
            return True, "تم فك قفل التاريخ. تأكد أن تاريخ الجهاز صحيح."
    base = now
    if d.get("expires") and st in ("ok", "clock"):      # تجديد مبكر: تُضاف المدة إلى ما تبقى (إن لم ينتهِ)
        exp = datetime.fromisoformat(d["expires"])
        if exp > now:
            base = exp
    d.update(expires=add_months(base, months).isoformat(), last_serial=serial,
             last_seen=now.isoformat(), plan=months)
    _lic_save(d)
    return True, f"تم التفعيل ({LC.PLANS[months]}) — الترخيص ساري حتى {d['expires'][:10]}"


# ───────────────────────── إدارة الحساب ─────────────────────────
def need_setup() -> bool:
    return not VAULT.exists()


def keys_ready() -> bool:
    return LC.keys_ready()


def setup_account(user, password, escrow=True):
    """ينشئ الحساب (اسم مستخدم + كلمة مرور) ويشفّر أي بيانات من إصدارات سابقة.
    escrow=False: لا يُغلَّف مفتاح البيانات للمدير (الاسترداد بمفتاح الاسترداد فقط). يعيد مفتاح الاسترداد للعرض مرة واحدة."""
    if not LC.keys_ready():
        raise VaultError("مفاتيح المطوّر غير مضبوطة في هذه النسخة (public_keys.py). شغّل: python keygen.py init")
    rkey = VAULT.create(user, password, LC.box_pub(), escrow=escrow)
    open_db()
    _migrate_all_legacy()
    return rkey


def unlock(user, password, accept_rollback=False) -> str:
    """'ok' | 'bad' | 'wait' (فترة انتظار بعد محاولات خاطئة؛ VAULT.wait_seconds).
    يرفع RollbackError إن بدا أن db.enc أقدم من آخر حفظ، ويُعاد الاستدعاء بـ accept_rollback=True بقرار المستخدم."""
    r = VAULT.login(user, password)
    if r == "ok":
        _mem["accept_rollback"] = bool(accept_rollback)
        try:
            open_db()
            _migrate_all_legacy()
        except RollbackError:
            lock_app()
            raise
        except MG.SchemaTooNew as ex:
            lock_app()
            raise VaultError(str(ex))
        except Exception as ex:
            lock_app()
            LOG.log_exc("unlock_open_db", ex)
            raise VaultError(f"تعذّر فتح قاعدة البيانات المشفّرة ({type(ex).__name__}). "
                             f"إن كان الملف تالفاً فاستعد آخر نسخة احتياطية.")
        finally:
            _mem["accept_rollback"] = False
    return r


# ───────────────────────── القفل التلقائي ─────────────────────────
LOCK_CHOICES = (0, 30, 60, 180, 600)          # ثوانٍ: 0 = فور الخروج من التطبيق
LOCK_DEFAULT = 0


def lock_policy() -> int:
    """مهلة القفل عند الذهاب للخلفية بالثواني (0 = فوراً)."""
    v = jload(SET_PATH, {}).get("lock_after")
    return int(v) if v in LOCK_CHOICES else LOCK_DEFAULT


def set_lock_policy(seconds: int):
    if seconds not in LOCK_CHOICES:
        raise ValueError("قيمة غير مدعومة")
    st = jload(SET_PATH, {})
    st["lock_after"] = int(seconds)
    jsave(SET_PATH, st)


def lock_app():
    close_db()
    VAULT.lock()
    _stop_server()                      # يمسح أي ملفات مؤقتة (تقارير/مرفقات مفتوحة)


def reset_request_code() -> str:
    return VAULT.begin_reset(lic_load()["device_id"])


def reset_with_code(reply_code, new_password):
    VAULT.finish_reset(reply_code, new_password, lic_load()["device_id"], LC.box_pub())
    open_db()
    _migrate_all_legacy()


def reset_with_recovery_key(text, new_password):
    """استرداد كلمة المرور بمفتاح الاسترداد الذي يحتفظ به صاحب العيادة (دون المدير)."""
    VAULT.reset_with_recovery_key(text, new_password)
    open_db()
    _migrate_all_legacy()


def create_recovery_key() -> str:
    return VAULT.create_recovery_key()


def set_escrow(enabled: bool):
    VAULT.set_escrow(enabled, LC.box_pub() if enabled else None)


# ───────────────────────── ترحيل بيانات الإصدارات السابقة ─────────────────────────
_OPAQUE = re.compile(r"patients/[^/]+/[0-9a-f]{16}\.bin$")


def _migrate_legacy_files():
    """يشفّر الصور/المرفقات القديمة ويعيد تسميتها بأسماء معتمة، ثم يمحو القديم وأي ملف غير مُشار إليه."""
    keep, old = set(), []
    with closing(db()) as c, c:
        codes = {r["id"]: r["code"] for r in c.execute("SELECT id, code FROM patients")}

        def move(rel, code):
            if not rel or not os.path.isfile(ap(rel)):
                return rel
            with open(ap(rel), "rb") as f:
                already = K.is_encrypted(f.read(4))
            if already and _OPAQUE.fullmatch(rel):
                keep.add(rel)
                return rel
            new = new_rel(code)
            write_enc(new, read_file(rel))
            keep.add(new)
            old.append(ap(rel))
            return new
        for pid, code in codes.items():
            row = c.execute("SELECT photo_before, photo_after, photo_lab FROM patients WHERE id=?", (pid,)).fetchone()
            for key in ("photo_before", "photo_after", "photo_lab"):
                new = move(row[key], code)
                if new != row[key]:
                    c.execute(f"UPDATE patients SET {key}=? WHERE id=?", (new, pid))
            c.execute("UPDATE patients SET folder=? WHERE id=?", (code, pid))
            for a in c.execute("SELECT id, path FROM attachments WHERE patient_id=?", (pid,)).fetchall():
                new = move(a["path"], code)
                if new != a["path"]:
                    c.execute("UPDATE attachments SET path=? WHERE id=?", (new, a["id"]))
        for ev in c.execute("SELECT id, patient_id, photo_before, photo_after FROM events").fetchall():
            for key in ("photo_before", "photo_after"):
                new = move(ev[key], codes.get(ev["patient_id"], "PT-00000"))
                if new != ev[key]:
                    c.execute(f"UPDATE events SET {key}=? WHERE id=?", (new, ev["id"]))
    for path in old:                     # بعد نجاح الحفظ فقط
        _wipe_file(path)
    for rel in list(keep):                           # مصغّرات الصور المحتفظ بها ليست يتيمة
        if os.path.isfile(ap(thumb_rel(rel))):
            keep.add(thumb_rel(rel))
    for root, _, files in os.walk(PAT_DIR):          # أي ملف غير مُشار إليه = يتيم
        for fn in files:
            full = os.path.join(root, fn)
            if os.path.relpath(full, BASE).replace(os.sep, "/") not in keep:
                _wipe_file(full)
    for root, dirs, _ in os.walk(PAT_DIR, topdown=False):
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except OSError:
                pass


def _migrate_legacy_backups():
    for fn in os.listdir(BK_DIR):
        if not fn.endswith(".zip"):
            continue
        zp = os.path.join(BK_DIR, fn)
        try:
            with zipfile.ZipFile(zp) as z, _bk_open(zp[:-4] + BK_EXT) as w:
                if "shifa.db" not in z.namelist():
                    raise ValueError("not a backup")
                w.add("__db__", b"\x01" + z.read("shifa.db"))
                for m in z.namelist():
                    if m.startswith("patients/") and not m.endswith("/") and ".." not in m:
                        w.add(m, z.read(m))
            os.remove(zp)
        except Exception:
            try:
                os.remove(zp[:-4] + BK_EXT)
            except OSError:
                pass


def _migrate_all_legacy():
    st = jload(SET_PATH, {})
    if st.get("enc_v") == 2:
        return
    if os.path.exists(DB_ENC):
        for suffix in ("", "-wal", "-shm", "-journal"):
            if os.path.exists(DB_PATH + suffix):
                _wipe_file(DB_PATH + suffix)
    _migrate_legacy_files()
    _migrate_legacy_backups()
    st = jload(SET_PATH, {})
    st["enc_v"] = 2
    jsave(SET_PATH, st)


# ───────────────────────── النسخ الاحتياطي (مشفّر) ─────────────────────────
# النسخة = حاوية .shbk: ترويسة الحساب (ملح + DEK مغلَّف) ثم سجلات (قاعدة البيانات + الملفات)، كل سجل مشفّر
# ومصادَق على حدة. استعادتها على جهاز آخر تتطلب كلمة مرور الحساب الذي أُخذت منه النسخة.
BK_EXT = ".shbk"
_BK_MAGIC = b"SHBK1"


class _bk_open:
    """كاتب حاوية نسخة احتياطية (بثّ تدريجي إلى القرص)."""

    def __init__(self, path):
        self.path, self.tmp = path, path + ".tmp"

    def __enter__(self):
        self.f = open(self.tmp, "wb")
        hb = json.dumps(VAULT.public_header()).encode()
        self.f.write(_BK_MAGIC + struct.pack(">I", len(hb)) + hb)
        return self

    def add(self, name, data: bytes):
        nb = name.encode("utf-8")
        sealed = K.seal(VAULT.dek, struct.pack(">H", len(nb)) + nb + data, aad=b"bk")
        self.f.write(struct.pack(">I", len(sealed)) + sealed)

    def __exit__(self, et, ev, tb):
        self.f.flush()
        os.fsync(self.f.fileno())
        self.f.close()
        if et is None:
            os.replace(self.tmp, self.path)
        else:
            try:
                os.remove(self.tmp)
            except OSError:
                pass
        return False


def _bk_header(path):
    with open(path, "rb") as f:
        if f.read(5) != _BK_MAGIC:
            raise ValueError("ملف النسخة الاحتياطية غير صالح")
        n = struct.unpack(">I", f.read(4))[0]
        return json.loads(f.read(n)), f.tell()


def _bk_records(path, key):
    _, off = _bk_header(path)
    with open(path, "rb") as f:
        f.seek(off)
        while True:
            lb = f.read(4)
            if not lb:
                return
            rec = K.open_sealed(key, f.read(struct.unpack(">I", lb)[0]), aad=b"bk")
            nl = struct.unpack(">H", rec[:2])[0]
            yield rec[2:2 + nl].decode("utf-8"), rec[2 + nl:]


def _bk_key(f):
    """ترتيب زمني حقيقي: وقت إنشاء الملف أولاً، ثم الطابع/اللاحقة _N رقمياً عند التساوي
    (الاسم وحده لا يكفي: _10 تسبق _2 أبجدياً، ويُعاد استخدام لاحقة محذوفة فتبدو الجديدة أقدم)."""
    m = re.match(r"shifa_backup_(\d{8}_\d{6})(?:_(\d+))?", f)
    try:
        mt = os.stat(os.path.join(BK_DIR, f)).st_mtime_ns
    except OSError:
        mt = 0
    return (mt, m.group(1) if m else "", int(m.group(2) or 1) if m else 0, f)


def list_backups():
    os.makedirs(BK_DIR, exist_ok=True)
    return sorted([f for f in os.listdir(BK_DIR) if f.endswith(BK_EXT)], key=_bk_key, reverse=True)


def _prune_backups(keep=None, protect=None):
    """يحتفظ بأحدث `keep` نسخة داخل الجهاز ويحذف الأقدم. `protect`: مسار نسخة لا تُحذف أبداً (التي أُنشئت للتو)."""
    for f in list_backups()[(keep or KEEP_BACKUPS):]:
        if protect and os.path.abspath(os.path.join(BK_DIR, f)) == os.path.abspath(protect):
            continue
        try:
            os.remove(os.path.join(BK_DIR, f))
        except OSError:
            pass


def mark_exported():
    """يسجّل أن المستخدم صدّر نسخة إلى خارج مجلد التطبيق (يُفتح الملف في المتصفح للتنزيل)."""
    st = jload(SET_PATH, {})
    st["last_export"] = datetime.now().isoformat()
    jsave(SET_PATH, st)


def export_due():
    """(مستحق؟, عدد الأيام منذ آخر تصدير أو None). لا تذكير إن لم يوجد مرضى بعد."""
    if not q("SELECT 1 FROM patients LIMIT 1"):
        return False, None
    last = jload(SET_PATH, {}).get("last_export")
    if not last:
        return True, None
    try:
        days = (datetime.now() - datetime.fromisoformat(last)).days
    except ValueError:
        return True, None
    return days >= EXPORT_REMIND_DAYS, days


def make_backup(prune=True):
    if not VAULT.unlocked:
        raise NotUnlocked("سجّل الدخول أولاً")
    os.makedirs(BK_DIR, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d_%H%M%S}"
    path, n = os.path.join(BK_DIR, f"shifa_backup_{stamp}{BK_EXT}"), 1
    while os.path.exists(path):                       # لا نكتب فوق نسخة موجودة أبداً (قد تكون هي المصدر)
        n += 1
        path = os.path.join(BK_DIR, f"shifa_backup_{stamp}_{n}{BK_EXT}")
    with _lock:
        db_blob = _serialize(_mem["conn"])
    total, skipped = 0, 0
    with _bk_open(path) as w:
        w.add("__db__", db_blob)
        for root, _, files in os.walk(PAT_DIR):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, BASE).replace(os.sep, "/")
                total += 1
                try:
                    w.add(rel, read_file(rel))
                except Exception as ex:               # ملف تالف/غير مقروء: لا نُسقط النسخة كلها لكن نُبلغ بوضوح
                    skipped += 1
                    LOG.log_exc("backup_skip", ex, file=os.path.basename(rel))
    st = jload(SET_PATH, {})
    st["last_backup"] = datetime.now().isoformat()
    st["last_backup_report"] = {"files": total, "skipped": skipped}
    jsave(SET_PATH, st)
    LOG.log("backup_done", files=total, skipped=skipped)
    if prune:
        _prune_backups(protect=path)
    return path


def backup_report() -> dict:
    """نتيجة آخر نسخة: {'files': عدد الملفات, 'skipped': ما تعذّر نسخه}. skipped > 0 يستوجب تنبيه المستخدم."""
    return jload(SET_PATH, {}).get("last_backup_report") or {"files": 0, "skipped": 0}


def auto_backup_if_due():
    st = jload(SET_PATH, {})
    last = st.get("last_backup")
    if not last:
        if q("SELECT 1 FROM patients LIMIT 1"):
            make_backup()
        else:
            st["last_backup"] = datetime.now().isoformat()
            jsave(SET_PATH, st)
        return
    if datetime.now() - datetime.fromisoformat(last) >= timedelta(days=BACKUP_EVERY_DAYS):
        make_backup()


def backup_needs_password(path) -> bool:
    """هل النسخة من حساب/مفتاح مختلف عن الحالي (فتحتاج كلمة مرور الحساب الأصلي)؟"""
    hdr, _ = _bk_header(path)
    try:
        K.open_sealed(VAULT.dek, bytes.fromhex(hdr["check"]), aad=b"check")
        return False
    except (K.CryptoError, KeyError, ValueError):
        return True


def restore_backup(path, password=None):
    """يستبدل كل البيانات بمحتوى النسخة (يُعاد تشفيرها بمفتاح هذا الحساب). تُؤخذ نسخة أمان قبل الاستبدال."""
    if backup_needs_password(path):
        hdr, _ = _bk_header(path)
        dek_b = VT.unwrap_with_password(hdr, password or "") or VT.unwrap_with_recovery_key(hdr, password or "")
        if dek_b is None:
            raise ValueError("كلمة المرور أو مفتاح الاسترداد غير صحيح (المطلوب: كلمة مرور الحساب وقت أخذ النسخة)")
    else:
        dek_b = VAULT.dek
    if q("SELECT 1 FROM patients LIMIT 1"):
        make_backup(prune=False)          # لا نحذف شيئاً قبل نجاح الاستعادة: قد يكون الملف المُستعاد من هذا المجلد
    new_dir = PAT_DIR + ".restore"
    shutil.rmtree(new_dir, ignore_errors=True)
    os.makedirs(new_dir)
    db_blob = None
    try:
        for name, data in _bk_records(path, dek_b):
            if name == "__db__":
                db_blob = data
                continue
            parts = name.split("/")
            if len(parts) < 3 or parts[0] != "patients" or any(p in ("", "..", ".") for p in parts):
                continue                                   # يمنع الخروج من المجلد (path traversal)
            target = os.path.join(new_dir, *parts[1:])
            os.makedirs(os.path.dirname(target), exist_ok=True)
            _atomic_write(target, K.encrypt_blob(VAULT.dek, data, aad=_faad("/".join(parts))))
        if db_blob is None:
            raise ValueError("النسخة لا تحوي قاعدة بيانات")
        new_conn = _new_conn(db_blob)
        ok = new_conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok" and \
            new_conn.execute("SELECT 1 FROM sqlite_master WHERE name='patients'").fetchone()
        if not ok:
            raise ValueError("قاعدة البيانات داخل النسخة تالفة")
    except K.CryptoError:
        shutil.rmtree(new_dir, ignore_errors=True)
        raise ValueError("النسخة تالفة أو عُدّلت بعد إنشائها")
    except Exception:
        shutil.rmtree(new_dir, ignore_errors=True)
        raise
    with _lock:
        old = PAT_DIR + ".old"
        shutil.rmtree(old, ignore_errors=True)
        old_conn = _mem["conn"]
        # سجلّ التعافي: بصمة القاعدة الحالية؛ فإن انقطع التطبيق أُعيد الوضع السابق كاملاً عند الإقلاع التالي
        _atomic_write(JOURNAL, json.dumps({"db_sig": _file_sig(DB_ENC), "at": datetime.now().isoformat()}).encode())
        try:
            os.replace(PAT_DIR, old)
            os.replace(new_dir, PAT_DIR)
            _mem["conn"] = new_conn
            init_db()
            _persist()
        except BaseException as ex:
            LOG.log_exc("restore_swap", ex)
            res = recover_interrupted_restore()
            if res == "rolled_back":
                _mem["conn"] = old_conn
                new_conn.close()
            raise
    if old_conn is not None:
        old_conn.close()
    shutil.rmtree(old, ignore_errors=True)
    try:
        os.remove(JOURNAL)
    except OSError:
        pass
    _migrate_legacy_files()                                 # أسماء معتمة لأي ملفات من نسخ قديمة
    _prune_backups()


def _file_sig(path) -> str:
    try:
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except OSError:
        return ""


def recover_interrupted_restore():
    """يُستدعى عند الإقلاع (وعند فشل الاستعادة): إن وُجد سجلّ استعادة غير مكتمل يحسم الحالة بلا فقد بيانات:
       • قاعدة db.enc لم تتغيّر منذ بدء الاستبدال  → تُرجَع الصور القديمة (rolled_back)
       • القاعدة الجديدة حُفظت                     → يُكمَل التنظيف (committed)
    ويحذف بقايا مجلدات الاستعادة المؤقتة. يعيد None إن لم يكن هناك شيء."""
    new_dir, old = PAT_DIR + ".restore", PAT_DIR + ".old"
    try:
        with open(JOURNAL, encoding="utf-8") as f:
            j = json.load(f)
    except (OSError, ValueError):
        shutil.rmtree(new_dir, ignore_errors=True)
        return None
    if _file_sig(DB_ENC) != j.get("db_sig", ""):
        shutil.rmtree(old, ignore_errors=True)
        res = "committed"
    else:
        if os.path.isdir(old):
            shutil.rmtree(PAT_DIR, ignore_errors=True)
            os.replace(old, PAT_DIR)
        res = "rolled_back"
    shutil.rmtree(new_dir, ignore_errors=True)
    try:
        os.remove(JOURNAL)
    except OSError:
        pass
    LOG.log("restore_recovered", result=res)
    return res


# ───────────────────────── خادم المشاركة المحلي ─────────────────────────
# يعرض ملفاً (تقرير للطباعة / نسخة احتياطية) على 127.0.0.1 فقط، برابط عشوائي
# غير قابل للتخمين، ثم يُفتح في متصفح الهاتف (للطباعة أو التنزيل). يتوقف تلقائياً.
class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def list_directory(self, path):          # منع عرض محتوى المجلدات
        self.send_error(403)
        return None

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


_srv = {"httpd": None, "port": None, "timer": None}


def _stop_server():
    h = _srv["httpd"]
    if h:
        try:
            h.shutdown()
            h.server_close()
        except Exception:
            pass
    _srv.update(httpd=None, port=None, timer=None)
    shutil.rmtree(SHARE_DIR, ignore_errors=True)


SHARE_TTL = 900                      # عمر الرابط المحلي بالثواني (يطابق مؤقّت الخادم)


def new_share_dir():
    """ينشئ مجلداً عشوائياً داخل SHARE_DIR ويعيد (المسار, الرمز).
    يمحو المجلدات المنتهية فقط؛ فتح مرفق ثانٍ لا يكسر تقريراً ما زال مفتوحاً في المتصفح."""
    os.makedirs(SHARE_DIR, exist_ok=True)
    now = time.time()
    for d in os.listdir(SHARE_DIR):
        full = os.path.join(SHARE_DIR, d)
        try:
            if now - os.path.getmtime(full) > SHARE_TTL:
                shutil.rmtree(full, ignore_errors=True)
        except OSError:
            pass
    token = secrets.token_urlsafe(12)
    path = os.path.join(SHARE_DIR, token)
    os.makedirs(path, exist_ok=True)
    return path, token


def share_url(token, filename):
    if not _srv["httpd"]:
        handler = functools.partial(_Handler, directory=SHARE_DIR)
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        _srv.update(httpd=httpd, port=httpd.server_address[1])
    if _srv["timer"]:
        _srv["timer"].cancel()
    t = threading.Timer(900, _stop_server)   # يتوقف بعد 15 دقيقة
    t.daemon = True
    t.start()
    _srv["timer"] = t
    return f"http://127.0.0.1:{_srv['port']}/{token}/{urllib.parse.quote(filename)}"


def share_attachment(rel, name):
    """يفكّ تشفير مرفق إلى مجلد مشاركة مؤقت (يُمحى عند القفل/انتهاء المهلة) ويعيد رابطه المحلي."""
    folder, token = new_share_dir()
    name = os.path.basename((name or "file").replace("\\", "/")) or "file"
    with open(os.path.join(folder, name), "wb") as f:
        f.write(read_file(rel))
    return share_url(token, name)


def share_text(name, text):
    """يجهّز نصاً (مثل تقرير التشخيص) للتنزيل عبر المتصفح ويعيد الرابط."""
    folder, token = new_share_dir()
    name = os.path.basename((name or "report.txt").replace("\\", "/")) or "report.txt"
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(text)
    return share_url(token, name)


def share_file(src_path, name=None):
    """يجهّز ملفاً للفتح/التنزيل عبر المتصفح ويعيد الرابط (name = الاسم الظاهر للمستخدم)."""
    folder, token = new_share_dir()
    name = os.path.basename((name or src_path).replace("\\", "/")) or "file"
    shutil.copyfile(src_path, os.path.join(folder, name))
    return share_url(token, name)


# ───────────────────────── تقرير المريض للطباعة ─────────────────────────
def _css():
    return f""":root{{--p:{TH.PRIMARY};--d:{TH.DARK};--m:{TH.MUTED};--bg:{TH.BG}}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:{TH.TEXT};
font-family:"Noto Naskh Arabic","Segoe UI",Tahoma,Arial,sans-serif;line-height:1.7}}
.page{{max-width:800px;margin:0 auto;background:#fff;padding:26px 28px}}
.bar{{position:sticky;top:0;background:{TH.MINT};border-bottom:1px solid {TH.BORDER_STRONG};padding:10px;text-align:center}}
.bar button{{background:{TH.DEEP};color:#fff;border:0;border-radius:14px;padding:10px 26px;font-size:16px;font-weight:700}}
header{{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid {TH.BORDER_STRONG};padding-bottom:12px;margin-bottom:16px}}
header h1{{margin:0;color:var(--d);font-size:22px}} header small{{color:var(--m)}}
.head{{background:linear-gradient(135deg,{TH.tint(TH.PRIMARY,.2)},#F6FBFA);border:1px solid {TH.BORDER_STRONG};color:var(--d);border-radius:18px;padding:16px 18px;margin-bottom:16px}}
.head h2{{margin:0 0 6px;font-size:24px}} .tag{{display:inline-block;background:#fff;border:1px solid {TH.BORDER_STRONG};border-radius:20px;padding:2px 12px;margin-left:8px;font-size:13px}}
h3{{color:var(--d);border-right:5px solid var(--p);padding-right:10px;margin:20px 0 10px;font-size:17px}}
.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px 18px}}
.f{{display:flex;justify-content:space-between;border-bottom:1px dashed {TH.BORDER_STRONG};padding:4px 0}} .f span{{color:var(--m)}}
.full{{grid-column:1/-1}}
.photos{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
figure{{margin:0;text-align:center}} .ph{{aspect-ratio:1;background:{TH.MINT};border-radius:10px;overflow:hidden;display:flex;align-items:center;justify-content:center;color:var(--m);font-size:12px}}
.ph img{{width:100%;height:100%;object-fit:cover}} figcaption{{font-size:12px;color:var(--m);margin-top:4px}}
table{{width:100%;border-collapse:collapse;font-size:14px}} th{{background:{TH.MINT};color:{TH.DEEP};padding:6px 8px;text-align:right}}
td{{border-bottom:1px solid {TH.DIVIDER};padding:6px 8px}}
footer{{margin-top:26px;color:var(--m);font-size:12px;text-align:center;border-top:1px solid {TH.DIVIDER};padding-top:8px}}
@media print{{body{{background:#fff}} .bar{{display:none}} .page{{padding:0;max-width:none}}
 .head,th{{-webkit-print-color-adjust:exact;print-color-adjust:exact}} h3,table,figure{{break-inside:avoid}}}}
.photos.two{{grid-template-columns:repeat(2,1fr)}} .pt{{font-weight:700;color:var(--d);margin:10px 0 6px}}
.sum{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:6px}}
.box{{background:{TH.MINT};border-radius:12px;padding:10px;text-align:center}} .box span{{display:block;color:var(--m);font-size:13px}} .box b{{font-size:18px;color:var(--d)}}
ul.it{{margin:0;padding:0;list-style:none}} ul.it li{{display:flex;justify-content:space-between;gap:10px}}
td.n{{white-space:nowrap}} tfoot td{{font-weight:700;background:{TH.MINT}}} .neg{{color:{TH.DANGER};font-weight:700}} .pos{{color:{TH.OK};font-weight:700}}
"""


def build_report(pid):
    """ينشئ تقرير HTML (RTL، جاهز للطباعة) ويعيد رابطه المحلي."""
    p = q("SELECT * FROM patients WHERE id=?", (pid,), one=True)
    evs = q("SELECT * FROM events WHERE patient_id=? ORDER BY date,time", (pid,))
    atts = q("SELECT * FROM attachments WHERE patient_id=?", (pid,))
    folder, token = new_share_dir()
    e = lambda v: html.escape(str(v)) if v not in (None, "") else "—"

    def img(rel, name):
        if not rel or not os.path.exists(ap(rel)):
            return ""
        try:
            data = read_file(rel)
        except Exception:
            return ""
        fn = f"{name}{_sniff_ext(data)}"
        with open(os.path.join(folder, fn), "wb") as f:      # نسخة مؤقتة للطباعة فقط (تُمحى تلقائياً)
            f.write(data)
        return fn

    photos = [("قبل", img(p["photo_before"], "before")), ("بعد", img(p["photo_after"], "after")),
              ("التحاليل", img(p["photo_lab"], "lab"))]
    photo_html = "".join(
        f'<figure><div class="ph">{"<img src=%s>" % fn if fn else "<span>لا توجد صورة</span>"}</div>'
        f'<figcaption>{cap}</figcaption></figure>' for cap, fn in photos)

    pairs_html = ""                      # صور قبل/بعد للمواعيد التي اختارها المستخدم للطباعة
    for ev in evs:
        if not ev["in_report"]:
            continue
        b = img(ev["photo_before"], f"ev{ev['id']}_b")
        a_ = img(ev["photo_after"], f"ev{ev['id']}_a")
        if not (b or a_):
            continue
        cell = lambda cap, fn: (f'<figure><div class="ph">{"<img src=%s>" % fn if fn else "<span>لا توجد صورة</span>"}'
                                f'</div><figcaption>{cap}</figcaption></figure>')
        pairs_html += (f'<div class="pt">{KIND_AR[ev["kind"]]} — {e(ev["date"])}</div>'
                       f'<div class="photos two">{cell("قبل", b)}{cell("بعد", a_)}</div>')

    att_imgs = ""
    att_files = ""
    for i, a in enumerate(atts):
        if is_image_name(a["name"]):
            fn = img(a["path"], f"att{i}")
            if fn:
                att_imgs += f'<figure><div class="ph"><img src="{fn}"></div><figcaption>{e(a["name"])}</figcaption></figure>'
        else:
            att_files += f"<li>{e(a['name'])}</li>"

    def ev_rows(done):
        rows = ""
        for ev in evs:
            if bool(ev["done"]) != done or (not done and ev["cancelled"]):
                continue
            when = f"{ev['date']} {ev['time'] or ''}".strip()
            extra = f"<td>{e((ev['done_at'] or '')[:16].replace('T', ' '))}</td><td>{e(ev['notes'])}</td>" if done else ""
            rows += f"<tr><td>{KIND_AR[ev['kind']]}</td><td>{when}</td>{extra}</tr>"
        return rows

    done_rows, pend_rows = ev_rows(True), ev_rows(False)
    field = lambda label, val: f'<div class="f"><span>{label}</span><b>{e(val)}</b></div>'
    doc = f"""<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ملف المريض {e(p['full_name'])}</title>
<style>
{_css()}
</style></head><body>
<div class="bar"><button onclick="window.print()">🖨️ طباعة / حفظ PDF</button></div>
<div class="page">
<header><h1>{APP_NAME} — ملف مريض</h1><small>تاريخ الطباعة: {today()}</small></header>
<div class="head"><h2>{e(p['full_name'])}</h2><span class="tag">الكود: {e(p['code'])}</span><span class="tag">الحالة: {e(p['status'])}</span></div>
<h3>البيانات الشخصية</h3>
<div class="grid">{field('الجنس', p['gender'])}{field('العمر', p['age'])}{field('مكان السكن', p['residence'])}
{field('رقم التواصل', p['phone'])}{field('العمل', p['job'])}{field('زمرة الدم', p['blood'])}
<div class="f full"><span>الأمراض</span><b>{e(p['diseases'])}</b></div>
<div class="f full"><span>الحساسية</span><b>{e(p['allergies'])}</b></div>
<div class="f full"><span>الأدوية الحالية</span><b>{e(p['medications'])}</b></div>
<div class="f full"><span>التشخيص</span><b>{e(p['diagnosis'])}</b></div>
<div class="f full"><span>ملاحظات</span><b>{e(p['notes'])}</b></div>
{field('تاريخ التسجيل', (p['created_at'] or '')[:10])}</div>
<h3>الصور</h3><div class="photos">{photo_html}</div>
{('<h3>قبل وبعد</h3>' + pairs_html) if pairs_html else ''}
{('<h3>مرفقات مصوّرة</h3><div class="photos">' + att_imgs + '</div>') if att_imgs else ''}
{('<h3>ملفات مرفقة</h3><ul>' + att_files + '</ul>') if att_files else ''}
<h3>سجل العمليات والمراجعات المؤكدة</h3>
{('<table><tr><th>النوع</th><th>الموعد</th><th>تم الإنجاز</th><th>ملاحظات</th></tr>' + done_rows + '</table>') if done_rows else '<p>لا يوجد سجل مؤكد.</p>'}
{('<h3>المواعيد القادمة</h3><table><tr><th>النوع</th><th>الموعد</th></tr>' + pend_rows + '</table>') if pend_rows else ''}
<footer>تم إنشاء هذا التقرير بواسطة تطبيق {APP_NAME} — {datetime.now():%Y-%m-%d %H:%M}</footer>
</div></body></html>"""
    with open(os.path.join(folder, "report.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    return share_url(token, "report.html")


def build_fin_report(pid):
    """الملف المالي للمريض (تقرير منفصل عن ملف المريض): الإجراءات وتكاليفها والمدفوع والمتبقي بالعملتين."""
    p = q("SELECT * FROM patients WHERE id=?", (pid,), one=True)
    entries, tdue, tpaid, trem = fin_file(pid)
    folder, token = new_share_dir()
    e = lambda v: html.escape(str(v)) if v not in (None, "") else "—"
    lines = lambda d, neg=False: "<br>".join(money(d[c], c) for c in CURS if round(d[c], 2) != 0) or "0"
    cls = lambda d: "neg" if any(v > 0 for v in d.values()) else "pos"
    rows = ""
    pay_rows = ""
    for en in sorted(entries, key=lambda z: (z["ev"]["date"], z["ev"]["time"] or "")):
        ev = en["ev"]
        items = "".join(f"<li><span>{e(i['name'])}</span><b>{money(i['price'], i['cur'])}</b></li>"
                        for i in en["items"]) or "—"
        when = f"{ev['date']} {ev['time'] or ''}".strip()
        rows += (f"<tr><td class='n'>{when}</td><td>{KIND_AR[ev['kind']]}</td><td><ul class='it'>{items}</ul></td>"
                 f"<td class='n'>{lines(en['due'])}</td><td class='n'>{lines(en['paid'])}</td>"
                 f"<td class='n {cls(en['rem'])}'>{lines(en['rem'])}</td></tr>")
        for pay in en["pays"]:
            pay_rows += (f"<tr><td class='n'>{e((pay['paid_at'] or '')[:10])}</td><td>{KIND_AR[ev['kind']]} — {ev['date']}</td>"
                         f"<td class='n'>{money(pay['amount'], pay['cur'])}</td><td>{e(pay['note'])}</td></tr>")
    box = lambda label, d, klass="": f'<div class="box"><span>{label}</span><b class="{klass}">{lines(d)}</b></div>'
    doc = f"""<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>الملف المالي {e(p['full_name'])}</title>
<style>{_css()}</style></head><body>
<div class="bar"><button onclick="window.print()">🖨️ طباعة / حفظ PDF</button></div>
<div class="page">
<header><h1>{APP_NAME} — الملف المالي</h1><small>تاريخ الطباعة: {today()}</small></header>
<div class="head"><h2>{e(p['full_name'])}</h2><span class="tag">الكود: {e(p['code'])}</span></div>
<div class="sum">{box('إجمالي المستحق', tdue)}{box('إجمالي المدفوع', tpaid)}{box('المتبقي', trem, cls(trem))}</div>
<h3>الإجراءات والتكاليف</h3>
{('<table><tr><th>الموعد</th><th>النوع</th><th>الإجراءات (التكلفة)</th><th>المستحق</th><th>المدفوع</th><th>المتبقي</th></tr>' + rows + f'<tfoot><tr><td colspan="3">الإجمالي</td><td class="n">{lines(tdue)}</td><td class="n">{lines(tpaid)}</td><td class="n">{lines(trem)}</td></tr></tfoot></table>') if rows else '<p>لا توجد مواعيد أو إجراءات مسجّلة.</p>'}
{('<h3>سجل الدفعات</h3><table><tr><th>التاريخ</th><th>الموعد</th><th>المبلغ</th><th>ملاحظة</th></tr>' + pay_rows + '</table>') if pay_rows else ''}
<footer>تم إنشاء هذا التقرير بواسطة تطبيق {APP_NAME} — {datetime.now():%Y-%m-%d %H:%M}</footer>
</div></body></html>"""
    with open(os.path.join(folder, "finance.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    return share_url(token, "finance.html")


# ───────────────────────── الجدول اليومي وكشف التعارض ─────────────────────────
def ev_span(ev):
    """(بداية, نهاية) موعد كـ datetime."""
    start = ev_dt(ev)
    dur = ev["duration_min"] if ev["duration_min"] else DEFAULT_DURATION.get(ev["kind"], 30)
    return start, start + timedelta(minutes=int(dur))


def event_conflicts(date_s, time_s, duration, exclude_id=None):
    """المواعيد الفعّالة (غير الملغاة/«لم يحضر») التي تتداخل مع [الوقت, الوقت+المدة] في اليوم نفسه."""
    start = datetime.strptime(f"{date_s} {time_s or DEFAULT_TIME}", "%Y-%m-%d %H:%M")
    end = start + timedelta(minutes=int(duration))
    out = []
    for r in q("""SELECT e.*, p.full_name FROM events e JOIN patients p ON p.id=e.patient_id
                  WHERE e.date=? AND COALESCE(e.cancelled,0)=0 AND e.id IS NOT ?""", (date_s, exclude_id)):
        s0, e0 = ev_span(r)
        if start < e0 and s0 < end:
            out.append(r)
    return out


def event_status(ev, now=None):
    """'done' | 'no_show' | 'cancelled' | 'late' (معلّق فات وقته) | 'pending'"""
    if ev["done"]:
        return "done"
    if ev["cancelled"]:
        return "no_show" if ev["no_show"] else "cancelled"
    return "late" if ev_dt(ev) < (now or datetime.now()) else "pending"


def day_schedule(date_s):
    """جدول يوم: قائمة مرتبة بالوقت من {ev, start, end, status, conflicts:[ids]}. التعارض بين المواعيد الفعّالة فقط."""
    rows = q("""SELECT e.*, p.full_name, p.code, p.phone FROM events e JOIN patients p ON p.id=e.patient_id
                WHERE e.date=?""", (date_s,))
    items = []
    for r in rows:
        s0, e0 = ev_span(r)
        items.append(dict(ev=r, start=s0, end=e0, status=event_status(r), conflicts=[]))
    items.sort(key=lambda z: (z["start"], z["ev"]["id"]))
    active = [i for i in items if i["status"] not in ("cancelled", "no_show")]
    for a in active:
        a["conflicts"] = [b["ev"]["id"] for b in active if b is not a and a["start"] < b["end"] and b["start"] < a["end"]]
    return items


def day_counts(first_date, days=7):
    """{تاريخ: عدد المواعيد الفعّالة} لشريط الأسبوع."""
    d0 = datetime.strptime(first_date, "%Y-%m-%d")
    dates = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    cnt = dict.fromkeys(dates, 0)
    for r in q("SELECT date, COUNT(*) FROM events WHERE date BETWEEN ? AND ? AND COALESCE(cancelled,0)=0 GROUP BY date",
               (dates[0], dates[-1])):
        cnt[r[0]] = r[1]
    return cnt


def mark_no_show(event_id, reason=""):
    """«لم يحضر»: يُغلق موعداً معلّقاً فات وقته. يُخزَّن كموعد ملغى بعلم no_show فلا يدخل المستحقات ولا المواعيد القريبة،
    ويمكن استعادته. يُرفض إن لم يحن وقته، أو كان مؤكَّداً، أو عليه دفعات."""
    now = datetime.now()
    with closing(db()) as c, c:
        row = c.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise ValueError("الموعد غير موجود")
        if row["done"]:
            raise ValueError("لا يمكن تسجيل «لم يحضر» لموعد مؤكَّد الإنجاز")
        if row["cancelled"]:
            raise ValueError("هذا الموعد ملغى أو مسجَّل «لم يحضر» سابقاً")
        if ev_dt(row) > now:
            raise ValueError("لم يحن وقت هذا الموعد بعد")
        if c.execute("SELECT 1 FROM payments WHERE event_id=? LIMIT 1", (event_id,)).fetchone():
            raise ValueError("على هذا الموعد دفعات مسجّلة. احذفها أو عدّلها أولاً من «الحسابات».")
        c.execute("UPDATE events SET cancelled=1, no_show=1, cancelled_at=?, cancel_reason=? WHERE id=?",
                  (now.isoformat(timespec="seconds"), (reason or "").strip() or "لم يحضر", event_id))


# ───────────────────────── تعديل وحذف ─────────────────────────
def ensure_recent_backup(max_hours=24):
    """قبل أي حذف نهائي: نسخة احتياطية حديثة (آخر 24 ساعة) أو تُؤخذ الآن. يعيد مسارها أو None إن كانت حديثة."""
    names = list_backups()
    if names and time.time() - os.path.getmtime(os.path.join(BK_DIR, names[0])) < max_hours * 3600:
        return None
    return make_backup()


def _commit_then(c, after):
    """يثبّت معاملة المستدعي ويحفظ القاعدة ثم ينفّذ after() (محو الملفات) فقط بعد نجاح الحفظ."""
    c.commit_mem()
    _persist()
    after()


def patient_delete_summary(pid):
    """ما سيُحذف مع المريض (لحوار التأكيد)."""
    p = q("SELECT * FROM patients WHERE id=?", (pid,), one=True)
    if not p:
        raise ValueError("المريض غير موجود")
    evs = q("SELECT id, done, COALESCE(cancelled,0) AS cancelled FROM events WHERE patient_id=?", (pid,))
    paid_m = {c: 0 for c in CURS}
    for r in q("""SELECT pm.amount_minor, pm.cur FROM payments pm JOIN events e ON e.id=pm.event_id WHERE e.patient_id=?""", (pid,)):
        paid_m[r["cur"]] += r["amount_minor"]
    paid = {c: from_minor(v) for c, v in paid_m.items()}
    due, _, rem = fin_totals(pid)
    photos = sum(1 for k in ("photo_before", "photo_after", "photo_lab") if p[k]) + \
        q("SELECT COUNT(*) FROM events WHERE patient_id=? AND photo_before IS NOT NULL", (pid,), one=True)[0] + \
        q("SELECT COUNT(*) FROM events WHERE patient_id=? AND photo_after IS NOT NULL", (pid,), one=True)[0]
    return dict(name=p["full_name"], code=p["code"], events=len(evs), done=sum(1 for e in evs if e["done"]),
                attachments=q("SELECT COUNT(*) FROM attachments WHERE patient_id=?", (pid,), one=True)[0],
                photos=photos, paid=paid, remaining=rem)


def delete_patient(pid):
    """حذف نهائي للمريض وكل ما يخصه (مواعيد، إجراءات، دفعات، مرفقات، صور) بمعاملة واحدة، ثم محو الملفات بعد نجاح الحفظ.
    يأخذ نسخة احتياطية حديثة أولاً إن لم توجد."""
    p = q("SELECT * FROM patients WHERE id=?", (pid,), one=True)
    if not p:
        raise ValueError("المريض غير موجود")
    ensure_recent_backup()
    rels = {p[k] for k in ("photo_before", "photo_after", "photo_lab") if p[k]}
    rels |= {a["path"] for a in q("SELECT path FROM attachments WHERE patient_id=?", (pid,)) if a["path"]}
    for e in q("SELECT photo_before, photo_after FROM events WHERE patient_id=?", (pid,)):
        rels |= {e[k] for k in ("photo_before", "photo_after") if e[k]}
    code, committed = p["code"], False
    c = db()
    try:
        sub = "(SELECT id FROM events WHERE patient_id=?)"
        c.execute(f"DELETE FROM payments WHERE event_id IN {sub}", (pid,))
        c.execute(f"DELETE FROM event_items WHERE event_id IN {sub}", (pid,))
        c.execute("DELETE FROM events WHERE patient_id=?", (pid,))
        c.execute("DELETE FROM attachments WHERE patient_id=?", (pid,))
        c.execute("DELETE FROM patients WHERE id=?", (pid,))
        c.commit_mem()
        committed = True
        _persist()
    except BaseException as ex:
        if not committed:
            c.rollback()
        LOG.log_exc("delete_patient", ex, committed=committed)
        raise
    finally:
        c.close()
    for rel in rels:
        _wipe_rel(rel)
    folder = os.path.join(PAT_DIR, safe(code or ""))
    if code and os.path.isdir(folder):
        for fn in os.listdir(folder):
            _wipe_file(os.path.join(folder, fn))
        shutil.rmtree(folder, ignore_errors=True)
    LOG.log("patient_deleted", files=len(rels))


def delete_event(event_id):
    """حذف موعد نهائياً (وإجراءاته وصوره). يُرفض إن كانت عليه دفعات (احذفها أولاً من «الحسابات»)."""
    ev = q("SELECT * FROM events WHERE id=?", (event_id,), one=True)
    if not ev:
        raise ValueError("الموعد غير موجود")
    if q("SELECT 1 FROM payments WHERE event_id=? LIMIT 1", (event_id,)):
        raise ValueError("على هذا الموعد دفعات مسجّلة. احذفها أولاً من «الحسابات» ثم احذف الموعد.")
    ensure_recent_backup()
    rels = [ev[k] for k in ("photo_before", "photo_after") if ev[k]]
    c = db()
    committed = False
    try:
        c.execute("DELETE FROM event_items WHERE event_id=?", (event_id,))
        c.execute("DELETE FROM events WHERE id=?", (event_id,))
        c.commit_mem()
        committed = True
        _persist()
    except BaseException:
        if not committed:
            c.rollback()
        raise
    finally:
        c.close()
    for rel in rels:
        _wipe_rel(rel)


def delete_attachment(att_id):
    a = q("SELECT * FROM attachments WHERE id=?", (att_id,), one=True)
    if not a:
        raise ValueError("المرفق غير موجود")
    x("DELETE FROM attachments WHERE id=?", (att_id,))
    _wipe_rel(a["path"])                              # بعد نجاح الحذف من القاعدة


def rename_attachment(att_id, name):
    name = " ".join((name or "").replace("/", " ").replace("\\", " ").split())[:120]
    if not name:
        raise ValueError("اسم المرفق فارغ")
    old = q("SELECT name FROM attachments WHERE id=?", (att_id,), one=True)
    if not old:
        raise ValueError("المرفق غير موجود")
    if "." not in name and "." in (old["name"] or ""):          # نحافظ على الامتداد (يحدّد طريقة الفتح)
        name += "." + old["name"].rsplit(".", 1)[1]
    x("UPDATE attachments SET name=? WHERE id=?", (name, att_id))
    return name


def clear_patient_photo(pid, key):
    if key not in ("photo_before", "photo_after", "photo_lab"):
        raise ValueError("key")
    p = q("SELECT * FROM patients WHERE id=?", (pid,), one=True)
    if not p:
        raise ValueError("المريض غير موجود")
    x(f"UPDATE patients SET {key}=NULL WHERE id=?", (pid,))
    _wipe_rel(p[key])


def clear_event_photo(event_id, which):
    if which not in ("before", "after"):
        raise ValueError("which")
    ev = q("SELECT * FROM events WHERE id=?", (event_id,), one=True)
    if not ev:
        raise ValueError("الموعد غير موجود")
    x(f"UPDATE events SET photo_{which}=NULL WHERE id=?", (event_id,))
    _wipe_rel(ev[f"photo_{which}"])


# ───────────────────────── تحسين الصور الموجودة ─────────────────────────
OPT_MIN_BYTES = 300_000          # لا نعالج الصور الأصغر من هذا (لا فائدة تُذكر)


def images_to_optimize():
    """مراجع صور مخزّنة كبيرة وبلا مصغّرة (من إصدارات قبل 2.5). فارغة إن لم تتوفر مكتبة الصور."""
    if not IMG.PIL_OK or not VAULT.unlocked:
        return []
    rels = set()
    for sql in ("SELECT photo_before FROM patients", "SELECT photo_after FROM patients",
                "SELECT photo_lab FROM patients", "SELECT photo_before FROM events", "SELECT photo_after FROM events"):
        rels.update(r[0] for r in q(sql) if r[0])
    rels.update(r["path"] for r in q("SELECT path, name FROM attachments") if is_image_name(r["name"]))
    return sorted(r for r in rels if os.path.isfile(ap(r)) and file_size(r) > OPT_MIN_BYTES
                  and not os.path.isfile(ap(thumb_rel(r))))


def optimize_images(progress=None):
    """يصغّر الصور القديمة وينشئ مصغّراتها في مكانها (الاسم نفسه فلا تتغير القاعدة). يأخذ نسخة احتياطية أولاً.
    كل ملف يُكتب ذرّياً؛ الانقطاع في المنتصف لا يفسد شيئاً. يعيد {'done':n,'saved':بايت,'failed':n}."""
    todo = images_to_optimize()
    if not todo:
        return {"done": 0, "saved": 0, "failed": 0}
    make_backup(prune=False)
    done = saved = failed = 0
    for i, rel in enumerate(todo, 1):
        try:
            data = read_file(rel)
            full, thumb = IMG.process(data)
            if thumb is None and full is data:
                failed += 1
            else:
                write_enc(rel, full)
                if thumb:
                    write_enc(thumb_rel(rel), thumb)
                saved += max(len(data) - len(full), 0)
                done += 1
        except Exception as ex:
            failed += 1
            LOG.log_exc("optimize_image", ex, file=os.path.basename(rel))
        if progress:
            progress(i, len(todo))
    _prune_backups()
    LOG.log("optimize_done", done=done, failed=failed, saved=saved)
    return {"done": done, "saved": saved, "failed": failed}


# ───────────────────────── التشخيص ─────────────────────────
def diagnostics() -> str:
    """تقرير نصّي لدعم العملاء: إصدارات، فحوص ذاتية وأزمنة على هذا الجهاز، حالة الترخيص والنسخ، آخر سطور السجل.
    لا يحوي أسماء مرضى ولا أرقاماً ولا اسم المستخدم."""
    import platform
    import selftest
    lines = [f"{APP_NAME} {APP_VERSION} — تقرير تشخيص {datetime.now():%Y-%m-%d %H:%M}",
             f"النظام: {sys.platform} {platform.machine()} | بايثون {platform.python_version()}"]
    fv = "?"
    try:
        from importlib.metadata import version as _ver
        fv = _ver("flet")
    except Exception:
        try:
            import importlib
            fv = importlib.import_module("flet.version").version     # استيراد ديناميكي: وحدات المنطق لا تستورد Flet ساكناً
        except Exception:
            pass
    lines.append(f"Flet: {fv}")
    lines.append(f"معالجة الصور: {'Pillow ' + IMG.PIL_VERSION if IMG.PIL_OK else 'غير متوفرة'}")
    st, days = lic_status()
    d = lic_load()
    lines += ["", "── الحالة ──", f"الترخيص: {st} ({days} يوم) | معرّف الجهاز: {d['device_id'].upper()}"]
    h = VAULT.h or {}
    lines.append(f"الحساب: دورات الاشتقاق={h.get('iter')} | مفتاح استرداد={'نعم' if VAULT.has_recovery_key else 'لا'} | "
                 f"اعتماد المدير={'نعم' if VAULT.escrow_enabled else 'لا'} | قفل={'نعم' if VAULT.locked_out else 'لا'}")
    sset = jload(SET_PATH, {})
    rep = backup_report()
    lines.append(f"آخر نسخة: {sset.get('last_backup', '—')[:19]}"
                 + ("" if list_backups() else " (لا ملف نسخة فعلياً بعد: لا مرضى لنسخهم)")
                 + f" | ملفات={rep['files']} متخطّاة={rep['skipped']} | "
                 f"آخر تصدير: {sset.get('last_export', '—')[:10]} | نسخ داخل الجهاز: {len(list_backups())}")
    n_files = sum(len(f) for _, _, f in os.walk(PAT_DIR))
    size = sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(PAT_DIR) for f in fs)
    lines.append(f"التخزين: db.enc={os.path.getsize(DB_ENC) if os.path.exists(DB_ENC) else 0} بايت | "
                 f"ملفات المرضى={n_files} ({size // 1024} كيلوبايت) | صور بلا مصغّرة تستحق التحسين: {len(images_to_optimize())}")
    try:
        t0 = time.perf_counter()
        with _lock:
            blob = _db_encode(_serialize(_mem["conn"]), _mem["gen"] + 1)
        lines.append(f"زمن حفظ القاعدة المشفّرة (تسلسل + تشفير): {(time.perf_counter() - t0) * 1000:.0f} مللي ثانية "
                     f"({len(blob) // 1024} كيلوبايت)")
    except Exception as ex:
        lines.append(f"زمن حفظ القاعدة: تعذّر ({type(ex).__name__})")
    lines += ["", "── الفحوص الذاتية على هذا الجهاز ──"]
    for name, ok, detail in selftest.run(BASE, VT.PBKDF2_ITER):
        lines.append(f"{'✓' if ok else '✗'} {name}" + (f" — {detail}" if detail else ""))
    lines += ["", "── آخر أحداث السجل (بلا رسائل ولا بيانات مرضى) ──", LOG.tail(80) or "(فارغ)"]
    return "\n".join(lines)


# ───────────────────────── تعافٍ عند الإقلاع ─────────────────────────
def module_mismatch() -> list:
    """أسماء الملفات التي من إصدار مختلف عن core.py (يحدث عند نسخ بعض ملفات الحزمة دون بقيتها)."""
    return [name for name, mod in (("vault.py", VT), ("license_core.py", LC))
            if getattr(mod, "BUILD", None) != APP_VERSION]


def _prune_pre_migration(days=30):
    """نسخ db.enc.pre_v* (قبل الترقية) تحوي بيانات قد يكون المستخدم حذفها لاحقاً: لا نُبقيها أكثر من days."""
    try:
        for fn in os.listdir(BASE):
            if ".pre_v" in fn and fn.startswith(os.path.basename(DB_ENC)):
                full = os.path.join(BASE, fn)
                if time.time() - os.path.getmtime(full) > days * 86400:
                    _wipe_file(full)
    except OSError:
        pass


def _startup_recovery():
    _prune_pre_migration()
    try:
        recover_interrupted_restore()
    except Exception as ex:
        LOG.log_exc("startup_recovery", ex)
    try:                                                    # نسخ احتياطية مقطوعة (انقطع التطبيق أثناء كتابتها)
        for fn in os.listdir(BK_DIR):
            if fn.endswith(BK_EXT + ".tmp"):
                os.remove(os.path.join(BK_DIR, fn))
    except OSError:
        pass


_startup_recovery()
