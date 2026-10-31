# -*- coding: utf-8 -*-
"""
applog.py — سجل أخطاء محلي دوّار لتشخيص المشاكل عند العملاء، **بلا أي بيانات مرضى**.

قاعدة التصميم: لا تُسجَّل رسائل الاستثناءات (قد تحوي اسماً أو رقماً أو مساراً)، بل فقط: اسم الموضع، نوع الاستثناء،
وسلسلة الاستدعاء (ملف:سطر:دالة)، وحقول بسيطة تمرّرها الشيفرة نفسها (أرقام/أسماء ملفات معتمة). حجم السجل محدود
(3 ملفات × 200 كيلوبايت). لا يُرسَل إلى أي مكان؛ يخرج فقط عندما يصدّر المستخدم «تقرير التشخيص».
"""
import logging
import logging.handlers
import os
import re
import sys
import threading
import traceback

_state = {"logger": None, "path": None}
MAX_BYTES, BACKUPS = 200_000, 2


def init(log_dir: str):
    """يهيّئ السجل داخل log_dir (آمن للاستدعاء أكثر من مرة)."""
    try:
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "app.log")
        lg = logging.getLogger("myclinic")
        lg.setLevel(logging.INFO)
        lg.propagate = False
        for h in list(lg.handlers):
            lg.removeHandler(h)
            h.close()
        h = logging.handlers.RotatingFileHandler(path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8")
        h.setFormatter(logging.Formatter("%(asctime)s %(message)s", "%Y-%m-%d %H:%M:%S"))
        lg.addHandler(h)
        _state.update(logger=lg, path=path)
    except OSError:
        _state.update(logger=None, path=None)


def _fields(kw) -> str:
    ok = lambda v: isinstance(v, (int, float, bool)) or (          # أرقام، أو نصوص ASCII قصيرة (أسماء ملفات معتمة) فقط
        isinstance(v, str) and v.isascii() and len(v) <= 40 and v.replace("_", "").replace("-", "").replace(".", "").isalnum())
    return " ".join(f"{k}={v}" for k, v in kw.items() if ok(v))


def log(event: str, **kw):
    """حدث بلا استثناء. القيم النصية المسموحة: قصيرة وأبجدية-رقمية فقط (تُتجاهل الباقية)."""
    lg = _state["logger"]
    if lg:
        try:
            lg.info(f"[{event}] {_fields(kw)}".rstrip())
        except Exception:
            pass


def safe_text(text, limit: int = 200) -> str:
    """نصّ تشخيصي منقّى: ASCII مطبوع فقط (يُسقط العربية فلا يتسرّب اسم/ملاحظة)، والأرقام الطويلة (هاتف/رقم) → #."""
    s = "".join(ch for ch in str(text or "") if ch.isascii() and (ch.isprintable() or ch in "\n\t"))
    s = re.sub(r"\d{4,}", "#", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:limit]


def log_text(event: str, text):
    """حدث مع نصّ خارجي (مثل رسالة خطأ من واجهة Flutter) بعد تنقيته."""
    lg = _state["logger"]
    if lg:
        try:
            lg.error(f"[{event}] {safe_text(text)}")
        except Exception:
            pass


class _ExcHandler(logging.Handler):
    """يلتقط أي استثناء تسجّله المكتبات عبر logging (Flet/asyncio تضع أخطاء المعالجات في Future ولا تمرّرها لـ excepthook)."""

    def emit(self, record):
        try:
            if record.exc_info and record.exc_info[1] is not None and not record.name.startswith("myclinic"):
                log_exc("log_" + record.name.split(".")[0], record.exc_info[1])
        except Exception:
            pass


def frames(tb) -> str:
    out = []
    for fr in traceback.extract_tb(tb)[-6:]:
        out.append(f"{os.path.basename(fr.filename)}:{fr.lineno}:{fr.name}")
    return " > ".join(out)


def log_exc(where: str, ex: BaseException | None = None, **kw):
    """يسجّل نوع الاستثناء ومواضعه فقط (دون رسالته)."""
    lg = _state["logger"]
    if not lg:
        return
    try:
        ex = ex or sys.exc_info()[1]
        if ex is None:
            return log(where, **kw)
        code = f" errno={ex.errno}" if isinstance(ex, OSError) and ex.errno is not None else ""
        lg.error(f"[{where}] {type(ex).__name__}{code} @ {frames(ex.__traceback__)} {_fields(kw)}".rstrip())
    except Exception:
        pass


def install_hooks():
    """يلتقط الاستثناءات غير المعالجة (في الخيط الرئيسي وفي خيوط Flet) دون كسر السلوك الافتراضي."""
    if _state.get("hooked"):
        return
    _state["hooked"] = True
    prev_sys, prev_thr = sys.excepthook, getattr(threading, "excepthook", None)

    def _sys_hook(et, ev, tb):
        log_exc("uncaught", ev)
        prev_sys(et, ev, tb)

    def _thr_hook(args):
        log_exc("uncaught_thread", args.exc_value)
        if prev_thr:
            prev_thr(args)
    sys.excepthook = _sys_hook
    h = _ExcHandler(level=logging.ERROR)
    logging.getLogger().addHandler(h)
    if prev_thr:
        threading.excepthook = _thr_hook


def tail(n: int = 120) -> str:
    """آخر n سطراً من السجل (الملف الحالي ثم السابق إن لزم)."""
    path = _state["path"]
    if not path:
        return ""
    lines = []
    for p in (path + ".1", path):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                lines += f.read().splitlines()
        except OSError:
            pass
    return "\n".join(lines[-n:])
