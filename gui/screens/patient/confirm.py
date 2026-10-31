# -*- coding: utf-8 -*-
"""قسم «التأكيد»: تأكيد إنجاز موعد (ملاحظات + إجراءات + دفعات + موعد مراجعة) وحذف المريض نهائياً بتأكيد مضاعف."""
import flet as ft

import core as C
from theme import DANGER, DARK, MUTED, OK, PRIMARY, TEXT
from core import KIND_AR
from gui.common import PAY_LBL
from gui.when_picker import WhenPicker


def confirm_event_dialog(ctx, ev):
    a = ctx.app
    T, btn, field = a.T, a.btn, a.field
    money_field = a.money_field
    notes = field("ملاحظات (اختياري)", multiline=True, min_lines=2)
    extra = []
    follow = {"on": False}
    if ev["kind"] == "visit":
        wp = WhenPicker(a, *C.default_slot(7, ev["time"]), expanded=True)
        wp.ui.visible = False

        def toggle_next(e):
            follow["on"] = e.control.value
            wp.ui.visible = follow["on"]
            wp.ui.update()
        extra = [ft.Row([ft.Switch(value=False, active_color=PRIMARY, on_change=toggle_next),
                         T("حجز موعد مراجعة جديد", 13, DARK, True, expand=True)]), wp.ui]

    _, paid_before, _ = C.amounts(C.ev_fin(ev["id"]))
    ed_ui, collect, total = a.items_editor(C.ev_items(ev["id"]))
    pay_fs = {c: money_field(PAY_LBL[c], hint_text="0") for c in C.CURS}
    pay_err = T("", 12, DANGER, True)

    def pay_all(e):
        tot = total()
        for c in C.CURS:
            v = max(tot[c] - paid_before[c], 0)
            pay_fs[c].value, pay_fs[c].error_text = (C.money(v) if v > 0 else ""), None
            pay_fs[c].update()
        pay_err.value = ""
        pay_err.update()

    def do(e):
        items = collect()
        if items is None:
            return
        pays, bad = a.read_pays(pay_fs)
        if bad:
            return
        try:
            C.confirm_event(ev["id"], notes.value.strip(), items, pays, wp.value() if follow["on"] else None)
        except ValueError as ex:
            pay_err.value = str(ex)
            pay_err.update()
            return
        except Exception as ex:                          # حدّ الواجهة: نسجّل ونُبلغ
            C.LOG.log_exc("confirm_event", ex)
            return a.toast(f"تعذر التأكيد: {ex}", DANGER)
        a.page.close(dlg)
        a.toast("تم تأكيد الإنجاز وتسجيله في الملف", OK)
        ctx.reload()
    fin_ctrls = [T("الإجراءات والتكلفة المستحقة", 13, DARK, True), ed_ui]
    if any(paid_before.values()):
        fin_ctrls.append(T("مدفوع سابقاً: " + C.money_multi(paid_before), 12, OK, True))
    fin_ctrls += [T("المبلغ المدفوع الآن — اختر العملة بتعبئة حقلها، أو ادفع بالعملتين معاً", 12, MUTED)] + \
        list(pay_fs.values()) + [pay_err, btn("دفع المتبقي كاملاً", "coins", pay_all, kind="soft", height=40)]
    dlg = a.dialog(f"تأكيد إنجاز {KIND_AR[ev['kind']]}",
                   ft.Column([T("بعد التأكيد لا يمكن تعديل التاريخ.", 12, DANGER, True), notes] + fin_ctrls + extra,
                             tight=True, width=a.dlg_w(), rtl=True, spacing=12),
                   [a.dlg_btn("تأكيد", do, "ok"), a.dlg_btn("إلغاء", lambda e: a.page.close(dlg))])


def delete_patient_dialog(ctx, e=None):
    a = ctx.app
    T = a.T
    try:
        sm = C.patient_delete_summary(ctx.pid)
    except ValueError as ex:
        return a.toast(str(ex), DANGER)
    sure = ft.Switch(value=False, active_color=DANGER)
    err = T("", 12, DANGER, True)
    lines = [f"المواعيد: {sm['events']} (منجزة {sm['done']})", f"المرفقات: {sm['attachments']} • الصور: {sm['photos']}"]
    if any(sm["paid"].values()):
        lines.append("مدفوعات مسجّلة ستُحذف: " + C.money_multi(sm["paid"]))
    if any(v > 0 for v in sm["remaining"].values()):
        lines.append("متبقٍ عليه (سيضيع سجله): " + C.money_multi({k: max(v, 0) for k, v in sm["remaining"].items()}))

    def go(e2):
        if not sure.value:
            err.value = "فعّل الخيار لتأكيد الحذف النهائي"
            return err.update()
        try:
            C.delete_patient(ctx.pid)
        except Exception as ex:                          # حدّ الواجهة: نسجّل ونُبلغ
            C.LOG.log_exc("delete_patient", ex)
            a.page.close(d)
            return a.toast(f"تعذّر الحذف: {ex}", DANGER)
        a.page.close(d)
        a.toast("تم حذف المريض وكل بياناته", OK)
        a.s.home()
    d = a.dialog("حذف المريض نهائياً",
                 ft.Column([T(sm["name"] + " — " + sm["code"], 15, DARK, True),
                            T("سيُحذف كل ما يخصه نهائياً، ولا يمكن التراجع إلا باستعادة نسخة احتياطية "
                              "(تُؤخذ نسخة تلقائياً قبل الحذف إن لم تكن حديثة).", 12, DANGER, True)] +
                           [T(ln, 13, TEXT) for ln in lines] +
                           [ft.Row([sure, T("أفهم أن الحذف نهائي", 13, TEXT, True, expand=True)]), err],
                           tight=True, width=a.dlg_w(), rtl=True, spacing=10),
                 [a.dlg_btn("حذف نهائي", go, "danger"), a.dlg_btn("تراجع", lambda e2: a.page.close(d))])
