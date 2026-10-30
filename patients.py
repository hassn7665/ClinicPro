# -*- coding: utf-8 -*-
"""
patients.py — المرضى: البحث ومنع التكرار والحفظ والحذف، المرفقات والصور، وتاريخ الميلاد/العمر.
"""
import os
import shutil
import time
from datetime import datetime

import applog as LOG
import schema as SC

from backup import ensure_recent_backup
from db import _persist, db, q, x
from finance import fin_totals, zero
from storage import PAT_DIR, _DIGITS, _wipe_file, _wipe_rel, digits, norm, phone_key, safe, store_file


class DuplicatePatient(ValueError):
    """مريض مشابه موجود. .matches = قائمة {id, code, full_name, phone, age, reason: 'name'|'phone'}."""

    def __init__(self, matches):
        super().__init__("يوجد مريض مشابه")
        self.matches = matches


UNNAMED = "بدون اسم"                     # الاسم اختياري: المريض بلا اسم يُحفظ بهذا الاسم ويتميّز بكوده ورقم هاتفه
SORTS = ("alpha", "newest", "oldest")   # أبجدي، الأحدث تسجيلاً أولاً، الأقدم أولاً


def _sorted(rows, sort):
    """ترتيب المرضى: أبجدي بالاسم المطبَّع (الهمزات والتشكيل لا تفرّق)، أو زمني بتاريخ التسجيل (والرقم عند التساوي)."""
    if sort not in SORTS:
        raise ValueError("ترتيب غير معروف")
    if sort == "alpha":
        return sorted(rows, key=lambda r: (norm(r["full_name"]), r["id"]))
    return sorted(rows, key=lambda r: ((r["created_at"] or ""), r["id"]), reverse=(sort == "newest"))


def search_patients(term, limit=50, sort="alpha"):
    """بحث بالاسم (مطبَّع) أو الكود أو **رقم الهاتف** (جزء من الرقم، 3 أرقام فأكثر، يتجاهل الصفر البادئ ورمز الدولة)."""
    t, td = norm(term), digits(term)
    if not t and not td:
        return []
    tz = td.lstrip("0")
    out = []
    for r in q("SELECT id, code, full_name, status, phone, birth_date, created_at FROM patients"):
        hit = bool(t) and (t in norm(r["full_name"]) or t in (r["code"] or "").lower())
        if not hit and len(td) >= 3:
            pd = digits(r["phone"])
            hit = td in pd or (len(tz) >= 3 and tz in pd)
        if hit:
            out.append(r)
    return _sorted(out, sort)[:limit]


def list_patients(sort="alpha", offset=0, limit=30):
    """تصفّح كل المرضى بالترتيب المطلوب (صفحات): يعيد (الصفوف, الإجمالي)."""
    rows = _sorted(q("SELECT id, code, full_name, status, phone, birth_date, created_at FROM patients"), sort)
    return rows[offset:offset + limit], len(rows)


def patient_age(p, today=None):
    """عمر المريض الحالي (يُحسب من تاريخ الميلاد فلا يتقادم)، أو None."""
    return SC.age_on(p["birth_date"], today)


def resolve_birth(birth_text=None, age=None, current=None):
    """يحدد تاريخ الميلاد المخزَّن من مدخلات النموذج:
       • تاريخ ميلاد مكتوب (YYYY-MM-DD أو سنة YYYY) له الأولوية؛
       • وإلا إن كُتب عمر: إن طابق عمر التاريخ المخزَّن حالياً أبقيناه كما هو (لا نستبدل يوماً دقيقاً بسنة تقريبية)،
         وإلا نخزّن سنة الميلاد التقريبية (السنة الحالية − العمر)؛
       • وإلا None. يرفع ValueError برسالة عربية لمدخل غير معقول."""
    today = datetime.now().date()
    bt = (birth_text or "").strip().translate(_DIGITS)
    if bt:
        if len(bt) == 4 and bt.isdigit():
            bd = bt
        else:
            bd = SC.canon_date(bt) if len(bt) >= 8 else None
            if bd is None:
                raise ValueError("تاريخ الميلاد يُكتب هكذا: 1990-05-23 (أو السنة فقط 1990)")
        y = SC.birth_year(bd)
        if y > today.year or (len(bd) == 10 and bd > today.isoformat()):
            raise ValueError("تاريخ الميلاد في المستقبل")
        if today.year - y > 150:
            raise ValueError("تاريخ ميلاد غير معقول")
        return bd
    if age is None or age == "":
        return None
    age = int(age)
    if not 0 <= age <= 150:
        raise ValueError("عمر غير صحيح")
    if current and SC.age_on(current) == age:
        return current
    return str(today.year - age)


def find_duplicates(name, phone, age=None, exclude_id=None):
    """مرضى يحتمل أنهم الشخص نفسه:
       • reason='name'  : الاسم نفسه (مطبَّعاً) مع تطابق الهاتف أو غيابه أو تقارب العمر (±2)
       • reason='phone' : الهاتف نفسه باسم مختلف (قد يكونون من العائلة) — يُنبَّه فقط."""
    nn, pk = norm(name), phone_key(phone)
    out = []
    for r in q("SELECT id, code, full_name, phone, birth_date FROM patients"):
        if exclude_id and r["id"] == exclude_id:
            continue
        rk = phone_key(r["phone"])
        same_phone = len(pk) >= 7 and pk == rk
        r_age = patient_age(r)
        if nn and norm(r["full_name"]) == nn and (same_phone or not pk or not rk or age is None or r_age is None
                                                   or abs(int(age) - r_age) <= 2):
            out.append(dict(r, age=r_age, reason="name"))
        elif same_phone:
            out.append(dict(r, age=r_age, reason="phone"))
    return out


def save_patient(f, photos, atts, pid=None, allow_duplicate=False):
    """يحفظ المريض وصوره ومرفقاته في **معاملة واحدة** وبحفظ واحد للقاعدة المشفّرة.
    الفشل في أي خطوة يُرجع كل شيء (لا مريض بكود فارغ ولا ملفات يتيمة)، والصور القديمة المستبدَلة لا تُمحى
    إلا بعد نجاح الحفظ."""
    raw_name = (f.get("full_name") or "").strip()          # الاسم اختياري؛ الفراغ يُحفظ UNNAMED ولا يُعدّ تطابقاً مع غيره
    f = dict(f, full_name=raw_name or UNNAMED)
    cur_bd = q("SELECT birth_date FROM patients WHERE id=?", (pid,), one=True) if pid else None
    f = dict(f, birth_date=resolve_birth(f.get("birth_date"), f.get("age"), cur_bd["birth_date"] if cur_bd else None))
    f_age = SC.age_on(f["birth_date"])
    if not allow_duplicate:                           # منع التكرار: عند مريض جديد أو تغيير الاسم/الهاتف فقط
        cur = q("SELECT full_name, phone FROM patients WHERE id=?", (pid,), one=True) if pid else None
        if cur is None or norm(cur["full_name"]) != norm(f["full_name"]) or phone_key(cur["phone"]) != phone_key(f.get("phone")):
            dups = find_duplicates(raw_name, f.get("phone"), f_age, pid)
            if dups:
                raise DuplicatePatient(dups)
    now = datetime.now().isoformat(timespec="seconds")
    new_rels, old_rels, committed = [], [], False
    c = db()                                          # يمسك القفل حتى النهاية
    try:
        if pid is None:
            pid = c.execute("INSERT INTO patients(code,full_name,status,created_at,updated_at) VALUES('',?,?,?,?)",
                            (f["full_name"], f["status"], now, now)).lastrowid
            code = f"PT-{pid:05d}"
            c.execute("UPDATE patients SET code=?, folder=? WHERE id=?", (code, code, pid))
        c.execute("""UPDATE patients SET full_name=?, gender=?, birth_date=?, residence=?, phone=?, job=?,
             diseases=?, notes=?, blood=?, status=?, allergies=?, medications=?, diagnosis=?, updated_at=?
             WHERE id=?""",
                  (f["full_name"], f["gender"], f["birth_date"], f["residence"], f["phone"], f["job"],
                   f["diseases"], f["notes"], f["blood"], f["status"], f.get("allergies") or "",
                   f.get("medications") or "", f.get("diagnosis") or "", now, pid))
        p = c.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
        for key, src in photos.items():
            if key not in ("photo_before", "photo_after", "photo_lab"):   # حماية: أسماء الأعمدة من قائمة ثابتة فقط
                continue
            if src and os.path.exists(src):
                rel = store_file(p, src, key.replace("photo_", ""))
                new_rels.append(rel)
                c.execute(f"UPDATE patients SET {key}=? WHERE id=?", (rel, pid))
                if p[key] and p[key] != rel:
                    old_rels.append(p[key])
        for i, src in enumerate(atts):
            if os.path.exists(src):
                rel = store_file(p, src, f"att_{int(time.time() * 1000)}_{i}")
                new_rels.append(rel)
                c.execute("INSERT INTO attachments(patient_id,path,name) VALUES(?,?,?)",
                          (pid, rel, os.path.basename(src)))
        c.commit_mem()
        committed = True
        _persist()
        for rel in old_rels:                          # بعد نجاح الحفظ فقط
            _wipe_rel(rel)
        return c.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()
    except BaseException as ex:
        if not committed:                             # لم يُثبَّت شيء: نُرجع القاعدة ونمحو الملفات الجديدة
            c.rollback()
            for rel in new_rels:
                _wipe_rel(rel)
        LOG.log_exc("save_patient", ex, committed=committed)
        raise
    finally:
        c.close()


def fin_patients(term: str, limit=50):
    """بحث مالي عن مريض بالاسم أو الكود، مع إجمالي المستحق والمدفوع والمتبقي لكل عملة."""
    out = []
    for r in search_patients(term, limit):
        due, paid, rem = fin_totals(r["id"])
        out.append(dict(id=r["id"], code=r["code"], full_name=r["full_name"], due=due, paid=paid, rem=rem))
    return out


def patient_delete_summary(pid):
    """ما سيُحذف مع المريض (لحوار التأكيد)."""
    p = q("SELECT * FROM patients WHERE id=?", (pid,), one=True)
    if not p:
        raise ValueError("المريض غير موجود")
    evs = q("SELECT id, status FROM events WHERE patient_id=?", (pid,))
    paid = zero()
    for r in q("""SELECT pm.amount, pm.cur FROM payments pm JOIN events e ON e.id=pm.event_id WHERE e.patient_id=?""", (pid,)):
        paid[r["cur"]] += r["amount"]
    due, _, rem = fin_totals(pid)
    photos = sum(1 for k in ("photo_before", "photo_after", "photo_lab") if p[k]) + \
        q("SELECT COUNT(*) FROM events WHERE patient_id=? AND photo_before IS NOT NULL", (pid,), one=True)[0] + \
        q("SELECT COUNT(*) FROM events WHERE patient_id=? AND photo_after IS NOT NULL", (pid,), one=True)[0]
    return dict(name=p["full_name"], code=p["code"], events=len(evs), done=sum(1 for e in evs if e["status"] == "done"),
                attachments=q("SELECT COUNT(*) FROM attachments WHERE patient_id=?", (pid,), one=True)[0],
                photos=photos, paid=paid, remaining=rem)


def delete_patient(pid):
    """حذف نهائي للمريض وكل ما يخصه (مواعيد، إجراءات، دفعات، مرفقات، صور) بمعاملة واحدة، ثم محو الملفات بعد نجاح الحفظ.
    يأخذ نسخة احتياطية حديثة أولاً إن لم توجد."""
    p = q("SELECT * FROM patients WHERE id=?", (pid,), one=True)
    if not p:
        raise ValueError("المريض غير موجود")
    ensure_recent_backup()
    rels = {p[k] for k in ("photo_before", "photo_after", "photo_lab") if p[k]}
    rels |= {a["path"] for a in q("SELECT path FROM attachments WHERE patient_id=?", (pid,)) if a["path"]}
    for e in q("SELECT photo_before, photo_after FROM events WHERE patient_id=?", (pid,)):
        rels |= {e[k] for k in ("photo_before", "photo_after") if e[k]}
    code, committed = p["code"], False
    c = db()
    try:
        sub = "(SELECT id FROM events WHERE patient_id=?)"
        c.execute(f"DELETE FROM payments WHERE event_id IN {sub}", (pid,))
        c.execute(f"DELETE FROM event_items WHERE event_id IN {sub}", (pid,))
        c.execute("DELETE FROM events WHERE patient_id=?", (pid,))
        c.execute("DELETE FROM attachments WHERE patient_id=?", (pid,))
        c.execute("DELETE FROM patients WHERE id=?", (pid,))
        c.commit_mem()
        committed = True
        _persist()
    except BaseException as ex:
        if not committed:
            c.rollback()
        LOG.log_exc("delete_patient", ex, committed=committed)
        raise
    finally:
        c.close()
    for rel in rels:
        _wipe_rel(rel)
    folder = os.path.join(PAT_DIR, safe(code or ""))
    if code and os.path.isdir(folder):
        for fn in os.listdir(folder):
            _wipe_file(os.path.join(folder, fn))
        shutil.rmtree(folder, ignore_errors=True)
    LOG.log("patient_deleted", files=len(rels))


def delete_attachment(att_id):
    a = q("SELECT * FROM attachments WHERE id=?", (att_id,), one=True)
    if not a:
        raise ValueError("المرفق غير موجود")
    x("DELETE FROM attachments WHERE id=?", (att_id,))
    _wipe_rel(a["path"])                              # بعد نجاح الحذف من القاعدة


def rename_attachment(att_id, name):
    name = " ".join((name or "").replace("/", " ").replace("\\", " ").split())[:120]
    if not name:
        raise ValueError("اسم المرفق فارغ")
    old = q("SELECT name FROM attachments WHERE id=?", (att_id,), one=True)
    if not old:
        raise ValueError("المرفق غير موجود")
    if "." not in name and "." in (old["name"] or ""):          # نحافظ على الامتداد (يحدّد طريقة الفتح)
        name += "." + old["name"].rsplit(".", 1)[1]
    x("UPDATE attachments SET name=? WHERE id=?", (name, att_id))
    return name


def clear_patient_photo(pid, key):
    if key not in ("photo_before", "photo_after", "photo_lab"):
        raise ValueError("key")
    p = q("SELECT * FROM patients WHERE id=?", (pid,), one=True)
    if not p:
        raise ValueError("المريض غير موجود")
    x(f"UPDATE patients SET {key}=NULL WHERE id=?", (pid,))
    _wipe_rel(p[key])
