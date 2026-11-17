# -*- coding: utf-8 -*-
"""日常工作入口：聚合补料、成品培养基和低频资料维护。"""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import ttk

from ...db import new_id, now_iso
from ...services.units import volume_to_l
from ..base import Page
from ..theme import COLORS, FONT_H3
from ..widgets import Card, DataTable, FormDialog, error, info


class FeedPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = Card(self, padding=16)
        top.pack(fill="x")
        tk.Label(top.body, text="补料记录", bg=COLORS['white'], font=FONT_H3).pack(anchor="w")
        tk.Label(top.body, text="先记录开始读数；补料结束后载入同一条记录补填。", bg=COLORS['white']).pack(anchor="w", pady=6)
        actions = tk.Frame(top.body, bg=COLORS['white'])
        actions.pack(fill="x")
        ttk.Button(actions, text="开始 / 结束补料", command=self.open_records).pack(side="left")
        ttk.Button(actions, text="补料计划", command=lambda: app.go('plan')).pack(side="left", padx=8)
        ttk.Button(actions, text="文件数据核算", command=lambda: app.go('dose_calc')).pack(side="left")
        self.table = DataTable(self, [("pump_code", "泵", 100), ("liquid_name", "补料液", 110),
            ("start_time", "开始", 150), ("end_time", "结束", 150), ("estimate_ml", "设备估算(mL)", 120),
            ("measured_ml", "独立实测(mL)", 120), ("lifecycle_status", "记录状态", 80), ("quality_status", "核查状态", 80),
            ("issues", "原因", 220)], height=12, id_key="record_id")
        self.table.pack(fill="both", expand=True, pady=12)

    def open_records(self):
        if self.app.require_batch():
            from .manual_feed import ManualFeedWindow
            window = ManualFeedWindow(self)
            window.bind("<Destroy>", lambda e: self.refresh() if e.widget is window else None)

    def on_show(self): self.refresh()
    def on_batch_changed(self): self.refresh()
    def refresh(self):
        bid = self.app.current_batch_id
        self.table.set_rows(self.ctx.manual_feed.list_for_batch(bid) if bid else [], "record_id")


class MediumPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        head = Card(self, padding=16)
        head.pack(fill="x")
        tk.Label(head.body, text="选择本次培养基使用方式", bg=COLORS['white'], font=FONT_H3).pack(anchor="w")
        bar = tk.Frame(head.body, bg=COLORS['white'])
        bar.pack(fill="x", pady=10)
        ttk.Button(bar, text="使用成品", command=self.add_commercial).pack(side="left")
        ttk.Button(bar, text="按配方配制", command=lambda: app.go('preparation')).pack(side="left", padx=8)
        ttk.Button(bar, text="配方资料", command=lambda: app.go('formula')).pack(side="left")
        self.table = DataTable(self, [("used_at", "使用时间", 150), ("medium_name", "成品名称", 160),
            ("product_lot", "产品批号", 130), ("volume", "体积", 80), ("volume_unit", "单位", 60),
            ("operator", "操作人", 90), ("notes", "备注", 200)], height=10, id_key="record_id")
        self.table.pack(fill="both", expand=True, pady=12)

    def add_commercial(self):
        bid = self.app.require_batch()
        if not bid: return
        values = FormDialog(self, "成品培养基使用记录", [
            {"key": "medium_name", "label": "成品名称", "required": True},
            {"key": "product_lot", "label": "产品批号"},
            {"key": "volume", "label": "使用体积", "type": "number", "required": True},
            {"key": "volume_unit", "label": "体积单位", "type": "combo", "values": ["mL", "L"], "default": "mL", "required": True},
            {"key": "used_at", "label": "使用时间", "type": "date", "default": now_iso(), "required": True},
            {"key": "operator", "label": "操作人", "default": self.ctx.operator, "required": True},
            {"key": "notes", "label": "备注"},
        ], width=580).show()
        if not values: return
        try:
            volume = float(values['volume'])
            if not math.isfinite(volume) or volume <= 0: raise ValueError("使用体积必须大于零")
            volume_to_l(volume, values['volume_unit'])
            from ...services.dose_calc import parse_ts
            if not parse_ts(values['used_at']): raise ValueError("使用时间无效")
            rid = new_id('MED')
            self.ctx.db.execute("INSERT INTO commercial_medium_record VALUES(?,?,?,?,?,?,?,?,?)", (rid, bid, values['medium_name'], values.get('product_lot'), volume, values['volume_unit'], values['used_at'], values['operator'], values.get('notes')))
            self.ctx.audit("登记成品培养基", "commercial_medium_record", rid, after=values)
            self.refresh()
        except ValueError as exc: error(self, str(exc))

    def on_show(self): self.refresh()
    def on_batch_changed(self): self.refresh()
    def refresh(self):
        bid = self.app.current_batch_id
        rows = [dict(row) for row in self.ctx.db.q("SELECT * FROM commercial_medium_record WHERE batch_id=? ORDER BY used_at DESC", (bid,))] if bid else []
        self.table.set_rows(rows, "record_id")


class ResourcesPage(Page):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        card = Card(self, padding=20)
        card.pack(fill="both", expand=True)
        tk.Label(card.body, text="设备、实验资料与系统维护", bg=COLORS['white'], font=FONT_H3).pack(anchor="w", pady=(0, 12))
        if self.ctx.db.get_setting("initial_setup") == "pending":
            from .setup_wizard import SetupWizard
            ttk.Button(card.body, text="继续首次设备配置", command=lambda: SetupWizard(app)).pack(fill="x", pady=5)
        for title, key in [("反应器、泵、补料液与组分", "master"), ("配方与版本", "formula"),
                           ("泵校准", "calibration"), ("剂量文件导入", "dose_import"),
                           ("备份、单位、日志与系统设置", "settings"), ("报告与历史", "reports")]:
            ttk.Button(card.body, text=title, command=lambda k=key: app.go(k)).pack(fill="x", pady=5)
