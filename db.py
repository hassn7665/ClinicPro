# -*- coding: utf-8 -*-
"""
db.py — قاعدة البيانات المشفّرة في الذاكرة: الاتصال، الحفظ المشفّر، الفتح/الإغلاق، q/x/db، وتهيئة المخطط (schema.py).
"""
import os
import sqlite3
import struct
from contextlib import closing

import applog as LOG
import crypto_core as K
import schema as SC

from storage import (
    BASE, DB_ENC, DB_PATH, NotUnlocked, SET_PATH,
    VAULT, VaultError, _atomic_write, _lock, _mem,
    _migrate_file_aad, _wipe_file, jload)


def _new_conn(blob: bytes | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    SC.harden(conn)
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
            SC.run_dump(conn, body.decode("utf-8"))                 # عبارات من قائمة بيضاء فقط
        else:
            raise ValueError("صيغة قاعدة بيانات غير معروفة")
        SC.validate_structure(conn)                                  # لا triggers ولا views ولا جداول غريبة
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _serialize(conn) -> bytes:
    if hasattr(conn, "serialize"):
        return b"\x01" + conn.serialize()
    ver = SC.get_version(conn)                       # iterdump لا يحفظ user_version: نضيفه صراحةً كي لا تُعاد ترقية قاعدة مرقّاة
    return b"\x02" + ("\n".join(conn.iterdump()) + f"\nPRAGMA user_version={ver};").encode("utf-8")


DB_MAGIC = b"MCD1"


class RollbackError(VaultError):
    """db.enc أقدم من آخر حفظ مسجّل: احتمال استبدال القاعدة بنسخة قديمة (أو استرجاع جزئي لملفات التطبيق)."""

    def __init__(self, got, expected):
        super().__init__("قاعدة البيانات أقدم من آخر حفظ مسجّل على هذا الجهاز (احتمال استبدالها بنسخة قديمة).")
        self.got, self.expected = got, expected


def _db_encode(plain: bytes, gen: int) -> bytes:
    """MCD1 ‖ gen(8) ‖ sealed(aad="db|"+gen): الجيل ظاهر لكنه مربوط بالمصادقة فلا يمكن تعديله دون كشف."""
    g = struct.pack(">Q", gen)
    return DB_MAGIC + g + K.seal(VAULT.dek, plain, aad=b"db|" + g)


def _db_decode(blob: bytes):
    """(الجيل, القاعدة). يقرأ الصيغة القديمة (MCF1, aad=db) كجيل 0."""
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


def open_db():
    """يفتح القاعدة المشفّرة بعد تسجيل الدخول (أو يهيّئ قاعدة جديدة، أو يرحّل قاعدة قديمة)."""
    if not VAULT.unlocked:
        raise NotUnlocked("سجّل الدخول أولاً")
    with _lock:
        if _mem["conn"] is not None:
            return
        raw_enc = None
        if os.path.exists(DB_ENC):
            with open(DB_ENC, "rb") as f:
                raw_enc = f.read()
                gen, plain = _db_decode(raw_enc)
            if gen < VAULT.dbgen:
                if not _mem["accept_rollback"]:
                    raise RollbackError(gen, VAULT.dbgen)
                LOG.log("rollback_accepted", got=gen, expected=VAULT.dbgen)
                VAULT.set_dbgen(gen)         # قرار المستخدم الصريح: نعتمد القاعدة الحالية أساساً جديداً
            _mem["gen"] = gen
            _mem["conn"] = _new_conn(plain)
        else:
            _mem["conn"] = _new_conn()
            if os.path.exists(DB_PATH):             # ترحيل قاعدة الإصدارات السابقة
                with closing(sqlite3.connect(DB_PATH)) as src:
                    src.backup(_mem["conn"])
                _mem["conn"].row_factory = sqlite3.Row
                _mem["conn"].execute("PRAGMA foreign_keys=ON")
        try:
            rep = init_db()
            if rep["applied"] and raw_enc:                  # نسخة أمان من الملف المشفّر كما كان قبل أول ترقية للمخطط
                _atomic_write(DB_ENC + f".pre-v{rep['to']}", raw_enc)
            _persist()
        except BaseException:                               # فشل الترقية/الحفظ: لا نترك اتصالاً نصف مرقّى مفتوحاً
            try:
                _mem["conn"].close()
            except sqlite3.Error as ex:
                LOG.log_exc("open_db_close", ex)
            _mem["conn"] = None
            raise
        _migrate_file_aad()


def close_db():
    with _lock:
        if _mem["conn"] is not None:
            try:
                _persist()                       # آخر حفظ قبل الإغلاق: فشله يُسجَّل ولا يمنع القفل (الحفظ السابق سليم)
            except Exception as ex:
                LOG.log_exc("close_db_persist", ex)
            try:
                _mem["conn"].close()
            except sqlite3.Error as ex:
                LOG.log_exc("close_db_close", ex)
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


def init_db() -> dict:
    """يرقّي مخطط القاعدة المفتوحة إلى آخر إصدار (PRAGMA user_version؛ التفاصيل في schema.py).
    يعيد تقرير الترقية {'from','to','applied','sanitized'}. على المستدعي أن يستدعي _persist() بعدها."""
    with _lock:
        conn = _mem["conn"]
        if conn is None:
            raise NotUnlocked("البيانات مقفلة. سجّل الدخول.")
        legacy = "USD" if str(jload(SET_PATH, {}).get("currency") or "").strip().upper() in ("$", "USD", "دولار") else "SYP"
        rep = SC.migrate(conn, legacy)
        if rep["applied"]:
            LOG.log("schema_migrated", frm=rep["from"], to=rep["to"])
            for k, n in sorted(rep["sanitized"].items()):
                LOG.log("schema_sanitized", what=k.replace(".", "_"), rows=n)
        return rep


# ───────────────────────── قراءة/كتابة للواجهة (الواجهة لا تكتب SQL أبداً) ─────────────────────────
def get_patient(pid):
    """صف المريض أو None."""
    return q("SELECT * FROM patients WHERE id=?", (pid,), one=True)


def patient_events(pid):
    """كل مواعيد المريض مرتبة زمنياً."""
    return q("SELECT * FROM events WHERE patient_id=? ORDER BY date,time", (pid,))


def patient_attachments(pid):
    return q("SELECT * FROM attachments WHERE patient_id=?", (pid,))


def set_event_in_report(event_id, flag):
    """إدراج صور الموعد (قبل/بعد) في الملف المطبوع أو إخراجها منه."""
    x("UPDATE events SET in_report=? WHERE id=?", (1 if flag else 0, event_id))


def _commit_then(c, after):
    """يثبّت معاملة المستدعي ويحفظ القاعدة ثم ينفّذ after() (محو الملفات) فقط بعد نجاح الحفظ."""
    c.commit_mem()
    _persist()
    after()
