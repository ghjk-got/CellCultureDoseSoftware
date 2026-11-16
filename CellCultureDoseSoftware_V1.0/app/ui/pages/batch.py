# -*- coding: utf-8 -*-
"""批次管理：批次档案、培养阶段、参数与泵-液体绑定。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ...db import now_iso
from ..base import Page
from ..theme import COLORS, FONT, FONT_H3, FONT_SMALL
from ..widgets import Card, DataTable, FormDialog, confirm, error, human_dt, info


class BatchPage(Page):
    key = "batch"
    title = "批次管理"
    subtitle = "批次档案、培养阶段、参数与泵-液体绑定"

    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.current_id: str | None = None
        self._build()
        self.refresh()

    def _build(self):
        top = tk.Frame(self, bg=COLORS["bg"])
        top.pack(fill="x")
        ttk.Button(top, text="新建批次", style="Primary.TButton", command=self.new_batch).pack(side="left")
        ttk.Button(top, text="编辑批次", style="Secondary.TButton", command=self.edit_batch).pack(side="left", padx=6)
        ttk.Button(top, text="刷新", style="Ghost.TButton", command=self.refresh).pack(side="left")
        self.search_var = tk.StringVar()
        entry = ttk.Entry(top, textvariable=self.search_var, width=24)
        entry.pack(side="right")
        entry.bind("<Return>", lambda e: self.refresh())
        tk.Label(top, text="搜索批次", bg=COLORS["bg"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="right", padx=6)

        list_card = Card(self, padding=12)
        list_card.pack(fill="x", pady=(10, 0))
        self.table = DataTable(list_card.body, [
            ("batch_code", "批次编号", 135), ("project_name", "项目", 150),
            ("culture_system", "培养体系", 80), ("reactor_code", "反应器", 70),
            ("working_volume_ml", "工作体积(mL)", 95), ("status", "状态", 65),
            ("start_time", "开始时间", 120),
        ], height=4, id_key="batch_id", on_select=self._select_batch)
        self.table.pack(fill="x")
        self.table.tree.bind("<Double-1>", lambda e: self.edit_batch())

        detail = tk.Frame(self, bg=COLORS["bg"])
        detail.pack(fill="both", expand=True, pady=(10, 0))
        self.detail_title = tk.Label(detail, text="批次详情", bg=COLORS["bg"], fg=COLORS["text"], font=(FONT[0], 13, "bold"))
        self.detail_title.pack(anchor="w", pady=(0, 6))
        self.notebook = ttk.Notebook(detail)
        self.notebook.pack(fill="both", expand=True)

        # 基本信息
        info_tab = tk.Frame(self.notebook, bg=COLORS["white"])
        self.notebook.add(info_tab, text="基本信息")
        self.info_labels = {}
        grid = tk.Frame(info_tab, bg=COLORS["white"])
        grid.pack(fill="both", expand=True, padx=18, pady=16)
        keys = [("batch_code", "批次编号"), ("project_name", "项目名称"), ("culture_system", "培养体系"),
                ("reactor_code", "反应器"), ("working_volume_ml", "工作体积 (mL)"), ("status", "状态"),
                ("start_time", "开始时间"), ("end_time", "结束时间"), ("created_by", "创建人"),
                ("created_at", "创建时间"), ("notes", "备注")]
        for i, (key, label) in enumerate(keys):
            row, col = divmod(i, 3)
            box = tk.Frame(grid, bg=COLORS["white"])
            box.grid(row=row, column=col, sticky="ew", padx=(0, 24), pady=5)
            tk.Label(box, text=label, bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(anchor="w")
            value = tk.Label(box, text="—", bg=COLORS["white"], fg=COLORS["text"], font=(FONT[0], 10))
            value.pack(anchor="w")
            grid.grid_columnconfigure(col, weight=1)
            self.info_labels[key] = value

        # 阶段
        stage_tab = tk.Frame(self.notebook, bg=COLORS["white"])
        self.notebook.add(stage_tab, text="培养阶段")
        bar = tk.Frame(stage_tab, bg=COLORS["white"])
        bar.pack(fill="x", padx=12, pady=8)
        ttk.Button(bar, text="新增阶段", style="Primary.TButton", command=self.add_stage).pack(side="left")
        ttk.Button(bar, text="编辑", style="Secondary.TButton", command=self.edit_stage).pack(side="left", padx=6)
        ttk.Button(bar, text="删除", style="Ghost.TButton", command=self.delete_stage).pack(side="left")
        self.stage_table = DataTable(stage_tab, [
            ("stage_name", "阶段", 160), ("start_time", "开始", 160), ("end_time", "结束", 160),
            ("notes", "说明", 300),
        ], height=7, id_key="stage_id")
        self.stage_table.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # 参数
        param_tab = tk.Frame(self.notebook, bg=COLORS["white"])
        self.notebook.add(param_tab, text="培养参数")
        bar2 = tk.Frame(param_tab, bg=COLORS["white"])
        bar2.pack(fill="x", padx=12, pady=8)
        ttk.Button(bar2, text="记录参数", style="Primary.TButton", command=self.add_parameter).pack(side="left")
        ttk.Button(bar2, text="删除", style="Ghost.TButton", command=self.delete_parameter).pack(side="left", padx=6)
        self.param_table = DataTable(param_tab, [
            ("recorded_at", "记录时间", 160), ("stage_name", "阶段", 120), ("param_name", "参数", 140),
            ("param_value", "数值", 90), ("unit", "单位", 80), ("notes", "备注", 260),
        ], height=7, id_key="param_id")
        self.param_table.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # 泵映射
        map_tab = tk.Frame(self.notebook, bg=COLORS["white"])
        self.notebook.add(map_tab, text="泵 - 液体绑定")
        bar3 = tk.Frame(map_tab, bg=COLORS["white"])
        bar3.pack(fill="x", padx=12, pady=8)
        ttk.Button(bar3, text="新增绑定", style="Primary.TButton", command=self.add_mapping).pack(side="left")
        ttk.Button(bar3, text="解除绑定", style="Ghost.TButton", command=self.delete_mapping).pack(side="left", padx=6)
        tk.Label(bar3, text="同一设备泵可在不同批次绑定不同液体；历史批次不受主数据修改影响。",
                 bg=COLORS["white"], fg=COLORS["muted"], font=FONT_SMALL).pack(side="right")
        self.map_table = DataTable(map_tab, [
            ("pump_code", "泵", 100), ("pump_name", "泵名称", 130), ("liquid_code", "液体代码", 100),
            ("liquid_name", "液体名称", 150), ("valid_from", "生效时间", 150), ("valid_to", "失效时间", 150),
            ("mapping_note", "说明", 200),
        ], height=7, id_key="mapping_id")
        self.map_table.pack(fill="both", expand=True, padx=12, pady=(0, 12))

    # ---------- 列表 ----------
    def on_show(self):
        self.refresh()

    def on_batch_changed(self):
        if not self.winfo_exists():
            return
        self.refresh(select_id=self.app.current_batch_id)

    def refresh(self, select_id: str | None = None):
        rows = self.ctx.repos.batches.list_with_reactor(self.search_var.get().strip())
        self.table.set_rows(rows, "batch_id")
        target = select_id or self.current_id or self.app.current_batch_id
        if target:
            self.table.select_by_id(target)
        if rows and not self.table.selected_row():
            self.table.tree.selection_set(self.table.tree.get_children()[0])

    def _select_batch(self, row: dict):
        self.current_id = row["batch_id"]
        self.ctx.settings.last_batch_id = row["batch_id"]
        self.ctx.settings.save()
        if hasattr(self.app, "batch_ids"):
            self.app.batch_var.set(self.app.batch_ids.get(row["batch_id"], ""))
        self._load_detail(row)

    def _load_detail(self, row: dict):
        self.detail_title.configure(text=f"批次详情 · {row['batch_code']}")
        for key, label in self.info_labels.items():
            value = row.get(key)
            if key.endswith("_time") or key.endswith("_at"):
                value = human_dt(value)
            label.configure(text=value if value not in (None, "") else "—")
        self.stage_table.set_rows(self.ctx.repos.batches.stages(row["batch_id"]), "stage_id")
        self.param_table.set_rows(self.ctx.repos.batches.parameters(row["batch_id"]), "param_id")
        self.map_table.set_rows(self.ctx.repos.batches.mappings(row["batch_id"]), "mapping_id")

    # ---------- 批次 ----------
    def _reactor_choices(self):
        return [{"label": f"{r['reactor_code']} · {r['reactor_name']}", "value": r["reactor_id"]}
                for r in self.ctx.repos.reactors.active()]

    def _batch_fields(self, row: dict | None = None):
        reactors = self._reactor_choices()
        current = row.get("reactor_code") if row else ""
        default_reactor = next((c["label"] for c in reactors if c["label"].startswith(str(current))), "") if current else (reactors[0]["label"] if reactors else "")
        return [
            {"key": "batch_code", "label": "批次编号", "required": True, "default": row.get("batch_code") if row else ""},
            {"key": "project_name", "label": "项目名称", "default": row.get("project_name") if row else ""},
            {"key": "culture_system", "label": "培养体系", "type": "combo", "values": ["CHO", "HEK293", "Vero", "其他"],
             "default": row.get("culture_system") if row else "CHO"},
            {"key": "reactor_id", "label": "反应器", "type": "combo", "choices": reactors, "default": default_reactor},
            {"key": "working_volume_ml", "label": "工作体积 (mL)", "type": "number",
             "default": row.get("working_volume_ml") if row else 3000},
            {"key": "start_time", "label": "开始时间", "type": "date",
             "default": row.get("start_time") if row else now_iso()},
            {"key": "end_time", "label": "结束时间", "type": "date", "default": row.get("end_time") if row else ""},
            {"key": "status", "label": "状态", "type": "combo", "values": ["进行中", "已完成", "已关闭", "草稿"],
             "default": row.get("status") if row else "进行中"},
            {"key": "notes", "label": "备注", "type": "multiline", "lines": 3, "default": row.get("notes") if row else ""},
        ]

    def new_batch(self):
        dialog = FormDialog(self, "新建培养批次", self._batch_fields(), width=600,
                            intro="批次编号应唯一；创建后会自动生成“接种 / 培养 / 收获”三个可编辑阶段。")
        values = dialog.show()
        if not values:
            return
        if self.ctx.repos.batches.code_exists(values["batch_code"]):
            error(self, f"批次编号 {values['batch_code']} 已存在")
            return
        values["created_by"] = self.ctx.operator
        try:
            bid = self.ctx.repos.batches.create(values)
        except Exception as exc:
            error(self, f"创建失败：{exc}")
            return
        self.ctx.audit("新增批次", "batch", bid, after=values)
        self.current_id = bid
        self.ctx.settings.last_batch_id = bid
        self.ctx.settings.save()
        self.app.refresh_batches()
        self.refresh(select_id=bid)
        self.set_status(f"批次 {values['batch_code']} 已创建")

    def edit_batch(self):
        row = self.table.selected_row()
        if not row:
            info(self, "请先选择批次")
            return
        dialog = FormDialog(self, "编辑批次", self._batch_fields(row), width=600)
        values = dialog.show()
        if not values:
            return
        if self.ctx.repos.batches.code_exists(values["batch_code"], row["batch_id"]):
            error(self, "批次编号已被其他批次使用")
            return
        try:
            self.ctx.repos.batches.update(row["batch_id"], values)
            self.ctx.audit("修改批次", "batch", row["batch_id"], before=row, after=values)
        except Exception as exc:
            error(self, f"更新失败：{exc}")
            return
        self.app.refresh_batches()
        self.refresh(select_id=row["batch_id"])
        self.set_status("批次信息已更新")

    # ---------- 阶段 ----------
    def _require_batch(self):
        row = self.table.selected_row()
        if not row:
            info(self, "请先选择批次")
            return None
        return row

    def add_stage(self):
        row = self._require_batch()
        if not row:
            return
        dialog = FormDialog(self, "新增培养阶段", [
            {"key": "stage_name", "label": "阶段名称", "required": True},
            {"key": "start_time", "label": "开始时间", "type": "date", "default": now_iso()},
            {"key": "end_time", "label": "结束时间", "type": "date"},
            {"key": "notes", "label": "说明", "type": "multiline", "lines": 3},
        ], width=560)
        values = dialog.show()
        if not values:
            return
        sid = self.ctx.repos.batches.add_stage(row["batch_id"], values)
        self.ctx.audit("新增培养阶段", "batch_stage", sid, after=values)
        self._load_detail(row)

    def edit_stage(self):
        row = self._require_batch()
        stage = self.stage_table.selected_row()
        if not row or not stage:
            info(self, "请先选择阶段")
            return
        dialog = FormDialog(self, "编辑培养阶段", [
            {"key": "stage_name", "label": "阶段名称", "required": True, "default": stage["stage_name"]},
            {"key": "start_time", "label": "开始时间", "type": "date", "default": stage.get("start_time") or ""},
            {"key": "end_time", "label": "结束时间", "type": "date", "default": stage.get("end_time") or ""},
            {"key": "notes", "label": "说明", "type": "multiline", "lines": 3, "default": stage.get("notes") or ""},
        ], width=560)
        values = dialog.show()
        if not values:
            return
        self.ctx.repos.batches.update_stage(stage["stage_id"], values)
        self._load_detail(row)

    def delete_stage(self):
        row = self._require_batch()
        stage = self.stage_table.selected_row()
        if not row or not stage:
            return
        if not confirm(self, "删除阶段", f"删除阶段“{stage['stage_name']}”？关联参数会保留但阶段变为空。"):
            return
        self.ctx.repos.batches.delete_stage(stage["stage_id"])
        self._load_detail(row)

    # ---------- 参数 ----------
    def add_parameter(self):
        row = self._require_batch()
        if not row:
            return
        stages = self.ctx.repos.batches.stages(row["batch_id"])
        choices = [{"label": s["stage_name"], "value": s["stage_id"]} for s in stages]
        dialog = FormDialog(self, "记录培养参数", [
            {"key": "stage_id", "label": "所属阶段", "type": "combo", "choices": choices,
             "default": choices[0]["label"] if choices else ""},
            {"key": "param_name", "label": "参数名称", "required": True, "help": "如 VCD、活率、pH、DO、温度、代谢物"},
            {"key": "param_value", "label": "数值", "type": "number"},
            {"key": "unit", "label": "单位", "default": ""},
            {"key": "recorded_at", "label": "记录时间", "type": "date", "default": now_iso()},
            {"key": "notes", "label": "备注", "type": "multiline", "lines": 2},
        ], width=560)
        values = dialog.show()
        if not values:
            return
        pid = self.ctx.repos.batches.add_parameter(row["batch_id"], values)
        self.ctx.audit("记录培养参数", "culture_parameter", pid, after=values)
        self._load_detail(row)

    def delete_parameter(self):
        row = self._require_batch()
        param = self.param_table.selected_row()
        if not row or not param:
            return
        if confirm(self, "删除参数", f"删除参数“{param.get('param_name')}”记录？"):
            self.ctx.repos.batches.delete_parameter(param["param_id"])
            self._load_detail(row)

    # ---------- 泵映射 ----------
    def add_mapping(self):
        row = self._require_batch()
        if not row:
            return
        pumps = self.ctx.repos.pumps.active()
        liquids = self.ctx.repos.liquids.active()
        if not pumps or not liquids:
            error(self, "请先维护泵和工艺液基础数据")
            return
        dialog = FormDialog(self, "新增泵 - 液体绑定", [
            {"key": "pump_id", "label": "泵", "type": "combo",
             "choices": [{"label": f"{p['pump_code']} · {p['pump_name']}", "value": p["pump_id"]} for p in pumps],
             "required": True},
            {"key": "liquid_id", "label": "液体", "type": "combo",
             "choices": [{"label": f"{l['liquid_code']} · {l['liquid_name']}", "value": l["liquid_id"]} for l in liquids],
             "required": True},
            {"key": "valid_from", "label": "生效时间", "type": "date", "default": now_iso()},
            {"key": "valid_to", "label": "失效时间", "type": "date"},
            {"key": "mapping_note", "label": "说明", "type": "multiline", "lines": 2},
        ], width=560)
        values = dialog.show()
        if not values:
            return
        mid = self.ctx.repos.batches.add_mapping(row["batch_id"], values)
        self.ctx.audit("新增泵液体绑定", "batch_pump_mapping", mid, after=values)
        self._load_detail(row)

    def delete_mapping(self):
        row = self._require_batch()
        mapping = self.map_table.selected_row()
        if not row or not mapping:
            return
        if confirm(self, "解除绑定", f"解除 {mapping.get('pump_code')} 与 {mapping.get('liquid_name')} 的绑定？"):
            self.ctx.repos.batches.delete_mapping(mapping["mapping_id"])
            self._load_detail(row)
