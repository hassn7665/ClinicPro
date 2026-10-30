# -*- coding: utf-8 -*-
"""
ملف المريض — شاشة تجمّع أقساماً مستقلة (لا SQL: كل الوصول للبيانات عبر core):
  info.py          بطاقة المعلومات (الرأس، الحساسية، البيانات الشخصية والطبية)
  attachments.py   الصور والمرفقات وصور قبل/بعد للمواعيد
  appointments.py  السجل المؤكد، المواعيد القادمة، الملغاة، وحوارات الإضافة/التعديل/الإلغاء/الحذف
  confirm.py       تأكيد إنجاز الموعد وحذف المريض
"""
import flet as ft

import core as C
from theme import DANGER
from gui.screens.patient.appointments import history_section, schedule_section
from gui.screens.patient.attachments import attachments_section
from gui.screens.patient.confirm import delete_patient_dialog
from gui.screens.patient.context import PatientCtx
from gui.screens.patient.info import info_section


def install(app):
    def patient_screen(pid):
        app.ui["img_left"] = 6
        ctx = PatientCtx(app, pid)
        if not ctx.p:
            return app.s.home()

        def do_print(e):
            try:
                app.open_url(C.build_report(pid))
                app.toast("يُفتح التقرير في المتصفح — اضغط «طباعة / حفظ PDF»")
            except Exception as ex:                      # حدّ الواجهة: نسجّل ونُبلغ
                C.LOG.log_exc("build_report", ex)
                app.toast(f"تعذر إنشاء التقرير: {ex}", DANGER)
        edit = lambda e: app.s.patient_form(pid=pid)
        btn = app.btn
        app.show("ملف المريض",
                 info_section(ctx) + attachments_section(ctx) + history_section(ctx) + schedule_section(ctx) + [
                     ft.Row([btn("طباعة الملف", "printer", do_print, kind="outline", expand=True),
                             btn("تعديل البيانات", "edit", edit, kind="outline", expand=True)], spacing=12),
                     btn("الملف المالي للمريض", "wallet", lambda e: app.s.financial_screen(pid, ctx.reload), kind="soft"),
                     btn("حذف المريض نهائياً", "x", lambda e: delete_patient_dialog(ctx), kind="danger"),
                     ft.Container(height=16)],
                 back=app.s.home,
                 actions=[app.icon_btn("printer", "d", do_print, tip="طباعة الملف"),
                          app.icon_btn("edit", "d", edit, tip="تعديل البيانات")])

    app.register(patient_screen=patient_screen)
