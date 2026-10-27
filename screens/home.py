# -*- coding: utf-8 -*-
"""الشاشة الرئيسية وبطاقاتها."""

import flet as ft
import core as C
from theme import (BG, DANGER, DARK, DEEP, MINT, MUTED, OK, PRIMARY, R_CARD, R_HERO, R_SM, R_TILE, SURFACE_TINT, TEXT, TINT_A, TINT_G, TINT_R, WHITE, tint)
from core import (APP_NAME, KIND_AR, rel_label)
from ui_kit import (WINDOWS, ic, logo, shadow)


def register(app):
    page, ui = app.page, app.ui
    T, btn, card, fchip, fx, nav_bar, pill, sec, tile = app.T, app.btn, app.card, app.fchip, app.fx, app.nav_bar, app.pill, app.sec, app.tile


    # ═════════════════════ الرئيسية ═════════════════════
    def avatar(name, size=48, bg=None):
        ch = (name or "؟").strip()[:1] or "؟"
        return ft.Container(T(ch, size * 0.42, DEEP, True), width=size, height=size, border_radius=size // 2,
                            bgcolor=bg or MINT, alignment=ft.alignment.center, border=ft.border.all(2, WHITE))


    def stat_mini(icon, color, bg, number, label, on_click):
        return ft.Container(
            ft.Column([tile(icon, bg, color, 36, 18, 11), T(str(number), 22, TEXT, True), T(label, 11, MUTED)],
                      spacing=4), bgcolor=WHITE, border_radius=R_TILE, padding=12, expand=True, ink=True,
            shadow=shadow(), on_click=on_click)


    def cat_tile(icon, label, on_click, filled=False):
        box = ft.Container(ic(icon, 28, "w" if filled else "p"), width=64, height=64, border_radius=R_TILE,
                           bgcolor=PRIMARY if filled else WHITE, alignment=ft.alignment.center,
                           shadow=ft.BoxShadow(blur_radius=14, color=ft.Colors.with_opacity(
                               0.22 if filled else 0.07, PRIMARY if filled else DARK), offset=ft.Offset(0, 5)))
        box = fx(box, PRIMARY if filled else WHITE, DEEP if filled else tint(PRIMARY, .14), on_click)
        return ft.Column([box, T(label, 12, DARK if filled else TEXT, filled, text_align=ft.TextAlign.CENTER)],
                         spacing=8, width=76, horizontal_alignment=ft.CrossAxisAlignment.CENTER)


    def appt_card(dt, ev, late):
        """بطاقة موعد أفقية."""
        return ft.Container(ft.Column([
            avatar(ev["full_name"], 64),
            pill(rel_label(dt), DANGER if late else OK, WHITE, 11),
            T(ev["full_name"], 14, TEXT, True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS,
              text_align=ft.TextAlign.CENTER),
            T(f"{KIND_AR[ev['kind']]} • {ev['time'] or C.DEFAULT_TIME}", 12, MUTED),
            ft.Container(height=2),
            btn("فتح الملف", None, lambda e, pid=ev["patient_id"]: app.patient_screen(pid), height=40)],
            spacing=6, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            width=172, padding=16, bgcolor=WHITE, border_radius=R_CARD, shadow=shadow(), alignment=ft.alignment.center)


    def home(e=None):
        page.clean()
        page.appbar = None
        page.bgcolor = BG
        st, days = C.lic_status()
        if st != "ok":
            return app.license_screen(first=True)

        s = C.stats()

        def round_btn(icn, fn, tip):
            return ft.Container(ic(icn, 24, "d"), width=48, height=48, border_radius=24, bgcolor=WHITE, ink=True,
                                alignment=ft.alignment.center, shadow=shadow(), on_click=fn, tooltip=tip)
        header = ft.Container(ft.Row([
            ft.Row([logo(46), ft.Column([T(APP_NAME, 22, DARK, True, rtl=False), T("مرحباً بك", 13, MUTED)],
                                        spacing=0)], spacing=12),
            ft.Row([round_btn("lock", app.lock_now, "قفل التطبيق"), round_btn("settings", lambda e: app.settings_screen(), "الإعدادات")], spacing=8),
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
            padding=ft.padding.only(left=18, right=18, top=44, bottom=6), rtl=True)

        search_bar = ft.Container(ft.Row([
            ic("search", 24, "m"), T("ابحث عن مريض بالاسم أو الكود أو الهاتف", 13, MUTED, expand=True),
            ft.Container(ic("filter", 20, "w"), width=40, height=40, border_radius=20, bgcolor=PRIMARY,
                         alignment=ft.alignment.center)], spacing=12),
            bgcolor=WHITE, border_radius=R_HERO, padding=ft.padding.only(left=8, right=16, top=8, bottom=8),
            shadow=shadow(), on_click=lambda e: app.search_screen(), ink=True)
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
            cat_tile("user_plus", "إضافة مريض", lambda e: app.patient_form(), filled=True),
            cat_tile("calendar_check", "جدول اليوم", lambda e: app.schedule_screen()),
            cat_tile("wallet", "الحسابات", lambda e: app.accounts_screen()),
            cat_tile("search", "البحث", lambda e: app.search_screen()),
            cat_tile("chart", "الإحصائيات", lambda e: app.stats_screen()),
            cat_tile("backup", "النسخ الاحتياطي", lambda e: app.backup_screen())],
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
            bgcolor=tint(PRIMARY, .14), border_radius=R_CARD, padding=16, on_click=lambda e: app.security_screen(), ink=True)

        body = [
            hero, cats,
            sec("المواعيد القريبة", "bell"), chips, up_row,
            ft.Row([sec("نظرة سريعة", "chart"),
                    ft.Container(T("التفاصيل", 13, PRIMARY, True), on_click=lambda e: app.stats_screen(), ink=True,
                                 padding=ft.padding.symmetric(vertical=4, horizontal=10), border_radius=R_SM)],
                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            ft.Row([stat_mini("users", "p", MINT, s["total_patients"], "المرضى", lambda e: app.stats_screen()),
                    stat_mini("scissors", "r", TINT_R, s["surgeries"], "عمليات منجزة", lambda e: app.stats_screen()),
                    stat_mini("stethoscope", "g", TINT_G, s["visits"], "مراجعات", lambda e: app.stats_screen())],
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
                padding=12, on_click=lambda e: app.backup_screen()))
        if not C.VAULT.has_recovery_key:
            extras.append(card(ft.Row([
                tile("key", TINT_A, "a", 36, 18, 11),
                ft.Column([T("أنشئ مفتاح الاسترداد", 14, DARK, True),
                           T("يمكّنك من استرجاع بياناتك إن نسيت كلمة المرور، دون الحاجة لأي طرف آخر.", 12, MUTED)],
                          spacing=1, expand=True), ic("chevron_left", 20, "m")], spacing=12),
                padding=12, on_click=lambda e: app.security_screen()))
        body[-1:-1] = extras                                  # قبل بطاقة «بياناتك مشفّرة»
        if days <= 30:
            body.append(card(ft.Row([tile("alert", TINT_R, "r", 36, 18, 11),
                                     T(f"ينتهي الترخيص خلال {days} يوماً — جدّده من الإعدادات", 13, DANGER, True,
                                       expand=True)], spacing=12), padding=12))
        body.append(ft.Container(height=10))

        page.add(ft.Column([header, ft.Container(ft.Column(body, spacing=16, rtl=True,
                                                          horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                                                 padding=ft.padding.only(left=16, right=16, top=8, bottom=8), rtl=True)],
                           scroll=ft.ScrollMode.AUTO, expand=True, spacing=0, rtl=True))
        nav_bar(0)
        page.update()

    # ── تسجيل الشاشات/الأدوات ليستعملها غيرها عبر app ──
    app.avatar = avatar
    app.stat_mini = stat_mini
    app.cat_tile = cat_tile
    app.appt_card = appt_card
    app.home = home
