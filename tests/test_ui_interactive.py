# -*- coding: utf-8 -*-
"""
اختبارات تفاعلية: «ننقر» الأزرار الحساسة كما يفعل المستخدم (إلغاء، لم يحضر، تأكيد مع دفعة، حذف موعد/مريض، نموذج المريض،
الدخول) ثم نتحقق من النتيجة **في القاعدة** لا من الشكل فقط.   تشغيل: python tests/test_ui_interactive.py
"""
import datetime as dt
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import boot_core, make_account  # noqa: E402
from ui_driver import Driver  # noqa: E402

PW = "Correct-Horse-9"


def day(n):
    return (dt.date.today() + dt.timedelta(days=n)).strftime("%Y-%m-%d")


class UiBase(unittest.TestCase):
    def setUp(self):
        self.C, self.tmp = boot_core("ui")
        make_account(self.C, password=PW)
        d = self.C.lic_load()
        d["expires"] = (dt.datetime.now() + dt.timedelta(days=30)).isoformat()
        self.C._lic_save(d)
        self.pid = self.C.save_patient(dict(full_name="سلمى أحمد حسن", gender="أنثى", age=30, residence="", phone="0944111222",
                                            job="", diseases="", notes="", blood="", status="جديد"), {}, [])["id"]
        self.ui = Driver()

    def status(self, eid):
        return self.C.q("SELECT status FROM events WHERE id=?", (eid,), one=True)[0]

    def row(self, eid):
        return self.C.q("SELECT * FROM events WHERE id=?", (eid,), one=True)

    def open_patient(self):
        self.ui.page.opened.clear()
        self.ui.s.patient_screen(self.pid)


class AppointmentButtons(UiBase):
    def test_cancel_with_reason_then_reinstate(self):
        C, ui = self.C, self.ui
        eid = C.create_event(self.pid, "visit", day(3), "10:00", items=[("كشف", 100000, "SYP")])
        self.open_patient()
        ui.click("إلغاء الموعد")                                   # زر البطاقة → حوار السبب
        ui.type("سبب الإلغاء (اختياري)", "اعتذر المريض")
        ui.click_dialog("إلغاء الموعد")
        r = self.row(eid)
        self.assertEqual((r["status"], r["cancel_reason"]), ("cancelled", "اعتذر المريض"))
        self.assertIsNotNone(r["cancelled_at"])
        self.assertEqual(C.fin_totals(self.pid)[0]["SYP"], 0)       # لا يُحتسب في المستحقات
        self.assertTrue(ui.has_text("مواعيد ملغاة"))
        ui.click("استعادة الموعد")
        r = self.row(eid)
        self.assertEqual((r["status"], r["cancelled_at"], r["cancel_reason"]), ("pending", None, None))
        self.assertEqual(C.fin_totals(self.pid)[0]["SYP"], 100000)

    def test_cancel_blocked_when_payments_exist(self):
        C, ui = self.C, self.ui
        eid = C.create_event(self.pid, "visit", day(3), "10:00", items=[("كشف", 100000, "SYP")])
        C.add_payments(eid, [(50000, "SYP")])
        self.open_patient()
        ui.click("إلغاء الموعد")
        ui.click_dialog("إلغاء الموعد")
        self.assertEqual(self.status(eid), "pending")                # لم يتغير شيء
        self.assertTrue(any("دفعات" in t for t in ui.toasts), ui.toasts)

    def test_dialog_back_button_changes_nothing(self):
        eid = self.C.create_event(self.pid, "visit", day(3), "10:00")
        self.open_patient()
        self.ui.click("إلغاء الموعد")
        self.ui.click_dialog("تراجع")
        self.assertEqual(self.status(eid), "pending")

    def test_no_show_only_for_past_appointments(self):
        C, ui = self.C, self.ui
        future = C.create_event(self.pid, "visit", day(2), "10:00")
        self.open_patient()
        self.assertEqual(ui.count("لم يحضر"), 0)                    # لا زر لموعد لم يحن وقته
        past = C.create_event(self.pid, "visit", day(-1), "09:00")
        self.open_patient()
        self.assertEqual(ui.count("لم يحضر"), 1)
        ui.click("لم يحضر")
        ui.click_dialog("تسجيل «لم يحضر»")
        self.assertEqual(self.status(past), "no_show")
        self.assertEqual(self.status(future), "pending")
        self.assertEqual(C.stats()["no_show"], 1)

    def test_confirm_with_partial_payment_and_overpayment_blocked(self):
        C, ui = self.C, self.ui
        eid = C.create_event(self.pid, "visit", day(0), "23:30", items=[("كشف", 150000, "SYP")])   # 1500.00
        self.open_patient()
        ui.click("تأكيد الإنجاز")
        ui.type("ملاحظات (اختياري)", "بخير")
        ui.type("المدفوع بالليرة السورية (ل.س)", "99999")           # أكبر من المتبقي
        ui.click_dialog("تأكيد")
        self.assertEqual(self.status(eid), "pending", "دفع زائد يجب أن يمنع التأكيد كاملاً")
        self.assertEqual(C.q("SELECT count(*) FROM payments", one=True)[0], 0)
        ui.type("المدفوع بالليرة السورية (ل.س)", "500.25")
        ui.click_dialog("تأكيد")
        r = self.row(eid)
        self.assertEqual((r["status"], r["notes"]), ("done", "بخير"))
        self.assertIsNotNone(r["done_at"])
        due, paid, rem = C.amounts(C.ev_fin(eid))
        self.assertEqual((due["SYP"], paid["SYP"], rem["SYP"]), (150000, 50025, 99975))
        self.assertTrue(ui.has_text("منجزة"))

    def test_pay_remaining_button_fills_exact_amount(self):
        C, ui = self.C, self.ui
        eid = C.create_event(self.pid, "visit", day(0), "23:30", items=[("كشف", 123456, "SYP"), ("دواء", 1050, "USD")])
        C.add_payments(eid, [(23456, "SYP")])
        self.open_patient()
        ui.click("تأكيد الإنجاز")
        ui.click_dialog("دفع المتبقي كاملاً")
        self.assertEqual(ui.field("المدفوع بالليرة السورية (ل.س)").value, "1,000")
        self.assertEqual(ui.field("المدفوع بالدولار ($)").value, "10.50")
        ui.click_dialog("تأكيد")
        self.assertEqual(self.status(eid), "done")
        self.assertEqual(C.amounts(C.ev_fin(eid))[2], {"SYP": 0, "USD": 0})

    def test_delete_event_needs_confirmation_and_cascades(self):
        C, ui = self.C, self.ui
        eid = C.create_event(self.pid, "visit", day(4), "10:00", items=[("كشف", 5000, "SYP")])
        self.open_patient()
        ui.click("حذف الموعد نهائياً")
        ui.click_dialog("تراجع")
        self.assertIsNotNone(self.row(eid))                         # التراجع لا يحذف
        ui.click("حذف الموعد نهائياً")
        ui.click_dialog("حذف نهائي")
        self.assertIsNone(self.row(eid))
        self.assertEqual(C.q("SELECT count(*) FROM event_items", one=True)[0], 0)
        self.assertGreaterEqual(len(C.list_backups()), 1, "نسخة احتياطية قبل الحذف النهائي")

    def test_delete_event_with_payments_is_refused(self):
        C, ui = self.C, self.ui
        eid = C.create_event(self.pid, "visit", day(4), "10:00", items=[("كشف", 5000, "SYP")])
        C.add_payments(eid, [(1000, "SYP")])
        self.open_patient()
        ui.click("حذف الموعد نهائياً")
        ui.click_dialog("حذف نهائي")
        self.assertIsNotNone(self.row(eid))                         # الأموال المستلمة لا تضيع
        self.assertEqual(C.q("SELECT count(*) FROM payments", one=True)[0], 1)
        self.assertTrue(any("دفعات" in t for t in ui.toasts), ui.toasts)


class PatientDeletion(UiBase):
    def test_delete_patient_requires_switch_and_takes_backup(self):
        C, ui = self.C, self.ui
        C.create_event(self.pid, "visit", day(1), "10:00", items=[("كشف", 5000, "SYP")])
        self.open_patient()
        before = len(C.list_backups())
        ui.click("حذف المريض نهائياً")
        ui.click_dialog("حذف نهائي")                                  # بلا تفعيل خيار الفهم
        self.assertIsNotNone(C.get_patient(self.pid))
        self.assertTrue(ui.has_text("فعّل الخيار", ui.dialog()))
        ui.switches()[0].value = True
        ui.click_dialog("حذف نهائي")
        self.assertIsNone(C.get_patient(self.pid))
        self.assertEqual(C.q("SELECT count(*) FROM events", one=True)[0], 0)
        self.assertGreater(len(C.list_backups()), before, "نسخة احتياطية قبل الحذف")

    def test_delete_then_restore_backup_brings_patient_back(self):
        C, ui = self.C, self.ui
        self.open_patient()
        ui.click("حذف المريض نهائياً")
        ui.switches()[0].value = True
        ui.click_dialog("حذف نهائي")
        self.assertIsNone(C.get_patient(self.pid))
        C.restore_backup(os.path.join(C.BK_DIR, C.list_backups()[0]))
        self.assertEqual(C.get_patient(self.pid)["full_name"], "سلمى أحمد حسن")


class PatientForm(UiBase):
    def test_new_patient_with_age_and_birth_date(self):
        C, ui = self.C, self.ui
        ui.page.opened.clear()
        ui.s.patient_form()
        ui.type("الاسم (اختياري)", "خالد محمد العلي")
        ui.type("رقم التواصل", "0955777888")
        ui.type("تاريخ الميلاد (اختياري) سنة-شهر-يوم", "1990-05-23")
        ui.click("إضافة المريض")
        r = C.q("SELECT * FROM patients WHERE full_name=?", ("خالد محمد العلي",), one=True)
        self.assertEqual((r["birth_date"], r["status"]), ("1990-05-23", "جديد"))
        self.assertEqual(C.patient_age(r), C.patient_age({"birth_date": "1990-05-23"}))
        self.assertTrue(ui.has_text("تمت إضافة المريض", ui.dialog()))

    def test_age_only_stores_year_and_edit_keeps_exact_birth_date(self):
        C, ui = self.C, self.ui
        ui.page.opened.clear()
        ui.s.patient_form()
        ui.type("الاسم (اختياري)", "ليلى سعيد الخطيب")
        ui.type("العمر", "40")
        ui.click("إضافة المريض")
        r = C.q("SELECT * FROM patients WHERE full_name=?", ("ليلى سعيد الخطيب",), one=True)
        self.assertEqual(r["birth_date"], str(dt.date.today().year - 40))
        # مريض بتاريخ دقيق: تعديل الهاتف فقط لا يستبدله بسنة تقريبية
        C.x("UPDATE patients SET birth_date='1985-03-09' WHERE id=?", (self.pid,))
        ui.page.opened.clear()
        ui.s.patient_form(pid=self.pid)
        ui.type("رقم التواصل", "0999000111")
        ui.click("حفظ التعديلات")
        r = C.get_patient(self.pid)
        self.assertEqual((r["birth_date"], r["phone"]), ("1985-03-09", "0999000111"))

    def test_invalid_birth_date_and_age_rejected(self):
        C, ui = self.C, self.ui
        ui.page.opened.clear()
        ui.s.patient_form()
        ui.type("الاسم (اختياري)", "عمر خالد حسن")
        ui.type("تاريخ الميلاد (اختياري) سنة-شهر-يوم", "2999-01-01")
        ui.click("إضافة المريض")
        self.assertIsNone(C.q("SELECT 1 FROM patients WHERE full_name=?", ("عمر خالد حسن",), one=True))
        self.assertIn("المستقبل", ui.field("تاريخ الميلاد (اختياري) سنة-شهر-يوم").error_text)
        ui.type("تاريخ الميلاد (اختياري) سنة-شهر-يوم", "")
        ui.type("العمر", "200")
        ui.click("إضافة المريض")
        self.assertIsNone(C.q("SELECT 1 FROM patients WHERE full_name=?", ("عمر خالد حسن",), one=True))

    def test_duplicate_patient_is_flagged_not_silently_added(self):
        C, ui = self.C, self.ui
        ui.page.opened.clear()
        ui.s.patient_form()
        ui.type("الاسم (اختياري)", "سلمى أحمد حسن")
        ui.type("رقم التواصل", "0944111222")
        ui.click("إضافة المريض")
        self.assertEqual(C.q("SELECT count(*) FROM patients", one=True)[0], 1)
        self.assertTrue(ui.has_text("فتح الملف الموجود", ui.dialog()))
        ui.click_dialog("حفظ كمريض جديد")
        self.assertEqual(C.q("SELECT count(*) FROM patients", one=True)[0], 2)


class Attachments(UiBase):
    def test_rename_and_delete_attachment(self):
        C, ui = self.C, self.ui
        src = os.path.join(self.tmp, "report.txt")
        with open(src, "w") as f:
            f.write("x")
        p = C.get_patient(self.pid)
        C.save_patient(dict(full_name=p["full_name"], gender=p["gender"], residence="", phone=p["phone"], job="", diseases="",
                            notes="", blood="", status="جديد", birth_date=p["birth_date"]), {}, [src], pid=self.pid)
        self.open_patient()
        ui.click("إعادة تسمية")
        ui.type("اسم المرفق", "تحليل دم.txt")
        ui.click_dialog("حفظ")
        self.assertEqual(C.patient_attachments(self.pid)[0]["name"], "تحليل دم.txt")
        ui.click("حذف المرفق")
        ui.click_dialog("حذف")
        self.assertEqual(C.patient_attachments(self.pid), [])


class Login(UiBase):
    def test_wrong_password_then_correct(self):
        C, ui = self.C, self.ui
        C.lock_app()
        ui.page.opened.clear()
        ui.s.login_screen()
        ui.type("كلمة المرور", "wrong-password-1")
        ui.click("دخول")
        self.assertFalse(C.VAULT.unlocked)
        self.assertTrue(any("غير صحيحة" in t for t in ui.texts()), ui.texts())
        ui.type("كلمة المرور", PW)
        ui.click("دخول")
        self.assertTrue(C.VAULT.unlocked)
        self.assertEqual(C.get_patient(self.pid)["full_name"], "سلمى أحمد حسن")


if __name__ == "__main__":
    unittest.main(verbosity=2)
