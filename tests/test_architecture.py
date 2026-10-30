# -*- coding: utf-8 -*-
"""
حراسة البنية بعد تقسيم core.py وملف المريض:
  • core.py واجهة توافق: كل اسم عام كان فيه ما زال موجوداً (لا ينكسر أي import قديم).
  • طبقات الوحدات لا تعتمد على ما فوقها (لا دورات استيراد).
  • دوال ملف المريض ≤ 80 سطراً، وكل وحدة منطق ≤ 650 سطراً.
  • لا `except Exception` صامت (pass/continue بلا تسجيل ولا رفع) في المنطق والواجهة.
"""
import ast
import glob
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import ROOT, boot_core  # noqa: E402

# الترتيب من الأدنى إلى الأعلى: الوحدة تستورد من الوحدات التي قبلها فقط
LAYERS = ["storage", "db", "finance", "backup", "events", "patients", "media", "licensing", "share", "accounts",
          "reports", "diagnostics"]

API = """
APP_NAME APP_VERSION BACKUP_EVERY_DAYS BASE BK_DIR BK_EXT CURS CUR_BI CUR_NAME CUR_SYM DB_ENC DB_MAGIC DB_PATH
DEFAULT_DURATION DEFAULT_TIME DURATIONS DuplicatePatient EXPORT_REMIND_DAYS IMG IMG_EXT JOURNAL K KEEP_BACKUPS
KIND_AR LC LIC_PATH LOCK_CHOICES LOCK_DEFAULT LOG META_SCRUB_VER MINOR NotUnlocked OPT_MIN_BYTES PAT_DIR
RollbackError SC SET_PATH SHARE_DIR SHARE_TTL TH VAULT VT VaultError _BK_END _BK_FMT _BK_MAGIC _BK_MAX_REC
_DIGITS _FIN _Handle _Handler _OPAQUE _all_image_rels _ar_n _atomic_write _bk_aad _bk_header _bk_key _bk_open
_bk_records _canon_when _check_pay _check_when _commit_then _css _db_decode _db_encode _faad _file_sig
_insert_payment _jlock _lic_mac _lic_save _lock _mem _migrate_all_legacy _migrate_file_aad
_migrate_legacy_backups _migrate_legacy_files _new_conn _persist _prune_backups _serialize _sniff_ext _srv
_startup_recovery _stop_server _sum _wipe_file _wipe_rel _write_items add_months add_payments amounts ap
auto_backup_if_due backup_needs_password backup_report build_fin_report build_report cancel_event
clear_event_photo clear_patient_photo close_db confirm_event create_event create_recovery_key day_counts
day_schedule db delete_attachment delete_event delete_patient delete_payment diagnostics digits edit_payment
ensure_recent_backup ev_dt ev_fin ev_items ev_payments ev_span event_conflicts event_status export_due
file_b64 file_size fin_file fin_patients fin_stats fin_totals find_duplicates get_patient images_to_optimize
init_db is_image_name jload jsave keys_ready lic_activate lic_load lic_status list_backups lock_app
lock_policy make_backup mark_exported mark_no_show minor module_mismatch money money_multi need_setup new_rel
new_share_dir norm open_db optimize_images parse_money patient_age patient_attachments patient_delete_summary
patient_events phone_key q read_file recover_interrupted_restore reinstate_event rel_label rename_attachment
reset_request_code reset_with_code reset_with_recovery_key resolve_birth restore_backup safe save_patient
scrub_metadata scrub_metadata_if_needed search_patients set_escrow set_event_in_report set_event_photo
set_lock_policy setup_account share_attachment share_file share_text share_url stats store_file thumb_b64
thumb_rel today unlock upcoming_events update_event update_items write_enc x zero
""".split()


def _src(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class FacadeTests(unittest.TestCase):
    def test_every_legacy_name_still_exported(self):
        C, _ = boot_core("facade")
        missing = [n for n in API if not hasattr(C, n)]
        self.assertEqual(missing, [])

    def test_facade_is_reexport_only(self):
        tree = ast.parse(_src(os.path.join(ROOT, "core.py")))
        defs = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        self.assertEqual(defs, [], "core.py يجب ألا يحوي منطقاً")


class LayerTests(unittest.TestCase):
    def test_no_upward_imports(self):
        for i, mod in enumerate(LAYERS):
            tree = ast.parse(_src(os.path.join(ROOT, f"{mod}.py")))
            for n in ast.walk(tree):
                if isinstance(n, ast.ImportFrom) and n.module in LAYERS:
                    self.assertLess(LAYERS.index(n.module), i, f"{mod}.py يستورد من وحدة أعلى منه: {n.module}")
                if isinstance(n, ast.ImportFrom) and n.module == "core":
                    self.fail(f"{mod}.py لا يجوز أن يستورد core (الواجهة تستورد منه، لا العكس)")

    def test_logic_modules_stay_small(self):
        for mod in LAYERS:
            n = _src(os.path.join(ROOT, f"{mod}.py")).count("\n")
            self.assertLessEqual(n, 650, f"{mod}.py صار {n} سطراً")


class SizeTests(unittest.TestCase):
    def test_patient_screen_functions_are_small(self):
        for path in glob.glob(os.path.join(ROOT, "gui", "screens", "patient", "*.py")):
            for n in ast.parse(_src(path)).body:
                if isinstance(n, ast.FunctionDef):
                    self.assertLessEqual(n.end_lineno - n.lineno + 1, 80, f"{os.path.basename(path)}:{n.name}")


def _silent_handlers(path):
    """معالجات except Exception/عارية جسمها صامت: لا raise ولا تسجيل ولا إبلاغ ولا قيمة مفيدة."""
    out = []
    for n in ast.walk(ast.parse(_src(path))):
        if not isinstance(n, ast.ExceptHandler):
            continue
        broad = n.type is None or (isinstance(n.type, ast.Name) and n.type.id in ("Exception", "BaseException"))
        if not broad:
            continue
        calls = [c for c in ast.walk(n) if isinstance(c, ast.Call)]
        loud = any(isinstance(x, ast.Raise) for x in ast.walk(n)) or any(
            (isinstance(c.func, ast.Attribute) and c.func.attr in ("log", "log_exc", "log_text", "toast", "error"))
            or (isinstance(c.func, ast.Name) and c.func.id in ("toast", "_toast")) for c in calls)
        if not loud:
            out.append(f"{os.path.relpath(path, ROOT)}:{n.lineno}")
    return out


class SilentExceptTests(unittest.TestCase):
    # مواضع قديمة مقبولة صراحةً (أخطاء تنظيف/عرض لا تؤثر على البيانات) — أي موضع جديد يُرفض
    ALLOWED = {}

    def test_no_new_silent_broad_except(self):
        files = [os.path.join(ROOT, f"{m}.py") for m in LAYERS] + glob.glob(os.path.join(ROOT, "gui", "**", "*.py"), recursive=True)
        bad = sorted(h for p in files for h in _silent_handlers(p) if h not in self.ALLOWED)
        self.assertEqual(bad, [], "except عريض صامت: سجّل الخطأ (LOG.log_exc) أو ضيّق النوع أو أعد رفعه")


if __name__ == "__main__":
    unittest.main(verbosity=2)
