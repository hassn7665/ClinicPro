# -*- coding: utf-8 -*-
"""
البحث — لا تحتوي أي SQL: كل الوصول للبيانات عبر core.
"""
import flet as ft
import core as C

from theme import (PRIMARY, BLUE, TEXT, MUTED, MINT)


def install(app):
    _with_nav = app.with_nav
    T = app.T
    card = app.card
    tile = app.tile
    pill = app.pill
    btn = app.btn
    field = app.field
    show = app.show
    def home(*a, **k):
        return app.s.home(*a, **k)
    def patient_screen(*a, **k):
        return app.s.patient_screen(*a, **k)

    SORTS = {"alpha": "الأبجدي", "newest": "الأحدث أولاً", "oldest": "الأقدم أولاً"}
    PAGE = 30

    def patient_card(r):
        sub = [T(r["code"], 12, MUTED), pill(r["status"], PRIMARY if r["status"] == "جديد" else BLUE, size=11)]
        return card(ft.Row([
            tile("user", MINT, "p", 44, 22, 14),
            ft.Column([T(r["full_name"], 14, TEXT, True), ft.Row(sub, spacing=8),
                       T("سُجّل: " + (r["created_at"] or "")[:10], 11, MUTED),
                       T(r["phone"] or "", 12, MUTED, selectable=True) if r["phone"] else ft.Container()],
                      spacing=4, expand=True),
            btn("فتح الملف", "file", lambda e, i=r["id"]: patient_screen(i), height=40)], spacing=12), padding=12)

    def search_screen():
        """بحث، أو تصفّح كل المرضى (مربع البحث فارغ) بترتيب أبجدي أو زمني."""
        st = {"limit": PAGE}
        results = ft.Column(spacing=12, rtl=True)
        box = field("ابحث بالاسم أو الكود أو الهاتف")
        inv = {v: k for k, v in SORTS.items()}

        def sort_key():
            return inv[get_sort()]

        def go(e=None, update=True):
            results.controls.clear()
            term = (box.value or "").strip()
            if term:
                rows, total = C.search_patients(term, 50, sort_key()), None
            else:
                rows, total = C.list_patients(sort_key(), 0, st["limit"])
            if not rows:
                results.controls.append(card(ft.Column([
                    tile("search", MINT, "p", 52, 26, 16), T("لا توجد نتائج" if term else "لا يوجد مرضى بعد", 14, MUTED, True)],
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8), padding=24))
            elif total is not None:
                results.controls.append(T(f"كل المرضى ({total})", 13, MUTED, True))
            results.controls += [patient_card(r) for r in rows]
            if total is not None and total > st["limit"]:
                results.controls.append(btn("عرض المزيد", "plus", more, kind="soft", height=44))
            if update:
                results.update()

        def more(e):
            st["limit"] += PAGE
            go()

        def on_sort(v):
            app.ui["patient_sort"] = inv[v]
            st["limit"] = PAGE
            go()
        sort_ui, get_sort = app.choice_group("ترتيب المرضى", list(SORTS.values()), SORTS[app.ui.get("patient_sort", "alpha")],
                                             on_sort, allow_none=False)

        def typed(e=None):
            st["limit"] = PAGE
            go()
        box.on_change = typed
        box.on_submit = typed
        go(update=False)
        show("البحث عن مريض", [box, T("اترك المربع فارغاً لتصفّح كل المرضى", 12, MUTED), sort_ui, results], back=home)

    search_screen = _with_nav(search_screen, 3)
    app.register(search_screen=search_screen)
