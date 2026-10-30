# -*- coding: utf-8 -*-
"""
شاشتا التفعيل (الترخيص) والترحيب — لا تحتوي أي SQL: كل الوصول للبيانات عبر core.
"""
import time

import flet as ft
import core as C

from theme import (PRIMARY, DARK, DANGER, OK, WHITE, BG, TEXT, MUTED, MINT, SURFACE_TINT, tint)
from core import (APP_NAME)
from gui.common import (logo)


def install(app):
    page = app.page
    toast = app.toast
    T = app.T
    card = app.card
    tile = app.tile
    btn = app.btn
    icon_btn = app.icon_btn
    field = app.field
    show = app.show
    def home(*a, **k):
        return app.s.home(*a, **k)
    def boot_account(*a, **k):
        return app.s.boot_account(*a, **k)

    def license_screen(first=False, back=None):
        d = C.lic_load()
        st, days = C.lic_status()
        code = field("كود التفعيل (الصقه كما وصلك)", hint_text="XXXXX-XXXXX-XXXXX-…", text_align=ft.TextAlign.LEFT,
                     multiline=True, min_lines=3, max_lines=6, capitalization=ft.TextCapitalization.CHARACTERS)
        title, sub, colr, icn = {
            "none": ("التطبيق غير مفعّل", "أرسل معرّف الجهاز إلى المطوّر لتحصل على كود التفعيل.", DANGER, "lock"),
            "expired": ("انتهت مدة الترخيص", "أرسل معرّف الجهاز للحصول على كود تجديد. بياناتك محفوظة.", DANGER, "lock"),
            "clock": ("تاريخ الجهاز غير صحيح",
                      f"تاريخ الجهاز أقدم من آخر استخدام مسجّل ({d['last_seen'][:10]}). صحّح التاريخ والوقت، أو أرسل "
                      "معرّف الجهاز للمطوّر ليصدر لك «كود فك قفل التاريخ».", DANGER, "alert"),
            "tampered": ("تعذّر التحقق من ملف الترخيص", "ملف الترخيص تالف أو معدَّل. أرسل معرّف الجهاز للمطوّر للحصول على كود تفعيل جديد.",
                         DANGER, "alert"),
            "ok": ("الترخيص فعّال", f"متبقٍ {days} يوماً. يمكنك التجديد مبكراً وستُضاف المدة إلى المتبقي.", OK, "shield_check"),
        }[st]

        def activate(e):
            ok, m = C.lic_activate(code.value)
            toast(m, OK if ok else DANGER)
            if ok:
                boot_account() if first else (back or home)()

        def paste_code(e):
            try:
                code.value = (page.get_clipboard() or "").strip()
                code.update()
            except Exception:
                toast("تعذّر القراءة من الحافظة — الصق الكود يدوياً داخل الحقل", DANGER)

        def copy_id(e):
            page.set_clipboard(d["device_id"])
            toast("تم نسخ معرّف الجهاز")

        ctrls = [
            card(ft.Column([
                tile(icn, ft.Colors.with_opacity(0.12, colr), {"r": "r", "g": "g"}[("r" if colr == DANGER else "g")], 64, 32, 20),
                T(title, 20, DARK, True, text_align=ft.TextAlign.CENTER),
                T(sub, 13, MUTED, text_align=ft.TextAlign.CENTER)],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8)),
            card(ft.Row([ft.Column([T("معرّف الجهاز", 12, MUTED),
                                    T(d["device_id"].upper(), 28, PRIMARY, True, selectable=True)], spacing=0),
                         icon_btn("share", "p", copy_id)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)),
        ]
        if d["expires"]:
            ctrls.append(card(ft.Row([tile("calendar", MINT, "p", 44, 22, 14),
                                      ft.Column([T("ينتهي الترخيص في", 12, MUTED),
                                                 T(d["expires"][:10], 16, TEXT, True)], spacing=0)], spacing=12)))
        ctrls += [code, btn("لصق من الحافظة", "download", paste_code, kind="soft", height=44),
                  btn("تفعيل" if st != "ok" else "تجديد", "key", activate)]
        show("تفعيل التطبيق" if first else "الترخيص", ctrls, back=None if first else (back or home))

    def splash():
        page.clean()
        page.appbar = None
        page.bottom_appbar = None
        page.bgcolor = BG
        anim = ft.Animation(700, ft.AnimationCurve.EASE_OUT)
        mark = ft.Container(logo(84), width=140, height=140, border_radius=70, bgcolor=WHITE,
                            alignment=ft.alignment.center, opacity=0, animate_opacity=anim,
                            shadow=ft.BoxShadow(blur_radius=30, color=ft.Colors.with_opacity(0.18, PRIMARY),
                                                offset=ft.Offset(0, 10)))
        name = ft.Text(APP_NAME, size=36, weight=ft.FontWeight.BOLD, color=DARK, opacity=0,
                       animate_opacity=anim, rtl=False)
        bar = ft.Container(width=44, height=4, border_radius=2, bgcolor=PRIMARY, opacity=0, animate_opacity=anim)
        prog = ft.ProgressBar(width=130, bar_height=3, color=PRIMARY, bgcolor=tint(PRIMARY, .18), opacity=0,
                              animate_opacity=anim)
        circle = lambda s, l, t, o: ft.Container(width=s, height=s, border_radius=s // 2, left=l, top=t,
                                                 bgcolor=tint(PRIMARY, o))
        page.add(ft.Container(ft.Stack([
            circle(300, -100, -90, .13), circle(200, 220, 560, .11), circle(90, 260, 150, .09),
            ft.Container(ft.Column([mark, ft.Container(height=18), name, ft.Container(height=4), bar],
                                   alignment=ft.MainAxisAlignment.CENTER,
                                   horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                         alignment=ft.alignment.center, left=0, right=0, top=0, bottom=80),
            ft.Container(prog, alignment=ft.alignment.center, left=0, right=0, bottom=60),
        ], expand=True), expand=True,
            gradient=ft.LinearGradient(colors=[tint(PRIMARY, .22), SURFACE_TINT], begin=ft.alignment.top_center,
                                       end=ft.alignment.bottom_center)))
        page.update()
        for c in (mark, name, bar, prog):
            c.opacity = 1
        page.update()
        time.sleep(2.0)
        home()

    app.register(license_screen=license_screen, splash=splash)
