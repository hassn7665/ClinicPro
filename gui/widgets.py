# -*- coding: utf-8 -*-
"""
المكوّنات المشتركة للواجهة (عناصر، حوارات، منتقيات، التنقل) — لا تحتوي أي SQL.
"""
import os
import time
from datetime import datetime

import flet as ft
import core as C

from theme import (PRIMARY, DEEP, DEEP_HV, DARK, DANGER, OK, WHITE, BG, FIELD_BG, TEXT, MUTED, BORDER, MINT, R_SM, R_FIELD, R_CTRL, R_CARD, R_TILE, R_PILL, R_DIALOG, MUTED_TEXT, TRANSPARENT, SOFT, tint, shade)
from core import (APP_NAME, KIND_AR, ap, rel_label)
from gui.digits import DigitText
from gui.common import (dur_text, ic, logo, shadow, LARGE_IMG)


def install(app):
    page = app.page
    ui = app.ui
    picker = app.picker
    def home(*a, **k):
        return app.s.home(*a, **k)
    def settings_screen(*a, **k):
        return app.s.settings_screen(*a, **k)
    def search_screen(*a, **k):
        return app.s.search_screen(*a, **k)
    def patient_screen(*a, **k):
        return app.s.patient_screen(*a, **k)
    def event_details(*a, **k):
        return app.s.event_details(*a, **k)
    def schedule_screen(*a, **k):
        return app.s.schedule_screen(*a, **k)
    def accounts_screen(*a, **k):
        return app.s.accounts_screen(*a, **k)

    def width():
        return max(int(page.width or 360), 300)

    def lazy_tile(rel, w, h, fit):
        """بلاطة تُحمَّل صورتها عند اللمس فقط: تمنع إرسال عشرات الميغابايت دفعة واحدة إلى الواجهة."""
        holder = ft.Container(width=w, height=h, alignment=ft.alignment.center, ink=True)
        holder.content = ft.Column([ic("image", 26, "p"), T("اضغط للتحميل", 10, MUTED)], spacing=2,
                                   alignment=ft.MainAxisAlignment.CENTER,
                                   horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        def load(e):
            try:
                holder.content = ft.Image(src_base64=C.file_b64(rel), width=w, height=h, fit=fit)
                holder.on_click = None                # بعد التحميل يمرّر اللمس للحاوية الخارجية (فتح العارض)
            except Exception as ex:
                C.LOG.log_exc("lazy_image", ex)
                holder.content = ic("image", 28, "m")
            holder.update()
        holder.on_click = load
        return holder

    def img_ctl(rel, w, h, fit=ft.ImageFit.COVER, full=False):
        """صورة مخزّنة مشفّرة: تُفكّ في الذاكرة وتُعرض دون كتابة ملف عادي على القرص.
        full=False (القوائم والبلاطات): المصغّرة إن وُجدت؛ وإلا الأصل مع تحميل كسول للصور الكبيرة.
        full=True (العارض): الأصل المُصغَّر عند الحفظ."""
        try:
            if full:
                return ft.Image(src_base64=C.file_b64(rel), width=w, height=h, fit=fit)
            if not os.path.isfile(ap(C.thumb_rel(rel))) and C.file_size(rel) > LARGE_IMG:
                if ui["img_left"] <= 0:
                    return lazy_tile(rel, w, h, fit)
                ui["img_left"] -= 1
            return ft.Image(src_base64=C.thumb_b64(rel)[0], width=w, height=h, fit=fit)
        except Exception as ex:
            C.LOG.log_exc("img_ctl", ex)
            return ft.Container(ic("image", 28, "m"), width=w, height=h, alignment=ft.alignment.center)

    def toast(msg, color=DARK):
        page.open(ft.SnackBar(DigitText(msg, color=WHITE, rtl=True), bgcolor=color))

    def T(text, size=14, color=TEXT, bold=False, **kw):
        kw.setdefault("rtl", True)
        if color == MUTED:                       # نص ثانوي: لون أغمق لتباين مقروء (WCAG AA)
            color = MUTED_TEXT
        return DigitText(text, size=size, color=color,
                         weight=ft.FontWeight.BOLD if bold else ft.FontWeight.W_500, **kw)

    def card(content, padding=16, on_click=None, bgcolor=WHITE, radius=R_CARD, border=True):
        return ft.Container(content=content, padding=padding, bgcolor=bgcolor, border_radius=radius,
                            border=ft.border.all(1, BORDER) if border else None, shadow=shadow(),
                            on_click=on_click, ink=on_click is not None)

    def tile(name, bg=MINT, color="p", box=44, size=22, radius=14):
        return ft.Container(ic(name, size, color), width=box, height=box, bgcolor=bg,
                            border_radius=radius, alignment=ft.alignment.center)

    def pill(text, bg=PRIMARY, fg=WHITE, size=12, dot=True):
        """شارة ناعمة: إن مُرّر لون ممتلئ مع نص أبيض (الاستدعاء القديم) تتحول تلقائياً إلى خلفية فاتحة ونص أعمق."""
        if fg == WHITE:
            sb, sd, sf = tint(bg, .14), tint(bg, .34), shade(bg, .62)
        else:
            sb, sd, sf = bg, tint(fg, .3), fg
        row = ([ft.Container(width=7, height=7, border_radius=4, bgcolor=sf)] if dot else []) + [T(text, size, sf, True)]
        return ft.Container(ft.Row(row, spacing=6, tight=True), bgcolor=sb, border_radius=R_PILL,
                            border=ft.border.all(1, sd), padding=ft.padding.symmetric(vertical=3, horizontal=11))

    def fx(c, bg, hv, action):
        """تأثير الضغط: يتعمّق اللون ويصغر الزر قليلاً ثم يعود، مع تموّج اللمس. لا يغيّر عمل الزر."""
        c.animate = ft.Animation(130, ft.AnimationCurve.EASE_OUT)
        c.animate_scale = ft.Animation(130, ft.AnimationCurve.EASE_OUT)
        c.ink = True
        c.ink_color = ft.Colors.with_opacity(0.18, DARK)

        def hover(e):
            try:
                c.bgcolor = hv if e.data == "true" else bg
                c.update()
            except (AssertionError, RuntimeError):          # عنصر أُزيل من الصفحة أثناء التمرير: تجميلي فقط
                pass

        def click(e):
            try:
                c.bgcolor, c.scale = hv, 0.95
                c.update()
                time.sleep(0.11)
                c.bgcolor, c.scale = bg, 1
                c.update()
            except (AssertionError, RuntimeError):          # عنصر أُزيل من الصفحة أثناء الحركة: تجميلي فقط
                pass
            if action:
                action(e)
        c.on_hover, c.on_click = hover, click
        return c

    def btn(text, icon=None, on_click=None, kind="primary", expand=False, height=52):
        if kind == "primary":                       # ممتلئ تيل عميق
            bg, bd, fg, hv, ico = DEEP, DEEP, WHITE, DEEP_HV, "w"
        elif kind == "outline":
            bg, bd, fg, hv, ico = WHITE, tint(PRIMARY, .6), DEEP, tint(PRIMARY, .12), "p"
        else:                                        # soft / ok / danger: خلفية فاتحة وإطار رفيع
            tone = {"soft": "p", "ok": "g", "danger": "r"}[kind]
            sb, sd, sf = SOFT[tone]
            bg, bd, fg, hv, ico = sb, sd, sf, tint({"p": PRIMARY, "g": OK, "r": DANGER}[tone], .26), {"p": "p", "g": "g", "r": "r"}[tone]
        row = ([ic(icon, 20, ico)] if icon else []) + [T(text, 14, fg, True)]
        c = ft.Container(ft.Row(row, alignment=ft.MainAxisAlignment.CENTER, spacing=8),
                         height=height, bgcolor=bg, border_radius=R_CTRL, expand=expand,
                         padding=ft.padding.symmetric(horizontal=16), border=ft.border.all(1.2, bd),
                         alignment=ft.alignment.center)
        return fx(c, bg, hv, on_click)

    def icon_btn(name, color="w", on_click=None, size=24, bg=None, tip=None):
        c = ft.Container(ic(name, size, color), padding=12, border_radius=R_CTRL, margin=ft.margin.symmetric(horizontal=2),
                         bgcolor=bg or TRANSPARENT, tooltip=tip)
        hv = ft.Colors.with_opacity(0.2, WHITE) if color == "w" else tint(PRIMARY, .2)
        return fx(c, bg or TRANSPARENT, hv, on_click)

    def sec(title, icon):
        return ft.Row([tile(icon, MINT, "p", 36, 18, 11), T(title, 16, DARK, True)], spacing=12)

    def fchip(text, selected, on_click):
        return ft.Container(T(text, 13, WHITE if selected else DARK, True),
                            bgcolor=PRIMARY if selected else WHITE, border_radius=R_PILL, on_click=on_click,
                            border=ft.border.all(1.2, PRIMARY if selected else BORDER), ink=True,
                            padding=ft.padding.symmetric(vertical=7, horizontal=14))

    def field(label, **kw):
        kw.setdefault("text_align", ft.TextAlign.START)
        latin = kw.pop("latin", kw.get("keyboard_type") in (ft.KeyboardType.NUMBER, ft.KeyboardType.PHONE))
        if latin and DigitText.digit_font:                  # حقول الأرقام/الهاتف/الكود: المكتوب بخط لاتيني دائماً
            kw.setdefault("text_style", ft.TextStyle(font_family=DigitText.digit_font))
        return ft.TextField(
            label=label, rtl=True, text_size=15, filled=True,
            bgcolor=FIELD_BG, fill_color=FIELD_BG, border_radius=R_FIELD, border_color=BORDER,
            focused_border_color=PRIMARY, border_width=1.2, focused_border_width=1.8,
            label_style=ft.TextStyle(color=MUTED, size=14), cursor_color=PRIMARY,
            content_padding=ft.padding.symmetric(vertical=16, horizontal=16), **kw)

    def choice_group(label, options, value=None, on_change=None, chip_w=None, allow_none=True):
        """مجموعة خيارات بديلة عن القوائم المنسدلة: أزرار اختيار واضحة."""
        state = {"v": value}
        row = ft.Row(wrap=True, spacing=8, run_spacing=8)

        def build():
            row.controls = [ft.Container(
                T(o, 14, DEEP if state["v"] == o else DARK, True, text_align=ft.TextAlign.CENTER),
                bgcolor=SOFT["p"][0] if state["v"] == o else FIELD_BG, width=chip_w,
                border=ft.border.all(1.8 if state["v"] == o else 1.2, PRIMARY if state["v"] == o else BORDER), border_radius=R_SM,
                padding=ft.padding.symmetric(vertical=11, horizontal=18), ink=True,
                alignment=ft.alignment.center, on_click=lambda e, o=o: select(o)) for o in options]

        def select(o):
            if state["v"] == o and not allow_none:
                return
            state["v"] = None if state["v"] == o else o
            build()
            row.update()
            if on_change:
                on_change(state["v"])
        build()
        return ft.Column([T(label, 13, MUTED, True), row], spacing=8), (lambda: state["v"])

    def nav_bar(idx):
        """شريط التنقل السفلي: الرئيسية، الحسابات، البحث، الإعدادات (يستدعي الشاشات الموجودة كما هي)."""
        items = [("home", "الرئيسية", lambda: home()), ("calendar", "الجدول", lambda: schedule_screen()),
                 ("wallet", "الحسابات", lambda: accounts_screen()),
                 ("search", "البحث", lambda: search_screen()), ("settings", "الإعدادات", lambda: settings_screen())]
        cells = []
        for i, (icn, lbl, fn) in enumerate(items):
            act = i == idx
            cells.append(ft.Container(
                ft.Column([ft.Container(ic(icn, 24, "p" if act else "m"), bgcolor=MINT if act else None,
                                        border_radius=R_CTRL, padding=ft.padding.symmetric(vertical=5, horizontal=20)),
                           T(lbl, 11, DEEP if act else MUTED, act)], spacing=2, tight=True,
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                expand=True, on_click=(lambda e, fn=fn: fn()), ink=True, border_radius=R_CTRL))
        page.bottom_appbar = ft.BottomAppBar(content=ft.Row(cells, spacing=0, rtl=True), bgcolor=WHITE, height=76,
                                             padding=ft.padding.symmetric(horizontal=8), elevation=12,
                                             shadow_color=ft.Colors.with_opacity(0.3, DARK))

    def show(title, controls, back=None, actions=None, pad=16):
        page.clean()
        page.bottom_appbar = None
        page.bgcolor = BG
        page.appbar = ft.AppBar(
            title=DigitText(title, size=18, weight=ft.FontWeight.BOLD, color=DARK, rtl=True),
            center_title=True, bgcolor=BG, elevation=0, toolbar_height=58, rtl=True,
            leading=icon_btn("arrow_right", "d", lambda e: back(), bg=WHITE, tip="رجوع") if back else None,
            leading_width=56, actions=(actions or []) + [ft.Container(width=6)])
        page.add(ft.Container(
            ft.Column(controls, spacing=16, scroll=ft.ScrollMode.AUTO, rtl=True,
                      horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            padding=pad, expand=True, rtl=True))
        page.update()

    def dlg_w():
        """عرض محتوى الحوار: لا يتجاوز عرض الشاشة (تفادي القصّ على الهواتف الضيقة)."""
        return max(min(width() - 64, 360), 240)

    def dialog(title, content, actions):
        dlg = ft.AlertDialog(modal=True, bgcolor=WHITE, shape=ft.RoundedRectangleBorder(radius=R_DIALOG),
                             title=T(title, 18, DARK, True), content=content, actions=actions, scrollable=True,
                             actions_alignment=ft.MainAxisAlignment.START,
                             inset_padding=ft.padding.symmetric(horizontal=16, vertical=24),
                             content_padding=ft.padding.symmetric(horizontal=20, vertical=8),
                             actions_padding=ft.padding.symmetric(horizontal=16, vertical=12))
        page.open(dlg)
        return dlg

    def dlg_btn(text, on_click, kind="soft"):
        if kind == "primary":
            bg, bd, fg, hv = DEEP, DEEP, WHITE, DEEP_HV
        else:
            tone, base = {"soft": ("p", PRIMARY), "ok": ("g", OK), "danger": ("r", DANGER)}[kind]
            bg, bd, fg = SOFT[tone]
            hv = tint(base, .26)
        c = ft.Container(T(text, 14, fg, True), bgcolor=bg, border_radius=R_SM, border=ft.border.all(1, bd),
                         padding=ft.padding.symmetric(vertical=10, horizontal=20))
        return fx(c, bg, hv, on_click)

    def ask_confirm(title, message, on_yes, yes_text="تأكيد", danger=True, extra=None):
        """حوار تأكيد عام (للحذف والإجراءات الحساسة)."""
        def go(e):
            page.close(d)
            on_yes()
        d = dialog(title, ft.Column([T(message, 14, TEXT)] + (extra or []), tight=True, width=dlg_w(), rtl=True, spacing=12),
                   [dlg_btn(yes_text, go, "danger" if danger else "ok"), dlg_btn("تراجع", lambda e: page.close(d))])
        return d

    def duration_picker(default_min, on_change=None):
        """اختيار مدة الموعد. يعيد (عنصر الواجهة, دالة تعيد الدقائق)."""
        mins = sorted(set(C.DURATIONS) | {int(default_min)})
        inv = {dur_text(m): m for m in mins}
        ui_, get = choice_group("مدة الموعد", list(inv), dur_text(default_min),
                                (lambda v: on_change(inv.get(v, default_min))) if on_change else None, allow_none=False)
        return ui_, (lambda: inv.get(get(), int(default_min)))

    def conflict_text(rows):
        parts = []
        for r in rows[:3]:
            s0, e0 = C.ev_span(r)
            parts.append(f"{r['full_name']} ({C.fmt12(s0.strftime('%H:%M'))} – {C.fmt12(e0.strftime('%H:%M'))})")
        return "⚠ يتعارض مع: " + "، ".join(parts) + (f" و{len(rows) - 3} آخرين" if len(rows) > 3 else "")

    def cur_chips(value=None, on_change=None):
        """اختيار العملة (ل.س / $) بزرّين. يعيد (الواجهة, getter). يتذكر آخر عملة استُخدمت."""
        st = {"v": value if value in C.CURS else ui.get("cur", "SYP")}
        row = ft.Row(spacing=6)

        def build():
            row.controls = [ft.Container(
                T(C.CUR_SYM[c], 14, DEEP if st["v"] == c else DARK, True, text_align=ft.TextAlign.CENTER),
                bgcolor=SOFT["p"][0] if st["v"] == c else FIELD_BG, width=54, height=48, alignment=ft.alignment.center,
                border=ft.border.all(1.8 if st["v"] == c else 1.2, PRIMARY if st["v"] == c else BORDER), border_radius=R_SM, ink=True,
                on_click=lambda e, c=c: select(c)) for c in C.CURS]

        def select(c):
            st["v"] = ui["cur"] = c
            build()
            row.update()
            if on_change:
                on_change(c)
        build()
        return row, (lambda: st["v"])

    def items_editor(initial=None):
        """قائمة إجراءات (اسم + تكلفة + عملة) مع إجمالي حي بالعملتين. يعيد (الواجهة, collect(), total())."""
        rows = []
        box = ft.Column(spacing=12, rtl=True, tight=True)
        total_t = T("", 13, DARK, True)

        def total():
            tot = C.zero()
            for r in rows:
                try:
                    tot[r["cur"]()] += C.parse_money(r["price"].value)
                except ValueError:
                    pass
            return tot

        def refresh(upd=True):
            total_t.value = "إجمالي التكلفة المستحقة: " + C.money_multi(total())
            if upd:
                total_t.update()

        def add_row(name="", price="", cur=None):
            nm = field("الإجراء", value=name, expand=True)
            pr = field("التكلفة", value=price, expand=True, keyboard_type=ft.KeyboardType.NUMBER,
                       on_change=lambda e: refresh())
            chips, get_cur = cur_chips(cur, on_change=lambda c: refresh())
            r = {"name": nm, "price": pr, "cur": get_cur}

            def rm(e):
                rows.remove(r)
                box.controls.remove(r["row"])
                refresh(False)
                total_t.update()
                box.update()
            r["row"] = ft.Container(ft.Column([ft.Row([nm, icon_btn("x", "r", rm, 18)], spacing=4),
                                               ft.Row([pr, chips], spacing=8)], spacing=8),
                                    padding=8, border=ft.border.all(1, BORDER), border_radius=R_FIELD)
            rows.append(r)
            box.controls.append(r["row"])

        def add_clicked(e):
            add_row()
            box.update()

        for it in (initial or []):
            add_row(it["name"], C.money(it["price"]), it["cur"])
        if not rows:
            add_row()
        refresh(False)

        def collect():
            out, ok = [], True
            for r in rows:
                nm, pv = (r["name"].value or "").strip(), (r["price"].value or "").strip()
                if not nm and not pv:
                    continue
                err = None
                try:
                    if not pv:
                        err = "أدخل التكلفة"
                    else:
                        out.append((nm, C.parse_money(pv), r["cur"]()))
                except ValueError:
                    err = "مبلغ غير صحيح"
                r["price"].error_text = err
                r["price"].update()
                ok = ok and err is None
            return out if ok else None
        ui_col = ft.Column([box, btn("إضافة إجراء", "plus", add_clicked, kind="soft", height=42), total_t],
                           spacing=12, rtl=True, tight=True)
        return ui_col, collect, total

    def read_pays(fields_by_cur):
        """يقرأ حقول المدفوع بالعملتين → ([(مبلغ, عملة)], يوجد_خطأ)."""
        pays, bad = [], False
        for c in C.CURS:
            f = fields_by_cur[c]
            pv, f.error_text = (f.value or "").strip(), None
            if pv:
                try:
                    v = C.parse_money(pv)
                    if v > 0:
                        pays.append((v, c))
                except ValueError:
                    f.error_text, bad = "مبلغ غير صحيح", True
            f.update()
        return pays, bad

    def ext(seconds=120):
        """يعلّم أن المستخدم بدأ تدفقاً خارجياً (فتح ملف/متصفح): الخروج المؤقت للتطبيق عندها ليس سبباً للقفل الفوري."""
        ui["ext_until"] = time.time() + seconds

    def open_url(url):
        ext()
        page.launch_url(url)

    def pick(cb, images=True, multiple=False):
        ext()
        def on_res(e):
            if e.files:
                cb([f.path for f in e.files if f.path])
        picker.on_result = on_res
        picker.pick_files(file_type=ft.FilePickerFileType.IMAGE if images else ft.FilePickerFileType.ANY,
                          allow_multiple=multiple)

    def ask_date(cb, initial=None):
        page.open(ft.DatePicker(first_date=datetime(2020, 1, 1), last_date=datetime(2100, 12, 31),
                                value=initial, on_change=lambda e: cb(e.control.value)))

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
            T(f"{KIND_AR[ev['kind']]} • {C.fmt12(ev['time'] or C.DEFAULT_TIME)}", 12, MUTED),
            ft.Container(height=2),
            btn("عرض التفاصيل", None, lambda e, i=ev["id"]: event_details(i), height=40)],
            spacing=6, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
            width=172, padding=16, bgcolor=WHITE, border_radius=R_CARD, shadow=shadow(), alignment=ft.alignment.center)

    def info_row(icon, label, value, last=False, pill_color=None):
        val = (pill(str(value), pill_color) if pill_color and value not in (None, "")
               else T(str(value) if value not in (None, "") else "—", 14, TEXT, True, selectable=True))
        r = ft.Row([tile(icon, MINT, "p", 36, 18, 11),
                    ft.Column([T(label, 12, MUTED), val], spacing=1, expand=True)], spacing=12)
        return ft.Column([r] if last else [r, ft.Divider(height=1, color=BORDER)], spacing=12)

    def fin_box(label, d, color, bg):
        """مربع مبالغ بالعملتين (سطر لكل عملة غير صفرية)."""
        lines = [T(C.money(d[c], c), 14, color, True) for c in C.CURS if d.get(c, 0) != 0] \
            or [T("0", 14, color, True)]
        return ft.Container(ft.Column([T(label, 12, MUTED, True)] + lines, spacing=4),
                            bgcolor=bg, border_radius=R_FIELD, padding=12, expand=True,
                            border=ft.border.all(1, SOFT["p"][1]))

    def rem_pill(due, rem):
        if any(v > 0 for v in rem.values()):
            return pill("متبقٍ " + C.money_multi({c: max(v, 0) for c, v in rem.items()}), DANGER, size=11)
        return pill("مسدّد" if any(due.values()) else "بلا حسابات", OK if any(due.values()) else MUTED, size=11)

    def auth_shell(title, sub, controls):
        """إطار موحّد لشاشات الدخول (بلا شريط علوي ولا تنقل)."""
        page.clean()
        page.appbar = None
        page.bottom_appbar = None
        page.bgcolor = BG
        page.add(ft.Container(ft.Column(
            [ft.Container(height=18), ft.Container(logo(84), alignment=ft.alignment.center),
             T(APP_NAME, 28, DARK, True, text_align=ft.TextAlign.CENTER, rtl=False),
             T(title, 18, TEXT, True, text_align=ft.TextAlign.CENTER),
             T(sub, 13, MUTED, text_align=ft.TextAlign.CENTER)] + controls + [ft.Container(height=24)],
            spacing=12, scroll=ft.ScrollMode.AUTO, horizontal_alignment=ft.CrossAxisAlignment.STRETCH, rtl=True),
            padding=24, expand=True, rtl=True))
        page.update()

    def pw_field(label, **kw):
        return field(label, password=True, can_reveal_password=True, latin=True, **kw)

    def _with_nav(fn, idx):
        def w(*a, **k):
            r = fn(*a, **k)
            nav_bar(idx)
            page.update()
            return r
        return w

    app.export(width=width, lazy_tile=lazy_tile, img_ctl=img_ctl, toast=toast, T=T, card=card, tile=tile, pill=pill, fx=fx, btn=btn, icon_btn=icon_btn, sec=sec, fchip=fchip, field=field, choice_group=choice_group, nav_bar=nav_bar, show=show, dlg_w=dlg_w, dialog=dialog, dlg_btn=dlg_btn, ask_confirm=ask_confirm, duration_picker=duration_picker, conflict_text=conflict_text, cur_chips=cur_chips, items_editor=items_editor, read_pays=read_pays, ext=ext, open_url=open_url, pick=pick, ask_date=ask_date, avatar=avatar, stat_mini=stat_mini, cat_tile=cat_tile, appt_card=appt_card, info_row=info_row, fin_box=fin_box, rem_pill=rem_pill, auth_shell=auth_shell, pw_field=pw_field, with_nav=_with_nav)
