# -*- coding: utf-8 -*-
"""قسم «بطاقة المعلومات»: الرأس، شريط الحساسية، البيانات الشخصية، المعلومات الطبية."""
import flet as ft

import core as C
from theme import ACCENT, BLUE, DANGER, DARK, DEEP, MUTED, R_CARD, R_FIELD, SOFT, TEXT, TINT_R, WHITE


def _fact(a, label, value):
    return ft.Container(ft.Column([a.T(label, 11, MUTED), a.T(value, 16, DARK, True)], spacing=0,
                                  horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        expand=True, bgcolor=WHITE, border=ft.border.all(1, SOFT["p"][1]),
                        border_radius=R_FIELD, padding=12)


def _header(ctx):
    a, p = ctx.app, ctx.p
    T, pill = a.T, a.pill
    age = C.patient_age(p)
    facts = ft.Row([_fact(a, "العمر", str(age) if age is not None else "—"),
                    _fact(a, "الجنس", p["gender"] or "—"), _fact(a, "زمرة الدم", p["blood"] or "—")], spacing=8)
    initial = (p["full_name"].strip() or "؟")[0]
    return ft.Container(ft.Column([
        ft.Row([
            ft.Container(T(initial, 28, DEEP, True), width=64, height=64, border_radius=32, bgcolor=WHITE,
                         border=ft.border.all(1.5, SOFT["p"][1]), alignment=ft.alignment.center),
            ft.Column([T(p["full_name"], 20, DARK, True),
                       ft.Row([pill(p["code"], DARK, WHITE),
                               pill(p["status"], ACCENT if p["status"] == "جديد" else BLUE, WHITE)], spacing=8)],
                      spacing=6, expand=True)], spacing=16),
        facts], spacing=16),
        padding=16, border_radius=R_CARD, rtl=True, bgcolor=SOFT["p"][0], border=ft.border.all(1.2, SOFT["p"][1]))


def _allergy_banner(ctx):
    a, p = ctx.app, ctx.p
    if not (p["allergies"] or "").strip():
        return []
    return [a.card(ft.Row([a.tile("alert", TINT_R, "r", 36, 18, 11),
                           ft.Column([a.T("حساسية", 12, DANGER, True), a.T(p["allergies"], 14, TEXT, True, selectable=True)],
                                     spacing=1, expand=True)], spacing=12), padding=12, bgcolor=TINT_R, border=True)]


def info_section(ctx):
    """بطاقة المعلومات كاملة: [الرأس] + [شريط الحساسية إن وُجدت] + [شخصية، طبية]."""
    a, p = ctx.app, ctx.p
    card, sec, info_row = a.card, a.sec, a.info_row
    personal = card(ft.Column([
        sec("البيانات الشخصية", "badge"),
        info_row("phone", "رقم التواصل", p["phone"]), info_row("pin", "مكان السكن", p["residence"]),
        info_row("briefcase", "العمل", p["job"]),
        info_row("calendar", "تاريخ التسجيل", (p["created_at"] or "")[:10], last=True)], spacing=12))
    medical = card(ft.Column([
        sec("المعلومات الطبية", "heart_pulse"),
        info_row("droplet", "زمرة الدم", p["blood"], pill_color=DANGER if p["blood"] else None),
        info_row("heart_pulse", "الأمراض", p["diseases"]),
        info_row("alert", "الحساسية", p["allergies"]),
        info_row("note", "الأدوية الحالية", p["medications"]),
        info_row("stethoscope", "التشخيص", p["diagnosis"]),
        info_row("note", "ملاحظات", p["notes"], last=True)], spacing=12))
    return [_header(ctx)] + _allergy_banner(ctx) + [personal, medical]
