# -*- coding: utf-8 -*-
"""
My Clinic
تطبيق إدارة العيادة (يعمل بدون إنترنت) — Python + Flet
نقطة الدخول فقط. الواجهة في الحزمة gui/ (راجع gui/app.py) والمنطق والبيانات في core.py.
"""
import flet as ft

from gui.app import main

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
