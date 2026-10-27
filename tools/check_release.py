# -*- coding: utf-8 -*-
"""
tools/check_release.py — حرس ما قبل البناء (يعمل في GitHub Actions وعلى جهازك قبل الرفع):
  1) لا يوجد ملف سرّي ضمن الملفات المتتبَّعة في git (admin_keys / issued_log / مفاتيح التوقيع).
     (keygen.py نفسه ليس سرّاً — المفاتيح في admin_keys.json — فيُرفع ليعمل CI، ويُستبعد من الـAPK بـexclude وبفحص check_apk.)
  2) .gitignore موجود (بهذا الاسم تماماً، لا _gitignore) ويستثني الملفات السرّية.
  3) pyproject.toml يستثني الملفات السرّية من حزمة التطبيق.
  4) public_keys.py مملوء بمفتاحين صالحين (64 خانة hex) وإلا سيظهر في التطبيق «إعداد غير مكتمل».
الاستعمال:  python tools/check_release.py        (يخرج بالرمز 1 عند أي خلل)
"""
import fnmatch
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN = ["admin_keys*.json", "issued_log*.json", "issued_codes*.json", "*.jks", "*.keystore",
             "*.p12", "key.properties", "*.shbk", "shifa_data/*", "keystore.b64"]
NEED_IGNORE = ["admin_keys", "*.jks", "issued_log"]
NEED_EXCLUDE = ["keygen.py", "admin_keys.json"]


def tracked_files():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return out.splitlines(), True
    except (OSError, subprocess.CalledProcessError):
        return [], False


def main():
    bad = []
    files, in_git = tracked_files()
    for f in files:
        base = os.path.basename(f)
        if any(fnmatch.fnmatch(base, pat) or fnmatch.fnmatch(f, pat) for pat in FORBIDDEN):
            bad.append(f"ملف سرّي/أداة مدير مرفوع إلى git: {f}  (احذفه من المستودع: git rm --cached {f})")
    if not in_git:
        print("ملاحظة: لا يوجد مستودع git هنا — تخطّيت فحص الملفات المتتبَّعة.")

    gi = os.path.join(ROOT, ".gitignore")
    if not os.path.exists(gi):
        bad.append("لا يوجد ملف .gitignore (قد يكون اسمه _gitignore؛ أعد تسميته إلى .gitignore بنقطة في البداية)")
    else:
        txt = open(gi, encoding="utf-8").read()
        for need in NEED_IGNORE:
            if need not in txt:
                bad.append(f".gitignore لا يستثني: {need}")

    py = os.path.join(ROOT, "pyproject.toml")
    ptxt = open(py, encoding="utf-8").read() if os.path.exists(py) else ""
    m = re.search(r"exclude\s*=\s*\[(.*?)\]", ptxt, re.S)
    excl = m.group(1) if m else ""
    for need in NEED_EXCLUDE:
        if f'"{need}"' not in excl:
            bad.append(f"pyproject.toml ← [tool.flet.app] exclude لا يحوي: {need}")

    pk = os.path.join(ROOT, "public_keys.py")
    ktxt = open(pk, encoding="utf-8").read() if os.path.exists(pk) else ""
    for name in ("SIGN_PUB", "BOX_PUB"):
        mm = re.search(rf'^{name}\s*=\s*"([0-9a-fA-F]*)"', ktxt, re.M)
        if not mm or len(mm.group(1)) != 64:
            bad.append(f"public_keys.py: {name} فارغ أو غير صالح (يجب 64 خانة hex). شغّل python keygen.py ثم ارفع public_keys.py")

    if bad:
        print("✗ فحص الإصدار فشل:\n  - " + "\n  - ".join(bad))
        sys.exit(1)
    print("✓ فحص الإصدار نجح")


if __name__ == "__main__":
    main()
