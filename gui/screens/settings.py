# -*- coding: utf-8 -*-
"""
الإعدادات وتشخيص الجهاز والحساب والأمان — لا تحتوي أي SQL: كل الوصول للبيانات عبر core.
"""
from datetime import datetime

import flet as ft
import core as C

from theme import (PRIMARY, DANGER, OK, TEXT, MUTED, MINT, TINT_R, TINT_G, TINT_A, TINT_B)
from core import (APP_NAME, APP_VERSION)
from gui.common import (ic)


def install(app):
    _with_nav = app.with_nav
    page = app.page
    toast = app.toast
    T = app.T
    card = app.card
    tile = app.tile
    btn = app.btn
    sec = app.sec
    show = app.show
    dlg_w = app.dlg_w
    dialog = app.dialog
    dlg_btn = app.dlg_btn
    open_url = app.open_url
    pw_field = app.pw_field
    def license_screen(*a, **k):
        return app.s.license_screen(*a, **k)
    def home(*a, **k):
        return app.s.home(*a, **k)
    def stats_screen(*a, **k):
        return app.s.stats_screen(*a, **k)
    def backup_screen(*a, **k):
        return app.s.backup_screen(*a, **k)
    def recovery_key_dialog(*a, **k):
        return app.s.recovery_key_dialog(*a, **k)
    def lock_now(*a, **k):
        return app.s.lock_now(*a, **k)

    def settings_screen():
        st, days = C.lic_status()
        last = C.jload(C.SET_PATH, {}).get("last_backup")

        def item(icon, bg, col, title, sub, on_click):
            return card(ft.Row([tile(icon, bg, col, 44, 22, 14),
                                ft.Column([T(title, 16, TEXT, True), T(sub, 12, MUTED)], spacing=1, expand=True),
                                ic("chevron_left", 20, "m")], spacing=16), padding=16, on_click=on_click)
        show("الإعدادات", [
            item("lock", TINT_R, "r", "الحساب والأمان", f"المستخدم: {C.VAULT.user} — البيانات مشفّرة",
                 lambda e: security_screen()),
            item("shield_check", TINT_G, "g", "الترخيص",
                 f"فعّال — متبقٍ {days} يوماً" if st == "ok" else "غير فعّال",
                 lambda e: license_screen(back=settings_screen)),
            item("backup", MINT, "p", "النسخ الاحتياطي",
                 f"آخر نسخة: {last[:10]}" if last else "لم تؤخذ نسخة بعد", lambda e: backup_screen()),
            item("chart", TINT_B, "b", "الإحصائيات", "المرضى والعمليات والمراجعات", lambda e: stats_screen()),
            item("pulse", TINT_A, "a", "تشخيص الجهاز", "فحوص ذاتية وتقرير للدعم الفني وتحسين الصور",
                 lambda e: diagnostics_screen()),
            card(ft.Row([tile("info", MINT, "p", 44, 22, 14),
                         ft.Column([T(APP_NAME, 16, TEXT, True, rtl=False), T(f"الإصدار {APP_VERSION}", 12, MUTED)],
                                   spacing=1, expand=True)], spacing=16), padding=16),
        ], back=home)

    def diagnostics_screen():
        st = {"report": ""}
        out = ft.Column(spacing=4, rtl=True)
        status = T("جارٍ الفحص… (بضع ثوانٍ)", 12, PRIMARY, True)
        opt_info = T("", 12, MUTED)

        def run(e=None):
            status.value, status.color = "جارٍ الفحص… (بضع ثوانٍ)", PRIMARY
            status.update()
            try:
                st["report"] = C.diagnostics()
            except Exception as ex:
                C.LOG.log_exc("diagnostics", ex)
                st["report"] = f"تعذّر إنشاء التقرير ({type(ex).__name__})"
            out.controls = [T(ln, 12, DANGER if ln.startswith("✗") else TEXT, selectable=True, text_align=ft.TextAlign.RIGHT)
                            for ln in st["report"].splitlines()]
            n = len(C.images_to_optimize())
            opt_info.value = (f"{n} صورة كبيرة بلا مصغّرة. التحسين يصغّرها ويحذف بيانات EXIF (ومنها الموقع الجغرافي) بعد أخذ نسخة احتياطية."
                              if n else "لا توجد صور تحتاج تحسيناً" + ("" if C.IMG.PIL_OK else " (مكتبة الصور غير متوفرة في هذه النسخة)"))
            opt_btn.disabled = not n
            status.value = ""
            page.update()

        def export(e):
            try:
                open_url(C.share_text(f"clinicpro_diag_{datetime.now():%Y%m%d_%H%M}.txt", st["report"]))
                toast("سيُفتح المتصفح لتنزيل التقرير؛ أرسله للمطوّر")
            except Exception as ex:
                toast(f"تعذّر التصدير: {ex}", DANGER)

        def copy(e):
            page.set_clipboard(st["report"])
            toast("تم نسخ التقرير")

        def do_opt(e):
            def go(e2):
                page.close(d)
                status.value, status.color = "جارٍ التحسين… لا تغلق التطبيق", PRIMARY
                status.update()

                def prog(i, n):
                    status.value = f"جارٍ التحسين… {i}/{n}"
                    status.update()
                try:
                    r = C.optimize_images(prog)
                except Exception as ex:
                    C.LOG.log_exc("optimize", ex)
                    status.value = ""
                    return toast(f"فشل التحسين: {ex}", DANGER)
                toast(f"تم تحسين {r['done']} صورة (وفّر {r['saved'] / 1_048_576:.1f} MB)"
                      + (f" — تعذّر {r['failed']}" if r["failed"] else ""), OK if not r["failed"] else DANGER)
                run()
            d = dialog("تحسين الصور الموجودة",
                       T("سيُؤخذ نسخة احتياطية أولاً، ثم تُصغَّر الصور الكبيرة (أطول ضلع 1600 بكسل) وتُنشأ لها مصغّرات. "
                         "التصغير لا رجعة فيه إلا باستعادة النسخة. تابع؟", 14, TEXT),
                       [dlg_btn("تحسين", go, "ok"), dlg_btn("إلغاء", lambda e2: page.close(d))])
        opt_btn = btn("تحسين الصور الموجودة", "image", do_opt, kind="soft")
        show("تشخيص الجهاز", [
            status, card(out, padding=14),
            btn("تصدير تقرير التشخيص", "share", export), btn("نسخ التقرير", "file", copy, kind="soft"),
            btn("إعادة الفحص", "restore", run, kind="outline"), sec("الصور", "image"), opt_info, opt_btn,
            T("التقرير لا يحوي أسماء مرضى ولا اسم المستخدم، ولا يُرسَل تلقائياً إلى أي مكان.", 12, MUTED),
        ], back=settings_screen)
        run()

    def security_screen():
        def change_pw(e):
            old, new, new2 = pw_field("كلمة المرور الحالية"), pw_field("كلمة المرور الجديدة"), pw_field("تأكيد الجديدة")
            err = T("", 12, DANGER, True)

            def go(e):
                if new.value != new2.value:
                    err.value = "كلمتا المرور غير متطابقتين"
                    return err.update()
                try:
                    C.VAULT.change_password(old.value or "", new.value or "")
                except C.VaultError as ex:
                    err.value = str(ex)
                    return err.update()
                page.close(dlg)
                toast("تم تغيير كلمة المرور", OK)
            dlg = dialog("تغيير كلمة المرور", ft.Column([old, new, new2, err], tight=True, width=dlg_w(), rtl=True, spacing=12),
                         [dlg_btn("حفظ", go, "ok"), dlg_btn("إلغاء", lambda e: page.close(dlg))])
        def new_rk(e):
            def go(e2):
                try:
                    rk = C.create_recovery_key()
                except C.VaultError as ex:
                    page.close(d2)
                    return toast(str(ex), DANGER)
                page.close(d2)
                recovery_key_dialog(rk, security_screen)
            d2 = dialog("مفتاح الاسترداد",
                        T("سيُنشأ مفتاح جديد ويُعرض لك مرة واحدة، وأي مفتاح سابق يتوقف عن العمل فوراً. تابع؟", 14, TEXT),
                        [dlg_btn("إنشاء", go, "ok"), dlg_btn("إلغاء", lambda e2: page.close(d2))])

        show("الحساب والأمان", [
            card(ft.Row([tile("shield_check", TINT_G, "g", 44, 22, 14),
                         ft.Column([T(C.VAULT.user, 16, TEXT, True),
                                    T("البيانات والصور والمرفقات والنسخ مشفّرة", 12, OK, True)], spacing=1, expand=True)],
                        spacing=16), padding=16),
            btn("تغيير كلمة المرور", "key", change_pw, kind="soft"),
            btn("تجديد مفتاح الاسترداد" if C.VAULT.has_recovery_key else "إنشاء مفتاح الاسترداد", "key", new_rk, kind="soft"),
            btn("قفل التطبيق الآن", "lock", lock_now, kind="outline"),
            T("بعد 5 محاولات دخول خاطئة يلزم رمز إعادة تعيين من مدير البرنامج.", 12, MUTED),
        ], back=settings_screen)

    settings_screen = _with_nav(settings_screen, 4)
    app.register(settings_screen=settings_screen, diagnostics_screen=diagnostics_screen, security_screen=security_screen)
