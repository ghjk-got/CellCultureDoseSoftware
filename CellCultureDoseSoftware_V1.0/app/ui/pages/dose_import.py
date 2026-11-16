# -*- coding: utf-8 -*-
"""剂量数据导入：五步向导、字段映射、质量检查与导入历史。"""
from __future__ import annotations

import csv
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..base import Page
from ..theme import COLORS, FONT, FONT_H3, FONT_SMALL
from ..widgets import (Card, DataTable, FormDialog, center_window, confirm, error,
                       human_dt, info, warning)


STEP_NAMES = ["选择文件", "工作表与表头", "字段映射", "数据预览", "确认导入"]
DOSE_FIELDS = [
    ("timestamp", "时间戳 *"), ("pump_code", "泵编号 *"), ("flow_rate", "流速"),
    ("flow_unit", "流速单位"), ("total_volume", "累计体积"), ("volume_unit", "体积单位"),
    ("pump_status", "泵状态"),
]


class DoseImportWizard(tk.Toplevel):
    def __init__(self, parent, page: "DoseImportPage"):
        super().__init__(parent)
        self.page = page
        self.ctx = page.ctx
        self.service = self.ctx.dose_import
        self.batch_id = page.app.current_batch_id
        self.files: list[Path] = []
        self.header_rows: dict[str, int] = {}
        self.mappings: dict[str, dict[str, int]] = {}
        self.previews: dict[str, object] = {}
        self.first_table = None
        self.step = 0
        self.title("导入 Dose Monitor 剂量数据")
        self.configure(bg=COLORS["white"])
        self.geometry("1040x780")
        center_window(self, 1040, 780)
        self.transient(parent)
        self.grab_set()
        self._build()
        self.show_step(0)

    def _build(self):
        header = tk.Frame(self, bg=COLORS["white"])
        header.pack(fill="x", padx=24, pady=(18, 8))
        tk.Label(header, text="导入 Dose Monitor 剂量数据", bg=COLORS["white"], fg=COLORS["text"],
                 font=(FONT[0], 15, "bold")).pack(anchor="w")
        self.batch_label = tk.Label(header, text=f"目标批次：{self.page.app.current_batch.get('batch_code') if self.page.app.current_batch else '未选择'}",
                                    bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL)
        self.batch_label.pack(anchor="w", pady=(2, 0))

        self.step_bar = tk.Frame(self, bg=COLORS["white"])
        self.step_bar.pack(fill="x", padx=24, pady=8)
        self.step_labels = []
        for i, name in enumerate(STEP_NAMES):
            box = tk.Frame(self.step_bar, bg="#F1F5F9")
            box.pack(side="left", fill="x", expand=True, padx=(0, 4))
            num = tk.Label(box, text=f" {i + 1} ", bg="#E2E8F0", fg=COLORS["muted"],
                           font=(FONT[0], 9, "bold"))
            num.pack(side="left", padx=(4, 6), pady=6)
            label = tk.Label(box, text=name, bg="#F1F5F9", fg=COLORS["muted"], font=(FONT[0], 9))
            label.pack(side="left", pady=6)
            self.step_labels.append((box, num, label))

        self.body = tk.Frame(self, bg=COLORS["white"])
        self.body.pack(fill="both", expand=True, padx=24, pady=4)
        self.frames = []
        for i in range(len(STEP_NAMES)):
            frame = tk.Frame(self.body, bg=COLORS["white"])
            self.frames.append(frame)
        self._build_step1(self.frames[0])
        self._build_step2(self.frames[1])
        self._build_step3(self.frames[2])
        self._build_step4(self.frames[3])
        self._build_step5(self.frames[4])

        footer = tk.Frame(self, bg="#F8FAFC")
        footer.pack(fill="x", side="bottom")
        inner = tk.Frame(footer, bg="#F8FAFC")
        inner.pack(fill="x", padx=24, pady=12)
        ttk.Button(inner, text="取消", style="Secondary.TButton", command=self.destroy).pack(side="right")
        self.next_btn = ttk.Button(inner, text="下一步", style="Primary.TButton", command=self.next_step)
        self.next_btn.pack(side="right", padx=8)
        self.back_btn = ttk.Button(inner, text="上一步", style="Ghost.TButton", command=self.prev_step)
        self.back_btn.pack(side="right", padx=6)
        self.status_label = tk.Label(inner, text="", bg="#F8FAFC", fg=COLORS["muted"], font=FONT_SMALL)
        self.status_label.pack(side="left")

    # ---------- 步骤 1 ----------
    def _build_step1(self, frame):
        tk.Label(frame, text="选择 Dose Monitor 导出的 CSV / XLSX 文件（可多选）", bg=COLORS["white"],
                 fg=COLORS["text"], font=FONT_H3).pack(anchor="w", pady=(4, 6))
        bar = tk.Frame(frame, bg=COLORS["white"])
        bar.pack(fill="x")
        ttk.Button(bar, text="添加文件", style="Primary.TButton", command=self.add_files).pack(side="left")
        ttk.Button(bar, text="移除选中", style="Ghost.TButton", command=self.remove_file).pack(side="left", padx=6)
        self.file_list = tk.Listbox(frame, bg="#F8FAFC", fg=COLORS["text"], font=FONT_SMALL,
                                    relief="solid", bd=1, selectbackground=COLORS["accent_soft"],
                                    selectforeground=COLORS["text"], height=10)
        self.file_list.pack(fill="both", expand=True, pady=(10, 0))
        tk.Label(frame, text="导入过程不会静默删除异常行；无法解析的行会进入错误明细并阻止确认导入。",
                 bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(anchor="w", pady=(8, 0))

    def add_files(self):
        paths = filedialog.askopenfilenames(parent=self, title="选择 Dose Monitor 文件",
                                           filetypes=[("表格文件", "*.csv *.xlsx *.xlsm *.txt *.tsv"), ("所有文件", "*.*")])
        for path in paths:
            p = Path(path)
            if p not in self.files:
                self.files.append(p)
                self.file_list.insert("end", p.name + "    " + str(p.parent))
        if paths and not self.first_table:
            self._load_first_table()

    def remove_file(self):
        selection = self.file_list.curselection()
        if not selection:
            return
        idx = selection[0]
        self.file_list.delete(idx)
        del self.files[idx]
        self.first_table = None

    # ---------- 步骤 2 ----------
    def _build_step2(self, frame):
        tk.Label(frame, text="选择工作表与表头行", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w", pady=(4, 6))
        bar = tk.Frame(frame, bg=COLORS["white"])
        bar.pack(fill="x")
        tk.Label(bar, text="工作表", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="left")
        self.sheet_var = tk.StringVar()
        self.sheet_combo = ttk.Combobox(bar, textvariable=self.sheet_var, state="readonly", width=26)
        self.sheet_combo.pack(side="left", padx=6)
        tk.Label(bar, text="表头行", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="left", padx=(12, 0))
        self.header_var = tk.StringVar(value="1")
        ttk.Entry(bar, textvariable=self.header_var, width=6).pack(side="left", padx=6)
        ttk.Button(bar, text="读取表头", style="Secondary.TButton", command=self._load_first_table).pack(side="left")
        ttk.Button(bar, text="自动识别", style="Ghost.TButton", command=self._guess_header).pack(side="left", padx=6)
        self.raw_text = tk.Text(frame, bg="#F8FAFC", fg=COLORS["text"], font=("Consolas", 9),
                                relief="solid", bd=1, wrap="none", height=18)
        self.raw_text.pack(fill="both", expand=True, pady=(10, 0))
        tk.Label(frame, text="提示：Dose Monitor 的累计体积可能是批次累计或单次累计；如存在自动归零，导入后会在核算时识别计数区段。",
                 bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL, wraplength=900).pack(anchor="w", pady=(8, 0))

    def _guess_header(self):
        if not self.files:
            return
        from ...importers.table_reader import guess_header_row
        try:
            self.header_var.set(str(guess_header_row(self.files[0], self.sheet_var.get() or None)))
            self._load_first_table()
        except Exception as exc:
            error(self, str(exc))

    def _load_first_table(self):
        if not self.files:
            info(self, "请先在第一步添加文件")
            return
        from ...importers.table_reader import list_sheets, read_table
        path = self.files[0]
        try:
            sheets = list_sheets(path)
        except Exception:
            sheets = []
        if sheets and not self.sheet_var.get():
            self.sheet_combo.configure(values=sheets)
            self.sheet_var.set(sheets[0])
        elif sheets:
            self.sheet_combo.configure(values=sheets)
        try:
            table = read_table(path, self.sheet_var.get() or None, int(self.header_var.get() or 1))
        except Exception as exc:
            error(self, f"读取失败：{exc}")
            return
        self.first_table = table
        self.header_rows[str(path)] = int(self.header_var.get() or 1)
        self.raw_text.delete("1.0", "end")
        self.raw_text.insert("1.0", "\t".join(table.headers) + "\n")
        for row in table.rows[:20]:
            self.raw_text.insert("end", "\t".join("" if v is None else str(v) for v in row) + "\n")
        self._build_mapping_values(table.headers)

    # ---------- 步骤 3 ----------
    def _build_step3(self, frame):
        tk.Label(frame, text="字段映射", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w", pady=(4, 4))
        tk.Label(frame, text="将源文件列映射到标准字段。映射将应用到本批所有文件；列名需一致。",
                 bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(anchor="w", pady=(0, 8))
        self.map_frame = tk.Frame(frame, bg=COLORS["white"])
        self.map_frame.pack(fill="x")
        self.map_vars = {}
        self.map_combos = {}
        for i, (key, label) in enumerate(DOSE_FIELDS):
            row, col = divmod(i, 4)
            tk.Label(self.map_frame, text=label, bg=COLORS["white"], fg=COLORS["muted"],
                     font=(FONT[0], 8)).grid(row=row * 2, column=col, sticky="w", padx=8, pady=(8, 0))
            var = tk.StringVar()
            combo = ttk.Combobox(self.map_frame, textvariable=var, state="readonly", width=24)
            combo.grid(row=row * 2 + 1, column=col, sticky="ew", padx=8, pady=(2, 8))
            self.map_vars[key] = var
            self.map_combos[key] = combo
        for col in range(4):
            self.map_frame.grid_columnconfigure(col, weight=1)
        ttk.Button(frame, text="自动匹配字段", style="Secondary.TButton", command=self._auto_map).pack(anchor="w", pady=10)
        tk.Label(frame, text="标准时间格式：YYYY-MM-DD HH:MM:SS；流速与累计体积可直接带单位（如 10 mL/h）。",
                 bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(anchor="w")

    def _build_mapping_values(self, headers):
        choices = ["（不导入）"] + list(headers)
        self._header_choices = choices
        self._header_values = list(headers)
        auto = self.service.suggest_mapping(headers)
        for key, var in self.map_vars.items():
            self.map_combos[key].configure(values=choices)
            var.set("（不导入）")
        for key, idx in auto.items():
            if key in self.map_vars and idx < len(headers):
                self.map_vars[key].set(headers[idx])

    def _auto_map(self):
        if not self.first_table:
            self._load_first_table()
        if not self.first_table:
            return
        auto = self.service.suggest_mapping(self.first_table.headers)
        for key, var in self.map_vars.items():
            var.set("（不导入）")
        for key, idx in auto.items():
            if key in self.map_vars and idx < len(self.first_table.headers):
                self.map_vars[key].set(self.first_table.headers[idx])

    def _mapping_for_file(self, path: Path, table) -> dict[str, int]:
        wanted = {}
        for key, var in self.map_vars.items():
            value = var.get()
            if value in self._header_values:
                wanted[key] = value
        mapping = {}
        for key, header in wanted.items():
            if header in table.headers:
                mapping[key] = table.headers.index(header)
        missing = [key for key in ("timestamp", "pump_code")
                   if key in wanted and key not in mapping]
        if missing:
            raise ValueError(f"{path.name} 缺少映射列：{', '.join(missing)}")
        return mapping

    # ---------- 步骤 4 ----------
    def _build_step4(self, frame):
        tk.Label(frame, text="数据预览与质量检查", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w", pady=(4, 6))
        self.preview_summary = tk.Label(frame, text="", bg=COLORS["white"], fg=COLORS["text"],
                                        font=FONT_SMALL, justify="left", anchor="w")
        self.preview_summary.pack(fill="x")
        self.preview_table = DataTable(frame, [
            ("timestamp_utc", "时间", 145), ("pump_code", "泵", 90), ("flow_rate", "流速", 80),
            ("flow_unit", "单位", 70), ("total_volume", "累计体积", 95), ("volume_unit", "单位", 60),
            ("pump_status", "状态", 70), ("quality_flags", "质量标记", 180),
        ], height=10)
        self.preview_table.pack(fill="both", expand=True, pady=(8, 4))
        issue_bar = tk.Frame(frame, bg=COLORS["white"])
        issue_bar.pack(fill="x", pady=(4, 0))
        tk.Label(issue_bar, text="错误与警告", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        ttk.Button(issue_bar, text="导出问题清单", style="Ghost.TButton", command=self.export_issues).pack(side="right")
        self.issue_text = tk.Text(frame, bg="#F8FAFC", fg=COLORS["text"], font=FONT_SMALL,
                                  relief="solid", bd=1, height=6, wrap="word")
        self.issue_text.pack(fill="x", pady=(4, 0))

    def _build_previews(self) -> bool:
        from ...importers.table_reader import read_table
        self.previews = {}
        all_rows = []
        all_errors = []
        all_warnings = []
        summaries = []
        for path in self.files:
            try:
                table = read_table(path, self.sheet_var.get() or None, int(self.header_var.get() or 1))
                mapping = self._mapping_for_file(path, table)
                pv = self.service.preview(self.page.app.current_batch_id, path, self.sheet_var.get() or None,
                                          int(self.header_var.get() or 1), mapping,
                                          self.ctx.settings.default_flow_unit,
                                          self.ctx.settings.default_volume_unit)
            except Exception as exc:
                all_errors.append({"file": path.name, "row": "-", "field": "读取", "message": str(exc)})
                continue
            self.previews[str(path)] = pv
            all_rows.extend(pv.normalized[:300])
            for e in pv.errors:
                all_errors.append({"file": path.name, **e})
            for w in pv.warnings:
                all_warnings.append({"file": path.name, **w})
            summaries.append(
                f"{path.name}：总行 {pv.stats.get('total_rows', 0)}，有效 {pv.stats.get('success_rows', 0)}，"
                f"错误 {pv.stats.get('error_rows', 0)}，警告 {pv.stats.get('warning_rows', 0)}，"
                f"时间 {human_dt(pv.stats.get('time_start'))} ~ {human_dt(pv.stats.get('time_end'))}")
        self.preview_table.set_rows(all_rows)
        self.preview_summary.configure(text="\n".join(summaries) if summaries else "没有可预览的数据。")
        lines = []
        for e in all_errors[:80]:
            lines.append(f"[错误] {e.get('file')} 第 {e.get('row')} 行 / {e.get('field')}：{e.get('message')}")
        for w in all_warnings[:80]:
            lines.append(f"[警告] {w.get('file')} 第 {w.get('row')} 行 / {w.get('type')}：{w.get('message')}")
        self.issue_text.delete("1.0", "end")
        self.issue_text.insert("1.0", "\n".join(lines) if lines else "质量检查通过，未发现错误或警告。")
        self.issue_text.configure(fg=COLORS["danger"] if all_errors else COLORS["text"])
        self._preview_errors = all_errors
        self._preview_warnings = all_warnings
        return not all_errors and bool(all_rows)

    def export_issues(self) -> None:
        errors = getattr(self, "_preview_errors", [])
        warnings = getattr(self, "_preview_warnings", [])
        if not errors and not warnings:
            info(self, "当前没有错误或警告可导出")
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="导出导入问题清单", defaultextension=".csv",
            initialfile="导入问题清单.csv", filetypes=[("CSV 文件", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as fh:
            writer = csv.writer(fh)
            writer.writerow(["文件", "行号", "字段", "级别", "类型", "说明"])
            for e in errors:
                writer.writerow([e.get("file", ""), e.get("row", ""), e.get("field", ""), "错误", "", e.get("message", "")])
            for w in warnings:
                writer.writerow([w.get("file", ""), w.get("row", ""), w.get("field", ""), "警告", w.get("type", ""), w.get("message", "")])
        info(self, f"问题清单已导出：\n{path}")

    # ---------- 步骤 5 ----------
    def _build_step5(self, frame):
        tk.Label(frame, text="确认导入", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w", pady=(4, 6))
        self.confirm_summary = tk.Label(frame, text="", bg=COLORS["white"], fg=COLORS["text"],
                                        font=FONT_SMALL, justify="left", anchor="w", wraplength=900)
        self.confirm_summary.pack(fill="x", pady=(0, 8))
        tk.Label(frame, text="导入备注", bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(anchor="w")
        self.notes_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.notes_var).pack(fill="x", pady=(2, 10))
        self.duplicate_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="允许重复导入相同文件（仅用于确认重复数据场景）",
                        variable=self.duplicate_var).pack(anchor="w")
        self.duplicate_label = tk.Label(frame, text="", bg=COLORS["white"], fg=COLORS["warning"],
                                        font=FONT_SMALL, justify="left", anchor="w", wraplength=900)
        self.duplicate_label.pack(fill="x", pady=(8, 0))
        tk.Label(frame, text="确认后将保存原始文件归档、标准化数据行、导入记录和质量异常。原始导入记录不可覆盖。",
                 bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL, wraplength=900).pack(anchor="w", pady=(16, 0))

    def _prepare_confirm(self):
        lines = []
        total = 0
        for path in self.files:
            pv = self.previews.get(str(path))
            if not pv:
                continue
            s = pv.stats
            total += s.get("success_rows", 0)
            lines.append(f"{path.name}：{s.get('success_rows', 0)} 行，警告 {s.get('warning_rows', 0)} 条")
        self.confirm_summary.configure(text=f"将导入 {len(self.previews)} 个文件，共 {total} 行有效数据。\n" + "\n".join(lines))
        duplicates = []
        for path in self.files:
            dup = self.service.duplicate_import(self.page.app.current_batch_id, path)
            if dup:
                duplicates.append(f"{path.name} 已于 {human_dt(dup.get('imported_at'))} 导入（{dup['import_id']}）")
        self.duplicate_label.configure(text="\n".join(duplicates) if duplicates else "未发现重复文件。")
        self._duplicates = duplicates

    # ---------- 导航 ----------
    def show_step(self, index: int):
        self.step = index
        for frame in self.frames:
            frame.pack_forget()
        self.frames[index].pack(fill="both", expand=True)
        for i, (box, num, label) in enumerate(self.step_labels):
            if i == index:
                box.configure(bg=COLORS["accent_soft"])
                num.configure(bg=COLORS["accent"], fg="white")
                label.configure(bg=COLORS["accent_soft"], fg=COLORS["accent"], font=(FONT[0], 9, "bold"))
            elif i < index:
                box.configure(bg="#F0FDF4")
                num.configure(bg=COLORS["success"], fg="white")
                label.configure(bg="#F0FDF4", fg=COLORS["success"], font=(FONT[0], 9))
            else:
                box.configure(bg="#F1F5F9")
                num.configure(bg="#E2E8F0", fg=COLORS["muted"])
                label.configure(bg="#F1F5F9", fg=COLORS["muted"], font=(FONT[0], 9))
        self.back_btn.configure(state="normal" if index > 0 else "disabled")
        self.next_btn.configure(text="确认导入" if index == len(STEP_NAMES) - 1 else "下一步")
        self.status_label.configure(text="")

    def next_step(self):
        if self.step == 0:
            if not self.files:
                warning(self, "请至少添加一个文件")
                return
            if not self.first_table:
                self._load_first_table()
            self.show_step(1)
        elif self.step == 1:
            if not self.first_table:
                self._load_first_table()
            if not self.first_table:
                return
            self.show_step(2)
        elif self.step == 2:
            if self.map_vars["timestamp"].get() in ("", "（不导入）") or self.map_vars["pump_code"].get() in ("", "（不导入）"):
                warning(self, "必须映射时间戳和泵编号")
                return
            self.show_step(3)
            ok = self._build_previews()
            if not ok:
                self.status_label.configure(text="存在阻断错误，请返回字段映射或检查文件。", fg=COLORS["danger"])
        elif self.step == 3:
            if getattr(self, "_preview_errors", []):
                error(self, "存在阻断错误，不能继续")
                return
            self._prepare_confirm()
            self.show_step(4)
        else:
            self.commit()

    def prev_step(self):
        if self.step > 0:
            self.show_step(self.step - 1)

    def commit(self):
        if not getattr(self, "previews", {}):
            error(self, "没有可导入的数据")
            return
        if self._duplicates and not self.duplicate_var.get():
            error(self, "检测到重复文件。请勾选“允许重复导入”或移除重复文件。")
            return
        results = []
        failed = []
        for path in self.files:
            pv = self.previews.get(str(path))
            if not pv:
                continue
            try:
                import_id = self.service.commit(pv, self.page.app.current_batch_id, self.ctx.operator,
                                                notes=self.notes_var.get().strip(),
                                                allow_duplicate=self.duplicate_var.get())
                results.append((path.name, import_id))
                self.ctx.audit("导入剂量数据", "import_record", import_id,
                               after={"file": str(path), "rows": pv.stats.get("success_rows")})
            except Exception as exc:
                failed.append(f"{path.name}：{exc}")
        if results:
            message = "导入完成：\n" + "\n".join(f"{name} → {iid}" for name, iid in results)
            if failed:
                message += "\n\n部分文件失败：\n" + "\n".join(failed)
            info(self, message)
            self.destroy()
            self.page.refresh()
        else:
            error(self, "导入失败：\n" + "\n".join(failed))


class DoseImportPage(Page):
    key = "dose_import"
    title = "剂量导入"
    subtitle = "Dose Monitor 文件映射、质量检查与归档"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self._build()
        self.refresh()

    def _build(self):
        top = tk.Frame(self, bg=COLORS["bg"])
        top.pack(fill="x")
        ttk.Button(top, text="开始导入", style="Primary.TButton", command=self.open_wizard).pack(side="left")
        ttk.Button(top, text="刷新", style="Ghost.TButton", command=self.refresh).pack(side="left", padx=6)
        self.batch_hint = tk.Label(top, text="", bg=COLORS["bg"], fg=COLORS["muted"], font=FONT_SMALL)
        self.batch_hint.pack(side="right")

        history = Card(self, padding=12)
        history.pack(fill="x", pady=(10, 0))
        h = tk.Frame(history.body, bg=COLORS["white"])
        h.pack(fill="x")
        tk.Label(h, text="导入历史", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        self.history_table = DataTable(history.body, [
            ("import_id", "导入编号", 145), ("source_type", "来源", 90), ("original_filename", "文件", 220),
            ("batch_code", "批次", 110), ("imported_at", "导入时间", 140), ("row_count", "总行", 55),
            ("success_count", "成功", 55), ("error_count", "错误", 55), ("import_status", "状态", 80),
        ], height=5, id_key="import_id", on_select=self.select_import)
        self.history_table.pack(fill="x", pady=(6, 0))
        self.history_table.tree.bind("<Double-1>", lambda e: self.view_anomalies())

        detail = tk.Frame(self, bg=COLORS["bg"])
        detail.pack(fill="both", expand=True, pady=(10, 0))
        detail.grid_columnconfigure(0, weight=1)
        detail.grid_rowconfigure(1, weight=1)
        stats = Card(detail, padding=12)
        stats.grid(row=0, column=0, sticky="ew")
        self.stats_label = tk.Label(stats.body, text="选择一条导入记录查看标准化数据。", bg=COLORS["white"],
                                    fg=COLORS["muted"], font=FONT_SMALL, justify="left", anchor="w")
        self.stats_label.pack(fill="x")
        ttk.Button(stats.body, text="查看关联异常", style="Ghost.TButton",
                   command=self.view_anomalies).pack(side="right")
        data_card = Card(detail, padding=12)
        data_card.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        tk.Label(data_card.body, text="标准化数据预览（前 500 行）", bg=COLORS["white"], fg=COLORS["text"],
                 font=FONT_H3).pack(anchor="w")
        self.data_table = DataTable(data_card.body, [
            ("timestamp_utc", "时间", 145), ("pump_code", "泵", 90), ("flow_rate", "流速", 80),
            ("flow_unit", "单位", 70), ("total_volume", "累计体积", 95), ("volume_unit", "单位", 60),
            ("counter_segment", "区段", 55), ("quality_flags", "质量标记", 180),
        ], height=8)
        self.data_table.pack(fill="both", expand=True, pady=(6, 0))

    def on_show(self):
        self.refresh()

    def on_batch_changed(self):
        if self.winfo_exists():
            self.refresh()

    def refresh(self):
        batch = self.app.current_batch
        self.batch_hint.configure(text=f"当前批次：{batch['batch_code'] if batch else '未选择'}")
        batch_id = self.app.current_batch_id or ""
        rows = self.ctx.repos.imports.list_recent(batch_id, 300)
        self.history_table.set_rows(rows, "import_id")
        if rows:
            self.select_import(rows[0])
        else:
            self.stats_label.configure(text="该批次暂无导入记录。")
            self.data_table.clear()

    def select_import(self, row: dict):
        self.current_import = row
        stats = (f"导入编号：{row.get('import_id')}    来源：{row.get('source_type')}    文件：{row.get('original_filename')}\n"
                 f"时间：{human_dt(row.get('imported_at'))}    总行数：{row.get('row_count')}    "
                 f"成功：{row.get('success_count')}    错误：{row.get('error_count')}    状态：{row.get('import_status')}")
        self.stats_label.configure(text=stats)
        if row.get("source_type") == "Dose Monitor":
            data = self.ctx.repos.imports.normalized(row["import_id"])
            self.data_table.set_rows(data[:500])

    def view_anomalies(self):
        self.app.go("anomaly")

    def open_wizard(self):
        batch_id = self.app.require_batch()
        if not batch_id:
            return
        DoseImportWizard(self, self)
