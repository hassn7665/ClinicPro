"""
make_icons.py — يولّد أيقونات SVG الاحترافية (خطّية 24×24) بألوان الهوية الطبية
داخل assets/icons/  ←  اسم_اللون.svg   مثال: user_plus_p.svg

شغّله مرة واحدة قبل التجربة أو البناء:   python make_icons.py
(ملف GitHub Actions يشغّله تلقائياً قبل البناء.)
"""
import os

from theme import ICON_COLORS, GRAD_LIGHT, GRAD_DARK, DEEP

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "icons")

COLORS = ICON_COLORS   # الألوان من theme.py

# كل أيقونة: عناصر SVG بخط stroke فقط (شبكة 24×24)
ICONS = {
    "home": '<path d="M4 11.500L12 4l8 7.500V19a2 2 0 0 1-2 2h-3.500v-5.500h-5V21H6a2 2 0 0 1-2-2z"/>',
    "user_plus": '<circle cx="9" cy="8" r="3.6"/><path d="M2.6 20c0-3.6 2.8-6 6.4-6s6.4 2.4 6.4 6"/><path d="M19 7.5v6M16 10.5h6"/>',
    "user_clock": '<circle cx="9" cy="8" r="3.6"/><path d="M2.6 20c0-3.6 2.8-6 6.4-6 1 0 1.900.2 2.700.5"/><circle cx="18" cy="17" r="4"/><path d="M18 15v2l1.300 1"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4.500 20.500c.8-3.700 3.700-5.600 7.500-5.600s6.700 1.900 7.500 5.600"/>',
    "users": '<circle cx="9" cy="8.500" r="3.200"/><path d="M3 19.500c0-3.300 2.700-5.500 6-5.500s6 2.200 6 5.500"/><path d="M16 5.500a3 3 0 0 1 0 6M18 14c2 .7 3 2.300 3 5.500"/>',
    "search": '<circle cx="11" cy="11" r="6.500"/><path d="M20 20l-4.200-4.200"/>',
    "settings": '<path d="M4 7h9M18 7h2M4 17h2M11 17h9"/><circle cx="15.500" cy="7" r="2.500"/><circle cx="8.500" cy="17" r="2.500"/>',
    "chart": '<rect x="4" y="11" width="4" height="9" rx="1.200"/><rect x="10" y="4" width="4" height="16" rx="1.200"/><rect x="16" y="8" width="4" height="12" rx="1.200"/>',
    "calendar": '<rect x="3.500" y="5" width="17" height="15.500" rx="3"/><path d="M3.500 10.500h17M8 3v4M16 3v4"/>',
    "calendar_check": '<rect x="3.500" y="5" width="17" height="15.500" rx="3"/><path d="M3.500 10.500h17M8 3v4M16 3v4M9 15.500l2 2 4-4"/>',
    "calendar_plus": '<rect x="3.500" y="5" width="17" height="15.500" rx="3"/><path d="M3.500 10.500h17M8 3v4M16 3v4M12 13v5M9.500 15.500h5"/>',
    "calendar_edit": '<path d="M20.500 11V8a3 3 0 0 0-3-3h-11a3 3 0 0 0-3 3v9.500a3 3 0 0 0 3 3H11"/><path d="M3.500 10.500h17M8 3v4M16 3v4"/><path d="M14 20.500l.5-2.500 5-5a1.500 1.500 0 0 1 2 2l-5 5z"/>',
    "clock": '<circle cx="12" cy="12" r="8.500"/><path d="M12 7.500V12l3 2"/>',
    "stethoscope": '<path d="M6 3.500v5.500a4 4 0 0 0 8 0V3.500M5 3.500h2M13 3.500h2"/><path d="M10 13v2.500a4.500 4.500 0 0 0 9 0V14"/><circle cx="19" cy="12" r="2"/>',
    "scissors": '<circle cx="6" cy="6.500" r="2.800"/><circle cx="6" cy="17.500" r="2.800"/><path d="M8.300 8.300L20 18.500M8.300 15.700L20 5.500"/>',
    "file": '<path d="M14 3H7.500a2.500 2.500 0 0 0-2.500 2.500v13A2.500 2.500 0 0 0 7.500 21h9a2.500 2.500 0 0 0 2.500-2.500V8z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    "printer": '<path d="M7 9V3.500h10V9"/><rect x="3.500" y="9" width="17" height="8" rx="2.500"/><path d="M7 14h10v6.500H7z"/>',
    "image": '<rect x="3.500" y="5" width="17" height="14" rx="3"/><circle cx="9" cy="10.500" r="1.800"/><path d="M4 17l5-4.500 3.500 3 3-2.500 4.500 4"/>',
    "photo_add": '<path d="M12 20H6.500a3 3 0 0 1-3-3V8a3 3 0 0 1 3-3h11a3 3 0 0 1 3 3v4"/><circle cx="9" cy="10" r="1.600"/><path d="M3.800 16.500l4.700-4 3.500 3"/><path d="M18 15v6M15 18h6"/>',
    "paperclip": '<path d="M20 11.500l-8.200 8.200a5 5 0 0 1-7-7l8.600-8.600a3.400 3.400 0 0 1 4.800 4.800l-8.600 8.600a1.800 1.800 0 0 1-2.500-2.500l7.800-7.800"/>',
    "phone": '<path d="M5.500 4h3.300l1.900 4.800-2.300 1.500a11 11 0 0 0 5.300 5.300l1.500-2.300 4.800 1.900v3.300a2 2 0 0 1-2.200 2A16 16 0 0 1 3.500 6.200 2 2 0 0 1 5.500 4z"/>',
    "pin": '<path d="M12 21s7-5.600 7-11a7 7 0 0 0-14 0c0 5.400 7 11 7 11z"/><circle cx="12" cy="10" r="2.500"/>',
    "briefcase": '<rect x="3" y="7.500" width="18" height="12.500" rx="3"/><path d="M9 7.500V6a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v1.500M3 13.500h18"/>',
    "droplet": '<path d="M12 3.500S6 9.700 6 14a6 6 0 0 0 12 0c0-4.300-6-10.500-6-10.500z"/>',
    "heart_pulse": '<path d="M12 20.500S4 15.800 4 10A4.500 4.500 0 0 1 12 7.300 4.500 4.500 0 0 1 20 10c0 5.800-8 10.500-8 10.500z"/><path d="M7 12.500h3l1.500-2.500 2 4.500 1.500-2h2"/>',
    "note": '<path d="M5 4h14v11.500L14.500 20H5z"/><path d="M14.500 20v-4.500H19M8.500 9h7M8.500 12.500h4"/>',
    "badge": '<rect x="3" y="5" width="18" height="14" rx="3"/><circle cx="9" cy="11" r="2"/><path d="M5.800 16c.5-1.600 1.700-2.300 3.200-2.300s2.700.7 3.200 2.300M14.500 10h3.500M14.500 14h3"/>',
    "cake": '<path d="M4 20.500v-7a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v7zM4 16.500c2 1.500 3.500 1.500 5.300 0s3.500-1.500 5.400 0 3.400 1.500 5.300 0"/><path d="M12 11.500V8.500M12 4c1 1 1 2 0 3-1-1-1-2 0-3z"/>',
    "check_circle": '<circle cx="12" cy="12" r="9"/><path d="M8 12.500l2.800 2.800 5.400-5.800"/>',
    "check": '<path d="M5 12.500l4.500 4.500L19 7.500"/>',
    "x": '<path d="M6 6l12 12M18 6L6 18"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "edit": '<path d="M4 20h4L19.500 8.500a2.800 2.800 0 0 0-4-4L4 16z"/><path d="M13.500 6.500l4 4"/>',
    "arrow_right": '<path d="M4 12h16M14 6l6 6-6 6"/>',
    "chevron_left": '<path d="M15 5l-7 7 7 7"/>',
    "key": '<circle cx="8" cy="15.500" r="4"/><path d="M11 12.500l9-9M16 7.500l3 3M14 9.500l2 2"/>',
    "shield_check": '<path d="M12 3l7.500 3v5.500c0 4.600-3.200 8.200-7.500 9.500-4.300-1.300-7.500-4.900-7.500-9.500V6z"/><path d="M8.800 12l2.200 2.200 4.500-4.500"/>',
    "backup": '<path d="M7 18.500a4.500 4.500 0 0 1-.6-8.900A6 6 0 0 1 18 10a4.300 4.300 0 0 1-.5 8.500z"/><path d="M12 16v-6M9.500 12.500L12 10l2.500 2.500"/>',
    "download": '<path d="M12 4v11M7.500 10.500L12 15l4.500-4.500M5 20h14"/>',
    "upload": '<path d="M12 16V5M7.500 9.500L12 5l4.500 4.500M5 20h14"/>',
    "restore": '<path d="M4 12a8 8 0 1 0 2.300-5.600"/><path d="M4 4v4.500h4.500"/><path d="M12 8v4l2.500 1.500"/>',
    "folder": '<path d="M3.500 7.500a2 2 0 0 1 2-2H10l2 2.500h6.500a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.500M12 7.800v.2"/>',
    "bell": '<path d="M6 16.500V11a6 6 0 0 1 12 0v5.500l1.500 2h-15z"/><path d="M10 21a2 2 0 0 0 4 0"/>',
    "lock": '<rect x="5" y="10.500" width="14" height="10" rx="2.500"/><path d="M8 10.500V8a4 4 0 0 1 8 0v2.500"/>',
    "alert": '<path d="M12 4l9 16H3z"/><path d="M12 10v4.500M12 17.500v.1"/>',
    "pulse": '<path d="M3 12h4l2.500-6 4 12 2.500-6H21"/>',
    "filter": '<path d="M4 6.500h16M7 12h10M10 17.500h4"/>',
    "eye": '<path d="M2.500 12S6 5.500 12 5.500 21.500 12 21.500 12 18 18.500 12 18.500 2.500 12 2.500 12z"/><circle cx="12" cy="12" r="3"/>',
    "wallet": '<path d="M4 8.500A2.500 2.500 0 0 1 6.500 6H18a2 2 0 0 1 2 2v1"/><rect x="3.500" y="8" width="17" height="12" rx="3"/><path d="M16.500 14h2"/>',
    "receipt": '<path d="M6 3.500h12v17l-3-2-3 2-3-2-3 2z"/><path d="M9 8.500h6M9 12.500h6"/>',
    "coins": '<circle cx="12" cy="12" r="8.500"/><path d="M14.500 9.500c-.5-1-1.500-1.500-2.500-1.500-1.500 0-2.500.8-2.500 2s1 1.800 2.500 2 2.500.8 2.500 2-1 2-2.500 2c-1 0-2-.5-2.500-1.500M12 6.500V8M12 16v1.500"/>',
    "share": '<circle cx="6.500" cy="12" r="2.500"/><circle cx="17.500" cy="6" r="2.500"/><circle cx="17.500" cy="18" r="2.500"/><path d="M8.800 10.800l6.400-3.600M8.800 13.200l6.400 3.600"/>',
}

def svg_icon(body, color):
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="%s" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">%s</svg>' % (color, body))


# ── الشعار: شاشة مراقبة بنبض قلب (الأيقونة المعتمدة) بألوان الهوية ──
_GRAD = (f'<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{GRAD_LIGHT}"/>'
         f'<stop offset="1" stop-color="{GRAD_DARK}"/></linearGradient></defs>')


def _glyph(color):
    return (f'<g fill="none" stroke="{color}" stroke-linecap="round" stroke-linejoin="round">'
            '<rect x="14.500" y="15.500" width="35" height="25" rx="5.500" stroke-width="3.600"/>'
            '<path d="M32 40.500v6.500M22.500 48h19" stroke-width="3.600"/>'
            '<path d="M20.500 28h4.500l3.200 5 4.300-11.500 3.700 8.500 1.800-2H43.500" stroke-width="3.400"/></g>')


LOGO = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">' + _GRAD +
        '<rect width="64" height="64" rx="18" fill="url(#g)"/>' + _glyph("#FFFFFF") + '</svg>')

LOGO_LIGHT = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">' + _GRAD +
              '<rect x="1" y="1" width="62" height="62" rx="18" fill="#FFFFFF" stroke="#BFE0DB" stroke-width="2"/>' +
              _glyph(DEEP) + '</svg>')

LOGO_LAUNCHER = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">' + _GRAD +
                 '<rect width="64" height="64" fill="url(#g)"/>' + _glyph("#FFFFFF") + '</svg>')

HERO = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">
<circle cx="62" cy="64" r="48" fill="#CDEAE6"/><circle cx="34" cy="34" r="14" fill="#E4F4F1"/>
<rect x="32" y="20" width="58" height="78" rx="12" fill="#FFFFFF" stroke="#BFE0DB" stroke-width="1.500"/>
<path d="M32 32a12 12 0 0 1 12-12h34a12 12 0 0 1 12 12v8H32z" fill="#2A9D8F"/>
<path d="M58.500 26h5v3.500H67v5h-3.500V38h-5v-3.500H55v-5h3.500z" fill="#FFFFFF"/>
<rect x="42" y="50" width="38" height="5" rx="2.500" fill="#D5ECE8"/><rect x="42" y="61" width="26" height="5" rx="2.500" fill="#D5ECE8"/>
<circle cx="50" cy="82" r="8" fill="#E1F2EF"/><path d="M46 82l3 3 5-6" fill="none" stroke="#2A9D8F" stroke-width="2.200" stroke-linecap="round" stroke-linejoin="round"/>
<rect x="63" y="79" width="18" height="5" rx="2.500" fill="#D5ECE8"/>
<circle cx="90" cy="88" r="14" fill="#FFFFFF" stroke="#BFE0DB" stroke-width="1.500"/>
<path d="M81 88h4l2.500-6 4 11 2.500-5h5" fill="none" stroke="#2A9D8F" stroke-width="2.200" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="98" cy="26" r="3" fill="#F4B13E"/><circle cx="24" cy="78" r="2.500" fill="#9ED6CD"/>
</svg>"""


def main():
    os.makedirs(OUT, exist_ok=True)
    n = 0
    for name, body in ICONS.items():
        for k, col in COLORS.items():
            with open(os.path.join(OUT, f"{name}_{k}.svg"), "w", encoding="utf-8") as f:
                f.write(svg_icon(body, col))
            n += 1
    for name, data in (("logo", LOGO), ("logo_light", LOGO_LIGHT), ("logo_launcher", LOGO_LAUNCHER), ("hero", HERO)):
        with open(os.path.join(OUT, f"{name}.svg"), "w", encoding="utf-8") as f:
            f.write(data)
    print(f"generated {n} icons + logos -> {OUT}")


if __name__ == "__main__":
    main()
