# -*- coding: utf-8 -*-
"""通用界面组件：卡片、表格、表单对话框、折线图与状态徽标。"""
from __future__ import annotations

import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Sequence

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .theme import COLORS, FONT, FONT_BOLD, FONT_H1, FONT_H2, FONT_H3, FONT_SMALL


# ---------- 通用工具 ----------
def human_dt(value: Any) -> str:
    if not value:
        return "—"
    text = str(value)
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return text


def fmt_num(value: Any, digits: int = 4) -> str:
    if value is None or value == "":
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(v) or math.isinf(v):
        return "—"
    if abs(v) >= 10000:
        return f"{v:,.1f}"
    if abs(v) >= 100:
        return f"{v:,.2f}"
    if abs(v) >= 1:
        return f"{v:,.3f}".rstrip("0").rstrip(".")
    return f"{v:.4g}"


def status_kind(value: Any) -> str:
    text = str(value or "")
    if text in ("有效", "成功", "已解决", "已确认", "已发布", "启用", "正常", "完成", "已完成"):
        return "success"
    if text in ("待审核", "部分成功", "草稿", "计划", "估算", "进行中", "过期"):
        return "warning"
    if text in ("无效", "失败", "未解决", "停用", "错误", "已关闭"):
        return "danger"
    return "muted"


def badge(parent, text: str, kind: str | None = None) -> tk.Label:
    kind = kind or status_kind(text)
    bg, fg = {
        "success": (COLORS["success_soft"], COLORS["success"]),
        "warning": (COLORS["warning_soft"], COLORS["warning"]),
        "danger": (COLORS["danger_soft"], COLORS["danger"]),
        "info": (COLORS["info_soft"], COLORS["info"]),
        "muted": ("#F1F5F9", COLORS["muted"]),
    }.get(kind, ("#F1F5F9", COLORS["muted"]))
    label = tk.Label(parent, text=f" {text} ", bg=bg, fg=fg, font=(FONT[0], 9, "bold"),
                     padx=8, pady=2, bd=0)
    return label


def confirm(parent, title: str, message: str) -> bool:
    return messagebox.askyesno(title, message, parent=parent)


def info(parent, message: str, title: str = "提示") -> None:
    messagebox.showinfo(title, message, parent=parent)


def warning(parent, message: str, title: str = "警告") -> None:
    messagebox.showwarning(title, message, parent=parent)


def error(parent, message: str, title: str = "错误") -> None:
    messagebox.showerror(title, message, parent=parent)


def open_path(path: str | Path) -> None:
    target = str(path)
    if not Path(target).exists():
        raise FileNotFoundError(target)
    os.startfile(target)  # type: ignore[attr-defined]


def center_window(window: tk.Toplevel | tk.Tk, width: int, height: int) -> None:
    window.update_idletasks()
    screen_w = window.winfo_screenwidth()
    screen_h = window.winfo_screenheight()
    x = max(0, (screen_w - width) // 2)
    y = max(0, (screen_h - height) // 3)
    window.geometry(f"{width}x{height}+{x}+{y}")


# ---------- 卡片 ----------
class Card(tk.Frame):
    def __init__(self, parent, padding: int = 16, bg: str | None = None, **kw):
        bg = bg or COLORS["white"]
        super().__init__(parent, bg=bg, highlightbackground=COLORS["border"],
                         highlightcolor=COLORS["border"], highlightthickness=1, bd=0, **kw)
        self.body = tk.Frame(self, bg=bg)
        self.body.pack(fill="both", expand=True, padx=padding, pady=padding)


def section(parent, title: str, subtitle: str = "", bg: str | None = None):
    bg = bg or COLORS["white"]
    frame = tk.Frame(parent, bg=bg)
    tk.Label(frame, text=title, bg=bg, fg=COLORS["text"], font=FONT_H3).pack(side="left")
    if subtitle:
        tk.Label(frame, text=subtitle, bg=bg, fg=COLORS["muted"], font=FONT_SMALL).pack(side="left", padx=(10, 0))
    return frame


# ---------- 数据表格 ----------
class DataTable(tk.Frame):
    def __init__(self, parent, columns: Sequence[Any], height: int = 10,
                 id_key: str = "", on_select: Callable | None = None,
                 on_double: Callable | None = None, bg: str | None = None):
        super().__init__(parent, bg=bg or COLORS["white"])
        self.columns = []
        for col in columns:
            if isinstance(col, (tuple, list)):
                key, label = col[0], col[1]
                width = col[2] if len(col) > 2 else 100
                self.columns.append({"key": key, "label": label, "width": width})
            else:
                self.columns.append(dict(col))
        self.id_key = id_key
        self._rows: list[dict] = []
        self._by_iid: dict[str, dict] = {}
        self.on_select = on_select
        self.on_double = on_double

        self.tree = ttk.Treeview(self, columns=[c["key"] for c in self.columns], show="headings",
                                 height=height, selectmode="browse")
        self._base_widths = []
        for c in self.columns:
            self.tree.heading(c["key"], text=c["label"], anchor=c.get("anchor", "w"))
            width = c.get("width", 100)
            self._base_widths.append(width)
            self.tree.column(c["key"], width=width, minwidth=c.get("minwidth", 42),
                             anchor=c.get("anchor", "w"), stretch=c.get("stretch", True))
        self._last_fit_width = 0
        self.tree.bind("<Configure>", self._fit_columns, add="+")
        vsb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.tree.tag_configure("success", foreground=COLORS["success"])
        self.tree.tag_configure("warning", foreground=COLORS["warning"])
        self.tree.tag_configure("danger", foreground=COLORS["danger"])
        self.tree.tag_configure("muted", foreground=COLORS["muted"])
        self.tree.tag_configure("alt", background="#F8FAFC")
        self.tree.bind("<<TreeviewSelect>>", self._handle_select)
        if on_double:
            self.tree.bind("<Double-1>", lambda e: self._handle_double())
        self.empty_label = tk.Label(self, text="暂无数据", bg=bg or COLORS["white"], fg=COLORS["muted"],
                                    font=FONT_SMALL)

    def _fit_columns(self, event) -> None:
        width = int(event.width)
        if width < 80 or abs(width - self._last_fit_width) < 4:
            return
        self._last_fit_width = width
        total = sum(self._base_widths) or 1
        avail = width - 4
        scale = min(1.0, avail / total)
        for col, base in zip(self.columns, self._base_widths):
            self.tree.column(col["key"], width=max(42, int(base * scale)))

    def _handle_select(self, _event=None):
        if self.on_select:
            row = self.selected_row()
            if row is not None:
                self.on_select(row)

    def _handle_double(self):
        row = self.selected_row()
        if row is not None and self.on_double:
            self.on_double(row)

    def set_rows(self, rows: Sequence[dict], id_key: str | None = None) -> None:
        self._rows = list(rows)
        if id_key:
            self.id_key = id_key
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._by_iid.clear()
        for idx, row in enumerate(self._rows):
            values = []
            for c in self.columns:
                value = row.get(c["key"])
                formatter = c.get("format")
                if formatter:
                    try:
                        value = formatter(value, row)
                    except TypeError:
                        value = formatter(value)
                elif isinstance(value, float):
                    value = fmt_num(value)
                elif value is None:
                    value = "—"
                values.append(value)
            tag = row.get("_tag") or ""
            tags = [tag] if tag else []
            if idx % 2 == 1:
                tags.append("alt")
            iid = self.tree.insert("", "end", values=values, tags=tuple(tags))
            self._by_iid[iid] = row
            status_value = row.get("quality_status") or row.get("status") or row.get("calibration_status")
            if status_value:
                self.tree.item(iid, tags=tuple(tags + [status_kind(status_value)]))
        if self._rows:
            self.empty_label.place_forget()
        else:
            self.empty_label.place(relx=0.5, rely=0.5, anchor="center")
        if self._rows and not self.tree.selection():
            first = self.tree.get_children()
            if first:
                self.tree.selection_set(first[0])

    def selected_row(self) -> dict | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self._by_iid.get(selection[0])

    def selected_id(self) -> str | None:
        row = self.selected_row()
        if row is None:
            return None
        return row.get(self.id_key) if self.id_key else None

    def select_by_id(self, value: str) -> None:
        for iid, row in self._by_iid.items():
            if str(row.get(self.id_key)) == str(value):
                self.tree.selection_set(iid)
                self.tree.see(iid)
                return

    def clear(self) -> None:
        self.set_rows([])


# ---------- 表单对话框 ----------
class FormDialog(tk.Toplevel):
    def __init__(self, parent, title: str, fields: Sequence[dict], width: int = 560,
                 ok_text: str = "保存", on_submit: Callable[[dict], None] | None = None,
                 intro: str = ""):
        super().__init__(parent)
        self.title(title)
        self.configure(bg=COLORS["white"])
        self.resizable(False, False)
        self.fields = list(fields)
        self.on_submit = on_submit
        self.result: dict | None = None
        self.vars: dict[str, tk.Variable] = {}
        self.choice_maps: dict[str, dict[str, Any]] = {}
        self.widgets: dict[str, tk.Widget] = {}
        self.intro = intro

        height = min(760, max(240, 150 + len(self.fields) * 52 + (90 if intro else 0)))
        self.geometry(f"{width}x{height}")
        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self._build()
        center_window(self, width, height)

    def _build(self) -> None:
        header = tk.Frame(self, bg=COLORS["white"])
        header.pack(fill="x", padx=24, pady=(20, 8))
        tk.Label(header, text=self.title(), bg=COLORS["white"], fg=COLORS["text"], font=FONT_H2).pack(anchor="w")
        if self.intro:
            tk.Label(header, text=self.intro, bg=COLORS["white"], fg=COLORS["muted"],
                     font=FONT_SMALL, wraplength=480, justify="left").pack(anchor="w", pady=(4, 0))

        body = tk.Frame(self, bg=COLORS["white"])
        body.pack(fill="both", expand=True, padx=24, pady=4)
        body.grid_columnconfigure(1, weight=1)

        for row, field in enumerate(self.fields):
            key = field["key"]
            label = field.get("label", key)
            required = field.get("required", False)
            label_text = f"{label} *" if required else label
            tk.Label(body, text=label_text, bg=COLORS["white"],
                     fg=COLORS["danger"] if required else COLORS["text"],
                     font=(FONT[0], 9, "bold" if required else "normal"), anchor="w").grid(
                row=row, column=0, sticky="nw", padx=(0, 12), pady=8)
            ftype = field.get("type", "text")
            default = field.get("default", "")
            if ftype == "combo":
                choices = field.get("choices")
                var = tk.StringVar()
                if choices:
                    labels = [c["label"] if isinstance(c, dict) else str(c) for c in choices]
                    values = [c.get("value") if isinstance(c, dict) else c for c in choices]
                    self.choice_maps[key] = dict(zip(labels, values))
                    var.set(str(default))
                else:
                    labels = [str(v) for v in field.get("values", [])]
                    var.set(str(default))
                widget = ttk.Combobox(body, textvariable=var, values=labels, state="readonly" if not field.get("editable") else "normal")
                self.vars[key] = var
            elif ftype == "multiline":
                var = tk.StringVar(value=str(default))
                widget = tk.Text(body, height=field.get("lines", 4), bg="#F8FAFC", fg=COLORS["text"],
                                 font=FONT, relief="solid", bd=1, wrap="word", padx=6, pady=4)
                widget.insert("1.0", str(default))
                self.vars[key] = var
            elif ftype == "check":
                var = tk.BooleanVar(value=bool(default))
                widget = ttk.Checkbutton(body, variable=var, text=field.get("check_text", "是"),
                                         style="White.TCheckbutton")
                self.vars[key] = var
            else:
                var = tk.StringVar(value=str(default))
                widget = ttk.Entry(body, textvariable=var,
                                   state="readonly" if field.get("readonly") else "normal")
                self.vars[key] = var
                if ftype == "date":
                    wrap = tk.Frame(body, bg=COLORS["white"])
                    widget.pack(in_=wrap, side="left", fill="x", expand=True)
                    ttk.Button(wrap, text="现在", style="Ghost.TButton",
                               command=lambda k=key: self.vars[k].set(datetime.now().astimezone().replace(microsecond=0).isoformat())
                               ).pack(side="right", padx=(6, 0))
                    widget = wrap
            widget.grid(row=row, column=1, sticky="ew", pady=8)
            if field.get("help"):
                tk.Label(body, text=field["help"], bg=COLORS["white"], fg=COLORS["muted"],
                         font=(FONT[0], 8), anchor="w").grid(row=row + 1, column=1, sticky="w", pady=(0, 2))
            self.widgets[key] = widget

        footer = tk.Frame(self, bg="#F8FAFC")
        footer.pack(fill="x", side="bottom", padx=0, pady=(8, 0))
        inner = tk.Frame(footer, bg="#F8FAFC")
        inner.pack(fill="x", padx=24, pady=14)
        ttk.Button(inner, text="取消", style="Secondary.TButton", command=self.cancel).pack(side="right")
        ttk.Button(inner, text="保存", style="Primary.TButton", command=self.save).pack(side="right", padx=(0, 8))

    def show(self) -> dict | None:
        self.wait_window(self)
        return self.result

    def _value(self, field: dict) -> Any:
        key = field["key"]
        ftype = field.get("type", "text")
        if ftype == "multiline":
            return self.widgets[key].get("1.0", "end-1c").strip()
        if ftype == "check":
            return bool(self.vars[key].get())
        raw = self.vars[key].get().strip()
        if ftype == "combo" and key in self.choice_maps:
            return self.choice_maps[key].get(raw, raw)
        if ftype in ("number", "int") and raw != "":
            try:
                return float(raw) if ftype == "number" else int(float(raw))
            except ValueError:
                raise ValueError(f"“{field.get('label', key)}”必须是有效数字")
        return raw

    def save(self) -> None:
        values = {}
        try:
            for field in self.fields:
                value = self._value(field)
                if field.get("required") and (value is None or value == ""):
                    raise ValueError(f"请填写“{field.get('label', field['key'])}”")
                values[field["key"]] = value
            if self.on_submit:
                self.on_submit(values)
        except ValueError as exc:
            messagebox.showwarning("请检查输入", str(exc), parent=self)
            return
        except Exception as exc:  # 数据库唯一约束等
            messagebox.showerror("保存失败", str(exc), parent=self)
            return
        self.result = values
        self.destroy()

    def cancel(self) -> None:
        self.result = None
        self.destroy()


def ask_text(parent, title: str, label: str = "说明", default: str = "", intro: str = "") -> str | None:
    dialog = FormDialog(parent, title, [{"key": "text", "label": label, "type": "multiline",
                                         "default": default, "required": True, "lines": 4}], intro=intro)
    result = dialog.show()
    return None if result is None else result["text"]


# ---------- 折线图 ----------
class LineChart(tk.Canvas):
    def __init__(self, parent, height: int = 240, bg: str = COLORS["white"]):
        super().__init__(parent, bg=bg, height=height, highlightthickness=0)
        self.series: list[dict] = []
        self.x_label = ""
        self.y_label = ""
        self._empty = "暂无数据"
        self.x_numeric = False
        self.bind("<Configure>", lambda e: self.redraw())

    def set_series(self, series: Sequence[dict], x_label: str = "", y_label: str = "", empty: str = "暂无数据",
                   x_numeric: bool = False):
        self.series = [dict(s) for s in series if s.get("points")]
        self.x_label = x_label
        self.y_label = y_label
        self._empty = empty
        self.x_numeric = x_numeric
        self.redraw()

    def _xvalue(self, x: Any, index: int) -> float:
        if isinstance(x, (int, float)):
            return float(x)
        if isinstance(x, datetime):
            return x.timestamp()
        try:
            return datetime.fromisoformat(str(x).replace("Z", "+00:00")).timestamp()
        except ValueError:
            return float(index)

    def redraw(self) -> None:
        self.delete("all")
        width, height = self.winfo_width(), self.winfo_height()
        if width < 60 or height < 60:
            return
        left, right, top, bottom = 68, 18, 26, 38
        plot_w, plot_h = width - left - right, height - top - bottom
        self.create_rectangle(left, top, left + plot_w, top + plot_h, outline="#E2E8F0", fill="#FFFFFF")
        if not self.series:
            self.create_text(width / 2, height / 2, text=self._empty, fill=COLORS["muted"], font=FONT)
            return
        all_points = []
        for s in self.series:
            pts = []
            for i, point in enumerate(s.get("points", [])):
                try:
                    x, y = point[0], point[1]
                except (TypeError, IndexError):
                    continue
                if y is None:
                    continue
                pts.append((self._xvalue(x, i), float(y), x))
            if pts:
                all_points.extend(pts)
            s["_pts"] = pts
        if not all_points:
            self.create_text(width / 2, height / 2, text=self._empty, fill=COLORS["muted"], font=FONT)
            return
        xs = [p[0] for p in all_points]
        ys = [p[1] for p in all_points]
        xmin, xmax = min(xs), max(xs)
        ymin, ymax = min(ys), max(ys)
        if xmax == xmin:
            xmax = xmin + 1
        if ymax == ymin:
            pad = abs(ymax) * 0.1 or 1
            ymin, ymax = ymin - pad, ymax + pad
        else:
            pad = (ymax - ymin) * 0.08
            ymin, ymax = ymin - pad, ymax + pad
        steps = 4
        for i in range(steps + 1):
            y = top + plot_h - plot_h * i / steps
            value = ymin + (ymax - ymin) * i / steps
            self.create_line(left, y, left + plot_w, y, fill="#EEF2F7")
            self.create_text(left - 8, y, text=fmt_num(value), anchor="e", fill="#64748B", font=(FONT[0], 8))
        for i in range(steps + 1):
            x = left + plot_w * i / steps
            value = xmin + (xmax - xmin) * i / steps
            self.create_line(x, top, x, top + plot_h, fill="#F8FAFC")
            if self.x_numeric:
                label = fmt_num(value)
            else:
                try:
                    dt = datetime.fromtimestamp(value)
                    label = dt.strftime("%H:%M") if (xmax - xmin) < 48 * 3600 else dt.strftime("%m-%d %H:%M")
                except (OverflowError, OSError, ValueError):
                    label = fmt_num(value)
            self.create_text(x, top + plot_h + 14, text=label, fill="#64748B", font=(FONT[0], 8))
        palette = [COLORS["accent"], COLORS["success"], COLORS["warning"], COLORS["purple"], COLORS["info"]]
        legend_x = left + 8
        for idx, s in enumerate(self.series):
            pts = s.get("_pts", [])
            if not pts:
                continue
            color = s.get("color") or palette[idx % len(palette)]
            coords = []
            for xv, yv, _original in pts:
                px = left + (xv - xmin) / (xmax - xmin) * plot_w
                py = top + plot_h - (yv - ymin) / (ymax - ymin) * plot_h
                coords.extend([px, py])
            if len(coords) >= 4:
                self.create_line(*coords, fill=color, width=2, smooth=False)
            for j in range(0, len(coords), 2):
                if len(pts) <= 80:
                    self.create_oval(coords[j] - 2, coords[j + 1] - 2, coords[j] + 2, coords[j + 1] + 2,
                                     fill=color, outline=color)
            if len(self.series) > 1 or s.get("name"):
                self.create_rectangle(legend_x, top + 8, legend_x + 12, top + 14, fill=color, outline=color)
                self.create_text(legend_x + 17, top + 11, text=s.get("name", ""), anchor="w",
                                 fill=COLORS["text"], font=(FONT[0], 8))
                legend_x += 22 + max(50, len(str(s.get("name", ""))) * 12)
        if self.x_label:
            self.create_text(left + plot_w / 2, height - 10, text=self.x_label, fill=COLORS["muted"], font=(FONT[0], 8))
        if self.y_label:
            self.create_text(12, top + plot_h / 2, text=self.y_label, angle=90, fill=COLORS["muted"], font=(FONT[0], 8))


# ---------- 可滚动容器 ----------
class ScrollableFrame(tk.Frame):
    def __init__(self, parent, bg: str | None = None):
        bg = bg or COLORS["bg"]
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._window, width=e.width))
        self.canvas.bind_all("<MouseWheel>", self._on_wheel)

    def _on_wheel(self, event):
        if self.winfo_containing(event.x_root, event.y_root) in (self.canvas, self.inner):
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
