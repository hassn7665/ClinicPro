# -*- coding: utf-8 -*-
"""
tests/ui_driver.py — سائق واجهة للاختبارات التفاعلية: يبني التطبيق على صفحة وهمية ثم «ينقر» الأزرار بنصوصها ويملأ الحقول
بعناوينها كما يفعل المستخدم، ليتحقق الاختبار من النتيجة في القاعدة. لا يحتاج جهازاً ولا متصفحاً.
"""
import types

import flet as ft

from helpers import FakePage

ft.Control.update = lambda self, *a, **k: None          # لا صفحة حقيقية: التحديث لا يفعل شيئاً (الرسم يُعاد ببناء الشاشة)


class Driver:
    def __init__(self, width=390):
        from gui import app as A
        self.page = FakePage(width)
        self.app = A.App(self.page)
        self.toasts = []
        A.configure(self.app)
        A.widgets.install(self.app)
        self.app.toast = lambda msg, color=None, *a, **k: self.toasts.append(str(msg))   # قبل تركيب الشاشات (تنسخ المرجع)
        for m in A.SCREEN_MODULES:
            m.install(self.app)
        self.s = self.app.s

    # ── استعلام الشجرة ──
    @staticmethod
    def walk(c):
        if c is None or getattr(c, "visible", True) is False:        # المخفي لا يراه المستخدم ولا ينقره
            return
        yield c
        for ch in c._get_children():
            yield from Driver.walk(ch)

    def roots(self):
        return [self.page.appbar] + list(self.page.controls)

    def dialog(self):
        return self.page.opened[-1] if self.page.opened else None

    def nodes(self, scope=None):
        for r in ([scope] if scope is not None else self.roots()):
            yield from self.walk(r)

    def texts(self, scope=None):
        return [c.value for c in self.nodes(scope) if isinstance(c, ft.Text) and c.value]

    def has_text(self, text, scope=None):
        return any(text in t for t in self.texts(scope))

    def _matches(self, text, scope):
        out = []
        for c in self.nodes(scope):
            if not callable(getattr(c, "on_click", None)):
                continue
            if getattr(c, "tooltip", None) == text or any(isinstance(d, ft.Text) and d.value == text for d in self.walk(c)):
                out.append(c)
        ids = {id(c) for c in out}
        # الأعمق فقط: نتجاهل أي حاوية قابلة للنقر تحوي زراً مطابقاً آخر
        return [c for c in out if not any(id(d) in ids and d is not c for d in self.walk(c))]

    # ── أفعال ──
    def click(self, text, nth=0, scope=None):
        found = self._matches(text, scope)
        if len(found) <= nth:
            raise AssertionError(f"لا زر «{text}» (وُجد {len(found)}). النصوص الظاهرة: {self.texts(scope)[:40]}")
        found[nth].on_click(types.SimpleNamespace(data="true", control=found[nth]))

    def click_data(self, data, scope=None):
        """ينقر العنصر الذي data = القيمة (أيام التقويم، ساعات، دقائق، ص/م، زر التبديل…)."""
        for c in self.nodes(scope):
            if getattr(c, "data", None) == data and callable(getattr(c, "on_click", None)):
                c.on_click(types.SimpleNamespace(data="true", control=c))
                return
        raise AssertionError(f"لا عنصر data={data!r} ظاهر")

    def has_data(self, data, scope=None):
        return any(getattr(c, "data", None) == data for c in self.nodes(scope))

    def click_dialog(self, text, nth=0):
        d = self.dialog()
        assert d is not None, "لا حوار مفتوح"
        self.click(text, nth, scope=d)

    def count(self, text, scope=None):
        return len(self._matches(text, scope))

    def field(self, label, scope=None):
        for c in self.nodes(scope if scope is not None else (self.dialog() or None)):
            if isinstance(c, ft.TextField) and c.label == label:
                return c
        for c in self.nodes(None):
            if isinstance(c, ft.TextField) and c.label == label:
                return c
        raise AssertionError(f"لا حقل بعنوان «{label}»")

    def type(self, label, value, scope=None):
        self.field(label, scope).value = value

    def switches(self, scope=None):
        return [c for c in self.nodes(scope if scope is not None else self.dialog()) if isinstance(c, ft.Switch)]
