# -*- coding: utf-8 -*-
"""
اختبارات المرحلة 1 (الاستقرار والأداء، الإصدار 2.5): تصغير الصور والمصغّرات، حفظ المريض في معاملة واحدة،
تقرير النسخ الاحتياطي، التعافي من انقطاع الاستعادة، روابط المشاركة، سجل الأخطاء بلا بيانات، التشخيص،
تحسين الصور القديمة، التحميل الكسول للصور الكبيرة، والترحيب مرة واحدة.
التشغيل:   python tests/test_phase1.py        (على نسخة مؤقتة؛ لا يمسّ بياناتك)
"""
import datetime as dt
import io
import os
import shutil
import sys
import tempfile
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="clinicpro_p1_")
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
import images                                       # noqa: E402
import main as M                                    # noqa: E402

try:
    from PIL import Image
except Exception:
    Image = None
SLEEPS = []
M.time.sleep = lambda s=0, *a: SLEEPS.append(s)
FAILS = []
PW = "Pass#Word2026x"
F = dict(full_name="سارة أحمد خليل", gender="أنثى", age=28, residence="حلب", phone="0944", job="معلمة",
         diseases="لا", notes="", blood="A+", status="جديد")


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


def pat_files():
    return {os.path.relpath(os.path.join(r, f), C.BASE) for r, _, fs in os.walk(C.PAT_DIR) for f in fs}


def jpeg(w, h, orient=None, q=95):
    im = Image.frombytes("RGB", (w, h), os.urandom(w * h * 3))
    ex = Image.Exif()
    ex[0x010F] = "TestCam"
    if orient:
        ex[0x0112] = orient
    b = io.BytesIO()
    im.save(b, "JPEG", quality=q, exif=ex)
    return b.getvalue()


def tmpfile(data, suffix=".jpg"):
    p = tempfile.mktemp(suffix=suffix, dir=WORK)
    open(p, "wb").write(data)
    return p


# ───────────────────────── الصور ─────────────────────────
def t_images():
    if Image is None:
        return print("SKIP اختبارات الصور (Pillow غير مثبّتة هنا)")
    big = jpeg(4000, 3000)
    check("المدخل يحوي EXIF (فحص سلامة الاختبار)", bool(Image.open(io.BytesIO(big)).getexif()))
    full, thumb = images.process(big)
    im, th = Image.open(io.BytesIO(full)), Image.open(io.BytesIO(thumb))
    check("تصغير الأضلع إلى ≤ 1600", max(im.size) == images.MAX_SIDE, str(im.size))
    check("الحجم أقل من الأصل بوضوح", len(full) < len(big) * 0.6, f"{len(big) // 1024}KB → {len(full) // 1024}KB")
    check("إزالة EXIF بالكامل (ومنها GPS)", not Image.open(io.BytesIO(full)).getexif())
    check("مصغّرة ≤ 360 وأصغر بكثير", thumb and max(th.size) <= images.THUMB and len(thumb) < len(full) / 4, str(th.size))
    rot, _ = images.process(jpeg(400, 200, orient=6))
    check("تدوير EXIF يُطبَّق قبل التجريد", Image.open(io.BytesIO(rot)).size == (200, 400))
    b = io.BytesIO()
    Image.new("RGBA", (50, 50), (255, 0, 0, 0)).save(b, "PNG")
    out, _ = images.process(b.getvalue())
    o = Image.open(io.BytesIO(out))
    check("PNG شفاف يُسطَّح على الأبيض ويُحفظ JPEG", out[:3] == b"\xff\xd8\xff" and o.getpixel((5, 5)) == (255, 255, 255))
    gif = b"GIF89a" + os.urandom(40)
    check("GIF يُترك كما هو", images.process(gif) == (gif, None))
    check("غير الصور تُترك كما هي", images.process(b"hello") == (b"hello", None))
    bad = b"\xff\xd8\xff" + os.urandom(100)
    check("JPEG تالف لا يُفشل المعالجة", images.process(bad) == (bad, None))
    old = images.MAX_PIXELS
    images.MAX_PIXELS = 100
    d = jpeg(60, 60)
    check("حدّ البكسلات يمنع المعالجة", images.process(d)[1] is None and images.process(d)[0] == d)
    images.MAX_PIXELS = old
    images.PIL_OK = False
    check("بلا Pillow: لا تغيير على البيانات", images.process(big) == (big, None))
    images.PIL_OK = True


def t_store_and_wipe():
    if Image is None:
        return
    src = tmpfile(jpeg(3000, 2000))
    p = C.save_patient(F, {"photo_before": src}, [])
    rel = p["photo_before"]
    th = C.ap(C.thumb_rel(rel))
    check("حُفظت الصورة مصغّرة ومعها مصغّرة مشفّرة", os.path.isfile(th) and C.file_size(rel) < os.path.getsize(src) / 2)
    b64, is_thumb = C.thumb_b64(rel)
    check("thumb_b64 تعيد المصغّرة", is_thumb and len(b64) < len(C.file_b64(rel)) / 3)
    check("المصغّرة مشفّرة (لا JPEG مقروء)", open(th, "rb").read(4) == b"SHF1")
    C._migrate_legacy_files()
    check("مسح الأيتام لا يحذف المصغّرات", os.path.isfile(th) and os.path.isfile(C.ap(rel)))
    p2 = C.save_patient(F, {"photo_before": tmpfile(jpeg(2500, 1800))}, [], pid=p["id"])
    check("استبدال الصورة يمحو القديمة ومصغّرتها بعد النجاح",
          not os.path.exists(C.ap(rel)) and not os.path.exists(th) and os.path.isfile(C.ap(C.thumb_rel(p2["photo_before"]))))
    C._wipe_rel(p2["photo_before"])
    check("_wipe_rel يمحو الأصل والمصغّرة", not os.path.exists(C.ap(p2["photo_before"])) and
          not os.path.exists(C.ap(C.thumb_rel(p2["photo_before"]))))
    C.x("UPDATE patients SET photo_before=NULL WHERE id=?", (p["id"],))


# ───────────────────────── المعاملة الواحدة ─────────────────────────
def t_transaction():
    img = tmpfile(jpeg(800, 600))
    txt = tmpfile(b"report", ".txt")
    n0, files0, sig0 = C.q("select count(*) from patients")[0][0], pat_files(), C._file_sig(C.DB_ENC)
    real_store, real_persist, calls, pcalls = C.store_file, C._persist, {"n": 0}, []

    def flaky(p, src, tag=None):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return real_store(p, src, tag)
    C.store_file = flaky
    C._persist = lambda: (pcalls.append(1), real_persist())[1]
    ok = raises(lambda: C.save_patient(dict(F, full_name="مريض فاشل تماماً"), {"photo_before": img, "photo_after": img}, [txt]), OSError)
    C.store_file = real_store
    check("فشل في منتصف الحفظ يرفع الخطأ", ok)
    check("لا مريض نصف محفوظ", C.q("select count(*) from patients")[0][0] == n0 and
          not C.q("select 1 from patients where full_name like 'مريض فاشل%'"))
    check("لا ملفات يتيمة بعد الفشل", pat_files() == files0)
    check("لم يُكتب شيء على القرص (لا حفظ للقاعدة)", not pcalls and C._file_sig(C.DB_ENC) == sig0)
    p = C.save_patient(dict(F, full_name="مريض ناجح مكتمل"), {"photo_before": img, "photo_after": img, "photo_lab": img}, [txt, txt])
    check("حفظ ناجح بـ3 صور و2 مرفق = حفظ قاعدة واحد فقط", len(pcalls) == 1, str(len(pcalls)))
    check("المرفقات سُجّلت", C.q("select count(*) from attachments where patient_id=?", (p["id"],))[0][0] == 2)
    # فشل في تعديل: الصورة القديمة تبقى
    old_rel = p["photo_before"]
    C.store_file = lambda *a, **k: (_ for _ in ()).throw(OSError("x"))
    raises(lambda: C.save_patient(dict(F, full_name="اسم جديد"), {"photo_before": img}, [], pid=p["id"]), OSError)
    C.store_file = real_store
    row = C.q("select photo_before, full_name from patients where id=?", (p["id"],), one=True)
    check("فشل التعديل لا يمسّ الصورة القديمة ولا الاسم", row["photo_before"] == old_rel and os.path.isfile(C.ap(old_rel))
          and row["full_name"] == "مريض ناجح مكتمل")
    # فشل الحفظ على القرص بعد التثبيت: الملفات تبقى والبيانات في الذاكرة
    n1 = C.q("select count(*) from patients")[0][0]
    C._persist = lambda: (_ for _ in ()).throw(OSError("disk full"))
    ok = raises(lambda: C.save_patient(dict(F, full_name="مريض حفظ القرص"), {"photo_before": img}, []), OSError)
    C._persist = real_persist
    row = C.q("select photo_before from patients where full_name='مريض حفظ القرص'", one=True)
    check("فشل الحفظ على القرص بعد التثبيت: البيانات والملف باقيان للمحاولة التالية",
          ok and row and os.path.isfile(C.ap(row[0])) and C.q("select count(*) from patients")[0][0] == n1 + 1)
    real_persist()


# ───────────────────────── النسخ والاستعادة ─────────────────────────
def t_backup_report():
    bad = os.path.join(C.PAT_DIR, "PT-99999", "deadbeefdeadbeef.bin")
    os.makedirs(os.path.dirname(bad), exist_ok=True)
    open(bad, "wb").write(b"SHF1" + os.urandom(64))                       # مشفّر ظاهرياً لكنه تالف
    path = C.make_backup()
    rep = C.backup_report()
    check("النسخة تُبلغ عن الملف التالف", rep["skipped"] == 1 and rep["files"] >= 2, str(rep))
    check("السجل يذكر الملف المتخطّى (باسم معتم)", "backup_skip" in C.LOG.tail(50) and "deadbeefdeadbeef" in C.LOG.tail(50))
    os.remove(bad)
    shutil.rmtree(os.path.dirname(bad))
    C.make_backup()
    check("نسخة سليمة بعدها تمسح التحذير", C.backup_report()["skipped"] == 0)
    C.restore_backup(path)
    check("نسخة بملف متخطّى تُستعاد بدون أخطاء", C.q("select count(*) from patients")[0][0] >= 2)


def t_restore_recovery():
    path = C.make_backup()
    n0, files0 = C.q("select count(*) from patients")[0][0], pat_files()
    real_persist = C._persist
    C._persist = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    ok = raises(lambda: C.restore_backup(path), RuntimeError)
    C._persist = real_persist
    check("فشل الاستعادة وسط التبديل يرفع الخطأ", ok)
    check("…ويُرجع الصور القديمة كاملة", pat_files() == files0)
    check("…وتبقى القاعدة الحية سليمة", C.q("select count(*) from patients")[0][0] == n0)
    check("…ولا بقايا (.old/.restore/journal)", not any(os.path.exists(x) for x in
          (C.PAT_DIR + ".old", C.PAT_DIR + ".restore", C.JOURNAL)))
    # حالات الانقطاع المفاجئ (محاكاة الحالة على القرص ثم الإقلاع)
    sig = C._file_sig(C.DB_ENC)
    jr = lambda s: open(C.JOURNAL, "w").write('{"db_sig": "%s"}' % s)
    shutil.move(C.PAT_DIR, C.PAT_DIR + ".old")                           # A: انقطع بعد نقل القديم
    jr(sig)
    check("انقطاع A: يُرجَع المجلد القديم", C.recover_interrupted_restore() == "rolled_back" and pat_files() == files0)
    shutil.move(C.PAT_DIR, C.PAT_DIR + ".old")                           # B: وُضع الجديد ولم تُحفظ القاعدة
    os.makedirs(C.PAT_DIR)
    open(os.path.join(C.PAT_DIR, "junk.bin"), "wb").write(b"x")
    jr(sig)
    check("انقطاع B: يُحذف الجديد ويُرجَع القديم", C.recover_interrupted_restore() == "rolled_back" and pat_files() == files0)
    shutil.copytree(C.PAT_DIR, C.PAT_DIR + ".old")                       # C: حُفظت القاعدة الجديدة وبقي التنظيف
    jr("different-signature")
    check("انقطاع C: يُكمَل التنظيف ويبقى الجديد", C.recover_interrupted_restore() == "committed"
          and not os.path.exists(C.PAT_DIR + ".old") and pat_files() == files0)
    os.makedirs(C.PAT_DIR + ".restore")
    check("بقايا مؤقتة بلا سجلّ تُنظَّف", C.recover_interrupted_restore() is None and not os.path.exists(C.PAT_DIR + ".restore"))
    open(os.path.join(C.BK_DIR, "x.shbk.tmp"), "wb").write(b"1")
    C._startup_recovery()
    check("نسخة احتياطية مقطوعة (.tmp) تُحذف عند الإقلاع", not os.path.exists(os.path.join(C.BK_DIR, "x.shbk.tmp")))


# ───────────────────────── المشاركة والسجل والتشخيص ─────────────────────────
def t_share():
    u1 = C.share_text("a.txt", "first")
    u2 = C.share_text("b.txt", "second")
    get = lambda u: urllib.request.urlopen(u, timeout=5).read().decode()
    check("رابط المشاركة الأول ما زال صالحاً بعد فتح ثانٍ", get(u1) == "first" and get(u2) == "second")
    folder, token = C.new_share_dir()
    old = time.time() - C.SHARE_TTL - 60
    os.utime(folder, (old, old))
    C.new_share_dir()
    check("المجلدات المنتهية فقط تُحذف", not os.path.exists(folder) and get(u2) == "second")


def t_log_and_diag():
    def boom():
        raise ValueError("اسم سري سارة 0944")
    try:
        boom()
    except Exception as ex:
        C.LOG.log_exc("t_boom", ex, file="abc123", name="سارة", n=5)
    tail = C.LOG.tail(10)
    check("السجل يحوي نوع الاستثناء ومواضعه", "ValueError" in tail and "boom" in tail and "t_boom" in tail)
    check("السجل لا يحوي رسالة الاستثناء ولا قيماً غير ASCII", "سارة" not in tail and "0944" not in tail and "name=" not in tail)
    check("القيم الآمنة تُسجَّل", "file=abc123" in tail and "n=5" in tail)
    for i in range(6000):
        C.LOG.log("fill", i=i)
    sizes = sum(os.path.getsize(os.path.join(C.BASE, "logs", f)) for f in os.listdir(os.path.join(C.BASE, "logs")))
    check("السجل محدود الحجم (تدوير)", sizes <= (C.LOG.BACKUPS + 1) * C.LOG.MAX_BYTES + 5000, f"{sizes // 1024}KB")
    rep = C.diagnostics()
    check("تقرير التشخيص يحوي الفحوص والأزمنة", "✓" in rep and "اشتقاق كلمة المرور" in rep and "زمن حفظ القاعدة" in rep)
    check("التقرير بلا أسماء مرضى ولا اسم مستخدم", "سارة" not in rep and "tester" not in rep.lower().replace("testcam", ""))
    import selftest
    res = selftest.run(C.BASE, 2000)
    check("الفحوص الذاتية (متجهات RFC ...) كلها تنجح هنا", all(ok for _, ok, _ in res), str([n for n, ok, _ in res if not ok]))


def t_log_capture():
    import logging
    C.LOG.install_hooks()
    C.LOG.log_text("t_flet", "خطأ سارة 0944 RenderFlex overflowed by 12 pixels 987654321")
    t = C.LOG.tail(5)
    check("نص أخطاء Flet يُنقّى: يبقى الإنجليزي المفيد", "RenderFlex overflowed by 12 pixels" in t)
    check("…ويُحجب العربي والأرقام الطويلة", "سارة" not in t and "0944" not in t and "987654321" not in t and "#" in t)
    try:
        raise ValueError("سر سارة")
    except ValueError as ex:
        logging.getLogger("asyncio").error("Future exception was never retrieved", exc_info=ex)
    t = C.LOG.tail(5)
    check("استثناء مسجَّل عبر logging يُلتقط (نوعه ومواضعه فقط)", "log_asyncio" in t and "ValueError" in t and "سارة" not in t)
    rep = C.diagnostics()
    check("التشخيص يعرض إصدار Flet الفعلي", "Flet: ?" not in rep and "Flet: 0." in rep)


def t_optimize():
    if Image is None:
        return
    legacy = jpeg(2400, 1800, q=95)
    pid = C.q("select id, code from patients order by id", one=True)
    rel = C.new_rel(pid["code"])
    C.write_enc(rel, legacy)                                             # صورة قديمة: كبيرة وبلا مصغّرة
    C.x("UPDATE patients SET photo_lab=? WHERE id=?", (rel, pid["id"]))
    check("الصورة القديمة تُرصد للتحسين", rel in C.images_to_optimize(), str(len(legacy) // 1024))
    nb = len(C.list_backups())
    prog = []
    r = C.optimize_images(lambda i, n: prog.append((i, n)))
    check("التحسين نجح ووفّر مساحة وأنشأ مصغّرة", r["done"] >= 1 and r["saved"] > 0 and os.path.isfile(C.ap(C.thumb_rel(rel)))
          and C.file_size(rel) < len(legacy) / 2, str(r))
    check("المسار نفسه والقاعدة لم تتغير", C.q("select photo_lab from patients where id=?", (pid["id"],), one=True)[0] == rel)
    check("أُخذت نسخة احتياطية قبل التحسين وأُبلغ بالتقدّم", len(C.list_backups()) >= min(nb + 1, C.KEEP_BACKUPS) and prog)
    check("لا شيء متبقٍّ للتحسين", rel not in C.images_to_optimize())


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


def find(pg, label, n=0):
    return [c for c in tree(pg) if getattr(c, "on_click", None) and label in " ".join(texts(c))][n]


def t_versions():
    import re as _re
    import license_core as _lc
    import vault as _vt
    pyv = _re.search(r'^version\s*=\s*"([^"]+)"', open(os.path.join(APP, "pyproject.toml"), encoding="utf-8").read(), _re.M).group(1)
    check("إصدار الوحدات متطابق (core/vault/license_core/pyproject)",
          {C.APP_VERSION, _vt.BUILD, _lc.BUILD, pyv} == {C.APP_VERSION}, f"{C.APP_VERSION}/{_vt.BUILD}/{_lc.BUILD}/{pyv}")
    check("module_mismatch فارغة عند التطابق", C.module_mismatch() == [])
    old = _vt.BUILD
    _vt.BUILD = "2.3.0"
    check("خلط الإصدارات يُكتشف باسم الملف", C.module_mismatch() == ["vault.py"])
    pg = FakePage()
    M.main(pg)
    check("الواجهة تعرض رسالة واضحة بدل الانهيار", any("ملفات غير متطابقة" in " ".join(texts(c)) for c in pg.controls) and
          any("vault.py" in " ".join(texts(c)) for c in pg.controls))
    _vt.BUILD = old


def t_ui():
    images.PIL_OK = False                                               # بلا مصغّرات: نختبر التحميل الكسول
    big = tmpfile(jpeg(1200, 900) if Image else os.urandom(500_000))
    p = C.save_patient(dict(F, full_name="ليلى حسن عمر"), {"photo_before": big, "photo_after": big, "photo_lab": big}, [])
    for i in range(3):
        ev = C.create_event(p["id"], "visit", (dt.datetime.now() + dt.timedelta(days=i + 1)).strftime("%Y-%m-%d"), "10:00")
        C.set_event_photo(ev, "before", big)
        C.set_event_photo(ev, "after", big)
    check("الصور المخزّنة كبيرة وبلا مصغّرات (محاكاة بناء بلا Pillow)",
          C.file_size(p["photo_before"]) > 400_000 and not os.path.exists(C.ap(C.thumb_rel(p["photo_before"]))))
    pg = FakePage()
    M.main(pg)
    f = [c for c in tree(pg) if isinstance(c, ft.TextField)]
    f[0].value, f[1].value = "tester", PW
    find(pg, "دخول").on_click(Ev())
    check("الترحيب يظهر بعد أول دخول", SLEEPS.count(2.0) == 1)
    find(pg, "ابحث عن مريض").on_click(Ev())
    box = [c for c in tree(pg) if isinstance(c, ft.TextField)][0]
    box.value = "ليلى"
    box.on_change(Ev(box))
    find(pg, "فتح الملف").on_click(Ev())

    def holders():
        res = [c for c in tree(pg) if isinstance(c, ft.Container) and getattr(c, "on_click", None) and
               "اضغط للتحميل" in " ".join(texts(c))]
        return [c for c in res if not any(k is not c and k in res for k in walk(c, []))]
    h = holders()
    check("ميزانية الصور الكبيرة: بعض الصور تُحمَّل كسولاً (لا دفعة واحدة)", len(h) == 9 - 6, str(len(h)))
    before = len([c for c in tree(pg) if isinstance(c, ft.Image) and getattr(c, "src_base64", None)])
    h[0].on_click(Ev())
    after = len([c for c in tree(pg) if isinstance(c, ft.Image) and getattr(c, "src_base64", None)])
    check("اللمس يحمّل الصورة ويُلغي الحاضنة", after == before + 1 and h[0].on_click is None)
    images.PIL_OK = True
    # قفل ثم دخول: لا ترحيب ثانٍ
    for _ in range(4):                                                  # رجوع حتى يظهر شريط التنقّل
        if any("الإعدادات" in " ".join(texts(c)) and getattr(c, "on_click", None) for c in tree(pg)):
            break
        pg.appbar.leading.on_click(Ev())
    find(pg, "الإعدادات").on_click(Ev())
    find(pg, "الحساب والأمان").on_click(Ev())
    find(pg, "قفل التطبيق الآن").on_click(Ev())
    f = [c for c in tree(pg) if isinstance(c, ft.TextField)]
    f[0].value, f[1].value = "tester", PW
    find(pg, "دخول").on_click(Ev())
    check("بعد القفل التلقائي/اليدوي لا يتكرر الترحيب", SLEEPS.count(2.0) == 1 and
          any("ابحث عن مريض" in " ".join(texts(c)) for c in pg.controls))
    find(pg, "الإعدادات").on_click(Ev())
    find(pg, "تشخيص الجهاز").on_click(Ev())
    check("شاشة التشخيص تعرض الفحوص", any("✓" in t for c in pg.controls for t in texts(c)))


def main():
    d = C.lic_load()
    C.lic_activate(keygen.issue_activation(d["device_id"], 12, None, "t")["code"])
    C.setup_account("tester", PW)
    t_images()
    t_store_and_wipe()
    t_transaction()
    t_backup_report()
    t_restore_recovery()
    t_share()
    t_log_and_diag()
    t_log_capture()
    t_optimize()
    t_versions()
    t_ui()
    print("\n" + ("ALL PASSED" if not FAILS else f"FAILED: {FAILS}"))
    shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
