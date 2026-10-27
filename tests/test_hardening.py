# -*- coding: utf-8 -*-
"""
اختبارات «التحصين» (2.4): سياسة كلمة المرور وترقية الاشتراق، مفتاح الاسترداد والاسترداد عبر المدير، كتابة JSON الذرّية،
قفل التاريخ وكود فكّه، سياسة النسخ الاحتياطي، تشفير مفاتيح المدير، وفحوص الإصدار (check_release / check_apk).
التشغيل:   python tests/test_hardening.py      (يعمل على نسخة مؤقتة ولا يمسّ بياناتك ولا مفاتيحك)
"""
import datetime as dt
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = tempfile.mkdtemp(prefix="clinicpro_hard_")
shutil.copytree(ROOT, os.path.join(WORK, "app"), ignore=shutil.ignore_patterns(
    "admin_keys.json", "issued_log.json", "__pycache__", "shifa_data", "tests", ".git", "build"))
APP = os.path.join(WORK, "app")
os.environ["FLET_APP_STORAGE_DATA"] = os.path.join(WORK, "data")
os.environ.pop("CLINICPRO_ADMIN_PASS", None)
sys.path.insert(0, APP)
os.chdir(APP)
open(os.path.join(APP, "public_keys.py"), "w").write('SIGN_PUB = ""\nBOX_PUB = ""\n')

import keygen                                        # noqa: E402
keygen.ensure_keys()
import license_core as LC                            # noqa: E402
LC.reload_keys()
import core as C                                     # noqa: E402
C.LC.reload_keys()
import vault as VT                                   # noqa: E402

VT.PBKDF2_ITER, VT.RKEY_ITER = 2000, 1000            # لتسريع الاختبارات فقط
FAILS = []
PW = "Pass#Word2026x"


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        FAILS.append(name)


def raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    except Exception:
        return False
    return False


def t_password_policy():
    cases = [("abc12", "", True), ("aaaaaaaaaaaa", "", True), ("1234567890", "", True), ("qwertyuiop", "", True),
             ("abcdefghijk", "", True), ("tester-Pass-99", "Tester", True), ("onlyletters", "", True),
             ("9283746501", "", True), ("Clinic#2026x", "", False), ("onlyletterslong", "", False),
             ("كلمة سر طويلة جدا", "", False), ("7391 Zebra!", "", False)]
    for pw, user, bad in cases:
        check(f"سياسة كلمة المرور: {pw!r} {'مرفوضة' if bad else 'مقبولة'}",
              (VT.password_problem(pw, user) is not None) == bad, str(VT.password_problem(pw, user)))


def t_json_atomic():
    p = os.path.join(WORK, "x.json")
    C.jsave(p, {"n": 1})
    C.jsave(p, {"n": 2})
    open(p, "w").write('{"n": 2, "trunc')                       # تلف كما لو انقطعت الكهرباء
    check("jload يقرأ آخر نسخة سليمة عند تلف الملف", C.jload(p, None) == {"n": 1})
    check("لا ملفات .tmp متبقية", not os.path.exists(p + ".tmp"))
    check("jload يعيد الافتراضي عند غياب الملف", C.jload(os.path.join(WORK, "nope.json"), 7) == 7)


def t_license():
    d = C.lic_load()
    dev, seed = d["device_id"], keygen.load_keys()[0]
    ok, _ = C.lic_activate(keygen.issue_activation(dev, 1, None, "t")["code"])
    check("تفعيل شهر", ok and C.lic_status()[0] == "ok")
    exp0 = C.lic_load()["expires"]

    def lock_clock(days=5):
        d = C.lic_load()
        d["last_seen"] = (dt.datetime.now() + dt.timedelta(days=days)).isoformat()
        C._lic_save(d)
    lock_clock()
    check("تاريخ مضبوط للمستقبل ثم عاد → حالة clock", C.lic_status()[0] == "clock")
    ok, m = C.lic_activate(keygen.issue_clock_fix(dev)["code"])
    check("كود فك التاريخ يفتح القفل", ok and C.lic_status()[0] == "ok", m)
    check("الفك لا يمسّ مدة الاشتراك", C.lic_load()["expires"] == exp0)
    fix = keygen.issue_clock_fix(dev)["code"]
    ok, m = C.lic_activate(fix)
    check("كود الفك لا يُستهلك إن لم يوجد قفل", not ok and C.lic_load()["last_serial"] < LC.parse_code_ex(fix, dev)[0], m)
    lock_clock()
    ok, _ = C.lic_activate(fix)
    check("…ويعمل لاحقاً عند حدوث القفل", ok and C.lic_status()[0] == "ok")
    ok, m = C.lic_activate(fix)
    check("إعادة استخدام كود فك قديم مرفوضة", not ok and "مستخدم" in m)
    lock_clock()
    last = C.lic_load()["last_serial"]
    future = LC.make_code(seed, dev, last + 1, LC.CLOCK_FIX, issued=dt.date.today() + dt.timedelta(days=10))
    ok, m = C.lic_activate(future)
    check("جهاز تاريخه أقدم من تاريخ إصدار الكود لا يستطيع الفك", not ok and C.lic_status()[0] == "clock", m)
    ok, m = C.lic_activate(keygen.issue_activation(dev, 1, None, "renew")["code"])
    exp1 = dt.datetime.fromisoformat(C.lic_load()["expires"])
    check("كود تجديد يفكّ القفل ويُضيف المدة إلى المتبقي",
          ok and C.lic_status()[0] == "ok" and exp1 > dt.datetime.fromisoformat(exp0) + dt.timedelta(days=27), m)
    d = C.lic_load()
    d["expires"] = "2099-01-01T00:00:00"
    C.jsave(C.LIC_PATH, d)                                              # تعديل يدوي بلا إعادة حساب mac
    check("تعديل ملف الترخيص → tampered", C.lic_status()[0] == "tampered")
    ok, _ = C.lic_activate(keygen.issue_clock_fix(dev)["code"])
    check("كود فك التاريخ لا «يبارك» ملفاً معدّلاً", not ok and C.lic_status()[0] == "tampered")
    ok, _ = C.lic_activate(keygen.issue_activation(dev, 1, None, "heal")["code"])
    st = C.lic_status()[0]
    check("كود اشتراك جديد يعالج الملف المعدّل ويتجاهل التاريخ المزوّر",
          ok and st == "ok" and C.lic_load()["expires"][:4] != "2099")
    # ملف تالف تماماً
    for f in (C.LIC_PATH, C.LIC_PATH + ".bak"):
        open(f, "w").write("{broken")
    new_dev = C.lic_load()["device_id"]
    check("ملف ترخيص تالف يُحفظ للفحص (.corrupt) ولا يُمحى بصمت", os.path.exists(C.LIC_PATH + ".corrupt") and new_dev)
    # تقليل الكتابات
    d = C.lic_load()
    before = os.path.getmtime(C.LIC_PATH)
    time.sleep(0.05)
    C.lic_status()
    check("lic_status لا يعيد كتابة الملف عند كل استدعاء", os.path.getmtime(C.LIC_PATH) == before)
    return keygen.issue_activation(new_dev, 12, None, "again")["code"]


def t_vault(code):
    ok, _ = C.lic_activate(code)
    rkey = C.setup_account("tester", PW)
    check("إنشاء الحساب يعيد مفتاح استرداد مجمّعاً", isinstance(rkey, str) and rkey.count("-") >= 4)
    check("الحساب الجديد: مفتاح استرداد + اعتماد المدير مفعّلان", C.VAULT.has_recovery_key and C.VAULT.escrow_enabled)
    p = C.save_patient(dict(full_name="سارة أحمد خليل", gender="أنثى", age=28, residence="حلب", phone="0944", job="معلمة",
                            diseases="لا", notes="", blood="A+", status="جديد"), {}, [])
    check("مفتاح الاسترداد يقبل أحرفاً صغيرة وبلا شرطات",
          VT.unwrap_with_recovery_key(C.VAULT.h, rkey.lower().replace("-", "")) == C.VAULT.dek)
    check("مفتاح استرداد خاطئ مرفوض", VT.unwrap_with_recovery_key(C.VAULT.h, "AAAAA-AAAAA-AAAAA-AAAAA-AAAAA-AAA") is None)
    # ترقية الاشتقاق
    VT.PBKDF2_ITER = 3000
    C.lock_app()
    check("الدخول بعد رفع عدد الدورات يعمل", C.unlock("tester", PW) == "ok")
    check("الترويسة رُقّيت إلى الدورات الجديدة وتُحفظ", json.load(open(C.VAULT.path))["iter"] == 3000)
    C.lock_app()
    check("الدخول بعد الترقية ما زال يعمل", C.unlock("tester", PW) == "ok")
    # سقف iter
    t0 = time.time()
    hdr = dict(C.VAULT.public_header(), iter=10 ** 9)
    check("ترويسة بـ iter ضخم تُرفض فوراً", VT.unwrap_with_password(hdr, PW) is None and time.time() - t0 < 1)
    # قفل ثم الاسترداد بالمفتاح
    C.lock_app()
    for _ in range(VT.FREE_ATTEMPTS):
        C.unlock("tester", "wrong-pass-123")
    check("بعد المحاولات المجانية يبدأ تأخير الدخول", C.VAULT.locked_out)
    check("مفتاح خاطئ لا يفتح القفل", raises(lambda: C.reset_with_recovery_key("AAAAA-AAAAA", "New#Pass2027abc"), VT.VaultError)
          and C.VAULT.locked_out)
    check("كلمة جديدة ضعيفة مرفوضة عند الاسترداد", raises(lambda: C.reset_with_recovery_key(rkey, "12345"), VT.VaultError))
    C.reset_with_recovery_key(rkey, "New#Pass2027abc")
    check("الاسترداد بالمفتاح يمسح القفل ويفتح الحساب", not C.VAULT.locked_out and C.VAULT.unlocked)
    C.lock_app()
    check("كلمة المرور القديمة لم تعد تعمل", C.unlock("tester", PW) == "bad")
    check("الكلمة الجديدة تعمل والبيانات سليمة",
          C.unlock("tester", "New#Pass2027abc") == "ok" and C.q("select count(*) from patients")[0][0] == 1)
    check("بيانات المريض تُقرأ بعد الاسترداد", C.q("select full_name from patients")[0][0].startswith("سارة"))
    # مفتاح جديد يبطل القديم
    new_rk = C.create_recovery_key()
    check("تجديد المفتاح يبطل القديم",
          VT.unwrap_with_recovery_key(C.VAULT.h, rkey) is None and VT.unwrap_with_recovery_key(C.VAULT.h, new_rk))
    # الاسترداد عبر المدير
    C.set_escrow(False)
    check("إيقاف اعتماد المدير: لا رمز طلب", not C.VAULT.escrow_enabled and raises(C.reset_request_code, VT.VaultError))
    check("ترويسة النسخ الاحتياطي لا تحمل غلاف المدير", C.VAULT.public_header()["recovery"] == "")
    C.set_escrow(True)
    check("إعادة التفعيل: يعمل رمز الطلب", C.VAULT.escrow_enabled and len(C.reset_request_code()) > 50)
    h_backup = dict(C.VAULT.h)
    C.VAULT.h.pop("rk")
    check("لا يمكن إيقاف اعتماد المدير بلا مفتاح استرداد", raises(lambda: C.set_escrow(False), VT.VaultError))
    C.VAULT.h.clear()
    C.VAULT.h.update(h_backup)
    v2 = VT.Vault(os.path.join(WORK, "v2"))
    os.makedirs(v2.path.rsplit(os.sep, 1)[0], exist_ok=True)
    rk2 = v2.create("clinic2", "Long#Pass12345", C.LC.box_pub(), escrow=False)
    check("حساب بلا اعتماد مدير (escrow=False) له مفتاح استرداد فقط",
          not v2.escrow_enabled and v2.has_recovery_key and rk2 and v2.public_header()["recovery"] == "")
    return new_rk


def t_backups(rkey):
    C.KEEP_BACKUPS = 3
    for _ in range(5):
        C.make_backup()
    names = C.list_backups()
    check("الاحتفاظ بآخر N نسخة فقط", len(names) == 3, str(len(names)))
    hdr, _ = C._bk_header(os.path.join(C.BK_DIR, names[0]))
    check("مفتاح الاسترداد يفتح DEK من ترويسة نسخة احتياطية", VT.unwrap_with_recovery_key(hdr, rkey) == C.VAULT.dek)
    oldest = os.path.join(C.BK_DIR, names[-1])
    C.restore_backup(oldest, "")
    check("استعادة أقدم نسخة في المجلد لا تحذف مصدرها قبل النجاح والبيانات سليمة",
          C.q("select count(*) from patients")[0][0] == 1)
    orig = C.backup_needs_password
    C.backup_needs_password = lambda p: True
    try:
        C.restore_backup(os.path.join(C.BK_DIR, C.list_backups()[0]), rkey)
        check("الاستعادة تقبل مفتاح الاسترداد بدل كلمة المرور", True)
    except Exception as ex:
        check("الاستعادة تقبل مفتاح الاسترداد بدل كلمة المرور", False, str(ex))
    check("استعادة بسرّ خاطئ مرفوضة", raises(lambda: C.restore_backup(os.path.join(C.BK_DIR, C.list_backups()[0]), "nope"), ValueError))
    C.backup_needs_password = orig
    # الجدولة والتصدير
    st = C.jload(C.SET_PATH, {})
    st["last_backup"] = (dt.datetime.now() - dt.timedelta(days=C.BACKUP_EVERY_DAYS + 1)).isoformat()
    C.jsave(C.SET_PATH, st)
    before = set(C.list_backups())
    C.auto_backup_if_due()
    check("نسخة تلقائية بعد مرور الأسبوع", set(C.list_backups()) != before)
    before = set(C.list_backups())
    C.auto_backup_if_due()
    check("لا نسخة جديدة قبل موعدها", set(C.list_backups()) == before)
    st = C.jload(C.SET_PATH, {})
    st.pop("last_export", None)
    C.jsave(C.SET_PATH, st)
    check("تذكير التصدير مستحق قبل أول تصدير", C.export_due() == (True, None))
    C.mark_exported()
    check("بعد التصدير لا تذكير", C.export_due() == (False, 0))
    st = C.jload(C.SET_PATH, {})
    st["last_export"] = (dt.datetime.now() - dt.timedelta(days=C.EXPORT_REMIND_DAYS + 6)).isoformat()
    C.jsave(C.SET_PATH, st)
    check("التذكير يعود بعد المدة", C.export_due()[0] is True)


def t_admin_keys():
    k = keygen._read_keys_file()
    check("المفاتيح تُولَّد نصاً قابلاً للحماية (توليد تلقائي)", "sign_seed" in k)
    seed0 = keygen.load_keys()[0]
    keygen.protect_keys("correct horse battery staple")
    disk = open(keygen.KEYS, encoding="utf-8").read()
    check("admin_keys.json المحمي لا يحوي المفاتيح الخاصة نصاً", seed0.hex() not in disk and keygen.keys_protected())
    check("ensure_keys لا يطلب العبارة بعد الحماية", keygen.ensure_keys() == "ok")
    keygen._PASS["v"] = None
    os.environ["CLINICPRO_ADMIN_PASS"] = "wrong passphrase value"
    check("عبارة خاطئة ترفض إصدار الأكواد", raises(lambda: keygen.issue_activation("3fa91c07", 1), SystemExit))
    keygen._PASS["v"] = None
    os.environ["CLINICPRO_ADMIN_PASS"] = "correct horse battery staple"
    check("العبارة الصحيحة تُصدر كوداً صالحاً", LC.parse_code(keygen.issue_activation("3fa91c07", 1)["code"], "3fa91c07")[1] == 1)
    check("عبارة قصيرة مرفوضة", raises(lambda: keygen.protect_keys("short"), ValueError))
    os.environ.pop("CLINICPRO_ADMIN_PASS")


def t_release_tools():
    if shutil.which("git"):
        r = os.path.join(WORK, "repo")
        os.makedirs(os.path.join(r, "tools"))
        for f in ("pyproject.toml", ".gitignore"):
            shutil.copy(os.path.join(ROOT, f), r)
        shutil.copy(os.path.join(ROOT, "tools", "check_release.py"), os.path.join(r, "tools"))
        open(os.path.join(r, "public_keys.py"), "w").write(f'SIGN_PUB = "{"ab" * 32}"\nBOX_PUB = "{"cd" * 32}"\n')
        g = lambda *a: subprocess.run(["git", *a], cwd=r, capture_output=True, text=True)
        g("init", "-q")
        g("add", "-A")
        run = lambda: subprocess.run([sys.executable, "tools/check_release.py"], cwd=r, capture_output=True, text=True)
        check("check_release يمرّ على مستودع سليم", run().returncode == 0, run().stdout)
        open(os.path.join(r, "admin_keys.json"), "w").write("{}")
        g("add", "-f", "admin_keys.json")
        out = run()
        check("check_release يفشل إن رُفع admin_keys.json", out.returncode == 1 and "admin_keys.json" in out.stdout)
        g("rm", "-f", "--cached", "admin_keys.json")
        open(os.path.join(r, "public_keys.py"), "w").write('SIGN_PUB = ""\nBOX_PUB = ""\n')
        check("check_release يفشل إن كان public_keys.py فارغاً", run().returncode == 1)
    else:
        print("SKIP check_release (git غير متوفر)")
    chk = os.path.join(ROOT, "tools", "check_apk.py")

    def make_apk(path, inner_files):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for n in inner_files:
                z.writestr(n, "x")
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("AndroidManifest.xml", "x")
            z.writestr("assets/flutter_assets/app/app.zip", buf.getvalue())
    good, bad = os.path.join(WORK, "good.apk"), os.path.join(WORK, "bad.apk")
    make_apk(good, ["main.py", "core.py"])
    make_apk(bad, ["main.py", "keygen.py", "admin_keys.json"])
    check("check_apk يقبل حزمة نظيفة", subprocess.run([sys.executable, chk, good], capture_output=True).returncode == 0)
    out = subprocess.run([sys.executable, chk, bad], capture_output=True, text=True)
    check("check_apk يرفض حزمة فيها keygen/admin_keys", out.returncode == 1 and "keygen.py" in out.stdout)


def main():
    t_password_policy()
    t_json_atomic()
    code = t_license()
    rk = t_vault(code)
    t_backups(rk)
    t_admin_keys()
    t_release_tools()
    print("\n" + ("ALL PASSED" if not FAILS else f"FAILED: {FAILS}"))
    shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
