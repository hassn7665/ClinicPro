# -*- coding: utf-8 -*-
"""
keygen.py — أداة مدير برنامج Clinic Pro (للمدير فقط — لا تضعها في التطبيق ولا ترفعها إلى GitHub).

تُصدر نوعين من الأكواد:
  1) كود التفعيل / التجديد  : مرتبط بمعرّف الجهاز، لمدة شهر أو 3 أو 6 أشهر أو سنة.
  2) رمز إعادة تعيين كلمة المرور : يُصدَر ردّاً على «رمز الطلب» الذي يرسله المستخدم.

الاستخدام السريع
────────────────
  python keygen.py                       ← واجهة رسومية (الأسهل). أول مرة تُولَّد المفاتيح تلقائياً — لا حاجة لأي خطوة يدوية.
  python keygen.py activate 3fa91c07 --plan 3        ← كود تفعيل لـ 3 أشهر
  python keygen.py reset  <رمز الطلب>                ← رمز إعادة تعيين كلمة المرور   (يرفض جهازاً لم تفعّله؛ --force لتجاوز التحذير)
  python keygen.py log                   ← سجل ما أُصدر
  python keygen.py menu                  ← قائمة نصية (بدون واجهة رسومية)
  python keygen.py init                  ← (اختياري) توليد المفاتيح يدوياً؛ يحدث تلقائياً عند أول تشغيل
  python keygen.py protect               ← تشفير admin_keys.json بعبارة مرور (موصى به بشدة؛ ويغيّر العبارة إن كان محمياً)
  python keygen.py clockfix <DEVICE_ID>  ← كود فك «قفل التاريخ» (عندما يُقفل الجهاز بسبب ضبط تاريخ خاطئ)

الملفات:
  admin_keys.json   ← المفاتيح الخاصة (سرّية جداً! محميّة بعبارة مرور بعد `protect`؛ احتفظ بنسخة احتياطية خارج الجهاز، ضياعها = لا يمكنك إصدار أي كود)
  public_keys.py    ← المفاتيح العامة (انسخه إلى مجلد التطبيق قبل بناء APK؛ آمن للنشر)
  issued_log.json   ← سجل الأكواد الصادرة (يمنع تكرار الرقم التسلسلي ويوثّق العمليات)
"""
import argparse
import getpass
import json
import os
import secrets
import sys
from datetime import datetime

import crypto_core as K
import license_core as LC

try:                                   # ألوان الهوية البصرية (نفس ملف التطبيق)
    import theme as TH
except ImportError:                    # احتياط إن نُسخت الأداة وحدها
    class TH:
        PRIMARY, DEEP, DEEP_HV, DARK = "#2A9D8F", "#1F7A72", "#175F59", "#12343B"
        BG, FIELD_BG, TEXT, MUTED = "#EFF7F6", "#F4FAF9", "#16393F", "#7D909A"
        BORDER, BORDER_STRONG, MINT, WHITE = "#E3EEEE", "#BFE0DB", "#E3F2F0", "#FFFFFF"
        DANGER = "#E5484D"

HERE = os.path.dirname(os.path.abspath(__file__))
KEYS = os.path.join(HERE, "admin_keys.json")
LOG = os.path.join(HERE, "issued_log.json")
PUBLIC_PY = os.path.join(HERE, "public_keys.py")

PLAN_NAMES = {1: "شهر واحد", 3: "3 أشهر", 6: "6 أشهر", 12: "سنة كاملة"}
ADMIN_ITER = 1_000_000          # اشتقاق مفتاح فك admin_keys.json من عبارة المرور (على جهاز المدير فقط)
MIN_ADMIN_PASS = 12
_PASS = {"v": None, "provider": None, "warned": False}


# ═══════════════ المفاتيح والسجل ═══════════════
def _write_public(sign_seed: bytes, box_priv: bytes):
    with open(PUBLIC_PY, "w", encoding="utf-8") as f:
        f.write('# -*- coding: utf-8 -*-\n"""المفاتيح العامة للمدير (آمنة للنشر). مُولَّد تلقائياً بواسطة keygen.py"""\n'
                f'SIGN_PUB = "{K.ed_pub(sign_seed).hex()}"   # التحقق من أكواد التفعيل (Ed25519)\n'
                f'BOX_PUB = "{K.x25519_pub(box_priv).hex()}"    # استرداد كلمة المرور (X25519)\n')


def _current_public():
    """المفاتيح العامة المكتوبة حالياً في public_keys.py (فارغة = لم تُولَّد بعد)."""
    try:
        with open(PUBLIC_PY, encoding="utf-8") as f:
            txt = f.read()
    except OSError:
        return "", ""
    import re
    g = lambda n: (re.search(n + r'\s*=\s*"([0-9a-fA-F]*)"', txt) or [None, ""])[1].lower()
    return g("SIGN_PUB"), g("BOX_PUB")


def set_passphrase_provider(fn):
    """الواجهة الرسومية تسجّل دالة تسأل المستخدم (fn(prompt) -> نص أو None)."""
    _PASS["provider"] = fn


def _ask_pass(prompt: str) -> str:
    if _PASS["provider"]:
        return _PASS["provider"](prompt) or ""
    env = os.environ.get("CLINICPRO_ADMIN_PASS")
    if env:
        return env
    if sys.stdin and sys.stdin.isatty():
        return getpass.getpass(prompt)
    raise SystemExit("مفاتيح المدير محميّة بعبارة مرور ولا يمكن سؤالك عنها هنا. شغّل الأداة من الطرفية "
                     "(أو عرّف المتغير CLINICPRO_ADMIN_PASS).")


def _read_keys_file() -> dict:
    with open(KEYS, encoding="utf-8") as f:
        return json.load(f)


def keys_protected() -> bool:
    try:
        return bool(_read_keys_file().get("enc"))
    except (OSError, ValueError):
        return False


def _admin_kek(passphrase: str, salt: bytes, it: int) -> bytes:
    return K.kdf_password(passphrase, salt, it, "admin-keys")


def _load_secret():
    """(sign_seed, box_priv) من admin_keys.json — يفكّ التشفير بعبارة المرور إن كان الملف محمياً."""
    k = _read_keys_file()
    if not k.get("enc"):
        return bytes.fromhex(k["sign_seed"]), bytes.fromhex(k["box_priv"])
    salt, blob, it = bytes.fromhex(k["salt"]), bytes.fromhex(k["blob"]), int(k["iter"])
    for _ in range(3):
        pw = _PASS["v"] or _ask_pass("عبارة مرور مفاتيح المدير: ")
        try:
            sec = json.loads(K.open_sealed(_admin_kek(pw, salt, it), blob, aad=b"admin-keys"))
        except (K.CryptoError, ValueError):
            _PASS["v"] = None
            if _PASS["provider"] is None and not (sys.stdin and sys.stdin.isatty()):
                break
            print("✗ عبارة المرور غير صحيحة", file=sys.stderr)
            continue
        _PASS["v"] = pw
        return bytes.fromhex(sec["sign_seed"]), bytes.fromhex(sec["box_priv"])
    raise SystemExit("عبارة مرور مفاتيح المدير غير صحيحة.")


def _write_keys_file(data: dict):
    tmp = KEYS + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, KEYS)


def _protected_doc(sign_seed: bytes, box_priv: bytes, passphrase: str, created: str) -> dict:
    """مستند admin_keys.json المشفّر (المفاتيح العامة تبقى ظاهرة ليعمل ensure_keys دون عبارة المرور)."""
    if len(passphrase or "") < MIN_ADMIN_PASS:
        raise ValueError(f"عبارة المرور قصيرة (الحد الأدنى {MIN_ADMIN_PASS} خانة — استخدم جملة)")
    salt = secrets.token_bytes(16)
    blob = K.seal(_admin_kek(passphrase, salt, ADMIN_ITER),
                  json.dumps({"sign_seed": sign_seed.hex(), "box_priv": box_priv.hex()}).encode(), aad=b"admin-keys")
    return {"v": 2, "enc": True, "salt": salt.hex(), "iter": ADMIN_ITER, "blob": blob.hex(),
            "sign_pub": K.ed_pub(sign_seed).hex(), "box_pub": K.x25519_pub(box_priv).hex(), "created": created}


def protect_keys(passphrase: str):
    """يشفّر admin_keys.json بعبارة مرور (أو يغيّر العبارة إن كان محمياً). يتحقق من فك التشفير قبل الاستبدال."""
    sign_seed, box_priv = _load_secret()
    created = _read_keys_file().get("created") or datetime.now().isoformat(timespec="seconds")
    doc = _protected_doc(sign_seed, box_priv, passphrase, created)
    chk = json.loads(K.open_sealed(_admin_kek(passphrase, bytes.fromhex(doc["salt"]), ADMIN_ITER),
                                   bytes.fromhex(doc["blob"]), aad=b"admin-keys"))
    if (bytes.fromhex(chk["sign_seed"]), bytes.fromhex(chk["box_priv"])) != (sign_seed, box_priv):
        raise SystemExit("فشل التحقق من التشفير؛ لم يُغيَّر الملف.")
    _write_keys_file(doc)
    _PASS["v"] = passphrase


def ensure_keys() -> str:
    """يضمن وجود المفاتيح دون أي تدخل. يعيد: 'created' | 'repaired' | 'ok'.
       • لا مفاتيح أصلاً           → تُولَّد وتُكتب public_keys.py تلقائياً.
       • المفتاح الخاص موجود وpublic_keys.py فارغ → يُعاد كتابته من المفتاح الخاص (بلا تغيير المفاتيح).
       • public_keys.py مملوء لكن المفتاح الخاص مفقود → خطأ صريح (لا نولّد مفاتيح جديدة فنُيتّم الحسابات القائمة)."""
    pub_sign, pub_box = _current_public()
    if os.path.exists(KEYS):
        k = _read_keys_file()
        if k.get("enc"):                         # الملف محمي: المفاتيح العامة مخزّنة ظاهرة، لا نحتاج عبارة المرور للمقارنة
            want = (k["sign_pub"], k["box_pub"])
        else:
            sign_seed, box_priv = bytes.fromhex(k["sign_seed"]), bytes.fromhex(k["box_priv"])
            want = (K.ed_pub(sign_seed).hex(), K.x25519_pub(box_priv).hex())
        if (pub_sign, pub_box) == want:
            return "ok"
        if not pub_sign and not pub_box:
            sign_seed, box_priv = _load_secret()
            _write_public(sign_seed, box_priv)
            LC.reload_keys()
            return "repaired"
        raise SystemExit("public_keys.py لا يطابق admin_keys.json! انسخ public_keys.py الصحيح إلى التطبيق، "
                         "أو أعد توليد المفاتيح (init --force) إن كنت في مرحلة التجربة فقط.")
    if pub_sign or pub_box:
        raise SystemExit("ملف المفاتيح الخاص admin_keys.json مفقود بينما public_keys.py يحوي مفاتيح! "
                         "استرجع admin_keys.json من نسختك الاحتياطية. (لن أولّد مفاتيح جديدة حتى لا تتعطل الحسابات القائمة)")
    init_keys()
    return "created"


def init_keys(force=False, passphrase: str | None = None):
    if os.path.exists(KEYS) and not force:
        raise SystemExit("admin_keys.json موجود مسبقاً. إعادة توليد المفاتيح تُبطل كل الأكواد الصادرة وتعطّل "
                         "استرداد كلمات المرور للحسابات القائمة. إن كنت متأكداً أضف --force")
    sign_seed, box_priv = secrets.token_bytes(32), secrets.token_bytes(32)
    created = datetime.now().isoformat(timespec="seconds")
    if passphrase:
        _write_keys_file(_protected_doc(sign_seed, box_priv, passphrase, created))
        _PASS["v"] = passphrase
    else:        # التوليد التلقائي من التطبيق على حاسوب المطوّر (بلا لوحة مفاتيح): يُحمى لاحقاً بـ protect
        _write_keys_file({"sign_seed": sign_seed.hex(), "box_priv": box_priv.hex(), "created": created})
    _write_public(sign_seed, box_priv)
    LC.reload_keys()
    return {"sign_seed": sign_seed.hex(), "box_priv": box_priv.hex(), "created": created}


def load_keys():
    created = ensure_keys()
    if created != "ok":
        print("✓ تم إنشاء مفاتيح المدير تلقائياً — احتفظ بنسخة احتياطية من admin_keys.json" if created == "created"
              else "✓ تم إصلاح public_keys.py من مفتاح المدير الموجود")
    if not keys_protected() and not _PASS["warned"]:
        _PASS["warned"] = True
        print("⚠ مفاتيح المدير غير محميّة بعبارة مرور (admin_keys.json نصّ صريح). شغّل: python keygen.py protect",
              file=sys.stderr)
    secret = _load_secret()
    LC.reload_keys()
    return secret


def read_log():
    try:
        with open(LOG, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


def write_log(rows):
    with open(LOG, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def clean_device(dev: str) -> str:
    d = (dev or "").strip().lower().replace(" ", "")
    if len(d) != 8 or any(c not in "0123456789abcdef" for c in d):
        raise ValueError("معرّف الجهاز يجب أن يكون 8 خانات (أرقام وحروف a-f) كما يظهر في شاشة التفعيل")
    return d


# ═══════════════ العمليات ═══════════════
def issue_activation(device: str, months: int, serial: int | None = None, note: str = "") -> dict:
    sign_seed, _ = load_keys()
    dev = clean_device(device)
    if months not in LC.PLANS:
        raise ValueError("الخطة يجب أن تكون 1 أو 3 أو 6 أو 12 شهراً")
    rows = read_log()
    last = max([r["serial"] for r in rows if r["kind"] in ("activation", "clockfix") and r["device"] == dev], default=0)
    serial = serial or last + 1
    if serial <= last:
        raise ValueError(f"الرقم التسلسلي {serial} ليس أحدث من آخر رقم صادر لهذا الجهاز ({last}).")
    code = LC.make_code(sign_seed, dev, serial, months)
    LC.parse_code(code, dev)                                   # فحص ذاتي: يجب أن يقبله التطبيق
    rec = {"time": datetime.now().isoformat(timespec="seconds"), "kind": "activation", "device": dev,
           "serial": serial, "months": months, "note": note.strip(), "code": code}
    rows.append(rec)
    write_log(rows)
    return rec


def issue_clock_fix(device: str, note: str = "") -> dict:
    """كود فك «قفل التاريخ»: لا يمدّد الاشتراك. يحمل تاريخ إصداره الحقيقي موقّعاً، فلا يعمل على جهاز تاريخه متأخر عنه.
    يُرقَّم ضمن نفس تسلسل الجهاز، فأرسل أكواد الجهاز بترتيب إصدارها."""
    sign_seed, _ = load_keys()
    dev = clean_device(device)
    rows = read_log()
    last = max([r["serial"] for r in rows if r["kind"] in ("activation", "clockfix") and r["device"] == dev], default=0)
    serial = last + 1
    code = LC.make_code(sign_seed, dev, serial, LC.CLOCK_FIX)
    LC.parse_code_ex(code, dev)                                # فحص ذاتي
    rec = {"time": datetime.now().isoformat(timespec="seconds"), "kind": "clockfix", "device": dev,
           "serial": serial, "months": 0, "note": note.strip(), "code": code}
    rows.append(rec)
    write_log(rows)
    return rec


class UnknownDevice(ValueError):
    """طلب إعادة تعيين من جهاز لم يصدر له أي تفعيل من هذه الأداة. .device = معرّف الجهاز (hex)."""

    def __init__(self, device):
        super().__init__(f"الجهاز {device.upper()} لم يصدر له أي تفعيل من هذه الأداة (لا سجل له). قد يكون الطلب من شخص ليس عميلك، "
                         "أو من جهاز لم تفعّله أنت. تحقق من هوية صاحب الطلب بوسيلة أخرى ثم أعد الإصدار بخيار التجاوز (--force).")
        self.device = device


def device_history(dev: str):
    """سجل التفعيلات الصادرة لجهاز (الأقدم أولاً)."""
    return [r for r in read_log() if r.get("device") == dev and r.get("kind") in ("activation", "clockfix")]


def issue_reset(request_code: str, note: str = "", force: bool = False) -> dict:
    """يصدر رمز إعادة التعيين. يرفض (UnknownDevice) إن لم يكن للجهاز أي تفعيل صادر منك، ما لم يُمرَّر force=True،
    ويُرفق باسم العميل وتاريخ آخر تفعيل ليتحقق المدير بنفسه من الهوية."""
    _, box_priv = load_keys()
    try:
        reply, dev = K.admin_reset_respond(box_priv, K.x25519_pub(box_priv), request_code)
    except K.CryptoError as ex:
        raise ValueError(f"رمز الطلب غير صالح: {ex}")
    hist = device_history(dev)
    if not hist and not force:
        raise UnknownDevice(dev)
    last_act = next((r for r in reversed(hist) if r["kind"] == "activation"), hist[-1] if hist else None)
    client = next((r["note"] for r in reversed(hist) if r.get("note")), "")
    rec = {"time": datetime.now().isoformat(timespec="seconds"), "kind": "reset", "device": dev,
           "serial": 0, "months": 0, "note": note.strip(), "code": reply, "known": bool(hist), "client": client,
           "last_activation": last_act["time"] if last_act else ""}
    rows = read_log()
    rows.append(rec)
    write_log(rows)
    return rec


def describe(rec: dict) -> str:
    if rec["kind"] == "activation":
        return (f"الجهاز        : {rec['device'].upper()}\nالخطة         : {PLAN_NAMES[rec['months']]}\n"
                f"الرقم التسلسلي: {rec['serial']}\nيجب تفعيله خلال {LC.MAX_CODE_AGE_DAYS} يوماً من اليوم\n\n"
                f"كود التفعيل:\n{rec['code']}")
    if rec["kind"] == "clockfix":
        return (f"الجهاز        : {rec['device'].upper()}\nالرقم التسلسلي: {rec['serial']}\n\n"
                f"كود فك قفل التاريخ (لا يمدّد الاشتراك؛ يُلصق في شاشة التفعيل — صالح {LC.MAX_CODE_AGE_DAYS} يوماً):\n{rec['code']}")
    who = (f"العميل (من سجل التفعيل): {rec.get('client') or 'بلا اسم مسجّل'} — آخر تفعيل: {(rec.get('last_activation') or '')[:10]}"
           if rec.get("known", True) else "⚠ جهاز غير معروف في سجلّك — صدر الرمز بتجاوز صريح منك")
    return (f"الجهاز: {rec['device'].upper()}\n{who}\n\nرمز إعادة التعيين "
            f"(يُلصق في شاشة «نسيت كلمة المرور» ثم تُختار كلمة مرور جديدة):\n{rec['code']}")


# ═══════════════ قائمة نصية ═══════════════
def cli_protect():
    p1 = getpass.getpass(f"عبارة المرور الجديدة ({MIN_ADMIN_PASS} خانة على الأقل — جملة طويلة أفضل): ")
    if p1 != getpass.getpass("أعد كتابتها: "):
        raise ValueError("العبارتان غير متطابقتين")
    protect_keys(p1)
    print("✓ تم تشفير admin_keys.json. لا تنسَ العبارة: لا يمكن استرجاعها، وضياعها = ضياع المفاتيح.\n"
          "  انسخ الملف المشفّر (آمن للتخزين السحابي) إلى مكان خارج هذا الحاسوب.")


def cli_menu():
    while True:
        print("\n══ أداة مدير Clinic Pro ══\n1) كود تفعيل / تجديد\n2) رمز إعادة تعيين كلمة المرور\n3) السجل\n"
              "4) كود فك قفل التاريخ\n5) حماية مفاتيح المدير بعبارة مرور\n0) خروج")
        c = input("اختر: ").strip()
        try:
            if c == "1":
                dev = input("معرّف الجهاز (8 خانات): ")
                m = int(input("المدة بالأشهر [1/3/6/12]: "))
                print("\n" + describe(issue_activation(dev, m, note=input("ملاحظة (اسم العميل) اختياري: "))))
            elif c == "2":
                req = input("الصق رمز الطلب (سطر واحد) ثم Enter:\n> ")
                if input("هل تحققت من هوية صاحب الحساب؟ (y/n): ").lower() == "y":
                    note_ = input("ملاحظة اختياري: ")
                    try:
                        rec_ = issue_reset(req, note=note_)
                    except UnknownDevice as ex:
                        print("⚠ " + str(ex))
                        if input("اكتب YES (بالأحرف الكبيرة) لتجاوز هذا التحذير: ") != "YES":
                            continue
                        rec_ = issue_reset(req, note=note_, force=True)
                    print("\n" + describe(rec_))
            elif c == "4":
                print("\n" + describe(issue_clock_fix(input("معرّف الجهاز (8 خانات): "), note=input("ملاحظة اختياري: "))))
            elif c == "5":
                cli_protect()
            elif c == "3":
                for r in read_log()[-20:]:
                    print(r["time"], r["kind"], r["device"], r["serial"] or "", r["months"] or "", r["note"])
            elif c == "0":
                return
        except (ValueError, SystemExit) as ex:
            print("✗", ex)


# ═══════════════ الواجهة الرسومية ═══════════════
def _apply_style(root, tk, ttk):
    """هوية Clinic Pro على واجهة المدير (شكل فقط، لا يمسّ أي وظيفة)."""
    T = TH
    root.configure(bg=T.BG)
    st = ttk.Style(root)
    try:
        st.theme_use("clam")
    except tk.TclError:
        pass
    base = ("Segoe UI", 11)
    st.configure(".", background=T.BG, foreground=T.TEXT, font=base, bordercolor=T.BORDER, focuscolor=T.BG)
    st.configure("TFrame", background=T.BG)
    st.configure("TLabel", background=T.BG, foreground=T.TEXT)
    st.configure("TButton", background=T.DEEP, foreground=T.WHITE, borderwidth=0, padding=(18, 9),
                 font=("Segoe UI", 11, "bold"), relief="flat")
    st.map("TButton", background=[("pressed", T.DEEP_HV), ("active", T.DEEP_HV), ("disabled", T.BORDER)],
           foreground=[("disabled", T.MUTED)])
    st.configure("TEntry", fieldbackground=T.FIELD_BG, foreground=T.TEXT, bordercolor=T.BORDER,
                 lightcolor=T.BORDER, darkcolor=T.BORDER, padding=8)
    st.map("TEntry", bordercolor=[("focus", T.PRIMARY)], lightcolor=[("focus", T.PRIMARY)],
           darkcolor=[("focus", T.PRIMARY)])
    st.configure("TRadiobutton", background=T.BG, foreground=T.TEXT, font=base)
    st.map("TRadiobutton", background=[("active", T.BG)], foreground=[("selected", T.DEEP)])
    st.configure("TNotebook", background=T.BG, borderwidth=0, tabmargins=(2, 4, 2, 0))
    st.configure("TNotebook.Tab", background=T.MINT, foreground=T.MUTED, padding=(16, 9),
                 font=("Segoe UI", 11, "bold"), borderwidth=0)
    st.map("TNotebook.Tab", background=[("selected", T.WHITE)], foreground=[("selected", T.DEEP)])
    st.configure("Treeview", background=T.WHITE, fieldbackground=T.WHITE, foreground=T.TEXT, rowheight=28,
                 bordercolor=T.BORDER, borderwidth=0)
    st.configure("Treeview.Heading", background=T.MINT, foreground=T.DEEP, font=("Segoe UI", 10, "bold"),
                 padding=6, relief="flat")
    st.map("Treeview", background=[("selected", T.MINT)], foreground=[("selected", T.DARK)])
    for opt, val in (("background", T.WHITE), ("foreground", T.TEXT), ("relief", "flat"), ("highlightThickness", 1),
                     ("highlightBackground", T.BORDER), ("highlightColor", T.PRIMARY), ("padX", 8), ("padY", 6),
                     ("selectBackground", T.MINT), ("selectForeground", T.DARK), ("insertBackground", T.PRIMARY)):
        root.option_add(f"*Text.{opt}", val)


def gui():
    import tkinter as tk
    from tkinter import messagebox, ttk

    root = tk.Tk()
    root.title("Clinic Pro — مدير إصدار الأكواد")
    root.geometry("780x720")
    font = ("Segoe UI", 11)
    _apply_style(root, tk, ttk)
    # شريط علوي بالهوية: الأيقونة + الاسم
    banner = tk.Frame(root, bg=TH.MINT, highlightthickness=1, highlightbackground=TH.BORDER_STRONG)
    banner.pack(fill="x")
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.png")
    try:
        img = tk.PhotoImage(file=icon_path)
        root._icon_refs = [img, img.subsample(max(img.width() // 64, 1)),
                           img.subsample(max(img.width() // 56, 1))]   # مراجع تمنع حذف الصور من الذاكرة
        root.iconphoto(True, root._icon_refs[1])
        tk.Label(banner, image=root._icon_refs[2], bg=TH.MINT).pack(side="right", padx=14, pady=10)
    except Exception:
        pass
    box = tk.Frame(banner, bg=TH.MINT)
    box.pack(side="right", pady=10)
    tk.Label(box, text="Clinic Pro", bg=TH.MINT, fg=TH.DARK, font=("Segoe UI", 18, "bold")).pack(anchor="e")
    tk.Label(box, text="مدير الإصدار — أكواد التفعيل وإعادة التعيين", bg=TH.MINT, fg=TH.MUTED,
             font=("Segoe UI", 10)).pack(anchor="e")
    status = ttk.Frame(root)
    status.pack(fill="x", padx=12, pady=(10, 0))
    status_lbl = ttk.Label(status, text="", font=("Segoe UI", 10))
    status_lbl.pack(side="right")

    from tkinter import simpledialog
    set_passphrase_provider(lambda prompt: simpledialog.askstring("عبارة المرور", prompt, show="*", parent=root))

    def refresh_status():
        status_lbl.config(text=("✓ مفاتيح المدير جاهزة ومحميّة بعبارة مرور" if keys_protected()
                                else "⚠ مفاتيح المدير جاهزة لكن غير محميّة بعبارة مرور"))

    def protect_gui():
        a = simpledialog.askstring("حماية المفاتيح", f"اختر عبارة مرور ({MIN_ADMIN_PASS} خانة على الأقل — جملة طويلة أفضل):",
                                   show="*", parent=root)
        if not a:
            return
        if a != simpledialog.askstring("حماية المفاتيح", "أعد كتابة العبارة:", show="*", parent=root):
            return messagebox.showerror("خطأ", "العبارتان غير متطابقتين")
        try:
            protect_keys(a)
        except (ValueError, SystemExit) as ex:
            return messagebox.showerror("خطأ", str(ex))
        refresh_status()
        messagebox.showinfo("تم", "تم تشفير admin_keys.json.\nلا يمكن استرجاع العبارة إن نسيتها، وضياعها = ضياع المفاتيح.\n"
                                  "خذ الآن «نسخة احتياطية من المفاتيح» (الملف المشفّر آمن للتخزين خارج الجهاز).")

    def backup_keys():
        from tkinter import filedialog
        import shutil
        if not keys_protected() and not messagebox.askyesno(
                "المفاتيح غير محميّة", "الملف نصّ صريح: من يحصل على النسخة يستطيع إصدار أكواد باسمك وفتح بيانات العملاء.\n"
                                       "الأفضل إلغاء هذه النسخة وحماية المفاتيح أولاً. هل تريد المتابعة رغم ذلك؟"):
            return
        dst = filedialog.asksaveasfilename(title="احفظ نسخة احتياطية من مفاتيح المدير (في مكان آمن)",
                                           initialfile="admin_keys_BACKUP.json", defaultextension=".json")
        if dst:
            shutil.copyfile(KEYS, dst)
            messagebox.showinfo("تم", "تم حفظ النسخة الاحتياطية.\nاحتفظ بها في مكان آمن (فلاش/مدير كلمات مرور) — "
                                "من يملكها يستطيع إصدار أكواد باسمك.")
    ttk.Button(status, text="نسخة احتياطية من المفاتيح", command=backup_keys).pack(side="left")
    ttk.Button(status, text="حماية المفاتيح بعبارة مرور", command=protect_gui).pack(side="left", padx=8)
    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True, padx=10, pady=10)

    def copy(txt):
        root.clipboard_clear()
        root.clipboard_append(txt)
        messagebox.showinfo("تم", "تم نسخ الكود إلى الحافظة")

    def out_box(parent):
        t = tk.Text(parent, height=11, wrap="char", font=("Consolas", 11))
        t.pack(fill="both", expand=True, padx=8, pady=6)
        return t

    def show(t, rec):
        t.delete("1.0", "end")
        t.insert("1.0", describe(rec))
        t.rec = rec

    # ── تفعيل / تجديد ──
    f1 = ttk.Frame(nb)
    nb.add(f1, text="  تفعيل / تجديد  ")
    ttk.Label(f1, text="معرّف الجهاز (8 خانات كما يظهر في شاشة التفعيل):", font=font).pack(anchor="e", padx=10, pady=(14, 2))
    dev_var = tk.StringVar()
    ttk.Entry(f1, textvariable=dev_var, font=("Consolas", 16), justify="center").pack(fill="x", padx=10)
    ttk.Label(f1, text="مدة الاشتراك:", font=font).pack(anchor="e", padx=10, pady=(12, 2))
    plan = tk.IntVar(value=12)
    pf = ttk.Frame(f1)
    pf.pack(anchor="e", padx=10)
    for m in (12, 6, 3, 1):
        ttk.Radiobutton(pf, text=PLAN_NAMES[m], value=m, variable=plan).pack(side="right", padx=8)
    ttk.Label(f1, text="ملاحظة (اسم العميل — اختياري):", font=font).pack(anchor="e", padx=10, pady=(12, 2))
    note1 = tk.StringVar()
    ttk.Entry(f1, textvariable=note1, font=font, justify="right").pack(fill="x", padx=10)
    out1 = out_box(f1)

    def do_act():
        try:
            show(out1, issue_activation(dev_var.get(), plan.get(), note=note1.get()))
        except (ValueError, SystemExit) as ex:
            messagebox.showerror("خطأ", str(ex))
    bf = ttk.Frame(f1)
    bf.pack(pady=4)
    ttk.Button(bf, text="إصدار كود التفعيل", command=do_act).pack(side="right", padx=6)
    ttk.Button(bf, text="نسخ الكود", command=lambda: copy(out1.rec["code"]) if hasattr(out1, "rec") else None).pack(side="right")

    def do_clockfix():
        if not messagebox.askyesno("فك قفل التاريخ", "هذا الكود لا يمدّد الاشتراك، ويفكّ فقط قفل «تاريخ الجهاز أقدم من آخر استخدام».\n"
                                   "تأكد أن العميل يستطيع فعلاً ضبط تاريخ جهازه الصحيح. المتابعة؟"):
            return
        try:
            show(out1, issue_clock_fix(dev_var.get(), note=note1.get()))
        except (ValueError, SystemExit) as ex:
            messagebox.showerror("خطأ", str(ex))
    ttk.Button(bf, text="كود فك قفل التاريخ", command=do_clockfix).pack(side="right", padx=6)

    # ── إعادة تعيين كلمة المرور ──
    f2 = ttk.Frame(nb)
    nb.add(f2, text="  إعادة تعيين كلمة المرور  ")
    ttk.Label(f2, text="الصق «رمز الطلب» الذي أرسله المستخدم:", font=font).pack(anchor="e", padx=10, pady=(14, 2))
    req_t = tk.Text(f2, height=6, wrap="char", font=("Consolas", 10))
    req_t.pack(fill="x", padx=10)
    ttk.Label(f2, text="ملاحظة (اختياري):", font=font).pack(anchor="e", padx=10, pady=(8, 2))
    note2 = tk.StringVar()
    ttk.Entry(f2, textvariable=note2, font=font, justify="right").pack(fill="x", padx=10)
    out2 = out_box(f2)

    def do_reset():
        if not messagebox.askyesno("تأكيد الهوية", "رمز الإعادة يمكّن صاحبه من فتح بيانات المرضى على ذلك الجهاز.\n"
                                   "هل تحققت من هوية طالب الإعادة (اتصال/معرفة شخصية)؟"):
            return
        try:
            try:
                rec = issue_reset(req_t.get("1.0", "end"), note=note2.get())
            except UnknownDevice as ex:
                if not messagebox.askyesno("جهاز غير معروف", str(ex) + "\n\nهل تريد التجاوز وإصدار الرمز رغم ذلك؟",
                                           icon="warning", default="no"):
                    return
                rec = issue_reset(req_t.get("1.0", "end"), note=note2.get(), force=True)
            show(out2, rec)
        except (ValueError, SystemExit) as ex:
            messagebox.showerror("خطأ", str(ex))
    bf2 = ttk.Frame(f2)
    bf2.pack(pady=4)
    ttk.Button(bf2, text="إصدار رمز الإعادة", command=do_reset).pack(side="right", padx=6)
    ttk.Button(bf2, text="نسخ الرمز", command=lambda: copy(out2.rec["code"]) if hasattr(out2, "rec") else None).pack(side="right")

    # ── السجل ──
    f3 = ttk.Frame(nb)
    nb.add(f3, text="  السجل  ")
    cols = ("time", "kind", "device", "serial", "plan", "note")
    tv = ttk.Treeview(f3, columns=cols, show="headings", height=18)
    for c, t, w in zip(cols, ("الوقت", "النوع", "الجهاز", "التسلسلي", "الخطة", "ملاحظة"), (150, 90, 90, 70, 90, 220)):
        tv.heading(c, text=t)
        tv.column(c, width=w, anchor="center")
    tv.pack(fill="both", expand=True, padx=8, pady=8)

    def refresh(_=None):
        tv.delete(*tv.get_children())
        for r in reversed(read_log()):
            tv.insert("", "end", values=(r["time"].replace("T", " "),
                                         {"activation": "تفعيل", "clockfix": "فك التاريخ"}.get(r["kind"], "إعادة تعيين"),
                                         r["device"].upper(), r["serial"] or "", PLAN_NAMES.get(r["months"], ""), r["note"]))
    nb.bind("<<NotebookTabChanged>>", refresh)
    try:
        created = ensure_keys()
        refresh_status()
        if created == "created":
            messagebox.showinfo("إعداد تلقائي", "تم إنشاء مفاتيح المدير تلقائياً.\n\n"
                                "• public_keys.py (عام) أُنشئ بجانب التطبيق — ارفعه مع المشروع عند بناء APK.\n"
                                "• admin_keys.json (سرّي) — احمِه بعبارة مرور ثم خذ نسخة احتياطية في مكان آمن.")
        if not keys_protected() and messagebox.askyesno("حماية المفاتيح",
                                                         "مفاتيحك الآن نصّ صريح على القرص. هل تريد حمايتها بعبارة مرور الآن؟ (موصى به بشدة)"):
            protect_gui()
    except SystemExit as ex:
        status_lbl.config(text="✗ مشكلة في المفاتيح")
        messagebox.showwarning("المفاتيح", str(ex))
    root.mainloop()


def main():
    ap = argparse.ArgumentParser(description="أداة مدير Clinic Pro")
    sub = ap.add_subparsers(dest="cmd")
    i = sub.add_parser("init", help="توليد مفاتيح المدير (مرة واحدة)")
    i.add_argument("--force", action="store_true")
    a = sub.add_parser("activate", help="إصدار كود تفعيل")
    a.add_argument("device_id")
    a.add_argument("--plan", type=int, default=12, choices=sorted(LC.PLANS), help="المدة بالأشهر: 1 / 3 / 6 / 12")
    a.add_argument("--serial", type=int, default=None)
    a.add_argument("--note", default="")
    r = sub.add_parser("reset", help="إصدار رمز إعادة تعيين كلمة المرور")
    r.add_argument("request_code")
    r.add_argument("--note", default="")
    r.add_argument("--force", action="store_true", help="تجاوز تحذير «جهاز لم يصدر له تفعيل»")
    c = sub.add_parser("clockfix", help="إصدار كود فك قفل التاريخ لجهاز")
    c.add_argument("device_id")
    c.add_argument("--note", default="")
    sub.add_parser("protect", help="تشفير admin_keys.json بعبارة مرور (أو تغيير العبارة)")
    sub.add_parser("log", help="عرض السجل")
    sub.add_parser("menu", help="قائمة نصية")
    args = ap.parse_args()
    try:
        if args.cmd == "init":
            pw = None
            if sys.stdin and sys.stdin.isatty():
                pw = getpass.getpass(f"عبارة مرور لحماية المفاتيح ({MIN_ADMIN_PASS} خانة على الأقل، أو Enter لتخطّي): ") or None
                if pw and pw != getpass.getpass("أعد كتابتها: "):
                    raise ValueError("العبارتان غير متطابقتين")
            init_keys(args.force, pw)
            print("✓ تم توليد المفاتيح.\n  - admin_keys.json : سرّي، احتفظ بنسخة احتياطية آمنة ولا ترفعه إلى GitHub\n"
                  "  - public_keys.py  : ارفعه مع المشروع عند بناء التطبيق")
        elif args.cmd == "activate":
            print(describe(issue_activation(args.device_id, args.plan, args.serial, args.note)))
        elif args.cmd == "reset":
            print(describe(issue_reset(args.request_code, args.note, args.force)))
        elif args.cmd == "clockfix":
            print(describe(issue_clock_fix(args.device_id, args.note)))
        elif args.cmd == "protect":
            cli_protect()
        elif args.cmd == "log":
            for rec in read_log():
                print(rec["time"], rec["kind"], rec["device"], rec["serial"] or "-", rec["months"] or "-", rec["note"])
        elif args.cmd == "menu":
            cli_menu()
        else:
            try:
                gui()
            except Exception as ex:          # لا يوجد Tkinter/شاشة
                print("تعذّر فتح الواجهة الرسومية:", ex, "\nاستخدم: python keygen.py menu")
    except ValueError as ex:
        sys.exit(f"✗ {ex}")


if __name__ == "__main__":
    main()
