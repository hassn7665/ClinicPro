# -*- coding: utf-8 -*-
"""
tools/check_release.py — حارس ما قبل البناء (يعمل في CI قبل بناء الـAPK، ويمكن تشغيله محلياً: python tools/check_release.py).

يفشل (رمز خروج 1) إن:
  • وُجد في المستودع أي سرّ: مفاتيح المدير الخاصة (admin_keys*.json)، سجل الأكواد، ملفات توقيع أندرويد (.jks/.keystore/.p12/key.properties)،
    أو نص مفتاح خاص (BEGIN … PRIVATE KEY).
  • غاب public_keys.py أو كان فارغاً/غير صالح (SIGN_PUB و BOX_PUB: 64 خانة hex) — بدونه يعرض التطبيق «إعداد غير مكتمل».
  • نقص في .gitignore أو في قائمة exclude داخل pyproject.toml ما يحمي الأسرار وأداة المدير من الرفع والتحزيم.
مكتبة بايثون القياسية فقط.
"""
import fnmatch
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_DIRS = {".git", "build", "__pycache__", ".venv", ".hypothesis", "node_modules"}

SECRET_FILES = ("admin_keys*.json", "issued_log*.json*", "issued_codes.json", "*.jks", "*.keystore", "*.p12",
                "key.properties", "keystore.b64")
GITIGNORE_NEED = ("admin_keys.json", "issued_log.json", "*.jks", "key.properties")
EXCLUDE_NEED = ("keygen.py", "admin_keys.json", "issued_log.json")
_PRIV = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")
_TEXT_EXT = (".py", ".json", ".toml", ".yml", ".yaml", ".md", ".txt", ".bat", ".properties", ".cfg", ".ini")


def _walk():
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            yield os.path.join(root, f)


def check_secret_files(problems):
    for p in _walk():
        name = os.path.basename(p)
        if any(fnmatch.fnmatch(name, pat) for pat in SECRET_FILES):
            problems.append(f"ملف سرّي داخل المشروع: {os.path.relpath(p, ROOT)} — احذفه من المجلد ولا ترفعه")
        elif name.endswith(_TEXT_EXT) and os.path.getsize(p) < 2_000_000:
            try:
                with open(p, encoding="utf-8") as f:
                    if _PRIV.search(f.read()):
                        problems.append(f"نص مفتاح خاص داخل: {os.path.relpath(p, ROOT)}")
            except (OSError, UnicodeDecodeError):
                pass


def check_public_keys(problems):
    path = os.path.join(ROOT, "public_keys.py")
    if not os.path.isfile(path):
        problems.append("public_keys.py غير موجود: ولّده بـ python keygen.py وارفعه مع المشروع (هو مفاتيح عامة آمنة)")
        return
    with open(path, encoding="utf-8") as f:
        text = f.read()
    for name in ("SIGN_PUB", "BOX_PUB"):
        m = re.search(rf'^{name}\s*=\s*"([0-9a-fA-F]*)"', text, re.M)
        if not m or len(m.group(1)) != 64:
            problems.append(f"public_keys.py: {name} فارغ أو غير صالح (يجب 64 خانة hex)")


def check_ignore_and_exclude(problems):
    gi = os.path.join(ROOT, ".gitignore")
    if not os.path.isfile(gi):
        problems.append(".gitignore غير موجود")
    else:
        with open(gi, encoding="utf-8") as f:
            lines = {ln.strip() for ln in f if ln.strip() and not ln.lstrip().startswith("#")}
        for need in GITIGNORE_NEED:
            if need not in lines:
                problems.append(f".gitignore ينقصه السطر: {need}")
    pp = os.path.join(ROOT, "pyproject.toml")
    try:
        with open(pp, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        problems.append("pyproject.toml غير موجود")
        return
    m = re.search(r"^exclude\s*=\s*\[(.*?)\]", text, re.M | re.S)
    items = set(re.findall(r'"([^"]+)"', m.group(1))) if m else set()
    for need in EXCLUDE_NEED:
        if need not in items:
            problems.append(f"pyproject.toml: قائمة exclude تنقصها «{need}» (ستدخل الـAPK)")


def main() -> int:
    problems = []
    check_secret_files(problems)
    check_public_keys(problems)
    check_ignore_and_exclude(problems)
    if problems:
        print("✗ فشل فحص الإصدار:")
        for p in problems:
            print("  -", p)
        return 1
    print("✓ فحص الإصدار نجح: لا أسرار في المستودع، و public_keys.py صالح، و .gitignore/exclude سليمان")
    return 0


if __name__ == "__main__":
    sys.exit(main())
