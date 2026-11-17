# -*- coding: utf-8 -*-
"""首次配置：由使用者录入设备档案，不将示例设备视作实物。"""
import tkinter as tk
from tkinter import ttk

from ...db import new_id, now_iso
from ..widgets import error, info


class SetupWizard(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app, self.ctx = app, app.ctx
        self.title("首次使用：实验室设备")
        self.geometry("540x360")
        self.transient(app)
        self.vars = {key: tk.StringVar() for key in ('reactor', 'pump', 'liquid', 'unit')}
        body = ttk.Frame(self, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="建立本实验室的设备档案", font=("Microsoft YaHei", 13, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        for i, (label, key) in enumerate((("反应器名称", 'reactor'), ("补料泵名称", 'pump'), ("补料液名称", 'liquid'), ("设备累计读数单位", 'unit')), 1):
            ttk.Label(body, text=label).grid(row=i, column=0, sticky="w", pady=6)
            widget = ttk.Combobox(body, textvariable=self.vars[key], values=('mL', 'L'), state='readonly') if key == 'unit' else ttk.Entry(body, textvariable=self.vars[key])
            widget.grid(row=i, column=1, sticky="ew", pady=6)
        body.columnconfigure(1, weight=1)
        ttk.Label(body, text="泵型号、通道和校准需依据现场设备确认，可稍后在资料中完善。", wraplength=480).grid(row=5, column=0, columnspan=2, sticky="w", pady=10)
        ttk.Button(body, text="保存设备档案", command=self.save).grid(row=6, column=1, sticky="e")
        ttk.Button(body, text="稍后设置", command=self.destroy).grid(row=6, column=0, sticky="w")

    def save(self):
        data = {k: v.get().strip() for k, v in self.vars.items()}
        if not all(data.values()):
            error(self, "请填写反应器、泵、补料液名称和读数单位")
            return
        with self.ctx.db.transaction() as cur:
            reactor, pump, liquid = new_id('RCT'), new_id('PMP'), new_id('LIQ')
            cur.execute("INSERT INTO reactor_info(reactor_id,reactor_code,reactor_name,notes,status,created_at) VALUES(?,?,?,?,?,?)", (reactor, reactor, data['reactor'], '用户首次配置', '启用', now_iso()))
            cur.execute("INSERT INTO pump_info(pump_id,pump_code,pump_name,notes,status,created_at) VALUES(?,?,?,?,?,?)", (pump, pump, data['pump'], '读数单位：' + data['unit'] + '；连接与校准待现场确认', '启用', now_iso()))
            cur.execute("INSERT INTO liquid_info(liquid_id,liquid_code,liquid_name,notes,status,created_at) VALUES(?,?,?,?,?,?)", (liquid, liquid, data['liquid'], '用户首次配置', '启用', now_iso()))
            # 首次配置结束后，示例仅停用并保留，以免误选为现场设备。
            for table in ('pump_info', 'liquid_info', 'reactor_info'):
                cur.execute(f"UPDATE {table} SET status='停用' WHERE notes='系统初始化示例，可在基础数据中修改'")
            cur.execute("UPDATE reactor_info SET status='停用' WHERE notes='系统初始化示例'")
            cur.execute("INSERT OR REPLACE INTO app_setting(key,value,updated_at) VALUES('initial_setup','complete',?)", (now_iso(),))
        self.ctx.settings.default_volume_unit = data['unit']
        self.ctx.settings.save()
        self.ctx.audit("首次设备配置", "system", "initial_setup", after=data)
        info(self, "设备档案已保存。请在实际使用前确认连接、单位及校准。")
        self.destroy()
