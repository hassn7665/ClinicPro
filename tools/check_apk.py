# -*- coding: utf-8 -*-
"""
tools/check_apk.py — يفتح ملف APK (وأي أرشيف zip داخله مثل app.zip الذي يحوي شيفرة بايثون) ويفشل إن وجد
ملفاً سرّياً أو أداة مدير بداخله.    الاستعمال:  python tools/check_apk.py path/to/app.apk
"""
import fnmatch
import io
import sys
import zipfile

FORBIDDEN = ["admin_keys*.json", "issued_log*.json", "issued_codes*.json", "keygen.py", "*.jks", "*.keystore",
             "*.p12", "key.properties"]


def scan(zf, prefix, hits, stats):
    for name in zf.namelist():
        base = name.rsplit("/", 1)[-1]
        if any(fnmatch.fnmatch(base, p) for p in FORBIDDEN):
            hits.append(prefix + name)
        if name.lower().endswith(".zip") and zf.getinfo(name).file_size < 400_000_000:
            try:
                with zipfile.ZipFile(io.BytesIO(zf.read(name))) as inner:
                    stats["nested"] += 1
                    if any(n.endswith("main.py") for n in inner.namelist()):
                        stats["app"] += 1
                    scan(inner, prefix + name + "!/", hits, stats)
            except zipfile.BadZipFile:
                pass


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: check_apk.py app.apk")
    hits, stats = [], {"nested": 0, "app": 0}
    with zipfile.ZipFile(sys.argv[1]) as z:
        scan(z, "", hits, stats)
    if hits:
        print("✗ الحزمة تحوي ملفات سرّية/أدوات مدير:\n  - " + "\n  - ".join(hits))
        sys.exit(1)
    if not stats["app"]:
        print("::warning::لم أجد أرشيف شيفرة التطبيق داخل الـAPK، فلم أستطع التحقق من محتواه (بنية الحزمة تغيّرت؟)")
    print("✓ الـAPK خالٍ من الملفات السرّية")


if __name__ == "__main__":
    main()
