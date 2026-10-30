# -*- coding: utf-8 -*-
"""
gui/digits.py — أرقام لاتينية (0-9) مهما كان خط التطبيق.

المشكلة: بعض الخطوط العربية (ومنها GE Dinar One) ترسم الأرقام ASCII بأشكال هندية (٠١٢٣…). الحل المستقل عن محتوى ملف الخط:
نص كل عنصر يُقسَّم إلى «مقاطع»: الأرقام وما بينها (10:30، 2026-10-29، 1,500.50) تُعرض بخط لاتيني (Cairo إن وُجد وإلا Roboto)،
والباقي بخط التطبيق. يعمل فقط حين يكون الخط الأساسي من هذا النوع (digit_font ليس None).
"""
import re

import flet as ft

_RUN = re.compile(r"[0-9]+(?:[.,:/\-][0-9]+)*")


def split_runs(text: str):
    """[(مقطع, هو_رقم)] بترتيب ورودها؛ يحفظ النص كاملاً (ضمّ المقاطع = الأصل)."""
    out, pos = [], 0
    for m in _RUN.finditer(text):
        if m.start() > pos:
            out.append((text[pos:m.start()], False))
        out.append((m.group(), True))
        pos = m.end()
    if pos < len(text):
        out.append((text[pos:], False))
    return out


class DigitText(ft.Text):
    """ft.Text يُبقي .value كما كتبه المستدعي، ويُرسل لـFlutter مقاطع بخطين عند وجود أرقام."""
    digit_font = None            # يضبطه gui.app.configure: اسم عائلة الخط اللاتيني أو None لتعطيل الميزة
    _raw = None
    _spanned = False

    @property
    def value(self):
        return self._raw

    @value.setter
    def value(self, v):
        self._raw = v
        ft.Text.value.fset(self, v)

    def before_update(self):
        text = "" if self._raw is None else str(self._raw)
        font = DigitText.digit_font
        if font and _RUN.search(text):
            ft.Text.value.fset(self, "")
            self.spans = [ft.TextSpan(chunk, style=ft.TextStyle(font_family=font) if is_num else None)
                          for chunk, is_num in split_runs(text)]
            self._spanned = True
        else:
            ft.Text.value.fset(self, self._raw)
            if self._spanned:
                self.spans = None
                self._spanned = False
        super().before_update()
