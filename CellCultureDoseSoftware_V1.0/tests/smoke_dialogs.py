# -*- coding: utf-8 -*-
"""对话框与页面构造冒烟测试。"""
from __future__ import annotations
import os, sys, tempfile, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
tmp = Path(tempfile.mkdtemp(prefix="ccds_dlg_"))
os.environ["CCDS_DATA_DIR"] = str(tmp / "data")
os.environ["CCDS_CONFIG"] = str(tmp / "config.json")
from app.context import AppContext
from app.ui.main_window import MainWindow
from app.ui.widgets import FormDialog
from app.ui.pages.dose_import import DoseImportWizard
from app.ui.pages.calibration import CalibrationImportDialog

errors = []
# 演示数据：使用 seed_demo 生成到当前临时目录
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
import seed_demo
seed_demo.seed(str(tmp / "data"), reset=True)
ctx = AppContext()
app = MainWindow(ctx)
app.withdraw()

def handler(exc_type, exc_value, exc_tb):
    errors.append(exc_value)
    traceback.print_exception(exc_type, exc_value, exc_tb)
app._report_exception = handler
app.report_callback_exception = handler

for key in ["dashboard", "master", "formula", "preparation", "batch", "plan", "calibration",
            "dose_import", "dose_calc", "anomaly", "reports", "settings"]:
    try:
        app.go(key); app.update_idletasks(); app.update()
        print("PAGE OK", key)
    except Exception:
        handler(*sys.exc_info())

try:
    d = FormDialog(app, "测试表单", [
        {"key": "a", "label": "文本", "required": True},
        {"key": "b", "label": "数字", "type": "number"},
        {"key": "c", "label": "选择", "type": "combo", "values": ["A", "B"], "default": "A"},
        {"key": "d", "label": "时间", "type": "date"},
        {"key": "e", "label": "多行", "type": "multiline", "lines": 3},
    ])
    d.update_idletasks(); d.destroy()
    print("FORM OK")
except Exception:
    handler(*sys.exc_info())

try:
    app.go("dose_import"); app.update_idletasks()
    page = app.pages["dose_import"]
    wiz = DoseImportWizard(page, page)
    wiz.update_idletasks(); wiz.destroy()
    print("DOSE WIZARD OK")
except Exception:
    handler(*sys.exc_info())

try:
    app.go("calibration"); app.update_idletasks()
    page = app.pages["calibration"]
    pump_id = page.pump_map.get(page.pump_var.get())
    dlg = CalibrationImportDialog(page, page, pump_id)
    dlg.update_idletasks(); dlg.destroy()
    print("CAL WIZARD OK")
except Exception:
    handler(*sys.exc_info())

app.destroy(); ctx.close()
print("ERRORS", len(errors))
sys.exit(1 if errors else 0)
