# -*- coding: utf-8 -*-
"""
reports.py — التقارير: التقرير المطبوع للمريض، التقرير المالي، والإحصائيات.
"""
import html
import os
from datetime import datetime

import applog as LOG
import crypto_core as K
import theme as TH

from db import q
from finance import CURS, fin_file, money
from patients import patient_age
from share import new_share_dir, share_url
from storage import APP_NAME, KIND_AR, _sniff_ext, ap, is_image_name, read_file, today


# ───────────────────────── الإحصائيات ─────────────────────────
def stats(start: str | None = None, end: str | None = None) -> dict:
    """إحصائيات ضمن نطاق تواريخ YYYY-MM-DD (شامل). None = بلا حد."""
    lo, hi = start or "0000-01-01", end or "9999-12-31"
    one = lambda sql, a=(): q(sql, a, one=True)[0]
    return {
        "patients": one("SELECT COUNT(*) FROM patients WHERE substr(created_at,1,10) BETWEEN ? AND ?", (lo, hi)),
        "new": one("SELECT COUNT(*) FROM patients WHERE status='جديد' AND substr(created_at,1,10) BETWEEN ? AND ?", (lo, hi)),
        "old": one("SELECT COUNT(*) FROM patients WHERE status='قديم' AND substr(created_at,1,10) BETWEEN ? AND ?", (lo, hi)),
        "surgeries": one("SELECT COUNT(*) FROM events WHERE kind='surgery' AND status='done' AND substr(done_at,1,10) BETWEEN ? AND ?", (lo, hi)),
        "visits": one("SELECT COUNT(*) FROM events WHERE kind='visit' AND status='done' AND substr(done_at,1,10) BETWEEN ? AND ?", (lo, hi)),
        "pending": one("SELECT COUNT(*) FROM events WHERE status='pending' AND date BETWEEN ? AND ?", (lo, hi)),
        "cancelled": one("SELECT COUNT(*) FROM events WHERE status='cancelled' AND substr(cancelled_at,1,10) BETWEEN ? AND ?", (lo, hi)),
        "no_show": one("SELECT COUNT(*) FROM events WHERE status='no_show' AND date BETWEEN ? AND ?", (lo, hi)),
        "total_patients": one("SELECT COUNT(*) FROM patients"),
    }


# ───────────────────────── تقرير المريض للطباعة ─────────────────────────
def _css():
    return f""":root{{--p:{TH.PRIMARY};--d:{TH.DARK};--m:{TH.MUTED};--bg:{TH.BG}}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:{TH.TEXT};
font-family:"Noto Naskh Arabic","Segoe UI",Tahoma,Arial,sans-serif;line-height:1.7}}
.page{{max-width:800px;margin:0 auto;background:#fff;padding:26px 28px}}
.bar{{position:sticky;top:0;background:{TH.MINT};border-bottom:1px solid {TH.BORDER_STRONG};padding:10px;text-align:center}}
.bar button{{background:{TH.DEEP};color:#fff;border:0;border-radius:14px;padding:10px 26px;font-size:16px;font-weight:700}}
header{{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid {TH.BORDER_STRONG};padding-bottom:12px;margin-bottom:16px}}
header h1{{margin:0;color:var(--d);font-size:22px}} header small{{color:var(--m)}}
.head{{background:linear-gradient(135deg,{TH.tint(TH.PRIMARY,.2)},#F6FBFA);border:1px solid {TH.BORDER_STRONG};color:var(--d);border-radius:18px;padding:16px 18px;margin-bottom:16px}}
.head h2{{margin:0 0 6px;font-size:24px}} .tag{{display:inline-block;background:#fff;border:1px solid {TH.BORDER_STRONG};border-radius:20px;padding:2px 12px;margin-left:8px;font-size:13px}}
h3{{color:var(--d);border-right:5px solid var(--p);padding-right:10px;margin:20px 0 10px;font-size:17px}}
.grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px 18px}}
.f{{display:flex;justify-content:space-between;border-bottom:1px dashed {TH.BORDER_STRONG};padding:4px 0}} .f span{{color:var(--m)}}
.full{{grid-column:1/-1}}
.photos{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}}
figure{{margin:0;text-align:center}} .ph{{aspect-ratio:1;background:{TH.MINT};border-radius:10px;overflow:hidden;display:flex;align-items:center;justify-content:center;color:var(--m);font-size:12px}}
.ph img{{width:100%;height:100%;object-fit:cover}} figcaption{{font-size:12px;color:var(--m);margin-top:4px}}
table{{width:100%;border-collapse:collapse;font-size:14px}} th{{background:{TH.MINT};color:{TH.DEEP};padding:6px 8px;text-align:right}}
td{{border-bottom:1px solid {TH.DIVIDER};padding:6px 8px}}
footer{{margin-top:26px;color:var(--m);font-size:12px;text-align:center;border-top:1px solid {TH.DIVIDER};padding-top:8px}}
@media print{{body{{background:#fff}} .bar{{display:none}} .page{{padding:0;max-width:none}}
 .head,th{{-webkit-print-color-adjust:exact;print-color-adjust:exact}} h3,table,figure{{break-inside:avoid}}}}
.photos.two{{grid-template-columns:repeat(2,1fr)}} .pt{{font-weight:700;color:var(--d);margin:10px 0 6px}}
.sum{{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:6px}}
.box{{background:{TH.MINT};border-radius:12px;padding:10px;text-align:center}} .box span{{display:block;color:var(--m);font-size:13px}} .box b{{font-size:18px;color:var(--d)}}
ul.it{{margin:0;padding:0;list-style:none}} ul.it li{{display:flex;justify-content:space-between;gap:10px}}
td.n{{white-space:nowrap}} tfoot td{{font-weight:700;background:{TH.MINT}}} .neg{{color:{TH.DANGER};font-weight:700}} .pos{{color:{TH.OK};font-weight:700}}
"""


def build_report(pid):
    """ينشئ تقرير HTML (RTL، جاهز للطباعة) ويعيد رابطه المحلي."""
    p = q("SELECT * FROM patients WHERE id=?", (pid,), one=True)
    evs = q("SELECT * FROM events WHERE patient_id=? ORDER BY date,time", (pid,))
    atts = q("SELECT * FROM attachments WHERE patient_id=?", (pid,))
    folder, token = new_share_dir()
    e = lambda v: html.escape(str(v)) if v not in (None, "") else "—"

    def img(rel, name):
        if not rel or not os.path.exists(ap(rel)):
            return ""
        try:
            data = read_file(rel)
        except (OSError, K.CryptoError) as ex:            # صورة تالفة لا توقف التقرير؛ تُسجَّل وتُحذف منه
            LOG.log_exc("report_image", ex, file=os.path.basename(rel))
            return ""
        fn = f"{name}{_sniff_ext(data)}"
        with open(os.path.join(folder, fn), "wb") as f:      # نسخة مؤقتة للطباعة فقط (تُمحى تلقائياً)
            f.write(data)
        return fn

    photos = [("قبل", img(p["photo_before"], "before")), ("بعد", img(p["photo_after"], "after")),
              ("التحاليل", img(p["photo_lab"], "lab"))]
    photo_html = "".join(
        f'<figure><div class="ph">{"<img src=%s>" % fn if fn else "<span>لا توجد صورة</span>"}</div>'
        f'<figcaption>{cap}</figcaption></figure>' for cap, fn in photos)

    pairs_html = ""                      # صور قبل/بعد للمواعيد التي اختارها المستخدم للطباعة
    for ev in evs:
        if not ev["in_report"]:
            continue
        b = img(ev["photo_before"], f"ev{ev['id']}_b")
        a_ = img(ev["photo_after"], f"ev{ev['id']}_a")
        if not (b or a_):
            continue
        cell = lambda cap, fn: (f'<figure><div class="ph">{"<img src=%s>" % fn if fn else "<span>لا توجد صورة</span>"}'
                                f'</div><figcaption>{cap}</figcaption></figure>')
        pairs_html += (f'<div class="pt">{KIND_AR[ev["kind"]]} — {e(ev["date"])}</div>'
                       f'<div class="photos two">{cell("قبل", b)}{cell("بعد", a_)}</div>')

    att_imgs = ""
    att_files = ""
    for i, a in enumerate(atts):
        if is_image_name(a["name"]):
            fn = img(a["path"], f"att{i}")
            if fn:
                att_imgs += f'<figure><div class="ph"><img src="{fn}"></div><figcaption>{e(a["name"])}</figcaption></figure>'
        else:
            att_files += f"<li>{e(a['name'])}</li>"

    def ev_rows(done):
        rows = ""
        for ev in evs:
            if (ev["status"] == "done") != done or (not done and ev["status"] != "pending"):
                continue
            when = f"{ev['date']} {ev['time'] or ''}".strip()
            extra = f"<td>{e((ev['done_at'] or '')[:16].replace('T', ' '))}</td><td>{e(ev['notes'])}</td>" if done else ""
            rows += f"<tr><td>{KIND_AR[ev['kind']]}</td><td>{when}</td>{extra}</tr>"
        return rows

    done_rows, pend_rows = ev_rows(True), ev_rows(False)
    field = lambda label, val: f'<div class="f"><span>{label}</span><b>{e(val)}</b></div>'
    doc = f"""<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ملف المريض {e(p['full_name'])}</title>
<style>
{_css()}
</style></head><body>
<div class="bar"><button onclick="window.print()">🖨️ طباعة / حفظ PDF</button></div>
<div class="page">
<header><h1>{APP_NAME} — ملف مريض</h1><small>تاريخ الطباعة: {today()}</small></header>
<div class="head"><h2>{e(p['full_name'])}</h2><span class="tag">الكود: {e(p['code'])}</span><span class="tag">الحالة: {e(p['status'])}</span></div>
<h3>البيانات الشخصية</h3>
<div class="grid">{field('الجنس', p['gender'])}{field('العمر', patient_age(p))}{field('مكان السكن', p['residence'])}
{field('رقم التواصل', p['phone'])}{field('العمل', p['job'])}{field('زمرة الدم', p['blood'])}
<div class="f full"><span>الأمراض</span><b>{e(p['diseases'])}</b></div>
<div class="f full"><span>الحساسية</span><b>{e(p['allergies'])}</b></div>
<div class="f full"><span>الأدوية الحالية</span><b>{e(p['medications'])}</b></div>
<div class="f full"><span>التشخيص</span><b>{e(p['diagnosis'])}</b></div>
<div class="f full"><span>ملاحظات</span><b>{e(p['notes'])}</b></div>
{field('تاريخ التسجيل', (p['created_at'] or '')[:10])}</div>
<h3>الصور</h3><div class="photos">{photo_html}</div>
{('<h3>قبل وبعد</h3>' + pairs_html) if pairs_html else ''}
{('<h3>مرفقات مصوّرة</h3><div class="photos">' + att_imgs + '</div>') if att_imgs else ''}
{('<h3>ملفات مرفقة</h3><ul>' + att_files + '</ul>') if att_files else ''}
<h3>سجل العمليات والمراجعات المؤكدة</h3>
{('<table><tr><th>النوع</th><th>الموعد</th><th>تم الإنجاز</th><th>ملاحظات</th></tr>' + done_rows + '</table>') if done_rows else '<p>لا يوجد سجل مؤكد.</p>'}
{('<h3>المواعيد القادمة</h3><table><tr><th>النوع</th><th>الموعد</th></tr>' + pend_rows + '</table>') if pend_rows else ''}
<footer>تم إنشاء هذا التقرير بواسطة تطبيق {APP_NAME} — {datetime.now():%Y-%m-%d %H:%M}</footer>
</div></body></html>"""
    with open(os.path.join(folder, "report.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    return share_url(token, "report.html")


def build_fin_report(pid):
    """الملف المالي للمريض (تقرير منفصل عن ملف المريض): الإجراءات وتكاليفها والمدفوع والمتبقي بالعملتين."""
    p = q("SELECT * FROM patients WHERE id=?", (pid,), one=True)
    entries, tdue, tpaid, trem = fin_file(pid)
    folder, token = new_share_dir()
    e = lambda v: html.escape(str(v)) if v not in (None, "") else "—"
    lines = lambda d, neg=False: "<br>".join(money(d[c], c) for c in CURS if d[c] != 0) or "0"
    cls = lambda d: "neg" if any(v > 0 for v in d.values()) else "pos"
    rows = ""
    pay_rows = ""
    for en in sorted(entries, key=lambda z: (z["ev"]["date"], z["ev"]["time"] or "")):
        ev = en["ev"]
        items = "".join(f"<li><span>{e(i['name'])}</span><b>{money(i['price'], i['cur'])}</b></li>"
                        for i in en["items"]) or "—"
        when = f"{ev['date']} {ev['time'] or ''}".strip()
        rows += (f"<tr><td class='n'>{when}</td><td>{KIND_AR[ev['kind']]}</td><td><ul class='it'>{items}</ul></td>"
                 f"<td class='n'>{lines(en['due'])}</td><td class='n'>{lines(en['paid'])}</td>"
                 f"<td class='n {cls(en['rem'])}'>{lines(en['rem'])}</td></tr>")
        for pay in en["pays"]:
            pay_rows += (f"<tr><td class='n'>{e((pay['paid_at'] or '')[:10])}</td><td>{KIND_AR[ev['kind']]} — {ev['date']}</td>"
                         f"<td class='n'>{money(pay['amount'], pay['cur'])}</td><td>{e(pay['note'])}</td></tr>")
    box = lambda label, d, klass="": f'<div class="box"><span>{label}</span><b class="{klass}">{lines(d)}</b></div>'
    doc = f"""<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>الملف المالي {e(p['full_name'])}</title>
<style>{_css()}</style></head><body>
<div class="bar"><button onclick="window.print()">🖨️ طباعة / حفظ PDF</button></div>
<div class="page">
<header><h1>{APP_NAME} — الملف المالي</h1><small>تاريخ الطباعة: {today()}</small></header>
<div class="head"><h2>{e(p['full_name'])}</h2><span class="tag">الكود: {e(p['code'])}</span></div>
<div class="sum">{box('إجمالي المستحق', tdue)}{box('إجمالي المدفوع', tpaid)}{box('المتبقي', trem, cls(trem))}</div>
<h3>الإجراءات والتكاليف</h3>
{('<table><tr><th>الموعد</th><th>النوع</th><th>الإجراءات (التكلفة)</th><th>المستحق</th><th>المدفوع</th><th>المتبقي</th></tr>' + rows + f'<tfoot><tr><td colspan="3">الإجمالي</td><td class="n">{lines(tdue)}</td><td class="n">{lines(tpaid)}</td><td class="n">{lines(trem)}</td></tr></tfoot></table>') if rows else '<p>لا توجد مواعيد أو إجراءات مسجّلة.</p>'}
{('<h3>سجل الدفعات</h3><table><tr><th>التاريخ</th><th>الموعد</th><th>المبلغ</th><th>ملاحظة</th></tr>' + pay_rows + '</table>') if pay_rows else ''}
<footer>تم إنشاء هذا التقرير بواسطة تطبيق {APP_NAME} — {datetime.now():%Y-%m-%d %H:%M}</footer>
</div></body></html>"""
    with open(os.path.join(folder, "finance.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    return share_url(token, "finance.html")
