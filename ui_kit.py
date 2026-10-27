# -*- coding: utf-8 -*-
"""
ui_kit.py — أدوات الواجهة المشتركة لتطبيق Clinic Pro: الثوابت والأيقونات و«سياق التطبيق» App،
وregister(app) الذي يبني العناصر المشتركة (بطاقات، أزرار، حقول، حوارات، منتقيات، محرّر الإجراءات، شريط التنقل).
الشاشات في screens/*.py وتستعمل هذه الأدوات عبر app.
"""
import os
import sys
import time
from datetime import datetime

import flet as ft

import core as C
from theme import (PRIMARY, DEEP, DEEP_HV, DARK, DANGER, OK, WHITE, BG, FIELD_BG, TEXT, MUTED, BORDER, MINT, R_SM,
                   R_FIELD, R_CTRL, R_CARD, R_PILL, R_DIALOG, MUTED_TEXT, TRANSPARENT, SHADOW, ICON_COLORS, SOFT,
                   tint, shade)

# ───────── توليد الأيقونات تلقائياً عند التشغيل على الحاسوب إن لم تكن موجودة ─────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_MOBILE = os.getenv("FLET_PLATFORM", "").lower() in ("android", "ios") or sys.platform in ("android", "ios")
if not _MOBILE and os.path.exists(os.path.join(_HERE, "make_icons.py")) \
        and not os.path.exists(os.path.join(_HERE, "assets", "icons", "coins_p.svg")):
    try:
        import make_icons
        make_icons.main()
    except Exception:
        pass

AUTO_LOCK_SECONDS = 180          # حدّ القفل بعد تدفق خارجي (كاميرا/ملفات/متصفح) إن كانت السياسة أقصر

# ───────────────────────── الهوية البصرية ─────────────────────────
COL = dict(ICON_COLORS)

BLOODS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]      # datetime.weekday(): 0 = الاثنين
AR_DAYS_SHORT = ["إثنين", "ثلاثاء", "أربعاء", "خميس", "جمعة", "سبت", "أحد"]               # مختصرات غير ملتبسة لشريط الأسبوع
DUR_NAMES = {15: "15 د", 30: "30 د", 45: "45 د", 60: "ساعة", 90: "ساعة ونصف", 120: "ساعتان", 180: "3 ساعات"}


def dur_text(m):
    return DUR_NAMES.get(int(m), f"{int(m)} د")


def ev_dur(ev):
    return ev["duration_min"] or C.DEFAULT_DURATION.get(ev["kind"], 30)
WINDOWS = [("24 ساعة", 1), ("يومان", 2), ("3 أيام", 3), ("أسبوع", 7), ("شهر", 30)]
RANGES = [("اليوم", 0), ("7 أيام", 7), ("30 يوماً", 30), ("90 يوماً", 90), ("سنة", 365),
          ("الكل", None), ("مخصص", "custom")]
FALLBACK = {"user_plus": ft.Icons.PERSON_ADD, "search": ft.Icons.SEARCH, "settings": ft.Icons.SETTINGS,
            "arrow_right": ft.Icons.ARROW_FORWARD, "chevron_left": ft.Icons.CHEVRON_LEFT,
            "calendar": ft.Icons.CALENDAR_MONTH, "printer": ft.Icons.PRINT, "edit": ft.Icons.EDIT,
            "check": ft.Icons.CHECK, "x": ft.Icons.CLOSE, "chart": ft.Icons.BAR_CHART,
            "wallet": ft.Icons.ACCOUNT_BALANCE_WALLET, "receipt": ft.Icons.RECEIPT_LONG, "coins": ft.Icons.PAYMENTS,
            "download": ft.Icons.DOWNLOAD, "eye": ft.Icons.VISIBILITY, "plus": ft.Icons.ADD,
            "home": ft.Icons.HOME, "users": ft.Icons.PEOPLE, "filter": ft.Icons.TUNE, "bell": ft.Icons.NOTIFICATIONS}
PAY_LBL = {"SYP": "المدفوع بالليرة السورية (ل.س)", "USD": "المدفوع بالدولار ($)"}
IMG_EXT = (".jpg", ".jpeg", ".png", ".webp", ".gif")
FRANGES = [("اليوم", "today"), ("آخر 7 أيام", "week"), ("هذا الشهر", "month"), ("الكل", "all"), ("نطاق محدد", "custom")]


def ic(name, size=22, color="p"):
    """أيقونة SVG من assets/icons (مع بديل مدمج إن تعذّر تحميلها)."""
    return ft.Image(src=f"/icons/{name}_{color}.svg", width=size, height=size, fit=ft.ImageFit.CONTAIN,
                    error_content=ft.Icon(FALLBACK.get(name, ft.Icons.CIRCLE), size=size, color=COL[color]))


def logo(size=64, light=False):
    return ft.Image(src=f"/icons/logo{'_light' if light else ''}.svg", width=size, height=size,
                    fit=ft.ImageFit.CONTAIN,
                    error_content=ft.Icon(ft.Icons.LOCAL_HOSPITAL, size=size, color=WHITE if not light else PRIMARY))


def shadow(op=0.07):
    return ft.BoxShadow(blur_radius=18, spread_radius=0, color=ft.Colors.with_opacity(op, SHADOW),
                        offset=ft.Offset(0, 4))


class App:
    """السياق المشترك: الصفحة (page) وحالة الواجهة (ui) ومنتقي الملفات (picker)، وكل أداة/شاشة تسجّلها الوحدات
    بـ register(app) فيستدعيها غيرها بـ app.<name> دون استيراد متبادل."""

    def __init__(self, page):
        self.page = page
        self.ui = {}
        self.picker = None


def register(app):
    page, picker, ui = app.page, app.picker, app.ui


    # ═════════════════════ مكوّنات الواجهة ═════════════════════
    def width():
        return max(int(page.width or 360), 300)

    LARGE_IMG = 400_000          # صورة أكبر من هذا ولا مصغّرة لها (صور قديمة) تُحمَّل كسولاً بعد استنفاد ميزانية الشاشة


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
            if not C.thumb_exists(rel) and C.file_size(rel) > LARGE_IMG:
                if ui["img_left"] <= 0:
                    return lazy_tile(rel, w, h, fit)
                ui["img_left"] -= 1
            return ft.Image(src_base64=C.thumb_b64(rel)[0], width=w, height=h, fit=fit)
        except Exception as ex:
            C.LOG.log_exc("img_ctl", ex)
            return ft.Container(ic("image", 28, "m"), width=w, height=h, alignment=ft.alignment.center)


    def toast(msg, color=DARK):
        page.open(ft.SnackBar(ft.Text(msg, color=WHITE, rtl=True), bgcolor=color))


    def T(text, size=14, color=TEXT, bold=False, **kw):
        kw.setdefault("rtl", True)
        if color == MUTED:                       # نص ثانوي: لون أغمق لتباين مقروء (WCAG AA)
            color = MUTED_TEXT
        return ft.Text(text, size=size, color=color,
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
            except Exception:
                pass

        def click(e):
            try:
                c.bgcolor, c.scale = hv, 0.95
                c.update()
                time.sleep(0.11)
                c.bgcolor, c.scale = bg, 1
                c.update()
            except Exception:
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
        items = [("home", "الرئيسية", lambda: app.home()), ("calendar", "الجدول", lambda: app.schedule_screen()),
                 ("wallet", "الحسابات", lambda: app.accounts_screen()),
                 ("search", "البحث", lambda: app.search_screen()), ("settings", "الإعدادات", lambda: app.settings_screen())]
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
            title=ft.Text(title, size=18, weight=ft.FontWeight.BOLD, color=DARK, rtl=True),
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
            parts.append(f"{r['full_name']} ({s0:%H:%M}–{e0:%H:%M})")
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


    def ask_datetime(cb, initial=None):
        """تاريخ ثم وقت."""
        def got_date(d):
            def got_time(e):
                t = e.control.value
                cb(d.date() if hasattr(d, "date") else d, f"{t.hour:02d}:{t.minute:02d}")
            page.open(ft.TimePicker(value=(initial or datetime.now().replace(hour=9, minute=0)).time(),
                                    on_change=got_time, help_text="اختر وقت الموعد",
                                    confirm_text="تأكيد", cancel_text="إلغاء"))
        ask_date(got_date, initial)

    # ── تسجيل الأدوات ليستعملها غيرها عبر app ──
    app.width = width
    app.LARGE_IMG = LARGE_IMG
    app.lazy_tile = lazy_tile
    app.img_ctl = img_ctl
    app.toast = toast
    app.T = T
    app.card = card
    app.tile = tile
    app.pill = pill
    app.fx = fx
    app.btn = btn
    app.icon_btn = icon_btn
    app.sec = sec
    app.fchip = fchip
    app.field = field
    app.choice_group = choice_group
    app.nav_bar = nav_bar
    app.show = show
    app.dlg_w = dlg_w
    app.dialog = dialog
    app.dlg_btn = dlg_btn
    app.ask_confirm = ask_confirm
    app.duration_picker = duration_picker
    app.conflict_text = conflict_text
    app.cur_chips = cur_chips
    app.items_editor = items_editor
    app.read_pays = read_pays
    app.ext = ext
    app.open_url = open_url
    app.pick = pick
    app.ask_date = ask_date
    app.ask_datetime = ask_datetime
