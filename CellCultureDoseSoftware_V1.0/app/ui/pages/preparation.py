# -*- coding: utf-8 -*-
"""配制计算：配方选择、体积、纯度修正、称量清单与配制记录。"""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import ttk

from ...db import new_id, now_iso
from ...services.formula_calc import calculate_formula
from ...services.units import volume_to_l
from ..base import Page
from ..theme import COLORS, FONT, FONT_H2, FONT_H3, FONT_SMALL
from ..widgets import Card, DataTable, error, fmt_num, info, open_path


class PreparationPage(Page):
    key = "preparation"
    title = "配制计算"
    subtitle = "目标浓度、纯度修正、母液与称量清单"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.formula_map: dict[str, str] = {}
        self.batch_map: dict[str, str] = {}
        self.current_result: dict | None = None
        self.last_prep_id: str | None = None
        self._build()
        self.table.columns[0]["format"] = lambda v, r: f"{v}  {r.get('component_name') or ''}"
        self.table.columns[1]["format"] = lambda v, r: f"{fmt_num(v)} {r.get('concentration_unit') or ''}"
        self.refresh()

    def _build(self):
        top = tk.Frame(self, bg=COLORS["bg"])
        top.pack(fill="both", expand=False)
        form_card = Card(top, padding=16)
        form_card.pack(fill="x")
        grid = tk.Frame(form_card.body, bg=COLORS["white"])
        grid.pack(fill="x")
        for i in range(6):
            grid.grid_columnconfigure(i, weight=1, uniform="f")

        def label(parent, text, row, col):
            tk.Label(parent, text=text, bg=COLORS["white"], fg=COLORS["muted"],
                     font=FONT_SMALL, anchor="w").grid(row=row, column=col, sticky="w", padx=(0, 6), pady=(4, 0))

        label(grid, "配方版本", 0, 0)
        self.formula_var = tk.StringVar()
        self.formula_combo = ttk.Combobox(grid, textvariable=self.formula_var, state="readonly")
        self.formula_combo.grid(row=1, column=0, columnspan=4, sticky="ew", padx=(0, 12), pady=(2, 8))
        self.formula_combo.bind("<<ComboboxSelected>>", lambda e: self._formula_selected())

        label(grid, "关联批次（可选）", 0, 4)
        self.batch_var = tk.StringVar()
        self.batch_combo = ttk.Combobox(grid, textvariable=self.batch_var, state="readonly")
        self.batch_combo.grid(row=1, column=4, columnspan=2, sticky="ew", pady=(2, 8))
        self.batch_combo.bind("<<ComboboxSelected>>", lambda e: self._batch_selected())

        label(grid, "目标体积", 2, 0)
        self.volume_var = tk.StringVar(value="1000")
        ttk.Entry(grid, textvariable=self.volume_var).grid(row=3, column=0, sticky="ew", padx=(0, 8), pady=(2, 8))
        label(grid, "体积单位", 2, 1)
        self.volume_unit = tk.StringVar(value="mL")
        ttk.Combobox(grid, textvariable=self.volume_unit, values=["mL", "L", "uL"], state="readonly").grid(
            row=3, column=1, sticky="ew", padx=(0, 12), pady=(2, 8))
        label(grid, "实际称量总量 (g)", 2, 2)
        self.weighed_var = tk.StringVar()
        ttk.Entry(grid, textvariable=self.weighed_var).grid(row=3, column=2, sticky="ew", padx=(0, 12), pady=(2, 8))
        label(grid, "实际定容体积", 2, 3)
        self.final_volume_var = tk.StringVar()
        ttk.Entry(grid, textvariable=self.final_volume_var).grid(row=3, column=3, sticky="ew", padx=(0, 12), pady=(2, 8))
        label(grid, "配制时间", 2, 4)
        self.time_var = tk.StringVar(value=now_iso())
        ttk.Entry(grid, textvariable=self.time_var).grid(row=3, column=4, sticky="ew", padx=(0, 12), pady=(2, 8))
        label(grid, "操作人", 2, 5)
        self.operator_var = tk.StringVar(value=self.ctx.operator)
        ttk.Entry(grid, textvariable=self.operator_var).grid(row=3, column=5, sticky="ew", pady=(2, 8))

        self.notes_var = tk.StringVar()

        bar = tk.Frame(form_card.body, bg=COLORS["white"])
        bar.pack(fill="x", pady=(10, 0))
        ttk.Button(bar, text="计算预览", style="Primary.TButton", command=self.preview).pack(side="left")
        ttk.Button(bar, text="保存配制记录", style="Success.TButton", command=self.save_record).pack(side="left", padx=8)
        ttk.Button(bar, text="导出称量清单", style="Secondary.TButton", command=self.export_current).pack(side="left")
        tk.Label(bar, text="备注", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="left", padx=(16, 4))
        ttk.Entry(bar, textvariable=self.notes_var, width=24).pack(side="left")
        self.formula_hint = tk.Label(bar, text="", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL)
        self.formula_hint.pack(side="right")

        result_area = tk.Frame(self, bg=COLORS["bg"])
        result_area.pack(fill="both", expand=True, pady=(12, 0))
        result_area.grid_columnconfigure(0, weight=3)
        result_area.grid_columnconfigure(1, weight=1)
        result_area.grid_rowconfigure(0, weight=1)

        table_card = Card(result_area, padding=12)
        table_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        h = tk.Frame(table_card.body, bg=COLORS["white"])
        h.pack(fill="x")
        tk.Label(h, text="理论用量与称量清单", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        self.table = DataTable(table_card.body, [
            ("component_code", "组分", 145), ("target_concentration", "目标浓度", 90),
            ("source_type", "来源", 60), ("purity_fraction", "纯度", 45),
            ("theoretical_amount_g", "理论(g)", 60), ("corrected_amount_g", "修正(g)", 60),
            ("stock_volume_ml", "母液(mL)", 60),
        ], height=6)
        self.table.pack(fill="both", expand=True, pady=(8, 0))

        total_card = Card(result_area, padding=16)
        total_card.grid(row=0, column=1, sticky="nsew")
        tk.Label(total_card.body, text="计算结果", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w")
        self.total_lines = {}
        metrics_frame = tk.Frame(total_card.body, bg=COLORS["white"])
        metrics_frame.pack(fill="x")
        for i, (key, title) in enumerate((("theory", "理论总量 (g)"), ("corrected", "纯度修正 (g)"),
                                          ("stock", "母液合计 (mL)"), ("solvent", "定容补足 (mL)"),
                                          ("final_conc", "实际总量浓度 (g/L)"))):
            box = tk.Frame(metrics_frame, bg=COLORS["white"])
            box.grid(row=i // 2, column=i % 2, sticky="ew", padx=(0, 10), pady=(8, 0))
            tk.Label(box, text=title, bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(anchor="w")
            value = tk.Label(box, text="—", bg=COLORS["white"], fg=COLORS["text"], font=(FONT[0], 14, "bold"))
            value.pack(anchor="w")
            self.total_lines[key] = value
        metrics_frame.grid_columnconfigure(0, weight=1)
        metrics_frame.grid_columnconfigure(1, weight=1)
        self.message = tk.Label(total_card.body, text="", bg=COLORS["white"], fg=COLORS["muted"],
                                font=FONT_SMALL, wraplength=280, justify="left", anchor="w")
        self.message.pack(fill="x", pady=(12, 0))

        history_card = Card(self, padding=12, height=170)
        history_card.pack(fill="x", side="bottom", pady=(12, 0))
        history_card.pack_propagate(False)
        h2 = tk.Frame(history_card.body, bg=COLORS["white"])
        h2.pack(fill="x")
        tk.Label(h2, text="最近配制记录", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        ttk.Button(h2, text="导出选中称量清单", style="Ghost.TButton", command=self.export_selected).pack(side="right")
        self.history = DataTable(history_card.body, [
            ("prepared_at", "配制时间", 130), ("formula_code", "配方", 110), ("version_no", "版本", 55),
            ("batch_code", "批次", 120), ("target_volume", "体积", 80), ("volume_unit", "单位", 55),
            ("theoretical_amount", "理论总量(g)", 100), ("operator", "操作人", 90),
        ], height=3, id_key="preparation_id")
        self.history.pack(fill="both", expand=True, pady=(6, 0))

    # ---------- 刷新 ----------
    def on_show(self):
        self.refresh()

    def on_batch_changed(self):
        if self.winfo_exists():
            self.refresh()

    def refresh(self):
        formulas = self.ctx.repos.formulas.list_with_counts()
        self.formula_map = {}
        labels = []
        for f in formulas:
            label = f"{f['formula_code']} V{f['version_no']} · {f['formula_name']}"
            labels.append(label)
            self.formula_map[label] = f["formula_id"]
        self.formula_combo.configure(values=labels)
        current_formula = self.formula_var.get()
        if current_formula not in self.formula_map:
            published = labels[0] if labels else ""
            self.formula_var.set(published)
        batches = self.ctx.repos.batches.list_with_reactor()
        self.batch_map = {}
        batch_labels = []
        for b in batches:
            label = b["batch_code"]
            batch_labels.append(label)
            self.batch_map[label] = b["batch_id"]
        self.batch_combo.configure(values=batch_labels)
        current_batch = self.batch_var.get()
        if current_batch not in self.batch_map:
            current_batch = next((l for l, bid in self.batch_map.items() if bid == self.app.current_batch_id), "")
            self.batch_var.set(current_batch)
        self._formula_selected()
        self._load_history()

    def _formula_selected(self):
        fid = self.formula_map.get(self.formula_var.get())
        if not fid:
            self.formula_hint.configure(text="尚无配方，请先到配方管理新建")
            return
        formula = self.ctx.repos.formulas.get(fid)
        details = self.ctx.repos.formulas.details(fid)
        if formula:
            self.formula_hint.configure(text=f"类型：{formula.get('formula_type') or '—'} · 组分 {len(details)} 项 · 状态 {formula['status']}")
        self.preview()

    def _batch_selected(self):
        bid = self.batch_map.get(self.batch_var.get())
        if bid:
            self.ctx.settings.last_batch_id = bid
            self.ctx.settings.save()
            self.app.refresh_batches()
        self.preview()

    def _load_history(self):
        rows = [dict(r) for r in self.ctx.db.q(
            "SELECT p.*, f.formula_code, f.version_no, b.batch_code FROM preparation_record p "
            "JOIN formula_info f ON f.formula_id=p.formula_id LEFT JOIN batch_info b ON b.batch_id=p.batch_id "
            "ORDER BY p.prepared_at DESC LIMIT 30")]
        self.history.set_rows(rows, "preparation_id")

    # ---------- 计算 ----------
    def preview(self):
        fid = self.formula_map.get(self.formula_var.get())
        if not fid:
            return
        try:
            volume = float(self.volume_var.get())
        except ValueError:
            self.message.configure(text="目标体积必须是有效数字", fg=COLORS["danger"])
            return
        details = self.ctx.repos.formulas.details(fid)
        result = calculate_formula(details, volume, self.volume_unit.get())
        self.current_result = result
        rows = []
        for line in result["lines"]:
            rows.append(line)
        self.table.set_rows(rows)
        self.total_lines["theory"].configure(text=fmt_num(result["total_theoretical_g"]))
        self.total_lines["corrected"].configure(text=fmt_num(result["total_corrected_g"]))
        self.total_lines["stock"].configure(text=fmt_num(result["total_stock_ml"]))
        self.total_lines["solvent"].configure(text=fmt_num(result["solvent_ml"]))
        final_conc = None
        try:
            if self.weighed_var.get().strip() and self.final_volume_var.get().strip():
                final_l = volume_to_l(float(self.final_volume_var.get()), self.volume_unit.get())
                if final_l > 0:
                    final_conc = float(self.weighed_var.get()) / final_l
        except ValueError:
            final_conc = None
        self.total_lines["final_conc"].configure(text=fmt_num(final_conc))
        if result["errors"]:
            self.message.configure(text="错误：" + "；".join(result["errors"][:4]), fg=COLORS["danger"])
        elif result["warnings"]:
            self.message.configure(text="警告：" + "；".join(result["warnings"][:4]), fg=COLORS["warning"])
        else:
            self.message.configure(text="计算完成。保存后将生成不可变的配制记录快照。", fg=COLORS["success"])

    def save_record(self):
        fid = self.formula_map.get(self.formula_var.get())
        if not fid:
            info(self, "请先选择配方")
            return
        if not self.current_result or not self.current_result.get("lines"):
            self.preview()
        result = self.current_result
        if not result or result.get("errors"):
            error(self, "计算结果存在错误，不能保存配制记录")
            return
        if not confirm(self, "保存配制记录", "确认将当前计算结果保存为正式配制记录？"):
            return
        try:
            volume = float(self.volume_var.get())
        except ValueError:
            error(self, "目标体积无效")
            return
        weighed = None
        final_volume = None
        try:
            weighed = float(self.weighed_var.get()) if self.weighed_var.get().strip() else None
            final_volume = float(self.final_volume_var.get()) if self.final_volume_var.get().strip() else None
        except ValueError:
            error(self, "实际称量量或定容体积不是有效数字")
            return
        final_conc = None
        try:
            if weighed is not None and final_volume:
                final_conc = weighed / volume_to_l(final_volume, self.volume_unit.get())
        except ValueError:
            final_conc = None
        pid = new_id("PREP")
        snapshot = json.dumps(result["lines"], ensure_ascii=False, default=str)
        self.ctx.db.execute(
            "INSERT INTO preparation_record(preparation_id,batch_id,formula_id,target_volume,volume_unit,"
            "theoretical_amount,corrected_amount,actual_weighed_amount,actual_final_volume,"
            "calculated_actual_concentration,prepared_at,operator,notes,detail_snapshot) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (pid, self.batch_map.get(self.batch_var.get()), fid, volume, self.volume_unit.get(),
             result["total_theoretical_g"], result["total_corrected_g"], weighed, final_volume,
             final_conc, self.time_var.get().strip() or now_iso(), self.operator_var.get().strip(),
             self.notes_var.get().strip(), snapshot),
        )
        self.last_prep_id = pid
        self.ctx.audit("保存配制记录", "preparation", pid, after={"formula_id": fid, "volume": volume})
        self._load_history()
        self.set_status(f"配制记录已保存：{pid}")

    def export_current(self):
        if not self.current_result:
            self.preview()
        fid = self.formula_map.get(self.formula_var.get())
        if not fid:
            return
        if not self.last_prep_id:
            info(self, "请先保存配制记录，再导出称量清单")
            return
        self._export(self.last_prep_id)

    def export_selected(self):
        pid = self.history.selected_id()
        if not pid:
            info(self, "请先选择一条配制记录")
            return
        self._export(pid)

    def _export(self, pid: str):
        try:
            path = self.ctx.reports.generate_weighing_list(pid)
            self.set_status(f"称量清单已导出：{path.name}")
            if confirm(self, "导出完成", f"称量清单已保存：\n{path}\n\n是否立即打开？"):
                open_path(path)
        except Exception as exc:
            error(self, f"导出失败：{exc}")
