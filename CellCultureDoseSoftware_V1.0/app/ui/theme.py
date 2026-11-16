# -*- coding: utf-8 -*-
"""界面主题：颜色、字体与 ttk 样式。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

COLORS = {
    "bg": "#F4F6FA",
    "white": "#FFFFFF",
    "sidebar": "#0F172A",
    "sidebar_hover": "#1E293B",
    "sidebar_active": "#1D4ED8",
    "sidebar_text": "#CBD5E1",
    "accent": "#2563EB",
    "accent_dark": "#1D4ED8",
    "accent_soft": "#DBEAFE",
    "text": "#0F172A",
    "muted": "#64748B",
    "border": "#E2E8F0",
    "success": "#16A34A",
    "success_soft": "#DCFCE7",
    "warning": "#D97706",
    "warning_soft": "#FEF3C7",
    "danger": "#DC2626",
    "danger_soft": "#FEE2E2",
    "info": "#0EA5E9",
    "info_soft": "#E0F2FE",
    "purple": "#7C3AED",
}

FONT_FAMILY = "Microsoft YaHei UI"
FONT = (FONT_FAMILY, 10)
FONT_SMALL = (FONT_FAMILY, 9)
FONT_BOLD = (FONT_FAMILY, 10, "bold")
FONT_H1 = (FONT_FAMILY, 20, "bold")
FONT_H2 = (FONT_FAMILY, 13, "bold")
FONT_H3 = (FONT_FAMILY, 11, "bold")
FONT_NUM = (FONT_FAMILY, 24, "bold")
FONT_MONO = ("Consolas", 9)


def setup_theme(root: tk.Tk) -> None:
    root.configure(bg=COLORS["bg"])
    root.option_add("*Font", FONT)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(".", font=FONT, background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("TFrame", background=COLORS["bg"])
    style.configure("White.TFrame", background=COLORS["white"])
    style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("White.TLabel", background=COLORS["white"], foreground=COLORS["text"])
    style.configure("H1.TLabel", font=FONT_H1, background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("H2.TLabel", font=FONT_H2, background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("H2White.TLabel", font=FONT_H2, background=COLORS["white"], foreground=COLORS["text"])
    style.configure("H3.TLabel", font=FONT_H3, background=COLORS["bg"], foreground=COLORS["text"])
    style.configure("Muted.TLabel", font=FONT_SMALL, background=COLORS["bg"], foreground=COLORS["muted"])
    style.configure("MutedWhite.TLabel", font=FONT_SMALL, background=COLORS["white"], foreground=COLORS["muted"])
    style.configure("Metric.TLabel", font=FONT_NUM, background=COLORS["white"], foreground=COLORS["text"])
    style.configure("Accent.TLabel", background=COLORS["bg"], foreground=COLORS["accent"], font=FONT_BOLD)
    style.configure("Success.TLabel", background=COLORS["bg"], foreground=COLORS["success"], font=FONT_BOLD)
    style.configure("Warning.TLabel", background=COLORS["bg"], foreground=COLORS["warning"], font=FONT_BOLD)
    style.configure("Danger.TLabel", background=COLORS["bg"], foreground=COLORS["danger"], font=FONT_BOLD)

    style.configure("TButton", padding=(12, 6), borderwidth=0, font=FONT)
    style.configure("Primary.TButton", background=COLORS["accent"], foreground="white",
                    padding=(14, 7), font=FONT_BOLD)
    style.map("Primary.TButton",
              background=[("active", COLORS["accent_dark"]), ("disabled", "#93C5FD")],
              foreground=[("disabled", "#EFF6FF")])
    style.configure("Secondary.TButton", background=COLORS["white"], foreground=COLORS["text"],
                    padding=(12, 7), borderwidth=1)
    style.map("Secondary.TButton", background=[("active", "#F1F5F9")])
    style.configure("Ghost.TButton", background=COLORS["bg"], foreground=COLORS["muted"], padding=(10, 5))
    style.map("Ghost.TButton", background=[("active", "#E2E8F0")], foreground=[("active", COLORS["text"])])
    style.configure("Danger.TButton", background=COLORS["danger"], foreground="white", padding=(12, 7))
    style.map("Danger.TButton", background=[("active", "#B91C1C")])
    style.configure("Success.TButton", background=COLORS["success"], foreground="white", padding=(12, 7))
    style.map("Success.TButton", background=[("active", "#15803D")])
    style.configure("Link.TButton", background=COLORS["white"], foreground=COLORS["accent"],
                    padding=(4, 2), font=(FONT_FAMILY, 9, "underline"))
    style.map("Link.TButton", background=[("active", COLORS["white"])])

    style.configure("TEntry", fieldbackground=COLORS["white"], foreground=COLORS["text"],
                    padding=6, borderwidth=1, relief="solid")
    style.map("TEntry", bordercolor=[("focus", COLORS["accent"])])
    style.configure("TCombobox", fieldbackground=COLORS["white"], background=COLORS["white"],
                    foreground=COLORS["text"], padding=5, arrowsize=14)
    style.map("TCombobox", fieldbackground=[("readonly", COLORS["white"])])
    style.configure("TSpinbox", fieldbackground=COLORS["white"], padding=5)
    style.configure("TCheckbutton", background=COLORS["bg"], font=FONT)
    style.configure("White.TCheckbutton", background=COLORS["white"], font=FONT)

    style.configure("Treeview", background=COLORS["white"], fieldbackground=COLORS["white"],
                    foreground=COLORS["text"], rowheight=28, borderwidth=0, font=FONT_SMALL)
    style.map("Treeview", background=[("selected", COLORS["accent_soft"])],
              foreground=[("selected", COLORS["text"])])
    style.configure("Treeview.Heading", background="#EEF2F7", foreground="#334155",
                    font=(FONT_FAMILY, 9, "bold"), relief="flat", padding=(8, 6))
    style.map("Treeview.Heading", background=[("active", "#E2E8F0")])
    style.configure("Vertical.TScrollbar", background="#CBD5E1", troughcolor=COLORS["white"],
                    borderwidth=0, arrowsize=12)
    style.configure("Horizontal.TScrollbar", background="#CBD5E1", troughcolor=COLORS["white"],
                    borderwidth=0, arrowsize=12)

    style.configure("TNotebook", background=COLORS["bg"], borderwidth=0, tabmargins=(0, 2, 0, 0))
    style.configure("TNotebook.Tab", background="#E2E8F0", foreground="#475569",
                    padding=(18, 8), font=(FONT_FAMILY, 9, "bold"), borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", COLORS["white"])],
              foreground=[("selected", COLORS["accent"])])

    style.configure("TLabelframe", background=COLORS["white"], bordercolor=COLORS["border"])
    style.configure("TLabelframe.Label", background=COLORS["white"], foreground=COLORS["text"], font=FONT_BOLD)
    style.configure("TSeparator", background=COLORS["border"])
    style.configure("TProgressbar", background=COLORS["accent"], troughcolor="#E2E8F0", borderwidth=0)
