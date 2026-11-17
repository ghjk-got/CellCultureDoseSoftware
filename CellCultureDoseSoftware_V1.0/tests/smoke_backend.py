# -*- coding: utf-8 -*-
"""后端冒烟测试：数据库、配方计算、剂量核算、导入与报告。"""
from __future__ import annotations

import json
import sys
import tempfile

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))
from datetime import datetime, timedelta
from pathlib import Path

from app.config import Settings
from app.db import Database
from app.repositories import Repositories
from app.services.formula_calc import calculate_formula
from app.services.calibration import interpolate
from app.services import dose_calc
from app.services.reporting import ReportService
from app.importers.dose_importer import DoseImportService


def main():
    tmp = Path(tempfile.mkdtemp(prefix="ccds_"))
    settings = Settings(data_dir=str(tmp))
    settings.ensure_dirs()
    db = Database(settings.db_path)
    db.seed_defaults()
    repos = Repositories(db)
    print("pumps:", [p["pump_code"] for p in repos.pumps.active()])

    # 基础数据
    cid = repos.components.insert({
        "component_id": "", "component_code": "GLU", "component_name": "葡萄糖", "category": "碳源",
        "default_unit": "g", "molecular_weight": 180.16, "purity_default": 1.0,
        "status": "启用", "created_at": datetime.now().isoformat(),
    })
    cid2 = repos.components.insert({
        "component_id": "", "component_code": "GLN", "component_name": "谷氨酰胺", "category": "氨基酸",
        "default_unit": "g", "molecular_weight": 146.15, "purity_default": 0.99,
        "status": "启用", "created_at": datetime.now().isoformat(),
    })
    fid = repos.formulas.create({
        "formula_code": "F-001", "formula_name": "基础培养基", "formula_type": "基础培养基",
        "version_no": 1, "status": "已发布", "created_by": "tester",
    }, [
        {"component_id": cid, "target_concentration": 4.0, "concentration_unit": "g/L",
         "purity_fraction": 1.0, "source_type": "直接称量", "molecular_weight": 180.16},
        {"component_id": cid2, "target_concentration": 0.6, "concentration_unit": "g/L",
         "purity_fraction": 0.99, "source_type": "直接称量", "molecular_weight": 146.15},
    ])
    details = repos.formulas.details(fid)
    calc = calculate_formula(details, 1000, "mL")
    print("formula:", calc["total_theoretical_g"], calc["total_corrected_g"], "errors:", calc["errors"])
    assert calc["errors"] == []
    assert abs(calc["total_theoretical_g"] - 4.6) < 1e-9
    assert abs(calc["total_corrected_g"] - (4.0 + 0.6 / 0.99)) < 1e-9

    # 校准插值
    pts = [
        {"setpoint_value": 10, "setpoint_unit": "rpm", "measured_flow": 2, "flow_unit": "mL/h"},
        {"setpoint_value": 30, "setpoint_unit": "rpm", "measured_flow": 6, "flow_unit": "mL/h"},
    ]
    interp = interpolate(pts, 20)
    print("interp:", interp)
    assert interp["flow_ml_h"] == 4.0
    assert interpolate(pts, 40)["flow_ml_h"] is None

    # 批次与数据
    bid = repos.batches.create({"batch_code": "B-TEST-001", "project_name": "测试项目",
                                "culture_system": "CHO", "working_volume_ml": 3000,
                                "created_by": "tester", "status": "进行中"})
    pumps = repos.pumps.active()
    liquids = repos.liquids.active()
    repos.batches.add_mapping(bid, {"pump_id": pumps[0]["pump_id"], "liquid_id": liquids[0]["liquid_id"]})
    pid = repos.plans.create(bid, "tester", copy_latest=False)
    eid = repos.plans.add_event(pid, {"liquid_id": liquids[0]["liquid_id"], "pump_id": pumps[0]["pump_id"],
                                      "planned_start": "2026-11-11T08:00:00+08:00",
                                      "planned_end": "2026-11-11T12:00:00+08:00",
                                      "planned_volume_ml": 40, "target_flow_ml_h": 10, "duration_h": 4})

    # CSV 导入
    csv_path = tmp / "dose.csv"
    rows = ["时间,泵编号,流速(mL/h),累计体积(mL),状态"]
    start = datetime(2026, 11, 11, 8, 0, 0)
    total = 100.0
    for i in range(13):
        t = start + timedelta(minutes=20 * i)
        rows.append(f"{t:%Y-%m-%d %H:%M:%S},{pumps[0]['pump_code']},10,{total:.3f},RUN")
        total += 10 / 3
    csv_path.write_text("\n".join(rows), encoding="utf-8-sig")
    importer = DoseImportService(repos, settings)
    table = importer.read(csv_path)
    mapping = importer.suggest_mapping(table.headers)
    print("mapping:", mapping)
    pv = importer.preview(bid, csv_path, None, 1, mapping, "mL/h", "mL")
    print("preview:", pv.stats, "errors:", pv.errors[:2])
    assert not pv.errors
    iid = importer.commit(pv, bid, "tester")
    print("import:", iid)

    data = repos.imports.data_for(bid, pumps[0]["pump_id"], "2026-11-11T00:00:00+08:00", "2026-11-11T23:59:59+08:00")
    result = dose_calc.calculate(data, 40, "2026-11-11T08:00:00+08:00", "2026-11-11T12:00:00+08:00", 2)
    print("dose:", {k: result[k] for k in ("quality_status", "actual_volume_ml", "flow_integral_ml", "deviation_percent", "completion_percent", "anomalies")})
    assert abs(result["actual_volume_ml"] - 40) < 1e-6
    assert abs(result["flow_integral_ml"] - 40) < 1e-6
    assert result["quality_status"] == "有效"

    cid_calc = repos.doses.create({"batch_id": bid, "event_id": eid, "pump_id": pumps[0]["pump_id"],
                                   "liquid_id": liquids[0]["liquid_id"],
                                   "time_start": "2026-11-11T08:00:00+08:00",
                                   "time_end": "2026-11-11T12:00:00+08:00",
                                   "planned_volume_ml": 40, "actual_volume_ml": result["actual_volume_ml"],
                                   "flow_integral_ml": result["flow_integral_ml"],
                                   "deviation_ml": result["deviation_ml"],
                                   "deviation_percent": result["deviation_percent"],
                                   "completion_percent": result["completion_percent"],
                                   "calculation_method": result["calculation_method"],
                                   "quality_status": result["quality_status"], "data_import_id": iid})
    print("calc id:", cid_calc)

    # 报告
    service = ReportService(repos, settings)
    xlsx = service.generate_excel(bid, "tester")
    print("excel:", xlsx, xlsx.stat().st_size)
    pdf = service.generate_pdf(bid, "tester")
    print("pdf:", pdf, pdf.stat().st_size)
    assert xlsx.exists() and xlsx.stat().st_size > 5000
    assert pdf.exists() and pdf.stat().st_size > 5000
    print("SMOKE OK", tmp)


if __name__ == "__main__":
    main()
