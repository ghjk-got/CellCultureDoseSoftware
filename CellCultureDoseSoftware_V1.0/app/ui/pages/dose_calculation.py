# -*- coding: utf-8 -*-
"""实际剂量核算：累计体积差、流速积分、偏差与完成率。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ...services import dose_calc
from ...services.units import fmt
from ..base import Page
from ..theme import COLORS, FONT, FONT_H3, FONT_SMALL
from ..widgets import Card, DataTable, LineChart, badge, confirm, error, fmt_num, human_dt, info


class DoseCalculationPage(Page):
    key = "dose_calc"
    title = "剂量核算"
    subtitle = "累计体积差、流速积分、偏差与完成率"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.pump_map: dict[str, str] = {}
        self.event_map: dict[str, dict] = {}
        self.current_result: dict | None = None
        self.current_rows: list[dict] = []
        self.current_event: dict | None = None
        self._build()
        self.refresh()

    def _build(self):
        form = Card(self, padding=10)
        form.pack(fill="x")
        grid = tk.Frame(form.body, bg=COLORS["white"])
        grid.pack(fill="x")
        for i in range(6):
            grid.grid_columnconfigure(i, weight=1, uniform="calc")

        def lab(parent, text, row, col):
            tk.Label(parent, text=text, bg=COLORS["white"], fg=COLORS["muted"],
                     font=FONT_SMALL, anchor="w").grid(row=row, column=col, sticky="w", padx=(0, 8), pady=(4, 0))

        lab(grid, "泵", 0, 0)
        self.pump_var = tk.StringVar()
        self.pump_combo = ttk.Combobox(grid, textvariable=self.pump_var, state="readonly")
        self.pump_combo.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(2, 8))
        self.pump_combo.bind("<<ComboboxSelected>>", lambda e: self._pump_changed())

        lab(grid, "补料事件（可选）", 0, 1)
        self.event_var = tk.StringVar()
        self.event_combo = ttk.Combobox(grid, textvariable=self.event_var, state="readonly")
        self.event_combo.grid(row=1, column=1, columnspan=2, sticky="ew", padx=(0, 10), pady=(2, 8))
        self.event_combo.bind("<<ComboboxSelected>>", lambda e: self._event_selected())

        lab(grid, "核算开始", 0, 3)
        self.start_var = tk.StringVar()
        ttk.Entry(grid, textvariable=self.start_var).grid(row=1, column=3, sticky="ew", padx=(0, 10), pady=(2, 8))
        lab(grid, "核算结束", 0, 4)
        self.end_var = tk.StringVar()
        ttk.Entry(grid, textvariable=self.end_var).grid(row=1, column=4, sticky="ew", padx=(0, 10), pady=(2, 8))
        lab(grid, "计划量 (mL)", 0, 5)
        self.planned_var = tk.StringVar()
        ttk.Entry(grid, textvariable=self.planned_var).grid(row=1, column=5, sticky="ew", pady=(2, 8))

        bar = tk.Frame(form.body, bg=COLORS["white"])
        bar.pack(fill="x", pady=(8, 0))
        ttk.Button(bar, text="运行核算", style="Primary.TButton", command=self.run_calculation).pack(side="left")
        ttk.Button(bar, text="保存核算结果", style="Success.TButton", command=self.save_result).pack(side="left", padx=8)
        tk.Label(bar, text="允许采样间隔 (h)", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="left", padx=(16, 4))
        self.gap_var = tk.StringVar(value=str(self.ctx.settings.max_sample_gap_h))
        ttk.Entry(bar, textvariable=self.gap_var, width=7).pack(side="left")
        self.notes_var = tk.StringVar()
        tk.Label(bar, text="备注", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="left", padx=(16, 4))
        ttk.Entry(bar, textvariable=self.notes_var, width=26).pack(side="left")
        self.data_source_label = tk.Label(bar, text="", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL)
        self.data_source_label.pack(side="right")

        result = tk.Frame(self, bg=COLORS["bg"])
        result.pack(fill="both", expand=True, pady=(12, 0))
        result.grid_columnconfigure(0, weight=1)
        result.grid_rowconfigure(1, weight=1)

        metrics_card = Card(result, padding=14)
        metrics_card.grid(row=0, column=0, sticky="ew")
        head = tk.Frame(metrics_card.body, bg=COLORS["white"])
        head.pack(fill="x")
        tk.Label(head, text="核算结果", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        self.quality_badge = badge(head, "尚无结果", "muted")
        self.quality_badge.pack(side="left", padx=10)
        self.result_message = tk.Label(head, text="", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL)
        self.result_message.pack(side="left", padx=8)
        metrics = tk.Frame(metrics_card.body, bg=COLORS["white"])
        metrics.pack(fill="x", pady=(8, 0))
        self.metric_labels = {}
        for i, (key, title, color) in enumerate((
                ("actual", "实际量 (mL)", COLORS["accent"]), ("integral", "流速积分 (mL)", COLORS["info"]),
                ("deviation", "偏差量 (mL)", COLORS["warning"]), ("deviation_pct", "偏差率 (%)", COLORS["danger"]),
                ("completion", "完成率 (%)", COLORS["success"]))):
            metrics.grid_columnconfigure(i, weight=1, uniform="m")
            box = tk.Frame(metrics, bg=COLORS["white"])
            box.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 12, 0))
            tk.Label(box, text=title, bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(anchor="w")
            value = tk.Label(box, text="—", bg=COLORS["white"], fg=color, font=(FONT[0], 18, "bold"))
            value.pack(anchor="w")
            self.metric_labels[key] = value

        charts = tk.Frame(result, bg=COLORS["bg"])
        charts.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        charts.grid_columnconfigure(0, weight=1)
        charts.grid_columnconfigure(1, weight=1)
        charts.grid_rowconfigure(0, weight=1)
        flow_card = Card(charts, padding=10)
        flow_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        tk.Label(flow_card.body, text="流速—时间", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w")
        self.flow_chart = LineChart(flow_card.body, height=165)
        self.flow_chart.pack(fill="both", expand=True, pady=(4, 0))
        cum_card = Card(charts, padding=10)
        cum_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        tk.Label(cum_card.body, text="累计体积—时间", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w")
        self.cum_chart = LineChart(cum_card.body, height=165)
        self.cum_chart.pack(fill="both", expand=True, pady=(4, 0))

        quality_card = Card(self, padding=12)
        quality_card.pack(fill="x", pady=(10, 0))
        tk.Label(quality_card.body, text="数据质量与异常", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w")
        self.quality_text = tk.Label(quality_card.body, text="运行核算后显示数据点数、覆盖时间、计数区段与缺失区间。",
                                     bg=COLORS["white"], fg=COLORS["muted"], font=(FONT[0], 8),
                                     justify="left", anchor="w", wraplength=1100)
        self.quality_text.pack(fill="x", pady=(4, 0))

        history_card = Card(self, padding=12)
        history_card.pack(fill="x", pady=(10, 0))
        h = tk.Frame(history_card.body, bg=COLORS["white"])
        h.pack(fill="x")
        tk.Label(h, text="核算历史", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        self.history = DataTable(history_card.body, [
            ("calculation_id", "核算编号", 145), ("pump_code", "泵", 80), ("liquid_name", "液体", 100),
            ("time_start", "开始", 135), ("time_end", "结束", 135), ("actual_volume_ml", "实际量", 80),
            ("completion_percent", "完成率%", 75), ("quality_status", "质量", 75),
            ("calculation_version", "版本", 50),
        ], height=2, id_key="calculation_id", on_select=self._show_saved)
        self.history.pack(fill="x", pady=(6, 0))

    # ---------- 刷新 ----------
    def on_show(self):
        self.refresh()

    def on_batch_changed(self):
        if self.winfo_exists():
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
        self._load_events()
        batch_id = self.app.current_batch_id
        if batch_id:
            self.history.set_rows(self.ctx.repos.doses.list_for_batch(batch_id), "calculation_id")
        else:
            self.history.clear()
        self._pump_changed()

    def _load_events(self):
        batch_id = self.app.current_batch_id
        self.event_map = {}
        labels = ["（不关联事件）"]
        if batch_id:
            plan = self.ctx.repos.plans.latest(batch_id)
            if plan:
                for ev in self.ctx.repos.plans.events(plan["plan_id"]):
                    label = (f"V{plan['version_no']} · {ev.get('stage_name') or ''} · {ev.get('liquid_name')} · "
                             f"{human_dt(ev.get('planned_start'))}")
                    labels.append(label)
                    self.event_map[label] = ev
        self.event_combo.configure(values=labels)
        if self.event_var.get() not in labels:
            self.event_var.set(labels[0])

    def _pump_changed(self):
        batch_id = self.app.current_batch_id
        pump_id = self.pump_map.get(self.pump_var.get())
        if batch_id and pump_id:
            imports = self.ctx.repos.imports.imports_for_pump(batch_id, pump_id)
            self.data_source_label.configure(text=f"该泵已有 {len(imports)} 个导入批次")
        else:
            self.data_source_label.configure(text="")

    def _event_selected(self):
        ev = self.event_map.get(self.event_var.get())
        self.current_event = ev
        if not ev:
            return
        pump = self.ctx.repos.pumps.get(ev["pump_id"])
        if pump:
            for label, pid in self.pump_map.items():
                if pid == ev["pump_id"]:
                    self.pump_var.set(label)
                    break
        self.start_var.set(ev.get("planned_start") or "")
        self.end_var.set(ev.get("planned_end") or "")
        self.planned_var.set(fmt_num(ev.get("planned_volume_ml")) if ev.get("planned_volume_ml") is not None else "")
        self._pump_changed()

    # ---------- 核算 ----------
    def run_calculation(self):
        batch_id = self.app.require_batch()
        if not batch_id:
            return
        pump_id = self.pump_map.get(self.pump_var.get())
        if not pump_id:
            error(self, "请选择泵")
            return
        start_dt, end_dt = dose_calc.parse_ts(self.start_var.get()), dose_calc.parse_ts(self.end_var.get())
        if not start_dt or not end_dt:
            error(self, "请填写可解析的核算开始和结束时间")
            return
        if start_dt > end_dt:
            error(self, "核算开始时间晚于结束时间")
            return
        start = dose_calc.iso(start_dt)
        end = dose_calc.iso(end_dt)
        rows = self.ctx.repos.imports.data_for(batch_id, pump_id, start, end)
        if not rows:
            error(self, "该时间窗口内没有标准化剂量数据。请先导入 Dose Monitor 数据，或调整时间窗口。")
            return
        try:
            gap = float(self.gap_var.get())
        except ValueError:
            gap = float(self.ctx.settings.max_sample_gap_h)
        planned = None
        if self.planned_var.get().strip():
            try:
                planned = float(self.planned_var.get())
            except ValueError:
                error(self, "计划量必须是数字")
                return
        result = dose_calc.calculate(rows, planned, start, end, gap)
        self.current_result = result
        self.current_rows = rows
        self._render_result(result, rows)
        self.set_status(f"核算完成：{result['quality_status']}")

    def _render_result(self, result: dict, rows: list[dict]):
        status = result.get("quality_status") or "—"
        self.quality_badge.configure(text=f" {status} ")
        colors = {"success": (COLORS["success_soft"], COLORS["success"]),
                  "warning": (COLORS["warning_soft"], COLORS["warning"]),
                  "danger": (COLORS["danger_soft"], COLORS["danger"]),
                  "muted": ("#F1F5F9", COLORS["muted"])}
        kind = {"有效": "success", "待审核": "warning", "估算": "warning", "无效": "danger"}.get(status, "muted")
        bg, fg = colors[kind]
        self.quality_badge.configure(bg=bg, fg=fg)
        self.result_message.configure(text=result.get("message") or "", fg=COLORS["warning"])
        values = {
            "actual": result.get("actual_volume_ml"),
            "integral": result.get("flow_integral_ml"),
            "deviation": result.get("deviation_ml"),
            "deviation_pct": result.get("deviation_percent"),
            "completion": result.get("completion_percent"),
        }
        for key, value in values.items():
            self.metric_labels[key].configure(text=fmt_num(value))
        flow_points = [(r["timestamp_utc"], r.get("flow_rate")) for r in rows if r.get("flow_rate") is not None]
        cum_points = [(r["timestamp_utc"], r.get("total_volume")) for r in rows if r.get("total_volume") is not None]
        self.flow_chart.set_series([{"name": "流速", "points": flow_points}], y_label="mL/h",
                                   empty="没有流速数据（可能仅有累计体积）")
        self.cum_chart.set_series([{"name": "累计体积", "points": cum_points}], y_label="mL",
                                  empty="没有累计体积数据")
        gaps = result.get("gaps") or []
        anomalies = result.get("anomalies") or []
        lines = [
            f"数据点数：{result.get('point_count', 0)}    计数区段：{result.get('segment_count', 0)}    "
            f"覆盖时间：{human_dt(result.get('coverage_start'))} ~ {human_dt(result.get('coverage_end'))}",
            f"计算方法：{result.get('calculation_method') or '—'}    计划量：{fmt_num(result.get('planned_volume_ml'))} mL"
            + ("    断点：" + "；".join(f"{human_dt(g['from'])}~{human_dt(g['to'])} ({g['hours']} h)" for g in gaps[:3]) if gaps else ""),
            ("异常：" + "；".join(f"[{a.get('severity')}] {a.get('anomaly_type')} - {a.get('description')}" for a in anomalies[:4]))
            if anomalies else "未发现计数重置、重复时间或数据断点；累计体积差仅在连续计数区段内计算。",
        ]
        self.quality_text.configure(text="\n".join(lines), fg=COLORS["text"])

    def save_result(self):
        if not self.current_result:
            info(self, "请先运行核算")
            return
        batch_id = self.app.current_batch_id
        pump_id = self.pump_map.get(self.pump_var.get())
        if not batch_id or not pump_id:
            return
        result = self.current_result
        if result.get("quality_status") == "无效":
            if not confirm(self, "保存无效结果", "质量为“无效”，是否仍保存以保留审计记录？"):
                return
        ev = self.current_event or {}
        liquid_id = ev.get("liquid_id")
        if not liquid_id:
            mapping = self.ctx.repos.batches.mapping_for_pump(batch_id, pump_id)
            liquid_id = mapping["liquid_id"] if mapping else None
        data_import_id = next((r.get("import_id") for r in self.current_rows if r.get("import_id")), None)
        try:
            cid = self.ctx.repos.doses.create({
                "batch_id": batch_id, "event_id": ev.get("event_id"), "pump_id": pump_id,
                "liquid_id": liquid_id, "time_start": dose_calc.iso(dose_calc.parse_ts(self.start_var.get())),
                "time_end": dose_calc.iso(dose_calc.parse_ts(self.end_var.get())),
                "planned_volume_ml": result.get("planned_volume_ml"),
                "actual_volume_ml": result.get("actual_volume_ml"),
                "flow_integral_ml": result.get("flow_integral_ml"),
                "deviation_ml": result.get("deviation_ml"),
                "deviation_percent": result.get("deviation_percent"),
                "completion_percent": result.get("completion_percent"),
                "calculation_method": result.get("calculation_method"),
                "quality_status": result.get("quality_status"),
                "data_import_id": data_import_id,
                "notes": self.notes_var.get().strip(),
            })
        except Exception as exc:
            error(self, f"保存失败：{exc}")
            return
        for anomaly in result.get("anomalies", []):
            self.ctx.repos.anomalies.create({
                "batch_id": batch_id, "calculation_id": cid, "import_id": data_import_id,
                "anomaly_type": anomaly.get("anomaly_type"), "severity": anomaly.get("severity"),
                "description": anomaly.get("description"),
            })
        self.ctx.audit("保存剂量核算", "dose_calculation", cid, after={"quality": result.get("quality_status")})
        self.refresh()
        self.set_status(f"核算结果已保存：{cid}")

    def _show_saved(self, row: dict):
        full = self.ctx.repos.doses.get_full(row["calculation_id"])
        if not full:
            return
        result = {
            "quality_status": full.get("quality_status"),
            "actual_volume_ml": full.get("actual_volume_ml"),
            "flow_integral_ml": full.get("flow_integral_ml"),
            "deviation_ml": full.get("deviation_ml"),
            "deviation_percent": full.get("deviation_percent"),
            "completion_percent": full.get("completion_percent"),
            "planned_volume_ml": full.get("planned_volume_ml"),
            "calculation_method": full.get("calculation_method"),
            "message": f"历史核算版本 {full.get('calculation_version')} · {human_dt(full.get('calculated_at'))}",
        }
        rows = self.ctx.repos.imports.data_for(full["batch_id"], full["pump_id"],
                                               full["time_start"], full["time_end"])
        calc = dose_calc.calculate(rows, full.get("planned_volume_ml"), full["time_start"],
                                    full["time_end"], self.ctx.settings.max_sample_gap_h)
        for key in ("point_count", "segment_count", "coverage_start", "coverage_end", "gaps", "anomalies"):
            result[key] = calc.get(key)
        for label, pid in self.pump_map.items():
            if pid == full["pump_id"]:
                self.pump_var.set(label)
                break
        self._render_result(result, rows)
        self.start_var.set(full.get("time_start") or "")
        self.end_var.set(full.get("time_end") or "")
        self.planned_var.set(fmt_num(full.get("planned_volume_ml")) if full.get("planned_volume_ml") is not None else "")
