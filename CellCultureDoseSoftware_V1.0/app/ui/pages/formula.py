# -*- coding: utf-8 -*-
"""配方管理：版本、组分明细与计算预览。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ...db import now_iso
from ...services.formula_calc import calculate_formula
from ..base import Page
from ..theme import COLORS, FONT, FONT_H2, FONT_H3, FONT_SMALL
from ..widgets import Card, DataTable, FormDialog, badge, confirm, error, fmt_num, info


class FormulaPage(Page):
    key = "formula"
    title = "配方管理"
    subtitle = "配方版本、组分明细与发布状态"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.current_id: str | None = None
        self.current: dict | None = None
        self.details: list[dict] = []
        self._build()
        self._configure_formats()
        self.refresh()

    def _build(self):
        top = tk.Frame(self, bg=COLORS["bg"])
        top.pack(fill="x", pady=(0, 12))
        ttk.Button(top, text="新建配方", style="Primary.TButton", command=self.new_formula).pack(side="left")
        ttk.Button(top, text="创建新版本", style="Secondary.TButton", command=self.new_version).pack(side="left", padx=6)
        ttk.Button(top, text="发布 / 停用", style="Secondary.TButton", command=self.publish).pack(side="left")
        ttk.Button(top, text="删除草稿", style="Ghost.TButton", command=self.delete_draft).pack(side="left", padx=6)
        self.search_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.search_var, width=24)
        entry.pack(side="right")
        entry.bind("<Return>", lambda e: self.refresh())
        tk.Label(top, text="搜索配方", bg=COLORS["bg"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="right", padx=6)

        self.split = split = tk.PanedWindow(self, orient="horizontal", bg=COLORS["bg"], sashwidth=8,
                               sashrelief="flat", bd=0)
        split.pack(fill="both", expand=True)

        left = tk.Frame(split, bg=COLORS["white"])
        split.add(left, minsize=340, width=360)
        left_head = tk.Frame(left, bg=COLORS["white"])
        left_head.pack(fill="x", padx=12, pady=10)
        tk.Label(left_head, text="配方版本列表", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        self.count_label = tk.Label(left_head, text="", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL)
        self.count_label.pack(side="right")
        self.table = DataTable(left, [
            ("formula_code", "配方", 185), ("version_no", "版本", 42),
            ("status", "状态", 58), ("detail_count", "组分", 38),
        ], height=18, id_key="formula_id", on_select=self.select_formula)
        self.table.pack(fill="both", expand=True, padx=8, pady=(0, 10))

        right = tk.Frame(split, bg=COLORS["bg"])
        split.add(right, minsize=600)
        self.after_idle(lambda: split.paneconfigure(left, width=360))

        head_card = Card(right, padding=14)
        head_card.pack(fill="x")
        self.head_title = tk.Label(head_card.body, text="请选择配方", bg=COLORS["white"],
                                   fg=COLORS["text"], font=FONT_H2)
        self.head_title.pack(side="left")
        self.status_badge = badge(head_card.body, "—", "muted")
        self.status_badge.pack(side="left", padx=10)
        ttk.Button(head_card.body, text="编辑", style="Ghost.TButton",
                   command=self.edit_header).pack(side="right")
        self.head_meta = tk.Label(head_card.body, text="", bg=COLORS["white"], fg=COLORS["muted"],
                                  font=FONT_SMALL, justify="left", anchor="w")
        self.head_meta.pack(side="left", padx=16)

        detail_card = Card(right, padding=14)
        detail_card.pack(fill="both", expand=True, pady=(12, 0))
        bar = tk.Frame(detail_card.body, bg=COLORS["white"])
        bar.pack(fill="x")
        tk.Label(bar, text="组分明细", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        ttk.Button(bar, text="添加组分", style="Primary.TButton", command=self.add_detail).pack(side="right")
        ttk.Button(bar, text="编辑", style="Secondary.TButton", command=self.edit_detail).pack(side="right", padx=6)
        ttk.Button(bar, text="删除", style="Ghost.TButton", command=self.delete_detail).pack(side="right")
        ttk.Button(bar, text="刷新", style="Ghost.TButton", command=self._reload_details).pack(side="right", padx=6)
        self.detail_table = DataTable(detail_card.body, [
            ("component_code", "组分", 180), ("target_concentration", "目标浓度", 100),
            ("source_type", "来源/纯度", 90),
            ("theoretical_amount_g", "理论(g)", 65), ("corrected_amount_g", "修正(g)", 65),
            ("stock_volume_ml", "母液(mL)", 65),
        ], height=12)
        self.detail_table.pack(fill="both", expand=True, pady=(8, 0))
        self.detail_table.tree.bind("<Double-1>", lambda e: self.edit_detail())

        calc_card = Card(right, padding=14)
        calc_card.pack(fill="x", pady=(12, 0))
        row = tk.Frame(calc_card.body, bg=COLORS["white"])
        row.pack(fill="x")
        tk.Label(row, text="计算预览", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        tk.Label(row, text="目标体积", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="left", padx=(18, 4))
        self.volume_var = tk.StringVar(value="1000")
        ttk.Entry(row, textvariable=self.volume_var, width=10).pack(side="left")
        self.volume_unit = tk.StringVar(value="mL")
        ttk.Combobox(row, textvariable=self.volume_unit, values=["mL", "L", "uL"], width=6,
                     state="readonly").pack(side="left", padx=4)
        ttk.Button(row, text="计算", style="Primary.TButton", command=self.calculate).pack(side="left", padx=8)
        self.total_label = tk.Label(calc_card.body, text="", bg=COLORS["white"], fg=COLORS["text"],
                                    font=(FONT[0], 10, "bold"), anchor="w")
        self.total_label.pack(fill="x", pady=(6, 0))
        self.message = tk.Label(calc_card.body, text="", bg=COLORS["white"], fg=COLORS["muted"],
                                font=FONT_SMALL, wraplength=760, justify="left", anchor="w")
        self.message.pack(fill="x", pady=(6, 0))

    def _configure_formats(self) -> None:
        self.table.columns[0]["format"] = lambda v, r: f"{v}  {r.get('formula_name') or ''}"
        self.detail_table.columns[0]["format"] = lambda v, r: f"{v}  {r.get('component_name') or ''}"
        self.detail_table.columns[1]["format"] = lambda v, r: f"{fmt_num(v)} {r.get('concentration_unit') or ''}"
        self.detail_table.columns[2]["format"] = lambda v, r: f"{v} / {fmt_num(r.get('purity_fraction'))}"

    # ---------- 列表 ----------
    def refresh(self):
        rows = self.ctx.repos.formulas.list_with_counts(self.search_var.get().strip())
        self.table.set_rows(rows, "formula_id")
        self.count_label.configure(text=f"共 {len(rows)} 个版本")
        if self.current_id:
            self.table.select_by_id(self.current_id)
            if not self.table.selected_row():
                self._clear_detail()
        elif rows:
            self.table.tree.selection_set(self.table.tree.get_children()[0])

    def select_formula(self, row: dict):
        self.current_id = row["formula_id"]
        self.current = row
        self.head_title.configure(text=f"{row['formula_code']}  {row['formula_name']}")
        self.status_badge.configure(text=f" {row['status']} ")
        kind = {"已发布": "success", "草稿": "warning", "停用": "danger"}.get(row["status"], "muted")
        colors = {"success": (COLORS["success_soft"], COLORS["success"]),
                  "warning": (COLORS["warning_soft"], COLORS["warning"]),
                  "danger": (COLORS["danger_soft"], COLORS["danger"]),
                  "muted": ("#F1F5F9", COLORS["muted"])}[kind]
        self.status_badge.configure(bg=colors[0], fg=colors[1])
        self.head_meta.configure(text=f"类型：{row.get('formula_type') or '—'}    版本：V{row['version_no']}    "
                                      f"生效日期：{row.get('effective_date') or '—'}    创建：{row.get('created_at') or '—'}")
        self._reload_details()

    def _reload_details(self):
        if not self.current_id:
            return
        self.details = self.ctx.repos.formulas.details(self.current_id)
        self._render_details(self.details)

    def _render_details(self, lines: list[dict]):
        rows = []
        for d in lines:
            rows.append({
                "component_code": d.get("component_code"),
                "component_name": d.get("component_name"),
                "target_concentration": d.get("target_concentration"),
                "concentration_unit": d.get("concentration_unit"),
                "source_type": d.get("source_type"),
                "purity_fraction": d.get("purity_fraction"),
                "theoretical_amount_g": d.get("theoretical_amount_g"),
                "corrected_amount_g": d.get("corrected_amount_g"),
                "stock_volume_ml": d.get("stock_volume_ml"),
            })
        self.detail_table.set_rows(rows)

    def _clear_detail(self):
        self.current_id = None
        self.current = None
        self.details = []
        self.head_title.configure(text="请选择配方")
        self.status_badge.configure(text=" — ", bg="#F1F5F9", fg=COLORS["muted"])
        self.head_meta.configure(text="")
        self.detail_table.clear()
        self.message.configure(text="")

    # ---------- 配方头 ----------
    def new_formula(self):
        dialog = FormDialog(self, "新建配方", [
            {"key": "formula_code", "label": "配方代码", "required": True},
            {"key": "formula_name", "label": "配方名称", "required": True},
            {"key": "formula_type", "label": "配方类型", "type": "combo",
             "values": ["基础培养基", "浓缩培养基", "Feed", "其他"], "default": "基础培养基"},
            {"key": "version_no", "label": "初始版本号", "type": "int", "default": 1},
            {"key": "change_note", "label": "版本说明", "type": "multiline", "lines": 3},
        ], width=580)
        values = dialog.show()
        if not values:
            return
        values.update({"status": "草稿", "created_by": self.ctx.operator, "parent_formula_id": None})
        try:
            fid = self.ctx.repos.formulas.create(values, [])
        except Exception as exc:
            error(self, f"创建失败：{exc}")
            return
        self.ctx.audit("新增配方", "formula", fid, after=values)
        self.current_id = fid
        self.refresh()
        self.set_status(f"已创建配方 {values['formula_code']} V{values['version_no']}")

    def edit_header(self):
        if not self.current:
            info(self, "请先选择配方")
            return
        row = self.current
        dialog = FormDialog(self, "编辑配方基本信息", [
            {"key": "formula_name", "label": "配方名称", "required": True, "default": row["formula_name"]},
            {"key": "formula_type", "label": "配方类型", "type": "combo",
             "values": ["基础培养基", "浓缩培养基", "Feed", "其他"], "default": row.get("formula_type") or "基础培养基"},
            {"key": "status", "label": "状态", "type": "combo", "values": ["草稿", "已发布", "停用"], "default": row["status"]},
            {"key": "effective_date", "label": "生效日期", "default": row.get("effective_date") or ""},
            {"key": "change_note", "label": "版本变更说明", "type": "multiline", "lines": 3, "default": row.get("change_note") or ""},
        ], width=580)
        values = dialog.show()
        if not values:
            return
        self.ctx.repos.formulas.update_header(row["formula_id"], values)
        self.ctx.audit("修改配方", "formula", row["formula_id"], before=row, after=values)
        self.refresh()
        self.select_formula(self.ctx.repos.formulas.get(row["formula_id"]))
        self.set_status("配方基本信息已更新")

    def new_version(self):
        if not self.current:
            info(self, "请先选择原配方")
            return
        note = FormDialog(self, "创建新版本", [
            {"key": "change_note", "label": "本版本变更说明", "type": "multiline", "lines": 4, "required": True},
        ], width=520, intro="新版本会复制当前版本的全部组分明细，状态为草稿；原版本保持不变。").show()
        if not note:
            return
        try:
            new_id = self.ctx.repos.formulas.new_version(self.current_id, note["change_note"], self.ctx.operator)
        except Exception as exc:
            error(self, f"创建新版本失败：{exc}")
            return
        self.ctx.audit("创建配方新版本", "formula", new_id, after={"source": self.current_id})
        self.current_id = new_id
        self.refresh()
        self.set_status("已创建新的配方版本")

    def publish(self):
        if not self.current:
            info(self, "请先选择配方")
            return
        status = self.current["status"]
        if status == "草稿":
            if not self.details:
                error(self, "配方没有组分明细，不能发布")
                return
            if not confirm(self, "发布配方", f"发布 {self.current['formula_code']} V{self.current['version_no']}？发布后应通过新版本修改。"):
                return
            self.ctx.repos.formulas.update_header(self.current_id, {"status": "已发布", "effective_date": now_iso()[:10]})
            action = "发布配方"
        elif status == "已发布":
            if not confirm(self, "停用配方", "停用后新批次不应再引用该版本，历史记录不受影响。继续？"):
                return
            self.ctx.repos.formulas.update_header(self.current_id, {"status": "停用"})
            action = "停用配方"
        else:
            if not confirm(self, "启用配方", "将该版本状态恢复为“已发布”？"):
                return
            self.ctx.repos.formulas.update_header(self.current_id, {"status": "已发布"})
            action = "启用配方"
        self.ctx.audit(action, "formula", self.current_id)
        self.refresh()
        self.set_status(action + "完成")

    def delete_draft(self):
        if not self.current:
            return
        if self.current["status"] != "草稿":
            error(self, "只能删除草稿版本")
            return
        if not confirm(self, "删除草稿", f"删除 {self.current['formula_code']} V{self.current['version_no']}？此操作不可恢复。"):
            return
        self.ctx.repos.formulas.delete_draft(self.current_id)
        self.ctx.audit("删除配方草稿", "formula", self.current_id)
        self._clear_detail()
        self.refresh()
        self.set_status("草稿已删除")

    # ---------- 组分明细 ----------
    def _detail_dialog(self, row: dict | None = None):
        components = self.ctx.repos.components.search(active_only=True)
        if not components:
            error(self, "组分库为空，请先到“基础数据 → 培养基组分”新建组分")
            return
        choices = [{"label": f"{c['component_code']}  {c['component_name']}", "value": c["component_id"]} for c in components]
        current_component = next((c for c in components if row and c["component_id"] == row.get("component_id")), None)
        fields = [
            {"key": "component_id", "label": "组分", "type": "combo", "choices": choices, "required": True,
             "default": f"{current_component['component_code']}  {current_component['component_name']}" if current_component else ""},
            {"key": "target_concentration", "label": "目标浓度", "type": "number", "required": True,
             "default": row.get("target_concentration") if row else ""},
            {"key": "concentration_unit", "label": "浓度单位", "type": "combo",
             "values": ["g/L", "mg/L", "mg/mL", "ug/mL", "mM", "uM", "mol/L"],
             "default": row.get("concentration_unit") if row else "g/L"},
            {"key": "source_type", "label": "来源方式", "type": "combo", "values": ["直接称量", "母液"],
             "default": row.get("source_type") if row else "直接称量"},
            {"key": "purity_fraction", "label": "纯度 (0~1)", "type": "number",
             "default": row.get("purity_fraction") if row else 1.0},
            {"key": "molecular_weight", "label": "分子量 (g/mol)", "type": "number",
             "default": row.get("molecular_weight") if row else (current_component.get("molecular_weight") if current_component else "")},
            {"key": "stock_concentration", "label": "母液浓度", "type": "number",
             "default": row.get("stock_concentration") if row else ""},
            {"key": "stock_unit", "label": "母液单位", "type": "combo",
             "values": ["g/L", "mg/mL", "mM", "uM", "mg/L"],
             "default": row.get("stock_unit") if row else "g/L"},
            {"key": "notes", "label": "备注", "type": "multiline", "lines": 2, "default": row.get("notes") if row else ""},
        ]
        dialog = FormDialog(self, "编辑组分" if row else "添加组分", fields, width=600,
                            intro="直接称量按目标浓度计算质量；母液按浓度折算所需体积。摩尔浓度必须填写分子量。")
        values = dialog.show()
        if not values:
            return None
        component = next((c for c in components if c["component_id"] == values["component_id"]), None)
        if values["source_type"] == "母液" and not values.get("stock_concentration"):
            error(self, "选择母液时必须填写母液浓度")
            return None
        if not values.get("molecular_weight") and component and component.get("molecular_weight"):
            values["molecular_weight"] = component["molecular_weight"]
        values["component_code"] = component["component_code"] if component else ""
        values["component_name"] = component["component_name"] if component else ""
        if row:
            values["detail_id"] = row.get("detail_id")
        return values

    def add_detail(self):
        if not self.current:
            info(self, "请先选择配方")
            return
        if self.current["status"] != "草稿":
            error(self, "只有草稿状态可以修改组分明细；请先创建新版本。")
            return
        values = self._detail_dialog()
        if not values:
            return
        self.details.append(values)
        self._save_details()
        self.set_status("已添加组分")

    def edit_detail(self):
        if not self.current or self.current["status"] != "草稿":
            error(self, "只有草稿状态可以修改组分明细")
            return
        row = self.detail_table.selected_row()
        if not row:
            info(self, "请先选择一行组分明细")
            return
        target = next((d for d in self.details if d.get("detail_id") == row.get("detail_id") or
                       (d.get("component_code") == row.get("component_code"))), None)
        if not target:
            return
        values = self._detail_dialog(target)
        if not values:
            return
        idx = self.details.index(target)
        values["detail_id"] = target.get("detail_id")
        self.details[idx] = values
        self._save_details()
        self.set_status("已更新组分")

    def delete_detail(self):
        if not self.current or self.current["status"] != "草稿":
            error(self, "只有草稿状态可以删除组分明细")
            return
        row = self.detail_table.selected_row()
        if not row:
            return
        if not confirm(self, "删除组分", f"从配方中删除“{row.get('component_name')}”？"):
            return
        self.details = [d for d in self.details if not (
            d.get("detail_id") == row.get("detail_id") or d.get("component_code") == row.get("component_code"))]
        self._save_details()
        self.set_status("已删除组分")

    def _save_details(self):
        if not self.current_id:
            return
        payload = []
        for d in self.details:
            payload.append({
                "component_id": d["component_id"],
                "target_concentration": d.get("target_concentration"),
                "concentration_unit": d.get("concentration_unit"),
                "molecular_weight": d.get("molecular_weight"),
                "purity_fraction": d.get("purity_fraction") or 1.0,
                "source_type": d.get("source_type") or "直接称量",
                "stock_concentration": d.get("stock_concentration"),
                "stock_unit": d.get("stock_unit"),
                "notes": d.get("notes", ""),
            })
        self.ctx.repos.formulas.replace_details(self.current_id, payload)
        self.ctx.audit("保存配方组分明细", "formula", self.current_id, after={"count": len(payload)})
        self._reload_details()
        self.calculate()

    # ---------- 计算 ----------
    def calculate(self):
        if not self.details:
            self.message.configure(text="尚未添加组分明细。", fg=COLORS["muted"])
            self.total_label.configure(text="")
            return
        try:
            volume = float(self.volume_var.get())
        except ValueError:
            error(self, "目标体积必须是有效数字")
            return
        result = calculate_formula(self.details, volume, self.volume_unit.get())
        if result["errors"]:
            self.message.configure(text="错误：" + "；".join(result["errors"][:4]), fg=COLORS["danger"])
        elif result["warnings"]:
            self.message.configure(text="警告：" + "；".join(result["warnings"][:4]), fg=COLORS["warning"])
        else:
            self.message.configure(text="计算完成。保存配制记录时将以当前配方版本和体积生成快照。", fg=COLORS["success"])
        lines = result["lines"]
        for line in lines:
            line["component_code"] = line.get("component_code") or ""
            line["component_name"] = line.get("component_name") or ""
        merged = []
        for lp, original in zip(lines, self.details):
            lp["component_code"] = original.get("component_code", "")
            lp["component_name"] = original.get("component_name", "")
            merged.append(lp)
        self._render_details(merged)
        self.total_label.configure(
            text=f"理论总量 {fmt_num(result['total_theoretical_g'])} g · 纯度修正 {fmt_num(result['total_corrected_g'])} g · "
                 f"母液 {fmt_num(result['total_stock_ml'])} mL · 定容补足 {fmt_num(result['solvent_ml'])} mL")
