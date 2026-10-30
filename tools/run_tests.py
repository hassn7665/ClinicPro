# -*- coding: utf-8 -*-
"""
tools/run_tests.py — يشغّل كل ملفات tests/test_*.py (كلٌّ في عملية مستقلة) ويفشل إن فشل أي منها.
نقطة التشغيل الوحيدة للاختبارات: محلياً (run_tests.bat) وفي CI (.github/workflows/build-apk.yml).
"""
import glob
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    files = sorted(glob.glob(os.path.join(ROOT, "tests", "test_*.py")))
    if not files:
        print("لا توجد اختبارات في tests/")
        return 1
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    failed = []
    for f in files:
        name = os.path.relpath(f, ROOT)
        print(f"\n===== {name} =====", flush=True)
        t0 = time.time()
        rc = subprocess.call([sys.executable, f], cwd=ROOT, env=env)
        print(f"----- {name}: {'OK' if rc == 0 else 'FAILED'} ({time.time() - t0:.1f}s)", flush=True)
        if rc:
            failed.append(name)
    print("\n" + ("كل الاختبارات نجحت ✓" if not failed else "فشلت: " + ", ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
