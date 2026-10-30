# -*- coding: utf-8 -*-
"""
tests/helpers.py — بيئة اختبار معزولة: مجلد بيانات مؤقت + مفاتيح تفعيل مؤقتة (لا تمسّ public_keys.py ولا بياناتك).
يجب استيراده قبل أي import لـ core:   from helpers import boot_core
"""
import importlib
import os
import secrets
import sys
import tempfile
import types

# كل وحدات التطبيق ذات الحالة (المسارات تُحسب عند الاستيراد من متغير البيئة): تُعاد تحميلها نظيفة لكل اختبار
PURGE = ("core", "storage", "db", "finance", "events", "patients", "media", "licensing", "backup", "accounts", "share",
         "reports", "diagnostics", "vault", "license_core", "applog", "images", "keygen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def boot_core(tag="t"):
    """يهيّئ BASE مؤقتاً ثم يستورد core نظيفاً ويعيده (مع مفاتيح عامة مؤقتة)."""
    tmp = tempfile.mkdtemp(prefix=f"clinic_{tag}_")
    os.environ["FLET_APP_STORAGE_DATA"] = tmp
    for m in [m for m in sys.modules if m in PURGE or m.startswith("gui")]:
        del sys.modules[m]
    import crypto_core as K
    import license_core as LC
    core = importlib.import_module("core")
    seed = secrets.token_bytes(32)
    box_priv, box_pub = K.x25519_keypair()
    LC.PK = types.SimpleNamespace(SIGN_PUB=K.ed_pub(seed).hex(), BOX_PUB=box_pub.hex())
    core._test_keys = (seed, box_priv)
    return core, tmp


def make_account(core, user="tester", password="Correct-Horse-9"):
    core.setup_account(user, password)
    return core


# ───────────────────────── أدوات اختبار الواجهة ─────────────────────────
def make_png(path, w=64, h=48):
    """ملف PNG صالح بلا اعتماد على Pillow (لاختبار المسار الافتراضي للبناء)."""
    import struct
    import zlib
    raw = b"".join(b"\x00" + bytes((30, 150, 140)) * w for _ in range(h))
    chunk = lambda t, d: struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return path


class FakePage:
    """بديل خفيف لـ ft.Page يكفي لبناء الشاشات دون واجهة رسومية. أي خاصية/دالة غير معرّفة تُهمَل بأمان."""

    def __init__(self, width=390):
        import flet as ft
        self.controls, self.overlay, self.opened = [], [], []
        self.width, self.height = width, 800
        self.platform = ft.PagePlatform.ANDROID
        self.appbar = self.bottom_appbar = None

    def add(self, *c):
        self.controls += list(c)

    def clean(self):
        self.controls = []

    def update(self, *a):
        pass

    def open(self, c):
        self.opened.append(c)

    def close(self, c):
        if c in self.opened:
            self.opened.remove(c)

    def launch_url(self, *a, **k):
        pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        from unittest.mock import MagicMock
        return MagicMock()


def seed_clinic(C):
    """بيانات تمثيلية: مريضان، مواعيد (معلّق/منجز/ملغى/لم يحضر)، إجراءات ودفعات بالعملتين، صورة ومرفق. يعيد (pid1, pid2)."""
    import datetime as dt
    tmp = os.environ["FLET_APP_STORAGE_DATA"]
    png, txt = make_png(os.path.join(tmp, "p.png")), os.path.join(tmp, "note.txt")
    with open(txt, "w") as f:
        f.write("hello")
    base = dict(gender="ذكر", age=33, residence="دمشق", phone="0944123456", job="مهندس", diseases="لا", notes="",
                blood="O+", status="جديد", allergies="بنسلين", medications="", diagnosis="x")
    p1 = C.save_patient(dict(base, full_name="أحمد علي"), {"photo_before": png}, [txt])
    p2 = C.save_patient(dict(base, full_name="سلمى حسن", status="قديم", phone="0955000111"), {}, [])
    day = lambda n: (dt.date.today() + dt.timedelta(days=n)).strftime("%Y-%m-%d")
    e1 = C.create_event(p1["id"], "visit", day(0), "23:30",
                        items=[("كشف", C.parse_money("1500"), "SYP"), ("دواء", C.parse_money("10.5"), "USD")])
    e2 = C.create_event(p1["id"], "surgery", day(-3), "10:00", items=[("عملية", C.parse_money("2000000"), "SYP")])
    C.add_payments(e2, [(C.parse_money("500000"), "SYP")])
    C.confirm_event(e2, "تمت", None, [])
    e3 = C.create_event(p1["id"], "visit", day(5), "09:00", items=[("x", C.parse_money("100"), "USD")])
    C.cancel_event(e3, "سبب")
    C.create_event(p2["id"], "visit", day(-1), "08:00")
    C.set_event_photo(e1, "before", png)
    d = C.lic_load()                                           # ترخيص ساري كي لا تُحوَّل الشاشة الرئيسية إلى التفعيل
    d["expires"] = (dt.datetime.now() + dt.timedelta(days=30)).isoformat()
    C._lic_save(d)
    return p1["id"], p2["id"]
