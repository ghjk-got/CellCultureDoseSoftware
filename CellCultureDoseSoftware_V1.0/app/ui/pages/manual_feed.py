# -*- coding: utf-8 -*-
"""手工记录屏幕读数；所有输入及异常均原样保存以便复核。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, simpledialog

from ..widgets import error, info


class ManualFeedWindow(tk.Toplevel):
    def __init__(self, page):
        super().__init__(page)
        self.page, self.ctx = page, page.ctx
        self.batch_id = page.app.current_batch_id
        self.selected_record = None
        self.title("手工补料记录")
        self.geometry("1050x740")
        self.transient(page.winfo_toplevel())
        self.vars = {k: tk.StringVar() for k in ("pump", "liquid", "event", "start_time", "end_time", "start_reading", "end_reading", "reading_unit", "measured_value", "measured_unit", "measured_method", "equipment_notes", "notes")}
        self.pumps = {f"{p['pump_code']} · {p['pump_name']}": p['pump_id'] for p in self.ctx.repos.pumps.active()}
        self.liquids = {f"{v['liquid_code']} · {v['liquid_name']}": v['liquid_id'] for v in self.ctx.repos.liquids.active()}
        if len(self.pumps) == 1:
            self.vars['pump'].set(next(iter(self.pumps)))
        if len(self.liquids) == 1:
            self.vars['liquid'].set(next(iter(self.liquids)))
        if self.ctx.db.get_setting('initial_setup') == 'complete':
            self.vars['reading_unit'].set(self.ctx.settings.default_volume_unit)
        self.events = {}
        plans = self.ctx.db.q("SELECT plan_id, version_no FROM feed_plan WHERE batch_id=? ORDER BY version_no DESC", (self.batch_id,))
        for plan in plans:
            for e in self.ctx.repos.plans.events(plan['plan_id']):
                self.events[f"V{plan['version_no']} · {e['event_id']} · {e.get('liquid_name') or ''} · {e.get('planned_start') or ''}"] = e
        tk.Label(self, text="屏幕值为设备估算；请确认泵与执行器的对应关系和校准状态。时间格式：YYYY-MM-DD HH:MM", anchor="w").pack(fill="x", padx=12, pady=6)
        form = ttk.Frame(self, padding=8)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        def entry(row, col, label, key, choices=None):
            ttk.Label(form, text=label).grid(row=row, column=col, sticky="w", padx=4, pady=3)
            widget = (ttk.Combobox(form, textvariable=self.vars[key], values=choices, state="readonly") if choices is not None else ttk.Entry(form, textvariable=self.vars[key]))
            widget.grid(row=row, column=col + 1, sticky="ew", padx=4, pady=3)
            return widget
        self.pump_combo = entry(0, 0, "泵 *", "pump", list(self.pumps))
        self.liquid_combo = entry(0, 2, "补料液 *", "liquid", list(self.liquids))
        combo = entry(1, 0, "关联计划事件", "event", ["（计划外）"] + list(self.events))
        combo.bind("<<ComboboxSelected>>", self._event_changed)
        self.vars['event'].set("（计划外）")
        entry(1, 2, "累计读数单位 *", "reading_unit", ["mL", "L"])
        entry(2, 0, "开始时间", "start_time")
        entry(2, 2, "开始读数", "start_reading")
        entry(3, 0, "结束时间", "end_time")
        entry(3, 2, "结束读数", "end_reading")
        entry(4, 0, "独立实测量（可选）", "measured_value")
        entry(4, 2, "实测单位", "measured_unit", ["", "mL", "L"])
        entry(5, 0, "实测方法", "measured_method")
        entry(5, 2, "泵及连接/校准信息", "equipment_notes")
        entry(6, 0, "备注", "notes")
        self.known_reset = tk.BooleanVar(value=False)
        ttk.Checkbutton(form, text="本次期间已知发生归零", variable=self.known_reset).grid(row=6, column=2, columnspan=2, sticky="w")
        ttk.Label(form, text="中途读数（每行：时间,读数）").grid(row=7, column=0, sticky="nw", padx=4)
        self.intermediate = tk.Text(form, height=3, width=35)
        self.intermediate.grid(row=7, column=1, columnspan=3, sticky="ew", padx=4)
        self.optional_visible = False
        self.optional_widgets = [widget for widget in form.grid_slaves() if int(widget.grid_info()["row"]) in (4, 5, 6, 7)]
        for widget in self.optional_widgets:
            widget.grid_remove()
        ttk.Button(form, text="补充信息", command=self.toggle_optional).grid(row=8, column=0, sticky="w", pady=6)
        buttons = ttk.Frame(form)
        buttons.grid(row=8, column=1, columnspan=3, sticky="w", pady=6)
        ttk.Button(buttons, text="开始补料", command=lambda: self.save(start_only=True)).pack(side="left", padx=3)
        ttk.Button(buttons, text="保存完整记录", command=self.save).pack(side="left", padx=3)
        ttk.Button(buttons, text="载入所选记录", command=self.load_selected).pack(side="left", padx=3)
        ttk.Button(buttons, text="保存结束 / 更正", command=self.save_existing).pack(side="left", padx=3)
        ttk.Button(buttons, text="标记未完成", command=self.mark_incomplete).pack(side="left", padx=3)
        ttk.Label(self, text="手工记录历史：双击查看原始读数与审核原因").pack(anchor="w", padx=12)
        self.tree = ttk.Treeview(self, columns=("pump", "liquid", "start", "end", "estimate", "measured", "status"), show="headings", height=7)
        for key, label, width in (("pump", "泵", 90), ("liquid", "液体", 100), ("start", "开始", 150), ("end", "结束", 150), ("estimate", "设备估算 mL", 110), ("measured", "独立实测 mL", 110), ("status", "状态", 90)):
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width)
        self.tree.pack(fill="both", expand=True, padx=12, pady=6)
        self.tree.bind("<Double-1>", self.show_record)
        self.refresh()

    def _event_changed(self, _event=None):
        event = self.events.get(self.vars['event'].get())
        if event:
            for key, mapping, field in (("pump", self.pumps, "pump_id"), ("liquid", self.liquids, "liquid_id")):
                self.vars[key].set(next((label for label, value in mapping.items() if value == event[field]), ""))

    def toggle_optional(self):
        self.optional_visible = not self.optional_visible
        for widget in self.optional_widgets:
            widget.grid() if self.optional_visible else widget.grid_remove()

    def _data(self):
        data = {k: v.get().strip() for k, v in self.vars.items()}
        data.update(batch_id=self.batch_id, pump_id=self.pumps.get(data.pop('pump')),
                    liquid_id=self.liquids.get(data.pop('liquid')),
                    event_id=(self.events.get(data.pop('event')) or {}).get('event_id'),
                    known_reset=self.known_reset.get(),
                    intermediate_readings=self.intermediate.get('1.0', 'end').strip())
        return data

    def save(self, start_only=False):
        data = self._data()
        try:
            record_id = self.ctx.manual_feed.save(data, self.ctx.operator, start_only=start_only)
        except (ValueError, KeyError) as exc:
            error(self, str(exc))
            return
        self.ctx.audit("保存手工补料记录", "manual_feed_record", record_id)
        self.refresh()
        info(self, "开始记录已保存，结束后选择记录并补填。" if start_only else "已保存。存在缺失、无效读数或可能归零时会标记为待审核。")

    def load_selected(self):
        selected = self.tree.selection()
        if not selected:
            info(self, "请先选择一条记录")
            return
        row = self.records[selected[0]]
        self.selected_record = row['record_id']
        for key in self.vars:
            if key in row:
                self.vars[key].set(str(row[key] or ""))
        for key, mapping, field in (("pump", self.pumps, "pump_id"), ("liquid", self.liquids, "liquid_id")):
            if row[field] not in mapping.values():
                label = (row['pump_code'] if key == 'pump' else row['liquid_name']) + ' · 已停用'
                mapping[label] = row[field]
                (self.pump_combo if key == 'pump' else self.liquid_combo).configure(values=list(mapping))
            self.vars[key].set(next((label for label, value in mapping.items() if value == row[field]), ""))
        self.vars['event'].set(next((label for label, event in self.events.items() if event['event_id'] == row['event_id']), "（计划外）"))
        self.known_reset.set(bool(row['known_reset']))
        self.intermediate.delete('1.0', 'end')
        self.intermediate.insert('1.0', row['intermediate_readings'] or '')
        self.title(f"补料记录：{row['record_id']}（{row['lifecycle_status']}）")

    def save_existing(self):
        if not self.selected_record:
            info(self, "请先载入所选记录")
            return
        row = self.records[self.selected_record]
        data = self._data()
        if any(data.get(k) != row.get(k) for k in ('pump_id', 'liquid_id', 'event_id')):
            error(self, "已保存记录的泵、液体和关联事件不能在此更改，请恢复原选择。")
            return
        operator = simpledialog.askstring("操作人", "请输入操作人：", initialvalue=self.ctx.operator, parent=self)
        if not operator:
            return
        reason = ""
        if row['lifecycle_status'] != '进行中':
            reason = simpledialog.askstring("更正原因", "请输入更正原因：", parent=self) or ""
            if not reason.strip():
                return
        try:
            self.ctx.manual_feed.update_record(self.selected_record, data, operator, reason)
        except ValueError as exc:
            error(self, str(exc))
            return
        self.refresh()
        info(self, "记录已更新，原记录和修改人已保留。")

    def mark_incomplete(self):
        selected = self.tree.selection()
        if not selected:
            info(self, "请先选择进行中的记录")
            return
        reason = simpledialog.askstring("未完成原因", "请输入未完成原因：", parent=self)
        if not reason:
            return
        try:
            self.ctx.manual_feed.mark_incomplete(selected[0], self.ctx.operator, reason)
        except ValueError as exc:
            error(self, str(exc))
            return
        self.refresh()

    def refresh(self):
        self.records = {r['record_id']: r for r in self.ctx.manual_feed.list_for_batch(self.batch_id)}
        self.tree.delete(*self.tree.get_children())
        for key, row in self.records.items():
            self.tree.insert('', 'end', iid=key, values=(row['pump_code'], row['liquid_name'], row['start_time'], row['end_time'], row['estimate_ml'] if row['estimate_ml'] is not None else '未计算', row['measured_ml'] if row['measured_ml'] is not None else '未记录', row['lifecycle_status'] if row['lifecycle_status'] != '已完成' else row['quality_status']))

    def show_record(self, _event=None):
        selection = self.tree.selection()
        if not selection:
            return
        row = self.records[selection[0]]
        planned = row['planned_volume_ml']
        estimate = row['estimate_ml']
        measured = row['measured_ml']
        estimated_diff = estimate - planned if estimate is not None and planned is not None else '不适用'
        measured_diff = measured - planned if measured is not None and planned is not None else '不适用'
        revisions = self.ctx.db.q("SELECT action,operator,created_at,reason,before_json,after_json FROM manual_feed_revision WHERE record_id=? ORDER BY created_at", (row['record_id'],))
        history = "\n".join(f"{r['created_at']} {r['operator']} {r['action']}：{r['reason']}\n修改前：{r['before_json']}\n修改后：{r['after_json']}" for r in revisions) or "无"
        info(self, f"起止读数：{row['start_reading']} → {row['end_reading']} {row['reading_unit']}\n中途读数：{row['intermediate_readings'] or '无'}\n计划量：{planned if planned is not None else '未关联'} mL\n设备估算量：{estimate if estimate is not None else '未计算'} mL；与计划差值：{estimated_diff}\n独立实测量：{measured if measured is not None else '未记录'} mL；与计划差值：{measured_diff}\n独立实测方法：{row['measured_method'] or '未记录'}\n审核原因：{row['issues']}\n设备信息：{row['equipment_notes']}\n备注：{row['notes']}\n更正历史：{history}")
