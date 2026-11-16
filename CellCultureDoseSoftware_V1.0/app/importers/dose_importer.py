# -*- coding: utf-8 -*-
"""Dose Monitor 导入适配器：字段映射、标准化、质量检查与归档。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from ..db import new_id
from ..repositories import Repositories
from ..services import dose_calc
from ..services.units import UnitError, flow_to_ml_h, volume_to_l
from .common import archive_copy, normalize_timestamp, sha256_file
from .table_reader import TableData, auto_map, read_table, split_number_unit

SOURCE_TYPE = "Dose Monitor"


@dataclass
class Preview:
    table: TableData
    mapping: dict[str, int]
    normalized: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return bool(self.errors)


class DoseImportService:
    def __init__(self, repos: Repositories, settings):
        self.repos = repos
        self.settings = settings

    # ---------- 解析与预览 ----------
    def read(self, path: str | Path, sheet: str | None = None, header_row: int = 1) -> TableData:
        return read_table(path, sheet=sheet, header_row=header_row)

    def suggest_mapping(self, headers: Sequence[str]) -> dict[str, int]:
        return auto_map(headers)

    def preview(self, batch_id: str, path: str | Path, sheet: str | None, header_row: int,
                mapping: dict[str, int], default_flow_unit: str = "mL/h",
                default_volume_unit: str = "mL") -> Preview:
        table = self.read(path, sheet, header_row)
        pv = Preview(table=table, mapping=dict(mapping))
        prev_by_pump: dict[str, tuple[str, float | None]] = {}
        pump_counter: dict[str, int] = {}
        for offset, row in enumerate(table.rows):
            row_no = header_row + 1 + offset
            get = lambda field: row[mapping[field]] if field in mapping and mapping[field] < len(row) else None

            ts_raw = get("timestamp")
            ts = normalize_timestamp(ts_raw)
            if ts is None:
                pv.errors.append({"row": row_no, "field": "时间", "message": f"无法解析时间戳：{ts_raw!r}"})
                continue

            pump_code = str(get("pump_code") or "").strip()
            if not pump_code:
                pv.errors.append({"row": row_no, "field": "泵编号", "message": "泵编号缺失"})
                continue
            pump = self.repos.pumps.by_code(pump_code)
            if pump is None and pump_code.isdigit():
                pump = self.repos.pumps.by_code(f"PUMP_{int(pump_code):02d}")
            if pump is None:
                pv.errors.append({"row": row_no, "field": "泵编号", "message": f"未登记的泵编号：{pump_code}"})
                continue

            flow_raw = get("flow_rate")
            flow, embedded_flow_unit = split_number_unit(flow_raw)
            flow_unit = str(get("flow_unit") or embedded_flow_unit or default_flow_unit).strip()
            if flow is not None:
                try:
                    flow = flow_to_ml_h(flow, flow_unit)
                    flow_unit = "mL/h"
                except UnitError as exc:
                    pv.errors.append({"row": row_no, "field": "流速单位", "message": str(exc)})
                    flow, flow_unit = None, None

            total_raw = get("total_volume")
            total, embedded_vol_unit = split_number_unit(total_raw)
            volume_unit = str(get("volume_unit") or embedded_vol_unit or default_volume_unit).strip()
            if total is not None:
                try:
                    total = volume_to_l(total, volume_unit) * 1000.0
                    volume_unit = "mL"
                except UnitError as exc:
                    pv.errors.append({"row": row_no, "field": "体积单位", "message": str(exc)})
                    total, volume_unit = None, None
            if total is None and flow is None:
                pv.errors.append({"row": row_no, "field": "剂量", "message": "流速与累计体积均缺失或无法解析"})
                continue

            status = str(get("pump_status") or "").strip()
            flags: list[str] = []
            prev = prev_by_pump.get(pump["pump_id"])
            if prev:
                prev_ts, prev_total = prev
                if total is not None and prev_total is not None and total < prev_total - 1e-9:
                    flags.append("累计体积下降")
                    pv.warnings.append({"row": row_no, "type": "累计体积下降",
                                        "message": f"累计体积由 {prev_total:g} 降至 {total:g} {volume_unit}，可能是计数器重置"})
                gap_h = (dose_calc.parse_ts(ts) - dose_calc.parse_ts(prev_ts)).total_seconds() / 3600.0
                if gap_h > float(self.settings.max_sample_gap_h):
                    flags.append("采样间隔过长")
                    pv.warnings.append({"row": row_no, "type": "数据断点",
                                        "message": f"与上一条记录间隔 {gap_h:.2f} h，超过允许值 {self.settings.max_sample_gap_h:g} h"})
            if flow is not None and flow < 0:
                flags.append("流速为负")
                pv.warnings.append({"row": row_no, "type": "流速异常", "message": f"流速为负值：{flow:g} {flow_unit}"})
            prev_by_pump[pump["pump_id"]] = (ts, total if total is not None else (prev[1] if prev else None))
            pump_counter[pump["pump_code"]] = pump_counter.get(pump["pump_code"], 0) + 1

            pv.normalized.append({
                "batch_id": batch_id,
                "pump_id": pump["pump_id"],
                "pump_code": pump["pump_code"],
                "timestamp_utc": ts,
                "flow_rate": flow,
                "flow_unit": flow_unit if flow is not None else None,
                "total_volume": total,
                "volume_unit": volume_unit if total is not None else None,
                "pump_status": status,
                "counter_segment": 1,
                "quality_flags": ";".join(flags),
                "raw_row_no": row_no,
            })

        pv.stats = {
            "total_rows": len(table.rows),
            "success_rows": len(pv.normalized),
            "error_rows": len(pv.errors),
            "warning_rows": len(pv.warnings),
            "pump_counts": pump_counter,
            "time_start": min((r["timestamp_utc"] for r in pv.normalized), default=None),
            "time_end": max((r["timestamp_utc"] for r in pv.normalized), default=None),
        }
        return pv

    # ---------- 重复检查与提交 ----------
    def duplicate_import(self, batch_id: str, path: str | Path) -> dict | None:
        digest = sha256_file(path)
        row = self.repos.db.q1(
            "SELECT * FROM import_record WHERE batch_id=? AND file_hash=? AND source_type=? "
            "ORDER BY imported_at DESC LIMIT 1", (batch_id, digest, SOURCE_TYPE))
        return None if row is None else dict(row)

    def commit(self, pv: Preview, batch_id: str, user: str, notes: str = "",
               allow_duplicate: bool = False) -> str:
        if pv.errors:
            raise ValueError("存在阻断错误，不能确认导入")
        if not pv.normalized:
            raise ValueError("没有可导入的有效数据行")
        duplicate = self.duplicate_import(batch_id, pv.table.path)
        if duplicate and not allow_duplicate:
            raise ValueError(f"该文件已于 {duplicate['imported_at']} 导入过（导入编号 {duplicate['import_id']}）")
        batch = self.repos.batches.get(batch_id)
        batch_code = batch["batch_code"] if batch else "UNASSIGNED"
        archived = archive_copy(pv.table.path, self.settings.data_dir, batch_code, "dose_monitor")
        digest = sha256_file(pv.table.path)
        mapping_config = {field: pv.table.headers[idx] for field, idx in pv.mapping.items() if idx < len(pv.table.headers)}
        import_id = self.repos.imports.create({
            "batch_id": batch_id,
            "source_type": SOURCE_TYPE,
            "original_filename": pv.table.path.name,
            "archived_path": str(archived),
            "file_hash": digest,
            "imported_by": user,
            "row_count": pv.stats.get("total_rows", len(pv.table.rows)),
            "success_count": pv.stats.get("success_rows", 0),
            "error_count": pv.stats.get("error_rows", 0),
            "mapping_config": mapping_config,
            "import_status": "部分成功" if pv.warnings else "成功",
            "notes": notes,
        })
        payload = []
        for row in pv.normalized:
            copy = dict(row)
            copy["import_id"] = import_id
            copy["dose_row_id"] = new_id("DOSE")
            payload.append(copy)
        self.repos.imports.insert_normalized(payload)
        for i, warning in enumerate(pv.warnings[:500]):
            self.repos.anomalies.create({
                "batch_id": batch_id,
                "import_id": import_id,
                "anomaly_type": warning.get("type", "导入警告"),
                "severity": "警告",
                "description": f"导入 {pv.table.path.name} 第 {warning.get('row')} 行：{warning.get('message')}",
            })
        return import_id
