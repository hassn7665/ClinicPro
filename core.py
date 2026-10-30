# -*- coding: utf-8 -*-
"""
core.py — واجهة التوافق لطبقة المنطق (لا تحتوي منطقاً): تعيد تصدير كل ما كان يعيش هنا سابقاً من الوحدات التالية،
فتبقى كل الاستيرادات القديمة (import core as C ... C.money, C.q, C._mem) تعمل كما هي. لا يعتمد على Flet.

  storage → db → finance → events → patients → media / reports / share     (كل وحدة تعتمد على ما قبلها فقط)
  licensing · backup · accounts · diagnostics
"""
import applog as LOG
import crypto_core as K
import images as IMG
import license_core as LC
import schema as SC
import theme as TH
import vault as VT

from storage import (  # noqa: F401
    APP_NAME, APP_VERSION, BACKUP_EVERY_DAYS, BASE,
    BK_DIR, DB_ENC, DB_PATH, DEFAULT_DURATION,
    DEFAULT_TIME, DURATIONS, EXPORT_REMIND_DAYS, IMG_EXT,
    JOURNAL, KEEP_BACKUPS, KIND_AR, LIC_PATH,
    NotUnlocked, PAT_DIR, SET_PATH, SHARE_DIR,
    VAULT, VaultError, _DIGITS, _atomic_write,
    _faad, _jlock, _lock, _mem,
    _migrate_file_aad, _sniff_ext, _wipe_file, _wipe_rel,
    add_months, ap, digits, file_b64,
    file_size, is_image_name, jload, jsave,
    new_rel, norm, phone_key, read_file,
    safe, store_file, thumb_b64, thumb_rel,
    today, write_enc,
)
from db import (  # noqa: F401
    DB_MAGIC, RollbackError, _Handle, _commit_then,
    _db_decode, _db_encode, _new_conn, _persist,
    _serialize, close_db, db, get_patient,
    init_db, open_db, patient_attachments, patient_events,
    q, set_event_in_report, x,
)
from finance import (  # noqa: F401
    CURS, CUR_BI, CUR_NAME, CUR_SYM,
    MINOR, _FIN, _check_pay, _insert_payment,
    _sum, _write_items, add_payments, amounts,
    delete_payment, edit_payment, ev_fin, ev_items,
    ev_payments, fin_file, fin_stats, fin_totals,
    minor, money, money_multi, parse_money,
    update_items, zero,
)
from backup import (  # noqa: F401
    BK_EXT, _BK_END, _BK_FMT, _BK_MAGIC,
    _BK_MAX_REC, _OPAQUE, _bk_aad, _bk_header,
    _bk_key, _bk_open, _bk_records, _file_sig,
    _migrate_all_legacy, _migrate_legacy_backups, _migrate_legacy_files, _prune_backups,
    auto_backup_if_due, backup_needs_password, backup_report, ensure_recent_backup,
    export_due, list_backups, make_backup, mark_exported,
    recover_interrupted_restore, restore_backup,
)
from events import (  # noqa: F401
    _ar_n, _canon_when, _check_when, cancel_event,
    clear_event_photo, confirm_event, create_event, day_counts,
    day_schedule, delete_event, ev_dt, ev_span,
    event_conflicts, event_status, mark_no_show, reinstate_event,
    rel_label, set_event_photo, upcoming_events, update_event,
)
from patients import (  # noqa: F401
    DuplicatePatient, clear_patient_photo, delete_attachment, delete_patient,
    fin_patients, find_duplicates, patient_age, patient_delete_summary,
    rename_attachment, resolve_birth, save_patient, search_patients,
)
from media import (  # noqa: F401
    META_SCRUB_VER, OPT_MIN_BYTES, _all_image_rels, images_to_optimize,
    optimize_images, scrub_metadata, scrub_metadata_if_needed,
)
from licensing import (  # noqa: F401
    _lic_mac, _lic_save, lic_activate, lic_load,
    lic_status,
)
from share import (  # noqa: F401
    SHARE_TTL, _Handler, _srv, _stop_server,
    new_share_dir, share_attachment, share_file, share_text,
    share_url,
)
from accounts import (  # noqa: F401
    LOCK_CHOICES, LOCK_DEFAULT, create_recovery_key, keys_ready,
    lock_app, lock_policy, need_setup, reset_request_code,
    reset_with_code, reset_with_recovery_key, set_escrow, set_lock_policy,
    setup_account, unlock,
)
from reports import (  # noqa: F401
    _css, build_fin_report, build_report, stats,
)
from diagnostics import (  # noqa: F401
    _startup_recovery, diagnostics, module_mismatch,
)

from accounts import ensure_escrow  # noqa: F401
from events import default_slot, event_detail, fmt12, hm_from_12, hm_to_12  # noqa: F401
from patients import SORTS, UNNAMED, list_patients  # noqa: F401

__all__ = ['default_slot', 'SORTS', 'UNNAMED', 'ensure_escrow', 'event_detail', 'fmt12', 'hm_from_12', 'hm_to_12', 'list_patients', 'APP_NAME', 'APP_VERSION', 'BACKUP_EVERY_DAYS', 'BASE', 'BK_DIR', 'BK_EXT', 'CURS', 'CUR_BI', 'CUR_NAME', 'CUR_SYM', 'DB_ENC', 'DB_MAGIC', 'DB_PATH', 'DEFAULT_DURATION', 'DEFAULT_TIME', 'DURATIONS', 'DuplicatePatient', 'EXPORT_REMIND_DAYS', 'IMG', 'IMG_EXT', 'JOURNAL', 'K', 'KEEP_BACKUPS', 'KIND_AR', 'LC', 'LIC_PATH', 'LOCK_CHOICES', 'LOCK_DEFAULT', 'LOG', 'META_SCRUB_VER', 'MINOR', 'NotUnlocked', 'OPT_MIN_BYTES', 'PAT_DIR', 'RollbackError', 'SC', 'SET_PATH', 'SHARE_DIR', 'SHARE_TTL', 'TH', 'VAULT', 'VT', 'VaultError', '_BK_END', '_BK_FMT', '_BK_MAGIC', '_BK_MAX_REC', '_DIGITS', '_FIN', '_Handle', '_Handler', '_OPAQUE', '_all_image_rels', '_ar_n', '_atomic_write', '_bk_aad', '_bk_header', '_bk_key', '_bk_open', '_bk_records', '_canon_when', '_check_pay', '_check_when', '_commit_then', '_css', '_db_decode', '_db_encode', '_faad', '_file_sig', '_insert_payment', '_jlock', '_lic_mac', '_lic_save', '_lock', '_mem', '_migrate_all_legacy', '_migrate_file_aad', '_migrate_legacy_backups', '_migrate_legacy_files', '_new_conn', '_persist', '_prune_backups', '_serialize', '_sniff_ext', '_srv', '_startup_recovery', '_stop_server', '_sum', '_wipe_file', '_wipe_rel', '_write_items', 'add_months', 'add_payments', 'amounts', 'ap', 'auto_backup_if_due', 'backup_needs_password', 'backup_report', 'build_fin_report', 'build_report', 'cancel_event', 'clear_event_photo', 'clear_patient_photo', 'close_db', 'confirm_event', 'create_event', 'create_recovery_key', 'day_counts', 'day_schedule', 'db', 'delete_attachment', 'delete_event', 'delete_patient', 'delete_payment', 'diagnostics', 'digits', 'edit_payment', 'ensure_recent_backup', 'ev_dt', 'ev_fin', 'ev_items', 'ev_payments', 'ev_span', 'event_conflicts', 'event_status', 'export_due', 'file_b64', 'file_size', 'fin_file', 'fin_patients', 'fin_stats', 'fin_totals', 'find_duplicates', 'get_patient', 'images_to_optimize', 'init_db', 'is_image_name', 'jload', 'jsave', 'keys_ready', 'lic_activate', 'lic_load', 'lic_status', 'list_backups', 'lock_app', 'lock_policy', 'make_backup', 'mark_exported', 'mark_no_show', 'minor', 'module_mismatch', 'money', 'money_multi', 'need_setup', 'new_rel', 'new_share_dir', 'norm', 'open_db', 'optimize_images', 'parse_money', 'patient_age', 'patient_attachments', 'patient_delete_summary', 'patient_events', 'phone_key', 'q', 'read_file', 'recover_interrupted_restore', 'reinstate_event', 'rel_label', 'rename_attachment', 'reset_request_code', 'reset_with_code', 'reset_with_recovery_key', 'resolve_birth', 'restore_backup', 'safe', 'save_patient', 'scrub_metadata', 'scrub_metadata_if_needed', 'search_patients', 'set_escrow', 'set_event_in_report', 'set_event_photo', 'set_lock_policy', 'setup_account', 'share_attachment', 'share_file', 'share_text', 'share_url', 'stats', 'store_file', 'thumb_b64', 'thumb_rel', 'today', 'unlock', 'upcoming_events', 'update_event', 'update_items', 'write_enc', 'x', 'zero']

_startup_recovery()
