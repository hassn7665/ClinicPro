# -*- coding: utf-8 -*-
"""ملف المريض: النموذج والبحث وشاشة الملف (المواعيد والمرفقات والصور)."""
import os
from datetime import datetime

import flet as ft
import core as C
from theme import (ACCENT, BLUE, BORDER, BORDER_STRONG, DANGER, DARK, DEEP, FIELD_BG, MINT, MUTED, OK, PRIMARY, R_CARD, R_CTRL, R_FIELD, R_SM, SOFT, TEXT, TINT_G, TINT_R, VIEWER_BAR, VIEWER_BG, WHITE)
from core import (KIND_AR, ev_dt, rel_label)
from ui_kit import (BLOODS, PAY_LBL, dur_text, ev_dur, ic)


def register(app):
    page, ui = app.page, app.ui
    T, ask_confirm, ask_datetime, btn, card, choice_group, conflict_text, dialog, dlg_btn, dlg_w, duration_picker, field, icon_btn, img_ctl, items_editor, open_url, pick, pill, read_pays, sec, show, tile, toast, width = app.T, app.ask_confirm, app.ask_datetime, app.btn, app.card, app.choice_group, app.conflict_text, app.dialog, app.dlg_btn, app.dlg_w, app.duration_picker, app.field, app.icon_btn, app.img_ctl, app.items_editor, app.open_url, app.pick, app.pill, app.read_pays, app.sec, app.show, app.tile, app.toast, app.width


    def image_screen(rel, back):
        """عرض الصورة بملء الشاشة مع تكبير بالأصابع."""
        page.clean()
        page.bottom_appbar = None
        page.bgcolor = VIEWER_BG
        page.appbar = ft.AppBar(
            title=ft.Text("عرض الصورة", size=14, color=WHITE), center_title=True, bgcolor=VIEWER_BAR,
            leading=icon_btn("arrow_right", "w", lambda e: back()), leading_width=56, toolbar_height=54)
        page.add(ft.InteractiveViewer(
            content=img_ctl(rel, width(), max(int(page.height or 640) - 70, 300), ft.ImageFit.CONTAIN, full=True),
            min_scale=1, max_scale=6, expand=True))
        page.update()


    # ═════════════════════ نموذج المريض ═════════════════════
    def patient_form(status=None, pid=None):
        ui["img_left"] = 6
        p = C.patient_get(pid) if pid else None
        status = p["status"] if p else (status or "جديد")
        g = lambda k: (p[k] if p and p[k] is not None else "")

        status_ui, get_status = choice_group("حالة المريض", ["جديد", "قديم"], status, chip_w=110, allow_none=False)

        name = field("الاسم الثلاثي *", value=g("full_name"))
        gender_ui, get_gender = choice_group("الجنس", ["ذكر", "أنثى"], g("gender") or None, chip_w=110)
        age = field("العمر", value=str(g("age")), keyboard_type=ft.KeyboardType.NUMBER)
        blood_ui, get_blood = choice_group("زمرة الدم", BLOODS, g("blood") or None, chip_w=64)
        residence = field("مكان السكن", value=g("residence"))
        phone = field("رقم التواصل", value=g("phone"), keyboard_type=ft.KeyboardType.PHONE)
        job = field("العمل", value=g("job"))

        dis_txt = g("diseases")
        has0 = "نعم" if dis_txt.startswith("نعم") else ("لا" if dis_txt else None)
        dis_details = field("اذكر الأمراض", value=dis_txt.replace("نعم:", "").replace("نعم", "").strip(),
                            multiline=True, min_lines=2, visible=has0 == "نعم")

        def on_has(v):
            dis_details.visible = v == "نعم"
            dis_details.update()
        has_ui, get_has = choice_group("هل يوجد أمراض؟", ["لا", "نعم"], has0, on_has, chip_w=110)
        allergies = field("الحساسية (أدوية/مواد) — اتركه فارغاً إن لا يوجد", value=g("allergies"), multiline=True, min_lines=1)
        medications = field("الأدوية الحالية", value=g("medications"), multiline=True, min_lines=1)
        diagnosis = field("التشخيص", value=g("diagnosis"), multiline=True, min_lines=1)
        notes = field("ملاحظات", value=g("notes"), multiline=True, min_lines=3)

        photos, new_atts, gone = {}, [], set()
        tw = int((width() - 32 - 32 - 20) / 3)

        def photo_slot(label, key):
            box = ft.Container(width=tw, height=tw, border_radius=R_CTRL, bgcolor=FIELD_BG, alignment=ft.alignment.center,
                               border=ft.border.all(1.5, BORDER_STRONG), clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                               content=ft.Column([ic("photo_add", 28, "p"), T("إضافة", 11, MUTED)],
                                                 alignment=ft.MainAxisAlignment.CENTER,
                                                 horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2))
            empty = box.content
            if p and p[key]:
                box.content = img_ctl(p[key], tw, tw)

            def picked(paths):
                photos[key] = paths[0]
                gone.discard(key)
                box.content = ft.Image(src=paths[0], width=tw, height=tw, fit=ft.ImageFit.COVER)
                box.update()

            def remove(e):
                """يزيل الصورة المختارة حديثاً فوراً؛ والمحفوظة سابقاً تُحذف عند الحفظ (بعد تأكيد)."""
                def do():
                    photos.pop(key, None)
                    if p and p[key]:
                        gone.add(key)
                    box.content = empty
                    box.update()
                if p and p[key] and key not in gone and key not in photos:
                    ask_confirm("حذف الصورة", "ستُحذف الصورة نهائياً من ملف المريض عند حفظ التعديلات.", do, "حذف")
                else:
                    do()
            box.on_click = lambda e: pick(picked)
            return ft.Column([box, ft.Row([T(label, 12, DARK, True),
                                           ft.Container(T("حذف", 11, DANGER, True), on_click=remove, ink=True, border_radius=R_SM,
                                                        padding=ft.padding.symmetric(horizontal=6, vertical=2))],
                                          alignment=ft.MainAxisAlignment.CENTER, spacing=4)], spacing=6,
                             horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        att_list = ft.Column(spacing=6, rtl=True)
        if p:
            for a in C.patient_attachments(pid):
                att_list.controls.append(ft.Row([ic("paperclip", 16, "m"), T(a["name"], 12, MUTED)], spacing=6))

        def atts_picked(paths):
            for pth in paths:
                new_atts.append(pth)
                att_list.controls.append(ft.Row([ic("check_circle", 16, "g"), T(os.path.basename(pth), 12, OK)],
                                                spacing=6))
            att_list.update()

        def after_saved(rec):
            if pid:
                toast("تم تحديث البيانات", OK)
                return patient_screen(pid)
            dlg = dialog("تمت إضافة المريض",
                         ft.Column([T(rec["full_name"], 14, TEXT, True),
                                    T("كود المريض (للمراجعة)", 12, MUTED),
                                    ft.Container(T(rec["code"], 28, PRIMARY, True, selectable=True), bgcolor=MINT,
                                                 border_radius=R_FIELD, padding=ft.padding.symmetric(vertical=8, horizontal=22))],
                                   tight=True, horizontal_alignment=ft.CrossAxisAlignment.CENTER, rtl=True),
                         [dlg_btn("فتح الملف", lambda e: (page.close(dlg), patient_screen(rec["id"])), "primary"),
                          dlg_btn("الرئيسية", lambda e: (page.close(dlg), app.home()))])

        def dup_dialog(matches, data):
            rows = []
            for m in matches[:4]:
                why = "نفس الاسم" if m["reason"] == "name" else "نفس رقم الهاتف (قد يكون من العائلة)"
                rows.append(card(ft.Column([T(m["full_name"], 14, TEXT, True),
                                            T(f"{m['code']} • {m['phone'] or 'بلا هاتف'} • {why}", 12, MUTED)], spacing=2),
                                 padding=10, on_click=lambda e, i=m["id"]: (page.close(dlg), patient_screen(i))))
            first = matches[0]["id"]
            dlg = dialog("مريض مشابه موجود",
                         ft.Column([T("وُجد في التطبيق مريض مشابه. افتح ملفه بدل تكرار الإدخال، أو احفظ كمريض جديد إن كان شخصاً آخر.",
                                      13, TEXT)] + rows, tight=True, width=dlg_w(), rtl=True, spacing=10,
                                   scroll=ft.ScrollMode.AUTO),
                         [dlg_btn("فتح الملف الموجود", lambda e: (page.close(dlg), patient_screen(first)), "primary"),
                          dlg_btn("حفظ كمريض جديد", lambda e: (page.close(dlg), save_flow(data, True)), "danger"),
                          dlg_btn("رجوع", lambda e: page.close(dlg))])

        def save_flow(data, allow=False):
            try:
                rec = C.save_patient(data, photos, new_atts, pid, allow_duplicate=allow)
            except C.DuplicatePatient as ex:
                return dup_dialog(ex.matches, data)
            except Exception as ex:
                return toast(f"تعذر الحفظ: {ex}", DANGER)
            for key in gone:                       # صور حُذفت من النموذج (المحفوظة سابقاً) تُحذف بعد نجاح الحفظ
                if key not in photos:
                    try:
                        C.clear_patient_photo(pid, key)
                    except Exception as ex2:
                        C.LOG.log_exc("clear_photo", ex2)
            after_saved(rec)

        def submit(e):
            nm = name.value.strip()
            if len(nm.split()) < 3:
                name.error_text = "أدخل الاسم الثلاثي (ثلاث كلمات)"
                name.update()
                return
            name.error_text = None
            name.update()
            try:
                ag = int(age.value) if age.value.strip() else None
                if ag is not None and not 0 <= ag <= 130:
                    raise ValueError
            except ValueError:
                age.error_text = "عمر غير صحيح"
                age.update()
                return
            age.error_text = None
            has = get_has()
            dis = "" if has is None else ("لا" if has == "لا" else
                                          ("نعم: " + dis_details.value.strip() if dis_details.value.strip() else "نعم"))
            data = dict(full_name=nm, gender=get_gender(), age=ag, residence=residence.value.strip(),
                        phone=phone.value.strip(), job=job.value.strip(), diseases=dis,
                        notes=notes.value.strip(), blood=get_blood(), status=get_status() or "جديد",
                        allergies=allergies.value.strip(), medications=medications.value.strip(),
                        diagnosis=diagnosis.value.strip())
            save_flow(data)

        title = "تعديل البيانات" if pid else "إضافة مريض"
        show(title, [
            card(ft.Column([sec("البيانات الأساسية", "badge"), status_ui, name, gender_ui, age, blood_ui], spacing=16)),
            card(ft.Column([sec("التواصل والعمل", "phone"), residence, phone, job], spacing=16)),
            card(ft.Column([sec("الحالة الصحية", "heart_pulse"), has_ui, dis_details, allergies, medications, diagnosis,
                            notes], spacing=16)),
            card(ft.Column([sec("الصور", "image"),
                            ft.Row([photo_slot("قبل", "photo_before"), photo_slot("بعد", "photo_after"),
                                    photo_slot("التحاليل", "photo_lab")],
                                   alignment=ft.MainAxisAlignment.SPACE_BETWEEN)], spacing=16)),
            card(ft.Column([sec("المرفقات", "paperclip"), att_list,
                            btn("إضافة مرفقات", "upload", lambda e: pick(atts_picked, images=False, multiple=True),
                                kind="soft", height=46)], spacing=12)),
            btn("حفظ التعديلات" if pid else "إضافة المريض", "check_circle", submit),
            ft.Container(height=16),
        ], back=(lambda: patient_screen(pid)) if pid else app.home)


    # ═════════════════════ البحث ═════════════════════
    def search_screen():
        results = ft.Column(spacing=12, rtl=True)
        box = field("الاسم أو كود المريض أو رقم الهاتف", autofocus=True)

        def go(e=None):
            results.controls.clear()
            if (box.value or "").strip():
                rows = C.search_patients(box.value, 50)
                if not rows:
                    results.controls.append(card(ft.Column([
                        tile("search", MINT, "p", 52, 26, 16), T("لا توجد نتائج", 14, MUTED, True)],
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8), padding=24))
                for r in rows:
                    results.controls.append(card(ft.Row([
                        tile("user", MINT, "p", 44, 22, 14),
                        ft.Column([T(r["full_name"], 14, TEXT, True),
                                   ft.Row([T(r["code"], 12, MUTED),
                                           pill(r["status"], PRIMARY if r["status"] == "جديد" else BLUE, size=11)],
                                          spacing=8),
                                   T(r["phone"] or "", 12, MUTED, selectable=True) if r["phone"] else ft.Container()],
                                  spacing=4, expand=True),
                        btn("فتح الملف", "file", lambda e, i=r["id"]: patient_screen(i), height=40)], spacing=12),
                        padding=12))
            results.update()
        box.on_change = go
        box.on_submit = go
        show("البحث عن مريض", [box, results], back=app.home)


    # ═════════════════════ ملف المريض ═════════════════════
    def info_row(icon, label, value, last=False, pill_color=None):
        val = (pill(str(value), pill_color) if pill_color and value not in (None, "")
               else T(str(value) if value not in (None, "") else "—", 14, TEXT, True, selectable=True))
        r = ft.Row([tile(icon, MINT, "p", 36, 18, 11),
                    ft.Column([T(label, 12, MUTED), val], spacing=1, expand=True)], spacing=12)
        return ft.Column([r] if last else [r, ft.Divider(height=1, color=BORDER)], spacing=12)


    def patient_screen(pid):
        ui["img_left"] = 6
        p = C.patient_get(pid)
        if not p:
            return app.home()
        evs = C.patient_events(pid)
        atts = C.patient_attachments(pid)
        back_here = lambda: patient_screen(pid)

        def do_print(e):
            try:
                open_url(C.build_report(pid))
                toast("يُفتح التقرير في المتصفح — اضغط «طباعة / حفظ PDF»")
            except Exception as ex:
                toast(f"تعذر إنشاء التقرير: {ex}", DANGER)

        # رأس الملف
        initial = (p["full_name"].strip() or "؟")[0]

        def fact(label, value):
            return ft.Container(ft.Column([T(label, 11, MUTED), T(value, 16, DARK, True)], spacing=0,
                                          horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                expand=True, bgcolor=WHITE, border=ft.border.all(1, SOFT["p"][1]),
                                border_radius=R_FIELD, padding=12)
        facts = ft.Row([fact("العمر", str(p["age"]) if p["age"] is not None else "—"),
                        fact("الجنس", p["gender"] or "—"), fact("زمرة الدم", p["blood"] or "—")], spacing=8)
        header = ft.Container(ft.Column([
            ft.Row([
                ft.Container(T(initial, 28, DEEP, True), width=64, height=64, border_radius=32, bgcolor=WHITE,
                             border=ft.border.all(1.5, SOFT["p"][1]), alignment=ft.alignment.center),
                ft.Column([T(p["full_name"], 20, DARK, True),
                           ft.Row([pill(p["code"], DARK, WHITE),
                                   pill(p["status"], ACCENT if p["status"] == "جديد" else BLUE, WHITE)], spacing=8)],
                          spacing=6, expand=True)], spacing=16),
            facts], spacing=16),
            padding=16, border_radius=R_CARD, rtl=True, bgcolor=SOFT["p"][0], border=ft.border.all(1.2, SOFT["p"][1]))

        personal = card(ft.Column([
            sec("البيانات الشخصية", "badge"),
            info_row("phone", "رقم التواصل", p["phone"]), info_row("pin", "مكان السكن", p["residence"]),
            info_row("briefcase", "العمل", p["job"]),
            info_row("calendar", "تاريخ التسجيل", (p["created_at"] or "")[:10], last=True)], spacing=12))
        medical = card(ft.Column([
            sec("المعلومات الطبية", "heart_pulse"),
            info_row("droplet", "زمرة الدم", p["blood"], pill_color=DANGER if p["blood"] else None),
            info_row("heart_pulse", "الأمراض", p["diseases"]),
            info_row("alert", "الحساسية", p["allergies"]),
            info_row("note", "الأدوية الحالية", p["medications"]),
            info_row("stethoscope", "التشخيص", p["diagnosis"]),
            info_row("note", "ملاحظات", p["notes"], last=True)], spacing=12))
        allergy_ctrls = [card(ft.Row([tile("alert", TINT_R, "r", 36, 18, 11),
                                      ft.Column([T("حساسية", 12, DANGER, True), T(p["allergies"], 14, TEXT, True, selectable=True)],
                                                spacing=1, expand=True)], spacing=12), padding=12,
                              bgcolor=TINT_R, border=True)] if (p["allergies"] or "").strip() else []

        tw = int((width() - 32 - 32 - 20) / 3)

        def thumb(label, rel):
            if C.file_exists(rel):
                inner = img_ctl(rel, tw, tw)
                click = lambda e: image_screen(rel, back_here)
            else:
                inner = ft.Column([ic("image", 28, "m"), T("لا توجد", 11, MUTED)], spacing=2,
                                  alignment=ft.MainAxisAlignment.CENTER,
                                  horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                click = None
            return ft.Column([ft.Container(inner, width=tw, height=tw, border_radius=R_CTRL, bgcolor=FIELD_BG,
                                           clip_behavior=ft.ClipBehavior.ANTI_ALIAS, alignment=ft.alignment.center,
                                           border=ft.border.all(1, BORDER), on_click=click, ink=click is not None),
                              T(label, 12, DARK, True)], spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        photos = card(ft.Column([
            sec("الصور", "image"),
            ft.Row([thumb("قبل", p["photo_before"]), thumb("بعد", p["photo_after"]),
                    thumb("التحاليل", p["photo_lab"])], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            T("اضغط على أي صورة لعرضها بالحجم الكامل", 11, MUTED)], spacing=12))

        def open_attachment(a):
            path = C.ap(a["path"])
            if not os.path.exists(path):
                return toast("الملف غير موجود على الجهاز", DANGER)
            if C.is_image_name(a["name"]):
                return image_screen(a["path"], back_here)
            try:                       # PDF/Word/Excel…: يُفكّ تشفيره مؤقتاً ويُفتح عبر المتصفح (يُمحى عند القفل)
                open_url(C.share_attachment(a["path"], a["name"]))
                toast("يُفتح الملف في المتصفح…")
            except Exception as ex:
                toast(f"تعذر فتح الملف: {ex}", DANGER)

        def rename_att(a):
            nm = field("اسم المرفق", value=a["name"])
            err = T("", 12, DANGER, True)

            def go(e):
                try:
                    C.rename_attachment(a["id"], nm.value)
                except ValueError as ex:
                    err.value = str(ex)
                    return err.update()
                page.close(d)
                toast("تمت إعادة التسمية", OK)
                patient_screen(pid)
            d = dialog("إعادة تسمية المرفق", ft.Column([nm, err], tight=True, width=dlg_w(), rtl=True, spacing=10),
                       [dlg_btn("حفظ", go, "ok"), dlg_btn("إلغاء", lambda e: page.close(d))])

        def delete_att(a):
            def do():
                try:
                    C.delete_attachment(a["id"])
                except Exception as ex:
                    return toast(f"تعذّر الحذف: {ex}", DANGER)
                toast("تم حذف المرفق", OK)
                patient_screen(pid)
            ask_confirm("حذف المرفق", f"سيُحذف «{a['name']}» نهائياً من ملف المريض.", do, "حذف")

        att_ctrls = []
        if atts:
            rows = []
            for a in atts:
                is_img = C.is_image_name(a["name"])
                rows.append(ft.Container(ft.Row([
                    tile("image" if is_img else "file", MINT, "p", 36, 18, 11),
                    T(a["name"], 13, TEXT, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Container(ic("edit", 18, "m"), on_click=lambda e, a=a: rename_att(a), ink=True, border_radius=R_SM,
                                 padding=6, tooltip="إعادة تسمية"),
                    ft.Container(ic("x", 18, "r"), on_click=lambda e, a=a: delete_att(a), ink=True, border_radius=R_SM,
                                 padding=6, tooltip="حذف المرفق"),
                    ic("eye" if is_img else "download", 20, "p")], spacing=6),
                    on_click=lambda e, a=a: open_attachment(a), ink=True, border_radius=R_SM, padding=ft.padding.symmetric(vertical=10, horizontal=6)))
            att_ctrls = [card(ft.Column([sec("المرفقات", "paperclip")] + rows +
                                        [T("اضغط على المرفق لفتحه", 11, MUTED)], spacing=12))]

        def ev_photos(ev):
            """صورتا قبل/بعد للموعد + خيار إدراجهما في الملف المطبوع."""
            w, h = int((width() - 32 - 24 - 10) / 2), 112

            def slot(which, label):
                rel = ev[f"photo_{which}"]
                has = C.file_exists(rel)

                def choose(e=None):
                    def picked(paths):
                        try:
                            C.set_event_photo(ev["id"], which, paths[0])
                        except Exception as ex:
                            return toast(f"تعذر حفظ الصورة: {ex}", DANGER)
                        patient_screen(pid)
                    pick(picked)
                inner = (img_ctl(rel, w, h) if has else
                         ft.Column([ic("photo_add", 28, "p"), T("إضافة صورة", 11, MUTED)], spacing=2,
                                   alignment=ft.MainAxisAlignment.CENTER,
                                   horizontal_alignment=ft.CrossAxisAlignment.CENTER))
                box = ft.Container(inner, width=w, height=h, border_radius=R_CTRL, bgcolor=FIELD_BG,
                                   alignment=ft.alignment.center, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                                   border=ft.border.all(1.2, BORDER if has else BORDER_STRONG), ink=True,
                                   on_click=(lambda e: image_screen(rel, back_here)) if has else choose)
                def drop(e=None):
                    def do():
                        try:
                            C.clear_event_photo(ev["id"], which)
                        except Exception as ex:
                            return toast(f"تعذّر الحذف: {ex}", DANGER)
                        patient_screen(pid)
                    ask_confirm("حذف الصورة", "ستُحذف صورة هذا الموعد نهائياً.", do, "حذف")
                change = (ft.Row([ft.Container(T("تغيير", 12, PRIMARY, True), on_click=choose, ink=True, border_radius=R_SM,
                                               padding=ft.padding.symmetric(horizontal=6, vertical=2)),
                                  ft.Container(T("حذف", 12, DANGER, True), on_click=drop, ink=True, border_radius=R_SM,
                                               padding=ft.padding.symmetric(horizontal=6, vertical=2))], spacing=0)
                          if has else ft.Container())
                return ft.Column([box, ft.Row([T(label, 12, DARK, True), change], width=w,
                                              alignment=ft.MainAxisAlignment.SPACE_BETWEEN)], spacing=4)
            ctrls = [ft.Row([slot("before", "قبل"), slot("after", "بعد")], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)]
            if ev["photo_before"] or ev["photo_after"]:
                sw = ft.Switch(value=bool(ev["in_report"]), active_color=PRIMARY,
                               on_change=lambda e, i=ev["id"]: C.set_event_in_report(i, e.control.value))
                ctrls.append(ft.Row([T("إدراج قبل/بعد هذا الموعد في الملف المطبوع", 12, TEXT, True, expand=True), sw]))
            return ft.Column(ctrls, spacing=8)

        # السجل المؤكد
        done_evs = [v for v in evs if v["done"]]
        pend_evs = [v for v in evs if not v["done"] and not v["cancelled"]]
        canc_evs = [v for v in evs if not v["done"] and v["cancelled"]]
        hist = [sec("سجل العمليات والمراجعات", "calendar_check")]
        if not done_evs:
            hist.append(card(T("لا يوجد سجل مؤكد بعد", 13, MUTED), padding=16))
        for ev in sorted(done_evs, key=lambda z: z["done_at"] or ""):
            surg = ev["kind"] == "surgery"
            hist.append(card(ft.Column([ft.Row([
                tile("scissors" if surg else "stethoscope", TINT_R if surg else TINT_G,
                     "r" if surg else "g", 44, 22, 14),
                ft.Column([
                    ft.Row([T(KIND_AR[ev["kind"]], 14, TEXT, True), pill("منجزة", OK, size=11), ic("lock", 16, "m")],
                           spacing=8),
                    T(f"الموعد: {ev['date']} • {ev['time'] or C.DEFAULT_TIME}", 12, MUTED),
                    T("تم الإنجاز: " + (ev["done_at"] or "")[:16].replace("T", " "), 12, MUTED),
                    T(ev["notes"] or "بدون ملاحظات", 13, TEXT)], spacing=2, expand=True)], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START),
                ev_photos(ev),
                btn("حذف هذا السجل", "x", lambda e, v=ev: delete_ev(v), kind="outline", height=38)], spacing=12), padding=12))

        # المواعيد
        def add_event(kind):
            def cb(d, t):
                ed_ui, collect, _ = items_editor()
                date_s = d.strftime("%Y-%m-%d")
                warn = T("", 12, DANGER, True)
                st = {"ack": False}
                dur_ui, get_dur = duration_picker(C.DEFAULT_DURATION.get(kind, 30), lambda m: refresh())

                def refresh():
                    rows = C.event_conflicts(date_s, t, get_dur())
                    warn.value = conflict_text(rows) if rows else ""
                    st["ack"] = False
                    warn.update()

                def save(e):
                    items = collect()
                    if items is None:
                        return
                    rows = C.event_conflicts(date_s, t, get_dur())
                    if rows and not st["ack"]:                      # التعارض تحذير لا منع: يتطلب تأكيداً ثانياً
                        warn.value = conflict_text(rows) + "\nاضغط «حفظ الموعد» مرة أخرى للتأكيد رغم التعارض."
                        st["ack"] = True
                        return warn.update()
                    try:
                        C.create_event(pid, kind, date_s, t, items, duration=get_dur())
                    except Exception as ex:
                        return toast(f"تعذر حفظ الموعد: {ex}", DANGER)
                    page.close(dlg)
                    patient_screen(pid)
                warn.value = conflict_text(C.event_conflicts(date_s, t, get_dur())) if C.event_conflicts(date_s, t, get_dur()) else ""
                dlg = dialog(f"موعد {KIND_AR[kind]}",
                             ft.Column([T(f"{date_s}  •  {t}", 13, PRIMARY, True), dur_ui, warn,
                                        T("الإجراءات والتكلفة المستحقة (اختياري — يمكن تعديلها لاحقاً)", 12, MUTED),
                                        ed_ui], tight=True, width=dlg_w(), rtl=True, spacing=12),
                             [dlg_btn("حفظ الموعد", save, "ok"), dlg_btn("إلغاء", lambda e: page.close(dlg))])
            ask_datetime(cb)

        def edit_event(ev):
            """تعديل موعد قبل تأكيده: النوع والتاريخ والوقت والمدة والإجراءات وتكاليفها."""
            st = {"d": ev["date"], "t": ev["time"] or C.DEFAULT_TIME, "ack": False}
            when = T(f"{st['d']}  •  {st['t']}", 14, PRIMARY, True)
            kind_ui, get_kind = choice_group("نوع الموعد", ["عملية", "مراجعة"], KIND_AR[ev["kind"]], chip_w=110,
                                             allow_none=False)
            ed_ui, collect, _ = items_editor(C.ev_items(ev["id"]))
            err = T("", 12, DANGER, True)
            warn = T("", 12, DANGER, True)
            dur_ui, get_dur = duration_picker(ev_dur(ev), lambda m: refresh())

            def refresh():
                rows = C.event_conflicts(st["d"], st["t"], get_dur(), ev["id"])
                warn.value = conflict_text(rows) if rows else ""
                st["ack"] = False
                warn.update()

            def pick_when(e):
                def cb(d, t):
                    st.update(d=d.strftime("%Y-%m-%d"), t=t)
                    when.value = f"{st['d']}  •  {st['t']}"
                    when.update()
                    refresh()
                ask_datetime(cb, ev_dt(ev))

            def save(e):
                items = collect()
                if items is None:
                    return
                kind = {v: k for k, v in KIND_AR.items()}[get_kind() or KIND_AR[ev["kind"]]]
                rows = C.event_conflicts(st["d"], st["t"], get_dur(), ev["id"])
                if rows and not st["ack"]:
                    warn.value = conflict_text(rows) + "\nاضغط «حفظ التعديلات» مرة أخرى للتأكيد رغم التعارض."
                    st["ack"] = True
                    return warn.update()
                try:
                    C.update_event(ev["id"], kind, st["d"], st["t"], items, duration=get_dur())
                except ValueError as ex:
                    err.value = str(ex)
                    err.update()
                    return
                page.close(dlg)
                toast("تم تعديل الموعد", OK)
                patient_screen(pid)
            rows0 = C.event_conflicts(st["d"], st["t"], ev_dur(ev), ev["id"])
            warn.value = conflict_text(rows0) if rows0 else ""
            dlg = dialog("تعديل الموعد",
                         ft.Column([kind_ui, when, btn("تغيير التاريخ والوقت", "calendar_edit", pick_when, kind="soft", height=44),
                                    dur_ui, warn, T("الإجراءات والتكلفة المستحقة", 13, DARK, True), ed_ui, err],
                                   tight=True, width=dlg_w(), rtl=True, spacing=12),
                         [dlg_btn("حفظ التعديلات", save, "ok"), dlg_btn("إلغاء", lambda e: page.close(dlg))])

        def confirm(ev):
            notes = field("ملاحظات (اختياري)", multiline=True, min_lines=2)
            nxt = {"d": None, "t": None}
            nxt_lbl = T("", 13, PRIMARY, True)
            extra = []
            if ev["kind"] == "visit":
                def pick_next(e):
                    def cb(d, t):
                        nxt.update(d=d.strftime("%Y-%m-%d"), t=t)
                        nxt_lbl.value = f"المراجعة القادمة: {nxt['d']} • {t}"
                        nxt_lbl.update()
                    ask_datetime(cb)
                extra = [btn("تحديد موعد مراجعة جديد", "calendar_plus", pick_next, kind="soft", height=44), nxt_lbl]

            _, paid_before, _ = C.amounts(C.ev_fin(ev["id"]))
            ed_ui, collect, total = items_editor(C.ev_items(ev["id"]))
            pay_fs = {c: field(PAY_LBL[c], keyboard_type=ft.KeyboardType.NUMBER, hint_text="0") for c in C.CURS}
            pay_err = T("", 12, DANGER, True)

            def pay_all(e):
                tot = total()
                for c in C.CURS:
                    v = max(tot[c] - paid_before[c], 0)
                    pay_fs[c].value, pay_fs[c].error_text = (C.money(v) if v > 0 else ""), None
                    pay_fs[c].update()
                pay_err.value = ""
                pay_err.update()

            def do(e):
                items = collect()
                if items is None:
                    return
                pays, bad = read_pays(pay_fs)
                if bad:
                    return
                try:
                    C.confirm_event(ev["id"], notes.value.strip(), items, pays,
                                    (nxt["d"], nxt["t"]) if nxt["d"] else None)
                except ValueError as ex:
                    pay_err.value = str(ex)
                    pay_err.update()
                    return
                except Exception as ex:
                    return toast(f"تعذر التأكيد: {ex}", DANGER)
                page.close(dlg)
                toast("تم تأكيد الإنجاز وتسجيله في الملف", OK)
                patient_screen(pid)
            fin_ctrls = [T("الإجراءات والتكلفة المستحقة", 13, DARK, True), ed_ui]
            if any(paid_before.values()):
                fin_ctrls.append(T("مدفوع سابقاً: " + C.money_multi(paid_before), 12, OK, True))
            fin_ctrls += [T("المبلغ المدفوع الآن — اختر العملة بتعبئة حقلها، أو ادفع بالعملتين معاً", 12, MUTED)] + \
                list(pay_fs.values()) + [pay_err, btn("دفع المتبقي كاملاً", "coins", pay_all, kind="soft", height=40)]
            dlg = dialog(f"تأكيد إنجاز {KIND_AR[ev['kind']]}",
                         ft.Column([T("بعد التأكيد لا يمكن تعديل التاريخ.", 12, DANGER, True), notes] + fin_ctrls + extra,
                                   tight=True, width=dlg_w(), rtl=True, spacing=12),
                         [dlg_btn("تأكيد", do, "ok"), dlg_btn("إلغاء", lambda e: page.close(dlg))])

        def cancel_ev(ev):
            reason = field("سبب الإلغاء (اختياري)", multiline=True, min_lines=2)

            def do(e):
                try:
                    C.cancel_event(ev["id"], reason.value)
                except ValueError as ex:
                    page.close(dlg)
                    return toast(str(ex), DANGER)
                page.close(dlg)
                toast("تم إلغاء الموعد وبقي في السجل (يمكن استعادته)", OK)
                patient_screen(pid)
            dlg = dialog("إلغاء الموعد",
                         ft.Column([T(f"{KIND_AR[ev['kind']]} بتاريخ {ev['date']} • {ev['time'] or C.DEFAULT_TIME}", 14, TEXT, True),
                                    T("لن يظهر في المواعيد القريبة ولن يُحتسب في الإحصائيات أو المستحقات، ويبقى محفوظاً في سجل المريض.",
                                      12, MUTED),
                                    reason], tight=True, width=dlg_w(), rtl=True, spacing=12),
                         [dlg_btn("إلغاء الموعد", do, "danger"), dlg_btn("تراجع", lambda e: page.close(dlg))])

        def reinstate_ev(ev):
            try:
                C.reinstate_event(ev["id"])
            except ValueError as ex:
                return toast(str(ex), DANGER)
            toast("تمت استعادة الموعد", OK)
            patient_screen(pid)

        def delete_ev(ev):
            def do():
                try:
                    C.delete_event(ev["id"])
                except ValueError as ex:
                    return toast(str(ex), DANGER)
                except Exception as ex:
                    return toast(f"تعذّر الحذف: {ex}", DANGER)
                toast("تم حذف الموعد", OK)
                patient_screen(pid)
            ask_confirm("حذف الموعد نهائياً",
                        f"{KIND_AR[ev['kind']]} بتاريخ {ev['date']} • {ev['time'] or C.DEFAULT_TIME} — سيُحذف مع إجراءاته وصوره ولا يمكن استعادته. "
                        "للإبقاء على السجل استخدم «إلغاء الموعد» بدل الحذف.", do, "حذف نهائي")

        def no_show_ev(ev):
            reason = field("ملاحظة (اختياري)", multiline=True, min_lines=1)

            def do(e):
                try:
                    C.mark_no_show(ev["id"], reason.value)
                except ValueError as ex:
                    page.close(dlg)
                    return toast(str(ex), DANGER)
                page.close(dlg)
                toast("سُجّل «لم يحضر» وأُغلق الموعد (يمكن استعادته)", OK)
                patient_screen(pid)
            dlg = dialog("لم يحضر المريض",
                         ft.Column([T(f"{KIND_AR[ev['kind']]} بتاريخ {ev['date']} • {ev['time'] or C.DEFAULT_TIME}", 14, TEXT, True),
                                    T("يُغلق الموعد ولا يُحتسب في المستحقات أو المواعيد القريبة، ويبقى في السجل.", 12, MUTED),
                                    reason], tight=True, width=dlg_w(), rtl=True, spacing=12),
                         [dlg_btn("تسجيل «لم يحضر»", do, "danger"), dlg_btn("تراجع", lambda e: page.close(dlg))])

        def delete_patient_dlg(e=None):
            try:
                sm = C.patient_delete_summary(pid)
            except ValueError as ex:
                return toast(str(ex), DANGER)
            sure = ft.Switch(value=False, active_color=DANGER)
            err = T("", 12, DANGER, True)
            lines = [f"المواعيد: {sm['events']} (منجزة {sm['done']})", f"المرفقات: {sm['attachments']} • الصور: {sm['photos']}"]
            if any(sm["paid"].values()):
                lines.append("مدفوعات مسجّلة ستُحذف: " + C.money_multi(sm["paid"]))
            if any(v > 0 for v in sm["remaining"].values()):
                lines.append("متبقٍ عليه (سيضيع سجله): " + C.money_multi({k: max(v, 0) for k, v in sm["remaining"].items()}))

            def go(e2):
                if not sure.value:
                    err.value = "فعّل الخيار لتأكيد الحذف النهائي"
                    return err.update()
                try:
                    C.delete_patient(pid)
                except Exception as ex:
                    page.close(d)
                    return toast(f"تعذّر الحذف: {ex}", DANGER)
                page.close(d)
                toast("تم حذف المريض وكل بياناته", OK)
                app.home()
            d = dialog("حذف المريض نهائياً",
                       ft.Column([T(sm["name"] + " — " + sm["code"], 15, DARK, True),
                                  T("سيُحذف كل ما يخصه نهائياً، ولا يمكن التراجع إلا باستعادة نسخة احتياطية (تُؤخذ نسخة تلقائياً قبل الحذف إن لم تكن حديثة).",
                                    12, DANGER, True)] + [T(ln, 13, TEXT) for ln in lines] +
                                 [ft.Row([sure, T("أفهم أن الحذف نهائي", 13, TEXT, True, expand=True)]), err],
                                 tight=True, width=dlg_w(), rtl=True, spacing=10),
                       [dlg_btn("حذف نهائي", go, "danger"), dlg_btn("تراجع", lambda e2: page.close(d))])

        sched = [sec("المواعيد القادمة", "calendar")]
        if not pend_evs:
            sched.append(card(T("لا توجد مواعيد معلّقة", 13, MUTED), padding=16))
        for ev in pend_evs:
            start, end = C.ev_span(ev)
            late = start < datetime.now()
            surg = ev["kind"] == "surgery"
            cf = C.event_conflicts(ev["date"], ev["time"], ev_dur(ev), ev["id"])
            extra_btns = []
            if late:
                extra_btns.append(btn("لم يحضر", "user_clock", lambda e, v=ev: no_show_ev(v), kind="outline", height=40, expand=True))
            extra_btns.append(btn("إلغاء الموعد", "x", lambda e, v=ev: cancel_ev(v), kind="danger", height=40, expand=True))
            sched.append(card(ft.Column([
                ft.Row([tile("scissors" if surg else "stethoscope", TINT_R if surg else TINT_G,
                             "r" if surg else "g", 44, 22, 14),
                        ft.Column([T(KIND_AR[ev["kind"]], 14, TEXT, True),
                                   T(f"{ev['date']} • {start:%H:%M}–{end:%H:%M} ({dur_text(ev_dur(ev))})", 13,
                                     DANGER if late else MUTED, late)],
                                  spacing=0, expand=True),
                        pill(rel_label(ev_dt(ev)), DANGER if late else PRIMARY)], spacing=12),
                T(conflict_text(cf), 12, DANGER, True) if cf else ft.Container(),
                ev_photos(ev),
                ft.Row([btn("تعديل الموعد", "calendar_edit", lambda e, v=ev: edit_event(v), kind="soft", height=44, expand=True),
                        btn("تأكيد الإنجاز", "check", lambda e, v=ev: confirm(v), kind="ok", height=44, expand=True)],
                       spacing=12),
                ft.Row(extra_btns, spacing=12),
                ft.Container(T("حذف الموعد نهائياً", 12, DANGER, True), on_click=lambda e, v=ev: delete_ev(v), ink=True,
                             border_radius=R_SM, padding=ft.padding.symmetric(vertical=6, horizontal=10),
                             alignment=ft.alignment.center)], spacing=12), padding=12))
        sched.append(ft.Row([
            btn("موعد عملية", "scissors", lambda e: add_event("surgery"), kind="danger", expand=True),
            btn("موعد مراجعة", "stethoscope", lambda e: add_event("visit"), expand=True)], spacing=12))
        if canc_evs:
            sched.append(sec("مواعيد ملغاة / لم يحضر", "x"))
            for ev in canc_evs:
                ns = bool(ev["no_show"])
                sched.append(card(ft.Column([
                    ft.Row([tile("user_clock" if ns else "calendar", TINT_R if ns else MINT, "r" if ns else "m", 44, 22, 14),
                            ft.Column([T(KIND_AR[ev["kind"]], 14, MUTED, True),
                                       T(f"{ev['date']} • {ev['time'] or C.DEFAULT_TIME}", 12, MUTED)],
                                      spacing=0, expand=True),
                            pill("لم يحضر" if ns else "ملغى", DANGER if ns else MUTED, WHITE, 11)], spacing=12),
                    T((("ملاحظة: " if ns else "السبب: ") + ev["cancel_reason"]) if ev["cancel_reason"] else "بدون سبب مذكور", 12, MUTED),
                    T(("سُجّل في " if ns else "أُلغي في ") + (ev["cancelled_at"] or "")[:16].replace("T", " "), 11, MUTED),
                    ft.Row([btn("استعادة الموعد", "restore", lambda e, v=ev: reinstate_ev(v), kind="soft", height=40, expand=True),
                            btn("حذف", "x", lambda e, v=ev: delete_ev(v), kind="outline", height=40, expand=True)], spacing=12)],
                    spacing=8), padding=12))

        show("ملف المريض", [header] + allergy_ctrls + [personal, medical, photos] + att_ctrls + hist + sched + [
            ft.Row([btn("طباعة الملف", "printer", do_print, kind="outline", expand=True),
                    btn("تعديل البيانات", "edit", lambda e: patient_form(pid=pid), kind="outline", expand=True)],
                   spacing=12),
            btn("الملف المالي للمريض", "wallet", lambda e: app.financial_screen(pid, back_here), kind="soft"),
            btn("حذف المريض نهائياً", "x", delete_patient_dlg, kind="danger"),
            ft.Container(height=16)], back=app.home,
            actions=[icon_btn("printer", "d", do_print, tip="طباعة الملف"), icon_btn("edit", "d", lambda e: patient_form(pid=pid), tip="تعديل البيانات")])


    # ── تسجيل الشاشات/الأدوات ليستعملها غيرها عبر app ──
    app.image_screen = image_screen
    app.patient_form = patient_form
    app.search_screen = search_screen
    app.info_row = info_row
    app.patient_screen = patient_screen
    app.search_screen = search_screen
