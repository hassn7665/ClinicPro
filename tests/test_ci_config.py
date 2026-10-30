# -*- coding: utf-8 -*-
"""حراسة إعداد CI: الإجراءات مثبّتة بـSHA، التبعيات مقفلة بالتجزئات، البناء لا يبدأ قبل نجاح الاختبارات وفحص pyflakes."""
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import ROOT  # noqa: E402


WF = ".github/workflows/build-apk.yml"


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


class CiConfigTests(unittest.TestCase):
    def test_every_action_pinned_to_full_sha(self):
        uses = re.findall(r"^\s*uses:\s*(\S+)", read(WF), re.M)
        self.assertTrue(uses)
        for u in uses:
            self.assertRegex(u, r"^[\w.-]+/[\w.-]+@[0-9a-f]{40}$", f"الإجراء غير مثبّت بـSHA كامل: {u}")

    def test_lock_file_has_hashes_for_every_package(self):
        lock = read("requirements-dev.lock")
        pkgs = re.findall(r"^([A-Za-z0-9_.-]+)==", lock, re.M)
        self.assertGreaterEqual(len(pkgs), 8)
        for name in pkgs:
            block = re.search(rf"^{re.escape(name)}==.*?(?=^\S|\Z)", lock, re.M | re.S).group(0)
            self.assertIn("--hash=sha256:", block, f"{name} بلا تجزئة")
        for needed in ("flet", "hypothesis", "pyflakes", "cryptography"):
            self.assertIn(needed, [p.lower() for p in pkgs])

    def test_flet_version_is_consistent_everywhere(self):
        v = re.search(r"flet==([\d.]+)", read("requirements.txt")).group(1)
        for f in ("pyproject.toml", WF, "requirements-dev.in", "requirements-dev.lock"):
            self.assertIn(f"flet=={v}", read(f), f)

    def test_build_waits_for_tests_and_ci_runs_lint(self):
        wf = read(WF)
        self.assertRegex(wf, r"build:\s*\n\s*needs: test")
        self.assertIn("python -m pyflakes .", wf)
        self.assertIn("--require-hashes", wf)
        self.assertIn("python tools/run_tests.py", wf)
        self.assertIn("HYPOTHESIS_PROFILE: ci", wf)


if __name__ == "__main__":
    unittest.main(verbosity=2)
