# -*- coding: utf-8 -*-
"""首页与工作台。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..base import Page
from ..theme import COLORS, FONT, FONT_BOLD, FONT_H2, FONT_H3, FONT_SMALL
from ..widgets import Card, DataTable, human_dt, status_kind


class DashboardPage(Page):
    key = "dashboard"
    title = "首页"
    subtitle = "批次概览、待处理事项与快速入口"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()

    def _build(self) -> None:
        banner = tk.Frame(self, bg="#0F172A", height=88)
        banner.pack(fill="x")
        banner.pack_propagate(False)
        info = tk.Frame(banner, bg="#0F172A")
        info.pack(side="left", fill="y", padx=24, pady=16)
        tk.Label(info, text="细胞培养基配制与补料剂量核算", bg="#0F172A", fg="white",
                 font=(FONT[0], 16, "bold")).pack(anchor="w")
        tk.Label(info, text="配方计算 · 补料计划 · 泵校准 · Dose Monitor 导入 · 实际剂量核算 · 批次追溯",
                 bg="#0F172A", fg="#94A3B8", font=FONT_SMALL).pack(anchor="w", pady=(4, 0))
        actions = tk.Frame(banner, bg="#0F172A")
        actions.pack(side="right", padx=20)
        ttk.Button(actions, text="新建批次", style="Primary.TButton", command=self.app.new_batch_quick).pack(side="left", padx=4)
        ttk.Button(actions, text="导入剂量", style="Secondary.TButton", command=lambda: self.app.go("dose_import")).pack(side="left", padx=4)
        ttk.Button(actions, text="运行核算", style="Secondary.TButton", command=lambda: self.app.go("dose_calc")).pack(side="left", padx=4)

        cards = tk.Frame(self, bg=COLORS["bg"])
        cards.pack(fill="x", pady=(16, 0))
        for i in range(4):
            cards.grid_columnconfigure(i, weight=1, uniform="metric")
        self.metric_values: dict[str, tk.Label] = {}
        specs = [
            ("total", "批次总数", "全部培养批次", COLORS["accent"]),
            ("active", "进行中批次", "当前培养中的批次", COLORS["success"]),
            ("anomaly", "未解决异常", "导入与核算异常", COLORS["warning"]),
            ("pending", "待审核核算", "需要人工确认的结果", COLORS["danger"]),
        ]
        for idx, (key, title, hint, color) in enumerate(specs):
            card = Card(cards, padding=18)
            card.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 8, 0))
            tk.Label(card.body, text=title, bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(anchor="w")
            value = tk.Label(card.body, text="0", bg=COLORS["white"], fg=color, font=(FONT[0], 28, "bold"))
            value.pack(anchor="w", pady=(6, 0))
            tk.Label(card.body, text=hint, bg=COLORS["white"], fg="#94A3B8", font=(FONT[0], 8)).pack(anchor="w")
            self.metric_values[key] = value

        middle = tk.Frame(self, bg=COLORS["bg"])
        middle.pack(fill="both", expand=True, pady=(16, 0))
        middle.grid_columnconfigure(0, weight=3)
        middle.grid_columnconfigure(1, weight=2)
        middle.grid_rowconfigure(0, weight=1)

        recent_card = Card(middle, padding=14)
        recent_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        head = tk.Frame(recent_card.body, bg=COLORS["white"])
        head.pack(fill="x")
        tk.Label(head, text="最近批次", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        ttk.Button(head, text="查看全部", style="Link.TButton",
                   command=lambda: self.app.go("batch")).pack(side="right")
        self.batch_table = DataTable(recent_card.body, [
            ("batch_code", "批次编号", 130), ("project_name", "项目", 180),
            ("culture_system", "培养体系", 90), ("status", "状态", 70),
            ("start_time", "开始时间", 120),
        ], height=4, id_key="batch_id")
        self.batch_table.pack(fill="both", expand=True, pady=(8, 0))
        self.batch_table.tree.bind("<Double-1>", lambda e: self._open_batch())

        pending_card = Card(middle, padding=14)
        pending_card.grid(row=0, column=1, sticky="nsew")
        head2 = tk.Frame(pending_card.body, bg=COLORS["white"])
        head2.pack(fill="x")
        tk.Label(head2, text="待处理事项", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        ttk.Button(head2, text="异常审核", style="Link.TButton",
                   command=lambda: self.app.go("anomaly")).pack(side="right")
        self.pending_list = tk.Listbox(pending_card.body, bg=COLORS["white"], fg=COLORS["text"],
                                       font=FONT_SMALL, relief="flat", highlightthickness=0,
                                       activestyle="none", selectbackground=COLORS["accent_soft"],
                                       selectforeground=COLORS["text"])
        self.pending_list.pack(fill="both", expand=True, pady=(8, 0))
        self.pending_list.bind("<Double-1>", self._open_pending)
        self._pending_targets: list[tuple[str, str]] = []

        lower = tk.Frame(self, bg=COLORS["bg"], height=200)
        lower.pack(fill="x", pady=(16, 0))
        lower.pack_propagate(False)
        lower.grid_columnconfigure(0, weight=1)
        lower.grid_columnconfigure(1, weight=1)
        lower.grid_rowconfigure(0, weight=1)

        imports_card = Card(lower, padding=14)
        imports_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        h = tk.Frame(imports_card.body, bg=COLORS["white"])
        h.pack(fill="x")
        tk.Label(h, text="最近导入", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        ttk.Button(h, text="剂量导入", style="Link.TButton",
                   command=lambda: self.app.go("dose_import")).pack(side="right")
        self.import_table = DataTable(imports_card.body, [
            ("source_type", "来源", 90), ("original_filename", "文件", 210),
            ("batch_code", "批次", 120), ("imported_at", "导入时间", 130),
            ("import_status", "状态", 80),
        ], height=3)
        self.import_table.pack(fill="both", expand=True, pady=(8, 0))

        report_card = Card(lower, padding=14)
        report_card.grid(row=0, column=1, sticky="nsew")
        h2 = tk.Frame(report_card.body, bg=COLORS["white"])
        h2.pack(fill="x")
        tk.Label(h2, text="快捷操作", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        buttons = [
            ("配置配方与组分", "维护配方版本与浓度", "formula"),
            ("配制计算", "生成理论用量与称量清单", "preparation"),
            ("补料计划", "安排泵、液体与时间窗口", "plan"),
            ("生成批次报告", "导出 Excel / PDF 报告", "reports"),
        ]
        grid = tk.Frame(report_card.body, bg=COLORS["white"])
        grid.pack(fill="both", expand=True, pady=(8, 0))
        for i, (title, sub, key) in enumerate(buttons):
            row, col = divmod(i, 2)
            item = tk.Frame(grid, bg="#F8FAFC", highlightbackground=COLORS["border"], highlightthickness=1,
                            cursor="hand2")
            item.grid(row=row, column=col, sticky="nsew", padx=(0, 8), pady=(0, 8))
            grid.grid_columnconfigure(col, weight=1)
            tk.Label(item, text=title, bg="#F8FAFC", fg=COLORS["text"], font=FONT_BOLD,
                     anchor="w").pack(fill="x", padx=12, pady=(9, 0))
            tk.Label(item, text=sub, bg="#F8FAFC", fg=COLORS["muted"], font=(FONT[0], 8),
                     anchor="w").pack(fill="x", padx=12, pady=(1, 9))
            for child in item.winfo_children():
                child.bind("<Button-1>", lambda e, k=key: self.app.go(k))
            item.bind("<Button-1>", lambda e, k=key: self.app.go(k))

        self._configure_batch_table()

    def _configure_batch_table(self):
        self.batch_table.columns[4]["format"] = lambda v, r: human_dt(v)

    def on_show(self) -> None:
        self.refresh()

    def on_batch_changed(self) -> None:
        if self.winfo_exists():
            self.refresh()

    def refresh(self) -> None:
        db = self.ctx.db
        total = int(db.scalar("SELECT COUNT(*) FROM batch_info", (), 0))
        active = int(db.scalar("SELECT COUNT(*) FROM batch_info WHERE status='进行中'", (), 0))
        anomalies = int(db.scalar("SELECT COUNT(*) FROM dose_anomaly WHERE status='未解决'", (), 0))
        pending = int(db.scalar("SELECT COUNT(*) FROM dose_calculation WHERE quality_status='待审核'", (), 0))
        self.metric_values["total"].configure(text=str(total))
        self.metric_values["active"].configure(text=str(active))
        self.metric_values["anomaly"].configure(text=str(anomalies))
        self.metric_values["pending"].configure(text=str(pending))

        batches = self.ctx.repos.batches.list_with_reactor()[:8]
        self.batch_table.set_rows(batches, "batch_id")
        imports = self.ctx.repos.imports.list_recent(limit=8)
        self.import_table.set_rows(imports)

        self.pending_list.delete(0, "end")
        self._pending_targets = []
        items = []
        for a in self.ctx.repos.anomalies.list_for_batch(status="未解决")[:8]:
            items.append((f"⚠  {a.get('anomaly_type')}：{(a.get('description') or '')[:46]}", "anomaly"))
        for c in db.q("SELECT c.*, p.pump_code, b.batch_code FROM dose_calculation c "
                      "JOIN pump_info p ON p.pump_id=c.pump_id JOIN batch_info b ON b.batch_id=c.batch_id "
                      "WHERE c.quality_status='待审核' ORDER BY c.calculated_at DESC LIMIT 8"):
            items.append((f"◎  待审核核算 {c['batch_code']} / {c['pump_code']} / {c['calculation_id']}", "dose_calc"))
        for rep in self.ctx.repos.reports.list_for_batch()[:4]:
            items.append((f"▤  报告已生成：{rep.get('batch_code')} / {rep.get('report_type')}", "reports"))
        if not items:
            items = [("暂无待处理事项，数据状态良好。", "")]
        for text, target in items:
            self.pending_list.insert("end", text)
            self._pending_targets.append((text, target))

    def _open_batch(self):
        row = self.batch_table.selected_row()
        if row and row.get("batch_id"):
            self.ctx.settings.last_batch_id = row["batch_id"]
            self.ctx.settings.save()
            self.app.refresh_batches()
            self.app.go("batch")

    def _open_pending(self, _event=None):
        selection = self.pending_list.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx < len(self._pending_targets):
            target = self._pending_targets[idx][1]
            if target:
                self.app.go(target)
