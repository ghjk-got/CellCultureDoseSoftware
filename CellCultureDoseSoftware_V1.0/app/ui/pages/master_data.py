# -*- coding: utf-8 -*-
"""基础数据管理：组分、工艺液、泵与反应器。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ...db import now_iso
from ..base import Page
from ..theme import COLORS, FONT, FONT_H3
from ..widgets import DataTable, FormDialog, confirm, error, info


class MasterTab(tk.Frame):
    def __init__(self, parent, page: "MasterDataPage", kind: str):
        super().__init__(parent, bg=COLORS["white"])
        self.page = page
        self.ctx = page.ctx
        self.kind = kind
        self.repo, self.columns, self.fields, self.title, self.id_key, self.code_key = self._spec(kind)
        self.search_var = tk.StringVar()
        self._build()

    def _spec(self, kind):
        status_choices = ["启用", "停用"]
        if kind == "component":
            return (
                self.ctx.repos.components,
                [("component_code", "组分代码", 110), ("component_name", "组分名称", 160),
                 ("category", "类别", 100), ("default_unit", "默认单位", 80),
                 ("molecular_weight", "分子量", 90), ("purity_default", "默认纯度", 90),
                 ("stock_concentration", "母液浓度", 100), ("status", "状态", 70)],
                [
                    {"key": "component_code", "label": "组分代码", "required": True},
                    {"key": "component_name", "label": "组分名称", "required": True},
                    {"key": "category", "label": "类别", "type": "combo", "values": ["碳源", "氨基酸", "维生素", "盐类", "缓冲剂", "生长因子", "其他"], "default": "其他"},
                    {"key": "default_unit", "label": "默认计量单位", "type": "combo", "values": ["g", "mg", "ug", "kg"], "default": "g"},
                    {"key": "molecular_weight", "label": "分子量 (g/mol)", "type": "number", "help": "摩尔浓度换算时必填"},
                    {"key": "purity_default", "label": "默认纯度 (0~1)", "type": "number", "default": 1.0},
                    {"key": "stock_concentration", "label": "母液浓度", "type": "number"},
                    {"key": "stock_unit", "label": "母液浓度单位", "type": "combo", "values": ["g/L", "mg/mL", "mM", "uM", "mg/L"], "default": "g/L"},
                    {"key": "status", "label": "状态", "type": "combo", "values": status_choices, "default": "启用"},
                    {"key": "notes", "label": "备注", "type": "multiline", "lines": 3},
                ], "组分档案", "component_id", "component_code")
        if kind == "liquid":
            return (
                self.ctx.repos.liquids,
                [("liquid_code", "液体代码", 110), ("liquid_name", "液体名称", 160),
                 ("liquid_type", "类型", 90), ("concentration_value", "浓度", 90),
                 ("concentration_unit", "单位", 90), ("status", "状态", 70)],
                [
                    {"key": "liquid_code", "label": "液体代码", "required": True},
                    {"key": "liquid_name", "label": "液体名称", "required": True},
                    {"key": "liquid_type", "label": "类型", "type": "combo", "values": ["Feed", "碱液", "消泡剂", "其他"], "default": "Feed"},
                    {"key": "concentration_value", "label": "浓度", "type": "number"},
                    {"key": "concentration_unit", "label": "浓度单位", "type": "combo", "values": ["g/L", "mg/mL", "%", "mM"], "default": "g/L"},
                    {"key": "status", "label": "状态", "type": "combo", "values": status_choices, "default": "启用"},
                    {"key": "notes", "label": "备注", "type": "multiline", "lines": 3},
                ], "工艺液档案", "liquid_id", "liquid_code")
        if kind == "pump":
            return (
                self.ctx.repos.pumps,
                [("pump_code", "泵编号", 100), ("pump_name", "泵名称", 150),
                 ("pump_type", "泵类型", 100), ("flow_unit", "默认流速单位", 110),
                 ("status", "状态", 70)],
                [
                    {"key": "pump_code", "label": "泵/通道编号", "required": True, "help": "应与 Dose Monitor 导出中的泵编号一致"},
                    {"key": "pump_name", "label": "泵名称", "required": True},
                    {"key": "pump_type", "label": "泵类型", "type": "combo", "values": ["蠕动泵", "注射泵", "其他"], "default": "蠕动泵"},
                    {"key": "flow_unit", "label": "默认流速单位", "type": "combo", "values": ["mL/h", "mL/min", "L/h", "uL/min"], "default": "mL/h"},
                    {"key": "status", "label": "状态", "type": "combo", "values": status_choices, "default": "启用"},
                    {"key": "notes", "label": "备注", "type": "multiline", "lines": 3},
                ], "泵档案", "pump_id", "pump_code")
        return (
            self.ctx.repos.reactors,
            [("reactor_code", "反应器编号", 110), ("reactor_name", "名称", 170),
             ("working_volume_ml", "工作体积 (mL)", 110), ("status", "状态", 70)],
            [
                {"key": "reactor_code", "label": "反应器编号", "required": True},
                {"key": "reactor_name", "label": "反应器名称", "required": True},
                {"key": "working_volume_ml", "label": "工作体积 (mL)", "type": "number"},
                {"key": "status", "label": "状态", "type": "combo", "values": status_choices, "default": "启用"},
                {"key": "notes", "label": "备注", "type": "multiline", "lines": 3},
            ], "反应器档案", "reactor_id", "reactor_code")

    def _build(self):
        bar = tk.Frame(self, bg=COLORS["white"])
        bar.pack(fill="x", pady=(12, 8))
        tk.Label(bar, text=self.title, bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        ttk.Button(bar, text="新增", style="Primary.TButton", command=self.add).pack(side="right", padx=(6, 0))
        ttk.Button(bar, text="编辑", style="Secondary.TButton", command=self.edit).pack(side="right", padx=(6, 0))
        ttk.Button(bar, text="启用/停用", style="Secondary.TButton", command=self.toggle).pack(side="right", padx=(6, 0))
        ttk.Entry(bar, textvariable=self.search_var, width=22).pack(side="right", padx=(6, 10))
        self.search_var.trace_add("write", lambda *a: self.refresh())
        tk.Label(bar, text="搜索", bg=COLORS["white"], fg=COLORS["muted"], font=FONT).pack(side="right")
        self.table = DataTable(self, self.columns, height=16, id_key=self.id_key)
        self.table.pack(fill="both", expand=True)
        self.table.tree.bind("<Double-1>", lambda e: self.edit())

    def refresh(self):
        keyword = self.search_var.get().strip().lower()
        try:
            rows = self.repo.search(keyword) if hasattr(self.repo, "search") else self.repo.list()
        except Exception:
            rows = self.repo.list()
        if keyword and hasattr(self.repo, "search") is False:
            rows = [r for r in rows if any(keyword in str(v).lower() for v in r.values())]
        self.table.set_rows(rows, self.id_key)

    def _exists(self, code: str, exclude: str = "") -> bool:
        if self.kind == "component":
            return self.repo.code_exists(code, exclude)
        if self.kind == "liquid":
            return self.repo.code_exists(code, exclude)
        if self.kind == "pump":
            return self.repo.code_exists(code, exclude)
        return self.ctx.db.q1("SELECT 1 FROM reactor_info WHERE reactor_code=? AND reactor_id<>?", (code, exclude)) is not None

    def add(self):
        dialog = FormDialog(self, f"新增{self.title}", self.fields, width=600,
                            intro="基础数据会被配方、批次、补料计划等模块引用；请使用稳定、可追溯的编号。")
        values = dialog.show()
        if not values:
            return
        code = values.get(self.code_key)
        if self._exists(code):
            error(self, f"编号 {code} 已存在")
            return
        values["created_at"] = now_iso()
        try:
            new_id = self.repo.insert(values)
            self.ctx.audit("新增", self.kind, new_id, after=values)
            self.refresh()
            self.page.set_status(f"已新增 {self.title}：{code}")
        except Exception as exc:
            error(self, f"保存失败：{exc}")

    def edit(self):
        row = self.table.selected_row()
        if not row:
            info(self, "请先选择一条记录")
            return
        fields = []
        for f in self.fields:
            copy = dict(f)
            copy["default"] = row.get(f["key"]) if row.get(f["key"]) is not None else f.get("default", "")
            fields.append(copy)
        dialog = FormDialog(self, f"编辑{self.title}", fields, width=600)
        values = dialog.show()
        if not values:
            return
        code = values.get(self.code_key)
        if self._exists(code, row[self.id_key]):
            error(self, f"编号 {code} 已被其他记录使用")
            return
        try:
            self.repo.update(row[self.id_key], values)
            self.ctx.audit("修改", self.kind, row[self.id_key], before=row, after=values)
            self.refresh()
            self.table.select_by_id(row[self.id_key])
            self.page.set_status(f"已更新 {self.title}：{code}")
        except Exception as exc:
            error(self, f"更新失败：{exc}")

    def toggle(self):
        row = self.table.selected_row()
        if not row:
            return
        new_status = "停用" if row.get("status") == "启用" else "启用"
        if not confirm(self, "确认变更", f"将 {row.get(self.code_key)} 状态改为“{new_status}”？"):
            return
        self.repo.update(row[self.id_key], {"status": new_status})
        self.ctx.audit("变更状态", self.kind, row[self.id_key], before={"status": row.get("status")},
                       after={"status": new_status})
        self.refresh()
        self.page.set_status(f"{row.get(self.code_key)} 已{new_status}")


class MasterDataPage(Page):
    key = "master"
    title = "基础数据"
    subtitle = "组分、工艺液、泵与反应器档案"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        self.tab_objects = {}
        for kind, label in (("component", "培养基组分"), ("liquid", "工艺液"), ("pump", "泵"), ("reactor", "反应器")):
            frame = tk.Frame(self.tabs, bg=COLORS["white"])
            self.tabs.add(frame, text=label)
            tab = MasterTab(frame, self, kind)
            tab.pack(fill="both", expand=True, padx=10, pady=6)
            self.tab_objects[kind] = tab

    def on_show(self):
        for tab in self.tab_objects.values():
            tab.refresh()
