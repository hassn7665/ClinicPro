# -*- coding: utf-8 -*-
"""
media.py — صيانة الصور المخزّنة: تجريد البيانات الوصفية (EXIF/GPS) وتصغير الصور القديمة.
"""
import os

import applog as LOG
import images as IMG

from backup import _prune_backups, make_backup
from db import q
from storage import (
    SET_PATH, VAULT, ap, file_size, is_image_name,
    jload, jsave, read_file, thumb_rel, write_enc)


# ───────────────────────── تحسين الصور الموجودة ─────────────────────────
OPT_MIN_BYTES = 300_000          # لا نعالج الصور الأصغر من هذا (لا فائدة تُذكر)


def _all_image_rels() -> set:
    rels = set()
    for sql in ("SELECT photo_before FROM patients", "SELECT photo_after FROM patients",
                "SELECT photo_lab FROM patients", "SELECT photo_before FROM events", "SELECT photo_after FROM events"):
        rels.update(r[0] for r in q(sql) if r[0])
    rels.update(r["path"] for r in q("SELECT path, name FROM attachments") if is_image_name(r["name"]))
    return rels


def scrub_metadata(progress=None) -> dict:
    """يجرّد EXIF/GPS/XMP من كل الصور المخزّنة سابقاً (لا يحتاج Pillow). كل ملف يُكتب ذرّياً بنفس اسمه.
    يعيد {'checked': n, 'cleaned': n, 'failed': n}."""
    rels = sorted(r for r in _all_image_rels() if os.path.isfile(ap(r)))
    checked = cleaned = failed = 0
    for i, rel in enumerate(rels, 1):
        try:
            data = read_file(rel)
            checked += 1
            clean = IMG.strip_metadata(data)
            if clean is not data:
                write_enc(rel, clean)
                cleaned += 1
        except Exception as ex:
            failed += 1
            LOG.log_exc("scrub_metadata", ex, file=os.path.basename(rel))
        if progress:
            progress(i, len(rels))
    LOG.log("scrub_done", checked=checked, cleaned=cleaned, failed=failed)
    return {"checked": checked, "cleaned": cleaned, "failed": failed}


META_SCRUB_VER = 1


def scrub_metadata_if_needed():
    """مرة واحدة بعد التحديث: صور الإصدارات السابقة قد تحمل إحداثيات GPS. يُعاد التشغيل إن فشل شيء."""
    st = jload(SET_PATH, {})
    if st.get("meta_scrub") == META_SCRUB_VER or not VAULT.unlocked:
        return None
    rep = scrub_metadata()
    if not rep["failed"]:
        st = jload(SET_PATH, {})
        st["meta_scrub"] = META_SCRUB_VER
        jsave(SET_PATH, st)
    return rep


def images_to_optimize():
    """مراجع صور مخزّنة كبيرة وبلا مصغّرة (من إصدارات قبل 2.5). فارغة إن لم تتوفر مكتبة الصور."""
    if not IMG.PIL_OK or not VAULT.unlocked:
        return []
    rels = _all_image_rels()
    return sorted(r for r in rels if os.path.isfile(ap(r)) and file_size(r) > OPT_MIN_BYTES
                  and not os.path.isfile(ap(thumb_rel(r))))


def optimize_images(progress=None):
    """يصغّر الصور القديمة وينشئ مصغّراتها في مكانها (الاسم نفسه فلا تتغير القاعدة). يأخذ نسخة احتياطية أولاً.
    كل ملف يُكتب ذرّياً؛ الانقطاع في المنتصف لا يفسد شيئاً. يعيد {'done':n,'saved':بايت,'failed':n}."""
    todo = images_to_optimize()
    if not todo:
        return {"done": 0, "saved": 0, "failed": 0}
    make_backup(prune=False)
    done = saved = failed = 0
    for i, rel in enumerate(todo, 1):
        try:
            data = read_file(rel)
            full, thumb = IMG.process(data)
            if thumb is None and full is data:
                failed += 1
            else:
                write_enc(rel, full)
                if thumb:
                    write_enc(thumb_rel(rel), thumb)
                saved += max(len(data) - len(full), 0)
                done += 1
        except Exception as ex:
            failed += 1
            LOG.log_exc("optimize_image", ex, file=os.path.basename(rel))
        if progress:
            progress(i, len(todo))
    _prune_backups()
    LOG.log("optimize_done", done=done, failed=failed, saved=saved)
    return {"done": done, "saved": saved, "failed": failed}
