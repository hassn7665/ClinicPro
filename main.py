# -*- coding: utf-8 -*-
"""
Clinic Pro — نقطة الدخول.
تطبيق إدارة العيادة (يعمل بدون إنترنت) — Python + Flet، الواجهة RTL كاملة.

البنية:
  main.py        هذا الملف: يهيّئ الصفحة والسياق المشترك App، يسجّل الوحدات، يربط دورة حياة التطبيق (القفل عند الخلفية)، ويُقلع.
  ui_kit.py      الثوابت والأيقونات وسياق App وأدوات الواجهة المشتركة.
  screens/       الشاشات: auth (دخول/إعداد/استرداد/ترخيص) • home • patients • schedule • accounts • settings.
  core.py        كل المنطق والبيانات (SQL والملفات المشفّرة والمالية)؛ الواجهة لا تكتب SQL أبداً (يفرض ذلك tests/test_architecture.py).
  migrations.py  مخطط القاعدة وترقياتها (PRAGMA user_version).
"""
import os
import time

import flet as ft

import core as C
import ui_kit
from core import APP_NAME, APP_VERSION
from screens import accounts, auth, home, patients, schedule, settings
from theme import (ACCENT, BG, BLUE, BORDER, BORDER_STRONG, DANGER, DARK, MINT, MUTED, OK, PRIMARY, R_DIALOG, TEXT, WHITE)
from ui_kit import App, AUTO_LOCK_SECONDS, _HERE, _MOBILE


def main(page: ft.Page):
    app = App(page)
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
            supported_locales=[ft.Locale("ar", "SA")], current_locale=ft.Locale("ar", "SA"))
    except Exception:
        pass
    if os.path.exists(os.path.join(_HERE, "assets", "fonts", "Cairo.ttf")):
        page.fonts = {"Cairo": "fonts/Cairo.ttf"}
        page.theme.font_family = "Cairo"
    try:
        C.LOG.install_hooks()                         # استثناءات غير معالجة → السجل المحلي (بلا رسائل ولا بيانات)
        page.on_error = lambda e: C.LOG.log_text("flet_error", getattr(e, "data", ""))
    except Exception:
        pass

    # ── الحالة المشتركة ثم تسجيل الوحدات (ui_kit أولاً: الشاشات تفكّ أدواتها منه عند تسجيلها) ──
    app.ui = ui = {"win": 1, "img_left": 6}           # فلتر المواعيد المحفوظ + ميزانية الصور الكبيرة في الشاشة الواحدة
    app.picker = ft.FilePicker()
    page.overlay.append(app.picker)
    ui_kit.register(app)
    for module in (auth, home, patients, schedule, accounts, settings):
        module.register(app)

    # ── القفل عند الذهاب للخلفية ──
    away = {"t": None, "ext": False}

    def on_lifecycle(e):
        """يقفل التطبيق عند الذهاب للخلفية حسب السياسة (الافتراضي: فوراً)، مع استثناء التدفقات الخارجية التي
        يبدأها المستخدم نفسه (اختيار ملف/صورة، الطباعة، التصدير) فهي تُقفل فقط إن طال الغياب."""
        st_ = str(getattr(e, "data", "")).lower()
        if any(k in st_ for k in ("paused", "hidden", "detached")):
            if away["t"] is None:
                away["t"], away["ext"] = time.time(), time.time() < ui.get("ext_until", 0)
            if C.VAULT.unlocked and C.lock_policy() == 0 and not away["ext"]:
                try:
                    app.lock_now()
                except Exception as ex:
                    C.LOG.log_exc("bg_lock", ex)
        elif "resumed" in st_:
            t0, ext_ = away["t"], away["ext"]
            away["t"], away["ext"] = None, False
            limit = max(C.lock_policy(), AUTO_LOCK_SECONDS) if ext_ else C.lock_policy()
            if t0 and C.VAULT.unlocked and time.time() - t0 > limit:
                app.lock_now()
    try:
        page.on_app_lifecycle_state_change = on_lifecycle
    except Exception:
        pass

    # ── شريط التنقل: الشاشات الرئيسية الأربع تُغلَّف بحيث يظهر الشريط بعد رسمها أينما استُدعيت ──
    def _with_nav(fn, idx):
        def w(*a, **k):
            r = fn(*a, **k)
            app.nav_bar(idx)
            page.update()
            return r
        return w
    app.schedule_screen = _with_nav(app.schedule_screen, 1)
    app.accounts_screen = _with_nav(app.accounts_screen, 2)
    app.search_screen = _with_nav(app.search_screen, 3)
    app.settings_screen = _with_nav(app.settings_screen, 4)

    # ───── الإقلاع ─────
    mism = C.module_mismatch()
    if mism:
        return app.auth_shell("ملفات غير متطابقة", "هذه الملفات من إصدار مختلف عن بقية التطبيق: " + "، ".join(mism) +
                              f". انسخ **كل** ملفات الحزمة (الإصدار {APP_VERSION}) معاً فوق المجلد، ثم أعد التشغيل.", [])
    if _MOBILE and os.path.exists(os.path.join(_HERE, "admin_keys.json")):
        return app.auth_shell("حزمة غير آمنة", "هذه النسخة تحوي المفاتيح الخاصة للمدير (admin_keys.json). لا توزّعها؛ "
                              "أعد البناء من مجلد لا يحويها.", [])
    dev_note = None
    if not C.keys_ready() and page.platform in (ft.PagePlatform.WINDOWS, ft.PagePlatform.MACOS, ft.PagePlatform.LINUX):
        # حاسوب المطوّر فقط (حيث توجد keygen.py): توليد المفاتيح تلقائياً أول مرة — لا خطوة يدوية.
        try:
            import keygen
            if keygen.ensure_keys() == "created":
                dev_note = "تم إنشاء مفاتيح المدير تلقائياً (admin_keys.json) — احتفظ بنسخة احتياطية منه"
        except (Exception, SystemExit):
            pass
    st, _ = C.lic_status()
    if not C.keys_ready():
        app.config_error_screen()
    elif st == "ok":
        app.boot_account()
    else:
        app.license_screen(first=True)
    if dev_note:
        app.toast(dev_note, OK)


if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
