# -*- coding: utf-8 -*-
"""
share.py — خادم المشاركة المحلي (127.0.0.1) لفتح التقارير والنسخ في متصفح الهاتف برابط عشوائي مؤقت.
"""
import functools
import http.server
import os
import secrets
import shutil
import threading
import time
import urllib.parse

import applog as LOG

from storage import SHARE_DIR, read_file


# ───────────────────────── خادم المشاركة المحلي ─────────────────────────
# يعرض ملفاً (تقرير للطباعة / نسخة احتياطية) على 127.0.0.1 فقط، برابط عشوائي
# غير قابل للتخمين، ثم يُفتح في متصفح الهاتف (للطباعة أو التنزيل). يتوقف تلقائياً.
class _Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def list_directory(self, path):          # منع عرض محتوى المجلدات
        self.send_error(403)
        return None

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


_srv = {"httpd": None, "port": None, "timer": None}


def _stop_server():
    h = _srv["httpd"]
    if h:
        try:
            h.shutdown()
            h.server_close()
        except (OSError, RuntimeError) as ex:
            LOG.log_exc("share_stop", ex)
    _srv.update(httpd=None, port=None, timer=None)
    shutil.rmtree(SHARE_DIR, ignore_errors=True)


SHARE_TTL = 900                      # عمر الرابط المحلي بالثواني (يطابق مؤقّت الخادم)


def new_share_dir():
    """ينشئ مجلداً عشوائياً داخل SHARE_DIR ويعيد (المسار, الرمز).
    يمحو المجلدات المنتهية فقط؛ فتح مرفق ثانٍ لا يكسر تقريراً ما زال مفتوحاً في المتصفح."""
    os.makedirs(SHARE_DIR, exist_ok=True)
    now = time.time()
    for d in os.listdir(SHARE_DIR):
        full = os.path.join(SHARE_DIR, d)
        try:
            if now - os.path.getmtime(full) > SHARE_TTL:
                shutil.rmtree(full, ignore_errors=True)
        except OSError:
            pass
    token = secrets.token_urlsafe(12)
    path = os.path.join(SHARE_DIR, token)
    os.makedirs(path, exist_ok=True)
    return path, token


def share_url(token, filename):
    if not _srv["httpd"]:
        handler = functools.partial(_Handler, directory=SHARE_DIR)
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        _srv.update(httpd=httpd, port=httpd.server_address[1])
    if _srv["timer"]:
        _srv["timer"].cancel()
    t = threading.Timer(900, _stop_server)   # يتوقف بعد 15 دقيقة
    t.daemon = True
    t.start()
    _srv["timer"] = t
    return f"http://127.0.0.1:{_srv['port']}/{token}/{urllib.parse.quote(filename)}"


def share_attachment(rel, name):
    """يفكّ تشفير مرفق إلى مجلد مشاركة مؤقت (يُمحى عند القفل/انتهاء المهلة) ويعيد رابطه المحلي."""
    folder, token = new_share_dir()
    name = os.path.basename((name or "file").replace("\\", "/")) or "file"
    with open(os.path.join(folder, name), "wb") as f:
        f.write(read_file(rel))
    return share_url(token, name)


def share_text(name, text):
    """يجهّز نصاً (مثل تقرير التشخيص) للتنزيل عبر المتصفح ويعيد الرابط."""
    folder, token = new_share_dir()
    name = os.path.basename((name or "report.txt").replace("\\", "/")) or "report.txt"
    with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
        f.write(text)
    return share_url(token, name)


def share_file(src_path, name=None):
    """يجهّز ملفاً للفتح/التنزيل عبر المتصفح ويعيد الرابط (name = الاسم الظاهر للمستخدم)."""
    folder, token = new_share_dir()
    name = os.path.basename((name or src_path).replace("\\", "/")) or "file"
    shutil.copyfile(src_path, os.path.join(folder, name))
    return share_url(token, name)
