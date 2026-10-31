# -*- coding: utf-8 -*-
"""
finance.py — المال: تنسيق وتحليل المبالغ (أعداد صحيحة بأصغر وحدة)، إجراءات الموعد، الدفعات، والإحصاءات المالية.
"""
from contextlib import closing
from datetime import datetime

import schema as SC

from db import db, q, x
from storage import _DIGITS


# ───────────────────────── المالية والمواعيد ─────────────────────────
# عملتان مستقلتان (ليرة سورية / دولار): لكل إجراء ولكل دفعة عملتها، ولا يوجد تحويل بينهما.
CURS = ("SYP", "USD")


CUR_SYM = {"SYP": "ل.س", "USD": "$"}


CUR_NAME = {"SYP": "الليرة السورية", "USD": "الدولار"}


CUR_BI = {"SYP": "بالليرة السورية", "USD": "بالدولار"}


MINOR = SC.MINOR          # أصغر وحدة: كل المبالغ في القاعدة وفي هذا الملف أعداد صحيحة بها (1 ل.س أو 1 $ = 100)


def minor(v) -> int:
    """يتحقق أن المبلغ عدد صحيح بأصغر وحدة. يرفض float/str/Decimal عمداً: وصولها يعني نداءً لم يُرحَّل (خطأ ×100 صامت)."""
    if isinstance(v, bool) or not isinstance(v, int):
        raise TypeError(f"المبلغ يجب أن يكون عدداً صحيحاً بأصغر وحدة (استعمل parse_money)، وصل: {type(v).__name__}")
    return v


def money(v, cur=None) -> str:
    """تنسيق مبلغ (عدد صحيح بأصغر وحدة)؛ مع رمز العملة إن مُرّرت cur ('SYP'/'USD')."""
    v = minor(v or 0)
    sign, v = ("-" if v < 0 else ""), abs(v)
    major, frac = divmod(v, MINOR)
    s = f"{sign}{major:,}" + (f".{frac:02d}" if frac else "")
    return f"{s} {CUR_SYM[cur]}" if cur else s


def group_amount_text(s) -> str:
    """نص مبلغ أثناء الكتابة ← نص بفواصل الآلاف (1234567 → 1,234,567). يقبل الأرقام العربية، ويُبقي أول فاصلة عشرية فقط
    وبحد أقصى منزلتين، ويتجاهل أي حرف آخر. لا يغيّر القيمة: parse_money يعيد القيمة نفسها من النص المنسَّق."""
    t = (s or "").translate(_DIGITS) if isinstance(s, str) else ""
    t = "".join(ch for ch in t.replace("٫", ".").replace(",", "") if ch.isdigit() or ch == ".")
    whole, dot, frac = t.partition(".")
    frac = frac.replace(".", "")[:2]
    whole = whole.lstrip("0") or ("0" if (dot or whole) else "")
    out = f"{int(whole):,}" if whole else ""
    return out + (("." + frac) if dot else "")


def money_multi(d, sep=" + ") -> str:
    """مبالغ بالعملتين في نص واحد (يُخفي العملة الصفرية)."""
    parts = [money(d.get(c), c) for c in CURS if (d.get(c) or 0) != 0]
    return sep.join(parts) if parts else "0"


def zero():
    return {c: 0 for c in CURS}


def parse_money(s) -> int:
    """نص من المستخدم ← عدد صحيح بأصغر وحدة. يقبل الأرقام العربية والفواصل.
    يرفع ValueError لقيمة فارغة/سالبة/غير رقمية. أكثر من منزلتين عشريتين تُقرَّب (نصف للأعلى)."""
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
    t = (s or "").translate(_DIGITS).replace(",", "").replace(" ", "").strip()
    try:
        v = Decimal(t)
    except InvalidOperation:
        raise ValueError("amount is not a number")
    if not v.is_finite() or not 0 <= v <= Decimal(10) ** 12:       # يرفض السالب و NaN و inf
        raise ValueError("amount out of range")
    return int((v * MINOR).quantize(Decimal(1), rounding=ROUND_HALF_UP))


_FIN = """SELECT e.*, p.full_name, p.code,
  COALESCE((SELECT SUM(price) FROM event_items WHERE event_id=e.id AND cur='SYP'),0) * (CASE WHEN e.status IN ('cancelled','no_show') THEN 0 ELSE 1 END) AS due_syp,
  COALESCE((SELECT SUM(price) FROM event_items WHERE event_id=e.id AND cur='USD'),0) * (CASE WHEN e.status IN ('cancelled','no_show') THEN 0 ELSE 1 END) AS due_usd,
  COALESCE((SELECT SUM(amount) FROM payments WHERE event_id=e.id AND cur='SYP'),0) AS paid_syp,
  COALESCE((SELECT SUM(amount) FROM payments WHERE event_id=e.id AND cur='USD'),0) AS paid_usd
  FROM events e JOIN patients p ON p.id=e.patient_id"""


def amounts(r):
    """(المستحق, المدفوع, المتبقي) لصف من _FIN، كلٌّ كقاموس {SYP, USD}."""
    due = {"SYP": r["due_syp"], "USD": r["due_usd"]}
    paid = {"SYP": r["paid_syp"], "USD": r["paid_usd"]}
    return due, paid, {c: due[c] - paid[c] for c in CURS}


def ev_fin(event_id):
    return q(_FIN + " WHERE e.id=?", (event_id,), one=True)


def ev_items(event_id):
    return q("SELECT * FROM event_items WHERE event_id=? ORDER BY id", (event_id,))


def ev_payments(event_id):
    return q("SELECT * FROM payments WHERE event_id=? ORDER BY id", (event_id,))


def _sum(c, table, col, event_id, cur):
    return c.execute(f"SELECT COALESCE(SUM({col}),0) FROM {table} WHERE event_id=? AND cur=?",
                     (event_id, cur)).fetchone()[0]


def _write_items(c, event_id, items):
    """يستبدل إجراءات الموعد (name, price, cur) ضمن معاملة المستدعي. يعيد الإجمالي لكل عملة."""
    clean = []
    for n, pr, cur in items:
        if cur not in CURS:
            raise ValueError("عملة غير معروفة")
        if minor(pr) < 0:
            raise ValueError("التكلفة لا يمكن أن تكون سالبة")
        clean.append(((n or "").strip() or "إجراء", pr, cur))
    totals = {cur: sum(pr for _, pr, k in clean if k == cur) for cur in CURS}
    for cur in CURS:
        paid = _sum(c, "payments", "amount", event_id, cur)
        if totals[cur] < paid:
            raise ValueError(f"التكلفة {CUR_BI[cur]} ({money(totals[cur], cur)}) "
                             f"أقل من المبلغ المدفوع ({money(paid, cur)})")
    c.execute("DELETE FROM event_items WHERE event_id=?", (event_id,))
    c.executemany("INSERT INTO event_items(event_id,name,price,cur) VALUES(?,?,?,?)",
                  [(event_id, n, pr, cur) for n, pr, cur in clean])
    return totals


def _check_pay(c, event_id, amount, cur, exclude=0):
    """يتحقق أن الدفعة لا تتجاوز المتبقي بنفس العملة (exclude = قيمة دفعة سابقة يجري تعديلها)."""
    if cur not in CURS:
        raise ValueError("عملة غير معروفة")
    minor(amount)
    if amount <= 0:
        raise ValueError("المبلغ يجب أن يكون أكبر من صفر")
    ev = c.execute("SELECT status FROM events WHERE id=?", (event_id,)).fetchone()
    if ev is None:
        raise ValueError("الموعد غير موجود")
    if ev[0] in ("cancelled", "no_show"):
        raise ValueError("هذا الموعد ملغى — أعد تفعيله أولاً لتسجيل دفعة")
    due = _sum(c, "event_items", "price", event_id, cur)
    remaining = due - (_sum(c, "payments", "amount", event_id, cur) - exclude)
    if amount > remaining:
        if due == 0:
            raise ValueError(f"لا يوجد مستحق {CUR_BI[cur]} على هذا الموعد — "
                             f"عدّل الإجراءات لتسعيرها بهذه العملة أولاً")
        raise ValueError(f"المبلغ أكبر من المتبقي {CUR_BI[cur]} ({money(max(remaining, 0), cur)})")


def _insert_payment(c, event_id, amount, cur, note=""):
    minor(amount)
    _check_pay(c, event_id, amount, cur)
    c.execute("INSERT INTO payments(event_id,amount,cur,paid_at,note) VALUES(?,?,?,?,?)",
              (event_id, amount, cur, datetime.now().isoformat(timespec="seconds"), note or ""))


def update_items(event_id, items):
    with closing(db()) as c, c:
        row = c.execute("SELECT status FROM events WHERE id=?", (event_id,)).fetchone()
        if row and row[0] in ("cancelled", "no_show"):
            raise ValueError("هذا الموعد ملغى — أعد تفعيله أولاً لتعديل إجراءاته")
        return _write_items(c, event_id, items)


def add_payments(event_id, pays, note=""):
    """تسجيل دفعة أو أكثر (amount, cur) — مثلاً بالعملتين معاً — بمعاملة واحدة."""
    if not pays:
        raise ValueError("أدخل مبلغاً مدفوعاً")
    with closing(db()) as c, c:
        for amount, cur in pays:
            _insert_payment(c, event_id, amount, cur, note)


def edit_payment(pay_id, amount, cur, note=None):
    minor(amount)
    with closing(db()) as c, c:
        row = c.execute("SELECT event_id, amount, cur FROM payments WHERE id=?", (pay_id,)).fetchone()
        if row is None:
            raise ValueError("الدفعة غير موجودة")
        _check_pay(c, row[0], amount, cur, exclude=row[1] if row[2] == cur else 0)
        if note is None:
            c.execute("UPDATE payments SET amount=?, cur=? WHERE id=?", (amount, cur, pay_id))
        else:
            c.execute("UPDATE payments SET amount=?, cur=?, note=? WHERE id=?", (amount, cur, note, pay_id))


def delete_payment(pay_id):
    x("DELETE FROM payments WHERE id=?", (pay_id,))


def fin_stats(lo=None, hi=None) -> dict:
    """إحصائية مالية بالعملتين ضمن [lo, hi].
    المدفوع  = الدفعات المستلمة فعلاً خلال الفترة (حسب تاريخ الدفع).
    المستحق  = المتبقي غير المسدّد على مواعيد الفترة (حسب تاريخ الموعد).  المسجّل = إجمالي تكلفة مواعيد الفترة."""
    lo_, hi_ = lo or "0000-01-01", hi or "9999-12-31"
    pays = q("""SELECT amount, cur, substr(paid_at,1,10) AS d FROM payments
                WHERE substr(paid_at,1,10) BETWEEN ? AND ? ORDER BY paid_at""", (lo_, hi_))
    evs = q(_FIN + " WHERE e.date BETWEEN ? AND ?", (lo_, hi_))
    by_month = True
    if lo and hi:
        by_month = (datetime.strptime(hi, "%Y-%m-%d") - datetime.strptime(lo, "%Y-%m-%d")).days > 92
    paid, groups = zero(), {}
    for r in pays:
        paid[r["cur"]] += r["amount"]
        g = groups.setdefault(r["d"][:7] if by_month else r["d"], dict(zero(), n=0))
        g[r["cur"]] += r["amount"]
        g["n"] += 1
    registered, outstanding, n_events = zero(), zero(), 0
    for r in evs:
        due, _, rem = amounts(r)
        if not any(due.values()):
            continue
        n_events += 1
        for c in CURS:
            registered[c] += due[c]
            outstanding[c] += max(rem[c], 0)
    rnd = dict
    return dict(paid=rnd(paid), registered=rnd(registered), outstanding=rnd(outstanding),
                n_pays=len(pays), n_events=n_events, by_month=by_month,
                groups=[(k, rnd({c: v for c, v in g.items() if c != "n"}) | {"n": g["n"]})
                        for k, g in sorted(groups.items(), reverse=True)])


def fin_totals(pid):
    """إجمالي المستحق والمدفوع والمتبقي لمريض، لكل عملة."""
    due, paid = zero(), zero()
    for r in q(_FIN + " WHERE e.patient_id=?", (pid,)):
        d, p_, _ = amounts(r)
        for c in CURS:
            due[c] += d[c]
            paid[c] += p_[c]
    return due, paid, {c: due[c] - paid[c] for c in CURS}


def fin_file(pid):
    """الملف المالي للمريض: [{ev, items, pays, due, paid, rem}], ثم إجمالي المستحق والمدفوع والمتبقي."""
    out = []
    for ev in q(_FIN + " WHERE e.patient_id=? ORDER BY e.date DESC, e.time DESC", (pid,)):
        due, paid, rem = amounts(ev)
        out.append(dict(ev=ev, items=ev_items(ev["id"]), pays=ev_payments(ev["id"]), due=due, paid=paid, rem=rem))
    return (out,) + fin_totals(pid)
