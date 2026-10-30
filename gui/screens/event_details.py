# -*- coding: utf-8 -*-
"""
تفاصيل الموعد — نافذة تُفتح من بطاقات المواعيد القريبة وجدول اليوم بدل زر «فتح الملف» المباشر:
نوع الموعد والوقت (12 ساعة) والحالة والإجراءات وتكلفتها، وفي النهاية زر «فتح ملف المريض».
لا SQL: كل البيانات من C.event_detail.
"""
import flet as ft

import core as C
from theme import DANGER, DARK, MUTED, OK, PRIMARY, TEXT, TINT_G, TINT_R, WHITE
from core import KIND_AR
from gui.common import STATUS_UI, dur_text, ev_dur


def install(app):
    def event_details(event_id):
        d = C.event_detail(event_id)
        if d is None:
            return app.toast("هذا الموعد لم يعد موجوداً", DANGER)
        a, ev = app, d["ev"]
        T = a.T
        surg = ev["kind"] == "surgery"
        t_from, t_to = C.fmt12(d["start"].strftime("%H:%M")), C.fmt12(d["end"].strftime("%H:%M"))
        label, col = STATUS_UI[d["status"]]
        rows = [
            ft.Row([a.tile("scissors" if surg else "stethoscope", TINT_R if surg else TINT_G, "r" if surg else "g", 44, 22, 14),
                    ft.Column([T(ev["full_name"], 15, DARK, True), T(f"{KIND_AR[ev['kind']]} • {ev['code']}", 12, MUTED)],
                              spacing=1, expand=True),
                    a.pill(label, col, WHITE, 11)], spacing=12),
            _line(a, "التاريخ", ev["date"]),
            _line(a, "الوقت", f"{t_from} – {t_to}"),
            _line(a, "المدة", dur_text(ev_dur(ev))),
        ]
        if ev["phone"]:
            rows.append(_line(a, "الهاتف", ev["phone"]))
        rows += _procedures(a, d)
        if ev["status"] == "done" and ev["notes"]:
            rows.append(_line(a, "ملاحظات الإنجاز", ev["notes"]))
        if ev["status"] in ("cancelled", "no_show") and ev["cancel_reason"]:
            rows.append(_line(a, "السبب", ev["cancel_reason"]))

        def open_file(e):
            a.page.close(dlg)
            a.s.patient_screen(ev["patient_id"])
        dlg = a.dialog("تفاصيل الموعد", ft.Column(rows, tight=True, width=a.dlg_w(), rtl=True, spacing=10),
                       [a.dlg_btn("فتح ملف المريض", open_file, "primary"), a.dlg_btn("إغلاق", lambda e: a.page.close(dlg))])

    app.register(event_details=event_details)


def _line(a, label, value):
    return ft.Row([a.T(label, 12, MUTED, width=90), a.T(str(value), 13, TEXT, True, expand=True, selectable=True)], spacing=8,
                  vertical_alignment=ft.CrossAxisAlignment.START)


def _procedures(a, d):
    """قسم الإجراءات (عملية أو مراجعة): اسم كل إجراء وتكلفته، ثم الإجمالي والمدفوع إن وُجدت تكلفة."""
    items = d["items"]
    if not items:
        return [a.T("الإجراءات", 12, MUTED, True), a.T("لا توجد إجراءات مسجّلة لهذا الموعد", 13, MUTED)]
    out = [a.T("الإجراءات", 12, MUTED, True)]
    out += [ft.Row([a.T("• " + it["name"], 13, TEXT, expand=True), a.T(C.money(it["price"], it["cur"]), 12, PRIMARY, True)])
            for it in items]
    out.append(ft.Divider(height=1))
    out.append(_line(a, "المستحق", C.money_multi(d["due"])))
    if any(d["paid"].values()):
        out.append(_line(a, "المدفوع", C.money_multi(d["paid"])))
        if any(v > 0 for v in d["remaining"].values()):
            out.append(ft.Row([a.T("المتبقي", 12, MUTED, width=90),
                               a.T(C.money_multi({k: max(v, 0) for k, v in d["remaining"].items()}), 13, DANGER, True)], spacing=8))
        else:
            out.append(ft.Row([a.T("الحالة المالية", 12, MUTED, width=90), a.T("مسدّد بالكامل", 13, OK, True)], spacing=8))
    return out
