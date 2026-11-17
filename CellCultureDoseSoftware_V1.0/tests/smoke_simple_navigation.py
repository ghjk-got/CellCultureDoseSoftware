# -*- coding: utf-8 -*-
"""隔离验证四入口、首次配置和成品登记相关页面。"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
tmp = Path(tempfile.mkdtemp(prefix='ccds_nav_'))
os.environ['CCDS_DATA_DIR'] = str(tmp / 'data')
os.environ['CCDS_CONFIG'] = str(tmp / 'config.json')
from app.context import AppContext
from app.ui.main_window import MainWindow
import app.ui.pages.setup_wizard as setup

setup.info = lambda *args: None
setup.error = lambda parent, message: (_ for _ in ()).throw(AssertionError(message))
ctx = AppContext()
app = MainWindow(ctx)
app.withdraw()
app.update_idletasks()
windows = [w for w in app.winfo_children() if isinstance(w, setup.SetupWizard)]
assert len(windows) == 1
wizard = windows[0]
for key, val in {'reactor':'实验反应器', 'pump':'外接泵', 'liquid':'补料液', 'unit':'mL'}.items():
    wizard.vars[key].set(val)
wizard.save()
assert ctx.db.get_setting('initial_setup') == 'complete'
assert [p['pump_name'] for p in ctx.repos.pumps.active()] == ['外接泵']
assert list(app.nav_buttons) == ['dashboard', 'medium_work', 'feed_work', 'resources']
for key in ('dashboard', 'medium_work', 'feed_work', 'resources', 'master', 'formula', 'calibration', 'dose_import', 'settings', 'reports', 'batch', 'plan', 'dose_calc', 'anomaly', 'preparation'):
    app.go(key)
    app.update_idletasks()
    assert app.current_key == key
app.destroy()
ctx.close()
print('SIMPLE NAVIGATION OK')
