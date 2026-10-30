# -*- coding: utf-8 -*-
"""
اختبارات الدفعة الأخيرة: الأرقام اللاتينية، تنبيه الترخيص خلال 7 أيام فقط، إزالة القفل عند الخلفية والمدد من الإعدادات،
زر حذف الصورة الدائري، وحقول الأرقام بخط لاتيني. تشغيل: python tests/test_batch3.py
"""
import datetime as dt
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import FakePage, boot_core, make_account, make_png  # noqa: E402
from ui_driver import Driver  # noqa: E402

import flet as ft  # noqa: E402

PW = "Correct-Horse-9"


class Base(unittest.TestCase):
    def setUp(self):
        self.C, self.tmp = boot_core("b3")
        make_account(self.C, password=PW)
        self.set_days(30)
        self.ui = Driver()

    def set_days(self, days):
        d = self.C.lic_load()
        d["expires"] = (dt.datetime.now() + dt.timedelta(days=days, hours=1)).isoformat()
        self.C._lic_save(d)


# ── الأرقام ──
class LatinDigits(unittest.TestCase):
    def test_runs_split_exactly_and_losslessly(self):
        from gui.digits import split_runs
        samples = ["الموعد 10:30 م", "2026-10-29", "1,500.50 ل.س", "بلا أرقام", "", "٣ أرقام هندية 12", "a1b2", "0944123456 هاتف"]
        for s in samples:
            self.assertEqual("".join(c for c, _ in split_runs(s)), s)
        self.assertEqual(split_runs("الموعد 10:30 م"), [("الموعد ", False), ("10:30", True), (" م", False)])
        self.assertEqual([c for c, n in split_runs("2026-10-29 و 1,500.50") if n], ["2026-10-29", "1,500.50"])

    def test_text_keeps_value_and_sends_two_fonts_to_flutter(self):
        from gui.digits import DigitText
        DigitText.digit_font = "Cairo"
        try:
            t = DigitText("متبقٍ 12 يوماً", size=14)
            self.assertEqual(t.value, "متبقٍ 12 يوماً")                       # القارئون يرون النص الأصلي دائماً
            t.before_update()
            spans = t._get_children()
            self.assertEqual([s.text for s in spans], ["متبقٍ ", "12", " يوماً"])
            self.assertEqual([bool(s.style) for s in spans], [False, True, False])
            self.assertEqual(spans[1].style.font_family, "Cairo")
            self.assertEqual(ft.Text.value.fget(t), "")                       # القيمة العادية تُرسل فارغة والمقاطع تحمل النص
            t.value = "بلا أرقام"                                              # تحديث لاحق إلى نص بلا أرقام يزيل المقاطع
            t.before_update()
            self.assertEqual(t._get_children(), [])
            self.assertEqual(ft.Text.value.fget(t), "بلا أرقام")
            t.value = "الآن 5"
            t.before_update()
            self.assertEqual([s.text for s in t._get_children()], ["الآن ", "5"])
        finally:
            DigitText.digit_font = None

    def test_disabled_when_font_has_latin_digits(self):
        from gui.digits import DigitText
        DigitText.digit_font = None
        t = DigitText("رقم 5")
        t.before_update()
        self.assertEqual(t._get_children(), [])
        self.assertEqual(ft.Text.value.fget(t), "رقم 5")

    def test_dinar_font_enables_latin_digits_and_registers_font(self):
        boot_core("digits")
        from gui import common, app as A
        from gui.digits import DigitText
        old = common.FONT_DIR
        with tempfile.TemporaryDirectory() as d:
            common.FONT_DIR = os.path.join(d, "fonts")
            os.makedirs(common.FONT_DIR)
            open(os.path.join(common.FONT_DIR, "GE_Dinar_One_Medium.ttf"), "wb").close()
            try:
                page = FakePage()
                A.configure(A.App(page))
                self.assertEqual(DigitText.digit_font, "Roboto")             # بلا Cairo: خط النظام اللاتيني
                open(os.path.join(common.FONT_DIR, "Cairo.ttf"), "wb").close()
                page = FakePage()
                A.configure(A.App(page))
                self.assertEqual(DigitText.digit_font, "Cairo")
                self.assertEqual(set(page.fonts), {"GEDinarOne", "Cairo"})
            finally:
                common.FONT_DIR = old
                DigitText.digit_font = None

    def test_cairo_only_needs_no_digit_workaround(self):
        boot_core("digits2")
        from gui import common, app as A
        from gui.digits import DigitText
        old = common.FONT_DIR
        with tempfile.TemporaryDirectory() as d:
            common.FONT_DIR = os.path.join(d, "fonts")
            os.makedirs(common.FONT_DIR)
            open(os.path.join(common.FONT_DIR, "Cairo.ttf"), "wb").close()
            try:
                A.configure(A.App(FakePage()))
                self.assertIsNone(DigitText.digit_font)
            finally:
                common.FONT_DIR = old

    def test_pickers_use_latin_digit_locale(self):
        boot_core("loc")
        from gui import app as A
        page = FakePage()
        A.configure(A.App(page))
        loc = page.locale_configuration
        self.assertEqual(getattr(loc, "current_locale").country_code, "AE")   # ar-AE: أرقام لاتينية في منتقي التاريخ

    def test_numeric_inputs_use_the_latin_font(self):
        from gui.digits import DigitText
        ui = Driver()
        DigitText.digit_font = "Cairo"
        try:
            phone = ui.app.field("هاتف", keyboard_type=ft.KeyboardType.PHONE)
            name = ui.app.field("الاسم")
            code = ui.app.field("كود", latin=True)
            self.assertEqual(phone.text_style.font_family, "Cairo")
            self.assertEqual(code.text_style.font_family, "Cairo")
            self.assertIsNone(name.text_style)                                  # الأسماء تبقى بخط التطبيق
            self.assertEqual(ui.app.pw_field("كلمة").text_style.font_family, "Cairo")
        finally:
            DigitText.digit_font = None

    def test_whole_ui_text_goes_through_digit_text(self):
        """كل نص يُنشأ عبر T أو الإشعارات أو عنوان الصفحة يمرّ بـDigitText (لا ft.Text مباشر يفلت منه)."""
        import re
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gui")
        offenders = []
        for dp, _, files in os.walk(root):
            for f in files:
                if f.endswith(".py") and f not in ("digits.py",):
                    for n, line in enumerate(open(os.path.join(dp, f), encoding="utf-8"), 1):
                        if re.search(r"\bft\.Text\(", line):
                            offenders.append(f)
        self.assertEqual(sorted(offenders), ["startup.py", "viewer.py"])   # شعار الترحيب وعنوان العارض فقط (بلا أرقام)


# ── الترخيص ──
class LicenseNotice(Base):
    def banner(self):
        self.ui.page.clean()
        self.ui.s.home()
        return [t for t in self.ui.texts() if "الترخيص" in t and "جدّد" in t]

    def test_no_notice_before_seven_days(self):
        for days in (30, 15, 8):
            self.set_days(days)
            self.assertEqual(self.banner(), [], days)

    def test_notice_within_seven_days_with_new_wording(self):
        self.set_days(7)
        msg = self.banner()
        self.assertEqual(len(msg), 1)
        self.assertIn("جدّد قبل انتهاء المدة", msg[0])
        self.assertNotIn("الإعدادات", msg[0])
        self.assertIn("7 أيام", msg[0])
        self.set_days(1)
        self.assertIn("ينتهي الترخيص غداً", self.banner()[0])
        self.set_days(3)
        self.assertIn("3 أيام", self.banner()[0])

    def test_settings_hides_plans_and_lock_policy(self):
        ui = self.ui
        ui.page.clean()
        ui.s.settings_screen()
        self.assertFalse(ui.has_text("مدد"))
        ui.page.clean()
        ui.s.license_screen(back=ui.s.settings_screen)
        self.assertFalse(ui.has_text("مدد الاشتراك"))
        ui.page.clean()
        ui.s.security_screen()
        self.assertFalse(ui.has_text("القفل عند الذهاب للخلفية"))
        self.assertFalse(ui.has_text("يُقفل التطبيق تلقائياً"))
        self.assertTrue(ui.has_text("قفل التطبيق الآن"))                       # القفل اليدوي يبقى


class NoBackgroundLock(unittest.TestCase):
    def test_no_lifecycle_handler_is_installed(self):
        boot_core("life")
        from gui import app as A
        page = FakePage()
        A.configure(A.App(page))
        self.assertNotIn("on_app_lifecycle_state_change", vars(page))         # لا ربط لأحداث الخلفية إطلاقاً


# ── صور النموذج ──
class PhotoBadge(Base):
    def setUp(self):
        super().setUp()
        C = self.C
        png = make_png(os.path.join(self.tmp, "p.png"))
        self.pid = C.save_patient(dict(full_name="صورة", gender="", residence="", phone="", job="", diseases="", notes="",
                                       blood="", status="جديد"), {"photo_before": png}, [])["id"]

    def open_form(self, pid=None):
        self.ui.page.opened.clear()
        self.ui.s.patient_form(pid=pid)

    def test_badge_only_where_a_photo_exists(self):
        ui = self.ui
        self.open_form(self.pid)
        self.assertTrue(ui.has_data("delphoto:photo_before"))
        self.assertFalse(ui.has_data("delphoto:photo_after"))                   # خانة فارغة: لا زر
        self.assertFalse(ui.has_data("delphoto:photo_lab"))
        self.assertEqual(ui.count("حذف"), 0)                                    # لا زر نصي بدائي «حذف» تحت الخانات

    def test_delete_asks_confirmation_then_removes_on_save(self):
        C, ui = self.C, self.ui
        self.open_form(self.pid)
        ui.click_data("delphoto:photo_before")
        self.assertTrue(ui.has_text("ستُحذف الصورة نهائياً", ui.dialog()))
        ui.click_dialog("تراجع") if ui.count("تراجع", scope=ui.dialog()) else ui.click_dialog("إلغاء")
        self.assertTrue(C.get_patient(self.pid)["photo_before"])
        ui.click_data("delphoto:photo_before")
        ui.click_dialog("حذف")
        self.assertFalse(ui.has_data("delphoto:photo_before"))                  # اختفى الزر مع الصورة
        ui.click("حفظ التعديلات")
        self.assertFalse(C.get_patient(self.pid)["photo_before"])

    def test_birth_field_is_latin(self):
        from gui.digits import DigitText
        DigitText.digit_font = "Cairo"
        try:
            self.open_form()
            self.assertEqual(self.ui.field("تاريخ الميلاد (اختياري) سنة-شهر-يوم").text_style.font_family, "Cairo")
        finally:
            DigitText.digit_font = None


if __name__ == "__main__":
    unittest.main(verbosity=2)
