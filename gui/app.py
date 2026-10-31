# -*- coding: utf-8 -*-
"""
gui/app.py — تجميع الواجهة: إعداد الصفحة والثيم، حالة الجلسة المشتركة، تركيب المكوّنات والشاشات، ثم الإقلاع.

بنية الواجهة:
  gui/common.py   ثوابت ودوال بسيطة          gui/widgets.py   مكوّنات مشتركة (عناصر/حوارات/تنقل)
  gui/screens/*.py  شاشة (أو شاشات متقاربة) لكل وحدة؛ تتصل ببعضها عبر app.s (سجل الشاشات)
  قاعدة: لا SQL ولا sqlite في أي ملف داخل gui/ — الوصول للبيانات عبر دوال core.py فقط.
"""
import os
import time
from types import SimpleNamespace

import flet as ft

import core as C
from theme import (PRIMARY, DARK, ACCENT, DANGER, OK, BLUE, WHITE, BG, MUTED, TEXT,
                   BORDER, BORDER_STRONG, MINT, R_DIALOG)
from core import APP_NAME, APP_VERSION
from gui.common import _HERE, _MOBILE, find_app_font, find_latin_font
from gui.digits import DigitText
from gui import widgets
from gui.screens import (viewer, startup, home, settings, stats, backup, patient_form, search, patient,
                         schedule, accounts, auth, event_details)

SCREEN_MODULES = (viewer, startup, home, settings, stats, backup, patient_form, search, patient, schedule,
                  accounts, auth, event_details)


class App:
    """حاوية الحالة المشتركة: الصفحة، قاموس حالة الجلسة ui، المكوّنات المصدَّرة (app.T ...) وسجل الشاشات app.s."""

    def __init__(self, page):
        self.page = page
        self.s = SimpleNamespace()          # الشاشات: app.s.home() ...
        self.ui = {"win": 1, "img_left": 6}
        self.away = {"t": None, "ext": False}
        self.picker = None

    def export(self, **kw):
        """تسجيل المكوّنات المشتركة (app.T, app.btn ...) لتستعملها الشاشات."""
        for k, v in kw.items():
            setattr(self, k, v)

    def register(self, **screens):
        """تسجيل شاشات وحدة ما في السجل app.s لتستدعيها بقية الوحدات بالاسم (ربط متأخر)."""
        vars(self.s).update(screens)


def configure(app):
    page = app.page

    page.title = APP_NAME
    page.bgcolor = BG
    page.padding = 0
    page.spacing = 0
    page.theme_mode = ft.ThemeMode.LIGHT
    page.theme = ft.Theme(
        use_material3=True,
        color_scheme=ft.ColorScheme(
            primary=PRIMARY, on_primary=WHITE, primary_container=MINT, on_primary_container=DARK,
            secondary=ACCENT, on_secondary=WHITE, tertiary=BLUE, error=DANGER, on_error=WHITE,
            surface=WHITE, on_surface=TEXT, on_surface_variant=MUTED, outline=BORDER_STRONG,
            outline_variant=BORDER, surface_tint=PRIMARY),
        appbar_theme=ft.AppBarTheme(bgcolor=BG, foreground_color=DARK, elevation=0),
        snackbar_theme=ft.SnackBarTheme(bgcolor=DARK, content_text_style=ft.TextStyle(color=WHITE)),
        dialog_theme=ft.DialogTheme(bgcolor=WHITE, shape=ft.RoundedRectangleBorder(radius=R_DIALOG)))
    page.rtl = True                                   # اتجاه كامل من اليمين لليسار
    try:
        page.locale_configuration = ft.LocaleConfiguration(
            supported_locales=[ft.Locale("ar", "AE")], current_locale=ft.Locale("ar", "AE"))
    except (AttributeError, TypeError):               # إصدار Flet بلا هذه الخاصية
        pass
    font = find_app_font()                            # GE Dinar One Medium إن وُجد ملفه، وإلا Cairo
    DigitText.digit_font = None
    if font:
        page.fonts = {font[0]: font[1]}
        page.theme.font_family = font[0]
        if font[0] == "GEDinarOne":                   # خط يرسم الأرقام هندية: الأرقام بخط لاتيني (Cairo إن وُجد وإلا Roboto)
            latin = find_latin_font()
            if latin:
                page.fonts[latin[0]] = latin[1]
            DigitText.digit_font = latin[0] if latin else "Roboto"

    try:
        C.LOG.install_hooks()                         # استثناءات غير معالجة → السجل المحلي (بلا رسائل ولا بيانات)
        page.on_error = lambda e: C.LOG.log_text("flet_error", getattr(e, "data", ""))
    except (AttributeError, TypeError) as ex:
        C.LOG.log_exc("install_hooks", ex)
    picker = ft.FilePicker()
    page.overlay.append(picker)
    # لا قفل تلقائي عند الذهاب للخلفية (قرار المنتج): القفل يدوي من زر القفل في الشاشة الرئيسية.
    away = {"t": None, "ext": False}      # يبقى للتوافق مع وحدات تستعمله
    ui = {"win": 1, "img_left": 6}                    # فلتر المواعيد المحفوظ + ميزانية الصور الكبيرة في الشاشة الواحدة

    app.picker, app.away, app.ui = picker, away, ui


def warm_fonts(app, wait=0.5):
    """يمنع «وميض الخط»: Flutter يحمّل خطوط التطبيق (page.fonts) بشكل غير متزامن، فتظهر أول شاشة بخط النظام ثم تتبدّل.
    نعرض صفحة فارغة بلون الخلفية (مطابقة لشاشة البدء الأصلية) فيها نص شبه شفاف بكل عائلة خط ليبدأ تحميلها،
    وننتظر قليلاً قبل رسم أي واجهة حقيقية."""
    page = app.page
    fams = list(dict.fromkeys((page.fonts or {}).keys()))
    if not fams:
        return
    try:
        page.bgcolor = BG
        page.add(ft.Container(ft.Stack([ft.Text("أبجد هوز 0123456789", size=4, opacity=0.01, font_family=f) for f in fams]),
                              expand=True, bgcolor=BG))
        page.update()
        time.sleep(wait)
        page.clean()
    except (AttributeError, TypeError, RuntimeError) as ex:          # تحسين شكلي: فشله لا يمنع التشغيل
        C.LOG.log_exc("warm_fonts", ex)


def boot(app):
    page, toast, auth_shell = app.page, app.toast, app.auth_shell
    license_screen, boot_account, config_error_screen = (
        app.s.license_screen, app.s.boot_account, app.s.config_error_screen)

    mism = C.module_mismatch()
    if mism:
        return auth_shell("ملفات غير متطابقة", "هذه الملفات من إصدار مختلف عن بقية التطبيق: " + "، ".join(mism) +
                          f". انسخ **كل** ملفات الحزمة (الإصدار {APP_VERSION}) معاً فوق المجلد، ثم أعد التشغيل.", [])
    if _MOBILE and os.path.exists(os.path.join(_HERE, "admin_keys.json")):
        return auth_shell("حزمة غير آمنة", "هذه النسخة تحوي المفاتيح الخاصة للمدير (admin_keys.json). لا توزّعها؛ "
                          "أعد البناء من مجلد لا يحويها.", [])
    dev_note = None
    if not C.keys_ready() and page.platform in (ft.PagePlatform.WINDOWS, ft.PagePlatform.MACOS, ft.PagePlatform.LINUX):
        # حاسوب المطوّر فقط (حيث توجد keygen.py): إصلاح public_keys.py من مفتاح المدير الموجود.
        try:
            import keygen
            if os.path.exists(keygen.KEYS):          # إصلاح public_keys.py فقط؛ توليد مفاتيح جديدة يتطلب عبارة مرور (python keygen.py)
                keygen.ensure_keys()
        except (Exception, SystemExit):
            pass
    st, _ = C.lic_status()
    if not C.keys_ready():
        config_error_screen()
    elif st == "ok":
        boot_account()
    else:
        license_screen(first=True)
    if dev_note:
        toast(dev_note, OK)


def main(page: ft.Page):
    app = App(page)
    configure(app)
    warm_fonts(app)
    widgets.install(app)
    for m in SCREEN_MODULES:
        m.install(app)
    return boot(app)
