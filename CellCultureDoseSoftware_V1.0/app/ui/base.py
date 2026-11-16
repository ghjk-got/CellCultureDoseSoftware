# -*- coding: utf-8 -*-
"""页面基类。"""
from __future__ import annotations

from tkinter import ttk


class Page(ttk.Frame):
    key = ""
    title = ""
    subtitle = ""

    def __init__(self, parent, app):
        super().__init__(parent, style="TFrame")
        self.app = app
        self.ctx = app.ctx

    def on_show(self) -> None:
        pass

    def on_batch_changed(self) -> None:
        pass

    def set_status(self, message: str) -> None:
        self.app.set_status(message)
