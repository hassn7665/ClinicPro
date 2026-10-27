# -*- coding: utf-8 -*-
"""
اختبار دخاني آلي لـ Clinic Pro (بدون هاتف ولا نافذة): يبني الواجهة على «صفحة وهمية»، ويمرّ على كل الشاشات
والأزرار ويتحقق من تدفقات أساسية (دخول، إضافة مريض، تأكيد/إلغاء موعد، المستحقات، التقارير).
التشغيل:   python tests/test_smoke.py          (أو run_tests.bat)
يعمل على نسخة مؤقتة من المشروع، فلا يمسّ مفاتيحك ولا بياناتك.
"""
import datetime as dt
import os
import shutil
import sys
import tempfile
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="clinicpro_test_")
shutil.copytree(ROOT, os.path.join(WORK, "app"), ignore=shutil.ignore_patterns(
    "admin_keys.json", "issued_log.json", "__pycache__", "shifa_data", "tests", ".git"))
APP = os.path.join(WORK, "app")
os.environ["FLET_APP_STORAGE_DATA"] = os.path.join(WORK, "data")
sys.path.insert(0, APP)
os.chdir(APP)
open(os.path.join(APP, "public_keys.py"), "w").write('SIGN_PUB = ""\nBOX_PUB = ""\n')   # مفاتيح اختبار جديدة

import flet as ft                                   # noqa: E402
ft.Control.update = lambda self, *a, **k: None
ft.FilePicker.pick_files = lambda self, *a, **k: None
import keygen                                       # noqa: E402
keygen.ensure_keys()
import license_core                                 # noqa: E402
license_core.reload_keys()
import core as C                                    # noqa: E402
C.LC.reload_keys()
import main as M                                    # noqa: E402
M.time.sleep = lambda *_: None

FAILS = []


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        FAILS.append(name)


class Ev:
    def __init__(s, c=None):
        s.control, s.files, s.data = c, None, None


class FakePage:
    def __init__(s, w=390, h=800):
        s.controls, s.overlay, s.opened, s.launched = [], [], [], []
        s.width, s.height, s.appbar, s.bottom_appbar, s.theme, s.fonts = w, h, None, None, None, None
        s.platform, s.bgcolor, s.title = ft.PagePlatform.ANDROID, None, ""

    def clean(s): s.controls.clear()
    def add(s, *c): s.controls.extend(c)
    def update(s, *a): pass
    def open(s, c): s.opened.append(c)
    def close(s, c): pass
    def set_clipboard(s, v): pass
    def get_clipboard(s): return ""
    def launch_url(s, u): s.launched.append(u)


def kids(c):
    out = []
    for a in ("controls", "content", "leading", "actions", "title"):
        v = getattr(c, a, None)
        if v is None:
            continue
        out += list(v) if isinstance(v, (list, tuple)) else [v]
    return [k for k in out if hasattr(k, "_get_control_name")]


def walk(c, acc):
    acc.append(c)
    for k in kids(c):
        walk(k, acc)
    return acc


def tree(pg):
    acc = []
    for c in pg.controls:
        walk(c, acc)
    for extra in (pg.appbar, pg.bottom_appbar):
        if extra:
            walk(extra, acc)
    return acc


texts = lambda c: [t.value for t in walk(c, []) if isinstance(t, ft.Text)]


def find(pg, label, n=0):
    return [c for c in tree(pg) if getattr(c, "on_click", None) and label in " ".join(texts(c))][n]


def login(pg):
    f = [c for c in tree(pg) if isinstance(c, ft.TextField)]
    f[0].value, f[1].value = "tester", "Pass#Word2026x"
    find(pg, "دخول").on_click(Ev())


def boot(w=390):
    pg = FakePage(w, 800)
    M.main(pg)
    login(pg)
    return pg


def main():
    d = C.lic_load()
    ok, _ = C.lic_activate(keygen.issue_activation(d["device_id"], 12, None, "test")["code"])
    check("تفعيل الترخيص بكود موقّع", ok)
    C.setup_account("tester", "Pass#Word2026x")
    check("إنشاء الحساب وفتح الخزنة", C.VAULT.unlocked)
    img = tempfile.mktemp(suffix=".jpg")
    open(img, "wb").write(b"\xff\xd8x")
    p = C.save_patient(dict(full_name="سارة أحمد خليل", gender="أنثى", age=28, residence="حلب", phone="0944", job="معلمة",
                            diseases="لا", notes="", blood="A+", status="جديد"), {"photo_before": img}, [img])
    now = dt.datetime.now()
    C.create_event(p["id"], "visit", (now + dt.timedelta(hours=5)).strftime("%Y-%m-%d"), (now + dt.timedelta(hours=5)).strftime("%H:%M"))
    ev_surg = C.create_event(p["id"], "surgery", (now + dt.timedelta(days=3)).strftime("%Y-%m-%d"), "10:00",
                             items=[("عملية", 500, "USD")])

    # ── كل الشاشات بعرضين (عادي وضيق 320) بلا أخطاء ──
    for width in (390, 320):
        pg = boot(width)
        errors, screens = [], set()

        def crawl(depth):
            if depth == 0:
                return
            snap, ab, bb = list(pg.controls), pg.appbar, pg.bottom_appbar
            for i, c in enumerate([c for c in tree(pg) if getattr(c, "on_click", None)]):
                try:
                    c.on_click(Ev(c))
                except Exception:
                    errors.append(traceback.format_exc().splitlines()[-1])
                if not C.VAULT.unlocked:
                    C.unlock("tester", "Pass#Word2026x")
                if pg.controls != snap:
                    key = ((pg.appbar.title.value if pg.appbar and pg.appbar.title else "home"), len(tree(pg)))
                    if key not in screens:
                        screens.add(key)
                        crawl(depth - 1)
                    pg.controls[:], pg.appbar, pg.bottom_appbar = snap, ab, bb
        crawl(3)
        check(f"زحف على كل الشاشات (عرض {width}) بلا أخطاء", not errors, f"{len(screens)} شاشة {errors[:2]}")

    # ── إضافة مريض عبر النموذج ──
    pg = boot()
    col = [x for x in tree(pg) if isinstance(x, ft.Column) and x.width == 76 and "إضافة مريض" in " ".join(texts(x))][0]
    col.controls[0].on_click(Ev())
    tf = [c for c in tree(pg) if isinstance(c, ft.TextField)]
    before = C.q("select count(*) from patients")[0][0]
    tf[0].value = "خالد يوسف حسن"
    submit = [c for c in tree(pg) if getattr(c, "on_click", None) and "إضافة" in " ".join(texts(c)) and "مرفقات" not in " ".join(texts(c))][-1]
    submit.on_click(Ev())
    check("حفظ مريض جديد من النموذج", C.q("select count(*) from patients")[0][0] == before + 1)

    # ── إلغاء/استعادة الموعد والحسابات ──
    check("الموعد القادم يظهر قبل الإلغاء", len(C.upcoming_events(30)[1]) >= 2)
    due0 = C.fin_totals(p["id"])
    C.cancel_event(ev_surg, "اختبار")
    check("الموعد الملغى يختفي من القريبة", len(C.upcoming_events(30)[1]) == 1)
    check("الموعد الملغى لا يُحتسب في المستحق", C.fin_totals(p["id"])[0]["USD"] == 0 and due0[0]["USD"] == 500)
    s = C.stats()
    check("الإحصاء: ملغاة=1 والمعلّقة لا تشمله", s["cancelled"] == 1 and s["pending"] == 1)
    for name, fn in (("تأكيد", lambda: C.confirm_event(ev_surg, "x")),
                     ("إلغاء ثانٍ", lambda: C.cancel_event(ev_surg))):
        try:
            fn()
            check(f"رفض {name} لموعد ملغى", False)
        except ValueError:
            check(f"رفض {name} لموعد ملغى", True)
    C.reinstate_event(ev_surg)
    C.add_payments(ev_surg, [(100, "USD")])
    try:
        C.cancel_event(ev_surg)
        check("منع إلغاء موعد عليه دفعات", False)
    except ValueError:
        check("منع إلغاء موعد عليه دفعات", True)

    # ── التقرير المطبوع والنسخ الاحتياطي المشفّر ──
    url = C.build_report(p["id"])
    import urllib.request
    html = urllib.request.urlopen(url).read().decode("utf-8")
    check("تقرير الطباعة يُخدَّم محلياً ويحوي الاسم", "سارة" in html and "Clinic Pro" in html)
    bk = C.make_backup()
    path = bk if isinstance(bk, str) else bk[0]
    check("نسخة احتياطية مشفّرة (ليست zip مقروءاً)", open(path, "rb").read(4) != b"PK\x03\x04")
    print("\n" + ("ALL PASSED" if not FAILS else f"FAILED: {FAILS}"))
    shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
