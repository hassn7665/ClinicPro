# -*- coding: utf-8 -*-
"""
storage.py — التخزين الأساسي: الثوابت والمسارات والحساب (VAULT) وقراءة/كتابة JSON ذرّياً وتشفير ملفات المرضى والصور.
"""
import base64
import calendar
import json
import os
import re
import secrets
import shutil
import threading
from datetime import datetime

import applog as LOG
import crypto_core as K
import images as IMG
import vault as VT


APP_NAME = "My Clinic"


APP_VERSION = "2.7.0"


BASE = os.getenv("FLET_APP_STORAGE_DATA") or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "myclinic_data")


DB_PATH = os.path.join(BASE, "myclinic.db")        # قاعدة قديمة غير مشفّرة (تُرحَّل عند إنشاء الحساب)


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


def digits(s) -> str:
    """الأرقام فقط (يحوّل الأرقام العربية والهندية)."""
    return re.sub(r"\D", "", (s or "").translate(_DIGITS)) if isinstance(s, str) else ""


def phone_key(s) -> str:
    """مفتاح مقارنة للهاتف: آخر 9 أرقام (يطابق 0944123456 مع +963944123456 و00963944123456)."""
    d = digits(s)
    return d[-9:] if len(d) >= 9 else d


_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬،", "01234567890123456789.,,")
