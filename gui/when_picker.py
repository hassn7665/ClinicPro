# -*- coding: utf-8 -*-
"""
gui/when_picker.py — اختيار الموعد (التاريخ + الوقت) **داخل الحوار نفسه** بلا نوافذ منبثقة متداخلة.

لماذا؟ فتح منتقٍ منبثق فوق حوار قائم يُغلق الحوار الأم عند انتهائه فيضيع التعديل (هذا كان سبب «تُغلق النافذة ولا يُحفظ الموعد»).
هنا كل شيء عناصر عادية داخل الحوار:
  • ملخص دائم: «الخميس 29 تشرين الأول 2026 — 03:30 م» + زر تعديل/تم.
  • اللوحة: اختصارات (اليوم، غداً، بعد غد، بعد أسبوع) · شهر بتقويم يبدأ من السبت مع نقطة على الأيام المشغولة ·
    الساعة 1–12 · الدقائق · زرّا صباحاً/مساءً الصريحان.
value() ترجع (YYYY-MM-DD, HH:MM) بنظام 24 ساعة داخلياً.
"""
import calendar
from datetime import date, timedelta

import flet as ft

import core as C
from theme import ACCENT, BORDER, DARK, FIELD_BG, MINT, MUTED, PRIMARY, R_CTRL, R_SM, SOFT, WHITE
from gui.common import AR_DAYS, AR_MONTHS

WEEK_HEAD = ["س", "ح", "ن", "ث", "ر", "خ", "ج"]            # السبت أولاً
QUICK = [("اليوم", 0), ("غداً", 1), ("بعد غد", 2), ("بعد أسبوع", 7)]
AM, PM = "ص", "م"


def pretty_date(d: date) -> str:
    return f"{AR_DAYS[d.weekday()]} {d.day} {AR_MONTHS[d.month - 1]} {d.year}"


def month_weeks(year: int, month: int):
    """أسابيع الشهر (السبت أولاً)؛ 0 = خانة فارغة."""
    return calendar.Calendar(firstweekday=5).monthdayscalendar(year, month)


class WhenPicker:
    def __init__(self, app, d: str, hm: str, on_change=None, expanded=True):
        self.a, self.on_change = app, on_change
        self.d = date.fromisoformat(d)
        self.h, self.m, self.ap = C.hm_to_12(hm)
        self.view = date(self.d.year, self.d.month, 1)
        self._busy_cache = {}
        T = app.T
        self.sum_date, self.sum_time = T("", 15, DARK, True), T("", 20, PRIMARY, True)
        self.toggle_lbl = T("", 13, PRIMARY, True)
        self.toggle = ft.Container(self.toggle_lbl, on_click=lambda e: self.set_open(not self.panel.visible), ink=True,
                                   border_radius=R_SM, padding=ft.padding.symmetric(horizontal=12, vertical=8),
                                   bgcolor=MINT, data="when:toggle")
        self.panel = ft.Column(spacing=14, rtl=True)
        self.panel.visible = expanded
        self.summary = ft.Container(ft.Row([
            app.tile("calendar", MINT, "p", 44, 22, 14),
            ft.Column([self.sum_date, self.sum_time], spacing=0, expand=True), self.toggle], spacing=12),
            padding=12, border_radius=R_CTRL, bgcolor=SOFT["p"][0], border=ft.border.all(1, SOFT["p"][1]))
        self.ui = ft.Column([self.summary, self.panel], spacing=10, rtl=True)
        self._fill()

    # ── الواجهة العامة ──
    def value(self):
        return self.d.isoformat(), C.hm_from_12(self.h, self.m, self.ap)

    def set_open(self, flag: bool):
        self.panel.visible = flag
        self._label()
        self._upd(self.toggle, self.panel)

    def open(self):
        self.set_open(True)

    # ── بناء ──
    def _label(self):
        self.toggle_lbl.value = "تم" if self.panel.visible else "تعديل"

    def _fill(self):
        self.sum_date.value = pretty_date(self.d)
        self.sum_time.value = C.fmt12(self.value()[1])
        self._label()
        self.panel.controls = [self._quick(), self._calendar(), self._time()]

    def _chip(self, label, selected, handler, data, height=38):
        T = self.a.T
        return ft.Container(T(label, 14, WHITE if selected else DARK, True, text_align=ft.TextAlign.CENTER), expand=True,
                            height=height, alignment=ft.alignment.center, bgcolor=PRIMARY if selected else FIELD_BG,
                            border_radius=R_SM, border=ft.border.all(1, PRIMARY if selected else BORDER), ink=True,
                            on_click=handler, data=data)

    def _quick(self):
        today = date.today()
        return ft.Row([self._chip(lbl, self.d == today + timedelta(days=n), lambda e, n=n: self._set_day(today + timedelta(days=n)),
                                  f"quick:{n}", 36) for lbl, n in QUICK], spacing=6, rtl=True)

    def _busy(self, first: date):
        key = (first.year, first.month)
        if key not in self._busy_cache:
            start = first - timedelta(days=(first.weekday() - 5) % 7)          # أول سبت في شبكة الشهر
            self._busy_cache[key] = C.day_counts(start.isoformat(), 42)
        return self._busy_cache[key]

    def _calendar(self):
        T, today = self.a.T, date.today()
        busy = self._busy(self.view)
        nav = ft.Row([
            ft.Container(ft.Icon(ft.Icons.CHEVRON_RIGHT, color=DARK, size=26), on_click=lambda e: self._nav(-1), ink=True,
                         border_radius=R_SM, padding=4, data="nav:-1"),
            T(f"{AR_MONTHS[self.view.month - 1]} {self.view.year}", 15, DARK, True, expand=True, text_align=ft.TextAlign.CENTER),
            ft.Container(ft.Icon(ft.Icons.CHEVRON_LEFT, color=DARK, size=26), on_click=lambda e: self._nav(1), ink=True,
                         border_radius=R_SM, padding=4, data="nav:1")], rtl=True)
        head = ft.Row([T(h, 12, MUTED, True, expand=True, text_align=ft.TextAlign.CENTER) for h in WEEK_HEAD], rtl=True)
        rows = []
        for week in month_weeks(self.view.year, self.view.month):
            cells = []
            for day in week:
                if not day:
                    cells.append(ft.Container(expand=True, height=46))
                    continue
                dd = date(self.view.year, self.view.month, day)
                sel = dd == self.d
                dot = ft.Container(width=5, height=5, border_radius=3,
                                   bgcolor=(WHITE if sel else ACCENT) if busy.get(dd.isoformat()) else None)
                cells.append(ft.Container(
                    ft.Column([T(str(day), 14, WHITE if sel else DARK, sel or dd == today, text_align=ft.TextAlign.CENTER), dot],
                              spacing=1, tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                              alignment=ft.MainAxisAlignment.CENTER),
                    expand=True, height=46, alignment=ft.alignment.center, bgcolor=PRIMARY if sel else None,
                    border_radius=R_SM, border=ft.border.all(1.5, PRIMARY) if dd == today and not sel else None, ink=True,
                    on_click=lambda e, dd=dd: self._set_day(dd), data=f"day:{dd.isoformat()}"))
            rows.append(ft.Row(cells, spacing=2, rtl=True))
        legend = ft.Row([ft.Container(width=7, height=7, border_radius=4, bgcolor=ACCENT), T("يوم فيه مواعيد", 11, MUTED)],
                        spacing=6, rtl=True)
        return ft.Column([nav, head] + rows + [legend], spacing=4, rtl=True)

    def _time(self):
        T = self.a.T
        mins = sorted(set(range(0, 60, 5)) | {self.m})
        hours = [self._chip(str(h), h == self.h, lambda e, h=h: self._set_time(h=h), f"h:{h}") for h in range(1, 13)]
        minute = [self._chip(f"{m:02d}", m == self.m, lambda e, m=m: self._set_time(m=m), f"m:{m}") for m in mins]
        rows = lambda chips, n: [ft.Row(chips[i:i + n], spacing=6, rtl=True) for i in range(0, len(chips), n)]
        ampm = ft.Row([self._chip("صباحاً (ص)", self.ap == AM, lambda e: self._set_time(ap=AM), f"ap:{AM}", 44),
                       self._chip("مساءً (م)", self.ap == PM, lambda e: self._set_time(ap=PM), f"ap:{PM}", 44)],
                      spacing=8, rtl=True)
        return ft.Column([T("الساعة", 12, MUTED, True)] + rows(hours, 6) + [T("الدقيقة", 12, MUTED, True)] + rows(minute, 6)
                         + [ampm], spacing=6, rtl=True)

    # ── أحداث ──
    def _nav(self, delta):
        y, m = self.view.year, self.view.month + delta
        y, m = (y + (m - 1) // 12, (m - 1) % 12 + 1)
        self.view = date(y, m, 1)
        self._changed(notify=False)

    def _set_day(self, d: date):
        self.d = d
        self.view = date(d.year, d.month, 1)
        self._changed()

    def _set_time(self, h=None, m=None, ap=None):
        self.h, self.m, self.ap = h or self.h, self.m if m is None else m, ap or self.ap
        self._changed()

    def _changed(self, notify=True):
        self._fill()
        self._upd(self.summary, self.panel)
        if notify and self.on_change:
            self.on_change(*self.value())

    @staticmethod
    def _upd(*controls):
        for c in controls:
            try:
                c.update()
            except AssertionError:                    # لم يُضَف للصفحة بعد (أثناء البناء الأول)
                pass

