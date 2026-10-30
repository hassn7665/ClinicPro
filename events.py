# -*- coding: utf-8 -*-
"""
events.py — المواعيد: إنشاء/تعديل/تأكيد/إلغاء/لم يحضر، التعارضات، وجدول اليوم. الحالة عمود واحد status.
"""
import time
from contextlib import closing
from datetime import datetime, timedelta

import schema as SC

from backup import ensure_recent_backup
from db import _persist, db, q, x
from finance import _insert_payment, _write_items, amounts, ev_fin, ev_items
from storage import DEFAULT_DURATION, DEFAULT_TIME, KIND_AR, _wipe_rel, store_file


def ev_dt(ev) -> datetime:
    """تاريخ ووقت الموعد (الوقت الافتراضي 09:00 للمواعيد القديمة)."""
    t = ev["time"] or DEFAULT_TIME
    try:
        return datetime.strptime(f"{ev['date']} {t}", "%Y-%m-%d %H:%M")
    except ValueError:
        return datetime.strptime(ev["date"], "%Y-%m-%d")


def _ar_n(n, one, two, few, many):
    if n == 1:
        return f"بعد {one}"
    if n == 2:
        return f"بعد {two}"
    return f"بعد {n} {few}" if 3 <= n <= 10 else f"بعد {n} {many}"


def rel_label(dt: datetime) -> str:
    secs = (dt - datetime.now()).total_seconds()
    if secs < 0:
        return "متأخر"
    if secs < 3600:
        return _ar_n(max(1, int(secs // 60)), "دقيقة", "دقيقتين", "دقائق", "دقيقة")
    if secs < 86400:
        return _ar_n(int(secs // 3600), "ساعة", "ساعتين", "ساعات", "ساعة")
    return _ar_n(int(secs // 86400), "يوم", "يومين", "أيام", "يوماً")


def hm_to_12(hhmm):
    """'15:30' ← (3, 30, 'م'). 00:xx ← 12 ص، و12:xx ← 12 م."""
    h, m = (int(x) for x in (hhmm or DEFAULT_TIME).split(":")[:2])
    return (h % 12 or 12), m, ("ص" if h < 12 else "م")


def hm_from_12(hour12, minute, ampm):
    """(3, 30, 'م') ← '15:30'. ampm: 'ص' أو 'م'. يرفع ValueError لقيمة غير صالحة."""
    if not 1 <= int(hour12) <= 12 or not 0 <= int(minute) <= 59 or ampm not in ("ص", "م"):
        raise ValueError("وقت غير صالح")
    return f"{(int(hour12) % 12) + (12 if ampm == 'م' else 0):02d}:{int(minute):02d}"


def fmt12(hhmm):
    """عرض الوقت بنظام 12 ساعة مع ص/م لتفادي الخلط: '15:30' ← '03:30 م'."""
    h, m, ap_ = hm_to_12(hhmm)
    return f"{h:02d}:{m:02d} {ap_}"


def default_slot(days_ahead=0, hm=None, now=None):
    """موعد افتراضي مقترح (التاريخ, الوقت): أقرب نصف ساعة قادمة اليوم (بين 08:00 و21:00)، وإلا 09:00 صباحاً؛
    ومع days_ahead>0 يكون بعد هذا العدد من الأيام (الوقت hm أو 09:00)."""
    now = now or datetime.now()
    if days_ahead:
        return (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d"), hm or "09:00"
    t = now.replace(second=0, microsecond=0) + timedelta(minutes=30 - now.minute % 30)
    if t.date() != now.date() or t.hour >= 21:
        return (now + timedelta(days=1)).strftime("%Y-%m-%d"), "09:00"
    if t.hour < 8:
        return now.strftime("%Y-%m-%d"), "09:00"
    return t.strftime("%Y-%m-%d"), t.strftime("%H:%M")


def event_detail(event_id):
    """كل ما يلزم لعرض تفاصيل موعد: الصف + المريض + الإجراءات + الإجماليات. None إن لم يوجد."""
    ev = q("""SELECT e.*, p.full_name, p.code, p.phone FROM events e JOIN patients p ON p.id=e.patient_id
              WHERE e.id=?""", (event_id,), one=True)
    if ev is None:
        return None
    start, end = ev_span(ev)
    due, paid, rem = amounts(ev_fin(event_id))
    return dict(ev=ev, start=start, end=end, status=event_status(ev), items=ev_items(event_id),
                due=due, paid=paid, remaining=rem)


def upcoming_events(window_days):
    """(المتأخرة, القادمة خلال window_days×24 ساعة) للمواعيد غير المؤكدة."""
    now = datetime.now()
    limit = now + timedelta(days=window_days)
    rows = q("""SELECT e.*, p.full_name, p.code FROM events e
                JOIN patients p ON p.id=e.patient_id
                WHERE e.status='pending'""")
    late, soon = [], []
    for r in rows:
        dt = ev_dt(r)
        if dt < now:
            late.append((dt, r))
        elif dt <= limit:
            soon.append((dt, r))
    late.sort(key=lambda z: z[0])
    soon.sort(key=lambda z: z[0])
    return late, soon


def _check_when(date_s, time_s, duration):
    """يتحقق من التاريخ والوقت والمدة ويعيد المدة النهائية (دقائق)."""
    try:
        datetime.strptime(f"{date_s} {time_s or DEFAULT_TIME}", "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        raise ValueError("تاريخ أو وقت غير صحيح")
    d = int(duration)
    if not 5 <= d <= 720:
        raise ValueError("مدة الموعد يجب أن تكون بين 5 دقائق و12 ساعة")
    return d


def _canon_when(date_s, time_s):
    """(YYYY-MM-DD, HH:MM أو None) بالصيغة التي تفرضها قيود CHECK (يطبّع 2026-1-5 و9:05)."""
    d, t = SC.canon_date(date_s), SC.canon_time(time_s)
    if d is None or (time_s not in (None, "") and t is None):
        raise ValueError("تاريخ أو وقت غير صحيح")
    return d, t


def create_event(pid, kind, date_s, time_s, items=(), duration=None):
    if kind not in KIND_AR:
        raise ValueError("نوع غير معروف")
    dur = _check_when(date_s, time_s, duration or DEFAULT_DURATION.get(kind, 30))
    date_s, time_s = _canon_when(date_s, time_s)
    now = datetime.now().isoformat(timespec="seconds")
    with closing(db()) as c, c:
        eid = c.execute("INSERT INTO events(patient_id,kind,date,time,duration_min,created_at) VALUES(?,?,?,?,?,?)",
                        (pid, kind, date_s, time_s, dur, now)).lastrowid
        if items:
            _write_items(c, eid, items)
    return eid


def update_event(event_id, kind, date_s, time_s, items, duration=None):
    """تعديل موعد قبل تأكيده: النوع والتاريخ والوقت والمدة والإجراءات وتكاليفها."""
    if kind not in KIND_AR:
        raise ValueError("نوع غير معروف")
    cur_dur = q("SELECT duration_min FROM events WHERE id=?", (event_id,), one=True)
    dur = _check_when(date_s, time_s, duration or (cur_dur[0] if cur_dur and cur_dur[0] else DEFAULT_DURATION.get(kind, 30)))
    date_s, time_s = _canon_when(date_s, time_s)
    with closing(db()) as c, c:
        row = c.execute("SELECT status FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise ValueError("الموعد غير موجود")
        if row[0] == "done":
            raise ValueError("لا يمكن تعديل موعد مؤكَّد")
        if row[0] != "pending":
            raise ValueError("هذا الموعد ملغى — أعد تفعيله أولاً لتعديله")
        c.execute("UPDATE events SET kind=?, date=?, time=?, duration_min=? WHERE id=?",
                  (kind, date_s, time_s, dur, event_id))
        return _write_items(c, event_id, items)


def confirm_event(event_id, notes, items=None, pays=(), nxt=None):
    """تأكيد إنجاز موعد + (اختياري) تحديث الإجراءات + تسجيل المدفوع بالعملتين + موعد مراجعة قادم، بمعاملة واحدة."""
    now = datetime.now().isoformat(timespec="seconds")
    if nxt:
        nxt = _canon_when(nxt[0], nxt[1])
    with closing(db()) as c, c:
        row = c.execute("SELECT patient_id, status FROM events WHERE id=?", (event_id,)).fetchone()
        if not row:
            raise ValueError("الموعد غير موجود")
        if row[1] == "done":
            raise ValueError("تم تأكيد هذا الموعد سابقاً")
        if row[1] != "pending":
            raise ValueError("هذا الموعد ملغى — أعد تفعيله أولاً لتأكيده")
        c.execute("UPDATE events SET status='done', done_at=?, notes=? WHERE id=?", (now, notes, event_id))
        if items is not None:
            _write_items(c, event_id, items)
        for amount, cur in pays:
            _insert_payment(c, event_id, amount, cur, "عند التأكيد")
        if nxt:
            c.execute("INSERT INTO events(patient_id,kind,date,time,created_at) VALUES(?,?,?,?,?)",
                      (row[0], "visit", nxt[0], nxt[1], now))


def cancel_event(event_id, reason=""):
    """إلغاء موعد معلّق (لا يُحذف: يبقى في السجل بحالة «ملغى» ويمكن استعادته).
    يُرفض إن كان مؤكَّد الإنجاز أو مُلغى سابقاً أو عليه دفعات مسجّلة (لئلا تضيع أموال مستلمة)."""
    now = datetime.now().isoformat(timespec="seconds")
    with closing(db()) as c, c:
        row = c.execute("SELECT status FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise ValueError("الموعد غير موجود")
        if row[0] == "done":
            raise ValueError("لا يمكن إلغاء موعد مؤكَّد الإنجاز")
        if row[0] != "pending":
            raise ValueError("هذا الموعد ملغى سابقاً")
        if c.execute("SELECT 1 FROM payments WHERE event_id=? LIMIT 1", (event_id,)).fetchone():
            raise ValueError("على هذا الموعد دفعات مسجّلة. احذفها أو عدّلها أولاً من «الحسابات» ثم ألغِ الموعد.")
        c.execute("UPDATE events SET status='cancelled', cancelled_at=?, cancel_reason=? WHERE id=? AND status='pending'",
                  (now, (reason or "").strip(), event_id))


def reinstate_event(event_id):
    """استعادة موعد ملغى ليعود معلّقاً."""
    with closing(db()) as c, c:
        cur = c.execute("UPDATE events SET status='pending', cancelled_at=NULL, cancel_reason=NULL "
                        "WHERE id=? AND status IN ('cancelled','no_show')", (event_id,))
        if cur.rowcount == 0:
            raise ValueError("هذا الموعد ليس ملغى")


def set_event_photo(event_id, which, src):
    """صورة قبل/بعد لموعد محدد (تُحفظ في مجلد المريض وتحل محل السابقة)."""
    if which not in ("before", "after"):
        raise ValueError("which")
    ev = q("SELECT * FROM events WHERE id=?", (event_id,), one=True)
    p = q("SELECT * FROM patients WHERE id=?", (ev["patient_id"],), one=True)
    rel = store_file(p, src, f"ev{event_id}_{which}_{int(time.time())}")
    old = ev[f"photo_{which}"]
    try:
        x(f"UPDATE events SET photo_{which}=? WHERE id=?", (rel, event_id))
    except Exception:
        _wipe_rel(rel)                                # لا نترك الملف الجديد يتيماً إن فشل الحفظ
        raise
    if old and old != rel:
        _wipe_rel(old)
    return rel


# ───────────────────────── الجدول اليومي وكشف التعارض ─────────────────────────
def ev_span(ev):
    """(بداية, نهاية) موعد كـ datetime."""
    start = ev_dt(ev)
    dur = ev["duration_min"] if ev["duration_min"] else DEFAULT_DURATION.get(ev["kind"], 30)
    return start, start + timedelta(minutes=int(dur))


def event_conflicts(date_s, time_s, duration, exclude_id=None):
    """المواعيد الفعّالة (غير الملغاة/«لم يحضر») التي تتداخل مع [الوقت, الوقت+المدة] في اليوم نفسه."""
    start = datetime.strptime(f"{date_s} {time_s or DEFAULT_TIME}", "%Y-%m-%d %H:%M")
    end = start + timedelta(minutes=int(duration))
    out = []
    for r in q("""SELECT e.*, p.full_name FROM events e JOIN patients p ON p.id=e.patient_id
                  WHERE e.date=? AND e.status IN ('pending','done') AND e.id IS NOT ?""", (date_s, exclude_id)):
        s0, e0 = ev_span(r)
        if start < e0 and s0 < end:
            out.append(r)
    return out


def event_status(ev, now=None):
    """'done' | 'no_show' | 'cancelled' | 'late' (معلّق فات وقته) | 'pending'"""
    if ev["status"] != "pending":
        return ev["status"]
    return "late" if ev_dt(ev) < (now or datetime.now()) else "pending"


def day_schedule(date_s):
    """جدول يوم: قائمة مرتبة بالوقت من {ev, start, end, status, conflicts:[ids]}. التعارض بين المواعيد الفعّالة فقط."""
    rows = q("""SELECT e.*, p.full_name, p.code, p.phone FROM events e JOIN patients p ON p.id=e.patient_id
                WHERE e.date=?""", (date_s,))
    items = []
    for r in rows:
        s0, e0 = ev_span(r)
        items.append(dict(ev=r, start=s0, end=e0, status=event_status(r), conflicts=[]))
    items.sort(key=lambda z: (z["start"], z["ev"]["id"]))
    active = [i for i in items if i["status"] not in ("cancelled", "no_show")]
    for a in active:
        a["conflicts"] = [b["ev"]["id"] for b in active if b is not a and a["start"] < b["end"] and b["start"] < a["end"]]
    return items


def day_counts(first_date, days=7):
    """{تاريخ: عدد المواعيد الفعّالة} لشريط الأسبوع."""
    d0 = datetime.strptime(first_date, "%Y-%m-%d")
    dates = [(d0 + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    cnt = dict.fromkeys(dates, 0)
    for r in q("SELECT date, COUNT(*) FROM events WHERE date BETWEEN ? AND ? AND status IN ('pending','done') GROUP BY date",
               (dates[0], dates[-1])):
        cnt[r[0]] = r[1]
    return cnt


def mark_no_show(event_id, reason=""):
    """«لم يحضر»: يُغلق موعداً معلّقاً فات وقته. حالته no_show فلا يدخل المستحقات ولا المواعيد القريبة،
    ويمكن استعادته. يُرفض إن لم يحن وقته، أو كان مؤكَّداً، أو عليه دفعات."""
    now = datetime.now()
    with closing(db()) as c, c:
        row = c.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if row is None:
            raise ValueError("الموعد غير موجود")
        if row["status"] == "done":
            raise ValueError("لا يمكن تسجيل «لم يحضر» لموعد مؤكَّد الإنجاز")
        if row["status"] != "pending":
            raise ValueError("هذا الموعد ملغى أو مسجَّل «لم يحضر» سابقاً")
        if ev_dt(row) > now:
            raise ValueError("لم يحن وقت هذا الموعد بعد")
        if c.execute("SELECT 1 FROM payments WHERE event_id=? LIMIT 1", (event_id,)).fetchone():
            raise ValueError("على هذا الموعد دفعات مسجّلة. احذفها أو عدّلها أولاً من «الحسابات».")
        c.execute("UPDATE events SET status='no_show', cancelled_at=?, cancel_reason=? WHERE id=?",
                  (now.isoformat(timespec="seconds"), (reason or "").strip() or "لم يحضر", event_id))


def delete_event(event_id):
    """حذف موعد نهائياً (وإجراءاته وصوره). يُرفض إن كانت عليه دفعات (احذفها أولاً من «الحسابات»)."""
    ev = q("SELECT * FROM events WHERE id=?", (event_id,), one=True)
    if not ev:
        raise ValueError("الموعد غير موجود")
    if q("SELECT 1 FROM payments WHERE event_id=? LIMIT 1", (event_id,)):
        raise ValueError("على هذا الموعد دفعات مسجّلة. احذفها أولاً من «الحسابات» ثم احذف الموعد.")
    ensure_recent_backup()
    rels = [ev[k] for k in ("photo_before", "photo_after") if ev[k]]
    c = db()
    committed = False
    try:
        c.execute("DELETE FROM event_items WHERE event_id=?", (event_id,))
        c.execute("DELETE FROM events WHERE id=?", (event_id,))
        c.commit_mem()
        committed = True
        _persist()
    except BaseException:
        if not committed:
            c.rollback()
        raise
    finally:
        c.close()
    for rel in rels:
        _wipe_rel(rel)


def clear_event_photo(event_id, which):
    if which not in ("before", "after"):
        raise ValueError("which")
    ev = q("SELECT * FROM events WHERE id=?", (event_id,), one=True)
    if not ev:
        raise ValueError("الموعد غير موجود")
    x(f"UPDATE events SET photo_{which}=NULL WHERE id=?", (event_id,))
    _wipe_rel(ev[f"photo_{which}"])
