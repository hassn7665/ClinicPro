# -*- coding: utf-8 -*-
"""
الإحصائيات — لا تحتوي أي SQL: كل الوصول للبيانات عبر core.
"""
from datetime import datetime, timedelta

import flet as ft
import core as C

from theme import (PRIMARY, DARK, BLUE, WHITE, TEXT, MUTED, BORDER, MINT, TINT_R, TINT_G, TINT_A, R_TILE)
from core import (today)
from gui.common import (RANGES, ic, shadow)


def install(app):
    toast = app.toast
    T = app.T
    card = app.card
    tile = app.tile
    fchip = app.fchip
    show = app.show
    ask_date = app.ask_date
    def home(*a, **k):
        return app.s.home(*a, **k)

    def stats_screen():
        sel = {"r": 30, "lo": None, "hi": None}
        chips = ft.Row(wrap=True, spacing=8, run_spacing=8, rtl=True)
        body = ft.Column(spacing=12, rtl=True)

        def bounds():
            r = sel["r"]
            if r is None:
                return None, None
            if r == "custom":
                return sel["lo"], sel["hi"]
            return (datetime.now() - timedelta(days=r)).strftime("%Y-%m-%d") if r else today(), today()

        def big(icon, bg, col, number, label):
            return ft.Container(
                ft.Column([tile(icon, bg, col, 44, 22, 14), T(str(number), 28, TEXT, True), T(label, 12, MUTED)],
                          spacing=4), bgcolor=WHITE, border_radius=R_TILE, padding=16, expand=True,
                border=ft.border.all(1, BORDER), shadow=shadow())

        def small(label, number, color):
            return ft.Row([ft.Container(width=10, height=10, border_radius=5, bgcolor=color), T(label, 14, TEXT, expand=True),
                           T(str(number), 16, TEXT, True)], spacing=12)

        def render(update=True):
            lo, hi = bounds()
            s = C.stats(lo, hi)
            rng = "كل الفترات" if lo is None and hi is None else f"{lo or '…'}  ←  {hi or '…'}"
            chips.controls = [fchip(t, sel["r"] == v, lambda e, v=v: pick_range(v)) for t, v in RANGES]
            body.controls = [
                card(ft.Row([ic("calendar", 20, "p"), T("النطاق الزمني:", 13, MUTED), T(rng, 14, DARK, True)],
                            spacing=8), padding=12),
                ft.Row([big("users", MINT, "p", s["patients"], "مرضى جدد في الفترة"),
                        big("scissors", TINT_R, "r", s["surgeries"], "عمليات منجزة")], spacing=12),
                ft.Row([big("stethoscope", TINT_G, "g", s["visits"], "مراجعات منجزة"),
                        big("calendar", TINT_A, "a", s["pending"], "مواعيد معلّقة")], spacing=12),
                ft.Row([big("x", MINT, "m", s["cancelled"], "مواعيد ملغاة"),
                        big("user_clock", TINT_R, "r", s["no_show"], "لم يحضروا")], spacing=12),
                card(ft.Column([T("تفصيل المرضى في الفترة", 14, DARK, True),
                                small("مرضى جدد", s["new"], PRIMARY), small("مرضى قدامى", s["old"], BLUE),
                                ft.Divider(height=1, color=BORDER),
                                small("إجمالي المرضى في التطبيق", s["total_patients"], MUTED)], spacing=12)),
            ]
            if update:
                chips.update()
                body.update()

        def pick_range(v):
            if v == "custom":
                def got_lo(d):
                    sel["lo"] = d.strftime("%Y-%m-%d")

                    def got_hi(d2):
                        sel.update(r="custom", hi=d2.strftime("%Y-%m-%d"))
                        if sel["hi"] < sel["lo"]:
                            sel["lo"], sel["hi"] = sel["hi"], sel["lo"]
                        render()
                    toast("اختر تاريخ النهاية")
                    ask_date(got_hi)
                toast("اختر تاريخ البداية")
                ask_date(got_lo)
                return
            sel["r"] = v
            render()
        render(update=False)
        show("الإحصائيات", [chips, body, ft.Container(height=10)], back=home)

    app.register(stats_screen=stats_screen)
