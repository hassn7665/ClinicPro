# -*- coding: utf-8 -*-
"""الدخول والإعداد الأول والاسترداد والترخيص وشاشة الترحيب."""
import time

import flet as ft
import core as C
from theme import (BG, BORDER, DANGER, DARK, FIELD_BG, MINT, MUTED, OK, PRIMARY, R_FIELD, R_SM, SURFACE_TINT, TEXT, WHITE, tint)
from core import (APP_NAME)
from ui_kit import (logo)


def register(app):
    page, ui = app.page, app.ui
    T, btn, card, dialog, dlg_btn, dlg_w, field, icon_btn, show, tile, toast = app.T, app.btn, app.card, app.dialog, app.dlg_btn, app.dlg_w, app.field, app.icon_btn, app.show, app.tile, app.toast


    # ═════════════════════ التفعيل ═════════════════════
    def license_screen(first=False, back=None):
        d = C.lic_load()
        st, days = C.lic_status()
        code = field("كود التفعيل (الصقه كما وصلك)", hint_text="XXXXX-XXXXX-XXXXX-…", text_align=ft.TextAlign.LEFT,
                     multiline=True, min_lines=3, max_lines=6, capitalization=ft.TextCapitalization.CHARACTERS)
        title, sub, colr, icn = {
            "none": ("التطبيق غير مفعّل", "أرسل معرّف الجهاز إلى المطوّر لتحصل على كود التفعيل.", DANGER, "lock"),
            "expired": ("انتهت مدة الترخيص", "أرسل معرّف الجهاز للحصول على كود تجديد. بياناتك محفوظة.", DANGER, "lock"),
            "clock": ("تاريخ الجهاز غير صحيح",
                      f"تاريخ الجهاز أقدم من آخر استخدام مسجّل ({d['last_seen'][:10]}). صحّح التاريخ والوقت، أو أرسل "
                      "معرّف الجهاز للمطوّر ليصدر لك «كود فك قفل التاريخ».", DANGER, "alert"),
            "tampered": ("تعذّر التحقق من ملف الترخيص", "ملف الترخيص تالف أو معدَّل. أرسل معرّف الجهاز للمطوّر للحصول على كود تفعيل جديد.",
                         DANGER, "alert"),
            "ok": ("الترخيص فعّال", f"متبقٍ {days} يوماً. يمكنك التجديد مبكراً وستُضاف المدة إلى المتبقي.", OK, "shield_check"),
        }[st]

        def activate(e):
            ok, m = C.lic_activate(code.value)
            toast(m, OK if ok else DANGER)
            if ok:
                boot_account() if first else (back or app.home)()

        def paste_code(e):
            try:
                code.value = (page.get_clipboard() or "").strip()
                code.update()
            except Exception:
                toast("تعذّر القراءة من الحافظة — الصق الكود يدوياً داخل الحقل", DANGER)

        def copy_id(e):
            page.set_clipboard(d["device_id"])
            toast("تم نسخ معرّف الجهاز")

        ctrls = [
            card(ft.Column([
                tile(icn, ft.Colors.with_opacity(0.12, colr), {"r": "r", "g": "g"}[("r" if colr == DANGER else "g")], 64, 32, 20),
                T(title, 20, DARK, True, text_align=ft.TextAlign.CENTER),
                T(sub, 13, MUTED, text_align=ft.TextAlign.CENTER)],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8)),
            card(ft.Row([ft.Column([T("معرّف الجهاز", 12, MUTED),
                                    T(d["device_id"].upper(), 28, PRIMARY, True, selectable=True)], spacing=0),
                         icon_btn("share", "p", copy_id)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)),
        ]
        if d["expires"]:
            ctrls.append(card(ft.Row([tile("calendar", MINT, "p", 44, 22, 14),
                                      ft.Column([T("ينتهي الترخيص في", 12, MUTED),
                                                 T(d["expires"][:10], 16, TEXT, True)], spacing=0)], spacing=12)))
        ctrls += [card(ft.Column([T("مدد الاشتراك المتاحة", 12, MUTED, True),
                                  T("  •  ".join(C.LC.PLANS[m] for m in sorted(C.LC.PLANS)), 14, DARK, True)], spacing=4),
                       padding=12),
                  code, btn("لصق من الحافظة", "download", paste_code, kind="soft", height=44),
                  btn("تفعيل" if st != "ok" else "تجديد", "key", activate)]
        show("تفعيل التطبيق" if first else "الترخيص", ctrls, back=None if first else (back or app.home))


    # ═════════════════════ الترحيب ═════════════════════
    def splash():
        page.clean()
        page.appbar = None
        page.bottom_appbar = None
        page.bgcolor = BG
        anim = ft.Animation(700, ft.AnimationCurve.EASE_OUT)
        mark = ft.Container(logo(84), width=140, height=140, border_radius=70, bgcolor=WHITE,
                            alignment=ft.alignment.center, opacity=0, animate_opacity=anim,
                            shadow=ft.BoxShadow(blur_radius=30, color=ft.Colors.with_opacity(0.18, PRIMARY),
                                                offset=ft.Offset(0, 10)))
        name = ft.Text(APP_NAME, size=36, weight=ft.FontWeight.BOLD, color=DARK, opacity=0,
                       animate_opacity=anim, rtl=False)
        bar = ft.Container(width=44, height=4, border_radius=2, bgcolor=PRIMARY, opacity=0, animate_opacity=anim)
        prog = ft.ProgressBar(width=130, bar_height=3, color=PRIMARY, bgcolor=tint(PRIMARY, .18), opacity=0,
                              animate_opacity=anim)
        circle = lambda s, l, t, o: ft.Container(width=s, height=s, border_radius=s // 2, left=l, top=t,
                                                 bgcolor=tint(PRIMARY, o))
        page.add(ft.Container(ft.Stack([
            circle(300, -100, -90, .13), circle(200, 220, 560, .11), circle(90, 260, 150, .09),
            ft.Container(ft.Column([mark, ft.Container(height=18), name, ft.Container(height=4), bar],
                                   alignment=ft.MainAxisAlignment.CENTER,
                                   horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                         alignment=ft.alignment.center, left=0, right=0, top=0, bottom=80),
            ft.Container(prog, alignment=ft.alignment.center, left=0, right=0, bottom=60),
        ], expand=True), expand=True,
            gradient=ft.LinearGradient(colors=[tint(PRIMARY, .22), SURFACE_TINT], begin=ft.alignment.top_center,
                                       end=ft.alignment.bottom_center)))
        page.update()
        for c in (mark, name, bar, prog):
            c.opacity = 1
        page.update()
        time.sleep(2.0)
        app.home()


    # ═════════════════════ الحساب والأمان ═════════════════════
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
        return field(label, password=True, can_reveal_password=True, **kw)


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
        legacy = C.has_legacy_plain_db()
        escrow = ft.Switch(value=True, active_color=PRIMARY)
        esc_row = card(ft.Row([escrow, ft.Column([
            T("السماح لمدير البرنامج بمساعدتي في استرجاع كلمة المرور", 13, DARK, True),
            T("عند التفعيل يستطيع المدير (تقنياً) فتح بياناتك إن حصل على ملفاتك ورمز طلبك. عند الإيقاف لا يُسترجع شيء "
              "إلا بمفتاح الاسترداد الذي ستحفظه.", 11, MUTED)], spacing=2, expand=True)], spacing=12), padding=12)
        user = field("اسم المستخدم")
        pw = pw_field("كلمة المرور (10 خانات على الأقل — الأفضل جملة)")
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
                rkey = C.setup_account(user.value, pw.value, escrow.value)
            except C.VaultError as ex:
                err.value, err.color = str(ex), DANGER
                return err.update()
            except Exception as ex:
                err.value, err.color = f"تعذّر إنشاء الحساب: {ex}", DANGER
                return err.update()
            toast("تم إنشاء الحساب وتشفير البيانات", OK)
            recovery_key_dialog(rkey, after_login)
        auth_shell("إنشاء حساب المستخدم", "اختر اسم مستخدم وكلمة مرور. ستُطلب في كل مرة تفتح فيها التطبيق.", [
            user, pw, pw2, esc_row, err,
            btn("إنشاء الحساب", "user_plus", create),
            card(ft.Column([
                T("مهم", 13, DANGER, True),
                T("• جميع بيانات المرضى والصور والمرفقات والنسخ الاحتياطية ستُحفظ مشفّرة ولا تُفتح خارج التطبيق.", 12, TEXT),
                T("• إن نسيت كلمة المرور فتسترجعها بمفتاح الاسترداد الذي سيُعرض لك الآن مرة واحدة (أو عبر مدير البرنامج إن فعّلت ذلك).", 12, TEXT),
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
            except Exception as ex:
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
            except Exception as ex:
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
            return app.home()
        ui["splashed"] = True
        splash()


    def config_error_screen():
        auth_shell("إعداد غير مكتمل", "لا يمكن تشغيل هذه النسخة: ملف المفاتيح العامة (public_keys.py) غير مضبوط.", [
            card(ft.Column([T("على حاسوب المطوّر: شغّل keygen.py مرة واحدة (يولّد المفاتيح تلقائياً)، "
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

    # ── تسجيل الشاشات/الأدوات ليستعملها غيرها عبر app ──
    app.license_screen = license_screen
    app.splash = splash
    app.auth_shell = auth_shell
    app.pw_field = pw_field
    app.recovery_key_dialog = recovery_key_dialog
    app.setup_screen = setup_screen
    app.fmt_wait = fmt_wait
    app.login_screen = login_screen
    app.reset_screen = reset_screen
    app.lock_now = lock_now
    app.after_login = after_login
    app.config_error_screen = config_error_screen
    app.boot_account = boot_account
