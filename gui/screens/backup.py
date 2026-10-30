# -*- coding: utf-8 -*-
"""
النسخ الاحتياطي والاستعادة — لا تحتوي أي SQL: كل الوصول للبيانات عبر core.
"""
import os

import flet as ft
import core as C

from theme import (DANGER, OK, TEXT, MUTED, MINT, TINT_R)


def install(app):
    page = app.page
    toast = app.toast
    T = app.T
    card = app.card
    tile = app.tile
    btn = app.btn
    icon_btn = app.icon_btn
    sec = app.sec
    field = app.field
    show = app.show
    dlg_w = app.dlg_w
    dialog = app.dialog
    dlg_btn = app.dlg_btn
    open_url = app.open_url
    pick = app.pick
    def home(*a, **k):
        return app.s.home(*a, **k)
    def settings_screen(*a, **k):
        return app.s.settings_screen(*a, **k)

    def backup_screen():
        last = C.jload(C.SET_PATH, {}).get("last_backup")
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
                return toast("الملف ليس نسخة احتياطية صالحة لـ My Clinic", DANGER)
            pw = field("كلمة مرور الحساب وقت أخذ النسخة (أو مفتاح الاسترداد)", password=True, can_reveal_password=True) if need else None
            err = T("", 12, DANGER, True)

            def go(e):
                try:
                    C.restore_backup(path, pw.value if pw else None)
                except ValueError as ex:
                    err.value = str(ex)
                    err.update()
                    return
                except Exception as ex:                      # حدّ الواجهة: نسجّل ونُبلغ
                    C.LOG.log_exc("restore_backup_ui", ex)
                    err.value = f"فشلت الاستعادة: {ex}"
                    err.update()
                    return
                page.close(dlg)
                toast("تمت الاستعادة بنجاح", OK)
                home()
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
            full = os.path.join(C.BK_DIR, f)
            rows.append(card(ft.Row([
                tile("folder", MINT, "p", 44, 22, 14),
                ft.Column([T(f.replace("myclinic_backup_", "").replace(C.BK_EXT, ""), 14, TEXT, True),
                           T(f"{os.path.getsize(full) / 1_048_576:.1f} MB", 11, MUTED)], spacing=0, expand=True),
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
                           + ((C.jload(C.SET_PATH, {}).get("last_export") or "—")[:10]), 12, DANGER, True, expand=True)],
                        spacing=12), padding=12),
            btn("نسخة جديدة وتصديرها خارج الجهاز", "share", export_now),
            btn("إنشاء نسخة الآن (داخل الجهاز)", "backup", do_backup, kind="soft"),
            btn("استيراد نسخة من ملف (.shbk)", "upload", lambda e: pick(lambda ps: do_restore(ps[0]), images=False),
                kind="outline"),
            T("النسخ مشفّرة ولا تُفتح إلا بكلمة مرور الحساب. لنقل نسخة إلى جهاز آخر: اضغط أيقونة التنزيل بجانبها "
              "فيُنزَّل الملف إلى هاتفك، ثم انقله كأي ملف واستورده هناك.", 12, MUTED),
            sec("النسخ المحفوظة", "folder"),
        ] + (rows or [T("لا توجد نسخ بعد", 13, MUTED)]), back=settings_screen)

    app.register(backup_screen=backup_screen)
