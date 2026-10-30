# -*- coding: utf-8 -*-
"""سياق شاشة ملف المريض: بيانات تُقرأ مرة واحدة وتُمرَّر لكل قسم (بلا SQL)."""
import core as C


class PatientCtx:
    def __init__(self, app, pid):
        self.app, self.pid = app, pid
        self.p = C.get_patient(pid)
        self.evs = C.patient_events(pid) if self.p else []
        self.atts = C.patient_attachments(pid) if self.p else []
        self.done = [v for v in self.evs if v["status"] == "done"]
        self.pending = [v for v in self.evs if v["status"] == "pending"]
        self.cancelled = [v for v in self.evs if v["status"] in ("cancelled", "no_show")]

    def reload(self):
        """إعادة رسم الشاشة بعد أي تعديل (وهي أيضاً وجهة «رجوع» من العارض والملف المالي)."""
        self.app.s.patient_screen(self.pid)
