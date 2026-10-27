# -*- coding: utf-8 -*-
"""
run_all.py — يشغّل كل اختبارات المشروع بالترتيب (كل ملف في عملية مستقلة) ويلخّص النتيجة؛ رمز الخروج 1 عند أي فشل.
هو ما يشغّله run_tests.bat وما يشغّله CI (GitHub Actions) قبل بناء الـAPK.
التشغيل:   python tests/run_all.py            (أو:  python tests/run_all.py architecture vectors)
"""
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ORDER = ["architecture", "vectors", "migrations", "hardening", "smoke", "phase1", "phase2", "phase3", "phase4"]
FILES = {"architecture": "test_architecture.py", "vectors": "test_vectors.py", "migrations": "test_migrations.py",
         "hardening": "test_hardening.py", "smoke": "test_smoke.py", "phase1": "test_phase1.py", "phase2": "test_phase2.py",
         "phase3": "test_phase3.py", "phase4": "test_phase4.py"}


def main():
    wanted = [a for a in sys.argv[1:] if a in FILES] or ORDER
    rows, failed = [], []
    for name in wanted:
        t0 = time.time()
        r = subprocess.run([sys.executable, os.path.join(HERE, FILES[name])], capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        lines = r.stdout.splitlines()
        n_pass = sum(1 for l in lines if l.startswith("PASS"))
        fails = [l for l in lines if l.startswith("FAIL")]
        ok = r.returncode == 0 and any(l.startswith("ALL PASSED") for l in lines)
        rows.append((name, ok, n_pass, len(fails), time.time() - t0))
        print(f"{'✓' if ok else '✗'} {name:13s} {n_pass:4d} فحص   {time.time() - t0:5.1f}s")
        if not ok:
            failed.append(name)
            print("\n".join("    " + l for l in (fails or lines[-15:])[:25]))
            if r.stderr.strip():
                print("    stderr:", r.stderr.strip().splitlines()[-1][:200])
    total = sum(r[2] for r in rows)
    print(f"\nالمجموع: {total} فحصاً — " + ("كلها نجحت" if not failed else f"فشل: {', '.join(failed)}"))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
