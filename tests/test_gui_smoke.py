# -*- coding: utf-8 -*-
"""
اختبار دخان للواجهة بعد التقسيم إلى وحدات: كل شاشة تُبنى بعرضين (390 و320) دون استثناء، والتنقل السفلي يعمل عبر
سجل الشاشات، ولا يوجد SQL داخل gui/. تشغيل: python tests/test_gui_smoke.py
"""
import glob
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import ROOT, FakePage, boot_core, make_account, seed_clinic  # noqa: E402


def build_app(width=390):
    from gui import app as A
    page = FakePage(width)
    app = A.App(page)
    A.configure(app)
    A.widgets.install(app)
    for m in A.SCREEN_MODULES:
        m.install(app)
    return app


class GuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.C, _ = boot_core("gui")
        make_account(cls.C)
        cls.p1, cls.p2 = seed_clinic(cls.C)

    def screens(self):
        p1, p2 = self.p1, self.p2
        return [("home", ()), ("schedule_screen", ()), ("schedule_screen", ("2026-01-15",)), ("accounts_screen", ()),
                ("search_screen", ()), ("settings_screen", ()), ("stats_screen", ()), ("backup_screen", ()),
                ("security_screen", ()), ("patient_screen", (p1,)), ("patient_screen", (p2,)), ("patient_form", ()),
                ("patient_form", (None, p1)), ("financial_screen", (p1,)), ("financial_screen", (p2,)),
                ("login_screen", ()), ("setup_screen", ()), ("reset_screen", ()), ("config_error_screen", ()),
                ("splash", ()), ("license_screen", ())]

    def test_every_screen_builds(self):
        for width in (390, 320):
            app = build_app(width)
            for name, args in self.screens():
                with self.subTest(screen=name, args=args, width=width):
                    app.page.clean()
                    getattr(app.s, name)(*args)
                    self.assertTrue(app.page.controls, "الشاشة لم تُضِف شيئاً للصفحة")

    def test_nav_bar_goes_through_registry(self):
        app = build_app()
        titles = []
        for i in range(5):
            app.page.clean()
            app.nav_bar(0)
            app.page.bottom_appbar.content.controls[i].on_click(None)
            titles.append(app.page.appbar.title.value if app.page.appbar else None)
            self.assertIsNotNone(app.page.bottom_appbar, "الشاشات الأربع تُلفّ بـ with_nav فيظهر الشريط السفلي")
        self.assertEqual(titles[1:], ["جدول المواعيد", "الحسابات", "البحث عن مريض", "الإعدادات"])

    def test_all_registered_screens_exist(self):
        app = build_app()
        expected = {"image_screen", "license_screen", "splash", "home", "settings_screen", "diagnostics_screen",
                    "security_screen", "stats_screen", "backup_screen", "patient_form", "search_screen", "patient_screen",
                    "schedule_screen", "accounts_screen", "financial_screen", "recovery_key_dialog", "setup_screen",
                    "fmt_wait", "login_screen", "reset_screen", "lock_now", "after_login", "config_error_screen",
                    "boot_account", "event_details"}
        self.assertEqual(expected - set(vars(app.s)), set())


class ArchitectureTests(unittest.TestCase):
    """حراسة البنية: تمنع عودة SQL أو sqlite إلى الواجهة، وتمنع تضخّم الوحدات من جديد."""
    FILES = sorted(glob.glob(os.path.join(ROOT, "gui", "**", "*.py"), recursive=True)) + [os.path.join(ROOT, "main.py")]
    SQL = re.compile(r"\b(SELECT\s.+\sFROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET|DELETE\s+FROM|PRAGMA)\b", re.I)
    FORBIDDEN = re.compile(r"import sqlite3|sqlite3\.|\bC\.(q|x|db)\(|C\._mem|from core import .*\b(q|x|db)\b|\bexecute\(")

    def test_no_sql_in_ui(self):
        for path in self.FILES:
            with open(path, encoding="utf-8") as f:
                for n, line in enumerate(f, 1):
                    code = line.split("#")[0]
                    self.assertIsNone(self.SQL.search(code), f"{os.path.relpath(path, ROOT)}:{n} يحوي SQL")
                    self.assertIsNone(self.FORBIDDEN.search(code), f"{os.path.relpath(path, ROOT)}:{n} وصول مباشر للقاعدة")

    def test_modules_stay_small(self):
        for path in self.FILES:
            with open(path, encoding="utf-8") as f:
                n = sum(1 for _ in f)
            self.assertLessEqual(n, 650, f"{os.path.relpath(path, ROOT)} صار {n} سطراً: قسّمه")

    def test_main_is_entry_point_only(self):
        with open(os.path.join(ROOT, "main.py"), encoding="utf-8") as f:
            self.assertLess(sum(1 for _ in f), 30)


if __name__ == "__main__":
    unittest.main(verbosity=2)
