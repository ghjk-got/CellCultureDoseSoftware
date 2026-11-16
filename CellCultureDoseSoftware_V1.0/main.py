# -*- coding: utf-8 -*-
"""细胞培养基配制与补料剂量核算软件 V1.0 - 启动入口。"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

BASE_DIR = (Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False) else Path(__file__).resolve().parent)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def _enable_dpi_awareness() -> None:
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> int:
    _enable_dpi_awareness()
    try:
        from app.context import AppContext
        from app.ui.main_window import MainWindow
        ctx = AppContext()
        window = MainWindow(ctx)
        window.mainloop()
        return 0
    except Exception as exc:
        traceback.print_exc()
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("启动失败", f"软件启动失败：\n{exc}\n\n请检查 Python 环境和依赖是否完整。")
            root.destroy()
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
