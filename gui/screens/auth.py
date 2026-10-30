# -*- coding: utf-8 -*-
"""
إنشاء الحساب والدخول واستعادة كلمة المرور والقفل — لا تحتوي أي SQL: كل الوصول للبيانات عبر core.
"""
import os

import flet as ft
import core as C

from theme import (PRIMARY, DARK, DANGER, OK, FIELD_BG, TEXT, MUTED, BORDER, MINT, R_SM, R_FIELD)


def install(app):
    page = app.page
    ui = app.ui
    toast = app.toast
    T = app.T
    card = app.card
    btn = app.btn
    field = app.field
    dlg_w = app.dlg_w
    dialog = app.dialog
    dlg_btn = app.dlg_btn
    auth_shell = app.auth_shell
    pw_field = app.pw_field
    def splash(*a, **k):
        return app.s.splash(*a, **k)
    def home(*a, **k):
        return app.s.home(*a, **k)

    def recovery_key_dialog(rkey, then):
        """يعرض مفتاح الاسترداد مرة واحدة ولا يُغلق قبل تأكيد المستخدم أنه حفظه."""
        saved = ft.Checkbox(label="حفظتُ المفتاح في مكان آمن خارج هذا الهاتف", value=False, active_color=PRIMARY)
        err = T("", 12, DANGER, True)

        def copy_key(e):
            page.set_clipboard(rkey)
            toast("تم نسخ مفتاح الاسترداد")

        def go(e):
            if not saved.value:
                err.value = "أكّد أنك حفظت المفتاح أولاً"
                return err.update()
            page.close(dlg)
            then()
        dlg = dialog("مفتاح الاسترداد", ft.Column([
            T("هذا المفتاح هو طريقتك لاسترجاع بياناتك إن نسيت كلمة المرور، بلا أي وسيط. يُعرض لك مرة واحدة فقط.", 13, TEXT),
            ft.Container(T(rkey, 16, PRIMARY, True, selectable=True, text_align=ft.TextAlign.LEFT), bgcolor=MINT,
                         border_radius=R_FIELD, padding=ft.padding.symmetric(vertical=12, horizontal=14)),
            btn("نسخ المفتاح", "share", copy_key, kind="soft", height=44),
            T("اكتبه على ورقة أو احفظه في مدير كلمات مرور. لا تتركه على هذا الهاتف وحده، ومن يملكه يستطيع فتح بياناتك.",
              12, DANGER, True), saved, err], tight=True, width=dlg_w(), rtl=True, spacing=12),
            [dlg_btn("متابعة", go, "primary")])

    def setup_screen():
        legacy = os.path.exists(C.DB_PATH)
        user = field("اسم المستخدم")
        pw = pw_field("كلمة المرور (عشر خانات على الأقل — الأفضل جملة)")
        pw2 = pw_field("تأكيد كلمة المرور")
        err = T("", 12, DANGER, True, text_align=ft.TextAlign.CENTER)

        def create(e):
            if pw.value != pw2.value:
                err.value = "كلمتا المرور غير متطابقتين"
                return err.update()
            err.value = "جارٍ إنشاء الحساب وتشفير البيانات…" if legacy else ""
            err.color = PRIMARY
            err.update()
            try:
                rkey = C.setup_account(user.value, pw.value)
            except C.VaultError as ex:
                err.value, err.color = str(ex), DANGER
                return err.update()
            except Exception as ex:                          # حدّ الواجهة: نسجّل ونُبلغ
                C.LOG.log_exc("setup_account", ex)
                err.value, err.color = f"تعذّر إنشاء الحساب: {ex}", DANGER
                return err.update()
            toast("تم إنشاء الحساب وتشفير البيانات", OK)
            recovery_key_dialog(rkey, after_login)
        auth_shell("إنشاء حساب المستخدم", "اختر اسم مستخدم وكلمة مرور. ستُطلب في كل مرة تفتح فيها التطبيق.", [
            user, pw, pw2, err,
            btn("إنشاء الحساب", "user_plus", create),
            card(ft.Column([
                T("تنويه:", 13, DANGER, True),
                T("• جميع بيانات المرضى والصور والمرفقات والنسخ الاحتياطية ستُحفظ مشفّرة ولا تُفتح خارج التطبيق.", 12, TEXT),
                T("• إن نسيت كلمة المرور فتسترجعها بمفتاح الاسترداد الذي سيُعرض لك الآن مرة واحدة، وعن طريق مدير البرنامج.", 12, TEXT),
                T("• بعد 5 محاولات خاطئة يُقفل الدخول حتى يصدر المدير الرمز.", 12, TEXT)]
                + ([T("• ستُشفَّر بياناتك الحالية تلقائياً عند إنشاء الحساب.", 12, PRIMARY, True)] if legacy else []),
                spacing=4), padding=16)])

    def fmt_wait(sec):
        if sec < 60:
            return f"{sec} ثانية"
        m = (sec + 59) // 60
        return f"{m} دقيقة" if m < 60 else "ساعة"

    def login_screen(msg=None):
        user = field("اسم المستخدم", value=C.VAULT.user)
        pw = pw_field("كلمة المرور")
        w0 = C.VAULT.wait_seconds
        err = T(msg or (f"محاولات خاطئة كثيرة — حاول بعد {fmt_wait(w0)}، أو استرجع كلمة المرور" if w0 else ""),
                12, DANGER, True, text_align=ft.TextAlign.CENTER)

        def rollback_dialog(ex):
            d = dialog("القاعدة أقدم من آخر حفظ",
                       ft.Column([T("آخر حفظ مسجّل على هذا الجهاز أحدث من ملف البيانات الحالي، أي أن db.enc ربما استُبدل بنسخة قديمة "
                                    "(أو استُرجع جزء من ملفات التطبيق). افتحه فقط إن كنت أنت من فعل ذلك عمداً؛ "
                                    "وإلا فاستعد آخر نسخة احتياطية.", 13, TEXT)],
                                  tight=True, width=dlg_w(), rtl=True, spacing=10),
                       [dlg_btn("فتح القاعدة الحالية رغم ذلك", lambda e2: (page.close(d), enter(accept=True)), "danger"),
                        dlg_btn("إلغاء", lambda e2: page.close(d))])

        def enter(e=None, accept=False):
            w = C.VAULT.wait_seconds
            if w:
                err.value, err.color = f"محاولات خاطئة كثيرة — حاول بعد {fmt_wait(w)}، أو استرجع كلمة المرور", DANGER
                return err.update()
            err.value, err.color = "جارٍ التحقق…", PRIMARY          # الاشتقاق (600 ألف دورة) يستغرق ثانية على الهواتف الضعيفة
            err.update()
            weak = C.VT.password_problem(pw.value or "", user.value or "")
            try:
                r = C.unlock(user.value, pw.value or "", accept)
            except C.RollbackError as ex:
                err.value = ""
                err.update()
                return rollback_dialog(ex)
            except C.VaultError as ex:
                err.value, err.color = str(ex), DANGER
                return err.update()
            if r == "ok":
                if weak:
                    toast("كلمة مرورك أضعف من المعيار الجديد — غيّرها من الإعدادات ← الحساب والأمان", DANGER)
                return after_login()
            pw.value = ""
            err.color = DANGER
            w = C.VAULT.wait_seconds
            err.value = ("اسم المستخدم أو كلمة المرور غير صحيحة — " +
                         (f"حاول بعد {fmt_wait(w)}" if w else f"محاولات قبل بدء التأخير: {C.VAULT.attempts_left}"))
            err.update()
            pw.update()
        pw.on_submit = enter
        auth_shell("تسجيل الدخول", "أدخل بيانات حسابك لفتح الملفات.", [
            user, pw, err, btn("دخول", "lock", enter),
            ft.Container(T("نسيت كلمة المرور؟", 13, PRIMARY, True, text_align=ft.TextAlign.CENTER),
                         on_click=lambda e: reset_screen(), ink=True, border_radius=R_SM, padding=12)])

    def reset_screen():
        """استرداد كلمة المرور: رمز طلب ← المدير ← رمز إعادة ← كلمة مرور جديدة."""
        escrow = C.VAULT.escrow_enabled
        req = C.reset_request_code() if escrow else ""
        dev = C.lic_load()["device_id"].upper()
        reply = field("رمز الإعادة الذي أرسله المدير", multiline=True, min_lines=3, max_lines=6,
                      text_align=ft.TextAlign.LEFT)
        npw = pw_field("كلمة المرور الجديدة")
        npw2 = pw_field("تأكيد كلمة المرور الجديدة")
        err = T("", 12, DANGER, True, text_align=ft.TextAlign.CENTER)

        def copy_req(e):
            page.set_clipboard(req)
            toast("تم نسخ رمز الطلب — أرسله إلى المدير")

        def paste_reply(e):
            try:
                reply.value = (page.get_clipboard() or "").strip()
                reply.update()
            except Exception:
                toast("تعذّر القراءة من الحافظة — الصق الرمز يدوياً", DANGER)

        def apply(e):
            if npw.value != npw2.value:
                err.value = "كلمتا المرور غير متطابقتين"
                return err.update()
            try:
                C.reset_with_code(reply.value, npw.value)
            except C.VaultError as ex:
                err.value = str(ex)
                return err.update()
            except Exception as ex:                          # حدّ الواجهة: نسجّل ونُبلغ
                C.LOG.log_exc("reset_with_code", ex)
                err.value = f"تعذّرت الإعادة: {ex}"
                return err.update()
            toast("تمت إعادة تعيين كلمة المرور. بياناتك كما هي.", OK)
            after_login()
        rk_in = field("مفتاح الاسترداد (XXXXX-XXXXX-…)", text_align=ft.TextAlign.LEFT)
        rk_pw, rk_pw2 = pw_field("كلمة المرور الجديدة"), pw_field("تأكيد كلمة المرور الجديدة")
        rk_err = T("", 12, DANGER, True, text_align=ft.TextAlign.CENTER)

        def apply_rk(e):
            if rk_pw.value != rk_pw2.value:
                rk_err.value = "كلمتا المرور غير متطابقتين"
                return rk_err.update()
            rk_err.value, rk_err.color = "جارٍ التحقق…", PRIMARY
            rk_err.update()
            try:
                C.reset_with_recovery_key(rk_in.value, rk_pw.value)
            except C.VaultError as ex:
                rk_err.value, rk_err.color = str(ex), DANGER
                return rk_err.update()
            except Exception as ex:                          # حدّ الواجهة: نسجّل ونُبلغ
                C.LOG.log_exc("reset_with_recovery_key", ex)
                rk_err.value, rk_err.color = f"تعذّرت الإعادة: {ex}", DANGER
                return rk_err.update()
            toast("تمت إعادة تعيين كلمة المرور. بياناتك كما هي.", OK)
            after_login()
        rk_ctrls = [card(ft.Column([
            T("لديّ مفتاح الاسترداد", 13, DARK, True), rk_in, rk_pw, rk_pw2, rk_err,
            btn("استرجاع بمفتاح الاسترداد", "key", apply_rk)], spacing=12), padding=16)] if C.VAULT.has_recovery_key else []
        head = "استرجاع كلمة المرور"
        admin_ctrls = [
            card(ft.Column([T("الخطوة 1 — أرسل رمز الطلب للمدير", 13, DARK, True),
                            T("معرّف الجهاز: " + dev, 12, MUTED),
                            ft.Container(T(req, 11, TEXT, selectable=True, text_align=ft.TextAlign.LEFT), bgcolor=FIELD_BG,
                                         border_radius=R_SM, padding=12, border=ft.border.all(1, BORDER)),
                            btn("نسخ رمز الطلب", "share", copy_req, kind="soft", height=44)], spacing=8), padding=16),
            card(ft.Column([T("الخطوة 2 — الصق رمز الإعادة واختر كلمة مرور جديدة", 13, DARK, True), reply,
                            btn("لصق من الحافظة", "download", paste_reply, kind="soft", height=44), npw, npw2, err,
                            btn("تأكيد وإعادة التعيين", "key", apply)], spacing=12), padding=16)]
        ctrls = rk_ctrls + (admin_ctrls if escrow else [])
        ctrls.append(ft.Container(T("رجوع لتسجيل الدخول", 13, PRIMARY, True, text_align=ft.TextAlign.CENTER),
                                  on_click=lambda e: login_screen(), ink=True, border_radius=R_SM, padding=12))
        auth_shell(head, "استخدم مفتاح الاسترداد الذي حفظته، أو تواصل مع مدير البرنامج إن كان الاسترداد عبره مفعّلاً. بياناتك تبقى سليمة.", ctrls)

    def lock_now(e=None):
        C.lock_app()
        login_screen()

    def after_login():
        try:                                          # الاسترداد عبر المدير إلزامي: يُفعَّل تلقائياً للحسابات القديمة
            C.ensure_escrow()
        except Exception as ex:                       # حدّ الواجهة: نسجّل ولا نمنع الدخول
            C.LOG.log_exc("ensure_escrow", ex)
        try:                                          # مرة واحدة: تجريد GPS/EXIF من صور الإصدارات السابقة (قبل أخذ النسخة)
            C.scrub_metadata_if_needed()
        except Exception as ex:
            C.LOG.log_exc("scrub_metadata", ex)
        try:
            C.auto_backup_if_due()
            rep = C.backup_report()
            if rep["skipped"] and not ui.get("warned_skip"):
                ui["warned_skip"] = True
                toast(f"تنبيه: آخر نسخة لم تشمل {rep['skipped']} ملف تالف. راجع «النسخ الاحتياطي».", DANGER)
        except Exception as ex:
            C.LOG.log_exc("auto_backup", ex)
            toast(f"تعذّر أخذ النسخة الاحتياطية التلقائية: {ex}", DANGER)
        if ui.get("splashed"):                       # الترحيب مرة واحدة لكل تشغيل، لا بعد كل قفل تلقائي
            return home()
        ui["splashed"] = True
        splash()

    def config_error_screen():
        auth_shell("إعداد غير مكتمل", "لا يمكن تشغيل هذه النسخة: ملف المفاتيح العامة (public_keys.py) غير مضبوط.", [
            card(ft.Column([T("على حاسوب المطوّر: شغّل keygen.py مرة واحدة (يولّد المفاتيح ويطلب عبارة مرور لحمايتها)، "
                              "ثم أعد بناء التطبيق ليتضمّن الملف public_keys.py.", 13, TEXT),
                            T("python keygen.py", 14, PRIMARY, True, selectable=True,
                              text_align=ft.TextAlign.LEFT)], spacing=8),
                 padding=16)])

    def boot_account():
        if not C.keys_ready():
            config_error_screen()
        elif C.need_setup():
            setup_screen()
        else:
            login_screen()

    app.register(recovery_key_dialog=recovery_key_dialog, setup_screen=setup_screen, fmt_wait=fmt_wait, login_screen=login_screen, reset_screen=reset_screen, lock_now=lock_now, after_login=after_login, config_error_screen=config_error_screen, boot_account=boot_account)
