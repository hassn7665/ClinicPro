# -*- coding: utf-8 -*-
"""
licensing.py — الترخيص: حالة الاشتراك والتفعيل بالأكواد الموقّعة وحماية التاريخ.
"""
import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta

import crypto_core as K
import license_core as LC

from storage import LIC_PATH, add_months, jload, jsave


# ───────────────────────── الترخيص ─────────────────────────
# سجل الحالة (license.json) موثَّق بـ HMAC مرتبط بمعرّف الجهاز لكشف العبث العابر. الأكواد نفسها موقّعة
# توقيعاً غير متماثل (لا يمكن تزويرها). وبما أن التطبيق يعمل دون اتصال، فالتحقق من التاريخ «جهد معقول»
# وليس حماية مطلقة ضد من يملك صلاحية جذر على الجهاز.
def _lic_mac(d) -> str:
    key = K.sha256(b"myclinic-lic-state", bytes.fromhex(d["device_id"]))
    msg = f'{d["device_id"]}|{d["last_serial"]}|{d.get("expires")}|{d["last_seen"]}|{d.get("plan", 0)}'.encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()[:20]


def _lic_save(d):
    d["v"] = 2
    d["mac"] = _lic_mac(d)
    jsave(LIC_PATH, d)


def lic_load():
    d = jload(LIC_PATH, None)
    if not isinstance(d, dict) or "device_id" not in d:
        if os.path.exists(LIC_PATH):                      # ملف تالف فعلاً (لا نتخلص منه بصمت): نحفظه للفحص
            try:
                os.replace(LIC_PATH, LIC_PATH + ".corrupt")
            except OSError:
                pass
        d = {"device_id": secrets.token_hex(4), "last_serial": 0, "expires": None,
             "last_seen": datetime.now().isoformat(), "plan": 0}
        _lic_save(d)
    return d


def lic_status():
    """يعيد (الحالة, الأيام المتبقية). الحالة: ok | none | expired | tampered (ملف الترخيص معدّل)
    | clock (تاريخ الجهاز أقدم من آخر استخدام مسجّل — يُفكّ بكود من المطوّر)"""
    d = lic_load()
    now = datetime.now()
    if d.get("v") != 2:          # ترخيص من إصدار قديم: يُرحَّل مرة واحدة بسقف 400 يوم
        d.setdefault("plan", 0)
        d["last_serial"] = 0     # الأكواد القديمة بصيغة مختلفة ولا تُقبل أصلاً، فيبدأ العدّ من جديد
        if d.get("expires") and datetime.fromisoformat(d["expires"]) > now + timedelta(days=400):
            d["expires"] = (now + timedelta(days=400)).isoformat()
        _lic_save(d)
    elif d.get("mac") != _lic_mac(d):
        return "tampered", 0
    seen = datetime.fromisoformat(d["last_seen"])
    if now < seen - timedelta(days=1):
        return "clock", 0
    if now - seen >= timedelta(minutes=10):          # لا نعيد كتابة الملف عند كل استدعاء (تقليل خطر التلف)
        d["last_seen"] = now.isoformat()
        _lic_save(d)
    if not d["expires"]:
        return "none", 0
    exp = datetime.fromisoformat(d["expires"])
    if now > exp:
        return "expired", 0
    return "ok", (exp - now).days


def lic_activate(code):
    """يعيد (نجاح, رسالة). يقبل كود اشتراك أو كود فك قفل التاريخ."""
    d = lic_load()
    st, _ = lic_status()
    try:
        serial, months, issued = LC.parse_code_ex(code, d["device_id"])
    except LC.LicenseError as ex:
        return False, str(ex)
    if serial <= d["last_serial"]:
        return False, "هذا الكود مستخدم سابقاً. اطلب كوداً جديداً."
    now = datetime.now()
    if months == LC.CLOCK_FIX and st != "clock":
        return False, ("لا يوجد قفل تاريخ على هذا الجهاز، لم يُستهلك الكود." if st != "tampered" else
                       "ملف الترخيص نفسه معدّل أو تالف: اطلب كود تفعيل جديداً.")
    if st == "clock":
        # تاريخ الإصدار داخل الكود موقّع من المطوّر = مرجع زمني حقيقي: لا نقبل الفك إن كان تاريخ الجهاز أقدم منه
        if now.date() < issued - timedelta(days=1):
            return False, "تاريخ هذا الجهاز أقدم من تاريخ إصدار الكود. صحّح تاريخ الجهاز والوقت ثم أعد المحاولة."
        d["last_seen"] = now.isoformat()
        if months == LC.CLOCK_FIX:
            d["last_serial"] = serial
            _lic_save(d)
            return True, "تم فك قفل التاريخ. تأكد أن تاريخ الجهاز صحيح."
    base = now
    if d.get("expires") and st in ("ok", "clock"):      # تجديد مبكر: تُضاف المدة إلى ما تبقى (إن لم ينتهِ)
        exp = datetime.fromisoformat(d["expires"])
        if exp > now:
            base = exp
    d.update(expires=add_months(base, months).isoformat(), last_serial=serial,
             last_seen=now.isoformat(), plan=months)
    _lic_save(d)
    return True, f"تم التفعيل ({LC.PLANS[months]}) — الترخيص ساري حتى {d['expires'][:10]}"
