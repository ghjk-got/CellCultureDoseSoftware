# -*- coding: utf-8 -*-
"""补料计划：计划版本、补料事件、时间冲突与累计量。"""
from __future__ import annotations

from datetime import datetime

import tkinter as tk
from tkinter import ttk

from ...db import now_iso
from ...services.plan_calc import duration_h, end_time, find_conflicts, summarize
from ..base import Page
from ..theme import COLORS, FONT, FONT_H3, FONT_SMALL
from ..widgets import Card, DataTable, FormDialog, badge, confirm, error, fmt_num, info


class FeedPlanPage(Page):
    key = "plan"
    title = "补料计划"
    subtitle = "计划版本、补料事件、时间冲突与累计量"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.plan_map: dict[str, str] = {}
        self.current_plan: dict | None = None
        self._build()
        self.refresh()

    def _build(self):
        top = tk.Frame(self, bg=COLORS["bg"])
        top.pack(fill="x")
        tk.Label(top, text="计划版本", bg=COLORS["bg"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="left")
        self.plan_var = tk.StringVar()
        self.plan_combo = ttk.Combobox(top, textvariable=self.plan_var, state="readonly", width=32)
        self.plan_combo.pack(side="left", padx=8)
        self.plan_combo.bind("<<ComboboxSelected>>", lambda e: self._select_plan())
        ttk.Button(top, text="新建版本", style="Primary.TButton", command=self.new_version).pack(side="left")
        ttk.Button(top, text="确认计划", style="Success.TButton", command=self.confirm_plan).pack(side="left", padx=6)
        self.status_label = tk.Label(top, text="—", bg="#F1F5F9", fg=COLORS["muted"], font=(FONT[0], 9, "bold"),
                                     padx=10, pady=4)
        self.status_label.pack(side="left", padx=10)
        ttk.Button(top, text="刷新", style="Ghost.TButton", command=self.refresh).pack(side="right")

        cards = tk.Frame(self, bg=COLORS["bg"])
        cards.pack(fill="x", pady=(12, 0))
        for i in range(4):
            cards.grid_columnconfigure(i, weight=1, uniform="sum")
        self.summary_values = {}
        for idx, (key, title, color) in enumerate((
                ("count", "补料事件", COLORS["accent"]), ("total", "计划累计量 (mL)", COLORS["success"]),
                ("liquids", "涉及液体", COLORS["purple"]), ("conflicts", "泵时间冲突", COLORS["warning"]))):
            card = Card(cards, padding=14)
            card.grid(row=0, column=idx, sticky="nsew", padx=(0 if idx == 0 else 8, 0))
            tk.Label(card.body, text=title, bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(anchor="w")
            value = tk.Label(card.body, text="—", bg=COLORS["white"], fg=color, font=(FONT[0], 20, "bold"))
            value.pack(anchor="w", pady=(4, 0))
            self.summary_values[key] = value

        main = tk.Frame(self, bg=COLORS["bg"])
        main.pack(fill="both", expand=True, pady=(12, 0))
        main.grid_columnconfigure(0, weight=3, minsize=560)
        main.grid_columnconfigure(1, weight=1, minsize=230)
        main.grid_rowconfigure(0, weight=1)

        events_card = Card(main, padding=12)
        events_card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        h = tk.Frame(events_card.body, bg=COLORS["white"])
        h.pack(fill="x")
        tk.Label(h, text="补料事件", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(side="left")
        ttk.Button(h, text="新增事件", style="Primary.TButton", command=self.add_event).pack(side="right")
        ttk.Button(h, text="编辑", style="Secondary.TButton", command=self.edit_event).pack(side="right", padx=6)
        ttk.Button(h, text="删除", style="Ghost.TButton", command=self.delete_event).pack(side="right")
        self.event_table = DataTable(events_card.body, [
            ("stage_name", "阶段", 60), ("liquid_name", "液体", 90), ("pump_code", "泵", 75),
            ("planned_start", "计划开始", 130), ("planned_end", "计划结束", 130),
            ("planned_volume_ml", "计划量(mL)", 80), ("target_flow_ml_h", "流速(mL/h)", 80),
        ], height=13, id_key="event_id")
        self.event_table.pack(fill="both", expand=True, pady=(8, 0))
        self.event_table.tree.bind("<Double-1>", lambda e: self.edit_event())

        side = tk.Frame(main, bg=COLORS["bg"])
        side.grid(row=0, column=1, sticky="nsew")
        summary_card = Card(side, padding=14)
        summary_card.pack(fill="x")
        tk.Label(summary_card.body, text="液体累计量", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w")
        self.liquid_summary = tk.Label(summary_card.body, text="—", bg=COLORS["white"], fg=COLORS["text"],
                                       font=FONT_SMALL, justify="left", anchor="w", wraplength=240)
        self.liquid_summary.pack(fill="x", pady=(8, 0))

        conflict_card = Card(side, padding=14)
        conflict_card.pack(fill="both", expand=True, pady=(12, 0))
        tk.Label(conflict_card.body, text="计划检查", bg=COLORS["white"], fg=COLORS["text"], font=FONT_H3).pack(anchor="w")
        self.conflict_text = tk.Label(conflict_card.body, text="—", bg=COLORS["white"], fg=COLORS["muted"],
                                      font=FONT_SMALL, justify="left", anchor="nw", wraplength=240)
        self.conflict_text.pack(fill="both", expand=True, pady=(8, 0))

    # ---------- 刷新 ----------
    def on_show(self):
        self.refresh()

    def on_batch_changed(self):
        if self.winfo_exists():
            self.refresh()

    def refresh(self):
        batch_id = self.app.current_batch_id
        self.plan_map = {}
        if not batch_id:
            self.plan_combo.configure(values=[])
            self.plan_var.set("")
            self.current_plan = None
            self.event_table.clear()
            self._update_summary([])
            self.set_status("请先选择批次")
            return
        plans = self.ctx.repos.plans.plans_for_batch(batch_id)
        labels = []
        for p in plans:
            label = f"V{p['version_no']}  {p['status']}  {p.get('created_at', '')[:16]}"
            labels.append(label)
            self.plan_map[label] = p["plan_id"]
        self.plan_combo.configure(values=labels)
        if not labels:
            self.plan_var.set("")
            self.current_plan = None
            self.event_table.clear()
            self._update_summary([])
            self.conflict_text.configure(text="尚未创建补料计划。点击“新建版本”开始。", fg=COLORS["muted"])
            return
        if self.plan_var.get() not in self.plan_map:
            self.plan_var.set(labels[0])
        self._select_plan()

    def _select_plan(self):
        plan_id = self.plan_map.get(self.plan_var.get())
        if not plan_id:
            return
        self.current_plan = self.ctx.repos.plans.get(plan_id)
        if not self.current_plan:
            return
        status = self.current_plan["status"]
        self.status_label.configure(text=f"  {status}  ")
        self.status_label.configure(bg=COLORS["success_soft"] if status == "已确认" else COLORS["warning_soft"],
                                    fg=COLORS["success"] if status == "已确认" else COLORS["warning"])
        events = self.ctx.repos.plans.events(plan_id)
        self.event_table.set_rows(events, "event_id")
        self._update_summary(events)

    def _update_summary(self, events):
        self.summary_values["count"].configure(text=str(len(events)))
        total = sum(float(e.get("planned_volume_ml") or 0) for e in events)
        self.summary_values["total"].configure(text=fmt_num(total))
        summaries = summarize(events)
        self.summary_values["liquids"].configure(text=str(len(summaries)))
        conflicts = find_conflicts(events)
        self.summary_values["conflicts"].configure(text=str(len(conflicts)))
        if summaries:
            self.liquid_summary.configure(text="\n".join(
                f"{s['liquid_name'] or s['liquid_id']}：{fmt_num(s['volume_ml'])} mL / {s['events']} 次" for s in summaries))
        else:
            self.liquid_summary.configure(text="—")
        if conflicts:
            self.conflict_text.configure(text="\n\n".join(conflicts), fg=COLORS["warning"])
        elif events:
            self.conflict_text.configure(text="未发现同一泵的时间重叠。\n请同时确认泵已绑定正确液体。", fg=COLORS["success"])
        else:
            self.conflict_text.configure(text="暂无补料事件。", fg=COLORS["muted"])

    # ---------- 计划版本 ----------
    def new_version(self):
        batch_id = self.app.current_batch_id
        if not batch_id:
            info(self, "请先选择批次")
            return
        latest = self.ctx.repos.plans.latest(batch_id)
        intro = "将复制上一版本的事件作为新草稿。" if latest else "这是该批次的第一个补料计划。"
        dialog = FormDialog(self, "新建补料计划版本", [
            {"key": "notes", "label": "版本说明", "type": "multiline", "lines": 3},
        ], width=520, intro=intro).show()
        if dialog is None:
            return
        pid = self.ctx.repos.plans.create(batch_id, self.ctx.operator, copy_latest=bool(latest), notes=dialog["notes"])
        self.ctx.audit("新建补料计划版本", "feed_plan", pid)
        self.plan_var.set("")
        self.refresh()
        self.set_status("已创建补料计划草稿")

    def confirm_plan(self):
        if not self.current_plan:
            info(self, "请先新建或选择计划版本")
            return
        events = self.ctx.repos.plans.events(self.current_plan["plan_id"])
        if not events:
            error(self, "计划没有补料事件")
            return
        conflicts = find_conflicts(events)
        text = "确认该计划版本？确认后应通过新版本修改。"
        if conflicts:
            text = "检测到以下冲突：\n\n" + "\n".join(conflicts) + "\n\n仍要确认计划？"
        if not confirm(self, "确认补料计划", text):
            return
        self.ctx.repos.plans.set_status(self.current_plan["plan_id"], "已确认")
        self.ctx.audit("确认补料计划", "feed_plan", self.current_plan["plan_id"])
        self._select_plan()
        self.set_status("补料计划已确认")

    # ---------- 事件 ----------
    def _dialog_fields(self, row: dict | None = None):
        batch_id = self.app.current_batch_id
        stages = self.ctx.repos.batches.stages(batch_id) if batch_id else []
        liquids = self.ctx.repos.liquids.active()
        pumps = self.ctx.repos.pumps.active()
        stage_default = next((s["stage_name"] for s in stages if row and s["stage_id"] == row.get("stage_id")),
                             stages[0]["stage_name"] if stages else "")
        liquid_default = next((f"{l['liquid_code']} · {l['liquid_name']}" for l in liquids
                               if row and l["liquid_id"] == row.get("liquid_id")), "")
        pump_default = next((f"{p['pump_code']} · {p['pump_name']}" for p in pumps
                             if row and p["pump_id"] == row.get("pump_id")), "")
        return [
            {"key": "stage_id", "label": "工艺阶段", "type": "combo",
             "choices": [{"label": s["stage_name"], "value": s["stage_id"]} for s in stages],
             "default": stage_default},
            {"key": "liquid_id", "label": "补料液体", "type": "combo", "required": True,
             "choices": [{"label": f"{l['liquid_code']} · {l['liquid_name']}", "value": l["liquid_id"]} for l in liquids],
             "default": liquid_default},
            {"key": "pump_id", "label": "泵", "type": "combo", "required": True,
             "choices": [{"label": f"{p['pump_code']} · {p['pump_name']}", "value": p["pump_id"]} for p in pumps],
             "default": pump_default},
            {"key": "planned_start", "label": "计划开始时间", "type": "date", "required": True,
             "default": row.get("planned_start") if row else now_iso()},
            {"key": "planned_end", "label": "计划结束时间", "type": "date", "default": row.get("planned_end") if row else ""},
            {"key": "planned_volume_ml", "label": "单次计划量 (mL)", "type": "number", "required": True,
             "default": row.get("planned_volume_ml") if row else ""},
            {"key": "target_flow_ml_h", "label": "目标流速 (mL/h)", "type": "number", "required": True,
             "default": row.get("target_flow_ml_h") if row else ""},
            {"key": "duration_h", "label": "预计时长 (h)", "type": "number", "default": row.get("duration_h") if row else "",
             "help": "留空时按计划量 ÷ 目标流速自动计算"},
            {"key": "status", "label": "事件状态", "type": "combo", "values": ["计划", "执行中", "已完成", "取消"],
             "default": row.get("status") if row else "计划"},
            {"key": "notes", "label": "备注", "type": "multiline", "lines": 2, "default": row.get("notes") if row else ""},
        ]

    def _normalize_event(self, values: dict) -> dict | None:
        try:
            volume = float(values.get("planned_volume_ml") or 0)
            flow = float(values.get("target_flow_ml_h") or 0)
        except (TypeError, ValueError):
            error(self, "计划量和目标流速必须是有效数字")
            return None
        if volume <= 0 or flow <= 0:
            error(self, "计划量和目标流速必须大于 0")
            return None
        duration = values.get("duration_h")
        try:
            duration = float(duration) if duration not in (None, "") else None
        except (TypeError, ValueError):
            duration = None
        if duration is None or duration <= 0:
            duration = duration_h(volume, flow)
        values["duration_h"] = duration
        start = values.get("planned_start")
        if not values.get("planned_end") and start and duration:
            values["planned_end"] = end_time(start, duration)
        if not duration and start and values.get("planned_end"):
            try:
                a = datetime.fromisoformat(start)
                b = datetime.fromisoformat(values["planned_end"])
                values["duration_h"] = (b - a).total_seconds() / 3600.0
            except ValueError:
                pass
        return values

    def add_event(self):
        if not self.current_plan:
            info(self, "请先新建补料计划版本")
            return
        if self.current_plan["status"] == "已确认":
            error(self, "已确认的计划不能直接修改，请创建新版本")
            return
        dialog = FormDialog(self, "新增补料事件", self._dialog_fields(), width=620,
                            intro="计划时间窗口用于实际剂量核算；同一泵的时间不应重叠。")
        values = dialog.show()
        if not values:
            return
        values = self._normalize_event(values)
        if not values:
            return
        eid = self.ctx.repos.plans.add_event(self.current_plan["plan_id"], values)
        self.ctx.audit("新增补料事件", "feed_plan_event", eid, after=values)
        self._select_plan()
        self.set_status("补料事件已添加")

    def edit_event(self):
        row = self.event_table.selected_row()
        if not row:
            info(self, "请先选择补料事件")
            return
        if self.current_plan and self.current_plan["status"] == "已确认":
            error(self, "已确认的计划不能直接修改，请创建新版本")
            return
        dialog = FormDialog(self, "编辑补料事件", self._dialog_fields(row), width=620)
        values = dialog.show()
        if not values:
            return
        values = self._normalize_event(values)
        if not values:
            return
        self.ctx.repos.plans.update_event(row["event_id"], values)
        self.ctx.audit("修改补料事件", "feed_plan_event", row["event_id"], before=row, after=values)
        self._select_plan()
        self.set_status("补料事件已更新")

    def delete_event(self):
        row = self.event_table.selected_row()
        if not row:
            return
        if self.current_plan and self.current_plan["status"] == "已确认":
            error(self, "已确认的计划不能直接删除事件，请创建新版本")
            return
        if confirm(self, "删除事件", f"删除 {row.get('liquid_name')} / {row.get('pump_code')} 的补料事件？"):
            self.ctx.repos.plans.delete_event(row["event_id"])
            self._select_plan()
