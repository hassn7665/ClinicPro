# -*- coding: utf-8 -*-
"""
اختبارات المرحلة 3 (الأمان المتقدم، الإصدار 2.6): تأخير الدخول المتصاعد، ربط التشفير بمسار الملف (AAD)،
جيل القاعدة وكشف إرجاعها، القفل عند الذهاب للخلفية، وتحقق keygen من الجهاز عند إعادة التعيين.
التشغيل:   python tests/test_phase3.py        (على نسخة مؤقتة؛ لا يمسّ بياناتك)
"""
import json
import os
import shutil
import struct
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="clinicpro_p3_")
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
import crypto_core as K                             # noqa: E402
import vault as VT                                  # noqa: E402
import main as M                                    # noqa: E402

VT.PBKDF2_ITER, VT.RKEY_ITER = 2000, 1000
CLOCK = [1_000_000.0]
VT._now = lambda: CLOCK[0]
FAILS = []
PW = "Pass#Word2026x"
F = dict(gender="أنثى", age=30, residence="حلب", job="معلمة", diseases="لا", notes="", blood="A+", status="جديد", phone="")


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


def tmpfile(data, suffix=".pdf"):
    p = tempfile.mktemp(suffix=suffix, dir=WORK)
    open(p, "wb").write(data)
    return p


def patient(name, **kw):
    return C.save_patient(dict(F, full_name=name, **kw), {}, [], allow_duplicate=True)


# ───────────── تأخير الدخول المتصاعد ─────────────
def t_delay():
    check("جدول التأخير", [VT.delay_for(n) for n in range(0, 10)] == [0, 0, 0, 15, 30, 60, 300, 900, 3600, 3600])
    C.lock_app()
    for i in range(2):
        r = C.unlock("tester", "wrong-pass-1")
    check("محاولتان خاطئتان: لا تأخير", r == "bad" and C.VAULT.wait_seconds == 0 and C.VAULT.attempts_left == 1)
    r = C.unlock("tester", "wrong-pass-1")
    check("الثالثة الخاطئة: تأخير 15 ثانية", r == "bad" and C.VAULT.wait_seconds == 15)
    check("كلمة المرور الصحيحة أثناء الانتظار ترجع 'wait' ولا تفتح", C.unlock("tester", PW) == "wait" and not C.VAULT.unlocked)
    check("المحاولة أثناء الانتظار لا تُحتسب", C.VAULT.h["attempts"] == 3)
    CLOCK[0] += 10
    check("الانتظار ينقص مع الوقت", C.VAULT.wait_seconds == 5)
    v2 = VT.Vault(C.BASE)
    check("التأخير يبقى بعد إعادة تشغيل التطبيق (محفوظ على القرص)", v2.wait_seconds == 5)
    CLOCK[0] += 6
    check("بعد انتهاء المدة تُقبل المحاولة", C.VAULT.wait_seconds == 0)
    expected = [30, 60, 300, 900, 3600, 3600]
    got = []
    for _ in expected:
        C.unlock("tester", "wrong-pass-1")
        got.append(C.VAULT.wait_seconds)
        CLOCK[0] += C.VAULT.wait_seconds + 1
    check("التأخير يتصاعد: 30 ث، دقيقة، 5 د، 15 د، ساعة (سقف)", got == expected, str(got))
    C.unlock("tester", "wrong-pass-1")
    last = C.VAULT.wait_seconds
    CLOCK[0] -= 5000                                                  # إرجاع ساعة الجهاز للوراء
    check("إرجاع الساعة للوراء لا يختصر الانتظار", C.VAULT.wait_seconds >= VT.delay_for(C.VAULT.h["attempts"]) and last == 3600)
    CLOCK[0] += 5000 + 3601
    check("الدخول الصحيح بعد الانتظار يفتح ويصفّر العدّاد", C.unlock("tester", PW) == "ok" and C.VAULT.h["attempts"] == 0
          and C.VAULT.wait_seconds == 0 and C.VAULT.unlocked)
    # ترحيل قفل صلب قديم
    h = json.load(open(C.VAULT.path))
    h.update(locked=True, attempts=5)
    json.dump(h, open(C.VAULT.path, "w"))
    v3 = VT.Vault(C.BASE)
    check("قفل صلب قديم يتحول إلى تأخير (بلا حاجة للمدير)", not v3.h["locked"] and v3.wait_seconds == 60)
    CLOCK[0] += 61
    check("…ويمكن الدخول بعد انتهائه", v3.login("tester", PW) == "ok")
    C.VAULT.h["attempts"] = 0


# ───────────── AAD بمسار الملف ─────────────
def t_aad():
    C.lock_app()
    check("إعادة الدخول", C.unlock("tester", PW) == "ok")
    a, b = tmpfile(b"AAA-secret-A"), tmpfile(b"BBB-secret-B")
    pa = C.save_patient(dict(F, full_name="مريض ألف الأول"), {}, [a], allow_duplicate=True)
    pb = C.save_patient(dict(F, full_name="مريض باء الثاني"), {}, [b], allow_duplicate=True)
    ra = C.q("select path from attachments where patient_id=?", (pa["id"],), one=True)[0]
    rb = C.q("select path from attachments where patient_id=?", (pb["id"],), one=True)[0]
    check("القراءة المشروعة تعمل", C.read_file(ra) == b"AAA-secret-A" and C.read_file(rb) == b"BBB-secret-B")
    raw_a = open(C.ap(ra), "rb").read()
    check("أول بايتات الملف قياسية SHF1", raw_a[:4] == b"SHF1")
    shutil.copyfile(C.ap(ra), C.ap(rb))                                # تبديل: ملف مريض ألف مكان ملف باء
    check("ملف منسوخ إلى مسار آخر يفشل التحقق منه", raises(lambda: C.read_file(rb), K.CryptoError))
    check("…ولا يكشف محتواه عبر العرض", raises(lambda: C.file_b64(rb), K.CryptoError))
    # مصغّرة
    shutil.copyfile(C.ap(ra), C.ap(C.thumb_rel(rb)))
    check("تبديل المصغّرة أيضاً يُكتشف", raises(lambda: C.read_file(C.thumb_rel(rb)), K.CryptoError))
    os.remove(C.ap(C.thumb_rel(rb)))
    # ترحيل ملفات قديمة (aad=file)
    legacy_rel = f"patients/{pa['code']}/{'ab' * 8}.bin"
    open(C.ap(legacy_rel), "wb").write(K.encrypt_blob(C.VAULT.dek, b"legacy-bytes", aad=b"file"))
    C.x("INSERT INTO attachments(patient_id,path,name) VALUES(?,?,?)", (pa["id"], legacy_rel, "legacy.pdf"))   # مرجع في القاعدة (لا يتيم)
    st = C.jload(C.SET_PATH, {})
    st.pop("aad_v", None)
    C.jsave(C.SET_PATH, st)
    C._mem["aad_legacy"] = True
    check("ملف قديم (aad=file) يُقرأ أثناء الترحيل", C.read_file(legacy_rel) == b"legacy-bytes")
    C._migrate_file_aad()
    check("الترحيل أعاد تشفيره بـAAD المسار وأغلق المسار القديم",
          C.jload(C.SET_PATH, {}).get("aad_v") == 2 and not C._mem["aad_legacy"] and C.read_file(legacy_rel) == b"legacy-bytes")
    raw = open(C.ap(legacy_rel), "rb").read()
    check("…ولا يعمل ملف بـaad=file بعد إغلاق المسار", (open(C.ap(legacy_rel), "wb").write(
        K.encrypt_blob(C.VAULT.dek, b"x", aad=b"file")) and raises(lambda: C.read_file(legacy_rel), K.CryptoError)))
    open(C.ap(legacy_rel), "wb").write(raw)
    # نسخة احتياطية واستعادة تحافظان على القراءة بالمسار الجديد
    path = C.make_backup()
    C.restore_backup(path)
    check("استعادة نسخة احتياطية: ملف مريض يُقرأ بـAAD مساره", C.read_file(ra) == b"AAA-secret-A")
    check("…وملف قديم سليم بعد الاستعادة", C.read_file(legacy_rel) == b"legacy-bytes")
    C.delete_patient(pa["id"])
    C.delete_patient(pb["id"])


# ───────────── جيل القاعدة وكشف الإرجاع ─────────────
def t_db_generation():
    patient("مريض جيل أول")
    blob = open(C.DB_ENC, "rb").read()
    gen = struct.unpack(">Q", blob[4:12])[0]
    check("db.enc بصيغة SHD1 والجيل مطابق للمسجّل", blob[:4] == b"SHD1" and gen == C._mem["gen"] == C.VAULT.dbgen and gen > 0, str(gen))
    old_blob = blob
    n_old = C.q("select count(*) from patients")[0][0]
    patient("مريض جيل ثان")
    patient("مريض جيل ثالث")
    check("كل حفظ يرفع الجيل", C.VAULT.dbgen > gen)
    C.lock_app()
    open(C.DB_ENC, "wb").write(old_blob)                                # إرجاع القاعدة لنسخة أقدم
    try:
        C.unlock("tester", PW)
        check("إرجاع db.enc يُكتشف", False)
    except C.RollbackError as ex:
        check("إرجاع db.enc يُكتشف مع الجيلين", ex.got == gen and ex.expected > gen and not C.VAULT.unlocked)
    check("الإرجاع لا يمرّ دون قرار صريح (يتكرر الرفض)", raises(lambda: C.unlock("tester", PW), C.RollbackError))
    check("بقرار المستخدم: تُفتح القاعدة الأقدم وتصبح الأساس", C.unlock("tester", PW, accept_rollback=True) == "ok"
          and C.q("select count(*) from patients")[0][0] == n_old and gen <= C.VAULT.dbgen < gen + 3)
    patient("مريض بعد القبول")
    C.lock_app()
    check("بعد القبول يعمل الدخول العادي", C.unlock("tester", PW) == "ok")
    # تعديل حقل الجيل في الترويسة يُكتشف (مربوط بالمصادقة)
    C.lock_app()
    b = bytearray(open(C.DB_ENC, "rb").read())
    b[11] ^= 1
    good = bytes(open(C.DB_ENC, "rb").read())
    open(C.DB_ENC, "wb").write(bytes(b))
    check("تعديل الجيل داخل الملف يفشل التحقق", raises(lambda: C.unlock("tester", PW), C.VaultError)
          and not C.VAULT.unlocked)
    open(C.DB_ENC, "wb").write(good)
    # صيغة قديمة
    C.unlock("tester", PW)
    legacy = K.encrypt_blob(C.VAULT.dek, C._serialize(C._mem["conn"]), aad=b"db")
    n_now = C.q("select count(*) from patients")[0][0]
    C.lock_app()
    open(C.DB_ENC, "wb").write(legacy)
    C.VAULT.h["dbgen"] = 0
    C.VAULT._save()
    check("قاعدة بالصيغة القديمة (SHF1) تُفتح", C.unlock("tester", PW) == "ok" and C.q("select count(*) from patients")[0][0] == n_now)
    patient("مريض يرقّي الصيغة")
    check("أول حفظ يرقّيها إلى SHD1", open(C.DB_ENC, "rb").read()[:4] == b"SHD1")
    # انقطاع بين كتابة القاعدة وتسجيل الجيل: القاعدة أحدث من المسجّل = مقبولة
    C.lock_app()
    b = open(C.DB_ENC, "rb").read()
    g = struct.unpack(">Q", b[4:12])[0]
    C.VAULT.h["dbgen"] = g - 1
    C.VAULT._save()
    check("القاعدة أحدث من المسجّل (انقطاع بعد الكتابة) تُقبل وتُصلح السجل", C.unlock("tester", PW) == "ok")
    patient("مريض بعد الإصلاح")
    check("السجل صار ≥ الجيل", C.VAULT.dbgen >= g)
    # الاستعادة من نسخة أقدم لا تُعدّ إرجاعاً
    path = C.make_backup()
    patient("مريض بعد النسخة")
    C.restore_backup(path)
    C.lock_app()
    check("استعادة نسخة أقدم ثم دخول: لا إنذار إرجاع", C.unlock("tester", PW) == "ok")


# ───────────── الواجهة ─────────────
class Ev:
    def __init__(s, c=None, data=None):
        s.control, s.files, s.data = c, None, data


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


def find(pg, label, n=0):
    return [c for c in tree(pg) if getattr(c, "on_click", None) and label in " ".join(texts(c))][n]


def login(pg, pw=PW):
    f = [c for c in tree(pg) if isinstance(c, ft.TextField)]
    f[0].value, f[1].value = "tester", pw
    find(pg, "دخول").on_click(Ev())


def life(pg, state):
    pg.on_app_lifecycle_state_change(Ev(data=f"AppLifecycleState.{state}"))


def on_login_screen(pg):
    return any(isinstance(c, ft.TextField) and "كلمة المرور" in (c.label or "") for c in tree(pg))


def t_ui_login_delay():
    C.lock_app()
    C.VAULT.h.update(attempts=0, next_try=0, last_try=0)
    pg = FakePage()
    M.main(pg)
    for _ in range(3):
        login(pg, "wrong-pass-1")
    check("الواجهة: بعد 3 محاولات خاطئة تعرض مدة الانتظار", "حاول بعد" in alltext(pg) and "15 ثانية" in alltext(pg), alltext(pg)[:120])
    calls = []
    real = C.unlock
    C.unlock = lambda *a, **k: (calls.append(1), real(*a, **k))[1]
    login(pg, PW)
    C.unlock = real
    check("أثناء الانتظار لا يُشغَّل الاشتقاق ولا يُفتح الحساب", not calls and not C.VAULT.unlocked and "حاول بعد" in alltext(pg))
    pg2 = FakePage()
    M.main(pg2)
    check("إعادة تشغيل التطبيق أثناء الانتظار تعرض الرسالة من البداية", "حاول بعد" in alltext(pg2))
    CLOCK[0] += 20
    login(pg2, PW)
    check("بعد انتهاء الانتظار يدخل", C.VAULT.unlocked)
    # حوار الإرجاع
    C.lock_app()
    good = open(C.DB_ENC, "rb").read()
    old_gen = C.VAULT.dbgen
    C.VAULT.h["dbgen"] = old_gen + 5
    C.VAULT._save()
    pg3 = FakePage()
    M.main(pg3)
    login(pg3)
    check("الواجهة: حوار «القاعدة أقدم من آخر حفظ»", pg3.opened and "القاعدة أقدم" in " ".join(texts(pg3.opened[-1])) and not C.VAULT.unlocked)
    [c for c in walk(pg3.opened[-1], []) if getattr(c, "on_click", None) and "رغم ذلك" in " ".join(texts(c))][0].on_click(Ev())
    check("«فتح القاعدة الحالية رغم ذلك» يفتحها ويعتمدها أساساً", C.VAULT.unlocked and old_gen <= C.VAULT.dbgen < old_gen + 3)
    return pg3


def t_ui_background_lock():
    import ui_kit as UK
    stub = types.SimpleNamespace(time=lambda: CLOCK[0], sleep=lambda *a: None)
    real_time, M.time = M.time, stub
    real_uk_time, UK.time = UK.time, stub                              # نافذة «التدفق الخارجي» تُقاس بالساعة نفسها
    try:
        C.set_lock_policy(0)
        check("سياسة القفل الافتراضية/المضبوطة", C.lock_policy() == 0 and raises(lambda: C.set_lock_policy(7), ValueError))
        pg = FakePage()
        M.main(pg)
        login(pg)
        check("مسجّل الدخول", C.VAULT.unlocked)
        life(pg, "inactive")
        check("حالة inactive (إشعار/نافذة نظام) لا تقفل", C.VAULT.unlocked)
        life(pg, "paused")
        check("الخروج للخلفية يقفل فوراً (الذاكرة والواجهة)", not C.VAULT.unlocked and C.VAULT.dek is None and on_login_screen(pg))
        life(pg, "resumed")
        login(pg)
        check("العودة ثم الدخول يعمل", C.VAULT.unlocked)
        # تدفق خارجي (طباعة): لا قفل فوري
        p = patient("مريض للطباعة")
        find_search = [c for c in tree(pg) if getattr(c, "on_click", None) and "ابحث عن مريض" in " ".join(texts(c))]
        find_search[0].on_click(Ev())
        box = [c for c in tree(pg) if isinstance(c, ft.TextField)][0]
        box.value = "مريض للطباعة"
        box.on_change(Ev(box))
        find(pg, "فتح الملف").on_click(Ev())
        [c for c in tree(pg) if getattr(c, "on_click", None) and "طباعة" in " ".join(texts(c))][0].on_click(Ev())
        check("الطباعة فتحت رابطاً محلياً", pg.launched)
        life(pg, "paused")
        check("الخروج بسبب تدفق خارجي (طباعة) لا يقفل فوراً", C.VAULT.unlocked)
        CLOCK[0] += 60
        life(pg, "resumed")
        check("…والعودة خلال 3 دقائق تبقيه مفتوحاً", C.VAULT.unlocked)
        life(pg, "paused")
        CLOCK[0] += 240
        life(pg, "resumed")
        check("…أما الغياب الطويل بعد تدفق خارجي فيقفل", not C.VAULT.unlocked and on_login_screen(pg))
        login(pg)
        # سياسة 180 ثانية
        C.set_lock_policy(180)
        life(pg, "paused")
        check("سياسة 3 دقائق: لا قفل عند الخروج", C.VAULT.unlocked)
        CLOCK[0] += 100
        life(pg, "resumed")
        check("…ولا عند العودة قبل المهلة", C.VAULT.unlocked)
        life(pg, "paused")
        CLOCK[0] += 200
        life(pg, "resumed")
        check("…ويقفل بعد المهلة", not C.VAULT.unlocked)
        C.set_lock_policy(0)
        login(pg)
        # واجهة الإعداد
        [c for c in tree(pg) if getattr(c, "on_click", None) and "الإعدادات" in " ".join(texts(c))][0].on_click(Ev())
        find(pg, "الحساب والأمان").on_click(Ev())
        check("خيار القفل عند الخلفية ظاهر في الحساب والأمان", "القفل عند الذهاب للخلفية" in alltext(pg) and "فوراً" in alltext(pg))
    finally:
        M.time = real_time
        UK.time = real_uk_time


# ───────────── keygen: التحقق من الجهاز عند الاسترداد ─────────────
def t_keygen_reset():
    dev = C.lic_load()["device_id"]
    C.VAULT.h["pending"] = None
    C.set_escrow(True)
    req = C.reset_request_code()
    keygen.write_log([])
    try:
        keygen.issue_reset(req)
        check("جهاز بلا سجل تفعيل يُرفض", False)
    except keygen.UnknownDevice as ex:
        check("جهاز بلا سجل تفعيل يُرفض باسم الجهاز", ex.device == dev and dev.upper() in str(ex))
    check("…ولا يُسجَّل شيء عند الرفض", keygen.read_log() == [])
    rec = keygen.issue_reset(req, note="تحقق هاتفي", force=True)
    check("التجاوز الصريح يصدر الرمز ويُوسَم «غير معروف»", rec["known"] is False and "جهاز غير معروف" in keygen.describe(rec))
    keygen.issue_activation(dev, 3, None, "عيادة الشفاء")
    rec = keygen.issue_reset(req, note="تحقق هاتفي")
    d = keygen.describe(rec)
    check("جهاز معروف: يصدر ويُرفق باسم العميل وتاريخ آخر تفعيل", rec["known"] and "عيادة الشفاء" in d and "آخر تفعيل" in d)
    # الرمز نفسه صالح فعلاً
    C.lock_app()
    C.reset_with_code(rec["code"], "Brand#New2027pw")
    check("الرمز الصادر يفتح الحساب (سلامة الدورة كاملة)", C.VAULT.unlocked and C.q("select count(*) from patients")[0][0] > 0)
    keygen.issue_clock_fix(dev)
    check("سجل clockfix يُحسب تفعيلاً معروفاً", keygen.device_history(dev) != [])


def main():
    d = C.lic_load()
    C.lic_activate(keygen.issue_activation(d["device_id"], 12, None, "t")["code"])
    C.setup_account("tester", PW)
    patient("مريض أولي")
    t_delay()
    t_aad()
    t_db_generation()
    t_ui_login_delay()
    t_ui_background_lock()
    t_keygen_reset()
    print("\n" + ("ALL PASSED" if not FAILS else f"FAILED: {FAILS}"))
    shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
