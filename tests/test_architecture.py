# -*- coding: utf-8 -*-
"""
test_architecture.py — يفرض بنية الكود (المرحلة 4):
  • الواجهة (main.py و ui_kit.py و screens/*) لا تكتب SQL ولا تلمس الملفات/الإعدادات/القاعدة مباشرة؛ كل ذلك عبر core.
  • وحدات المنطق (core, migrations, vault, ...) لا تستورد Flet.
  • وحدات الشاشات لا تستورد بعضها ولا main (التواصل عبر app فقط) ولكل منها register(app).
  • حجم كل وحدة معقول، والشيفرة خالية من الأسماء غير المعرّفة/المستوردات غير المستعملة (pyflakes).
التشغيل:   python tests/test_architecture.py
"""
import ast
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAILS = []
UI_FILES = ["main.py", "ui_kit.py"] + sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "screens", "*.py"))
                                              if not p.endswith("__init__.py"))
SCREEN_FILES = [f for f in UI_FILES if f.startswith("screens")]
LOGIC_FILES = ["core.py", "migrations.py", "vault.py", "license_core.py", "crypto_core.py", "images.py", "applog.py", "selftest.py"]
SQL_RE = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|PRAGMA|WITH|REPLACE)\b", re.I)
FORBIDDEN_ATTRS = {"q", "x", "db", "closing", "jload", "jsave", "SET_PATH", "DB_ENC", "DB_PATH", "_mem", "_lock", "_persist",
                   "BASE", "PAT_DIR", "BK_DIR"}


def check(name, cond, extra=""):
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        FAILS.append(name)


def parse(rel):
    return ast.parse(open(os.path.join(ROOT, rel), encoding="utf-8").read())


def imported_modules(tree):
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module:
            out.add(n.module.split(".")[0])
    return out


def main():
    bad_sql, bad_attr, bad_imp = [], [], []
    for rel in UI_FILES:
        t = parse(rel)
        for n in ast.walk(t):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and SQL_RE.match(n.value) and len(n.value.split()) > 2:
                bad_sql.append(f"{rel}:{n.lineno}")
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "C" and n.attr in FORBIDDEN_ATTRS:
                bad_attr.append(f"{rel}:{n.lineno} C.{n.attr}")
            if isinstance(n, ast.ImportFrom) and n.module == "core":
                bad_attr += [f"{rel}:{n.lineno} from core import {a.name}" for a in n.names if a.name in FORBIDDEN_ATTRS]
        if "sqlite3" in imported_modules(t):
            bad_imp.append(rel)
    check("الواجهة لا تحوي SQL", not bad_sql, str(bad_sql[:5]))
    check("الواجهة لا تستدعي أدوات القاعدة/الملفات الداخلية في core (q/x/db/jload/_mem/...)", not bad_attr, str(bad_attr[:5]))
    check("الواجهة لا تستورد sqlite3", not bad_imp, str(bad_imp))
    check("وحدات المنطق لا تستورد Flet", all("flet" not in imported_modules(parse(f)) for f in LOGIC_FILES if os.path.exists(os.path.join(ROOT, f))))
    check("وحدات الشاشات مستقلة: لا تستورد main ولا بعضها", all(
        not ({"main"} & imported_modules(parse(f))) and not any(
            isinstance(n, ast.ImportFrom) and (n.module or "").startswith("screens") for n in ast.walk(parse(f))) for f in SCREEN_FILES))
    check("لكل وحدة شاشات دالة register(app)", all(
        any(isinstance(n, ast.FunctionDef) and n.name == "register" and [a.arg for a in n.args.args] == ["app"] for n in parse(f).body)
        for f in SCREEN_FILES + ["ui_kit.py"]))
    sizes = {f: len(open(os.path.join(ROOT, f), encoding="utf-8").read().splitlines()) for f in UI_FILES}
    check("حجم main.py ≤ 200 سطر (نقطة دخول فقط)", sizes["main.py"] <= 200, str(sizes["main.py"]))
    check("لا وحدة واجهة تتجاوز 900 سطر", all(v <= 900 for v in sizes.values()), str(sizes))
    names = [n.name for f in SCREEN_FILES for n in ast.walk(parse(f)) if isinstance(n, ast.FunctionDef) and n.col_offset == 4]
    dup = {n for n in names if names.count(n) > 1}
    check("لا دالة شاشة مكرّرة الاسم بين الوحدات", not dup, str(dup))
    try:
        r = subprocess.run([sys.executable, "-m", "pyflakes"] + UI_FILES + LOGIC_FILES + ["keygen.py", "theme.py"], cwd=ROOT,
                           capture_output=True, text=True)
        if "No module named pyflakes" in r.stderr:
            print("SKIP pyflakes غير مثبّت (pip install pyflakes)")
        else:
            check("pyflakes: لا أسماء غير معرّفة ولا مستوردات غير مستعملة", not r.stdout.strip(), r.stdout.strip()[:300])
    except OSError:
        print("SKIP pyflakes")
    print("\n" + ("ALL PASSED" if not FAILS else f"FAILED: {FAILS}"))
    sys.exit(1 if FAILS else 0)


if __name__ == "__main__":
    main()
