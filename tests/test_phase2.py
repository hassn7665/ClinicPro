# -*- coding: utf-8 -*-
"""
اختبارات المرحلة 2 (الإصدار 2.6): البحث بالهاتف، منع تكرار المريض، الحقول السريرية، مدة الموعد وكشف التعارض،
الجدول اليومي، «لم يحضر»، وتعديل/حذف المريض والموعد والمرفق والصور؛ ثم اختبارات الواجهة.
التشغيل:   python tests/test_phase2.py        (على نسخة مؤقتة؛ لا يمسّ بياناتك)
"""
import datetime as dt
import os
import shutil
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="clinicpro_p2_")
shutil.copytree(ROOT, os.path.join(WORK, "app"), ignore=shutil.ignore_patterns(
    "admin_keys.json", "issued_log.json", "__pycache__", "shifa_data", "tests", ".git", "build"))
APP = os.path.join(WORK, "app")
os.environ["FLET_APP_STORAGE_DATA"] = os.path.join(WORK, "data")
sys.path.insert(0, APP)
os.chdir(APP)
open(os.path.join(APP, "public_keys.py"), "w").write('SIGN_PUB = ""\nBOX_PUB = ""\n')

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
PW = "Pass#Word2026x"
BASE_F = dict(gender="أنثى", age=30, residence="حلب", job="معلمة", diseases="لا", notes="", blood="A+", status="جديد",
              phone="")


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


def patient(name, phone="", age=30, **kw):
    return C.save_patient(dict(BASE_F, full_name=name, phone=phone, age=age, **kw), {}, [], allow_duplicate=True)


def tmpfile(data, suffix=".txt"):
    p = tempfile.mktemp(suffix=suffix, dir=WORK)
    open(p, "wb").write(data)
    return p


def day(offset=0):
    return (dt.date.today() + dt.timedelta(days=offset)).strftime("%Y-%m-%d")


def pat_files():
    return {os.path.relpath(os.path.join(r, f), C.BASE) for r, _, fs in os.walk(C.PAT_DIR) for f in fs}


# ───────────────────────── البحث بالهاتف ─────────────────────────
def t_search():
    a = patient("سارة أحمد خليل", "0944 123 456")
    b = patient("ليلى حسن عمر", "+963 933 111 222")
    c = patient("نور محمد علي", "٠٩٤٥٦٧٨٩٠١")
    ids = lambda term: {r["id"] for r in C.search_patients(term)}
    check("بحث بجزء من الهاتف", a["id"] in ids("944123") and b["id"] not in ids("944123"))
    check("بحث برقم بصفر بادئ ورمز دولة مختلف", b["id"] in ids("0933111") and b["id"] in ids("933111"))
    check("بحث بأرقام عربية يطابق هاتفاً مخزّناً بالعربية", c["id"] in ids("٠٩٤٥٦٧") and c["id"] in ids("0945678"))
    check("هاتف مخزّن بأرقام لاتينية يُجاب عنه بأرقام عربية", a["id"] in ids("٠٩٤٤١٢٣"))
    check("أقل من 3 أرقام لا يطابق هاتفاً", a["id"] not in ids("94") and a["id"] not in ids("12"))
    check("البحث بالاسم والكود ما زال يعمل", a["id"] in ids("سارة") and a["id"] in ids(a["code"].lower()))
    check("تطبيع الألف والهمزة", a["id"] in ids("احمد") and a["id"] in ids("أحمد"))
    check("نص فارغ = لا نتائج", C.search_patients("") == [] and C.search_patients("   ") == [])
    check("fin_patients يبحث بالهاتف أيضاً", any(r["id"] == b["id"] for r in C.fin_patients("933111")))


# ───────────────────────── منع التكرار ─────────────────────────
def t_duplicates():
    base = dict(BASE_F, full_name="خالد يوسف حسن", phone="0955 111 000", age=40)
    first = C.save_patient(base, {}, [])
    check("أول مريض يُحفظ", first["id"])
    try:
        C.save_patient(dict(base, phone="+963955111000"), {}, [])
        check("نفس الاسم والهاتف (بصيغة مختلفة) مرفوض", False)
    except C.DuplicatePatient as ex:
        check("نفس الاسم والهاتف (بصيغة مختلفة) مرفوض", ex.matches and ex.matches[0]["reason"] == "name"
              and ex.matches[0]["id"] == first["id"])
    check("نفس الاسم مع اختلاف الألف/الهمزة", raises(lambda: C.save_patient(dict(base, full_name="خالد يوسف حَسَن"), {}, []), C.DuplicatePatient))
    check("نفس الاسم وعمر متقارب بهاتف مختلف: تنبيه",
          raises(lambda: C.save_patient(dict(base, phone="0966 000 111", age=41), {}, []), C.DuplicatePatient))
    other = C.save_patient(dict(base, phone="0966 000 111", age=70), {}, [])
    check("نفس الاسم بعمر وهاتف مختلفين كثيراً = شخص آخر (يُقبل)", other["id"] != first["id"])
    try:
        C.save_patient(dict(base, full_name="ريم يوسف حسن", phone="0955111000"), {}, [])
        check("هاتف مشترك باسم مختلف: تنبيه (قد يكونون عائلة)", False)
    except C.DuplicatePatient as ex:
        check("هاتف مشترك باسم مختلف: تنبيه (قد يكونون عائلة)", ex.matches[0]["reason"] == "phone")
    fam = C.save_patient(dict(base, full_name="ريم يوسف حسن", phone="0955111000"), {}, [], allow_duplicate=True)
    check("allow_duplicate=True يتجاوز التنبيه", fam["id"])
    check("تعديل مريض دون تغيير الاسم/الهاتف لا يُنبَّه (حتى لو كان مكرراً قديماً)",
          C.save_patient(dict(base, notes="x"), {}, [], pid=first["id"])["id"] == first["id"])
    check("تعديل الهاتف إلى هاتف مريض آخر يُنبَّه",
          raises(lambda: C.save_patient(dict(base, phone="0966 000 111", full_name="خالد يوسف حسن", age=70), {}, [], pid=first["id"]),
                 C.DuplicatePatient))
    n = C.q("select count(*) from patients")[0][0]
    raises(lambda: C.save_patient(dict(base, notes="مكرر"), {}, []), C.DuplicatePatient)
    check("المحاولة المرفوضة لا تترك أثراً", C.q("select count(*) from patients")[0][0] == n)


# ───────────────────────── الحقول السريرية والترقية ─────────────────────────
def t_clinical():
    p = C.save_patient(dict(BASE_F, full_name="هدى سمير جابر", phone="0911 222 333", allergies="بنسلين",
                            medications="ميتفورمين 500", diagnosis="سكري نمط 2"), {}, [])
    row = C.q("select allergies, medications, diagnosis from patients where id=?", (p["id"],), one=True)
    check("الحقول السريرية تُحفظ", tuple(row) == ("بنسلين", "ميتفورمين 500", "سكري نمط 2"))
    p2 = C.save_patient(dict(BASE_F, full_name="هدى سمير جابر", phone="0911 222 333"), {}, [], pid=p["id"])
    check("تعديل بلا الحقول يفرّغها (لا يُبقي قيماً قديمة خفية)", p2["allergies"] == "")
    C.save_patient(dict(BASE_F, full_name="هدى سمير جابر", phone="0911 222 333", allergies="سلفا"), {}, [], pid=p["id"])
    html = urllib.request.urlopen(C.build_report(p["id"]), timeout=5).read().decode()
    check("التقرير المطبوع يحوي الحساسية", "سلفا" in html and "الحساسية" in html and "التشخيص" in html)
    check("الأعمدة السريرية ومدة الموعد و«لم يحضر» في مخطط القاعدة الحالي",
          {"allergies", "medications", "diagnosis"} <= {r[1] for r in C.q("PRAGMA table_info(patients)")} and
          {"duration_min", "no_show"} <= {r[1] for r in C.q("PRAGMA table_info(events)")})      # ترقية قواعد 2.5/2.6: tests/test_migrations.py


# ───────────────────────── المدة والتعارض والجدول ─────────────────────────
def t_schedule():
    a = patient("مريض جدول أول", "0900 000 001")
    b = patient("مريض جدول ثان", "0900 000 002")
    d = day(5)
    v = C.create_event(a["id"], "visit", d, "10:00")
    s = C.create_event(b["id"], "surgery", d, "12:00")
    get = lambda i: C.q("select * from events where id=?", (i,), one=True)
    check("المدة الافتراضية: مراجعة 30 وعملية 120", get(v)["duration_min"] == 30 and get(s)["duration_min"] == 120)
    check("مدة مخصّصة", get(C.create_event(a["id"], "visit", d, "15:00", duration=45))["duration_min"] == 45)
    check("وقت غير صحيح مرفوض", raises(lambda: C.create_event(a["id"], "visit", d, "25:99"), ValueError))
    check("تاريخ غير صحيح مرفوض", raises(lambda: C.create_event(a["id"], "visit", "2026-13-40", "10:00"), ValueError))
    check("مدة خارج النطاق مرفوضة", raises(lambda: C.create_event(a["id"], "visit", d, "10:00", duration=2), ValueError)
          and raises(lambda: C.create_event(a["id"], "visit", d, "10:00", duration=9999), ValueError))
    ids = lambda t, du: {r["id"] for r in C.event_conflicts(d, t, du)}
    check("تداخل داخل المدة", v in ids("10:15", 30) and v in ids("09:45", 30))
    check("المواعيد المتلاصقة لا تتعارض", v not in ids("10:30", 30) and v not in ids("09:30", 30))
    check("تعارض مع عملية طويلة", s in ids("13:30", 15) and s not in ids("14:00", 15))
    check("exclude_id يستثني الموعد نفسه (للتعديل)", v not in {r["id"] for r in C.event_conflicts(d, "10:00", 30, exclude_id=v)})
    check("يوم آخر لا يتعارض", not C.event_conflicts(day(6), "10:00", 30))
    C.update_event(v, "visit", d, "10:00", [], duration=90)
    check("تعديل المدة", get(v)["duration_min"] == 90 and s not in ids("10:30", 30) and v in ids("11:15", 30))
    C.update_event(v, "visit", d, "10:00", [])
    check("تعديل بلا مدة يُبقي المدة الحالية", get(v)["duration_min"] == 90)
    C.update_event(v, "visit", d, "10:00", [], duration=30)
    ov = C.create_event(b["id"], "visit", d, "10:15")                     # يتداخل مع v (10:00-10:30)
    sched = C.day_schedule(d)
    check("الجدول مرتب بالوقت", [i["ev"]["id"] for i in sched][:3] == [v, ov, s])
    byid = {i["ev"]["id"]: i for i in sched}
    check("التعارض متماثل ويُشير للطرف الآخر", byid[v]["conflicts"] == [ov] and byid[ov]["conflicts"] == [v] and not byid[s]["conflicts"])
    check("الحالة 'pending' للمستقبل", byid[v]["status"] == "pending")
    C.cancel_event(ov, "اختبار")
    sched = C.day_schedule(d)
    byid = {i["ev"]["id"]: i for i in sched}
    check("الملغى يظهر بحالته ولا يُحتسب تعارضاً", byid[ov]["status"] == "cancelled" and not byid[v]["conflicts"])
    C.confirm_event(v, "تم")
    check("المؤكَّد يشغل وقته في التعارض", v in ids("10:10", 10))
    cnt = C.day_counts(d, 3)
    check("عدّاد الأسبوع يحسب الفعّالة فقط", cnt[d] == 3 and cnt[day(6)] == 0, str(cnt))


# ───────────────────────── لم يحضر ─────────────────────────
def t_no_show():
    p = patient("مريض لم يحضر", "0900 000 010")
    fut = C.create_event(p["id"], "visit", day(3), "10:00")
    check("لا «لم يحضر» لموعد مستقبلي", raises(lambda: C.mark_no_show(fut), ValueError))
    past = C.create_event(p["id"], "visit", day(-1), "10:00", items=[("كشف", 100, "USD")])
    check("الموعد المتأخر يظهر في upcoming_events.late", past in {r["id"] for _, r in C.upcoming_events(1)[0]})
    check("المستحق قبل «لم يحضر» = 100$", C.fin_totals(p["id"])[0]["USD"] == 100)
    s0 = C.stats()
    C.mark_no_show(past, "اتصلنا ولم يرد")
    ev = C.q("select * from events where id=?", (past,), one=True)
    check("الحالة no_show والسبب محفوظ", C.event_status(ev) == "no_show" and ev["cancel_reason"] == "اتصلنا ولم يرد")
    check("يخرج من المواعيد المتأخرة/القريبة", past not in {r["id"] for _, r in C.upcoming_events(1)[0] + C.upcoming_events(1)[1]})
    check("لا يُحتسب في المستحقات", C.fin_totals(p["id"])[0]["USD"] == 0)
    s1 = C.stats()
    check("الإحصاء: no_show يزيد 1 و«ملغاة» لا تزيد", s1["no_show"] == s0["no_show"] + 1 and s1["cancelled"] == s0["cancelled"])
    check("لا تسجيل مكرر", raises(lambda: C.mark_no_show(past), ValueError))
    check("لا إلغاء لموعد «لم يحضر»", raises(lambda: C.cancel_event(past), ValueError))
    C.reinstate_event(past)
    ev = C.q("select * from events where id=?", (past,), one=True)
    check("الاستعادة تمسح العلمين وتعيد المستحق", ev["no_show"] == 0 and ev["cancelled"] == 0 and C.fin_totals(p["id"])[0]["USD"] == 100)
    C.add_payments(past, [(10, "USD")])
    check("لا «لم يحضر» مع وجود دفعات", raises(lambda: C.mark_no_show(past), ValueError))
    C.confirm_event(past, "تم")
    check("لا «لم يحضر» لموعد مؤكَّد", raises(lambda: C.mark_no_show(past), ValueError))
    check("إلغاء عادي ما زال يُحتسب «ملغى» لا «لم يحضر»",
          (lambda e: (C.cancel_event(e), C.event_status(C.q("select * from events where id=?", (e,), one=True)))[1])(fut) == "cancelled")


# ───────────────────────── التعديل والحذف ─────────────────────────
def t_delete_edit():
    img = tmpfile(os.urandom(2000), ".jpg")
    doc = tmpfile(b"%PDF report", ".pdf")
    p = C.save_patient(dict(BASE_F, full_name="مريض للحذف الكامل", phone="0922 000 000", age=55),
                       {"photo_before": img, "photo_after": img}, [doc, doc], allow_duplicate=True)
    keep = patient("مريض يبقى سليماً", "0922 000 111")
    keep_ev = C.create_event(keep["id"], "visit", day(2), "11:00", items=[("كشف", 5, "USD")])
    C.add_payments(keep_ev, [(5, "USD")])
    atts = C.q("select * from attachments where patient_id=?", (p["id"],))
    # أ) المرفقات
    nm = C.rename_attachment(atts[0]["id"], "  تقرير/مختبر  ")
    check("إعادة تسمية مرفق: تنظيف الاسم وحفظ الامتداد", nm == "تقرير مختبر.pdf", nm)
    check("اسم فارغ مرفوض", raises(lambda: C.rename_attachment(atts[0]["id"], "  "), ValueError))
    rel0 = atts[0]["path"]
    C.delete_attachment(atts[0]["id"])
    check("حذف مرفق: الصف والملف", not C.q("select 1 from attachments where id=?", (atts[0]["id"],)) and not os.path.exists(C.ap(rel0)))
    check("المرفق الآخر سليم", os.path.exists(C.ap(atts[1]["path"])))
    # ب) الصور
    rel_b = p["photo_before"]
    C.clear_patient_photo(p["id"], "photo_before")
    check("حذف صورة مريض", C.q("select photo_before from patients where id=?", (p["id"],), one=True)[0] is None
          and not os.path.exists(C.ap(rel_b)))
    check("مفتاح عمود غير مسموح مرفوض", raises(lambda: C.clear_patient_photo(p["id"], "full_name"), ValueError))
    e1 = C.create_event(p["id"], "visit", day(4), "09:00", items=[("كشف", 10, "USD")])
    C.set_event_photo(e1, "before", img)
    rel_e = C.q("select photo_before from events where id=?", (e1,), one=True)[0]
    C.clear_event_photo(e1, "before")
    check("حذف صورة موعد", C.q("select photo_before from events where id=?", (e1,), one=True)[0] is None and not os.path.exists(C.ap(rel_e)))
    # ج) حذف موعد
    C.set_event_photo(e1, "after", img)
    rel_e2 = C.q("select photo_after from events where id=?", (e1,), one=True)[0]
    C.add_payments(e1, [(3, "USD")])
    check("لا حذف موعد عليه دفعات", raises(lambda: C.delete_event(e1), ValueError))
    C.delete_payment(C.q("select id from payments where event_id=?", (e1,), one=True)[0])
    C.delete_event(e1)
    check("حذف موعد: الصف والإجراءات والصور", not C.q("select 1 from events where id=?", (e1,)) and
          not C.q("select 1 from event_items where event_id=?", (e1,)) and not os.path.exists(C.ap(rel_e2)))
    # د) حذف مريض
    e2 = C.create_event(p["id"], "surgery", day(6), "10:00", items=[("عملية", 100, "USD")])
    C.add_payments(e2, [(40, "USD")])
    summ = C.patient_delete_summary(p["id"])
    check("ملخص الحذف يعدّ المحتوى والمدفوع والمتبقي", summ["events"] == 1 and summ["attachments"] == 1 and
          summ["paid"]["USD"] == 40 and summ["remaining"]["USD"] == 60, str(summ))
    # فشل أثناء الحذف يُرجع كل شيء
    with C.closing(C.db()) as c:
        c.execute("CREATE TRIGGER t_block BEFORE DELETE ON attachments BEGIN SELECT RAISE(ABORT, 'boom'); END")
        c.commit()
    files0 = pat_files()
    ok = raises(lambda: C.delete_patient(p["id"]))
    with C.closing(C.db()) as c:
        c.execute("DROP TRIGGER t_block")
        c.commit()
    check("فشل أثناء الحذف يُرجع كل شيء (مريض ومواعيد ودفعات وملفات)",
          ok and C.q("select 1 from patients where id=?", (p["id"],)) and C.q("select 1 from payments where event_id=?", (e2,))
          and pat_files() == files0)
    nb = len(C.list_backups())
    C.delete_patient(p["id"])
    check("حذف المريض يزيل كل صفوفه", not any(C.q(sql, (p["id"],)) for sql in (
        "select 1 from patients where id=?", "select 1 from events where patient_id=?", "select 1 from attachments where patient_id=?",
        "select 1 from payments where event_id in (select id from events where patient_id=?)")))
    check("…وكل ملفاته (مجلد المريض كاملاً)", not any(f.startswith(f"patients/{p['code']}/") for f in pat_files()))
    check("…ولم يمسّ مريضاً آخر ودفعاته", C.q("select count(*) from payments where event_id=?", (keep_ev,))[0][0] == 1)
    check("أُخذت نسخة احتياطية قبل الحذف (أو كانت حديثة)", len(C.list_backups()) >= 1)
    check("حذف مريض غير موجود يُرفض", raises(lambda: C.delete_patient(p["id"]), ValueError))


# ───────────────────────── الواجهة ─────────────────────────
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
alltext = lambda pg: " ".join(t for c in tree(pg) for t in ([c.value] if isinstance(c, ft.Text) and c.value else []))


def clickable(pg, label):
    return [c for c in tree(pg) if getattr(c, "on_click", None) and label in " ".join(texts(c))]


def find(pg, label, n=0):
    return clickable(pg, label)[n]


def dialog_ctrls(pg):
    return walk(pg.opened[-1], []) if pg.opened else []


def d_click(pg, label, n=0):
    return [c for c in dialog_ctrls(pg) if getattr(c, "on_click", None) and label in " ".join(texts(c))][n]


import types                                         # noqa: E402


def tf(pg, label):
    return [c for c in tree(pg) if isinstance(c, ft.TextField) and label in (c.label or "")][0]


def tile_click(pg, label):
    col = [x for x in tree(pg) if isinstance(x, ft.Column) and x.width == 76 and label in " ".join(texts(x))][0]
    col.controls[0].on_click(Ev())


def by_tip(pg, tip):
    return [c for c in tree(pg) if getattr(c, "tooltip", None) == tip and getattr(c, "on_click", None)]


def pick_when(pg, d, hh, mm):
    """يقود DatePicker ثم TimePicker في FakePage."""
    pg.opened[-1].on_change(types.SimpleNamespace(control=types.SimpleNamespace(value=dt.datetime.combine(d, dt.time(0, 0)))))
    pg.opened[-1].on_change(types.SimpleNamespace(control=types.SimpleNamespace(value=dt.time(hh, mm))))


def t_ui():
    pg = FakePage()
    M.main(pg)
    f = [c for c in tree(pg) if isinstance(c, ft.TextField)]
    f[0].value, f[1].value = "tester", PW
    find(pg, "دخول").on_click(Ev())
    # ① نموذج مريض جديد بالحقول السريرية
    tile_click(pg, "إضافة مريض")
    check("النموذج يحوي حقول الحساسية والأدوية والتشخيص",
          all(any(isinstance(c, ft.TextField) and k in (c.label or "") for c in tree(pg)) for k in ("الحساسية", "الأدوية", "التشخيص")))
    tf(pg, "الاسم الثلاثي").value = "منى عادل سعيد"
    tf(pg, "رقم التواصل").value = "0977 555 444"
    tf(pg, "الحساسية").value = "بنسلين"
    tf(pg, "التشخيص").value = "التهاب حلق"
    find(pg, "إضافة المريض").on_click(Ev())
    row = C.q("select * from patients where full_name='منى عادل سعيد'", one=True)
    check("الحفظ من النموذج يخزّن الحقول السريرية", row and row["allergies"] == "بنسلين" and row["diagnosis"] == "التهاب حلق")
    check("حوار «تمت إضافة المريض» يظهر", "تمت إضافة المريض" in " ".join(texts(pg.opened[-1])))
    # ② نموذج مكرر: حوار بدل الحفظ الصامت
    d_click(pg, "الرئيسية").on_click(Ev())
    tile_click(pg, "إضافة مريض")
    tf(pg, "الاسم الثلاثي").value = "منى عادل سعيد"
    tf(pg, "رقم التواصل").value = "+963 977 555 444"
    n0 = C.q("select count(*) from patients")[0][0]
    find(pg, "إضافة المريض").on_click(Ev())
    check("مريض مكرر: يظهر حوار «مريض مشابه» ولا يُحفظ", "مريض مشابه موجود" in " ".join(texts(pg.opened[-1])) and
          C.q("select count(*) from patients")[0][0] == n0)
    d_click(pg, "حفظ كمريض جديد").on_click(Ev())
    check("«حفظ كمريض جديد» يتجاوز التنبيه", C.q("select count(*) from patients")[0][0] == n0 + 1)
    d_click(pg, "الرئيسية").on_click(Ev())
    # ③ البحث بالهاتف من الواجهة
    find(pg, "ابحث عن مريض").on_click(Ev())
    box = tf(pg, "رقم الهاتف")
    box.value = "977555"
    box.on_change(Ev(box))
    check("البحث بالهاتف يعرض المريض والرقم", "منى عادل سعيد" in alltext(pg) and "0977 555 444" in alltext(pg))
    find(pg, "فتح الملف").on_click(Ev())
    check("ملف المريض يعرض شريط الحساسية والتشخيص", "حساسية" in alltext(pg) and "بنسلين" in alltext(pg) and "التهاب حلق" in alltext(pg))
    pid = row["id"]
    # ④ موعد جديد مع تحذير التعارض (يحتاج تأكيداً ثانياً)
    d0 = dt.date.today() + dt.timedelta(days=9)
    existing = C.create_event(pid, "visit", d0.strftime("%Y-%m-%d"), "10:00")
    find(pg, "موعد مراجعة").on_click(Ev())
    pick_when(pg, d0, 10, 10)
    dlg_text = " ".join(texts(pg.opened[-1]))
    check("حوار الموعد يعرض المدة وتحذير التعارض فوراً", "مدة الموعد" in dlg_text and "يتعارض مع" in dlg_text)
    n_ev = C.q("select count(*) from events where patient_id=?", (pid,))[0][0]
    d_click(pg, "حفظ الموعد").on_click(Ev())
    check("الضغطة الأولى على التعارض لا تحفظ وتطلب التأكيد", C.q("select count(*) from events where patient_id=?", (pid,))[0][0] == n_ev
          and "مرة أخرى" in " ".join(texts(pg.opened[-1])))
    d_click(pg, "حفظ الموعد").on_click(Ev())
    check("الضغطة الثانية تحفظ رغم التعارض", C.q("select count(*) from events where patient_id=?", (pid,))[0][0] == n_ev + 1)
    # ⑤ لم يحضر من ملف المريض
    past = C.create_event(pid, "visit", day(-2), "09:00")
    tile_back = [c for c in tree(pg) if getattr(c, "tooltip", None) == "رجوع"]
    tile_back[0].on_click(Ev())
    find(pg, "ابحث عن مريض").on_click(Ev())
    box = tf(pg, "رقم الهاتف")
    box.value = "977555"
    box.on_change(Ev(box))
    find(pg, "فتح الملف").on_click(Ev())
    nsb = clickable(pg, "لم يحضر")
    check("زر «لم يحضر» يظهر للموعد الذي فات وقته فقط", len(nsb) == 1)
    nsb[0].on_click(Ev())
    d_click(pg, "تسجيل").on_click(Ev())
    check("«لم يحضر» من الواجهة يُغلق الموعد", C.q("select no_show from events where id=?", (past,), one=True)[0] == 1 and
          "لم يحضر" in alltext(pg))
    # ⑥ المرفقات: إعادة تسمية وحذف من ملف المريض
    doc = tmpfile(b"%PDF x", ".pdf")
    C.save_patient(dict(BASE_F, full_name="منى عادل سعيد", phone="+963 977 555 444"), {}, [doc], pid=pid)
    tile_back = [c for c in tree(pg) if getattr(c, "tooltip", None) == "رجوع"]
    tile_back[0].on_click(Ev())
    find(pg, "ابحث عن مريض").on_click(Ev())
    box = tf(pg, "رقم الهاتف")
    box.value = "977555"
    box.on_change(Ev(box))
    find(pg, "فتح الملف").on_click(Ev())
    by_tip(pg, "إعادة تسمية")[0].on_click(Ev())
    nm = [c for c in dialog_ctrls(pg) if isinstance(c, ft.TextField)][0]
    nm.value = "نتيجة تحليل"
    d_click(pg, "حفظ").on_click(Ev())
    check("إعادة تسمية المرفق من الواجهة", C.q("select name from attachments where patient_id=?", (pid,), one=True)[0] == "نتيجة تحليل.pdf")
    by_tip(pg, "حذف المرفق")[0].on_click(Ev())
    d_click(pg, "حذف").on_click(Ev())
    check("حذف المرفق من الواجهة", C.q("select count(*) from attachments where patient_id=?", (pid,))[0][0] == 0)
    # ⑦ شاشة الجدول
    tile_back = [c for c in tree(pg) if getattr(c, "tooltip", None) == "رجوع"]
    tile_back[0].on_click(Ev())
    find(pg, "الجدول").on_click(Ev())
    check("شاشة الجدول تفتح على اليوم", dt.date.today().strftime("%Y-%m-%d") in alltext(pg) and "اليوم" in alltext(pg))
    for _ in range(9):
        by_tip(pg, "اليوم التالي")[0].on_click(Ev())
    check("التنقل بين الأيام يصل لليوم المطلوب", d0.strftime("%Y-%m-%d") in alltext(pg))
    txt = alltext(pg)
    check("الجدول يعرض الموعدين المتعارضين بنطاق الوقت ووسم التعارض",
          "10:00" in txt and "10:10" in txt and "متعارض" in txt and "يتعارض مع" in txt and "منى عادل سعيد" in txt, txt[:200])
    for _ in range(11):
        by_tip(pg, "اليوم السابق")[0].on_click(Ev())
    check("يوم «لم يحضر» يعرضه بحالته وزر الاستعادة", day(-2) in alltext(pg) and "لم يحضر" in alltext(pg) and clickable(pg, "استعادة"))
    clickable(pg, "استعادة")[0].on_click(Ev())
    check("الاستعادة من الجدول", C.q("select no_show from events where id=?", (past,), one=True)[0] == 0 and clickable(pg, "لم يحضر"))
    clickable(pg, "لم يحضر")[0].on_click(Ev())
    d_click(pg, "تسجيل").on_click(Ev())
    check("«لم يحضر» من الجدول", C.q("select no_show from events where id=?", (past,), one=True)[0] == 1)
    # ⑧ حذف المريض من الواجهة (يتطلب تفعيل مفتاح التأكيد)
    tile_back = [c for c in tree(pg) if getattr(c, "tooltip", None) == "رجوع"]
    tile_back[0].on_click(Ev())
    find(pg, "ابحث عن مريض").on_click(Ev())
    box = tf(pg, "رقم الهاتف")
    box.value = "977555"
    box.on_change(Ev(box))
    find(pg, "فتح الملف").on_click(Ev())
    find(pg, "حذف المريض نهائياً").on_click(Ev())
    check("حوار حذف المريض يعرض ما سيُحذف", "المواعيد:" in " ".join(texts(pg.opened[-1])))
    d_click(pg, "حذف نهائي").on_click(Ev())
    check("لا حذف بدون تفعيل التأكيد", C.q("select 1 from patients where id=?", (pid,)) and
          "فعّل الخيار" in " ".join(texts(pg.opened[-1])))
    [c for c in dialog_ctrls(pg) if isinstance(c, ft.Switch)][0].value = True
    d_click(pg, "حذف نهائي").on_click(Ev())
    check("حذف المريض من الواجهة يزيله ويعود للرئيسية", not C.q("select 1 from patients where id=?", (pid,)) and
          "ابحث عن مريض" in alltext(pg))


def main():
    d = C.lic_load()
    C.lic_activate(keygen.issue_activation(d["device_id"], 12, None, "t")["code"])
    C.setup_account("tester", PW)
    t_search()
    t_duplicates()
    t_clinical()
    t_schedule()
    t_no_show()
    t_delete_edit()
    t_ui()
    print("\n" + ("ALL PASSED" if not FAILS else f"FAILED: {FAILS}"))
    shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
