# -*- coding: utf-8 -*-
"""使用临时数据库验证手工记录窗口与保存流程。"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
tmp = Path(tempfile.mkdtemp(prefix="ccds_manual_ui_"))
os.environ['CCDS_DATA_DIR'] = str(tmp / 'data')
os.environ['CCDS_CONFIG'] = str(tmp / 'config.json')
from app.context import AppContext
from app.ui.main_window import MainWindow
import app.ui.pages.manual_feed as manual_ui

messages = []
manual_ui.info = lambda parent, message, *args: messages.append(message)
manual_ui.error = lambda parent, message, *args: (_ for _ in ()).throw(AssertionError(message))
ctx = AppContext()
bid = ctx.repos.batches.create({'batch_code': 'MANUAL-UI', 'status': '进行中', 'created_by': 'test'})
ctx.settings.last_batch_id = bid
app = MainWindow(ctx)
app.withdraw()
app.go('dose_calc')
page = app.pages['dose_calc']
window = manual_ui.ManualFeedWindow(page)
window.withdraw()
window.vars['pump'].set(next(iter(window.pumps)))
window.vars['liquid'].set(next(iter(window.liquids)))
for key, value in {'start_time': '2026-11-17 08:00', 'end_time': '2026-11-17 09:00',
                   'start_reading': '10', 'end_reading': '25', 'reading_unit': 'mL'}.items():
    window.vars[key].set(value)
window.save()
rows = ctx.manual_feed.list_for_batch(bid)
assert len(rows) == 1 and rows[0]['estimate_ml'] == 15 and rows[0]['measured_ml'] is None
window.vars['end_time'].set('')
window.vars['end_reading'].set('')
window.save(start_only=True)
ongoing = next(r for r in ctx.manual_feed.list_for_batch(bid) if r['lifecycle_status'] == '进行中')
window.tree.selection_set(ongoing['record_id'])
window.load_selected()
window.vars['end_time'].set('2026-11-17 09:00')
window.vars['end_reading'].set('25')
manual_ui.simpledialog.askstring = lambda *args, **kwargs: '测试操作员'
window.save_existing()
saved = next(r for r in ctx.manual_feed.list_for_batch(bid) if r['record_id'] == ongoing['record_id'])
assert saved['lifecycle_status'] == '已完成' and saved['estimate_ml'] == 15
assert ctx.db.scalar('SELECT COUNT(*) FROM manual_feed_revision WHERE record_id=?', (ongoing['record_id'],)) == 1
window.destroy()
app.destroy()
ctx.close()
print('MANUAL UI OK')
