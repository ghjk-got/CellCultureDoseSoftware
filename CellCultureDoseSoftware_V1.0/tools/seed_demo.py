# -*- coding: utf-8 -*-
"""生成一套可用于演示与验收的 CHO 培养数据。

用法：
    python tools/seed_demo.py --data-dir D:\\path\\DemoData [--reset]
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from app.config import Settings
from app.db import Database, now_iso
from app.repositories import Repositories
from app.services import dose_calc
from app.services.reporting import ReportService
from app.importers.dose_importer import DoseImportService


COMPONENTS = [
    ("GLU", "葡萄糖", "碳源", "g", 180.16, 1.0, None, None),
    ("GLN", "谷氨酰胺", "氨基酸", "g", 146.15, 0.99, 200.0, "g/L"),
    ("NAHCO3", "碳酸氢钠", "盐类", "g", 84.01, 1.0, None, None),
    ("INS", "胰岛素", "生长因子", "g", 5807.6, 1.0, 10.0, "g/L"),
    ("FEED_A_POWDER", "Feed A 干粉", "其他", "g", None, 1.0, 100.0, "g/L"),
    ("FEED_B_POWDER", "Feed B 干粉", "其他", "g", None, 1.0, 80.0, "g/L"),
]


def seed(data_dir: str, reset: bool = False) -> Path:
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dir=str(data_path), operator="演示用户")
    settings.ensure_dirs()
    if reset and settings.db_path.exists():
        settings.db_path.unlink()
    db = Database(settings.db_path)
    db.seed_defaults()
    repos = Repositories(db)
    if repos.batches.list():
        print("数据目录已有批次，未重复生成。使用 --reset 强制重建。")
        return settings.db_path

    comp_ids = {}
    for code, name, category, unit, mw, purity, stock, stock_unit in COMPONENTS:
        comp_ids[code] = repos.components.insert({
            "component_id": "", "component_code": code, "component_name": name, "category": category,
            "default_unit": unit, "molecular_weight": mw, "purity_default": purity,
            "stock_concentration": stock, "stock_unit": stock_unit,
            "status": "启用", "created_at": now_iso(), "notes": "演示数据",
        })

    repos.formulas.create({
        "formula_code": "MED-BASE-01", "formula_name": "CHO 基础培养基", "formula_type": "基础培养基",
        "version_no": 1, "status": "已发布", "effective_date": "2026-10-20",
        "change_note": "初始版本", "created_by": "演示用户",
    }, [
        {"component_id": comp_ids["GLU"], "target_concentration": 4.0, "concentration_unit": "g/L",
         "molecular_weight": 180.16, "purity_fraction": 1.0, "source_type": "直接称量"},
        {"component_id": comp_ids["GLN"], "target_concentration": 0.6, "concentration_unit": "g/L",
         "molecular_weight": 146.15, "purity_fraction": 0.99, "source_type": "直接称量"},
        {"component_id": comp_ids["NAHCO3"], "target_concentration": 2.0, "concentration_unit": "g/L",
         "molecular_weight": 84.01, "purity_fraction": 1.0, "source_type": "直接称量"},
        {"component_id": comp_ids["INS"], "target_concentration": 5.0, "concentration_unit": "mg/L",
         "molecular_weight": 5807.6, "purity_fraction": 1.0, "source_type": "母液",
         "stock_concentration": 10.0, "stock_unit": "g/L"},
    ])
    repos.formulas.create({
        "formula_code": "FEED-A-10X", "formula_name": "Feed A 浓缩液 10×", "formula_type": "Feed",
        "version_no": 1, "status": "已发布", "effective_date": "2026-10-20",
        "change_note": "初始版本", "created_by": "演示用户",
    }, [
        {"component_id": comp_ids["FEED_A_POWDER"], "target_concentration": 100.0, "concentration_unit": "g/L",
         "purity_fraction": 1.0, "source_type": "直接称量"},
    ])

    start = datetime(2026, 11, 1, 8, 0, 0).astimezone()
    batch_id = repos.batches.create({
        "batch_code": "CHO-20261101-01", "project_name": "CHO 补料培养工艺验证",
        "culture_system": "CHO", "working_volume_ml": 3000,
        "start_time": start.isoformat(), "status": "进行中", "created_by": "演示用户",
        "notes": "演示批次：3 L 反应器，Day 0~8 补料培养。",
    })
    stages = repos.batches.stages(batch_id)
    if len(stages) >= 3:
        s0, s1 = dict(stages[0]), dict(stages[1])
        s0.update({"start_time": start.isoformat(), "end_time": (start + timedelta(days=1)).isoformat()})
        repos.batches.update_stage(s0["stage_id"], s0)
        s1.update({"start_time": (start + timedelta(days=1)).isoformat(),
                   "end_time": (start + timedelta(days=8)).isoformat()})
        repos.batches.update_stage(s1["stage_id"], s1)
    culture_stage = stages[1]["stage_id"] if len(stages) > 1 else (stages[0]["stage_id"] if stages else None)

    for day, vcd, via, ph, do, temp in [
        (0, 0.5, 98, 7.15, 45, 36.8), (2, 2.1, 97, 7.05, 42, 36.9),
        (4, 5.8, 96, 6.98, 40, 36.8), (6, 11.2, 95, 6.92, 38, 36.7),
        (8, 16.5, 93, 6.88, 36, 36.7),
    ]:
        for name, value, unit in (("VCD", vcd, "×10^6/mL"), ("活率", via, "%"),
                                  ("pH", ph, ""), ("DO", do, "%"), ("温度", temp, "°C")):
            repos.batches.add_parameter(batch_id, {
                "stage_id": culture_stage, "param_name": name, "param_value": value, "unit": unit,
                "recorded_at": (start + timedelta(days=day, hours=2)).isoformat(), "notes": "演示数据",
            })

    pumps = repos.pumps.active()
    liquids = repos.liquids.active()
    liquid_by_code = {l["liquid_code"]: l for l in liquids}
    for pump, liquid_code in zip(pumps, ["FEED_A", "FEED_B", "ALKALI", "ANTIFOAM"]):
        liquid = liquid_by_code.get(liquid_code) or liquids[0]
        repos.batches.add_mapping(batch_id, {
            "pump_id": pump["pump_id"], "liquid_id": liquid["liquid_id"],
            "valid_from": start.isoformat(), "mapping_note": "演示批次绑定",
        })

    plan_id = repos.plans.create(batch_id, "演示用户", copy_latest=False, notes="演示补料计划")
    events = []
    for day in range(1, 8):
        day_start = start + timedelta(days=day)
        for pump, liquid_code, hour, volume, flow in (
                (pumps[0], "FEED_A", 9, 30.0, 10.0),
                (pumps[1], "FEED_B", 9, 15.0, 5.0),
                (pumps[2], "ALKALI", 15, 5.0, 5.0),
                (pumps[3], "ANTIFOAM", 15, 1.0, 1.0)):
            liquid = liquid_by_code.get(liquid_code) or liquids[0]
            begin = day_start.replace(hour=hour, minute=0, second=0, microsecond=0)
            end = begin + timedelta(hours=volume / flow)
            eid = repos.plans.add_event(plan_id, {
                "stage_id": culture_stage, "liquid_id": liquid["liquid_id"], "pump_id": pump["pump_id"],
                "planned_start": begin.isoformat(), "planned_end": end.isoformat(),
                "planned_volume_ml": volume, "target_flow_ml_h": flow,
                "duration_h": volume / flow, "status": "计划", "notes": f"Day {day}",
            })
            events.append({"event_id": eid, "pump_id": pump["pump_id"], "liquid_id": liquid["liquid_id"],
                           "begin": begin, "end": end, "volume": volume, "flow": flow})
    repos.plans.set_status(plan_id, "已确认")

    for pump, scale in zip(pumps, [1.0, 0.98, 1.03, 1.01]):
        points = [{"setpoint_value": rpm, "setpoint_unit": "rpm",
                   "measured_flow": rpm * 0.5 * scale, "flow_unit": "mL/h"}
                  for rpm in (10, 20, 30, 40, 50)]
        cid = repos.calibrations.create(pump["pump_id"], {
            "calibration_date": (start - timedelta(days=3)).date().isoformat(),
            "calibration_status": "待审核", "calibration_method": "my-Control 文件导入",
            "notes": "演示校准",
        }, points, "演示用户")
        repos.calibrations.set_status(cid, "有效")

    csv_path = data_path / "demo_dose_monitor.csv"
    lines = ["时间,泵编号,流速(mL/h),累计体积(mL),状态"]
    totals = {p["pump_id"]: 0.0 for p in pumps}
    current = start
    end_time = start + timedelta(days=8)
    index = 0
    while current <= end_time:
        for pump in pumps:
            flow = 0.0
            for ev in events:
                if ev["pump_id"] == pump["pump_id"] and ev["begin"] <= current <= ev["end"]:
                    flow = ev["flow"]
                    break
            totals[pump["pump_id"]] += flow * 0.5
            total = totals[pump["pump_id"]]
            if pump["pump_code"] == "PUMP_03" and index == 220:
                total = 0.0
                totals[pump["pump_id"]] = 0.0
            status = "RUN" if flow > 0 else "STOP"
            lines.append(f"{current:%Y-%m-%d %H:%M:%S},{pump['pump_code']},{flow:.3f},{total:.3f},{status}")
        current += timedelta(minutes=30)
        index += 1
    csv_path.write_text("\n".join(lines), encoding="utf-8-sig")

    importer = DoseImportService(repos, settings)
    table = importer.read(csv_path)
    mapping = importer.suggest_mapping(table.headers)
    pv = importer.preview(batch_id, csv_path, None, 1, mapping, "mL/h", "mL")
    if pv.errors:
        print("导入错误：", pv.errors[:5])
    import_id = importer.commit(pv, batch_id, "演示用户", notes="演示导入")
    print("导入", import_id, pv.stats)

    for ev in events[-8:]:
        rows = repos.imports.data_for(batch_id, ev["pump_id"],
                                      ev["begin"].isoformat(), ev["end"].isoformat())
        result = dose_calc.calculate(rows, ev["volume"], ev["begin"].isoformat(),
                                     ev["end"].isoformat(), settings.max_sample_gap_h)
        cid = repos.doses.create({
            "batch_id": batch_id, "event_id": ev["event_id"], "pump_id": ev["pump_id"],
            "liquid_id": ev["liquid_id"], "time_start": ev["begin"].isoformat(),
            "time_end": ev["end"].isoformat(), "planned_volume_ml": ev["volume"],
            "actual_volume_ml": result["actual_volume_ml"],
            "flow_integral_ml": result["flow_integral_ml"],
            "deviation_ml": result["deviation_ml"], "deviation_percent": result["deviation_percent"],
            "completion_percent": result["completion_percent"],
            "calculation_method": result["calculation_method"], "quality_status": result["quality_status"],
            "data_import_id": import_id, "notes": "演示核算",
        })
        for anomaly in result["anomalies"][:3]:
            repos.anomalies.create({
                "batch_id": batch_id, "calculation_id": cid, "import_id": import_id,
                "anomaly_type": anomaly["anomaly_type"], "severity": anomaly["severity"],
                "description": anomaly["description"],
            })

    repos.anomalies.create({
        "batch_id": batch_id, "import_id": import_id, "anomaly_type": "采样间隔过长",
        "severity": "警告", "description": "演示异常：第 5 天设备导出中断 3.5 h，需要人工确认。",
    })

    reports = ReportService(repos, settings)
    try:
        reports.generate_excel(batch_id, "演示用户")
        reports.generate_pdf(batch_id, "演示用户")
    except Exception as exc:
        print("报告生成失败：", exc)

    settings.last_batch_id = batch_id
    settings.save()
    print("演示数据已生成：", settings.db_path)
    return settings.db_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(BASE / "DemoData"))
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    seed(args.data_dir, args.reset)
