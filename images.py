# -*- coding: utf-8 -*-
"""
images.py — تصغير صور المرضى عند الإدخال وإنشاء مصغّرات للعرض.

المشكلة: صور الكاميرا (3–8 ميغابايت) كانت تُخزَّن كما هي وتُرمَّز base64 كاملةً في الواجهة لعرض بلاطة صغيرة.
الحل: عند الحفظ تُصغَّر الصورة إلى ≤ MAX_SIDE بكسل (JPEG) مع تدوير EXIF ثم **إزالة بيانات EXIF (ومنها إحداثيات GPS)**،
وتُنشأ مصغّرة THUMB بكسل تُستعمل في القوائم والبلاطات؛ والأصل المُصغَّر يُفتح في شاشة العارض فقط.

يعتمد التصغير على Pillow إن توفّر. **تجريد البيانات الوصفية (EXIF/GPS/XMP/IPTC/تعليقات) لا يعتمد عليها**: دوال strip_metadata
بايثون صافية تعمل دائماً (JPEG وPNG وWebP)، فلا تُخزَّن إحداثيات موقع المريض حتى في بناء بلا Pillow. الوحيد الباقي من EXIF في JPEG
هو وسم الاتجاه (Orientation) كي لا تظهر الصورة مقلوبة. لا يُضاف Pillow إلى requirements تلقائياً: راجع PHASE0_CHECKLIST_AR.md.
"""
import io
import struct

try:
    from PIL import Image, ImageOps
    import PIL
    PIL_OK, PIL_VERSION = True, getattr(PIL, "__version__", "?")
except Exception:                                   # الحزمة غير مثبّتة أو لا عجلة لها على هذه المنصة
    Image = ImageOps = None
    PIL_OK, PIL_VERSION = False, ""

MAX_SIDE = 1600          # أكبر ضلع للصورة المحفوظة
THUMB = 360              # أكبر ضلع للمصغّرة
FULL_QUALITY, THUMB_QUALITY = 85, 72
MAX_PIXELS = 60_000_000  # حماية من الصور الضخمة جداً (قنبلة فك الضغط)


def sniff(data: bytes) -> str:
    """'jpeg' | 'png' | 'webp' | 'gif' | ''  (من البصمة لا من الامتداد)."""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:4] == b"GIF8":
        return "gif"
    return ""


def _flatten(im):
    """RGB دائماً (الشفافية تُسطَّح على خلفية بيضاء) كي يصح حفظها JPEG."""
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        im = im.convert("RGBA")
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    return im.convert("RGB") if im.mode != "RGB" else im


def _jpeg(im, q) -> bytes:
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=q, optimize=True)
    return buf.getvalue()


# ───────────────────────── تجريد البيانات الوصفية (بايثون صافية) ─────────────────────────
_PNG_DROP = {b"eXIf", b"tEXt", b"zTXt", b"iTXt", b"tIME"}


def _exif_orientation(payload: bytes):
    """وسم الاتجاه (1..8) من حمولة APP1 «Exif\\0\\0»، أو None."""
    try:
        t = payload[6:]
        e = "<" if t[:2] == b"II" else ">" if t[:2] == b"MM" else None
        if e is None:
            return None
        off = struct.unpack(e + "I", t[4:8])[0]
        n = struct.unpack(e + "H", t[off:off + 2])[0]
        for k in range(min(n, 64)):
            ent = t[off + 2 + 12 * k: off + 14 + 12 * k]
            if len(ent) == 12 and struct.unpack(e + "H", ent[:2])[0] == 0x0112:
                v = struct.unpack(e + "H", ent[8:10])[0]
                return v if 1 <= v <= 8 else None
    except (struct.error, IndexError):
        pass
    return None


def _orientation_app1(v: int) -> bytes:
    """APP1 أدنى لا يحوي إلا الاتجاه (لا GPS ولا وقت ولا طراز جهاز)."""
    tiff = b"MM\x00\x2a\x00\x00\x00\x08" + b"\x00\x01" + b"\x01\x12\x00\x03\x00\x00\x00\x01" + struct.pack(">H", v) + b"\x00\x00" + b"\x00\x00\x00\x00"
    body = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + struct.pack(">H", len(body) + 2) + body


def _jpeg_strip(d: bytes) -> bytes:
    if d[:2] != b"\xff\xd8":
        return d
    segs, i, orient, n = [], 2, None, len(d)
    while i < n:
        if d[i] != 0xFF:
            return d                                     # بنية غير متوقعة: لا نلمس الملف
        while i + 1 < n and d[i + 1] == 0xFF:            # بايتات حشو
            i += 1
        if i + 1 >= n:
            return d
        m = d[i + 1]
        if m == 0xDA:                                    # بدء المسح: الباقي بيانات الصورة كما هي
            segs.append(d[i:])
            i = n
            break
        if m == 0xD9 or m == 0x01 or 0xD0 <= m <= 0xD8:  # علامات بلا طول
            segs.append(d[i:i + 2])
            i += 2
            if m == 0xD9:
                break
            continue
        if i + 4 > n:
            return d
        ln = struct.unpack(">H", d[i + 2:i + 4])[0]
        if ln < 2 or i + 2 + ln > n:
            return d
        seg, pay = d[i:i + 2 + ln], d[i + 4:i + 2 + ln]
        i += 2 + ln
        if m == 0xE1:
            if pay[:6] == b"Exif\x00\x00" and orient is None:
                orient = _exif_orientation(pay)
            continue                                     # كل APP1 (EXIF/XMP) يُحذف
        if m == 0xE2 and pay[:12] != b"ICC_PROFILE\x00":
            continue                                     # MPF وغيره قد يحمل مصغّرات
        if 0xE3 <= m <= 0xED or m == 0xEF or m == 0xFE:  # APP3..13، APP15، تعليقات (APP14 Adobe يبقى: يحدد الألوان)
            continue
        segs.append(seg)
    if i < n and not segs:
        return d
    out = [b"\xff\xd8"]
    rest = segs
    if rest and rest[0][:2] == b"\xff\xe0":
        out.append(rest[0])
        rest = rest[1:]
    if orient and orient != 1:
        out.append(_orientation_app1(orient))
    return b"".join(out + rest)


def _png_strip(d: bytes) -> bytes:
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        return d
    out, i, n = [d[:8]], 8, len(d)
    while i < n:
        if i + 12 > n:
            return d
        ln = struct.unpack(">I", d[i:i + 4])[0]
        end = i + 12 + ln
        if end > n:
            return d
        if d[i + 4:i + 8] not in _PNG_DROP:
            out.append(d[i:end])
        i = end
    return b"".join(out)


def _webp_strip(d: bytes) -> bytes:
    if d[:4] != b"RIFF" or d[8:12] != b"WEBP":
        return d
    out, i, n = [], 12, len(d)
    while i < n:
        if i + 8 > n:
            return d
        tag, ln = d[i:i + 4], struct.unpack("<I", d[i + 4:i + 8])[0]
        end = i + 8 + ln + (ln & 1)
        if end > n + (ln & 1):
            return d
        chunk = d[i:min(end, n)]
        if tag in (b"EXIF", b"XMP "):
            i = end
            continue
        if tag == b"VP8X" and ln >= 1:
            chunk = chunk[:8] + bytes([chunk[8] & ~0x0C & 0xFF]) + chunk[9:]
        out.append(chunk)
        i = end
    body = b"WEBP" + b"".join(out)
    return b"RIFF" + struct.pack("<I", len(body)) + body


def strip_metadata(data: bytes) -> bytes:
    """يعيد الصورة بلا EXIF/GPS/XMP/IPTC/تعليقات (JPEG وPNG وWebP). غير ذلك أو أي خلل في البنية: البيانات كما هي.
    الناتج هو الكائن نفسه إن لم يتغير شيء."""
    try:
        kind = sniff(data)
        out = {"jpeg": _jpeg_strip, "png": _png_strip, "webp": _webp_strip}.get(kind, lambda x: x)(data)
    except Exception:
        return data
    return data if out == data else out


def has_metadata(data: bytes) -> bool:
    return strip_metadata(data) is not data


def process(data: bytes):
    """يعيد (البيانات_المحفوظة, مصغّرة أو None). عند أي فشل أو غياب Pillow: (البيانات مجرَّدة من البيانات الوصفية, None)."""
    kind = sniff(data)
    if not PIL_OK or kind in ("", "gif"):          # غير صورة/متحركة/لا مكتبة: بلا تصغير، لكن البيانات الوصفية تُجرَّد دائماً
        return strip_metadata(data), None
    try:
        im = Image.open(io.BytesIO(data))
        if im.width * im.height > MAX_PIXELS:
            return strip_metadata(data), None
        if kind == "jpeg":
            im.draft("RGB", (MAX_SIDE * 2, MAX_SIDE * 2))      # فكّ مخفَّض الدقة: أسرع وأقل ذاكرة
        im = ImageOps.exif_transpose(im)
        im = _flatten(im)
        if max(im.size) > MAX_SIDE:
            im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
        full = _jpeg(im, FULL_QUALITY)
        thumb = None
        if max(im.size) > THUMB * 1.25:
            t = im.copy()
            t.thumbnail((THUMB, THUMB), Image.LANCZOS)
            thumb = _jpeg(t, THUMB_QUALITY)
        return full, thumb
    except Exception:
        return strip_metadata(data), None
