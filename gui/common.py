# -*- coding: utf-8 -*-
"""
gui/common.py — ثوابت ودوال بسيطة مشتركة بين كل شاشات الواجهة (لا حالة ولا SQL).
"""
import os
import sys

import flet as ft

import core as C
from theme import (PRIMARY, DANGER, OK, MUTED, WHITE, SHADOW, ICON_COLORS)

# جذر المشروع (مجلد main.py و assets)
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MOBILE = os.getenv("FLET_PLATFORM", "").lower() in ("android", "ios") or sys.platform in ("android", "ios")
if not _MOBILE and os.path.exists(os.path.join(_HERE, "make_icons.py")) \
        and not os.path.exists(os.path.join(_HERE, "assets", "icons", "coins_p.svg")):
    try:
        import make_icons
        make_icons.main()
    except (ImportError, OSError) as ex:               # الأيقونات تُولَّد على حاسوب المطوّر فقط؛ الفشل غير حرج
        C.LOG.log_exc("make_icons", ex)

# رابط نموذج Google Form للملاحظات والمقترحات: ضع رابطك هنا بين علامتي الاقتباس (يبدأ بـ https://).
# إن بقي فارغاً يُبلّغ المستخدم بأن النموذج غير مضبوط بدل أن يفتح شيئاً.
FEEDBACK_URL = "https://forms.gle/rooWuXaM5ErHa7dR8"

# ───────────────────────── الهوية البصرية ─────────────────────────
COL = dict(ICON_COLORS)

BLOODS = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
AR_DAYS = ["الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد"]      # datetime.weekday(): 0 = الاثنين
AR_MONTHS = ["كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران", "تموز", "آب", "أيلول", "تشرين الأول",
             "تشرين الثاني", "كانون الأول"]                                             # أسماء الأشهر المتداولة في سوريا
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


FONT_DIR = os.path.join(_HERE, "assets", "fonts")


def find_app_font():
    """خط التطبيق: GE Dinar One Medium إن وُضع ملفه في assets/fonts (أي ملف ttf/otf اسمه يحوي «dinar»)، وإلا Cairo، وإلا خط النظام.
    يعيد (اسم العائلة, مسار الملف نسبةً لـassets) أو None."""
    try:
        files = sorted(os.listdir(FONT_DIR))
    except OSError:
        return None
    for fam, test in (("GEDinarOne", lambda n: "dinar" in n.lower()), ("Cairo", lambda n: n.lower() == "cairo.ttf")):
        for n in files:
            if n.lower().endswith((".ttf", ".otf")) and test(n):
                return fam, f"fonts/{n}"
    return None


def find_latin_font():
    """خط الأرقام اللاتينية: Cairo إن وُجد في assets/fonts، وإلا None (فيُستعمل Roboto من النظام)."""
    path = os.path.join(FONT_DIR, "Cairo.ttf")
    return ("Cairo", "fonts/Cairo.ttf") if os.path.isfile(path) else None


LARGE_IMG = 400_000          # صورة أكبر من هذا ولا مصغّرة لها (صور قديمة) تُحمَّل كسولاً بعد استنفاد ميزانية الشاشة

# حالات الموعد في الجدول: (النص, اللون)
STATUS_UI = {"done": ("منجز", OK), "pending": ("معلّق", PRIMARY), "late": ("متأخر", DANGER),
             "no_show": ("لم يحضر", DANGER), "cancelled": ("ملغى", MUTED)}
