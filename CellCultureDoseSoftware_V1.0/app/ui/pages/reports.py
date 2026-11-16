# -*- coding: utf-8 -*-
"""报告中心：批次 Excel / PDF 报告与历史版本。"""
from __future__ import annotations

from pathlib import Path

import tkinter as tk
from tkinter import ttk

from ..base import Page
from ..theme import COLORS, FONT, FONT_H3, FONT_SMALL
from ..widgets import Card, DataTable, confirm, error, human_dt, info, open_path


class ReportsPage(Page):
    key = "reports"
    title = "报告中心"
    subtitle = "批次 Excel / PDF 报告与历史版本"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()
        self.refresh()

    def _build(self):
        top = tk.Frame(self, bg=COLORS["bg"])
        top.pack(fill="x")
        ttk.Button(top, text="生成 Excel 报告", style="Primary.TButton", command=self.generate_excel).pack(side="left")
        ttk.Button(top, text="生成 PDF 报告", style="Secondary.TButton", command=self.generate_pdf).pack(side="left", padx=6)
        ttk.Button(top, text="打开报告文件夹", style="Ghost.TButton", command=self.open_folder).pack(side="left", padx=6)
        self.batch_hint = tk.Label(top, text="", bg=COLORS["bg"], fg=COLORS["muted"], font=FONT_SMALL)
        self.batch_hint.pack(side="right")

        cards = tk.Frame(self, bg=COLORS["bg"])
        cards.pack(fill="x", pady=(10, 0))
        for i in range(4):
            cards.grid_columnconfigure(i, weight=1, uniform="r")
        self.metrics = {}
        for idx, (key, title, color) in enumerate((("reports", "报告总数", COLORS["accent"]),
                                                   ("excel", "Excel", COLORS["success"]),
                                                   ("pdf", "PDF", COLORS["purple"]),
                                                   ("latest", "最近生成", COLORS["warning"]))):
            card = Card(cards, padding=14)
            card.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 8, 0))
            tk.Label(card.body, text=title, bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(anchor="w")
            value = tk.Label(card.body, text="—", bg=COLORS["white"], fg=color,
                             font=(FONT[0], 20, "bold") if key != "latest" else (FONT[0], 10, "bold"))
            value.pack(anchor="w", pady=(4, 0))
            self.metrics[key] = value

        table_card = Card(self, padding=12)
        table_card.pack(fill="both", expand=True, pady=(10, 0))
        h = tk.Frame(table_card.body, bg=COLORS["white"])
        h.pack(fill="x")
        tk.Label(h, text="报告历史", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        ttk.Button(h, text="打开选中报告", style="Secondary.TButton", command=self.open_selected).pack(side="right")
        ttk.Button(h, text="打开所在文件夹", style="Ghost.TButton", command=self.open_selected_folder).pack(side="right", padx=6)
        self.table = DataTable(table_card.body, [
            ("report_type", "类型", 60), ("version_no", "版本", 50), ("filename", "文件", 340),
            ("generated_at", "生成时间", 130), ("generated_by", "生成人", 80),
        ], height=8, id_key="report_id")
        self.table.pack(fill="both", expand=True, pady=(8, 0))
        self.table.tree.bind("<Double-1>", lambda e: self.open_selected())

        note_card = Card(self, padding=12)
        note_card.pack(fill="x", pady=(10, 0))
        tk.Label(note_card.body, text="报告说明", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w")
        tk.Label(note_card.body, text="报告读取已保存的业务数据与核算版本，不直接修改原始数据。"
                                      "标记为“估算”“待审核”或“无效”的结果会在报告中明确显示；报告版本号按批次和类型递增。",
                 bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL, justify="left",
                 anchor="w", wraplength=1200).pack(fill="x", pady=(4, 0))

    def on_show(self):
        self.refresh()

    def on_batch_changed(self):
        if self.winfo_exists():
            self.refresh()

    def refresh(self):
        batch = self.app.current_batch
        self.batch_hint.configure(text=f"当前批次：{batch['batch_code'] if batch else '未选择'}")
        if not batch:
            self.table.clear()
            for key in self.metrics:
                self.metrics[key].configure(text="—")
            return
        rows = self.ctx.repos.reports.list_for_batch(batch["batch_id"])
        for row in rows:
            row["filename"] = Path(row.get("file_path") or "").name
        self.table.set_rows(rows, "report_id")
        self.metrics["reports"].configure(text=str(len(rows)))
        self.metrics["excel"].configure(text=str(sum(1 for r in rows if r["report_type"] == "Excel")))
        self.metrics["pdf"].configure(text=str(sum(1 for r in rows if r["report_type"] == "PDF")))
        self.metrics["latest"].configure(text=human_dt(rows[0]["generated_at"]) if rows else "—")

    def generate_excel(self):
        batch = self.app.current_batch
        if not batch:
            info(self, "请先选择批次")
            return
        self.set_status("正在生成 Excel 报告…")
        self.update_idletasks()
        try:
            path = self.ctx.reports.generate_excel(batch["batch_id"], self.ctx.operator)
        except Exception as exc:
            error(self, f"生成失败：{exc}")
            return
        self.refresh()
        self.set_status(f"Excel 报告已生成：{path.name}")
        if confirm(self, "生成完成", f"Excel 报告已保存：\n{path}\n\n是否立即打开？"):
            open_path(path)

    def generate_pdf(self):
        batch = self.app.current_batch
        if not batch:
            info(self, "请先选择批次")
            return
        self.set_status("正在生成 PDF 报告…")
        self.update_idletasks()
        try:
            path = self.ctx.reports.generate_pdf(batch["batch_id"], self.ctx.operator)
        except Exception as exc:
            error(self, f"生成失败：{exc}")
            return
        self.refresh()
        self.set_status(f"PDF 报告已生成：{path.name}")
        if confirm(self, "生成完成", f"PDF 报告已保存：\n{path}\n\n是否立即打开？"):
            open_path(path)

    def open_selected(self):
        row = self.table.selected_row()
        if not row:
            info(self, "请先选择报告")
            return
        path = Path(row["file_path"])
        if not path.exists():
            error(self, f"报告文件不存在：{path}")
            return
        open_path(path)

    def open_selected_folder(self):
        row = self.table.selected_row()
        if row:
            path = Path(row["file_path"]).parent
            if path.exists():
                open_path(path)
                return
        self.open_folder()

    def open_folder(self):
        batch = self.app.current_batch
        if not batch:
            info(self, "请先选择批次")
            return
        folder = self.ctx.settings.path("reports", batch["batch_code"])
        folder.mkdir(parents=True, exist_ok=True)
        open_path(folder)
