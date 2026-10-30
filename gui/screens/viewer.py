# -*- coding: utf-8 -*-
"""
عارض الصور بملء الشاشة — لا تحتوي أي SQL: كل الوصول للبيانات عبر core.
"""
import flet as ft

from theme import (WHITE, VIEWER_BG, VIEWER_BAR)


def install(app):
    page = app.page
    width = app.width
    img_ctl = app.img_ctl
    icon_btn = app.icon_btn

    def image_screen(rel, back):
        """عرض الصورة بملء الشاشة مع تكبير بالأصابع."""
        page.clean()
        page.bottom_appbar = None
        page.bgcolor = VIEWER_BG
        page.appbar = ft.AppBar(
            title=ft.Text("عرض الصورة", size=14, color=WHITE), center_title=True, bgcolor=VIEWER_BAR,
            leading=icon_btn("arrow_right", "w", lambda e: back()), leading_width=56, toolbar_height=54)
        page.add(ft.InteractiveViewer(
            content=img_ctl(rel, width(), max(int(page.height or 640) - 70, 300), ft.ImageFit.CONTAIN, full=True),
            min_scale=1, max_scale=6, expand=True))
        page.update()

    app.register(image_screen=image_screen)
