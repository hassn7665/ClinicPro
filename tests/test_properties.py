# -*- coding: utf-8 -*-
"""
اختبارات الخصائص (hypothesis): بدل أمثلة مكتوبة يدوياً نصف **قوانين** يجب أن تصح لأي مدخل، ويبحث hypothesis عن مثال يكسرها:
  • المبالغ: الكتابة ثم القراءة تعيد القيمة نفسها، ولا انجراف عشري، والسالب مرفوض.
  • المال والحالات: أي تسلسل عمليات (إلغاء/استعادة/تأكيد/لم يحضر/دفع/تعديل إجراءات) يحفظ الثوابت ولا يكسر قيود القاعدة.
  • النسخ الاحتياطي: الذهاب والإياب يطابق، وأي اقتطاع أو تعديل بايت أو حذف/إعادة ترتيب سجل يُكتشف دائماً.
تشغيل: python tests/test_properties.py   (في CI: HYPOTHESIS_PROFILE=ci لنتائج قابلة لإعادة الإنتاج)
"""
import datetime as dt
import os
import sqlite3
import struct
import sys
import unittest

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import boot_core, make_account  # noqa: E402

settings.register_profile("ci", derandomize=True, deadline=None, print_blob=True,
                          suppress_health_check=list(HealthCheck))
settings.register_profile("dev", deadline=None, print_blob=True, suppress_health_check=list(HealthCheck))
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "dev"))

C, TMP = boot_core("props")
make_account(C)
import crypto_core as K  # noqa: E402

MAX_MINOR = 10 ** 14 - 1                      # أقل من سقف parse_money (10^12 وحدة رئيسية)


# ───────────────────────── المبالغ ─────────────────────────
class MoneyProperties(unittest.TestCase):
    @given(st.integers(0, MAX_MINOR))
    def test_format_then_parse_roundtrip(self, v):
        self.assertEqual(C.parse_money(C.money(v)), v)

    @given(st.integers(0, MAX_MINOR))
    def test_format_shape(self, v):
        s = C.money(v)
        major, _, frac = s.replace(",", "").partition(".")
        self.assertTrue(major.isdigit())
        self.assertIn(len(frac), (0, 2))                           # لا كسور عائمة ولا منزلة واحدة
        self.assertTrue(frac == "" or frac != "00")
        self.assertEqual(C.money(-v) if v else "0", ("-" + s) if v else "0")

    @given(st.integers(0, 10 ** 12 - 1), st.integers(0, 99))
    def test_decimal_text_is_exact(self, whole, cents):
        self.assertEqual(C.parse_money(f"{whole}.{cents:02d}"), whole * 100 + cents)

    @given(st.decimals(min_value=-50, max_value=50, places=2, allow_nan=False, allow_infinity=False))
    def test_sign_is_enforced_for_small_values(self, d):
        if d < 0:
            with self.assertRaises(ValueError):
                C.parse_money(str(d))
        else:
            self.assertEqual(C.parse_money(str(d)), int(d * 100))

    @given(st.lists(st.integers(0, 10 ** 9), max_size=60))
    def test_sums_have_no_drift(self, parts):
        txt = [C.money(p) for p in parts]
        self.assertEqual(sum(C.parse_money(t) for t in txt), sum(parts))

    @given(st.one_of(st.text(max_size=30), st.from_regex(r"[-+ ]?[0-9٠-٩,.٫]{1,14}( ?[eE][-+]?[0-9]{1,3})?", fullmatch=True)))
    def test_parse_never_returns_bad_values(self, s):
        try:
            v = C.parse_money(s)
        except ValueError:
            return
        self.assertIsInstance(v, int)
        self.assertGreaterEqual(v, 0)
        self.assertLessEqual(v, 10 ** 14)

    @given(st.one_of(st.floats(allow_nan=True), st.text(), st.booleans(), st.none()))
    def test_non_integers_rejected_by_minor(self, v):
        if isinstance(v, bool) or not isinstance(v, int):
            with self.assertRaises(TypeError):
                C.minor(v)


# ───────────────────────── المال وحالات الموعد ─────────────────────────
OPS = ["cancel", "reinstate", "confirm", "no_show", "pay", "del_pay", "edit_items"]
STATUSES = {"pending", "done", "cancelled", "no_show"}


class EventStateProperties(unittest.TestCase):
    counter = 0

    def _patient(self):
        EventStateProperties.counter += 1
        n = EventStateProperties.counter
        return C.save_patient(dict(full_name=f"خاصية {n}", gender="", residence="", phone="", job="", diseases="", notes="",
                                   blood="", status="جديد"), {}, [], allow_duplicate=True)["id"]

    def _invariants(self, pid, eid):
        row = C.q("SELECT * FROM events WHERE id=?", (eid,), one=True)
        self.assertIn(row["status"], STATUSES)
        items = {c: C.q("SELECT COALESCE(SUM(price),0) FROM event_items WHERE event_id=? AND cur=?", (eid, c), one=True)[0]
                 for c in C.CURS}
        paid = {c: C.q("SELECT COALESCE(SUM(amount),0) FROM payments WHERE event_id=? AND cur=?", (eid, c), one=True)[0]
                for c in C.CURS}
        for c in C.CURS:
            self.assertLessEqual(paid[c], items[c], "المدفوع لا يتجاوز تكلفة الإجراءات")
        inactive = row["status"] in ("cancelled", "no_show")
        if inactive:
            self.assertEqual(sum(paid.values()), 0, "موعد ملغى لا يحمل دفعات")
            self.assertIsNotNone(row["cancelled_at"])
        if row["status"] == "done":
            self.assertIsNotNone(row["done_at"])
        due, got, rem = C.fin_totals(pid)
        for c in C.CURS:
            self.assertEqual(due[c], 0 if inactive else items[c])
            self.assertEqual(got[c], paid[c])
            self.assertEqual(rem[c], due[c] - got[c])
            self.assertGreaterEqual(rem[c], 0)

    @settings(max_examples=60)
    @given(st.lists(st.tuples(st.sampled_from(OPS), st.integers(1, 300_000), st.sampled_from(["SYP", "USD"])), max_size=14),
           st.lists(st.tuples(st.integers(0, 400_000), st.sampled_from(["SYP", "USD"])), max_size=3))
    def test_any_operation_sequence_keeps_invariants(self, ops, items):
        pid = self._patient()
        eid = C.create_event(pid, "visit", (dt.date.today() - dt.timedelta(days=1)).isoformat(), "09:00",
                             items=[(f"إجراء {i}", p, cur) for i, (p, cur) in enumerate(items)])
        self._invariants(pid, eid)
        for op, amount, cur in ops:
            try:
                if op == "cancel":
                    C.cancel_event(eid, "سبب")
                elif op == "reinstate":
                    C.reinstate_event(eid)
                elif op == "confirm":
                    C.confirm_event(eid, "ok", None, ())
                elif op == "no_show":
                    C.mark_no_show(eid)
                elif op == "pay":
                    C.add_payments(eid, [(amount, cur)])
                elif op == "del_pay":
                    row = C.q("SELECT id FROM payments WHERE event_id=? LIMIT 1", (eid,), one=True)
                    if row:
                        C.delete_payment(row[0])
                elif op == "edit_items":
                    C.update_items(eid, [("بديل", amount, cur)])
            except ValueError:
                pass                                              # رفض مشروع برسالة؛ أي استثناء آخر (مثل IntegrityError) فشل
            self._invariants(pid, eid)

    @settings(max_examples=40)
    @given(st.integers(0, 10 ** 8), st.integers(0, 10 ** 8))
    def test_overpayment_always_rejected_exact_payment_accepted(self, price, extra):
        pid = self._patient()
        eid = C.create_event(pid, "visit", dt.date.today().isoformat(), "23:00", items=[("x", price, "SYP")])
        if price:
            with self.assertRaises(ValueError):
                C.add_payments(eid, [(price + extra + 1, "SYP")])
            C.add_payments(eid, [(price, "SYP")])
            self.assertEqual(C.amounts(C.ev_fin(eid))[2]["SYP"], 0)
            with self.assertRaises(ValueError):
                C.add_payments(eid, [(1, "SYP")])


# ───────────────────────── النسخ الاحتياطي ─────────────────────────
names = st.from_regex(r"patients/PT-\d{5}/[a-z0-9_]{1,12}\.bin", fullmatch=True)
blobs = st.binary(max_size=300)
records_st = st.lists(st.tuples(names, blobs), max_size=6, unique_by=lambda t: t[0])


def write_backup(records, tag):
    path = os.path.join(TMP, f"prop_{tag}_{os.urandom(4).hex()}.mcbk")
    with C._bk_open(path) as w:
        w.add("__db__", b"\x01db-bytes")
        for n, d in records:
            w.add(n, d)
    return path


def read_all(path):
    return list(C._bk_records(path, C.VAULT.dek))


def body_start(path):
    with open(path, "rb") as f:
        raw = f.read()
    return raw, 9 + struct.unpack(">I", raw[5:9])[0]


BAD = (ValueError, K.CryptoError, struct.error, UnicodeDecodeError)


class BackupProperties(unittest.TestCase):
    @settings(max_examples=60)
    @given(records_st)
    def test_roundtrip_is_identical_and_ordered(self, recs):
        path = write_backup(recs, "rt")
        self.assertEqual(read_all(path), [("__db__", b"\x01db-bytes")] + list(recs))

    @settings(max_examples=40)
    @given(records_st, st.data())
    def test_any_truncation_is_detected(self, recs, data):
        path = write_backup(recs, "cut")
        raw, start = body_start(path)
        cut = data.draw(st.integers(start, len(raw) - 1))          # أي نقطة قطع داخل الجسم (حتى قبل الختام بنقطة)
        with open(path, "wb") as f:
            f.write(raw[:cut])
        with self.assertRaises(BAD):
            read_all(path)

    @settings(max_examples=60)
    @given(records_st, st.data())
    def test_any_single_byte_flip_in_body_is_detected(self, recs, data):
        path = write_backup(recs, "flip")
        raw, start = body_start(path)
        i = data.draw(st.integers(start, len(raw) - 1))
        bit = data.draw(st.integers(0, 7))
        bad = bytearray(raw)
        bad[i] ^= 1 << bit
        with open(path, "wb") as f:
            f.write(bytes(bad))
        with self.assertRaises(BAD):
            read_all(path)

    @settings(max_examples=40)
    @given(st.lists(st.tuples(names, blobs), min_size=2, max_size=6, unique_by=lambda t: t[0]), st.data())
    def test_dropping_or_reordering_records_is_detected(self, recs, data):
        path = write_backup(recs, "ord")
        raw, start = body_start(path)
        offs, pos = [], start
        while pos < len(raw):
            ln = struct.unpack(">I", raw[pos:pos + 4])[0]
            offs.append(raw[pos:pos + 4 + ln])
            pos += 4 + ln
        body = offs[:-1]                                          # بلا السجل الختامي
        mode = data.draw(st.sampled_from(["drop", "swap", "dup"]))
        if mode == "drop":
            k = data.draw(st.integers(0, len(body) - 1))
            new = body[:k] + body[k + 1:] + offs[-1:]
        elif mode == "swap":
            i, j = data.draw(st.integers(0, len(body) - 1)), data.draw(st.integers(0, len(body) - 1))
            if i == j:
                return
            body[i], body[j] = body[j], body[i]
            new = body + offs[-1:]
        else:
            k = data.draw(st.integers(0, len(body) - 1))
            new = body[:k + 1] + [body[k]] + body[k + 1:] + offs[-1:]
        with open(path, "wb") as f:
            f.write(raw[:start] + b"".join(new))
        with self.assertRaises(BAD):
            read_all(path)


class RestoreProperties(unittest.TestCase):
    @settings(max_examples=6)
    @given(st.lists(st.tuples(st.text("أبتثجحخدذرزسشصضطظعغفقكلمنهوي ", min_size=3, max_size=14),
                              st.integers(0, 10 ** 7)), min_size=1, max_size=4, unique_by=lambda t: t[0].strip()))
    def test_backup_restore_roundtrip_preserves_data_and_money(self, rows):
        rows = [(n.strip() or "اسم", p) for n, p in rows]
        if len({n for n, _ in rows}) != len(rows):
            return
        pids = []
        for n, price in rows:
            pid = C.save_patient(dict(full_name=f"{n} {os.urandom(2).hex()}", gender="", residence="", phone="", job="",
                                      diseases="", notes="", blood="", status="جديد"), {}, [], allow_duplicate=True)["id"]
            C.create_event(pid, "visit", dt.date.today().isoformat(), "10:00", items=[("x", price, "SYP")])
            pids.append(pid)
        snap = lambda: (C.q("SELECT id, full_name, birth_date FROM patients ORDER BY id"),
                        C.q("SELECT event_id, price, cur FROM event_items ORDER BY id"))
        before = [[tuple(r) for r in part] for part in snap()]
        path = C.make_backup(prune=False)
        for pid in pids:
            C.delete_patient(pid)                                   # تخريب بعد النسخ
        C.restore_backup(path)
        self.assertEqual([[tuple(r) for r in part] for part in snap()], before)
        self.assertEqual(C.q("PRAGMA integrity_check", one=True)[0], "ok")
        self.assertEqual(sqlite3.sqlite_version_info >= (3, 26), True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
