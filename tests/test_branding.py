# -*- coding: utf-8 -*-
"""
tests/test_branding.py — حارس الهوية: الاسم الرسمي «My Clinic» وعدم عودة أي أثر للأسماء القديمة،
وسلامة إعداد رابط نموذج الملاحظات.
"""
import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# تُبنى الأنماط من أجزاء كي لا يطابق هذا الملف نفسه
_OLD = re.compile("|".join(["clinic" + r"[ _-]?" + "pro", "shi" + "faa*[_\\-. ]", "shi" + "fa$", "SHI" + "FA",
                            "sh" + "bk", "SH" + "F1", "SH" + "D1"]), re.I | re.M)
_SKIP_DIRS = {"__pycache__", ".git", "build", "myclinic_data"}
_SKIP_EXT = (".png", ".jpg", ".ttf", ".otf", ".lock", ".pyc", ".jks")


def _files():
    for root, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fn in files:
            if fn.endswith(_SKIP_EXT) or os.path.join(root, fn) == os.path.abspath(__file__):
                continue
            yield os.path.join(root, fn)


class BrandingTests(unittest.TestCase):
    def test_app_name(self):
        import storage
        self.assertEqual(storage.APP_NAME, "My Clinic")

    def test_no_old_names_anywhere(self):
        bad = []
        for p in _files():
            try:
                text = open(p, encoding="utf-8").read()
            except (UnicodeDecodeError, OSError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                if _OLD.search(line):
                    bad.append(f"{os.path.relpath(p, ROOT)}:{i}: {line.strip()[:80]}")
        self.assertEqual(bad, [], "أسماء قديمة وُجدت:\n" + "\n".join(bad))

    def test_pyproject_identity(self):
        txt = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()
        self.assertIn('product = "My Clinic"', txt)
        self.assertRegex(txt, r'(?m)^name = "my_clinic"')

    def test_feedback_url_is_empty_or_https(self):
        txt = open(os.path.join(ROOT, "gui", "common.py"), encoding="utf-8").read()
        m = re.search(r'(?m)^FEEDBACK_URL = "(.*)"', txt)
        self.assertIsNotNone(m)
        self.assertTrue(m.group(1) == "" or m.group(1).startswith("https://"))

    def test_feedback_button_wired_in_settings(self):
        txt = open(os.path.join(ROOT, "gui", "screens", "settings.py"), encoding="utf-8").read()
        self.assertIn("تقديم الملاحظات والمقترحات", txt)
        self.assertIn("FEEDBACK_URL", txt)


def _read(*parts):
    return open(os.path.join(ROOT, *parts), encoding="utf-8").read()


class UxFixesTests(unittest.TestCase):
    def test_splash_assets_are_transparent_and_complete(self):
        import struct
        for n in ("splash.png", "splash_android.png", "splash_dark.png", "splash_dark_android.png"):
            data = open(os.path.join(ROOT, "assets", n), "rb").read()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n", n)
            w, h, depth, ctype = struct.unpack(">IIBB", data[16:26])
            self.assertEqual((w, h), (1024, 1024), n)
            self.assertEqual(ctype, 6, f"{n}: يجب أن تكون RGBA بزوايا شفافة")

    def test_pillow_declared_for_the_apk(self):
        import tomllib
        deps = tomllib.loads(_read("pyproject.toml"))["project"]["dependencies"]
        self.assertIn("pillow", [d.lower() for d in deps])
        self.assertEqual(sum(d.startswith("flet==") for d in deps), 1)

    def test_nav_bar_respects_system_insets_and_fonts_are_warmed(self):
        w = _read("gui", "widgets.py")
        self.assertIn("ft.SafeArea", w)
        self.assertNotIn("ft.BottomAppBar(", w)           # الارتفاع الثابت كان يقصّ الشريط خلف أزرار النظام
        self.assertIn("def warm_fonts", _read("gui", "app.py"))

    def test_amount_fields_use_money_field(self):
        for f in (("gui", "widgets.py"), ("gui", "screens", "accounts.py"), ("gui", "screens", "patient", "confirm.py")):
            self.assertIn("money_field(", _read(*f), f)

    def test_search_label_is_short(self):
        self.assertNotIn("أو اتركه فارغاً لتصفّح الكل\")", _read("gui", "screens", "search.py"))


class GroupAmountTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        os.environ["FLET_APP_STORAGE_DATA"] = tempfile.mkdtemp()
        import core
        self.C = core

    def test_grouping(self):
        g = self.C.group_amount_text
        self.assertEqual(g("1234567"), "1,234,567")
        self.assertEqual(g("١٢٣٤٥٦٧"), "1,234,567")
        self.assertEqual(g("20000.5"), "20,000.5")
        self.assertEqual(g("12345.6789"), "12,345.67")
        self.assertEqual(g("007"), "7")
        self.assertEqual(g("abc"), "")
        self.assertEqual(g(None), "")

    def test_value_is_unchanged_by_grouping(self):
        for raw in ("1", "999", "1000", "123456789", "0.5", "20000.50", "1500000"):
            self.assertEqual(self.C.parse_money(self.C.group_amount_text(raw)), self.C.parse_money(raw))

    def test_money_roundtrip_with_display_format(self):
        for v in (0, 100, 12345600, 2000050):
            self.assertEqual(self.C.parse_money(self.C.group_amount_text(self.C.money(v))), v)


class ImageCompressionTests(unittest.TestCase):
    def test_large_photo_is_resized_and_smaller(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow غير مثبّتة هنا")
        import io
        import random
        import images as IMG
        rnd = random.Random(1)
        im = Image.new("RGB", (3000, 2000))
        im.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(3000 * 2000)][:3000 * 2000])
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=95)
        src = buf.getvalue()
        full, thumb = IMG.process(src)
        out = Image.open(io.BytesIO(full))
        self.assertLessEqual(max(out.size), IMG.MAX_SIDE)
        self.assertLess(len(full), len(src) / 2)
        self.assertIsNotNone(thumb)

    def test_small_jpeg_is_never_enlarged(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow غير مثبّتة هنا")
        import io
        import images as IMG
        buf = io.BytesIO()
        Image.new("RGB", (400, 300), (30, 120, 110)).save(buf, "JPEG", quality=40)
        src = buf.getvalue()
        full, _ = IMG.process(src)
        self.assertLessEqual(len(full), len(src))


class ReleaseToolsTests(unittest.TestCase):
    """أدوات tools/check_release.py و tools/check_apk.py (يستدعيهما CI)."""

    def _apk(self, extra=None, nested=None, manifest=True):
        import io
        import tempfile
        import zipfile
        d = tempfile.mkdtemp()
        path = os.path.join(d, "t.apk")
        with zipfile.ZipFile(path, "w") as z:
            if manifest:
                z.writestr("AndroidManifest.xml", "x")
            for n in (extra or []):
                z.writestr(n, "x")
            if nested:
                buf = io.BytesIO()
                with zipfile.ZipFile(buf, "w") as inner:
                    for n in nested:
                        inner.writestr(n, "x")
                z.writestr("assets/app/app.zip", buf.getvalue())
        return path

    def test_check_apk(self):
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        import check_apk
        self.assertEqual(check_apk.check(self._apk(nested=["main.py", "public_keys.py"])), 0)
        self.assertEqual(check_apk.check(self._apk(nested=["main.py", "keygen.py"])), 1)
        self.assertEqual(check_apk.check(self._apk(extra=["assets/admin_keys.json"])), 1)
        self.assertEqual(check_apk.check(self._apk(extra=["x/upload-keystore.jks"])), 1)
        self.assertEqual(check_apk.check(self._apk(manifest=False)), 1)

    def test_check_release_passes_on_this_repo_layout(self):
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "check_release.py")], capture_output=True, text=True,
                           encoding="utf-8")
        # في بيئة المطوّر قد لا يوجد public_keys.py (يُنشأ محلياً): المسموح فقط أن يكون هو سبب الفشل الوحيد
        if r.returncode:
            lines = [ln for ln in r.stdout.splitlines() if ln.startswith("  -")]
            self.assertTrue(all("public_keys.py" in ln for ln in lines), r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
