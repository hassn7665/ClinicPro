# -*- coding: utf-8 -*-
"""
نموذج إضافة/تعديل مريض — لا تحتوي أي SQL: كل الوصول للبيانات عبر core.
"""
import os

import flet as ft
import core as C

from theme import (PRIMARY, DARK, DANGER, OK, FIELD_BG, TEXT, MUTED, BORDER_STRONG, MINT, R_FIELD, R_CTRL, WHITE)
from gui.common import (BLOODS, ic, shadow)


def install(app):
    page = app.page
    ui = app.ui
    width = app.width
    img_ctl = app.img_ctl
    toast = app.toast
    T = app.T
    card = app.card
    btn = app.btn
    sec = app.sec
    field = app.field
    choice_group = app.choice_group
    show = app.show
    dlg_w = app.dlg_w
    dialog = app.dialog
    dlg_btn = app.dlg_btn
    ask_confirm = app.ask_confirm
    pick = app.pick
    def home(*a, **k):
        return app.s.home(*a, **k)
    def patient_screen(*a, **k):
        return app.s.patient_screen(*a, **k)

    def patient_form(status=None, pid=None):
        ui["img_left"] = 6
        p = C.get_patient(pid) if pid else None
        status = p["status"] if p else (status or "جديد")
        g = lambda k: (p[k] if p and p[k] is not None else "")

        status_ui, get_status = choice_group("حالة المريض", ["جديد", "قديم"], status, chip_w=110, allow_none=False)

        name = field("الاسم (اختياري)", value=g("full_name"))
        gender_ui, get_gender = choice_group("الجنس", ["ذكر", "أنثى"], g("gender") or None, chip_w=110)
        cur_age = C.patient_age(p) if p else None
        age = field("العمر", value="" if cur_age is None else str(cur_age), keyboard_type=ft.KeyboardType.NUMBER)
        birth = field("تاريخ الميلاد (اختياري) سنة-شهر-يوم", latin=True, hint_text="1990-05-23",
                      value=p["birth_date"] if p and p["birth_date"] and len(p["birth_date"]) == 10 else "")
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
            """خانة صورة: اللمس على الخانة لاختيار/تغيير الصورة، وزر دائري صغير (×) على زاويتها لحذفها (يظهر فقط مع وجود صورة)."""
            has = {"v": bool(p and p[key])}
            box = ft.Container(width=tw, height=tw, border_radius=R_CTRL, bgcolor=FIELD_BG, alignment=ft.alignment.center,
                               border=ft.border.all(1.5, BORDER_STRONG), clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                               content=ft.Column([ic("photo_add", 28, "p"), T("إضافة", 11, MUTED)],
                                                 alignment=ft.MainAxisAlignment.CENTER,
                                                 horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2))
            empty = box.content
            if has["v"]:
                box.content = img_ctl(p[key], tw, tw)
            badge = ft.Container(ic("x", 16, "r"), width=30, height=30, border_radius=15, bgcolor=WHITE, ink=True,
                                 alignment=ft.alignment.center, shadow=shadow(), tooltip="حذف الصورة", data=f"delphoto:{key}")
            badge.visible = has["v"]

            def picked(paths):
                photos[key] = paths[0]
                gone.discard(key)
                has["v"] = True
                box.content = ft.Image(src=paths[0], width=tw, height=tw, fit=ft.ImageFit.COVER)
                badge.visible = True
                box.update()
                badge.update()

            def remove(e):
                """يزيل الصورة المختارة حديثاً فوراً؛ والمحفوظة سابقاً تُحذف عند الحفظ (بعد تأكيد)."""
                def do():
                    photos.pop(key, None)
                    if p and p[key]:
                        gone.add(key)
                    has["v"] = False
                    box.content = empty
                    badge.visible = False
                    box.update()
                    badge.update()
                if p and p[key] and key not in gone and key not in photos:
                    ask_confirm("حذف الصورة", "ستُحذف الصورة نهائياً من ملف المريض عند حفظ التعديلات.", do, "حذف")
                else:
                    do()
            box.on_click = lambda e: pick(picked)
            badge.on_click = remove
            return ft.Column([ft.Stack([box, ft.Container(badge, top=6, right=6)], width=tw, height=tw),
                              T(label, 12, DARK, True, text_align=ft.TextAlign.CENTER)], spacing=6,
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
                          dlg_btn("الرئيسية", lambda e: (page.close(dlg), home()))])

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
            nm = name.value.strip()                          # الاسم اختياري (فراغه يُحفظ «بدون اسم») وأي عدد كلمات مقبول
            try:
                ag = int(age.value) if age.value.strip() else None
                if ag is not None and not 0 <= ag <= 130:
                    raise ValueError
            except ValueError:
                age.error_text = "عمر غير صحيح"
                age.update()
                return
            age.error_text = None
            try:                                           # تاريخ الميلاد يتقدّم على العمر؛ والعمر وحده يُخزَّن سنة تقريبية
                bd = C.resolve_birth(birth.value, ag, p["birth_date"] if p else None)
            except ValueError as ex:
                birth.error_text = str(ex)
                birth.update()
                return
            birth.error_text = None
            has = get_has()
            dis = "" if has is None else ("لا" if has == "لا" else
                                          ("نعم: " + dis_details.value.strip() if dis_details.value.strip() else "نعم"))
            data = dict(full_name=nm, gender=get_gender(), birth_date=bd, residence=residence.value.strip(),
                        phone=phone.value.strip(), job=job.value.strip(), diseases=dis,
                        notes=notes.value.strip(), blood=get_blood(), status=get_status() or "جديد",
                        allergies=allergies.value.strip(), medications=medications.value.strip(),
                        diagnosis=diagnosis.value.strip())
            save_flow(data)

        title = "تعديل البيانات" if pid else "إضافة مريض"
        show(title, [
            card(ft.Column([sec("البيانات الأساسية", "badge"), status_ui, name, gender_ui, age, birth, blood_ui], spacing=16)),
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
        ], back=(lambda: patient_screen(pid)) if pid else home)

    app.register(patient_form=patient_form)
