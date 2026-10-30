# -*- coding: utf-8 -*-
"""
الشاشة الرئيسية — لا تحتوي أي SQL: كل الوصول للبيانات عبر core.
"""
import flet as ft
import core as C

from theme import (PRIMARY, DARK, DANGER, WHITE, BG, MUTED, MINT, TINT_R, TINT_G, TINT_A, R_SM, R_CARD, R_HERO, SURFACE_TINT, tint)
from core import (APP_NAME)
from gui.common import (WINDOWS, ic, logo, shadow)


def install(app):
    page = app.page
    ui = app.ui
    T = app.T
    card = app.card
    tile = app.tile
    sec = app.sec
    fchip = app.fchip
    nav_bar = app.nav_bar
    stat_mini = app.stat_mini
    cat_tile = app.cat_tile
    appt_card = app.appt_card
    def license_screen(*a, **k):
        return app.s.license_screen(*a, **k)
    def settings_screen(*a, **k):
        return app.s.settings_screen(*a, **k)
    def security_screen(*a, **k):
        return app.s.security_screen(*a, **k)
    def stats_screen(*a, **k):
        return app.s.stats_screen(*a, **k)
    def backup_screen(*a, **k):
        return app.s.backup_screen(*a, **k)
    def patient_form(*a, **k):
        return app.s.patient_form(*a, **k)
    def search_screen(*a, **k):
        return app.s.search_screen(*a, **k)
    def schedule_screen(*a, **k):
        return app.s.schedule_screen(*a, **k)
    def accounts_screen(*a, **k):
        return app.s.accounts_screen(*a, **k)
    def lock_now(*a, **k):
        return app.s.lock_now(*a, **k)

    def home(e=None):
        page.clean()
        page.appbar = None
        page.bgcolor = BG
        st, days = C.lic_status()
        if st != "ok":
            return license_screen(first=True)

        s = C.stats()

        def round_btn(icn, fn, tip):
            return ft.Container(ic(icn, 24, "d"), width=48, height=48, border_radius=24, bgcolor=WHITE, ink=True,
                                alignment=ft.alignment.center, shadow=shadow(), on_click=fn, tooltip=tip)
        header = ft.Container(ft.Row([
            ft.Row([logo(46), ft.Column([T(APP_NAME, 22, DARK, True, rtl=False), T("مرحباً بك", 13, MUTED)],
                                        spacing=0)], spacing=12),
            ft.Row([round_btn("lock", lock_now, "قفل التطبيق"), round_btn("settings", lambda e: settings_screen(), "الإعدادات")], spacing=8),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.only(left=18, right=18, top=44, bottom=6), rtl=True)

        search_bar = ft.Container(ft.Row([
            ic("search", 24, "m"), T("ابحث عن مريض بالاسم أو الكود أو الهاتف", 13, MUTED, expand=True),
            ft.Container(ic("filter", 20, "w"), width=40, height=40, border_radius=20, bgcolor=PRIMARY,
                         alignment=ft.alignment.center)], spacing=12),
            bgcolor=WHITE, border_radius=R_HERO, padding=ft.padding.only(left=8, right=16, top=8, bottom=8),
            shadow=shadow(), on_click=lambda e: search_screen(), ink=True)
        hero = ft.Container(ft.Column([
            ft.Row([ft.Column([T("إدارة عيادتك", 20, DARK, True),
                               T("المرضى والمواعيد والحسابات في مكان واحد وبأمان.", 12, MUTED)], spacing=4, expand=True),
                    ft.Image(src="/icons/hero.svg", width=104, height=104, fit=ft.ImageFit.CONTAIN,
                             error_content=ft.Container(width=104, height=104))],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            search_bar], spacing=12),
            padding=16, border_radius=R_HERO,
            gradient=ft.LinearGradient(colors=[tint(PRIMARY, .2), SURFACE_TINT], begin=ft.alignment.top_right,
                                       end=ft.alignment.bottom_left),
            border=ft.border.all(1, tint(PRIMARY, .18)))

        cats = ft.Row([
            cat_tile("user_plus", "إضافة مريض", lambda e: patient_form(), filled=True),
            cat_tile("calendar_check", "جدول اليوم", lambda e: schedule_screen()),
            cat_tile("wallet", "الحسابات", lambda e: accounts_screen()),
            cat_tile("search", "البحث", lambda e: search_screen()),
            cat_tile("chart", "الإحصائيات", lambda e: stats_screen()),
            cat_tile("backup", "النسخ الاحتياطي", lambda e: backup_screen())],
            scroll=ft.ScrollMode.AUTO, spacing=12, rtl=True)

        chips = ft.Row(wrap=True, spacing=8, run_spacing=8, rtl=True)
        up_row = ft.Row(scroll=ft.ScrollMode.AUTO, spacing=12, rtl=True)

        def render_up():
            late, soon = C.upcoming_events(ui["win"])
            chips.controls = [fchip(t, ui["win"] == d, lambda e, d=d: set_win(d)) for t, d in WINDOWS]
            items = [appt_card(dt, ev, True) for dt, ev in late] + [appt_card(dt, ev, False) for dt, ev in soon]
            if not items:
                items = [ft.Container(ft.Row([tile("calendar_check", MINT, "p", 44, 22, 14),
                                              T("لا توجد مواعيد في هذه الفترة", 14, MUTED, True)], spacing=12),
                                      bgcolor=WHITE, border_radius=R_CARD, padding=16, shadow=shadow())]
            up_row.controls = items

        def set_win(d):
            ui["win"] = d
            render_up()
            chips.update()
            up_row.update()
        render_up()

        banner = ft.Container(ft.Row([
            ft.Container(ic("shield_check", 28, "p"), width=46, height=46, border_radius=23, bgcolor=WHITE,
                         alignment=ft.alignment.center),
            ft.Column([T("بياناتك مشفّرة ومحمية", 14, DARK, True),
                       T("تخزين محلي مشفّر على جهازك مع نسخ احتياطي دوري.", 12, MUTED)], spacing=1, expand=True),
            ic("chevron_left", 20, "m")], spacing=12),
            bgcolor=tint(PRIMARY, .14), border_radius=R_CARD, padding=16, on_click=lambda e: security_screen(), ink=True)

        body = [
            hero, cats,
            sec("المواعيد القريبة", "bell"), chips, up_row,
            ft.Row([sec("نظرة سريعة", "chart"),
                    ft.Container(T("التفاصيل", 13, PRIMARY, True), on_click=lambda e: stats_screen(), ink=True,
                                 padding=ft.padding.symmetric(vertical=4, horizontal=10), border_radius=R_SM)],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([stat_mini("users", "p", MINT, s["total_patients"], "المرضى", lambda e: stats_screen()),
                    stat_mini("scissors", "r", TINT_R, s["surgeries"], "عمليات منجزة", lambda e: stats_screen()),
                    stat_mini("stethoscope", "g", TINT_G, s["visits"], "مراجعات", lambda e: stats_screen())],
                   spacing=12),
            banner,
        ]
        extras = []
        due, ex_days = C.export_due()
        if due:
            extras.append(card(ft.Row([
                tile("backup", TINT_R, "r", 36, 18, 11),
                ft.Column([T("انسخ بياناتك خارج الهاتف", 14, DANGER, True),
                           T("لم تُصدَّر أي نسخة احتياطية بعد" if ex_days is None else
                             f"آخر تصدير قبل {ex_days} يوماً. النسخ الداخلية تُحذف مع إلغاء التثبيت أو فقدان الهاتف.", 12, MUTED)],
                          spacing=1, expand=True), ic("chevron_left", 20, "m")], spacing=12),
                padding=12, on_click=lambda e: backup_screen()))
        if not C.VAULT.has_recovery_key:
            extras.append(card(ft.Row([
                tile("key", TINT_A, "a", 36, 18, 11),
                ft.Column([T("أنشئ مفتاح الاسترداد", 14, DARK, True),
                           T("يمكّنك من استرجاع بياناتك إن نسيت كلمة المرور، دون الحاجة لأي طرف آخر.", 12, MUTED)],
                          spacing=1, expand=True), ic("chevron_left", 20, "m")], spacing=12),
                padding=12, on_click=lambda e: security_screen()))
        body[-1:-1] = extras                                  # قبل بطاقة «بياناتك مشفّرة»
        if days <= 7:                                          # تنبيه الانتهاء: خلال 7 أيام فقط
            when_ = "ينتهي الترخيص اليوم" if days == 0 else (
                "ينتهي الترخيص غداً" if days == 1 else f"ينتهي الترخيص خلال {days} أيام")
            body.append(card(ft.Row([tile("alert", TINT_R, "r", 36, 18, 11),
                                     T(f"{when_} — جدّد قبل انتهاء المدة", 13, DANGER, True, expand=True)], spacing=12),
                             padding=12))
        body.append(ft.Container(height=10))

        page.add(ft.Column([header, ft.Container(ft.Column(body, spacing=16, rtl=True,
                                                          horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                                                 padding=ft.padding.only(left=16, right=16, top=8, bottom=8), rtl=True)],
                           scroll=ft.ScrollMode.AUTO, expand=True, spacing=0, rtl=True))
        nav_bar(0)
        page.update()

    app.register(home=home)
