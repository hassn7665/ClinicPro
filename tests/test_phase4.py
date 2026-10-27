# -*- coding: utf-8 -*-
"""
اختبارات المرحلة 4 على مستوى التطبيق (core): المبالغ أعداداً صحيحة، قيود CHECK عبر الواجهة البرمجية،
وترقية قاعدة 2.6 الحقيقية (REAL بلا قيود) عند الدخول وعند استعادة نسخة احتياطية قديمة.
التشغيل:   python tests/test_phase4.py        (على نسخة مؤقتة؛ لا يمسّ بياناتك)
"""
import datetime as dt
import os
import shutil
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tests"))
WORK = tempfile.mkdtemp(prefix="clinicpro_p4_")
shutil.copytree(ROOT, os.path.join(WORK, "app"), ignore=shutil.ignore_patterns(
    "admin_keys.json", "issued_log.json", "__pycache__", "shifa_data", "tests", ".git", "build"))
APP = os.path.join(WORK, "app")
os.environ["FLET_APP_STORAGE_DATA"] = os.path.join(WORK, "data")
sys.path.insert(0, APP)
os.chdir(APP)
open(os.path.join(APP, "public_keys.py"), "w").write('SIGN_PUB = ""\nBOX_PUB = ""\n')

import keygen                                       # noqa: E402
keygen.ensure_keys()
import license_core                                 # noqa: E402
license_core.reload_keys()
import core as C                                    # noqa: E402
C.LC.reload_keys()
import migrations as MG                             # noqa: E402
import vault as VT                                  # noqa: E402
import test_migrations as TM                        # noqa: E402
sys.path[:] = [x for x in sys.path if os.path.abspath(x) != ROOT]   # test_migrations يضيف ROOT: يحجب public_keys.py الذي كتبته النسخة المؤقتة

VT.PBKDF2_ITER, VT.RKEY_ITER = 2000, 1000
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


def day(n=0):
    return (dt.date.today() + dt.timedelta(days=n)).strftime("%Y-%m-%d")


def patient(name):
    return C.save_patient(dict(F, full_name=name), {}, [], allow_duplicate=True)


def t_money():
    check("to_minor: تقريب نصف لأعلى بلا أخطاء الفاصلة العائمة", (C.to_minor(2.675), C.to_minor(0.005), C.to_minor(0.1 + 0.2),
                                                                C.to_minor("1,234.56"), C.to_minor(0)) == (268, 1, 30, 123456, 0))
    check("to_minor يرفض السالب وغير المنتهي والنص والضخم", all(raises(lambda v=v: C.to_minor(v), ValueError) for v in
                                                             (-1, float("nan"), float("inf"), "abc", "", 1e13, "1e30")))
    check("from_minor", C.from_minor(123456) == 1234.56 and C.from_minor(None) == 0.0 and C.from_minor(1) == 0.01)
    p = patient("مريض الحساب الدقيق")
    ev = C.create_event(p["id"], "surgery", day(3), "10:00", items=[("عشر مرات 0.1", 0.1, "USD")] * 10 + [("ليرة", 999_999_999.99, "SYP")])
    due, paid, rem = C.fin_totals(p["id"])
    check("10 × 0.1 = 1.00 بالضبط (لا 0.9999999999999999)", due["USD"] == 1.0 and due["SYP"] == 999_999_999.99, str(due))
    check("التخزين أعداد صحيحة فعلاً", {r[0] for r in C.q("SELECT typeof(price_minor) FROM event_items")} == {"integer"})
    for _ in range(9):
        C.add_payments(ev, [(0.1, "USD")])
    check("تسع دفعات 0.1 → متبقٍ 0.10 بالضبط", C.fin_totals(p["id"])[2]["USD"] == 0.1)
    check("الدفعة الأخيرة بالضبط مقبولة (بلا هامش 0.005)", (C.add_payments(ev, [(0.1, "USD")]), C.fin_totals(p["id"])[2]["USD"])[1] == 0.0)
    check("سنت واحد فوق المتبقي مرفوض", raises(lambda: C.add_payments(ev, [(0.01, "USD")]), ValueError))
    pid1 = C.q("SELECT id FROM payments WHERE event_id=? ORDER BY id", (ev,))[0][0]
    check("تعديل دفعة بالضبط إلى سقفها المسموح", (C.edit_payment(pid1, 0.1, "USD"), True)[1] and raises(lambda: C.edit_payment(pid1, 0.11, "USD"), ValueError))
    check("خفض التكلفة تحت المدفوع بسنت مرفوض وبالضبط مقبول",
          raises(lambda: C.update_event(ev, "surgery", day(3), "10:00", [("x", 0.99, "USD"), ("y", 5, "SYP")]), ValueError) and
          (C.update_event(ev, "surgery", day(3), "10:00", [("x", 1.0, "USD")]) is not None))
    check("ev_items / ev_payments تعرض القيمتين", C.ev_items(ev)[0]["price"] == 1.0 and C.ev_items(ev)[0]["price_minor"] == 100 and
          C.ev_payments(ev)[0]["amount"] == 0.1 and C.ev_payments(ev)[0]["amount_minor"] == 10)
    q2 = patient("مريض آلاف الدفعات")
    e2 = C.create_event(q2["id"], "visit", day(1), "09:00", items=[("كشف", 10, "USD")])
    with C.closing(C.db()) as c, c:
        c.executemany("INSERT INTO payments(event_id,amount_minor,cur,paid_at) VALUES(?,?,?,?)",
                      [(e2, 1, "USD", day(0) + "T10:00:00")] * 1000)
    st = C.fin_stats(day(0), day(0))
    check("1000 دفعة × 0.01 = 10.00 بالضبط في الإحصائيات", st["paid"]["USD"] >= 10.0 and
          C.fin_totals(q2["id"])[1]["USD"] == 10.0 and C.fin_totals(q2["id"])[2]["USD"] == 0.0)
    check("ملخص حذف المريض بأعداد صحيحة", C.patient_delete_summary(q2["id"])["paid"]["USD"] == 10.0)
    check("قيد CHECK على مستوى القاعدة: دفعة صفرية وعملة غريبة وموعد بنوع خاطئ",
          raises(lambda: C.x("INSERT INTO payments(event_id,amount_minor,cur) VALUES(?,0,'USD')", (e2,)), sqlite3.IntegrityError) and
          raises(lambda: C.x("INSERT INTO payments(event_id,amount_minor,cur) VALUES(?,5,'EUR')", (e2,)), sqlite3.IntegrityError) and
          raises(lambda: C.x("INSERT INTO events(patient_id,kind,date) VALUES(?,'consult','2026-01-01')", (p["id"],)), sqlite3.IntegrityError))
    check("تواريخ مستحيلة مرفوضة عبر الواجهة البرمجية أيضاً", raises(lambda: C.create_event(p["id"], "visit", "2026-02-30", "10:00"), ValueError))
    check("المخطط بآخر إصدار", C.q("PRAGMA user_version", one=True)[0] == MG.LATEST)


def t_upgrade():
    # قاعدة بمخطط 2.6 الحقيقي (REAL بلا قيود) تحلّ محل الحيّة كأن الإصدار القديم هو من كتبها
    lc = sqlite3.connect(":memory:")
    lc.row_factory = sqlite3.Row
    lc.execute("PRAGMA foreign_keys=ON")
    TM.legacy_26(lc)
    TM.populate(lc)
    live = C._mem["conn"]
    C._mem["conn"] = lc
    legacy_backup = C.make_backup()                                    # نسخة احتياطية بمخطط قديم
    C._persist()
    C.lock_app()                                                       # يحفظ القاعدة القديمة في db.enc
    for f in os.listdir(C.BASE):
        if ".pre_v" in f:
            os.remove(os.path.join(C.BASE, f))
    check("الدخول يرقّي القاعدة القديمة", C.unlock("tester", PW) == "ok" and C.q("PRAGMA user_version", one=True)[0] == MG.LATEST)
    due, paid, rem = C.fin_totals(1)
    check("المبالغ بعد الترقية صحيحة بالسنت", (due["USD"], paid["USD"], rem["USD"]) == (1350.34, 1250.35, 99.99) and due["SYP"] == 3_750_000.0
          and paid["SYP"] == 1_000_000.0, str((due, paid, rem)))
    check("حُفظت نسخة ما قبل الترقية بجانب db.enc", os.path.exists(C.DB_ENC + ".pre_v0"))
    old = C._db_decode(open(C.DB_ENC + ".pre_v0", "rb").read())[1]
    probe = sqlite3.connect(":memory:")
    probe.deserialize(old[1:])                                         # البايت الأول = نوع التسلسل
    check("…وهي قاعدة المخطط القديم سليمة (price REAL)", "price" in [r[1] for r in probe.execute("PRAGMA table_info(event_items)")])
    check("سجل الترقية يحوي الإصدارين", "schema_migrated" in C.LOG.tail(20) and "frm=0" in C.LOG.tail(20))
    old_f = os.path.getmtime(C.DB_ENC + ".pre_v0")
    os.utime(C.DB_ENC + ".pre_v0", (old_f - 40 * 86400, old_f - 40 * 86400))
    C._prune_pre_migration()
    check("نسخة ما قبل الترقية تُمحى بعد 30 يوماً (قد تحوي بيانات حُذفت لاحقاً)", not os.path.exists(C.DB_ENC + ".pre_v0"))
    # استعادة نسخة احتياطية قديمة المخطط
    C.restore_backup(legacy_backup)
    check("استعادة نسخة احتياطية بمخطط قديم تُرقّى تلقائياً", C.q("PRAGMA user_version", one=True)[0] == MG.LATEST and
          C.fin_totals(1)[0]["USD"] == 1350.34)
    live.close()
    # مخطط أحدث من التطبيق
    C._mem["conn"].execute("PRAGMA user_version=99")
    C._persist()
    C.lock_app()
    try:
        C.unlock("tester", PW)
        check("مخطط أحدث من التطبيق يُرفض برسالة واضحة", False)
    except C.VaultError as ex:
        check("مخطط أحدث من التطبيق يُرفض برسالة واضحة", "أحدث" in str(ex) and not C.VAULT.unlocked, str(ex)[:60])
    # نعيده لسلامة بقية الاختبارات: نفتحه بقرار تقني (نخفّض الرقم داخل الملف عبر قاعدة مؤقتة)
    C.VAULT.login("tester", PW)
    gen, plain = C._db_decode(open(C.DB_ENC, "rb").read())
    t = sqlite3.connect(":memory:")
    t.deserialize(plain[1:])
    t.execute("PRAGMA user_version=3")
    C._atomic_write(C.DB_ENC, C._db_encode(b"\x01" + t.serialize(), gen + 1))
    C.VAULT.set_dbgen(gen + 1)
    C.lock_app()
    check("بعد التصحيح يفتح الحساب ثانية", C.unlock("tester", PW) == "ok")


def main():
    d = C.lic_load()
    C.lic_activate(keygen.issue_activation(d["device_id"], 12, None, "t")["code"])
    C.setup_account("tester", PW)
    t_money()
    t_upgrade()
    print("\n" + ("ALL PASSED" if not FAILS else f"FAILED: {FAILS}"))
    shutil.rmtree(WORK, ignore_errors=True)
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
