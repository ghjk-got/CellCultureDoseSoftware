# -*- coding: utf-8 -*-
"""系统设置：操作员、数据目录、备份恢复与操作日志。"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, ttk

from ...config import APP_VERSION, BASE_DIR
from ..base import Page
from ..theme import COLORS, FONT, FONT_H3, FONT_SMALL
from ..widgets import Card, DataTable, confirm, error, human_dt, info, open_path


class SettingsPage(Page):
    key = "settings"
    title = "系统设置"
    subtitle = "操作员、数据目录、备份恢复与操作日志"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()
        self.refresh()

    def _build(self):
        top = tk.Frame(self, bg=COLORS["bg"])
        top.pack(fill="x")
        self.info_label = tk.Label(top, text="", bg=COLORS["bg"], fg=COLORS["muted"], font=FONT_SMALL)
        self.info_label.pack(side="left")

        columns = tk.Frame(self, bg=COLORS["bg"])
        columns.pack(fill="both", expand=True, pady=(12, 0))
        columns.grid_columnconfigure(0, weight=1)
        columns.grid_columnconfigure(1, weight=1)
        columns.grid_rowconfigure(0, weight=1)

        left = tk.Frame(columns, bg=COLORS["bg"])
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        app_card = Card(left, padding=16)
        app_card.pack(fill="x")
        tk.Label(app_card.body, text="软件与数据", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w")
        rows = [("软件版本", f"V{APP_VERSION}"), ("数据目录", str(self.ctx.settings.data_dir)),
                ("数据库", str(self.ctx.settings.db_path)), ("数据库结构版本", "1.0")]
        self.value_labels = {}
        for key, value in rows:
            box = tk.Frame(app_card.body, bg=COLORS["white"])
            box.pack(fill="x", pady=(8, 0))
            tk.Label(box, text=key, bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL, width=16,
                     anchor="w").pack(side="left")
            label = tk.Label(box, text=value, bg=COLORS["white"], fg=COLORS["text"], font=FONT_SMALL,
                             anchor="w", wraplength=360, justify="left")
            label.pack(side="left", fill="x", expand=True)
            self.value_labels[key] = label
        bar = tk.Frame(app_card.body, bg=COLORS["white"])
        bar.pack(fill="x", pady=(12, 0))
        ttk.Button(bar, text="更改数据目录", style="Secondary.TButton", command=self.change_data_dir).pack(side="left")
        ttk.Button(bar, text="打开数据目录", style="Ghost.TButton", command=self.open_data_dir).pack(side="left", padx=6)

        pref_card = Card(left, padding=16)
        pref_card.pack(fill="x", pady=(12, 0))
        tk.Label(pref_card.body, text="操作员与计算参数", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w")
        form = tk.Frame(pref_card.body, bg=COLORS["white"])
        form.pack(fill="x", pady=(8, 0))
        tk.Label(form, text="操作员", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL,
                 width=16, anchor="w").grid(row=0, column=0, sticky="w", pady=4)
        self.operator_var = tk.StringVar(value=self.ctx.settings.operator)
        ttk.Entry(form, textvariable=self.operator_var).grid(row=0, column=1, sticky="ew", pady=4)
        tk.Label(form, text="允许采样间隔 (h)", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL,
                 width=16, anchor="w").grid(row=1, column=0, sticky="w", pady=4)
        self.gap_var = tk.StringVar(value=str(self.ctx.settings.max_sample_gap_h))
        ttk.Entry(form, textvariable=self.gap_var).grid(row=1, column=1, sticky="ew", pady=4)
        tk.Label(form, text="默认体积单位", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL,
                 width=16, anchor="w").grid(row=2, column=0, sticky="w", pady=4)
        self.volume_unit_var = tk.StringVar(value=self.ctx.settings.default_volume_unit)
        ttk.Combobox(form, textvariable=self.volume_unit_var, values=["mL", "L", "uL"], state="readonly").grid(
            row=2, column=1, sticky="ew", pady=4)
        tk.Label(form, text="默认流速单位", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL,
                 width=16, anchor="w").grid(row=3, column=0, sticky="w", pady=4)
        self.flow_unit_var = tk.StringVar(value=self.ctx.settings.default_flow_unit)
        ttk.Combobox(form, textvariable=self.flow_unit_var, values=["mL/h", "mL/min", "L/h", "uL/min"],
                     state="readonly").grid(row=3, column=1, sticky="ew", pady=4)
        form.grid_columnconfigure(1, weight=1)
        ttk.Button(pref_card.body, text="保存设置", style="Primary.TButton", command=self.save_settings).pack(anchor="w", pady=(10, 0))

        right = tk.Frame(columns, bg=COLORS["bg"])
        right.grid(row=0, column=1, sticky="nsew")
        log_card = Card(right, padding=16)
        log_card.pack(fill="both", expand=True)
        h2 = tk.Frame(log_card.body, bg=COLORS["white"])
        h2.pack(fill="x")
        tk.Label(h2, text="操作日志（最近 300 条）", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        ttk.Button(h2, text="刷新", style="Ghost.TButton", command=self.refresh_logs).pack(side="right")
        self.log_table = DataTable(log_card.body, [
            ("created_at", "时间", 140), ("user_id", "用户", 80), ("action_type", "操作", 110),
            ("object_type", "对象", 100), ("reason", "说明", 190),
        ], height=14)
        self.log_table.pack(fill="both", expand=True, pady=(8, 0))

        backup_card = Card(right, padding=16)
        backup_card.pack(fill="x", pady=(12, 0))
        h = tk.Frame(backup_card.body, bg=COLORS["white"])
        h.pack(fill="x")
        tk.Label(h, text="备份与恢复", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        ttk.Button(h, text="立即备份", style="Primary.TButton", command=self.create_backup).pack(side="right")
        ttk.Button(h, text="校验选中", style="Ghost.TButton", command=self.verify_backup).pack(side="right", padx=6)
        ttk.Button(h, text="恢复选中", style="Danger.TButton", command=self.restore_backup).pack(side="right")
        self.backup_table = DataTable(backup_card.body, [
            ("name", "备份文件", 230), ("size", "大小", 75), ("mtime", "创建时间", 135),
        ], height=3, id_key="path")
        self.backup_table.pack(fill="both", expand=True, pady=(8, 0))

    def on_show(self):
        self.refresh()

    def refresh(self):
        self.info_label.configure(text=f"软件版本 V{APP_VERSION} · 数据库结构 1.0 · 操作员 {self.ctx.operator}")
        self.value_labels["数据目录"].configure(text=str(self.ctx.settings.data_dir))
        self.value_labels["数据库"].configure(text=str(self.ctx.settings.db_path))
        self.refresh_backups()
        self.refresh_logs()

    def refresh_backups(self):
        rows = []
        for path in self.ctx.backups.list():
            stat = path.stat()
            rows.append({"name": path.name, "size": f"{stat.st_size / 1024 / 1024:.2f} MB",
                         "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                         "path": str(path)})
        self.backup_table.set_rows(rows, "path")

    def refresh_logs(self):
        self.log_table.set_rows(self.ctx.repos.logs.recent(300))

    def save_settings(self):
        operator = self.operator_var.get().strip()
        if not operator:
            error(self, "操作员不能为空")
            return
        try:
            gap = float(self.gap_var.get())
        except ValueError:
            error(self, "允许采样间隔必须是数字")
            return
        if gap <= 0:
            error(self, "允许采样间隔必须大于 0")
            return
        self.ctx.settings.operator = operator
        self.ctx.settings.max_sample_gap_h = gap
        self.ctx.settings.default_volume_unit = self.volume_unit_var.get()
        self.ctx.settings.default_flow_unit = self.flow_unit_var.get()
        self.ctx.settings.save()
        self.app.operator_label.configure(text=f"  {operator}  ")
        self.ctx.audit("修改系统设置", "app_setting", after={"operator": operator, "max_gap": gap})
        self.set_status("设置已保存")
        self.refresh()

    def change_data_dir(self):
        folder = filedialog.askdirectory(parent=self, title="选择数据目录", initialdir=str(self.ctx.settings.data_dir))
        if not folder:
            return
        if not confirm(self, "更改数据目录", "更改后需要重启软件。新目录将创建空数据库，原数据不会被自动迁移。继续？"):
            return
        self.ctx.settings.data_dir = folder
        self.ctx.settings.save()
        self.value_labels["数据目录"].configure(text=folder)
        info(self, "数据目录已更改。请重启软件以使用新目录。")

    def open_data_dir(self):
        path = Path(self.ctx.settings.data_dir)
        path.mkdir(parents=True, exist_ok=True)
        open_path(path)

    def create_backup(self):
        self.set_status("正在创建备份…")
        self.update_idletasks()
        try:
            path = self.ctx.backups.create(note=f"手动备份 by {self.ctx.operator}")
        except Exception as exc:
            error(self, f"备份失败：{exc}")
            return
        self.ctx.audit("创建备份", "backup", path.name)
        self.refresh_backups()
        self.set_status(f"备份已创建：{path.name}")
        info(self, f"备份已创建：\n{path}")

    def _selected_backup(self) -> str | None:
        row = self.backup_table.selected_row()
        if not row:
            info(self, "请先选择备份文件")
            return None
        return row["path"]

    def verify_backup(self):
        path = self._selected_backup()
        if not path:
            return
        try:
            info_data = self.ctx.backups.verify(path)
        except Exception as exc:
            error(self, f"校验失败：{exc}")
            return
        manifest = info_data.get("manifest") or {}
        info(self, f"备份校验通过。\n\n创建时间：{manifest.get('created_at') or '—'}\n"
                   f"软件版本：{manifest.get('app_version') or '—'}\n"
                   f"数据库完整性：{info_data.get('integrity')}\n"
                   f"数据表数量：{info_data.get('tables')}\n"
                   f"说明：{manifest.get('note') or '—'}")

    def restore_backup(self):
        path = self._selected_backup()
        if not path:
            return
        try:
            info_data = self.ctx.backups.verify(path)
        except Exception as exc:
            error(self, f"备份不可用：{exc}")
            return
        if not confirm(self, "确认恢复备份",
                       "恢复将覆盖当前数据库，并把备份中的导入文件与报告合并到数据目录。\n"
                       "系统会先自动创建一份恢复前备份。\n\n是否继续？"):
            return
        if not confirm(self, "再次确认", "此操作会替换当前业务数据。确定恢复？"):
            return
        self.set_status("正在恢复备份…")
        self.update_idletasks()
        try:
            safety = self.ctx.backups.restore(path)
        except Exception as exc:
            error(self, f"恢复失败：{exc}")
            return
        messagebox_text = f"恢复完成。\n恢复前备份：{safety.name}\n\n软件将重新启动。"
        info(self, messagebox_text)
        self._restart()

    def _restart(self):
        try:
            subprocess.Popen([sys.executable, str(BASE_DIR / "main.py")], cwd=str(BASE_DIR))
        finally:
            self.app.destroy()
