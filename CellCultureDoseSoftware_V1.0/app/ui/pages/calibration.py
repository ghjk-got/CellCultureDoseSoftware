# -*- coding: utf-8 -*-
"""泵校准：手工录入、my-Control 导入、校准点与插值曲线。"""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import filedialog, ttk

from ...db import now_iso
from ...services.calibration import interpolate
from ...services.units import fmt
from ..base import Page
from ..theme import COLORS, FONT, FONT_H3, FONT_SMALL
from ..widgets import (Card, DataTable, FormDialog, LineChart, badge, center_window,
                       confirm, error, fmt_num, info)


class CalibrationImportDialog(tk.Toplevel):
    def __init__(self, parent, page: "CalibrationPage", pump_id: str):
        super().__init__(parent)
        self.page = page
        self.ctx = page.ctx
        self.pump_id = pump_id
        self.preview_obj = None
        self.title("导入 my-Control 校准文件")
        self.configure(bg=COLORS["white"])
        self.geometry("900x760")
        center_window(self, 900, 760)
        self.transient(parent)
        self.grab_set()
        self._build()

    def _build(self):
        head = tk.Frame(self, bg=COLORS["white"])
        head.pack(fill="x", padx=20, pady=(16, 6))
        tk.Label(head, text="导入 my-Control 校准文件", bg=COLORS["white"], fg=COLORS["text"],
                 font=(FONT[0], 14, "bold")).pack(anchor="w")
        tk.Label(head, text="支持 CSV / XLSX；导入后生成“待审核”校准记录，审核通过后才作为有效曲线。",
                 bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(anchor="w", pady=(2, 0))

        file_row = tk.Frame(self, bg=COLORS["white"])
        file_row.pack(fill="x", padx=20, pady=6)
        self.file_var = tk.StringVar()
        ttk.Entry(file_row, textvariable=self.file_var, state="readonly").pack(side="left", fill="x", expand=True)
        ttk.Button(file_row, text="选择文件", style="Primary.TButton", command=self.choose_file).pack(side="left", padx=6)

        option_row = tk.Frame(self, bg=COLORS["white"])
        option_row.pack(fill="x", padx=20, pady=6)
        tk.Label(option_row, text="工作表", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="left")
        self.sheet_var = tk.StringVar()
        self.sheet_combo = ttk.Combobox(option_row, textvariable=self.sheet_var, width=22, state="readonly")
        self.sheet_combo.pack(side="left", padx=6)
        tk.Label(option_row, text="表头行", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="left", padx=(12, 0))
        self.header_var = tk.StringVar(value="1")
        ttk.Entry(option_row, textvariable=self.header_var, width=6).pack(side="left", padx=6)
        ttk.Button(option_row, text="读取表头", style="Secondary.TButton", command=self.load_headers).pack(side="left")
        ttk.Button(option_row, text="自动识别", style="Ghost.TButton", command=self.guess_header).pack(side="left", padx=6)

        map_frame = tk.LabelFrame(self, text=" 字段映射 ", bg=COLORS["white"], fg=COLORS["text"], font=FONT_SMALL)
        map_frame.pack(fill="x", padx=20, pady=6)
        self.map_vars = {}
        self.map_combos = {}
        fields = [("setpoint_value", "设置值/转速 *"), ("setpoint_unit", "设置值单位"),
                  ("measured_flow", "实测流速"), ("flow_unit", "流速单位"),
                  ("measured_volume", "实测体积"), ("run_duration", "运行时长"),
                  ("duration_unit", "时长单位")]
        for i, (key, label) in enumerate(fields):
            row, col = divmod(i, 4)
            tk.Label(map_frame, text=label, bg=COLORS["white"], fg=COLORS["muted"],
                     font=(FONT[0], 8)).grid(row=row * 2, column=col, sticky="w", padx=8, pady=(6, 0))
            var = tk.StringVar()
            combo = ttk.Combobox(map_frame, textvariable=var, state="readonly", width=20)
            combo.grid(row=row * 2 + 1, column=col, sticky="ew", padx=8, pady=(2, 6))
            self.map_vars[key] = var
            self.map_combos[key] = combo
        for col in range(4):
            map_frame.grid_columnconfigure(col, weight=1)
        ttk.Button(map_frame, text="预览解析结果", style="Primary.TButton", command=self.preview).grid(
            row=4, column=3, sticky="e", padx=8, pady=8)

        panes = tk.Frame(self, bg=COLORS["white"])
        panes.pack(fill="both", expand=True, padx=20, pady=6)
        panes.grid_columnconfigure(0, weight=1)
        panes.grid_columnconfigure(1, weight=1)
        panes.grid_rowconfigure(0, weight=1)
        left = tk.Frame(panes, bg=COLORS["white"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(left, text="校准点预览", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w")
        self.points_table = DataTable(left, [
            ("setpoint_value", "设置值", 80), ("setpoint_unit", "单位", 60),
            ("measured_flow", "实测流速", 90), ("flow_unit", "单位", 70),
            ("measured_volume", "体积", 70), ("run_duration", "时长", 70),
        ], height=8)
        self.points_table.pack(fill="both", expand=True, pady=(4, 0))
        right = tk.Frame(panes, bg=COLORS["white"])
        right.grid(row=0, column=1, sticky="nsew")
        tk.Label(right, text="错误与警告", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w")
        self.issues = tk.Text(right, height=8, bg="#F8FAFC", fg=COLORS["text"], relief="solid", bd=1,
                              font=FONT_SMALL, wrap="word", padx=6, pady=4)
        self.issues.pack(fill="both", expand=True, pady=(4, 0))

        foot = tk.Frame(self, bg="#F8FAFC")
        foot.pack(fill="x", side="bottom", pady=(6, 0))
        inner = tk.Frame(foot, bg="#F8FAFC")
        inner.pack(fill="x", padx=20, pady=10)
        tk.Label(inner, text="校准日期", bg="#F8FAFC", fg=COLORS["muted"], font=FONT_SMALL).pack(side="left")
        self.date_var = tk.StringVar(value=now_iso()[:10])
        ttk.Entry(inner, textvariable=self.date_var, width=14).pack(side="left", padx=6)
        tk.Label(inner, text="备注", bg="#F8FAFC", fg=COLORS["muted"], font=FONT_SMALL).pack(side="left", padx=(10, 4))
        self.notes_var = tk.StringVar()
        ttk.Entry(inner, textvariable=self.notes_var, width=28).pack(side="left")
        ttk.Button(inner, text="取消", style="Secondary.TButton", command=self.destroy).pack(side="right")
        ttk.Button(inner, text="保存校准记录", style="Success.TButton", command=self.commit).pack(side="right", padx=8)

    def choose_file(self):
        path = filedialog.askopenfilename(parent=self, title="选择 my-Control 导出文件",
                                          filetypes=[("表格文件", "*.csv *.xlsx *.xlsm *.txt *.tsv"), ("所有文件", "*.*")])
        if not path:
            return
        self.file_var.set(path)
        from ...importers.table_reader import guess_header_row, list_sheets
        try:
            sheets = list_sheets(path)
        except Exception:
            sheets = []
        if sheets:
            self.sheet_combo.configure(values=sheets)
            self.sheet_var.set(sheets[0])
        else:
            self.sheet_combo.configure(values=[])
            self.sheet_var.set("")
        try:
            self.header_var.set(str(guess_header_row(path, self.sheet_var.get() or None)))
        except Exception:
            self.header_var.set("1")
        self.load_headers()

    def guess_header(self):
        if not self.file_var.get():
            return
        from ...importers.table_reader import guess_header_row
        try:
            self.header_var.set(str(guess_header_row(self.file_var.get(), self.sheet_var.get() or None)))
            self.load_headers()
        except Exception as exc:
            error(self, str(exc))

    def load_headers(self):
        if not self.file_var.get():
            return
        from ...importers.table_reader import read_table
        try:
            table = read_table(self.file_var.get(), self.sheet_var.get() or None, int(self.header_var.get() or 1))
        except Exception as exc:
            error(self, f"读取失败：{exc}")
            return
        choices = ["（不导入）"] + table.headers
        self._header_choices = choices
        self._header_values = table.headers
        mapping = self.ctx.calibration_import.suggest_mapping(table.headers)
        for key, var in self.map_vars.items():
            self.map_combos[key].configure(values=choices)
            var.set("（不导入）")
        for key, idx in mapping.items():
            if key in self.map_vars and idx < len(table.headers):
                self.map_vars[key].set(table.headers[idx])

    def _mapping(self):
        headers = getattr(self, "_header_choices", [])[1:]
        mapping = {}
        for key, var in self.map_vars.items():
            value = var.get()
            if value in headers:
                mapping[key] = headers.index(value)
        return mapping

    def preview(self):
        if not self.file_var.get():
            info(self, "请先选择文件")
            return
        try:
            mapping = self._mapping()
            pv = self.ctx.calibration_import.preview(
                self.file_var.get(), self.sheet_var.get() or None, int(self.header_var.get() or 1), mapping)
        except Exception as exc:
            error(self, f"解析失败：{exc}")
            return
        self.preview_obj = pv
        self.points_table.set_rows(pv.points)
        lines = []
        for e in pv.errors:
            lines.append(f"[错误] 第 {e.get('row')} 行 / {e.get('field')}：{e.get('message')}")
        for w in pv.warnings:
            lines.append(f"[警告] {w}")
        self.issues.delete("1.0", "end")
        self.issues.insert("1.0", "\n".join(lines) if lines else "解析通过，未发现错误或警告。")
        self.issues.configure(fg=COLORS["danger"] if pv.errors else COLORS["text"])

    def commit(self):
        if not self.preview_obj:
            self.preview()
        if not self.preview_obj:
            return
        if self.preview_obj.errors:
            error(self, "存在阻断错误，不能保存校准记录")
            return
        try:
            cid = self.ctx.calibration_import.commit(
                self.pump_id, self.preview_obj, self.ctx.operator,
                calibration_date=self.date_var.get().strip(), notes=self.notes_var.get().strip())
        except Exception as exc:
            error(self, f"保存失败：{exc}")
            return
        self.ctx.audit("导入泵校准", "pump_calibration", cid)
        info(self, f"校准记录已保存：{cid}\n状态为“待审核”，请在记录中确认后设为有效。")
        self.destroy()
        self.page.refresh()


class CalibrationPage(Page):
    key = "calibration"
    title = "泵校准"
    subtitle = "校准记录、my-Control 导入与插值曲线"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.pump_map: dict[str, str] = {}
        self.current_calibration: dict | None = None
        self._build()
        self.refresh()

    def _build(self):
        top = tk.Frame(self, bg=COLORS["bg"])
        top.pack(fill="x")
        tk.Label(top, text="泵", bg=COLORS["bg"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="left")
        self.pump_var = tk.StringVar()
        self.pump_combo = ttk.Combobox(top, textvariable=self.pump_var, state="readonly", width=28)
        self.pump_combo.pack(side="left", padx=8)
        self.pump_combo.bind("<<ComboboxSelected>>", lambda e: self.refresh_records())
        ttk.Button(top, text="手工新建校准", style="Primary.TButton", command=self.manual_create).pack(side="left")
        ttk.Button(top, text="导入 my-Control", style="Secondary.TButton", command=self.import_file).pack(side="left", padx=6)
        ttk.Button(top, text="设为有效", style="Success.TButton", command=self.set_effective).pack(side="right")
        ttk.Button(top, text="标记过期", style="Ghost.TButton", command=self.set_expired).pack(side="right", padx=6)

        split = tk.Frame(self, bg=COLORS["bg"])
        split.pack(fill="both", expand=True, pady=(12, 0))
        split.grid_columnconfigure(0, weight=2)
        split.grid_columnconfigure(1, weight=3)
        split.grid_rowconfigure(0, weight=1)

        left = Card(split, padding=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        h = tk.Frame(left.body, bg=COLORS["white"])
        h.pack(fill="x")
        tk.Label(h, text="校准记录", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        self.record_table = DataTable(left.body, [
            ("calibration_date", "日期", 105), ("calibration_status", "状态", 65),
            ("calibration_method", "方法", 115), ("point_count", "点数", 45),
        ], height=12, id_key="calibration_id", on_select=self.select_record)
        self.record_table.pack(fill="both", expand=True, pady=(8, 0))

        right = tk.Frame(split, bg=COLORS["bg"])
        right.grid(row=0, column=1, sticky="nsew")
        info_card = Card(right, padding=12)
        info_card.pack(fill="x")
        self.record_title = tk.Label(info_card.body, text="校准曲线", bg=COLORS["white"], fg=COLORS["text"],
                                     font=(FONT[0], 12, "bold"))
        self.record_title.pack(side="left")
        self.record_badge = badge(info_card.body, "—", "muted")
        self.record_badge.pack(side="left", padx=10)
        tk.Label(info_card.body, text="试算设置值", bg=COLORS["white"], fg=COLORS["muted"],
                 font=FONT_SMALL).pack(side="right", padx=(10, 4))
        self.setpoint_var = tk.StringVar()
        ttk.Entry(info_card.body, textvariable=self.setpoint_var, width=10).pack(side="right")
        ttk.Button(info_card.body, text="插值试算", style="Primary.TButton", command=self.try_interpolate).pack(side="right", padx=6)
        self.interp_label = tk.Label(info_card.body, text="", bg=COLORS["white"], fg=COLORS["muted"],
                                     font=FONT_SMALL)
        self.interp_label.pack(side="right", padx=10)

        chart_card = Card(right, padding=10)
        chart_card.pack(fill="both", expand=True, pady=(10, 0))
        self.chart = LineChart(chart_card.body, height=260)
        self.chart.pack(fill="both", expand=True)

        points_card = Card(right, padding=12)
        points_card.pack(fill="x", pady=(10, 0))
        tk.Label(points_card.body, text="校准点", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w")
        self.point_table = DataTable(points_card.body, [
            ("setpoint_value", "设置值", 90), ("setpoint_unit", "单位", 70),
            ("measured_flow", "实测流速", 100), ("flow_unit", "单位", 80),
            ("measured_volume", "实测体积", 90), ("run_duration", "运行时长", 90),
        ], height=5)
        self.point_table.pack(fill="x", pady=(6, 0))

    # ---------- 刷新 ----------
    def on_show(self):
        self.refresh()

    def refresh(self):
        pumps = self.ctx.repos.pumps.active()
        self.pump_map = {}
        labels = []
        for p in pumps:
            label = f"{p['pump_code']} · {p['pump_name']}"
            labels.append(label)
            self.pump_map[label] = p["pump_id"]
        self.pump_combo.configure(values=labels)
        if self.pump_var.get() not in self.pump_map:
            self.pump_var.set(labels[0] if labels else "")
        self.refresh_records()

    def refresh_records(self):
        pump_id = self.pump_map.get(self.pump_var.get())
        if not pump_id:
            self.record_table.clear()
            self.point_table.clear()
            self.chart.set_series([])
            return
        records = self.ctx.repos.calibrations.records(pump_id)
        self.record_table.set_rows(records, "calibration_id")
        if records:
            self.record_table.tree.selection_set(self.record_table.tree.get_children()[0])
        else:
            self.current_calibration = None
            self.point_table.clear()
            self.chart.set_series([])
            self.record_title.configure(text="校准曲线")
            self.record_badge.configure(text=" 无记录 ", bg="#F1F5F9", fg=COLORS["muted"])

    def select_record(self, row: dict):
        self.current_calibration = row
        points = self.ctx.repos.calibrations.points(row["calibration_id"])
        self.point_table.set_rows(points)
        self.record_title.configure(text=f"校准曲线 · {row.get('calibration_date')}")
        status = row.get("calibration_status") or "—"
        self.record_badge.configure(text=f" {status} ")
        kind = {"有效": "success", "过期": "danger", "待审核": "warning"}.get(status, "muted")
        colors = {"success": (COLORS["success_soft"], COLORS["success"]),
                  "danger": (COLORS["danger_soft"], COLORS["danger"]),
                  "warning": (COLORS["warning_soft"], COLORS["warning"]),
                  "muted": ("#F1F5F9", COLORS["muted"])}[kind]
        self.record_badge.configure(bg=colors[0], fg=colors[1])
        series = [{"name": "校准曲线", "points": [(p["setpoint_value"], p.get("measured_flow")) for p in points
                                                if p.get("measured_flow") is not None]}]
        self.chart.set_series(series, x_label=f"设置值 ({points[0]['setpoint_unit'] if points else ''})",
                              y_label="实测流速", empty="没有可绘制的校准点", x_numeric=True)
        if points:
            xs = [p["setpoint_value"] for p in points]
            self.interp_label.configure(text=f"范围 {min(xs):g} ~ {max(xs):g}")
        else:
            self.interp_label.configure(text="")

    # ---------- 手工 ----------
    def manual_create(self):
        pump_id = self.pump_map.get(self.pump_var.get())
        if not pump_id:
            error(self, "请先选择泵")
            return
        dialog = FormDialog(self, "手工新建校准记录", [
            {"key": "calibration_date", "label": "校准日期", "default": now_iso()[:10], "required": True},
            {"key": "calibration_method", "label": "校准方法", "default": "手工录入"},
            {"key": "points", "label": "校准点", "type": "multiline", "lines": 7, "required": True,
             "help": "每行：设置值, 实测流速, [设置值单位], [流速单位]；例如 10, 2.0, rpm, mL/h"},
            {"key": "notes", "label": "备注", "type": "multiline", "lines": 2},
        ], width=620, intro="至少录入 2 个不同设置值的校准点；测速单位需一致。")
        values = dialog.show()
        if not values:
            return
        points = []
        errors = []
        for line_no, line in enumerate(values["points"].splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in re.split(r"[,，\t;]+", line)]
            if len(parts) < 2:
                errors.append(f"第 {line_no} 行字段不足")
                continue
            try:
                setpoint = float(parts[0])
                flow = float(parts[1])
            except ValueError:
                errors.append(f"第 {line_no} 行设置值或流速不是数字")
                continue
            points.append({
                "setpoint_value": setpoint,
                "setpoint_unit": parts[2] if len(parts) > 2 and parts[2] else "rpm",
                "measured_flow": flow,
                "flow_unit": parts[3] if len(parts) > 3 and parts[3] else "mL/h",
            })
        if errors:
            error(self, "；".join(errors))
            return
        if len(points) < 2:
            error(self, "至少需要 2 个有效校准点")
            return
        try:
            cid = self.ctx.repos.calibrations.create(pump_id, values, points, self.ctx.operator)
        except Exception as exc:
            error(self, f"保存失败：{exc}")
            return
        self.ctx.audit("新增泵校准", "pump_calibration", cid)
        self.refresh_records()
        self.set_status("校准记录已保存为待审核")

    def import_file(self):
        pump_id = self.pump_map.get(self.pump_var.get())
        if not pump_id:
            error(self, "请先选择泵")
            return
        CalibrationImportDialog(self, self, pump_id)

    def set_effective(self):
        row = self.current_calibration
        if not row:
            info(self, "请先选择校准记录")
            return
        if not confirm(self, "设为有效", "设为有效后，同一泵的其他有效校准将自动标记为过期。继续？"):
            return
        self.ctx.repos.calibrations.set_status(row["calibration_id"], "有效")
        self.ctx.audit("设置校准有效", "pump_calibration", row["calibration_id"])
        self.refresh_records()
        self.set_status("校准记录已设为有效")

    def set_expired(self):
        row = self.current_calibration
        if not row:
            return
        self.ctx.repos.calibrations.set_status(row["calibration_id"], "过期")
        self.ctx.audit("设置校准过期", "pump_calibration", row["calibration_id"])
        self.refresh_records()

    def try_interpolate(self):
        row = self.current_calibration
        if not row:
            info(self, "请先选择校准记录")
            return
        try:
            value = float(self.setpoint_var.get())
        except ValueError:
            error(self, "试算设置值必须是数字")
            return
        points = self.ctx.repos.calibrations.points(row["calibration_id"])
        result = interpolate(points, value)
        if result["flow_ml_h"] is None:
            self.interp_label.configure(text=result["message"], fg=COLORS["warning"])
        else:
            self.interp_label.configure(text=f"{result['flow_ml_h']:.3f} mL/h", fg=COLORS["success"])
