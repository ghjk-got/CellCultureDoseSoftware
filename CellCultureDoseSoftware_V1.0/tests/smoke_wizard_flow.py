# -*- coding: utf-8 -*-
"""导入向导完整流程测试（文件→映射→预览→提交）。"""
from __future__ import annotations
import os, sys, tempfile, traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
tmp = Path(tempfile.mkdtemp(prefix="ccds_flow_"))
os.environ["CCDS_DATA_DIR"] = str(tmp / "data")
os.environ["CCDS_CONFIG"] = str(tmp / "config.json")
from app.context import AppContext
from app.ui.main_window import MainWindow
import app.ui.pages.dose_import as di
import app.ui.pages.calibration as cal

messages = []
di.info = lambda parent, msg, title="提示": messages.append(("info", msg))
di.error = lambda parent, msg, title="错误": messages.append(("error", msg))
di.warning = lambda parent, msg, title="警告": messages.append(("warning", msg))
cal.info = lambda parent, msg, title="提示": messages.append(("info", msg))
cal.error = lambda parent, msg, title="错误": messages.append(("error", msg))

ctx = AppContext()
repos = ctx.repos
bid = repos.batches.create({"batch_code": "B-FLOW-1", "project_name": "流程测试", "status": "进行中", "created_by": "t"})
pumps = repos.pumps.active()
app = MainWindow(ctx); app.withdraw()
app.go("dose_import"); app.update_idletasks()

csv = tmp / "dose2.csv"
from datetime import datetime, timedelta
rows = ["time,pump,flow,total,status"]
for i in range(8):
    t = datetime(2026, 11, 11, 8, 0, 0) + timedelta(minutes=10 * i)
    rows.append(f"{t:%Y-%m-%d %H:%M:%S},{pumps[0]['pump_code']},10,{i*1.6667:.3f},RUN")
csv.write_text("\n".join(rows), encoding="utf-8")

page = app.pages["dose_import"]
wiz = di.DoseImportWizard(page, page)
wiz.files = [csv]
wiz.file_list.insert("end", csv.name)
wiz.header_var.set("1")
wiz._load_first_table()
wiz._auto_map()
ok = wiz._build_previews()
print("dose preview ok", ok, getattr(wiz, "_preview_errors", None))
assert ok
wiz._prepare_confirm()
wiz.duplicate_var.set(True)
wiz.notes_var.set("流程测试")
wiz.commit()
app.update_idletasks()
count = ctx.db.scalar("SELECT COUNT(*) FROM import_record WHERE batch_id=?", (bid,))
print("imports", count, messages[-3:])
assert count == 1

app.go("calibration"); app.update_idletasks()
calpage = app.pages["calibration"]
pump_id = calpage.pump_map.get(calpage.pump_var.get())
cal_csv = tmp / "cal.csv"
cal_csv.write_text("rpm,flow\n10,5\n20,10\n30,15\n", encoding="utf-8")
dlg = cal.CalibrationImportDialog(calpage, calpage, pump_id)
dlg.file_var.set(str(cal_csv))
dlg.header_var.set("1")
dlg.load_headers()
dlg.preview()
print("cal preview", len(dlg.preview_obj.points), dlg.preview_obj.errors)
assert dlg.preview_obj.points
dlg.commit()
app.update_idletasks()
cal_count = ctx.db.scalar("SELECT COUNT(*) FROM pump_calibration WHERE pump_id=?", (pump_id,))
print("calibrations", cal_count, messages[-3:])
assert cal_count == 1
print("FLOW OK")
app.destroy(); ctx.close()
