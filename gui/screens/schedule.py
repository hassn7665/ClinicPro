# -*- coding: utf-8 -*-
"""
جدول اليوم — لا تحتوي أي SQL: كل الوصول للبيانات عبر core.
"""
from datetime import datetime, timedelta

import flet as ft
import core as C

from theme import (PRIMARY, DARK, DANGER, OK, WHITE, TEXT, MUTED, BORDER, MINT, TINT_R, TINT_G, R_SM)
from core import (KIND_AR, today)
from gui.common import (AR_DAYS, AR_DAYS_SHORT, dur_text, ev_dur, STATUS_UI)
from gui.screens.patient.appointments import edit_event_dialog
from gui.screens.patient.context import PatientCtx


def install(app):
    _with_nav = app.with_nav
    page = app.page
    toast = app.toast
    T = app.T
    card = app.card
    tile = app.tile
    pill = app.pill
    btn = app.btn
    icon_btn = app.icon_btn
    fchip = app.fchip
    field = app.field
    show = app.show
    dlg_w = app.dlg_w
    dialog = app.dialog
    dlg_btn = app.dlg_btn
    ask_date = app.ask_date
    def home(*a, **k):
        return app.s.home(*a, **k)
    def search_screen(*a, **k):
        return app.s.search_screen(*a, **k)
    def patient_screen(*a, **k):
        return app.s.patient_screen(*a, **k)

    def schedule_screen(date_s=None):
        """جدول يوم واحد مرتّباً بالوقت: المدة، التعارض بين المواعيد، «لم يحضر»، وتنقّل بين الأيام."""
        date_s = date_s or today()
        d0 = datetime.strptime(date_s, "%Y-%m-%d")
        items = C.day_schedule(date_s)
        names = {i["ev"]["id"]: i for i in items}
        go = lambda d: schedule_screen(d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else d)
        shift = lambda n: (lambda e: go(d0 + timedelta(days=n)))
        rel = {0: "اليوم", 1: "غداً", -1: "أمس"}.get((d0.date() - datetime.now().date()).days, "")

        head = card(ft.Row([
            icon_btn("arrow_right", "d", shift(-1), bg=WHITE, tip="اليوم السابق"),
            ft.Column([T(f"{AR_DAYS[d0.weekday()]} {date_s}", 16, DARK, True, text_align=ft.TextAlign.CENTER),
                       T(rel or " ", 12, PRIMARY, True, text_align=ft.TextAlign.CENTER)], spacing=0, expand=True,
                      horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            icon_btn("chevron_left", "d", shift(1), bg=WHITE, tip="اليوم التالي")],
            vertical_alignment=ft.CrossAxisAlignment.CENTER), padding=10)

        counts = C.day_counts((d0 - timedelta(days=3)).strftime("%Y-%m-%d"), 7)
        strip = ft.Row([
            ft.Container(ft.Column([
                T(AR_DAYS_SHORT[dd.weekday()], 10, WHITE if k == date_s else MUTED, True, text_align=ft.TextAlign.CENTER),
                T(str(dd.day), 15, WHITE if k == date_s else DARK, True, text_align=ft.TextAlign.CENTER),
                T("●" if counts[k] else " ", 8, WHITE if k == date_s else PRIMARY, text_align=ft.TextAlign.CENTER)],
                spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                expand=True, bgcolor=PRIMARY if k == date_s else WHITE, border_radius=R_SM, ink=True,
                border=ft.border.all(1, PRIMARY if k == date_s else BORDER), padding=ft.padding.symmetric(vertical=6),
                on_click=lambda e, k=k: go(k))
            for dd, k in ((d0 + timedelta(days=i), (d0 + timedelta(days=i)).strftime("%Y-%m-%d")) for i in range(-3, 4))],
            spacing=6)

        def pick_day(e):
            ask_date(lambda d: go(d), initial=d0)
        actions = ft.Row([fchip("اليوم", date_s == today(), lambda e: go(today())),
                          fchip("اختيار تاريخ", False, pick_day),
                          fchip("موعد جديد", False, lambda e: (toast("ابحث عن المريض ثم أضف موعداً من ملفه"), search_screen()))],
                         wrap=True, spacing=8, run_spacing=8, rtl=True)

        active = [i for i in items if i["status"] not in ("cancelled", "no_show")]
        n_conf = sum(1 for i in active if i["conflicts"])
        summary = ft.Row([pill(f"{len(active)} موعد", PRIMARY, size=11),
                          pill(f"{sum(1 for i in items if i['status'] == 'done')} منجز", OK, size=11),
                          pill(f"{sum(1 for i in items if i['status'] == 'no_show')} لم يحضر", DANGER, size=11)] +
                         ([pill(f"{n_conf} متعارض", DANGER, size=11)] if n_conf else []),
                         wrap=True, spacing=8, run_spacing=6, rtl=True)

        def mark_no_show(i):
            reason = field("ملاحظة (اختياري)")

            def do(e):
                try:
                    C.mark_no_show(i["ev"]["id"], reason.value)
                except ValueError as ex:
                    page.close(dlg)
                    return toast(str(ex), DANGER)
                page.close(dlg)
                toast("سُجّل «لم يحضر»", OK)
                go(date_s)
            dlg = dialog("لم يحضر المريض", ft.Column([T(i["ev"]["full_name"], 14, TEXT, True), reason],
                                                       tight=True, width=dlg_w(), rtl=True, spacing=10),
                         [dlg_btn("تسجيل", do, "danger"), dlg_btn("تراجع", lambda e: page.close(dlg))])

        def restore(i):
            try:
                C.reinstate_event(i["ev"]["id"])
            except ValueError as ex:
                return toast(str(ex), DANGER)
            go(date_s)

        def edit_conflicting(i):
            ctx = PatientCtx(app, i["ev"]["patient_id"])
            ctx.reload = lambda: go(date_s)                              # بعد الحفظ نبقى في الجدول لا في ملف المريض
            edit_event_dialog(ctx, i["ev"])

        def row(i):
            ev, st = i["ev"], i["status"]
            label, col = STATUS_UI[st]
            surg = ev["kind"] == "surgery"
            dim = st in ("cancelled", "no_show")
            conf = ""
            if i["conflicts"]:
                conf = "⚠ يتعارض مع: " + "، ".join(
                    f"{names[c]['ev']['full_name']} ({C.fmt12(names[c]['start'].strftime('%H:%M'))} – {C.fmt12(names[c]['end'].strftime('%H:%M'))})" for c in i["conflicts"][:3])
            btns = [btn("عرض التفاصيل", "file", lambda e, i=ev["id"]: app.s.event_details(i), kind="soft", height=40, expand=True)]
            if i["conflicts"] and st in ("pending", "late"):          # التعارض تنبيه لا منع: زر لتعديل الموعد إن شاء
                btns.append(btn("تعديل الموعد", "calendar_edit", lambda e, i=i: edit_conflicting(i), kind="outline", height=40,
                                expand=True))
            if st in ("pending", "late") and i["start"] <= datetime.now():
                btns.append(btn("لم يحضر", "user_clock", lambda e, i=i: mark_no_show(i), kind="outline", height=40, expand=True))
            if dim:
                btns.append(btn("استعادة", "restore", lambda e, i=i: restore(i), kind="outline", height=40, expand=True))
            return card(ft.Column([
                ft.Row([ft.Column([T(C.fmt12(i["start"].strftime("%H:%M")), 15, MUTED if dim else DARK, True),
                                   T("حتى " + C.fmt12(i["end"].strftime("%H:%M")), 11, MUTED)], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        tile("scissors" if surg else "stethoscope", TINT_R if surg else TINT_G, "r" if surg else "g", 44, 22, 14),
                        ft.Column([T(ev["full_name"], 14, MUTED if dim else TEXT, True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                   T(f"{KIND_AR[ev['kind']]} • {dur_text(ev_dur(ev))}" + (f" • {ev['phone']}" if ev["phone"] else ""),
                                     12, MUTED)], spacing=1, expand=True),
                        pill(label, col, WHITE, 11)], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                T(conf, 12, DANGER, True) if conf else ft.Container(),
                ft.Row(btns, spacing=10)], spacing=10), padding=12,
                bgcolor=TINT_R if i["conflicts"] else WHITE)

        body = [head, strip, actions, summary]
        if not items:
            body.append(card(ft.Column([tile("calendar_check", MINT, "p", 52, 26, 16),
                                        T("لا توجد مواعيد في هذا اليوم", 14, MUTED, True)],
                                       horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8), padding=24))
        body += [row(i) for i in items] + [ft.Container(height=10)]
        show("جدول المواعيد", body, back=home)

    schedule_screen = _with_nav(schedule_screen, 1)
    app.register(schedule_screen=schedule_screen)
