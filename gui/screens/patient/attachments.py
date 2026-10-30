# -*- coding: utf-8 -*-
"""قسم «المرفقات»: صور المريض الثلاث، قائمة المرفقات (فتح/إعادة تسمية/حذف)، وصور قبل/بعد لكل موعد."""
import os

import flet as ft

import core as C
from theme import BORDER, BORDER_STRONG, DANGER, DARK, FIELD_BG, MINT, MUTED, OK, PRIMARY, R_CTRL, R_SM, TEXT
from core import ap
from gui.common import ic


def _photo_thumb(ctx, label, rel):
    a = ctx.app
    tw = int((a.width() - 32 - 32 - 20) / 3)
    if rel and os.path.exists(ap(rel)):
        inner = a.img_ctl(rel, tw, tw)
        click = lambda e: a.s.image_screen(rel, ctx.reload)
    else:
        inner = ft.Column([ic("image", 28, "m"), a.T("لا توجد", 11, MUTED)], spacing=2,
                          alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        click = None
    return ft.Column([ft.Container(inner, width=tw, height=tw, border_radius=R_CTRL, bgcolor=FIELD_BG,
                                   clip_behavior=ft.ClipBehavior.ANTI_ALIAS, alignment=ft.alignment.center,
                                   border=ft.border.all(1, BORDER), on_click=click, ink=click is not None),
                      a.T(label, 12, DARK, True)], spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER)


def _open_attachment(ctx, att):
    a = ctx.app
    if not os.path.exists(ap(att["path"])):
        return a.toast("الملف غير موجود على الجهاز", DANGER)
    if C.is_image_name(att["name"]):
        return a.s.image_screen(att["path"], ctx.reload)
    try:                       # PDF/Word/Excel…: يُفكّ تشفيره مؤقتاً ويُفتح عبر المتصفح (يُمحى عند القفل)
        a.open_url(C.share_attachment(att["path"], att["name"]))
        a.toast("يُفتح الملف في المتصفح…")
    except Exception as ex:                       # حدّ الواجهة: نسجّل ونُبلغ ولا نُسقط التطبيق
        C.LOG.log_exc("open_attachment", ex)
        a.toast(f"تعذر فتح الملف: {ex}", DANGER)


def _rename_attachment(ctx, att):
    a = ctx.app
    nm = a.field("اسم المرفق", value=att["name"])
    err = a.T("", 12, DANGER, True)

    def go(e):
        try:
            C.rename_attachment(att["id"], nm.value)
        except ValueError as ex:
            err.value = str(ex)
            return err.update()
        a.page.close(d)
        a.toast("تمت إعادة التسمية", OK)
        ctx.reload()
    d = a.dialog("إعادة تسمية المرفق", ft.Column([nm, err], tight=True, width=a.dlg_w(), rtl=True, spacing=10),
                 [a.dlg_btn("حفظ", go, "ok"), a.dlg_btn("إلغاء", lambda e: a.page.close(d))])


def _delete_attachment(ctx, att):
    a = ctx.app

    def do():
        try:
            C.delete_attachment(att["id"])
        except Exception as ex:                       # حدّ الواجهة: نسجّل ونُبلغ
            C.LOG.log_exc("delete_attachment", ex)
            return a.toast(f"تعذّر الحذف: {ex}", DANGER)
        a.toast("تم حذف المرفق", OK)
        ctx.reload()
    a.ask_confirm("حذف المرفق", f"سيُحذف «{att['name']}» نهائياً من ملف المريض.", do, "حذف")


def attachments_section(ctx):
    """بطاقة صور المريض + بطاقة المرفقات (إن وُجدت)."""
    a, p = ctx.app, ctx.p
    T, card, tile, sec = a.T, a.card, a.tile, a.sec
    photos = card(ft.Column([
        sec("الصور", "image"),
        ft.Row([_photo_thumb(ctx, "قبل", p["photo_before"]), _photo_thumb(ctx, "بعد", p["photo_after"]),
                _photo_thumb(ctx, "التحاليل", p["photo_lab"])], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
        T("اضغط على أي صورة لعرضها بالحجم الكامل", 11, MUTED)], spacing=12))
    if not ctx.atts:
        return [photos]
    rows = []
    for att in ctx.atts:
        is_img = C.is_image_name(att["name"])
        rows.append(ft.Container(ft.Row([
            tile("image" if is_img else "file", MINT, "p", 36, 18, 11),
            T(att["name"], 13, TEXT, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
            ft.Container(ic("edit", 18, "m"), on_click=lambda e, x=att: _rename_attachment(ctx, x), ink=True,
                         border_radius=R_SM, padding=6, tooltip="إعادة تسمية"),
            ft.Container(ic("x", 18, "r"), on_click=lambda e, x=att: _delete_attachment(ctx, x), ink=True,
                         border_radius=R_SM, padding=6, tooltip="حذف المرفق"),
            ic("eye" if is_img else "download", 20, "p")], spacing=6),
            on_click=lambda e, x=att: _open_attachment(ctx, x), ink=True, border_radius=R_SM,
            padding=ft.padding.symmetric(vertical=10, horizontal=6)))
    return [photos, card(ft.Column([sec("المرفقات", "paperclip")] + rows + [T("اضغط على المرفق لفتحه", 11, MUTED)], spacing=12))]


def _event_photo_slot(ctx, ev, which, label, w, h):
    a = ctx.app
    rel = ev[f"photo_{which}"]
    has = bool(rel) and os.path.exists(ap(rel))

    def choose(e=None):
        def picked(paths):
            try:
                C.set_event_photo(ev["id"], which, paths[0])
            except Exception as ex:                       # حدّ الواجهة: نسجّل ونُبلغ
                C.LOG.log_exc("event_photo", ex)
                return a.toast(f"تعذر حفظ الصورة: {ex}", DANGER)
            ctx.reload()
        a.pick(picked)

    def drop(e=None):
        def do():
            try:
                C.clear_event_photo(ev["id"], which)
            except Exception as ex:                       # حدّ الواجهة: نسجّل ونُبلغ
                C.LOG.log_exc("clear_event_photo", ex)
                return a.toast(f"تعذّر الحذف: {ex}", DANGER)
            ctx.reload()
        a.ask_confirm("حذف الصورة", "ستُحذف صورة هذا الموعد نهائياً.", do, "حذف")
    inner = (a.img_ctl(rel, w, h) if has else
             ft.Column([ic("photo_add", 28, "p"), a.T("إضافة صورة", 11, MUTED)], spacing=2,
                       alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER))
    box = ft.Container(inner, width=w, height=h, border_radius=R_CTRL, bgcolor=FIELD_BG, alignment=ft.alignment.center,
                       clip_behavior=ft.ClipBehavior.ANTI_ALIAS, border=ft.border.all(1.2, BORDER if has else BORDER_STRONG),
                       ink=True, on_click=(lambda e: a.s.image_screen(rel, ctx.reload)) if has else choose)
    small = lambda t, col, fn: ft.Container(a.T(t, 12, col, True), on_click=fn, ink=True, border_radius=R_SM,
                                            padding=ft.padding.symmetric(horizontal=6, vertical=2))
    change = ft.Row([small("تغيير", PRIMARY, choose), small("حذف", DANGER, drop)], spacing=0) if has else ft.Container()
    return ft.Column([box, ft.Row([a.T(label, 12, DARK, True), change], width=w,
                                  alignment=ft.MainAxisAlignment.SPACE_BETWEEN)], spacing=4)


def event_photos(ctx, ev):
    """صورتا قبل/بعد للموعد + خيار إدراجهما في الملف المطبوع."""
    a = ctx.app
    w, h = int((a.width() - 32 - 24 - 10) / 2), 112
    ctrls = [ft.Row([_event_photo_slot(ctx, ev, "before", "قبل", w, h), _event_photo_slot(ctx, ev, "after", "بعد", w, h)],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN)]
    if ev["photo_before"] or ev["photo_after"]:
        sw = ft.Switch(value=bool(ev["in_report"]), active_color=PRIMARY,
                       on_change=lambda e, i=ev["id"]: C.set_event_in_report(i, e.control.value))
        ctrls.append(ft.Row([a.T("إدراج قبل/بعد هذا الموعد في الملف المطبوع", 12, TEXT, True, expand=True), sw]))
    return ft.Column(ctrls, spacing=8)
