# -*- coding: utf-8 -*-
"""主窗口：左侧导航、顶部批次条与页面容器。"""
from __future__ import annotations

import importlib
import traceback
import tkinter as tk
from tkinter import messagebox, ttk

from ..context import AppContext
from .theme import COLORS, FONT, FONT_BOLD, FONT_SMALL, setup_theme
from .widgets import center_window

PAGE_INFO = {
    "dashboard": ("app.ui.pages.dashboard", "DashboardPage", "首页", "批次概览、待处理事项与快速入口"),
    "master": ("app.ui.pages.master_data", "MasterDataPage", "基础数据", "组分、工艺液、泵与反应器档案"),
    "formula": ("app.ui.pages.formula", "FormulaPage", "配方管理", "配方版本、组分明细与发布状态"),
    "preparation": ("app.ui.pages.preparation", "PreparationPage", "配制计算", "目标浓度、纯度修正、母液与称量清单"),
    "batch": ("app.ui.pages.batch", "BatchPage", "批次管理", "批次档案、培养阶段、参数与泵-液体绑定"),
    "plan": ("app.ui.pages.feed_plan", "FeedPlanPage", "补料计划", "计划版本、补料事件、时间冲突与累计量"),
    "calibration": ("app.ui.pages.calibration", "CalibrationPage", "泵校准", "校准记录、my-Control 导入与插值曲线"),
    "dose_import": ("app.ui.pages.dose_import", "DoseImportPage", "剂量导入", "Dose Monitor 文件映射、质量检查与归档"),
    "dose_calc": ("app.ui.pages.dose_calculation", "DoseCalculationPage", "剂量核算", "累计体积差、流速积分、偏差与完成率"),
    "anomaly": ("app.ui.pages.anomaly", "AnomalyPage", "异常审核", "导入、计算与人工修正异常的闭环处理"),
    "reports": ("app.ui.pages.reports", "ReportsPage", "报告中心", "批次 Excel / PDF 报告与历史版本"),
    "settings": ("app.ui.pages.settings", "SettingsPage", "系统设置", "操作员、数据目录、备份恢复与操作日志"),
}


class MainWindow(tk.Tk):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.title("细胞培养基配制与补料剂量核算软件 V1.0")
        self.configure(bg=COLORS["bg"])
        setup_theme(self)
        width, height = 1280, 800
        center_window(self, width, height)
        self.minsize(1120, 720)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.report_callback_exception = self._report_exception

        self.pages: dict[str, object] = {}
        self.nav_buttons: dict[str, tk.Button] = {}
        self.current_key = ""
        self.batch_labels: dict[str, str] = {}
        self.batch_ids: dict[str, str] = {}
        self._status_text = tk.StringVar(value="就绪")

        self._build_layout()
        self._bind_shortcuts()
        self.refresh_batches()
        self.go("dashboard")

    # ---------- 布局 ----------
    def _build_layout(self) -> None:
        self.sidebar = tk.Frame(self, bg=COLORS["sidebar"], width=224)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        logo = tk.Frame(self.sidebar, bg=COLORS["sidebar"], height=104)
        logo.pack(fill="x", pady=(18, 8))
        mark = tk.Label(logo, text="CC", bg=COLORS["accent"], fg="white", font=(FONT[0], 14, "bold"),
                        width=3, height=1)
        mark.pack(side="left", padx=(18, 10))
        text = tk.Frame(logo, bg=COLORS["sidebar"])
        text.pack(side="left", fill="x", expand=True)
        tk.Label(text, text="细胞培养", bg=COLORS["sidebar"], fg="white",
                 font=(FONT[0], 11, "bold")).pack(anchor="w")
        tk.Label(text, text="配制与剂量核算", bg=COLORS["sidebar"], fg=COLORS["sidebar_text"],
                 font=(FONT[0], 9)).pack(anchor="w")
        tk.Label(text, text="V1.0", bg=COLORS["sidebar"], fg="#64748B",
                 font=(FONT[0], 8)).pack(anchor="w", pady=(2, 0))

        nav = tk.Frame(self.sidebar, bg=COLORS["sidebar"])
        nav.pack(fill="both", expand=True, padx=10, pady=(6, 0))
        items = [
            ("dashboard", "首页与工作台"), ("master", "基础数据"), ("formula", "配方管理"),
            ("preparation", "配制计算"), ("batch", "批次管理"), ("plan", "补料计划"),
            ("calibration", "泵校准"), ("dose_import", "剂量导入"), ("dose_calc", "剂量核算"),
            ("anomaly", "异常审核"), ("reports", "报告中心"), ("settings", "系统设置"),
        ]
        for key, label in items:
            btn = tk.Button(nav, text=f"    {label}", anchor="w", bg=COLORS["sidebar"],
                            fg=COLORS["sidebar_text"], activebackground=COLORS["sidebar_hover"],
                            activeforeground="white", relief="flat", bd=0, font=FONT,
                            padx=10, pady=9, cursor="hand2",
                            command=lambda k=key: self.go(k))
            btn.pack(fill="x", pady=1)
            btn.bind("<Enter>", lambda e, b=btn, k=key: self._hover(b, k, True))
            btn.bind("<Leave>", lambda e, b=btn, k=key: self._hover(b, k, False))
            self.nav_buttons[key] = btn

        bottom = tk.Frame(self.sidebar, bg=COLORS["sidebar"])
        bottom.pack(fill="x", side="bottom", padx=18, pady=14)
        tk.Label(bottom, text="离线核算 · 不控制设备", bg=COLORS["sidebar"], fg="#64748B",
                 font=(FONT[0], 8)).pack(anchor="w")
        tk.Label(bottom, text="Windows 10/11", bg=COLORS["sidebar"], fg="#475569",
                 font=(FONT[0], 8)).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(self, bg=COLORS["bg"])
        right.pack(side="left", fill="both", expand=True)

        header = tk.Frame(right, bg=COLORS["white"], height=78)
        header.pack(fill="x")
        header.pack_propagate(False)
        head_inner = tk.Frame(header, bg=COLORS["white"])
        head_inner.pack(fill="both", expand=True, padx=24, pady=12)
        title_box = tk.Frame(head_inner, bg=COLORS["white"])
        title_box.pack(side="left", fill="y")
        self.page_title = tk.Label(title_box, text="", bg=COLORS["white"], fg=COLORS["text"],
                                   font=(FONT[0], 17, "bold"))
        self.page_title.pack(anchor="w")
        self.page_subtitle = tk.Label(title_box, text="", bg=COLORS["white"], fg=COLORS["muted"],
                                      font=FONT_SMALL)
        self.page_subtitle.pack(anchor="w", pady=(2, 0))

        right_box = tk.Frame(head_inner, bg=COLORS["white"])
        right_box.pack(side="right", fill="y", pady=6)
        tk.Label(right_box, text="当前批次", bg=COLORS["white"], fg=COLORS["muted"],
                 font=FONT_SMALL).pack(side="left", padx=(0, 8))
        self.batch_var = tk.StringVar()
        self.batch_combo = ttk.Combobox(right_box, textvariable=self.batch_var, width=36, state="readonly")
        self.batch_combo.pack(side="left")
        self.batch_combo.bind("<<ComboboxSelected>>", self._batch_selected)
        ttk.Button(right_box, text="刷新", style="Ghost.TButton", command=self.refresh_batches).pack(side="left", padx=4)
        self.operator_label = tk.Label(right_box, text=f"  {self.ctx.operator}  ", bg="#F1F5F9",
                                       fg=COLORS["text"], font=(FONT[0], 9, "bold"), padx=10, pady=5)
        self.operator_label.pack(side="left", padx=(12, 0))

        self.content = tk.Frame(right, bg=COLORS["bg"])
        self.content.pack(fill="both", expand=True, padx=18, pady=(16, 8))

        footer = tk.Frame(right, bg=COLORS["white"], height=30)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Label(footer, textvariable=self._status_text, bg=COLORS["white"], fg=COLORS["muted"],
                 font=(FONT[0], 8), anchor="w").pack(side="left", padx=18)
        tk.Label(footer, text=str(self.ctx.settings.db_path), bg=COLORS["white"], fg="#94A3B8",
                 font=(FONT[0], 8), anchor="e").pack(side="right", padx=18)

    def _bind_shortcuts(self) -> None:
        keys = ["dashboard", "master", "formula", "preparation", "batch", "plan",
                "calibration", "dose_import", "dose_calc", "anomaly", "reports", "settings"]
        for i, key in enumerate(keys[:9]):
            self.bind_all(f"<Control-Key-{i + 1}>", lambda e, k=key: self.go(k))
        self.bind_all("<Control-Key-0>", lambda e: self.go("settings"))
        self.bind_all("<F5>", lambda e: self._refresh_current())

    def _refresh_current(self) -> None:
        page = self.pages.get(self.current_key)
        if page and hasattr(page, "refresh"):
            page.refresh()
            self.set_status("已刷新")

    def _hover(self, btn: tk.Button, key: str, entering: bool) -> None:
        if key == self.current_key:
            return
        btn.configure(bg=COLORS["sidebar_hover"] if entering else COLORS["sidebar"])

    # ---------- 页面切换 ----------
    def go(self, key: str) -> None:
        if key not in PAGE_INFO:
            return
        if self.current_key:
            old = self.pages.get(self.current_key)
            if old is not None:
                old.pack_forget()
            self.nav_buttons[self.current_key].configure(bg=COLORS["sidebar"], fg=COLORS["sidebar_text"])
        module_name, class_name, title, subtitle = PAGE_INFO[key]
        if key not in self.pages:
            module = importlib.import_module(module_name)
            cls = getattr(module, class_name)
            self.pages[key] = cls(self.content, self)
        page = self.pages[key]
        page.pack(fill="both", expand=True)
        self.current_key = key
        self.page_title.configure(text=title)
        self.page_subtitle.configure(text=subtitle)
        self.nav_buttons[key].configure(bg=COLORS["sidebar_active"], fg="white")
        try:
            page.on_show()
        except Exception:
            self._report_exception(*__import__("sys").exc_info())

    # ---------- 批次 ----------
    def refresh_batches(self) -> None:
        batches = self.ctx.repos.batches.list_with_reactor()
        self.batch_labels = {}
        self.batch_ids = {}
        for b in batches:
            label = f"{b['batch_code']}  ·  {b.get('project_name') or '未命名项目'}  [{b.get('status')}]"
            self.batch_labels[label] = b["batch_id"]
            self.batch_ids[b["batch_id"]] = label
        self.batch_combo.configure(values=list(self.batch_labels.keys()))
        last = self.ctx.settings.last_batch_id
        if last and last in self.batch_ids:
            self.batch_var.set(self.batch_ids[last])
        elif batches:
            self.batch_var.set(next(iter(self.batch_labels.keys())))
            self.ctx.settings.last_batch_id = self.batch_labels[self.batch_var.get()]
        else:
            self.batch_var.set("（暂无批次，请先在批次管理中新建）")
            self.ctx.settings.last_batch_id = ""
        self._notify_batch_change()

    def _batch_selected(self, _event=None) -> None:
        label = self.batch_var.get()
        batch_id = self.batch_labels.get(label, "")
        self.ctx.settings.last_batch_id = batch_id
        self.ctx.settings.save()
        self._notify_batch_change()

    def _notify_batch_change(self) -> None:
        for page in self.pages.values():
            try:
                page.on_batch_changed()
            except Exception:
                pass

    @property
    def current_batch_id(self) -> str | None:
        return self.ctx.settings.last_batch_id or None

    @property
    def current_batch(self) -> dict | None:
        batch_id = self.current_batch_id
        return self.ctx.repos.batches.get(batch_id) if batch_id else None

    def require_batch(self) -> str | None:
        batch_id = self.current_batch_id
        if not batch_id:
            messagebox.showinfo("请选择批次", "请先在顶部选择批次，或到“批次管理”新建批次。", parent=self)
            return None
        return batch_id

    def new_batch_quick(self) -> None:
        self.go("batch")
        page = self.pages.get("batch")
        if page and hasattr(page, "new_batch"):
            page.new_batch()

    # ---------- 状态与异常 ----------
    def set_status(self, message: str) -> None:
        self._status_text.set(message)

    def _report_exception(self, exc_type, exc_value, exc_tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        self._status_text.set(f"发生错误：{exc_value}")
        try:
            self.ctx.repos.logs.add(self.ctx.operator, "界面异常", "system", "", after={"error": str(exc_value)})
        except Exception:
            pass
        messagebox.showerror("软件运行异常", f"{exc_value}\n\n详细信息已写入控制台。", parent=self)
        print(text)

    def on_close(self) -> None:
        try:
            self.ctx.settings.last_batch_id = self.current_batch_id or ""
            self.ctx.settings.save()
            self.ctx.close()
        finally:
            self.destroy()
