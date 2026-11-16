# -*- coding: utf-8 -*-
"""界面冒烟测试：创建主窗口并逐个打开页面。"""
from __future__ import annotations

import os
import sys
import tempfile
import traceback
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
tmp = Path(tempfile.mkdtemp(prefix="ccds_ui_"))
os.environ["CCDS_DATA_DIR"] = str(tmp / "data")
os.environ["CCDS_CONFIG"] = str(tmp / "config.json")

from app.context import AppContext
from app.ui.main_window import MainWindow


def seed(ctx):
    repos = ctx.repos
    cid = repos.components.insert({"component_id": "", "component_code": "GLU", "component_name": "葡萄糖",
                                   "category": "碳源", "default_unit": "g", "molecular_weight": 180.16,
                                   "purity_default": 1.0, "status": "启用", "created_at": datetime.now().isoformat()})
    fid = repos.formulas.create({"formula_code": "F-001", "formula_name": "基础培养基", "formula_type": "基础培养基",
                                 "version_no": 1, "status": "已发布", "created_by": "tester"}, [
        {"component_id": cid, "target_concentration": 4.0, "concentration_unit": "g/L",
         "purity_fraction": 1.0, "source_type": "直接称量", "molecular_weight": 180.16},
    ])
    bid = repos.batches.create({"batch_code": "B-UI-001", "project_name": "界面测试", "culture_system": "CHO",
                                "working_volume_ml": 3000, "created_by": "tester", "status": "进行中"})
    pumps = repos.pumps.active()
    liquids = repos.liquids.active()
    repos.batches.add_mapping(bid, {"pump_id": pumps[0]["pump_id"], "liquid_id": liquids[0]["liquid_id"]})
    pid = repos.plans.create(bid, "tester", copy_latest=False)
    repos.plans.add_event(pid, {"liquid_id": liquids[0]["liquid_id"], "pump_id": pumps[0]["pump_id"],
                                "planned_start": "2026-11-11T08:00:00+08:00",
                                "planned_end": "2026-11-11T12:00:00+08:00",
                                "planned_volume_ml": 40, "target_flow_ml_h": 10, "duration_h": 4})
    cid_cal = repos.calibrations.create(pumps[0]["pump_id"], {"calibration_date": "2026-11-01",
                                                              "calibration_method": "手工录入"}, [
        {"setpoint_value": 10, "setpoint_unit": "rpm", "measured_flow": 2, "flow_unit": "mL/h"},
        {"setpoint_value": 30, "setpoint_unit": "rpm", "measured_flow": 6, "flow_unit": "mL/h"},
    ], "tester")
    repos.calibrations.set_status(cid_cal, "有效")

    csv_path = tmp / "dose.csv"
    rows = ["时间,泵编号,流速(mL/h),累计体积(mL),状态"]
    start = datetime(2026, 11, 11, 8, 0, 0)
    total = 100.0
    for i in range(13):
        t = start + timedelta(minutes=20 * i)
        rows.append(f"{t:%Y-%m-%d %H:%M:%S},{pumps[0]['pump_code']},10,{total:.3f},RUN")
        total += 10 / 3
    csv_path.write_text("\n".join(rows), encoding="utf-8-sig")
    table = ctx.dose_import.read(csv_path)
    mapping = ctx.dose_import.suggest_mapping(table.headers)
    pv = ctx.dose_import.preview(bid, csv_path, None, 1, mapping)
    ctx.dose_import.commit(pv, bid, "tester")
    ctx.settings.last_batch_id = bid
    ctx.settings.save()


errors = []
ctx = AppContext()
seed(ctx)
app = MainWindow(ctx)
app.withdraw()


def handler(exc_type, exc_value, exc_tb):
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    errors.append(text)
    print("PAGE ERROR:", exc_value)
    traceback.print_exception(exc_type, exc_value, exc_tb)


app._report_exception = handler
for key in ["dashboard", "master", "formula", "preparation", "batch", "plan", "calibration",
            "dose_import", "dose_calc", "anomaly", "reports", "settings"]:
    try:
        app.go(key)
        app.update_idletasks()
        app.update()
        print("OK", key)
    except Exception:
        handler(*sys.exc_info())

app.destroy()
ctx.close()
print("ERRORS", len(errors))
sys.exit(1 if errors else 0)
