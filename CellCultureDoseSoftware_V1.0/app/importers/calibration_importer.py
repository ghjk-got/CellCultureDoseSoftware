# -*- coding: utf-8 -*-
"""my-Control 泵校准文件导入适配器。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from ..repositories import Repositories
from ..services.units import UnitError, flow_to_ml_h, time_to_h
from .common import archive_copy, sha256_file
from .table_reader import CALIBRATION_SYNONYMS, TableData, auto_map, read_table, split_number_unit

SOURCE_TYPE = "my-Control"


@dataclass
class CalibrationPreview:
    table: TableData
    mapping: dict[str, int]
    points: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def blocking(self) -> bool:
        return bool(self.errors)


class CalibrationImportService:
    def __init__(self, repos: Repositories, settings):
        self.repos = repos
        self.settings = settings

    def suggest_mapping(self, headers: Sequence[str]) -> dict[str, int]:
        return auto_map(headers, CALIBRATION_SYNONYMS)

    def preview(self, path: str | Path, sheet: str | None, header_row: int,
                mapping: dict[str, int], default_setpoint_unit: str = "rpm",
                default_flow_unit: str = "mL/h", default_duration_unit: str = "min") -> CalibrationPreview:
        table = read_table(path, sheet=sheet, header_row=header_row)
        pv = CalibrationPreview(table=table, mapping=dict(mapping))
        seen: set[float] = set()
        for offset, row in enumerate(table.rows):
            row_no = header_row + 1 + offset
            get = lambda field: row[mapping[field]] if field in mapping and mapping[field] < len(row) else None

            setpoint, embedded_sp_unit = split_number_unit(get("setpoint_value"))
            if setpoint is None:
                pv.errors.append({"row": row_no, "field": "设置值", "message": "设置值缺失或无法解析"})
                continue
            if setpoint in seen:
                pv.warnings.append(f"第 {row_no} 行设置值 {setpoint:g} 重复，插值前请确认")
            seen.add(setpoint)
            setpoint_unit = str(get("setpoint_unit") or embedded_sp_unit or default_setpoint_unit).strip()

            flow, embedded_flow_unit = split_number_unit(get("measured_flow"))
            flow_unit = str(get("flow_unit") or embedded_flow_unit or default_flow_unit).strip()
            volume, embedded_vol_unit = split_number_unit(get("measured_volume"))
            duration, embedded_dur_unit = split_number_unit(get("run_duration"))
            duration_unit = str(get("duration_unit") or embedded_dur_unit or default_duration_unit).strip()

            if flow is None and not (volume is not None and duration):
                pv.errors.append({"row": row_no, "field": "实测流速",
                                  "message": "实测流速缺失，且实测体积/运行时长不足以计算流速"})
                continue
            if flow is not None:
                try:
                    flow_to_ml_h(flow, flow_unit)
                except UnitError as exc:
                    pv.errors.append({"row": row_no, "field": "流速单位", "message": str(exc)})
                    continue
            if flow is None and volume is not None and duration:
                try:
                    hours = time_to_h(duration, duration_unit)
                except UnitError as exc:
                    pv.errors.append({"row": row_no, "field": "时长单位", "message": str(exc)})
                    continue
                if hours <= 0:
                    pv.errors.append({"row": row_no, "field": "运行时长", "message": "运行时长必须大于 0"})
                    continue
                flow = volume / hours
                flow_unit = embedded_vol_unit or default_flow_unit

            pv.points.append({
                "setpoint_value": setpoint,
                "setpoint_unit": setpoint_unit,
                "measured_flow": flow,
                "flow_unit": flow_unit,
                "measured_volume": volume,
                "run_duration": duration,
                "duration_unit": duration_unit if duration is not None else None,
            })
        if len(pv.points) < 2:
            pv.warnings.append("有效校准点少于 2 个，保存后将无法进行插值核算")
        return pv

    def commit(self, pump_id: str, pv: CalibrationPreview, user: str,
               calibration_date: str | None = None, notes: str = "") -> str:
        if pv.errors:
            raise ValueError("存在阻断错误，不能保存校准记录")
        if not pv.points:
            raise ValueError("没有有效校准点")
        pump = self.repos.pumps.get(pump_id)
        if not pump:
            raise ValueError("泵不存在")
        digest = sha256_file(pv.table.path)
        archived = archive_copy(pv.table.path, self.settings.data_dir,
                                f"PUMP_{pump['pump_code']}", "my_control")
        import_id = self.repos.imports.create({
            "batch_id": None,
            "source_type": SOURCE_TYPE,
            "original_filename": pv.table.path.name,
            "archived_path": str(archived),
            "file_hash": digest,
            "imported_by": user,
            "row_count": len(pv.table.rows),
            "success_count": len(pv.points),
            "error_count": len(pv.errors),
            "mapping_config": {field: pv.table.headers[idx] for field, idx in pv.mapping.items() if idx < len(pv.table.headers)},
            "import_status": "部分成功" if pv.warnings else "成功",
            "notes": notes,
        })
        calibration_id = self.repos.calibrations.create(
            pump_id,
            {"calibration_date": calibration_date, "source_file_id": import_id,
             "calibration_status": "待审核", "calibration_method": "my-Control 文件导入",
             "notes": notes},
            pv.points,
            user,
        )
        return calibration_id
