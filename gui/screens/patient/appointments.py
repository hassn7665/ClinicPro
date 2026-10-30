# -*- coding: utf-8 -*-
"""قسم «قائمة المواعيد»: السجل المؤكد، المواعيد القادمة، الملغاة/لم يحضر، وحوارات الإضافة والتعديل والإلغاء والحذف."""
from datetime import datetime

import flet as ft

import core as C
from theme import DANGER, DARK, MINT, MUTED, OK, PRIMARY, R_SM, TEXT, TINT_G, TINT_R, WHITE
from core import KIND_AR, ev_dt, rel_label
from gui.common import dur_text, ev_dur, ic
from gui.screens.patient.attachments import event_photos
from gui.screens.patient.confirm import confirm_event_dialog
from gui.when_picker import WhenPicker


def _when(ev):
    return f"{ev['date']} • {C.fmt12(ev['time'] or C.DEFAULT_TIME)}"


def _run(ctx, fn, ok_msg, *args):
    """ينفّذ عملية على موعد: ValueError رسالة للمستخدم؛ أي خطأ آخر يُسجَّل ويُبلَّغ؛ النجاح يعيد رسم الشاشة."""
    a = ctx.app
    try:
        fn(*args)
    except ValueError as ex:
        return a.toast(str(ex), DANGER)
    except Exception as ex:                          # حدّ الواجهة: نسجّل ونُبلغ
        C.LOG.log_exc("appointment_action", ex)
        return a.toast(f"تعذّرت العملية: {ex}", DANGER)
    a.toast(ok_msg, OK)
    ctx.reload()


def history_section(ctx):
    """سجل العمليات والمراجعات المؤكدة (مرتّب بوقت الإنجاز)."""
    a = ctx.app
    T, card, tile, pill, btn, sec = a.T, a.card, a.tile, a.pill, a.btn, a.sec
    hist = [sec("سجل العمليات والمراجعات", "calendar_check")]
    if not ctx.done:
        hist.append(card(T("لا يوجد سجل مؤكد بعد", 13, MUTED), padding=16))
    for ev in sorted(ctx.done, key=lambda z: z["done_at"] or ""):
        surg = ev["kind"] == "surgery"
        hist.append(card(ft.Column([ft.Row([
            tile("scissors" if surg else "stethoscope", TINT_R if surg else TINT_G, "r" if surg else "g", 44, 22, 14),
            ft.Column([
                ft.Row([T(KIND_AR[ev["kind"]], 14, TEXT, True), pill("منجزة", OK, size=11), ic("lock", 16, "m")], spacing=8),
                T(f"الموعد: {_when(ev)}", 12, MUTED),
                T("تم الإنجاز: " + (ev["done_at"] or "")[:16].replace("T", " "), 12, MUTED),
                T(ev["notes"] or "بدون ملاحظات", 13, TEXT)], spacing=2, expand=True)],
            spacing=12, vertical_alignment=ft.CrossAxisAlignment.START),
            event_photos(ctx, ev),
            btn("حذف هذا السجل", "x", lambda e, v=ev: delete_event(ctx, v), kind="outline", height=38)], spacing=12), padding=12))
    return hist


def _pending_card(ctx, ev):
    a = ctx.app
    T, tile, pill, btn = a.T, a.tile, a.pill, a.btn
    start, end = C.ev_span(ev)
    t_from, t_to = C.fmt12(start.strftime("%H:%M")), C.fmt12(end.strftime("%H:%M"))
    late = start < datetime.now()
    surg = ev["kind"] == "surgery"
    cf = C.event_conflicts(ev["date"], ev["time"], ev_dur(ev), ev["id"])
    extra_btns = []
    if late:
        extra_btns.append(btn("لم يحضر", "user_clock", lambda e, v=ev: no_show_dialog(ctx, v), kind="outline", height=40, expand=True))
    extra_btns.append(btn("إلغاء الموعد", "x", lambda e, v=ev: cancel_dialog(ctx, v), kind="danger", height=40, expand=True))
    return a.card(ft.Column([
        ft.Row([tile("scissors" if surg else "stethoscope", TINT_R if surg else TINT_G, "r" if surg else "g", 44, 22, 14),
                ft.Column([T(KIND_AR[ev["kind"]], 14, TEXT, True),
                           T(f"{ev['date']} • {t_from} – {t_to} ({dur_text(ev_dur(ev))})", 13,
                             DANGER if late else MUTED, late)], spacing=0, expand=True),
                pill(rel_label(ev_dt(ev)), DANGER if late else PRIMARY)], spacing=12),
        T(a.conflict_text(cf), 12, DANGER, True) if cf else ft.Container(),
        event_photos(ctx, ev),
        ft.Row([btn("تعديل الموعد", "calendar_edit", lambda e, v=ev: edit_event_dialog(ctx, v), kind="soft", height=44, expand=True),
                btn("تأكيد الإنجاز", "check", lambda e, v=ev: confirm_event_dialog(ctx, v), kind="ok", height=44, expand=True)],
               spacing=12),
        ft.Row(extra_btns, spacing=12),
        ft.Container(T("حذف الموعد نهائياً", 12, DANGER, True), on_click=lambda e, v=ev: delete_event(ctx, v), ink=True,
                     border_radius=R_SM, padding=ft.padding.symmetric(vertical=6, horizontal=10),
                     alignment=ft.alignment.center)], spacing=12), padding=12)


def _cancelled_card(ctx, ev):
    a = ctx.app
    T, btn = a.T, a.btn
    ns = ev["status"] == "no_show"
    return a.card(ft.Column([
        ft.Row([a.tile("user_clock" if ns else "calendar", TINT_R if ns else MINT, "r" if ns else "m", 44, 22, 14),
                ft.Column([T(KIND_AR[ev["kind"]], 14, MUTED, True), T(_when(ev), 12, MUTED)], spacing=0, expand=True),
                a.pill("لم يحضر" if ns else "ملغى", DANGER if ns else MUTED, WHITE, 11)], spacing=12),
        T(((("ملاحظة: " if ns else "السبب: ") + ev["cancel_reason"]) if ev["cancel_reason"] else "بدون سبب مذكور"), 12, MUTED),
        T(("سُجّل في " if ns else "أُلغي في ") + (ev["cancelled_at"] or "")[:16].replace("T", " "), 11, MUTED),
        ft.Row([btn("استعادة الموعد", "restore", lambda e, v=ev: reinstate(ctx, v), kind="soft", height=40, expand=True),
                btn("حذف", "x", lambda e, v=ev: delete_event(ctx, v), kind="outline", height=40, expand=True)], spacing=12)],
        spacing=8), padding=12)


def schedule_section(ctx):
    """المواعيد القادمة (+أزرار إضافة) ثم الملغاة/لم يحضر."""
    a = ctx.app
    sched = [a.sec("المواعيد القادمة", "calendar")]
    if not ctx.pending:
        sched.append(a.card(a.T("لا توجد مواعيد معلّقة", 13, MUTED), padding=16))
    sched += [_pending_card(ctx, ev) for ev in ctx.pending]
    sched.append(ft.Row([
        a.btn("موعد عملية", "scissors", lambda e: add_event_dialog(ctx, "surgery"), kind="danger", expand=True),
        a.btn("موعد مراجعة", "stethoscope", lambda e: add_event_dialog(ctx, "visit"), expand=True)], spacing=12))
    if ctx.cancelled:
        sched.append(a.sec("مواعيد ملغاة / لم يحضر", "x"))
        sched += [_cancelled_card(ctx, ev) for ev in ctx.cancelled]
    return sched


class _Conflict:
    """تنبيه التعارض: نص + زر «تعديل الموعد»، يظهران عند وجود تعارض فقط. **تنبيه لا منع**: الحفظ متاح دائماً."""

    def __init__(self, a, change):
        self.a = a
        self.warn = a.T("", 12, DANGER, True)
        self.fix = a.btn("تعديل الموعد", "calendar_edit", lambda e: change(), kind="soft", height=40)
        self.fix.visible = False
        self.ui = ft.Column([self.warn, self.fix], spacing=6)

    def show(self, rows):
        self.warn.value = (self.a.conflict_text(rows) + "\nيمكنك حفظ الموعد كما هو، أو تعديل وقته.") if rows else ""
        self.fix.visible = bool(rows)

    def refresh(self, rows):
        self.show(rows)
        self.warn.update()
        self.fix.update()


def add_event_dialog(ctx, kind):
    """حوار موعد جديد: كل الاختيار داخله (بلا نوافذ منبثقة متداخلة). التعارض تنبيه فقط والحفظ بنقرة واحدة."""
    a = ctx.app
    T = a.T
    ed_ui, collect, _ = a.items_editor()
    wp = WhenPicker(a, *C.default_slot(), on_change=lambda d, t: check(), expanded=True)
    box = _Conflict(a, wp.open)
    dur_ui, get_dur = a.duration_picker(C.DEFAULT_DURATION.get(kind, 30), lambda m: check())

    def check():
        d, t = wp.value()
        box.refresh(C.event_conflicts(d, t, get_dur()))

    def save(e):
        items = collect()
        if items is None:
            return
        d, t = wp.value()
        try:
            C.create_event(ctx.pid, kind, d, t, items, duration=get_dur())
        except Exception as ex:                             # حدّ الواجهة: نسجّل ونُبلغ والحوار يبقى مفتوحاً
            C.LOG.log_exc("create_event", ex)
            return a.toast(f"تعذر حفظ الموعد: {ex}", DANGER)
        a.page.close(dlg)
        ctx.reload()
    box.show(C.event_conflicts(*wp.value(), get_dur()))
    dlg = a.dialog(f"موعد {KIND_AR[kind]}",
                   ft.Column([wp.ui, dur_ui, box.ui,
                              T("الإجراءات والتكلفة المستحقة (اختياري — يمكن تعديلها لاحقاً)", 12, MUTED), ed_ui],
                             tight=True, width=a.dlg_w(), rtl=True, spacing=12),
                   [a.dlg_btn("حفظ الموعد", save, "ok"), a.dlg_btn("إلغاء", lambda e: a.page.close(dlg))])


def edit_event_dialog(ctx, ev):
    """تعديل موعد قبل تأكيده: النوع والتاريخ والوقت والمدة والإجراءات. التعارض تنبيه فقط، ولا نوافذ متداخلة."""
    a = ctx.app
    T = a.T
    kind_ui, get_kind = a.choice_group("نوع الموعد", ["عملية", "مراجعة"], KIND_AR[ev["kind"]], chip_w=110, allow_none=False)
    ed_ui, collect, _ = a.items_editor(C.ev_items(ev["id"]))
    err = T("", 12, DANGER, True)
    wp = WhenPicker(a, ev["date"], ev["time"] or C.DEFAULT_TIME, on_change=lambda d, t: check(), expanded=False)
    box = _Conflict(a, wp.open)
    dur_ui, get_dur = a.duration_picker(ev_dur(ev), lambda m: check())

    def check():
        d, t = wp.value()
        box.refresh(C.event_conflicts(d, t, get_dur(), ev["id"]))

    def save(e):
        items = collect()
        if items is None:
            return
        kind = {v: k for k, v in KIND_AR.items()}[get_kind() or KIND_AR[ev["kind"]]]
        d, t = wp.value()
        try:
            C.update_event(ev["id"], kind, d, t, items, duration=get_dur())
        except ValueError as ex:
            err.value = str(ex)
            err.update()
            return
        except Exception as ex:                             # حدّ الواجهة: نسجّل ونُبلغ والحوار يبقى مفتوحاً
            C.LOG.log_exc("update_event", ex)
            return a.toast(f"تعذر حفظ التعديل: {ex}", DANGER)
        a.page.close(dlg)
        a.toast("تم تعديل الموعد", OK)
        ctx.reload()
    box.show(C.event_conflicts(*wp.value(), ev_dur(ev), ev["id"]))
    dlg = a.dialog("تعديل الموعد",
                   ft.Column([kind_ui, wp.ui, dur_ui, box.ui, T("الإجراءات والتكلفة المستحقة", 13, DARK, True), ed_ui, err],
                             tight=True, width=a.dlg_w(), rtl=True, spacing=12),
                   [a.dlg_btn("حفظ التعديلات", save, "ok"), a.dlg_btn("إلغاء", lambda e: a.page.close(dlg))])


def _reason_dialog(ctx, ev, title, info, action_label, fn, ok_msg, label, lines=2):
    a = ctx.app
    reason = a.field(label, multiline=True, min_lines=lines)

    def do(e):
        a.page.close(dlg)
        _run(ctx, fn, ok_msg, ev["id"], reason.value)
    dlg = a.dialog(title, ft.Column([a.T(f"{KIND_AR[ev['kind']]} بتاريخ {_when(ev)}", 14, TEXT, True),
                                     a.T(info, 12, MUTED), reason], tight=True, width=a.dlg_w(), rtl=True, spacing=12),
                   [a.dlg_btn(action_label, do, "danger"), a.dlg_btn("تراجع", lambda e: a.page.close(dlg))])


def cancel_dialog(ctx, ev):
    _reason_dialog(ctx, ev, "إلغاء الموعد",
                   "لن يظهر في المواعيد القريبة ولن يُحتسب في الإحصائيات أو المستحقات، ويبقى محفوظاً في سجل المريض.",
                   "إلغاء الموعد", C.cancel_event, "تم إلغاء الموعد وبقي في السجل (يمكن استعادته)", "سبب الإلغاء (اختياري)")


def no_show_dialog(ctx, ev):
    _reason_dialog(ctx, ev, "لم يحضر المريض", "يُغلق الموعد ولا يُحتسب في المستحقات أو المواعيد القريبة، ويبقى في السجل.",
                   "تسجيل «لم يحضر»", C.mark_no_show, "سُجّل «لم يحضر» وأُغلق الموعد (يمكن استعادته)", "ملاحظة (اختياري)", 1)


def reinstate(ctx, ev):
    _run(ctx, C.reinstate_event, "تمت استعادة الموعد", ev["id"])


def delete_event(ctx, ev):
    a = ctx.app
    a.ask_confirm("حذف الموعد نهائياً",
                  f"{KIND_AR[ev['kind']]} بتاريخ {_when(ev)} — سيُحذف مع إجراءاته وصوره ولا يمكن استعادته. "
                  "للإبقاء على السجل استخدم «إلغاء الموعد» بدل الحذف.",
                  lambda: _run(ctx, C.delete_event, "تم حذف الموعد", ev["id"]), "حذف نهائي")
