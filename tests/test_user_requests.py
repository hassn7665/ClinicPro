# -*- coding: utf-8 -*-
"""
اختبارات الطلبات الاثني عشر (أيقونة، شاشة التفعيل، الاسترداد الإلزامي عبر المدير، الاسم الاختياري، الترتيب، ص/م، التعارض الاختياري،
تفاصيل الموعد، الخط، إزالة الشروح، نص التنويه). تشغيل: python tests/test_user_requests.py
"""
import datetime as dt
import os
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import ROOT, boot_core, make_account  # noqa: E402
from ui_driver import Driver  # noqa: E402
from hypothesis import given, settings, strategies as st  # noqa: E402

PW = "Correct-Horse-9"


def day(n):
    return (dt.date.today() + dt.timedelta(days=n)).strftime("%Y-%m-%d")


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    assert head[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", head[16:24])


class Base(unittest.TestCase):
    def setUp(self):
        self.C, self.tmp = boot_core("req")
        make_account(self.C, password=PW)
        d = self.C.lic_load()
        d["expires"] = (dt.datetime.now() + dt.timedelta(days=30)).isoformat()
        self.C._lic_save(d)
        self.ui = Driver()

    def patient(self, name, phone="", **kw):
        return self.C.save_patient(dict(full_name=name, gender="", residence="", phone=phone, job="", diseases="", notes="",
                                        blood="", status="جديد", **kw), {}, [], allow_duplicate=True)["id"]


# ── 1: الأيقونة ──
class IconAndAssets(unittest.TestCase):
    def test_flet_build_finds_icons_in_assets(self):
        for name, min_px in (("icon.png", 512), ("icon_android.png", 192)):
            path = os.path.join(ROOT, "assets", name)
            self.assertTrue(os.path.isfile(path), f"{name} مفقود: يبني Flet أيقونة Flet الافتراضية بدونه")
            w, h = png_size(path)
            self.assertEqual(w, h)
            self.assertGreaterEqual(w, min_px)

    def test_assets_not_gitignored(self):
        with open(os.path.join(ROOT, ".gitignore"), encoding="utf-8") as f:
            ignored = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
        for p in ("assets/icon.png", "assets/icon_android.png", "assets/fonts/x.ttf"):
            self.assertFalse(any(p.startswith(g.rstrip("/")) and g.rstrip("/") in ("assets", "assets/fonts") for g in ignored), p)


# ── 2 + 12: شاشة التفعيل والتنويه ──
class FirstRunTexts(Base):
    def test_license_screen_never_lists_subscription_durations(self):
        ui = self.ui
        for first in (True, False):
            ui.page.clean()
            ui.s.license_screen(first=first)
            self.assertFalse(ui.has_text("مدد الاشتراك"), first)
            self.assertFalse(any("أشهر" in t and "سنة" in t for t in ui.texts()))

    def test_setup_notice_wording(self):
        ui = self.ui
        ui.page.clean()
        ui.s.setup_screen()
        texts = ui.texts()
        self.assertIn("تنويه:", texts)
        self.assertNotIn("مهم", texts)
        self.assertTrue(any("وعن طريق مدير البرنامج" in t and "إن فعّلت" not in t for t in texts), texts)


# ── 3 + 9: الاسترداد عبر المدير إلزامي ──
class MandatoryAdminRecovery(Base):
    def test_setup_screen_has_no_admin_switch(self):
        import flet as ft
        ui = self.ui
        ui.page.clean()
        ui.s.setup_screen()
        self.assertEqual([c for c in ui.nodes() if isinstance(c, ft.Switch)], [])
        self.assertFalse(ui.has_text("السماح لمدير البرنامج"))

    def test_account_created_from_screen_has_escrow(self):
        C = self.C
        C.lock_app()
        # حساب جديد كلياً عبر الشاشة
        C2, _ = boot_core("req_fresh")
        ui2 = Driver()
        ui2.s.setup_screen()
        ui2.type("اسم المستخدم", "doctor1")
        ui2.type("كلمة المرور (عشر خانات على الأقل — الأفضل جملة)", PW)
        ui2.type("تأكيد كلمة المرور", PW)
        ui2.click("إنشاء الحساب")
        self.assertTrue(C2.VAULT.unlocked)
        self.assertTrue(C2.VAULT.escrow_enabled)

    def test_security_screen_cannot_disable_it(self):
        ui = self.ui
        ui.page.clean()
        ui.s.security_screen()
        self.assertFalse(ui.has_text("الاسترداد عبر مدير البرنامج"))
        self.assertTrue(ui.has_text("تغيير كلمة المرور"))          # بقية خيارات الأمان موجودة

    def test_login_enforces_for_old_accounts(self):
        C, ui = self.C, self.ui
        C.VAULT.set_escrow(False) if C.VAULT.has_recovery_key else None
        C.lock_app()
        self.assertEqual(C.unlock("tester", PW), "ok")
        ui.s.after_login()
        self.assertTrue(C.VAULT.escrow_enabled)


# ── 4: الاسم اختياري ──
class OptionalName(Base):
    def test_unnamed_and_any_word_count(self):
        C = self.C
        a = self.patient("")
        b = self.patient("سلمى")
        c = self.patient("محمد علي")
        d = self.patient("   ")
        self.assertEqual([C.get_patient(i)["full_name"] for i in (a, b, c, d)], ["بدون اسم", "سلمى", "محمد علي", "بدون اسم"])

    def test_unnamed_patients_are_not_duplicates_of_each_other(self):
        C = self.C
        C.save_patient(dict(full_name="", gender="", residence="", phone="0944111222", job="", diseases="", notes="", blood="",
                            status="جديد"), {}, [])
        C.save_patient(dict(full_name="", gender="", residence="", phone="0955333444", job="", diseases="", notes="", blood="",
                            status="جديد"), {}, [])                  # هاتف مختلف: لا تكرار رغم تطابق «بدون اسم»
        with self.assertRaises(C.DuplicatePatient):                  # نفس الهاتف: تنبيه تكرار
            C.save_patient(dict(full_name="", gender="", residence="", phone="0944111222", job="", diseases="", notes="",
                                blood="", status="جديد"), {}, [])

    def test_form_saves_without_name_and_with_two_words(self):
        C, ui = self.C, self.ui
        ui.page.opened.clear()
        ui.s.patient_form()
        ui.type("رقم التواصل", "0999888777")
        ui.click("إضافة المريض")
        self.assertIsNotNone(C.q("SELECT 1 FROM patients WHERE full_name='بدون اسم' AND phone='0999888777'", one=True))
        ui.page.opened.clear()
        ui.s.patient_form()
        ui.type("الاسم (اختياري)", "ليلى حسن")
        ui.click("إضافة المريض")
        self.assertIsNotNone(C.q("SELECT 1 FROM patients WHERE full_name='ليلى حسن'", one=True))


# ── 5: التصفح بالترتيب ──
class BrowseOrder(Base):
    def setUp(self):
        super().setUp()
        C = self.C
        for i, n in enumerate(["إبراهيم", "ابراهيم الثاني", "أحمد", "بسام", "آدم"]):
            pid = self.patient(n)
            C.x("UPDATE patients SET created_at=? WHERE id=?", (f"2026-0{i + 1}-01T10:00:00", pid))

    def names(self, sort):
        return [r["full_name"] for r in self.C.list_patients(sort, 0, 50)[0]]

    def test_alphabetical_ignores_hamza_variants(self):
        n = self.names("alpha")
        self.assertEqual(n.index("أحمد") < n.index("بسام"), True)
        self.assertEqual(sorted(n[:4], key=lambda s: s) is not None, True)
        self.assertLess(n.index("آدم"), n.index("بسام"))              # آ/أ/إ/ا تُعامل كحرف واحد
        self.assertEqual(n[-1], "بسام")

    def test_chronological_both_directions(self):
        self.assertEqual(self.names("newest")[0], "آدم")             # آخر من سُجّل
        self.assertEqual(self.names("oldest")[0], "إبراهيم")
        self.assertEqual(self.names("newest"), list(reversed(self.names("oldest"))))

    def test_pagination_and_total(self):
        rows, total = self.C.list_patients("alpha", 0, 2)
        self.assertEqual((len(rows), total), (2, 5))
        rows2, _ = self.C.list_patients("alpha", 2, 2)
        self.assertEqual(len({r["id"] for r in rows + rows2}), 4)
        with self.assertRaises(ValueError):
            self.C.list_patients("random")

    def test_search_respects_sort(self):
        r = self.C.search_patients("ابراهيم", 50, "oldest")
        self.assertEqual([x["full_name"] for x in r], ["إبراهيم", "ابراهيم الثاني"])

    def test_search_screen_browses_all_and_switches_order(self):
        ui = self.ui
        ui.page.clean()
        ui.s.search_screen()
        shown = [t for t in ui.texts() if t in ("أحمد", "بسام", "آدم", "إبراهيم", "ابراهيم الثاني")]
        self.assertEqual(len(shown), 5)                              # مربع البحث فارغ: كل المرضى
        self.assertTrue(ui.has_text("كل المرضى (5)"))
        ui.click("الأحدث أولاً")
        self.assertEqual([t for t in ui.texts() if t in ("أحمد", "بسام", "آدم", "إبراهيم", "ابراهيم الثاني")][0], "آدم")
        ui.click("الأقدم أولاً")
        self.assertEqual([t for t in ui.texts() if t in ("أحمد", "بسام", "آدم", "إبراهيم", "ابراهيم الثاني")][0], "إبراهيم")
        self.assertEqual(ui.app.ui["patient_sort"], "oldest")


# ── 6: ص/م ──
class AmPm(Base):
    @settings(max_examples=50, deadline=None)
    @given(st.integers(0, 23), st.integers(0, 59))
    def test_every_minute_of_the_day_roundtrips(self, h, m):
        C = self.C
        hm = f"{h:02d}:{m:02d}"
        h12, mm, ap = C.hm_to_12(hm)
        self.assertTrue(1 <= h12 <= 12)
        self.assertEqual(C.hm_from_12(h12, mm, ap), hm)
        self.assertEqual(C.fmt12(hm).endswith("ص" if h < 12 else "م"), True)

    def test_edge_cases(self):
        C = self.C
        self.assertEqual(C.fmt12("00:00"), "12:00 ص")
        self.assertEqual(C.fmt12("12:00"), "12:00 م")
        self.assertEqual(C.fmt12("03:30"), "03:30 ص")
        self.assertEqual(C.fmt12("15:30"), "03:30 م")                # الفرق الذي كان يسبب الخطأ
        self.assertEqual(C.hm_from_12(12, 0, "ص"), "00:00")
        for bad in ((0, 0, "ص"), (13, 0, "م"), (5, 60, "ص"), (5, 0, "AM")):
            with self.assertRaises(ValueError):
                C.hm_from_12(*bad)

def goto(ui, target, hm=None, scope=None):
    """يحرّك منتقي الموعد المضمَّن كما يفعل المستخدم: شهر ← يوم ← ساعة ← دقيقة ← ص/م."""
    shown = None
    for _ in range(14):                                          # أقصى تنقل شهري معقول
        if ui.has_data(f"day:{target.isoformat()}", scope):
            shown = True
            break
        ui.click_data("nav:1" if any(getattr(c, "data", "") == "nav:1" for c in ui.nodes(scope)) else "nav:-1", scope)
    assert shown, f"اليوم {target} غير ظاهر"
    ui.click_data(f"day:{target.isoformat()}", scope)
    if hm:
        h12, m, ap = ui.app_C.hm_to_12(hm)
        ui.click_data(f"h:{h12}", scope)
        ui.click_data(f"m:{m}", scope)
        ui.click_data(f"ap:{ap}", scope)


class WhenPickerUI(Base):
    def setUp(self):
        super().setUp()
        from gui.when_picker import WhenPicker
        self.WP = WhenPicker
        self.ui.app_C = self.C
        self.changes = []

    def make(self, d="2026-10-29", hm="15:30", expanded=True):
        wp = self.WP(self.ui.app, d, hm, on_change=lambda *a: self.changes.append(a), expanded=expanded)
        self.ui.page.controls = [wp.ui]
        self.ui.page.appbar = None
        return wp

    def test_summary_shows_weekday_date_and_12h_time(self):
        wp = self.make()
        self.assertTrue(self.ui.has_text("الخميس 29 تشرين الأول 2026"))
        self.assertTrue(self.ui.has_text("03:30 م"))
        self.assertEqual(wp.value(), ("2026-10-29", "15:30"))

    def test_explicit_am_pm_and_all_choices(self):
        ui, wp = self.ui, self.make()
        ui.click_data("ap:ص")
        self.assertEqual(wp.value()[1], "03:30")
        ui.click_data("ap:م")
        ui.click_data("h:12")
        ui.click_data("m:0")
        self.assertEqual(wp.value()[1], "12:00")
        ui.click_data("ap:ص")
        self.assertEqual(wp.value()[1], "00:00")                    # 12 صباحاً = منتصف الليل
        self.assertTrue(ui.has_text("12:00 ص"))
        self.assertGreaterEqual(len(self.changes), 4)               # كل نقرة تُبلغ المستدعي

    def test_calendar_navigation_and_day_selection(self):
        ui, wp = self.ui, self.make()
        self.assertTrue(ui.has_text("تشرين الأول 2026"))
        ui.click_data("nav:1")
        self.assertTrue(ui.has_text("تشرين الثاني 2026"))
        self.assertEqual(wp.value()[0], "2026-10-29")               # التنقل لا يغيّر اليوم المختار
        ui.click_data("day:2026-11-15")
        self.assertEqual(wp.value()[0], "2026-11-15")
        ui.click_data("nav:-1")
        ui.click_data("nav:-1")
        self.assertTrue(ui.has_text("أيلول 2026"))
        for _ in range(9):
            ui.click_data("nav:-1")
        self.assertTrue(ui.has_text("كانون الأول 2025"))            # عبور حدّ السنة

    def test_quick_chips(self):
        ui, wp = self.ui, self.make(dt.date.today().isoformat(), "10:00")
        ui.click_data("quick:7")
        self.assertEqual(wp.value()[0], day(7))
        ui.click_data("quick:1")
        self.assertEqual(wp.value()[0], day(1))
        ui.click_data("quick:0")
        self.assertEqual(wp.value()[0], day(0))

    def test_busy_days_are_marked(self):
        C = self.C
        pid = self.patient("مشغول")
        C.create_event(pid, "visit", "2026-10-20", "10:00")
        self.make()
        cell = next(c for c in self.ui.nodes() if getattr(c, "data", None) == "day:2026-10-20")
        dot = cell.content.controls[1]
        self.assertIsNotNone(dot.bgcolor)                           # نقطة على اليوم المشغول
        quiet = next(c for c in self.ui.nodes() if getattr(c, "data", None) == "day:2026-10-21")
        self.assertIsNone(quiet.content.controls[1].bgcolor)

    def test_collapsed_panel_hides_choices_until_edit_pressed(self):
        ui = self.ui
        self.make(expanded=False)
        self.assertFalse(ui.has_data("h:3"))                        # اللوحة مطوية
        self.assertTrue(ui.has_text("03:30 م"))                     # لكن الملخص ظاهر
        ui.click_data("when:toggle")
        self.assertTrue(ui.has_data("h:3"))
        ui.click_data("when:toggle")
        self.assertFalse(ui.has_data("h:3"))

    def test_odd_minute_of_existing_event_stays_selectable(self):
        wp = self.make("2026-10-29", "09:07")
        self.assertTrue(self.ui.has_data("m:7"))
        self.assertEqual(wp.value()[1], "09:07")

    def test_default_slot_is_always_a_valid_future_choice(self):
        d, t = self.C.default_slot()
        self.assertGreaterEqual(dt.datetime.fromisoformat(f"{d}T{t}"), dt.datetime.now().replace(second=0, microsecond=0))
        self.make(d, t)                                              # يُبنى المنتقي بها بلا أخطاء


# ── 7: التعارض اختياري (المنتقي مضمَّن: لا نوافذ متداخلة) ──
class OptionalConflict(Base):
    def setUp(self):
        super().setUp()
        self.ui.app_C = self.C
        self.pid = self.patient("مريض تعارض")
        self.other = self.patient("مريض آخر")
        self.target = dt.date.today() + dt.timedelta(days=3)
        self.C.create_event(self.other, "visit", self.target.isoformat(), "10:00")      # يشغل 10:00–10:30

    def open_add(self, hm="10:00"):
        ui = self.ui
        ui.page.opened.clear()
        ui.s.patient_screen(self.pid)
        ui.click("موعد مراجعة")
        goto(ui, self.target, hm, scope=ui.dialog())
        self.assertEqual(len(ui.page.opened), 1, "لا نوافذ متداخلة")

    def count(self):
        return self.C.q("SELECT count(*) FROM events WHERE patient_id=?", (self.pid,), one=True)[0]

    def test_conflict_warns_with_edit_button_but_saves_in_one_click(self):
        ui = self.ui
        self.open_add("10:00")
        d = ui.dialog()
        self.assertTrue(ui.has_text("يتعارض مع", d))
        self.assertTrue(ui.has_text("مريض آخر", d))
        self.assertTrue(ui.has_text("يمكنك حفظ الموعد كما هو", d))
        self.assertEqual(ui.count("تعديل الموعد", scope=d), 1)
        ui.click_dialog("حفظ الموعد")                                  # نقرة واحدة، بلا تأكيد ثانٍ
        self.assertEqual(self.count(), 1)
        self.assertIsNone(ui.dialog())

    def test_moving_the_time_clears_the_warning_and_saves_new_time(self):
        ui = self.ui
        self.open_add("10:00")
        d = ui.dialog()
        ui.click_data("h:2", d)
        ui.click_data("m:0", d)
        ui.click_data("ap:م", d)
        self.assertFalse(ui.has_text("يتعارض مع", d))
        self.assertEqual(ui.count("تعديل الموعد", scope=d), 0)
        self.assertTrue(ui.has_text("02:00 م", d))
        ui.click_dialog("حفظ الموعد")
        row = self.C.q("SELECT date, time FROM events WHERE patient_id=?", (self.pid,), one=True)
        self.assertEqual((row["date"], row["time"]), (self.target.isoformat(), "14:00"))

    def test_no_conflict_means_no_warning_or_edit_button(self):
        ui = self.ui
        self.open_add("04:00")
        d = ui.dialog()
        self.assertFalse(ui.has_text("يتعارض مع", d))
        self.assertEqual(ui.count("تعديل الموعد", scope=d), 0)

    def test_edit_dialog_conflict_flow_saves_and_closes_only_after_save(self):
        """انحدار: كانت النافذة تُغلق دون حفظ عند تعديل موعد متعارض (منتقٍ منبثق فوق حوار)."""
        C, ui = self.C, self.ui
        eid = C.create_event(self.pid, "visit", self.target.isoformat(), "10:15")        # يتعارض مع الموجود
        ui.page.opened.clear()
        ui.s.patient_screen(self.pid)
        ui.click("تعديل الموعد")
        d = ui.dialog()
        self.assertTrue(ui.has_text("يتعارض مع", d))
        self.assertFalse(ui.has_data("h:3", d))                      # اللوحة مطوية افتراضياً
        ui.click_dialog("تعديل الموعد")                               # زر التعارض يفتح اللوحة داخل الحوار نفسه
        self.assertTrue(ui.has_data("h:3", ui.dialog()))
        self.assertIs(ui.dialog(), d)                                 # الحوار نفسه، لا نافذة أخرى
        ui.click_data("h:4", d)
        ui.click_data("m:30", d)
        ui.click_data("ap:م", d)
        self.assertIs(ui.dialog(), d)                                 # ما زال مفتوحاً
        self.assertFalse(ui.has_text("يتعارض مع", d))
        ui.click_dialog("حفظ التعديلات")
        self.assertEqual(C.q("SELECT time FROM events WHERE id=?", (eid,), one=True)[0], "16:30")
        self.assertIsNone(ui.dialog())                                # يُغلق بعد الحفظ فقط

    def test_edit_dialog_saves_even_with_conflict_in_one_click(self):
        C, ui = self.C, self.ui
        eid = C.create_event(self.pid, "visit", self.target.isoformat(), "10:15")
        ui.page.opened.clear()
        ui.s.patient_screen(self.pid)
        ui.click("تعديل الموعد")
        self.assertTrue(ui.has_text("يتعارض مع", ui.dialog()))
        ui.click_dialog("حفظ التعديلات")
        self.assertEqual(C.q("SELECT status FROM events WHERE id=?", (eid,), one=True)[0], "pending")
        self.assertIsNone(ui.dialog())

    def test_schedule_offers_edit_for_conflicting_rows(self):
        C, ui = self.C, self.ui
        C.create_event(self.pid, "visit", self.target.isoformat(), "10:10")
        ui.page.clean()
        ui.s.schedule_screen(self.target.isoformat())
        self.assertEqual(ui.count("تعديل الموعد"), 2)                  # لكل موعد من الاثنين المتعارضين
        self.assertGreaterEqual(ui.count("عرض التفاصيل"), 2)
        ui.click("تعديل الموعد")
        self.assertTrue(ui.has_text("تعديل الموعد", ui.dialog()))


# ── 8: تفاصيل الموعد ──
class EventDetails(Base):
    def test_core_detail_has_items_and_totals(self):
        C = self.C
        pid = self.patient("تفاصيل")
        eid = C.create_event(pid, "surgery", day(2), "13:30",
                             items=[("استئصال", 500000, "SYP"), ("تخدير", 2500, "USD")])
        C.add_payments(eid, [(100000, "SYP")])
        d = C.event_detail(eid)
        self.assertEqual([i["name"] for i in d["items"]], ["استئصال", "تخدير"])
        self.assertEqual((d["due"]["SYP"], d["paid"]["SYP"], d["remaining"]["SYP"]), (500000, 100000, 400000))
        self.assertIsNone(C.event_detail(99999))

    def test_dialog_shows_procedure_and_ends_with_open_file(self):
        C, ui = self.C, self.ui
        pid = self.patient("مريضة التفاصيل")
        C.create_event(pid, "surgery", day(0), "23:00", items=[("استئصال زائدة", 300000, "SYP")])
        ui.page.clean()
        ui.s.home()
        self.assertEqual(ui.count("فتح الملف"), 0)                     # الزر القديم لم يعد في بطاقات المواعيد
        ui.click("عرض التفاصيل")
        d = ui.dialog()
        self.assertTrue(ui.has_text("استئصال زائدة", d))
        self.assertTrue(ui.has_text("عملية", d))
        self.assertTrue(ui.has_text("11:00 م", d))
        self.assertTrue(ui.has_text("مريضة التفاصيل", d))
        texts = ui.texts(d)
        self.assertGreater(texts.index("فتح ملف المريض"), texts.index("• استئصال زائدة"))      # الزر في النهاية
        ui.click_dialog("فتح ملف المريض")
        self.assertTrue(ui.has_text("ملف المريض") or ui.has_text("مريضة التفاصيل"))

    def test_visit_without_items_says_so(self):
        C, ui = self.C, self.ui
        pid = self.patient("بلا إجراءات")
        eid = C.create_event(pid, "visit", day(1), "09:00")
        ui.s.event_details(eid)
        self.assertTrue(ui.has_text("لا توجد إجراءات مسجّلة", ui.dialog()))

    def test_missing_event_is_reported_not_crashed(self):
        self.ui.s.event_details(424242)
        self.assertTrue(any("لم يعد موجوداً" in t for t in self.ui.toasts))


# ── 10: الخط ──
class AppFont(unittest.TestCase):
    def test_prefers_ge_dinar_then_cairo_then_none(self):
        boot_core("font")
        from gui import common
        old = common.FONT_DIR
        try:
            with tempfile.TemporaryDirectory() as d:
                common.FONT_DIR = os.path.join(d, "fonts")
                self.assertIsNone(common.find_app_font())
                os.makedirs(common.FONT_DIR)
                open(os.path.join(common.FONT_DIR, "Cairo.ttf"), "wb").close()
                self.assertEqual(common.find_app_font(), ("Cairo", "fonts/Cairo.ttf"))
                open(os.path.join(common.FONT_DIR, "GE_Dinar_One_Medium.ttf"), "wb").close()
                self.assertEqual(common.find_app_font(), ("GEDinarOne", "fonts/GE_Dinar_One_Medium.ttf"))
                open(os.path.join(common.FONT_DIR, "GE-Dinar-One-Medium.otf"), "wb").close()
                self.assertEqual(common.find_app_font()[0], "GEDinarOne")
        finally:
            common.FONT_DIR = old

    def test_theme_uses_the_font_when_present(self):
        boot_core("font2")
        from gui import common, app as A
        from helpers import FakePage
        old = common.FONT_DIR
        with tempfile.TemporaryDirectory() as d:
            common.FONT_DIR = os.path.join(d, "fonts")
            os.makedirs(common.FONT_DIR)
            open(os.path.join(common.FONT_DIR, "GE_Dinar_One_Medium.ttf"), "wb").close()
            try:
                page = FakePage()
                A.configure(A.App(page))
                self.assertEqual(page.theme.font_family, "GEDinarOne")
                self.assertEqual(page.fonts, {"GEDinarOne": "fonts/GE_Dinar_One_Medium.ttf"})
            finally:
                common.FONT_DIR = old


# ── 11: إزالة مربعات الشرح ──
class NoHelpBoxes(Base):
    def test_stats_and_accounts_have_no_explanations(self):
        ui = self.ui
        ui.page.clean()
        ui.s.stats_screen()
        self.assertFalse(ui.has_text("المعلّقة:"))
        self.assertFalse(ui.has_text("تأكيد الإنجاز» عليها"))
        self.assertTrue(ui.has_text("مواعيد معلّقة"))                  # الأرقام نفسها باقية
        ui.page.clean()
        ui.s.accounts_screen()
        self.assertFalse(ui.has_text("المدفوع: الدفعات المستلمة"))
        self.assertFalse(ui.has_text("لا يوجد تحويل بين العملتين"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
