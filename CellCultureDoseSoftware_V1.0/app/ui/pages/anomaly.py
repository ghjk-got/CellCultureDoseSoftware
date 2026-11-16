# -*- coding: utf-8 -*-
"""异常审核：导入、核算与人工修正异常的闭环处理。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..base import Page
from ..theme import COLORS, FONT, FONT_H3, FONT_SMALL
from ..widgets import Card, DataTable, FormDialog, error, human_dt, info


class AnomalyPage(Page):
    key = "anomaly"
    title = "异常审核"
    subtitle = "导入、计算与人工修正异常的闭环处理"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()
        self.refresh()

    def _build(self):
        top = tk.Frame(self, bg=COLORS["bg"])
        top.pack(fill="x")
        tk.Label(top, text="范围", bg=COLORS["bg"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="left")
        self.scope_var = tk.StringVar(value="当前批次")
        scope = ttk.Combobox(top, textvariable=self.scope_var, values=["当前批次", "全部批次"], state="readonly", width=12)
        scope.pack(side="left", padx=6)
        scope.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        tk.Label(top, text="状态", bg=COLORS["bg"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="left", padx=(12, 0))
        self.status_var = tk.StringVar(value="全部")
        status = ttk.Combobox(top, textvariable=self.status_var, values=["全部", "未解决", "已解决"], state="readonly", width=10)
        status.pack(side="left", padx=6)
        status.bind("<<ComboboxSelected>>", lambda e: self.refresh())
        ttk.Button(top, text="刷新", style="Ghost.TButton", command=self.refresh).pack(side="left", padx=6)
        ttk.Button(top, text="解决选中异常", style="Primary.TButton", command=self.resolve).pack(side="right")
        ttk.Button(top, text="前往剂量核算", style="Secondary.TButton",
                   command=lambda: self.app.go("dose_calc")).pack(side="right", padx=6)

        cards = tk.Frame(self, bg=COLORS["bg"])
        cards.pack(fill="x", pady=(10, 0))
        for i in range(3):
            cards.grid_columnconfigure(i, weight=1, uniform="a")
        self.metrics = {}
        for idx, (key, title, color) in enumerate((("open", "未解决", COLORS["danger"]),
                                                   ("closed", "已解决", COLORS["success"]),
                                                   ("total", "全部异常", COLORS["accent"]))):
            card = Card(cards, padding=14)
            card.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 8, 0))
            tk.Label(card.body, text=title, bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(anchor="w")
            value = tk.Label(card.body, text="0", bg=COLORS["white"], fg=color, font=(FONT[0], 22, "bold"))
            value.pack(anchor="w")
            self.metrics[key] = value

        table_card = Card(self, padding=12)
        table_card.pack(fill="both", expand=True, pady=(10, 0))
        self.table = DataTable(table_card.body, [
            ("batch_code", "批次", 115), ("anomaly_type", "类型", 115), ("severity", "级别", 55),
            ("description", "描述", 430), ("status", "状态", 65), ("created_at", "创建时间", 130),
        ], height=8, id_key="anomaly_id", on_select=self.select_anomaly)
        self.table.pack(fill="both", expand=True)
        self.table.tree.bind("<Double-1>", lambda e: self.resolve())

        detail_card = Card(self, padding=12)
        detail_card.pack(fill="x", pady=(10, 0))
        tk.Label(detail_card.body, text="异常详情与处理说明", bg=COLORS["white"], fg=COLORS["text"],
                 font=FONT_H3).pack(anchor="w")
        self.detail_label = tk.Label(detail_card.body, text="选择一条异常记录查看详情。", bg=COLORS["white"],
                                     fg=COLORS["muted"], font=FONT_SMALL, justify="left", anchor="w",
                                     wraplength=1200)
        self.detail_label.pack(fill="x", pady=(4, 0))

    def on_show(self):
        self.refresh()

    def on_batch_changed(self):
        if self.winfo_exists():
            self.refresh()

    def refresh(self):
        batch_id = ""
        if self.scope_var.get() == "当前批次":
            batch_id = self.app.current_batch_id or ""
        status = "" if self.status_var.get() == "全部" else self.status_var.get()
        rows = self.ctx.repos.anomalies.list_for_batch(batch_id, status)
        self.table.set_rows(rows, "anomaly_id")
        all_rows = self.ctx.repos.anomalies.list_for_batch(batch_id, "")
        self.metrics["open"].configure(text=str(sum(1 for r in all_rows if r["status"] == "未解决")))
        self.metrics["closed"].configure(text=str(sum(1 for r in all_rows if r["status"] == "已解决")))
        self.metrics["total"].configure(text=str(len(all_rows)))
        if rows:
            self.select_anomaly(rows[0])
        else:
            self.detail_label.configure(text="没有符合条件的异常记录。")

    def select_anomaly(self, row: dict):
        lines = [
            f"异常编号：{row.get('anomaly_id')}    类型：{row.get('anomaly_type')}    级别：{row.get('severity')}",
            f"批次：{row.get('batch_code') or '—'}    状态：{row.get('status')}    创建：{human_dt(row.get('created_at'))}",
            f"描述：{row.get('description') or '—'}",
        ]
        if row.get("resolution_note"):
            lines.append(f"处理说明：{row['resolution_note']}")
        if row.get("resolved_at"):
            lines.append(f"解决时间：{human_dt(row.get('resolved_at'))}")
        self.detail_label.configure(text="\n".join(lines))

    def resolve(self):
        row = self.table.selected_row()
        if not row:
            info(self, "请先选择异常记录")
            return
        if row.get("status") == "已解决":
            info(self, "该异常已解决")
            return
        dialog = FormDialog(self, "解决异常", [
            {"key": "note", "label": "处理说明", "type": "multiline", "lines": 5, "required": True},
        ], width=560, intro="请记录核查结论、修正措施或确认依据；原始导入记录不会被覆盖。")
        values = dialog.show()
        if not values:
            return
        try:
            self.ctx.repos.anomalies.resolve(row["anomaly_id"], values["note"])
        except Exception as exc:
            error(self, f"处理失败：{exc}")
            return
        self.ctx.audit("解决异常", "dose_anomaly", row["anomaly_id"], after={"note": values["note"]})
        self.refresh()
        self.set_status("异常已标记为已解决")
