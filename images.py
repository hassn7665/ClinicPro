# -*- coding: utf-8 -*-
"""
images.py — تصغير صور المرضى عند الإدخال وإنشاء مصغّرات للعرض.

المشكلة: صور الكاميرا (3–8 ميغابايت) كانت تُخزَّن كما هي وتُرمَّز base64 كاملةً في الواجهة لعرض بلاطة صغيرة.
الحل: عند الحفظ تُصغَّر الصورة إلى ≤ MAX_SIDE بكسل (JPEG) مع تدوير EXIF ثم **إزالة بيانات EXIF (ومنها إحداثيات GPS)**،
وتُنشأ مصغّرة THUMB بكسل تُستعمل في القوائم والبلاطات؛ والأصل المُصغَّر يُفتح في شاشة العارض فقط.

يعتمد على Pillow إن توفّر؛ وإن لم يتوفر (مثلاً بناء أندرويد بلا الحزمة) تعمل الدوال بلا أي تغيير للبيانات،
ويعوّض main.py ذلك بالتحميل الكسول. لا يُضاف Pillow إلى requirements تلقائياً: راجع PHASE0_CHECKLIST_AR.md.
"""
import io

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


def process(data: bytes):
    """يعيد (البيانات_المحفوظة, مصغّرة أو None). عند أي فشل أو غياب Pillow: (data, None) دون تعديل."""
    kind = sniff(data)
    if not PIL_OK or kind in ("", "gif"):          # غير صورة/متحركة/لا مكتبة: تُحفظ كما هي
        return data, None
    try:
        im = Image.open(io.BytesIO(data))
        if im.width * im.height > MAX_PIXELS:
            return data, None
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
        return data, None
