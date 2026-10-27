# -*- coding: utf-8 -*-
"""الإعدادات: التشخيص والإحصائيات والنسخ الاحتياطي والحساب والأمان."""
import os
from datetime import datetime, timedelta

import flet as ft
import core as C
from theme import (BLUE, BORDER, DANGER, DARK, MINT, MUTED, OK, PRIMARY, R_TILE, TEXT, TINT_A, TINT_B, TINT_G, TINT_R, WHITE)
from core import (APP_NAME, APP_VERSION, today)
from ui_kit import (AUTO_LOCK_SECONDS, RANGES, ic, shadow)


def register(app):
    page = app.page
    T, ask_date, btn, card, choice_group, dialog, dlg_btn, dlg_w, fchip, field, icon_btn, open_url, pick, sec, show, tile, toast = app.T, app.ask_date, app.btn, app.card, app.choice_group, app.dialog, app.dlg_btn, app.dlg_w, app.fchip, app.field, app.icon_btn, app.open_url, app.pick, app.sec, app.show, app.tile, app.toast


    # ═════════════════════ الإعدادات ═════════════════════
    def settings_screen():
        st, days = C.lic_status()
        last = C.last_backup_time()

        def item(icon, bg, col, title, sub, on_click):
            return card(ft.Row([tile(icon, bg, col, 44, 22, 14),
                                ft.Column([T(title, 16, TEXT, True), T(sub, 12, MUTED)], spacing=1, expand=True),
                                ic("chevron_left", 20, "m")], spacing=16), padding=16, on_click=on_click)
        show("الإعدادات", [
            item("lock", TINT_R, "r", "الحساب والأمان", f"المستخدم: {C.VAULT.user} — البيانات مشفّرة",
                 lambda e: security_screen()),
            item("shield_check", TINT_G, "g", "الترخيص",
                 f"فعّال — متبقٍ {days} يوماً" if st == "ok" else "غير فعّال",
                 lambda e: app.license_screen(back=settings_screen)),
            item("backup", MINT, "p", "النسخ الاحتياطي",
                 f"آخر نسخة: {last[:10]}" if last else "لم تؤخذ نسخة بعد", lambda e: backup_screen()),
            item("chart", TINT_B, "b", "الإحصائيات", "المرضى والعمليات والمراجعات", lambda e: stats_screen()),
            item("pulse", TINT_A, "a", "تشخيص الجهاز", "فحوص ذاتية وتقرير للدعم الفني وتحسين الصور",
                 lambda e: diagnostics_screen()),
            card(ft.Row([tile("info", MINT, "p", 44, 22, 14),
                         ft.Column([T(APP_NAME, 16, TEXT, True, rtl=False), T(f"الإصدار {APP_VERSION}", 12, MUTED)],
                                   spacing=1, expand=True)], spacing=16), padding=16),
        ], back=app.home)


    # ═════════════════════ تشخيص الجهاز ═════════════════════
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
        ], back=app.settings_screen)
        run()


    # ═════════════════════ الإحصائيات ═════════════════════
    def stats_screen():
        sel = {"r": 30, "lo": None, "hi": None}
        chips = ft.Row(wrap=True, spacing=8, run_spacing=8, rtl=True)
        body = ft.Column(spacing=12, rtl=True)

        def bounds():
            r = sel["r"]
            if r is None:
                return None, None
            if r == "custom":
                return sel["lo"], sel["hi"]
            return (datetime.now() - timedelta(days=r)).strftime("%Y-%m-%d") if r else today(), today()

        def big(icon, bg, col, number, label):
            return ft.Container(
                ft.Column([tile(icon, bg, col, 44, 22, 14), T(str(number), 28, TEXT, True), T(label, 12, MUTED)],
                          spacing=4), bgcolor=WHITE, border_radius=R_TILE, padding=16, expand=True,
                border=ft.border.all(1, BORDER), shadow=shadow())

        def small(label, number, color):
            return ft.Row([ft.Container(width=10, height=10, border_radius=5, bgcolor=color), T(label, 14, TEXT, expand=True),
                           T(str(number), 16, TEXT, True)], spacing=12)

        def render(update=True):
            lo, hi = bounds()
            s = C.stats(lo, hi)
            rng = "كل الفترات" if lo is None and hi is None else f"{lo or '…'}  ←  {hi or '…'}"
            chips.controls = [fchip(t, sel["r"] == v, lambda e, v=v: pick_range(v)) for t, v in RANGES]
            body.controls = [
                card(ft.Row([ic("calendar", 20, "p"), T("النطاق الزمني:", 13, MUTED), T(rng, 14, DARK, True)],
                            spacing=8), padding=12),
                ft.Row([big("users", MINT, "p", s["patients"], "مرضى جدد في الفترة"),
                        big("scissors", TINT_R, "r", s["surgeries"], "عمليات منجزة")], spacing=12),
                ft.Row([big("stethoscope", TINT_G, "g", s["visits"], "مراجعات منجزة"),
                        big("calendar", TINT_A, "a", s["pending"], "مواعيد معلّقة")], spacing=12),
                ft.Row([big("x", MINT, "m", s["cancelled"], "مواعيد ملغاة"),
                        big("user_clock", TINT_R, "r", s["no_show"], "لم يحضروا")], spacing=12),
                card(ft.Row([ic("info", 20, "m"),
                             T("المعلّقة: مواعيد (عمليات أو مراجعات) لم يُضغط «تأكيد الإنجاز» عليها بعد، وتاريخ موعدها ضمن "
                               "النطاق المحدد، وتشمل المتأخرة. الملغاة لا تُحتسب فيها. المنجزة تُحسب بتاريخ تأكيدها.",
                               12, MUTED, expand=True)], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START),
                     padding=12),
                card(ft.Column([T("تفصيل المرضى في الفترة", 14, DARK, True),
                                small("مرضى جدد", s["new"], PRIMARY), small("مرضى قدامى", s["old"], BLUE),
                                ft.Divider(height=1, color=BORDER),
                                small("إجمالي المرضى في التطبيق", s["total_patients"], MUTED)], spacing=12)),
            ]
            if update:
                chips.update()
                body.update()

        def pick_range(v):
            if v == "custom":
                def got_lo(d):
                    sel["lo"] = d.strftime("%Y-%m-%d")

                    def got_hi(d2):
                        sel.update(r="custom", hi=d2.strftime("%Y-%m-%d"))
                        if sel["hi"] < sel["lo"]:
                            sel["lo"], sel["hi"] = sel["hi"], sel["lo"]
                        render()
                    toast("اختر تاريخ النهاية")
                    ask_date(got_hi)
                toast("اختر تاريخ البداية")
                ask_date(got_lo)
                return
            sel["r"] = v
            render()
        render(update=False)
        show("الإحصائيات", [chips, body, ft.Container(height=10)], back=app.home)


    # ═════════════════════ النسخ الاحتياطي ═════════════════════
    def backup_screen():
        last = C.last_backup_time()
        info = T("", 13, OK, True)
        rep = C.backup_report()
        warn = [card(ft.Row([tile("alert", TINT_R, "r", 36, 18, 11),
                             T(f"آخر نسخة لم تشمل {rep['skipped']} ملف من {rep['files']} (تالفة أو غير مقروءة). أنشئ نسخة جديدة، "
                               "وإن تكرر ذلك فأرسل «تقرير التشخيص» للمطوّر.", 12, DANGER, True, expand=True)], spacing=12),
                      padding=12)] if rep["skipped"] else []

        def do_backup(e):
            try:
                path = C.make_backup()
                info.value = "تم إنشاء النسخة: " + os.path.basename(path)
                info.update()
                r2 = C.backup_report()
                if r2["skipped"]:
                    toast(f"تحذير: تعذّر نسخ {r2['skipped']} ملف تالف من {r2['files']}", DANGER)
                backup_screen()
            except Exception as ex:
                toast(f"فشل النسخ: {ex}", DANGER)

        def download(path):
            try:
                open_url(C.share_file(path))
                C.mark_exported()
                toast("سيُفتح المتصفح لتنزيل النسخة إلى هاتفك")
            except Exception as ex:
                toast(f"تعذر التصدير: {ex}", DANGER)

        def export_now(e):
            try:
                download(C.make_backup())
                backup_screen()
            except Exception as ex:
                toast(f"فشل النسخ: {ex}", DANGER)

        def do_restore(path):
            try:
                need = C.backup_needs_password(path)
            except Exception:
                return toast("الملف ليس نسخة احتياطية صالحة لـ Clinic Pro", DANGER)
            pw = field("كلمة مرور الحساب وقت أخذ النسخة (أو مفتاح الاسترداد)", password=True, can_reveal_password=True) if need else None
            err = T("", 12, DANGER, True)

            def go(e):
                try:
                    C.restore_backup(path, pw.value if pw else None)
                except ValueError as ex:
                    err.value = str(ex)
                    err.update()
                    return
                except Exception as ex:
                    err.value = f"فشلت الاستعادة: {ex}"
                    err.update()
                    return
                page.close(dlg)
                toast("تمت الاستعادة بنجاح", OK)
                app.home()
            body = [T("سيتم استبدال جميع البيانات الحالية ببيانات النسخة. تؤخذ نسخة أمان تلقائياً قبل الاستبدال.", 14, TEXT)]
            if need:
                body.append(T("هذه النسخة من حساب آخر/جهاز آخر، فاكتب كلمة مرور ذلك الحساب. بعد الاستعادة تبقى كلمة مرورك "
                              "الحالية كما هي.", 12, MUTED))
            dlg = dialog("استعادة نسخة احتياطية", ft.Column(body + ([pw] if pw else []) + [err], tight=True, width=dlg_w(),
                                                            rtl=True, spacing=12),
                         [dlg_btn("استعادة", go, "danger"), dlg_btn("إلغاء", lambda e: page.close(dlg))])

        files = C.list_backups()
        rows = []
        for f in files[:10]:
            full, size = C.backup_info(f)
            rows.append(card(ft.Row([
                tile("folder", MINT, "p", 44, 22, 14),
                ft.Column([T(f.replace("shifa_backup_", "").replace(C.BK_EXT, ""), 14, TEXT, True),
                           T(f"{size / 1_048_576:.1f} MB", 11, MUTED)], spacing=0, expand=True),
                icon_btn("download", "p", lambda e, p=full: download(p)),
                icon_btn("restore", "r", lambda e, p=full: do_restore(p))], spacing=6), padding=12))

        show("النسخ الاحتياطي", warn + [
            card(ft.Column([
                ft.Row([tile("backup", MINT, "p", 44, 22, 14),
                        ft.Column([T(f"نسخة تلقائية كل {C.BACKUP_EVERY_DAYS} أيام (يُحتفظ بآخر {C.KEEP_BACKUPS})", 14, TEXT, True),
                                   T("آخر نسخة: " + (last[:10] if last else "—"), 12, MUTED)], spacing=1, expand=True)],
                       spacing=12), info], spacing=8)),
            card(ft.Row([tile("alert", TINT_R, "r", 36, 18, 11),
                         T("النسخ المحفوظة هنا تُحذف مع إلغاء تثبيت التطبيق أو فقدان الهاتف. صدّر نسخة بانتظام إلى مكان آخر "
                           "(واتساب لنفسك، بريد، حاسوب). آخر تصدير: "
                           + ((C.last_export_time() or "—")[:10]), 12, DANGER, True, expand=True)],
                        spacing=12), padding=12),
            btn("نسخة جديدة وتصديرها خارج الجهاز", "share", export_now),
            btn("إنشاء نسخة الآن (داخل الجهاز)", "backup", do_backup, kind="soft"),
            btn("استيراد نسخة من ملف (.shbk)", "upload", lambda e: pick(lambda ps: do_restore(ps[0]), images=False),
                kind="outline"),
            T("النسخ مشفّرة ولا تُفتح إلا بكلمة مرور الحساب. لنقل نسخة إلى جهاز آخر: اضغط أيقونة التنزيل بجانبها "
              "فيُنزَّل الملف إلى هاتفك، ثم انقله كأي ملف واستورده هناك.", 12, MUTED),
            sec("النسخ المحفوظة", "folder"),
        ] + (rows or [T("لا توجد نسخ بعد", 13, MUTED)]), back=app.settings_screen)


    def security_screen():
        def change_pw(e):
            old, new, new2 = app.pw_field("كلمة المرور الحالية"), app.pw_field("كلمة المرور الجديدة"), app.pw_field("تأكيد الجديدة")
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
                app.recovery_key_dialog(rk, security_screen)
            d2 = dialog("مفتاح الاسترداد",
                        T("سيُنشأ مفتاح جديد ويُعرض لك مرة واحدة، وأي مفتاح سابق يتوقف عن العمل فوراً. تابع؟", 14, TEXT),
                        [dlg_btn("إنشاء", go, "ok"), dlg_btn("إلغاء", lambda e2: page.close(d2))])

        def toggle_escrow(e):
            on = C.VAULT.escrow_enabled
            if on and not C.VAULT.has_recovery_key:
                return toast("أنشئ مفتاح الاسترداد أولاً، فبدونه لن تملك أي وسيلة لاسترجاع كلمة المرور", DANGER)

            def go(e2):
                try:
                    C.set_escrow(not on)
                except C.VaultError as ex:
                    page.close(d3)
                    return toast(str(ex), DANGER)
                page.close(d3)
                toast("تم تحديث إعداد الاسترداد", OK)
                security_screen()
            msg = ("لن يستطيع مدير البرنامج مساعدتك في استرجاع كلمة المرور. إن فقدت كلمة المرور ومفتاح الاسترداد معاً "
                   "فلن يستطيع أحد فتح بياناتك." if on else
                   "سيستطيع مدير البرنامج (تقنياً) فتح بياناتك إن حصل على ملفاتك ورمز طلب منك، وتتيح لك خدمة استرجاع "
                   "كلمة المرور عبره.")
            d3 = dialog("الاسترداد عبر مدير البرنامج", T(msg, 14, TEXT),
                        [dlg_btn("إيقاف" if on else "تفعيل", go, "danger" if on else "ok"),
                         dlg_btn("إلغاء", lambda e2: page.close(d3))])
        lock_labels = {0: "فوراً", 30: "30 ثانية", 60: "دقيقة", 180: "3 دقائق", 600: "10 دقائق"}
        inv_lock = {v: k for k, v in lock_labels.items()}

        def set_lock(v):
            try:
                C.set_lock_policy(inv_lock[v])
                toast("تم حفظ سياسة القفل", OK)
            except Exception as ex:
                toast(f"تعذّر الحفظ: {ex}", DANGER)
        lock_ui, _ = choice_group("القفل عند الذهاب للخلفية", list(lock_labels.values()), lock_labels[C.lock_policy()],
                                  set_lock, allow_none=False)
        show("الحساب والأمان", [
            card(ft.Row([tile("shield_check", TINT_G, "g", 44, 22, 14),
                         ft.Column([T(C.VAULT.user, 16, TEXT, True),
                                    T("البيانات والصور والمرفقات والنسخ مشفّرة", 12, OK, True)], spacing=1, expand=True)],
                        spacing=16), padding=16),
            btn("تغيير كلمة المرور", "key", change_pw, kind="soft"),
            btn("تجديد مفتاح الاسترداد" if C.VAULT.has_recovery_key else "إنشاء مفتاح الاسترداد", "key", new_rk, kind="soft"),
            btn("إيقاف الاسترداد عبر مدير البرنامج" if C.VAULT.escrow_enabled else "تفعيل الاسترداد عبر مدير البرنامج",
                "shield_check", toggle_escrow, kind="outline"),
            card(ft.Column([lock_ui, T("يُستثنى تلقائياً فتح الكاميرا/الملفات والطباعة والتصدير (يُقفل فقط إن طال الغياب أكثر من 3 دقائق).",
                                        11, MUTED)], spacing=8), padding=14),
            btn("قفل التطبيق الآن", "lock", app.lock_now, kind="outline"),
            T(f"يُقفل التطبيق تلقائياً إن غاب عن الشاشة أكثر من {AUTO_LOCK_SECONDS // 60} دقائق. "
              "بعد 5 محاولات دخول خاطئة يلزم رمز إعادة تعيين من مدير البرنامج.", 12, MUTED),
        ], back=app.settings_screen)


    # ── تسجيل الشاشات/الأدوات ليستعملها غيرها عبر app ──
    app.settings_screen = settings_screen
    app.diagnostics_screen = diagnostics_screen
    app.stats_screen = stats_screen
    app.backup_screen = backup_screen
    app.security_screen = security_screen
    app.settings_screen = settings_screen
