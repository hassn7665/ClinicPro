# -*- coding: utf-8 -*-
"""
tools/check_apk.py — يفحص ملف الـAPK الناتج (يعمل في CI بعد البناء):  python tools/check_apk.py build/apk/*.apk

يفشل (رمز خروج 1) إن:
  • الملف ليس APK صالحاً (ليس zip أو بلا AndroidManifest.xml).
  • وُجد داخله — حتى داخل أرشيفات zip المتداخلة (حزمة تطبيق Flet) — أي ملف سرّي: keygen.py أو admin_keys*.json أو
    issued_log*/issued_codes.json أو مفاتيح توقيع (.jks/.keystore/.p12/key.properties).
مكتبة بايثون القياسية فقط.
"""
import fnmatch
import io
import posixpath
import sys
import zipfile

FORBIDDEN = ("keygen.py", "admin_keys*", "issued_log*", "issued_codes.json", "*.jks", "*.keystore", "*.p12",
             "key.properties", "keystore.b64", "upload-keystore*")
MAX_DEPTH = 3
MAX_NESTED = 400 * 1024 * 1024       # سقف حجم أرشيف متداخل نفتحه في الذاكرة


def _scan(z: zipfile.ZipFile, where: str, depth: int, found: list, seen: dict):
    for info in z.infolist():
        if info.is_dir():
            continue
        name = info.filename
        base = posixpath.basename(name)
        if any(fnmatch.fnmatch(base.lower(), pat) for pat in FORBIDDEN):
            found.append(f"{where}{name}")
        if name == "public_keys.py" or name.endswith("/public_keys.py"):
            seen["public_keys"] = True
        if base.lower().endswith(".zip") and depth < MAX_DEPTH and info.file_size <= MAX_NESTED:
            try:
                with z.open(info) as fh:
                    inner = zipfile.ZipFile(io.BytesIO(fh.read()))
            except (zipfile.BadZipFile, OSError, RuntimeError):
                continue
            _scan(inner, f"{where}{name}!/", depth + 1, found, seen)


def check(path: str) -> int:
    try:
        z = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as ex:
        print(f"✗ {path}: ليس ملف APK صالحاً ({type(ex).__name__})")
        return 1
    with z:
        if "AndroidManifest.xml" not in z.namelist():
            print(f"✗ {path}: لا يحوي AndroidManifest.xml (ليس APK)")
            return 1
        found, seen = [], {}
        _scan(z, "", 0, found, seen)
    if found:
        print(f"✗ {path}: ملفات سرّية داخل الحزمة — لا توزّعها:")
        for f in found:
            print("  -", f)
        return 1
    note = "" if seen.get("public_keys") else "  (تنبيه: لم أجد public_keys.py ظاهراً؛ قد تكون الحزمة مضغوطة/مترجمة)"
    print(f"✓ {path}: نظيف، لا مفاتيح مدير ولا أداة مدير داخل الحزمة{note}")
    return 0


def main(argv) -> int:
    paths = argv[1:]
    if not paths:
        print("الاستعمال: python tools/check_apk.py <ملف.apk> ...")
        return 1
    return 1 if any([check(p) for p in paths]) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
