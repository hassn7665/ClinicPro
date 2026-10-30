# -*- coding: utf-8 -*-
"""
الحسابات والملف المالي — لا تحتوي أي SQL: كل الوصول للبيانات عبر core.
"""
from datetime import datetime, timedelta

import flet as ft
import core as C

from theme import (PRIMARY, DEEP, DARK, DANGER, OK, BLUE, WHITE, TEXT, MUTED, BORDER, MINT, TINT_R, TINT_G, R_SM, R_CARD, SOFT)
from core import (KIND_AR, today)
from gui.common import (PAY_LBL, FRANGES, ic, shadow)


def install(app):
    _with_nav = app.with_nav
    page = app.page
    ui = app.ui
    toast = app.toast
    T = app.T
    card = app.card
    tile = app.tile
    pill = app.pill
    btn = app.btn
    icon_btn = app.icon_btn
    sec = app.sec
    fchip = app.fchip
    field = app.field
    show = app.show
    dlg_w = app.dlg_w
    dialog = app.dialog
    dlg_btn = app.dlg_btn
    cur_chips = app.cur_chips
    items_editor = app.items_editor
    read_pays = app.read_pays
    open_url = app.open_url
    ask_date = app.ask_date
    fin_box = app.fin_box
    rem_pill = app.rem_pill
    def home(*a, **k):
        return app.s.home(*a, **k)
    def patient_screen(*a, **k):
        return app.s.patient_screen(*a, **k)

    def accounts_screen():
        sel = ui.setdefault("acc", {"r": "month", "lo": None, "hi": None})
        box = field("ابحث باسم المريض أو كوده أو هاتفه")
        chips = ft.Row(wrap=True, spacing=8, run_spacing=8, rtl=True)
        body = ft.Column(spacing=12, rtl=True)

        def bounds():
            r, now = sel["r"], datetime.now()
            if r == "today":
                return today(), today()
            if r == "week":
                return (now - timedelta(days=6)).strftime("%Y-%m-%d"), today()
            if r == "month":
                first = now.replace(day=1)
                return first.strftime("%Y-%m-%d"), (C.add_months(first, 1) - timedelta(days=1)).strftime("%Y-%m-%d")
            if r == "custom":
                return sel["lo"], sel["hi"]
            return None, None

        def cur_card(c, s):
            return ft.Container(ft.Column([
                ft.Row([pill(C.CUR_SYM[c], PRIMARY if c == "SYP" else BLUE, size=12), T(C.CUR_NAME[c], 13, DARK, True)],
                       spacing=8),
                T("المدفوع", 11, MUTED), T(C.money(s["paid"][c], c), 16, OK, True),
                ft.Divider(height=1, color=BORDER),
                T("المستحق (المتبقي)", 11, MUTED),
                T(C.money(s["outstanding"][c], c), 14, DANGER if s["outstanding"][c] > 0 else TEXT, True),
                T("إجمالي المسجّل", 11, MUTED), T(C.money(s["registered"][c], c), 13, TEXT)], spacing=4),
                bgcolor=WHITE, border_radius=R_CARD, padding=12, expand=True,
                border=ft.border.all(1, BORDER), shadow=shadow())

        def render(update=True):
            term = (box.value or "").strip()
            chips.controls = [fchip(t, sel["r"] == v, lambda e, v=v: pick_range(v)) for t, v in FRANGES]
            chips.visible = not term
            if term:                                           # نتائج البحث عن مريض
                rows = C.fin_patients(term)
                ctrls = [card(ft.Column([tile("search", MINT, "p", 52, 26, 16), T("لا توجد نتائج", 14, MUTED, True)],
                                        horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8), padding=24)] \
                    if not rows else []
                for r in rows:
                    ctrls.append(card(ft.Row([
                        tile("user", MINT, "p", 44, 22, 14),
                        ft.Column([T(r["full_name"], 14, TEXT, True),
                                   T(f"{r['code']}  •  مدفوع: {C.money_multi(r['paid'])}", 11, MUTED)],
                                  spacing=2, expand=True),
                        rem_pill(r["due"], r["rem"])], spacing=12),
                        padding=12, on_click=lambda e, i=r["id"]: financial_screen(i, accounts_screen)))
                body.controls = ctrls
            else:                                              # الإحصائية المالية بالعملتين
                lo, hi = bounds()
                s = C.fin_stats(lo, hi)
                rng = "كل الفترات" if lo is None and hi is None else f"{lo or '…'}  ←  {hi or '…'}"
                groups = [card(T("لا توجد دفعات مسجّلة في هذه الفترة", 13, MUTED), padding=16)] if not s["groups"] else []
                for key, g in s["groups"]:
                    groups.append(card(ft.Row([
                        ft.Column([T(key, 14, TEXT, True), T(f"{g['n']} دفعة", 11, MUTED)], spacing=0, expand=True),
                        ft.Column([T(C.money(g[c], c), 13, OK, True) for c in C.CURS if g[c]] or [T("0", 13, MUTED)],
                                  spacing=1, horizontal_alignment=ft.CrossAxisAlignment.END)], spacing=12), padding=12))
                body.controls = [
                    card(ft.Row([ic("calendar", 20, "p"), T("النطاق الزمني:", 13, MUTED), T(rng, 14, DARK, True)],
                                spacing=8), padding=12),
                    ft.Row([cur_card(c, s) for c in C.CURS], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START),
                    card(ft.Column([
                        ft.Row([T("عدد الدفعات المستلمة", 13, TEXT, expand=True), T(str(s["n_pays"]), 14, TEXT, True)]),
                        ft.Row([T("عدد المواعيد المسعّرة", 13, TEXT, expand=True), T(str(s["n_events"]), 14, TEXT, True)])],
                        spacing=8), padding=12),
                    sec("التفصيل الشهري للمدفوع" if s["by_month"] else "التفصيل اليومي للمدفوع", "calendar")] + groups
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
        box.on_change = lambda e: render()
        box.on_submit = lambda e: render()
        render(update=False)
        show("الحسابات", [box, chips, body, ft.Container(height=10)], back=home)

    def financial_screen(pid, back=None):
        p = C.get_patient(pid)
        if not p:
            return home()
        back = back or (lambda: patient_screen(pid))
        here = lambda: financial_screen(pid, back)
        entries, tdue, tpaid, trem = C.fin_file(pid)

        def do_print(e):
            try:
                open_url(C.build_fin_report(pid))
                toast("يُفتح الملف المالي في المتصفح — اضغط «طباعة / حفظ PDF»")
            except Exception as ex:
                toast(f"تعذر إنشاء التقرير: {ex}", DANGER)

        def edit_items(ev):
            ed_ui, collect, _ = items_editor(C.ev_items(ev["id"]))
            err = T("", 12, DANGER, True)

            def save(e):
                items = collect()
                if items is None:
                    return
                try:
                    C.update_items(ev["id"], items)
                except ValueError as ex:
                    err.value = str(ex)
                    err.update()
                    return
                page.close(dlg)
                toast("تم تحديث الإجراءات والتكلفة", OK)
                here()
            dlg = dialog("الإجراءات والتكلفة",
                         ft.Column([T(f"{KIND_AR[ev['kind']]}  •  {ev['date']}", 13, PRIMARY, True), ed_ui, err],
                                   tight=True, width=dlg_w(), rtl=True, spacing=12),
                         [dlg_btn("حفظ", save, "ok"), dlg_btn("إلغاء", lambda e: page.close(dlg))])

        def pay(ev):
            _, _, rem = C.amounts(ev)
            fs = {c: field(PAY_LBL[c], value=C.money(rem[c]) if rem[c] > 0 else "",
                           keyboard_type=ft.KeyboardType.NUMBER) for c in C.CURS}
            note = field("ملاحظة (اختياري)")
            err = T("", 12, DANGER, True)

            def save(e):
                pays, bad = read_pays(fs)
                if bad:
                    return
                try:
                    C.add_payments(ev["id"], pays, (note.value or "").strip())
                except ValueError as ex:
                    err.value = str(ex)
                    err.update()
                    return
                page.close(dlg)
                toast("تم تسجيل الدفعة", OK)
                here()
            dlg = dialog("تسجيل دفعة",
                         ft.Column([T("المتبقي: " + C.money_multi({c: max(v, 0) for c, v in rem.items()}), 13, DANGER, True),
                                    T("اختر العملة بتعبئة حقلها، أو ادفع بالعملتين معاً", 12, MUTED)] +
                                   list(fs.values()) + [note, err], tight=True, width=dlg_w(), rtl=True, spacing=12),
                         [dlg_btn("حفظ", save, "ok"), dlg_btn("إلغاء", lambda e: page.close(dlg))])

        def edit_pay(pm):
            amt = field("المبلغ", value=C.money(pm["amount"]), keyboard_type=ft.KeyboardType.NUMBER)
            chips, get_cur = cur_chips(pm["cur"])
            note = field("ملاحظة (اختياري)", value=pm["note"] or "")
            err = T("", 12, DANGER, True)

            def save(e):
                try:
                    v = C.parse_money(amt.value)
                except ValueError:
                    amt.error_text = "مبلغ غير صحيح"
                    amt.update()
                    return
                try:
                    C.edit_payment(pm["id"], v, get_cur(), (note.value or "").strip())
                except ValueError as ex:
                    err.value = str(ex)
                    err.update()
                    return
                page.close(dlg)
                toast("تم تعديل الدفعة", OK)
                here()

            def ask_delete(e):
                page.close(dlg)

                def do_delete(e):
                    C.delete_payment(pm["id"])
                    page.close(dlg2)
                    toast("تم حذف الدفعة", OK)
                    here()
                dlg2 = dialog("حذف الدفعة",
                              T(f"سيتم حذف دفعة بقيمة {C.money(pm['amount'], pm['cur'])} نهائياً.", 14, TEXT),
                              [dlg_btn("حذف", do_delete, "danger"), dlg_btn("تراجع", lambda e: page.close(dlg2))])
            dlg = dialog("تعديل الدفعة",
                         ft.Column([T(f"تاريخ الدفعة: {(pm['paid_at'] or '')[:10]}", 12, MUTED), amt,
                                    T("العملة", 13, MUTED, True), chips, note, err],
                                   tight=True, width=dlg_w(), rtl=True, spacing=12),
                         [dlg_btn("حفظ", save, "ok"), dlg_btn("حذف الدفعة", ask_delete, "danger"),
                          dlg_btn("إلغاء", lambda e: page.close(dlg))])

        header = ft.Container(ft.Column([
            ft.Row([ft.Container(T((p["full_name"].strip() or "؟")[0], 24, DEEP, True), width=54, height=54,
                                 border_radius=27, bgcolor=WHITE, border=ft.border.all(1.5, SOFT["p"][1]),
                                 alignment=ft.alignment.center),
                    ft.Column([T(p["full_name"], 18, DARK, True), pill(p["code"], DARK, WHITE)], spacing=4, expand=True)],
                   spacing=12),
            ft.Row([fin_box("المستحق", tdue, DARK, WHITE), fin_box("المدفوع", tpaid, OK, WHITE),
                    fin_box("المتبقي", trem, DANGER if any(v > 0 for v in trem.values()) else OK, WHITE)], spacing=8,
                   vertical_alignment=ft.CrossAxisAlignment.START)], spacing=16),
            padding=16, border_radius=R_CARD, rtl=True, bgcolor=SOFT["p"][0], border=ft.border.all(1.2, SOFT["p"][1]))

        cards = []
        if not entries:
            cards.append(card(T("لا توجد مواعيد أو إجراءات لهذا المريض بعد", 13, MUTED), padding=16))
        for en in entries:
            ev, items, pays, due, paid, rem = en["ev"], en["items"], en["pays"], en["due"], en["paid"], en["rem"]
            owes = any(v > 0 for v in rem.values())
            surg = ev["kind"] == "surgery"
            item_rows = [ft.Row([T(i["name"], 13, TEXT, expand=True), T(C.money(i["price"], i["cur"]), 13, DARK, True)],
                                spacing=8) for i in items] or [T("لم تُحدَّد الإجراءات / التكلفة بعد", 12, MUTED)]
            pay_rows = [ft.Container(ft.Row([
                ic("coins", 16, "g"),
                T(((pm["paid_at"] or "")[:10]) + (f" — {pm['note']}" if pm["note"] else ""), 12, MUTED, expand=True),
                T(C.money(pm["amount"], pm["cur"]), 12, OK, True), ic("edit", 16, "m")], spacing=6),
                on_click=lambda e, pm=pm: edit_pay(pm), ink=True, border_radius=R_SM, padding=ft.padding.symmetric(vertical=10, horizontal=6)) for pm in pays]
            btns = [btn("تعديل الإجراءات", "edit", lambda e, v=ev: edit_items(v), kind="soft", height=42, expand=True)]
            if owes:
                btns.append(btn("تسجيل دفعة", "coins", lambda e, v=ev: pay(v), kind="ok", height=42, expand=True))
            if ev["status"] in ("cancelled", "no_show"):
                btns = []          # موعد ملغى: لا تعديل ولا دفعات ولا مستحق
            cards.append(card(ft.Column([
                ft.Row([tile("scissors" if surg else "stethoscope", TINT_R if surg else TINT_G, "r" if surg else "g", 44, 22, 14),
                        ft.Column([T(KIND_AR[ev["kind"]], 14, TEXT, True),
                                   T(f"{ev['date']} • {C.fmt12(ev['time'] or C.DEFAULT_TIME)}", 12, MUTED)], spacing=0, expand=True),
                        pill("ملغى" if ev["status"] in ("cancelled", "no_show") else ("منجز" if ev["status"] == "done" else "معلّق"),
                             MUTED if ev["status"] in ("cancelled", "no_show") else (OK if ev["status"] == "done" else BLUE), size=11)], spacing=12),
                ft.Divider(height=1, color=BORDER)] + item_rows + [
                ft.Divider(height=1, color=BORDER),
                ft.Row([T("المستحق", 13, MUTED), T(C.money_multi(due), 14, DARK, True, expand=True, text_align=ft.TextAlign.END)]),
                ft.Row([T("المدفوع", 13, MUTED), T(C.money_multi(paid), 14, OK, True, expand=True, text_align=ft.TextAlign.END)]),
                ft.Row([T("المتبقي", 13, MUTED), T(C.money_multi(rem), 14, DANGER if owes else OK, True, expand=True,
                                                   text_align=ft.TextAlign.END)])] +
                pay_rows + [ft.Row(btns, spacing=8)], spacing=8), padding=12))

        show("الملف المالي", [header, sec("الإجراءات والدفعات", "receipt")] + cards + [
            T("اضغط على أي دفعة لتعديل مبلغها أو عملتها أو حذفها", 11, MUTED),
            btn("طباعة الملف المالي", "printer", do_print, kind="outline"), ft.Container(height=16)],
            back=back, actions=[icon_btn("printer", "d", do_print)])

    accounts_screen = _with_nav(accounts_screen, 2)
    app.register(accounts_screen=accounts_screen, financial_screen=financial_screen)
