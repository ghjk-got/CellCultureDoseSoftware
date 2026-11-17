# -*- coding: utf-8 -*-
"""首页：当前批次、待处理事项和常用操作。"""
import tkinter as tk
from tkinter import ttk

from ..base import Page
from ..theme import COLORS, FONT, FONT_H3, FONT_SMALL
from ..widgets import Card


class DashboardPage(Page):
    key = 'dashboard'
    title = '首页与批次'
    subtitle = '当前批次、补料进度与待处理事项'

    def __init__(self, parent, app):
        super().__init__(parent, app)
        actions = Card(self, padding=16)
        actions.pack(fill='x')
        tk.Label(actions.body, text='今天的培养工作', bg=COLORS['white'], font=FONT_H3).pack(anchor='w')
        bar = tk.Frame(actions.body, bg=COLORS['white'])
        bar.pack(fill='x', pady=10)
        for label, callback in [('新建批次', app.new_batch_quick), ('培养基配制', lambda: app.go('medium_work')),
                                ('记录补料', lambda: app.go('feed_work')), ('历史批次', lambda: app.go('batch')),
                                ('导出批次报告', lambda: app.go('reports'))]:
            ttk.Button(bar, text=label, command=callback).pack(side='left', padx=(0, 8))
        self.batch_label = tk.Label(actions.body, bg=COLORS['white'], fg=COLORS['text'], font=FONT, anchor='w')
        self.batch_label.pack(fill='x', pady=(4, 0))
        self.warning_label = tk.Label(actions.body, bg=COLORS['white'], fg=COLORS['danger'], font=FONT_SMALL, anchor='w')
        self.warning_label.pack(fill='x', pady=(4, 0))

        pending = Card(self, padding=16)
        pending.pack(fill='both', expand=True, pady=(12, 0))
        header = tk.Frame(pending.body, bg=COLORS['white'])
        header.pack(fill='x')
        tk.Label(header, text='待处理事项', bg=COLORS['white'], font=FONT_H3).pack(side='left')
        ttk.Button(header, text='查看补料记录', command=lambda: app.go('feed_work')).pack(side='right')
        self.pending_list = tk.Listbox(pending.body, relief='flat', bg=COLORS['white'], fg=COLORS['text'], font=FONT, activestyle='none')
        self.pending_list.pack(fill='both', expand=True, pady=10)
        self.pending_list.bind('<Double-1>', self.open_pending)
        self.targets = []

    def on_show(self): self.refresh()
    def on_batch_changed(self): self.refresh()

    def refresh(self):
        db = self.ctx.db
        batch = self.app.current_batch
        self.batch_label.configure(text=(f"当前批次：{batch['batch_code']}  ·  {batch.get('project_name') or '未命名项目'}  ·  {batch['status']}" if batch else '尚未选择批次，可新建或查看历史批次。'))
        active = int(db.scalar("SELECT COUNT(*) FROM batch_info WHERE status='进行中'", (), 0))
        self.warning_label.configure(text=f'已有 {active} 个进行中批次，请逐一处理；原记录不会被自动关闭。' if active > 1 else '')
        self.pending_list.delete(0, 'end')
        self.targets = []
        rows = db.q("SELECT m.record_id,m.batch_id,m.lifecycle_status,m.quality_status,m.issues,b.batch_code,p.pump_code FROM manual_feed_record m JOIN batch_info b ON b.batch_id=m.batch_id JOIN pump_info p ON p.pump_id=m.pump_id WHERE m.lifecycle_status='进行中' OR m.quality_status='待审核' ORDER BY m.created_at DESC LIMIT 30")
        for row in rows:
            label = '补料进行中' if row['lifecycle_status'] == '进行中' else '补料待审核'
            self.pending_list.insert('end', f"{label}  ·  {row['batch_code']}  ·  {row['pump_code']}  ·  {row['record_id']}")
            self.targets.append(('feed_work', row['batch_id']))
        for row in self.ctx.repos.anomalies.list_for_batch(status='未解决')[:20]:
            self.pending_list.insert('end', f"异常待处理  ·  {row.get('batch_code') or '未关联批次'}  ·  {row.get('anomaly_type')}")
            self.targets.append(('anomaly', row.get('batch_id')))
        if not self.targets:
            self.pending_list.insert('end', '暂无待处理事项。')

    def open_pending(self, _event=None):
        selection = self.pending_list.curselection()
        if not selection or selection[0] >= len(self.targets): return
        target, bid = self.targets[selection[0]]
        if bid:
            self.ctx.settings.last_batch_id = bid
            self.ctx.settings.save()
            self.app.refresh_batches()
        self.app.go(target)
