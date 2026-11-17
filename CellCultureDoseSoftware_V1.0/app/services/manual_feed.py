# -*- coding: utf-8 -*-
"""手工补料记录：保存设备原始读数，独立计算并标记不可比较的数据。"""
from __future__ import annotations

import json
import math

from ..db import new_id, now_iso
from .dose_calc import parse_ts
from .units import UnitError, volume_to_l


def evaluate(data: dict) -> dict:
    """校验原始输入；不完整或异常的读数保留原文并进入待审核。"""
    issues = []

    def time_value(value, label):
        parsed = parse_ts(value)
        if not parsed:
            issues.append(f"{label}缺失或无法解析")
        return parsed

    def volume(value, unit, label, required=True):
        if value is None or str(value).strip() == "":
            if required:
                issues.append(f"{label}未填写")
            return None
        try:
            number = float(value)
            if not math.isfinite(number) or number < 0:
                raise ValueError()
            return volume_to_l(number, unit) * 1000
        except (ValueError, TypeError, UnitError):
            issues.append(f"{label}或单位无效")
            return None

    start = time_value(data.get("start_time"), "开始时间")
    end = time_value(data.get("end_time"), "结束时间")
    if start and end and start >= end:
        issues.append("结束时间必须晚于开始时间")
    unit = str(data.get("reading_unit") or "").strip()
    first = volume(data.get("start_reading"), unit, "开始读数")
    last = volume(data.get("end_reading"), unit, "结束读数")
    points = []
    for line in str(data.get("intermediate_readings") or "").splitlines():
        if not line.strip():
            continue
        parts = line.split(",")
        if len(parts) != 2:
            issues.append("中途读数应为每行：时间,读数")
            continue
        dt = time_value(parts[0].strip(), "中途读数时间")
        val = volume(parts[1].strip(), unit, "中途读数")
        if dt and val is not None:
            points.append((dt, val))
    if start and end and any(not start < dt < end for dt, _ in points):
        issues.append("中途读数时间须在开始和结束之间")
    if any(points[i][0] >= points[i + 1][0] for i in range(len(points) - 1)):
        issues.append("中途读数时间必须递增")
    values = ([first] if first is not None else []) + [v for _, v in points] + ([last] if last is not None else [])
    if any(a > b for a, b in zip(values, values[1:])):
        issues.append("累计读数下降，可能发生归零")
    if data.get("known_reset"):
        issues.append("记录期间已知发生归零，不能直接计算完整剂量")
    measured = volume(data.get("measured_value"), data.get("measured_unit"), "独立实测量", False)
    if measured is not None and not str(data.get("measured_method") or "").strip():
        issues.append("独立实测量缺少测量方法")
    return {"estimate_ml": last - first if not issues and first is not None and last is not None else None,
            "measured_ml": measured, "quality_status": "待审核" if issues else "有效", "issues": issues}


class ManualFeedService:
    def __init__(self, db):
        self.db = db

    def save(self, data: dict, operator: str, start_only: bool = False) -> str:
        for key in ("batch_id", "pump_id", "liquid_id"):
            if not data.get(key):
                raise ValueError("请选择批次、泵和补料液")
        if start_only and self.db.scalar("SELECT status FROM batch_info WHERE batch_id=?", (data['batch_id'],)) != "进行中":
            raise ValueError("只能在进行中的批次开始补料")
        event_id = data.get("event_id") or None
        planned = None
        if event_id:
            event = self.db.q1("SELECT e.*, p.batch_id FROM feed_plan_event e JOIN feed_plan p ON p.plan_id=e.plan_id WHERE e.event_id=?", (event_id,))
            if not event or (event["batch_id"], event["pump_id"], event["liquid_id"]) != (data["batch_id"], data["pump_id"], data["liquid_id"]):
                raise ValueError("关联事件必须属于当前批次，并与所选泵、液体一致")
            planned = event["planned_volume_ml"]
        result = evaluate(data)
        if start_only:
            if str(data.get("end_time") or "").strip() or str(data.get("end_reading") or "").strip():
                raise ValueError("开始补料时请清空结束时间和结束读数；补录完整记录请使用保存完整记录")
            start_check = evaluate({**data, "end_time": data.get("start_time"), "end_reading": data.get("start_reading")})
            invalid = [item for item in start_check["issues"] if item != "结束时间必须晚于开始时间"]
            if invalid:
                raise ValueError("开始记录无效：" + "；".join(invalid))
            result.update(estimate_ml=None, quality_status="进行中", issues=[])
        record_id = new_id("MAN")
        fields = ("batch_id", "pump_id", "liquid_id", "start_time", "end_time", "start_reading", "end_reading", "reading_unit",
                  "intermediate_readings", "measured_value", "measured_unit", "measured_method", "equipment_notes", "notes")
        values = [str(data.get(k) if data.get(k) is not None else "").strip() for k in fields]
        with self.db.transaction() as cur:
            cur.execute("INSERT INTO manual_feed_record(record_id,event_id,planned_volume_ml,estimate_ml,measured_ml,quality_status,issues,created_at,created_by,known_reset,lifecycle_status," + ",".join(fields) + ") VALUES (" + ",".join(["?"] * (11 + len(fields))) + ")",
                        [record_id, event_id, planned, result["estimate_ml"], result["measured_ml"], result["quality_status"], json.dumps(result["issues"], ensure_ascii=False), now_iso(), operator, int(bool(data.get("known_reset"))), "进行中" if start_only else "已完成"] + values)
        return record_id

    def update_record(self, record_id: str, changes: dict, operator: str, reason: str = "") -> None:
        """结束或更正记录，原值、新值和修改人写入同一个事务。"""
        if not operator.strip():
            raise ValueError("请填写操作人")
        with self.db.transaction() as cur:
            row = cur.execute("SELECT * FROM manual_feed_record WHERE record_id=?", (record_id,)).fetchone()
            if row is None:
                raise ValueError("记录不存在")
            old = dict(row)
            if old["lifecycle_status"] != "进行中" and not reason.strip():
                raise ValueError("更正已结束记录时必须填写原因")
            allowed = ("start_time", "end_time", "start_reading", "end_reading", "reading_unit", "intermediate_readings", "measured_value", "measured_unit", "measured_method", "equipment_notes", "notes", "known_reset")
            updated = {**old, **{k: changes[k] for k in allowed if k in changes}}
            if old["lifecycle_status"] == "进行中" and (not str(updated.get("end_time") or "").strip() or updated.get("end_reading") is None or not str(updated["end_reading"]).strip()):
                raise ValueError("请填写结束时间和结束读数，或注明原因标记为未完成")
            result = evaluate(updated)
            updated.update(result, lifecycle_status="已完成")
            assignments = allowed + ("estimate_ml", "measured_ml", "quality_status", "lifecycle_status")
            cur.execute("UPDATE manual_feed_record SET " + ",".join(f"{k}=?" for k in assignments) + ",issues=? WHERE record_id=?",
                        [updated.get(k) for k in assignments] + [json.dumps(result["issues"], ensure_ascii=False), record_id])
            final = dict(cur.execute("SELECT * FROM manual_feed_record WHERE record_id=?", (record_id,)).fetchone())
            cur.execute("INSERT INTO manual_feed_revision VALUES(?,?,?,?,?,?,?,?)", (new_id("REV"), record_id, "结束补料" if old["lifecycle_status"] == "进行中" else "更正", json.dumps(old, ensure_ascii=False), json.dumps(final, ensure_ascii=False), reason.strip(), operator.strip(), now_iso()))

    def mark_incomplete(self, record_id: str, operator: str, reason: str) -> None:
        if not operator.strip() or not reason.strip():
            raise ValueError("请填写操作人和未完成原因")
        with self.db.transaction() as cur:
            row = cur.execute("SELECT * FROM manual_feed_record WHERE record_id=?", (record_id,)).fetchone()
            if not row or row["lifecycle_status"] != "进行中":
                raise ValueError("只能将进行中的记录标为未完成")
            old = dict(row)
            issues = json.dumps(["未完成：" + reason.strip()], ensure_ascii=False)
            cur.execute("UPDATE manual_feed_record SET lifecycle_status='未完成',quality_status='待审核',estimate_ml=NULL,issues=? WHERE record_id=?", (issues, record_id))
            final = dict(cur.execute("SELECT * FROM manual_feed_record WHERE record_id=?", (record_id,)).fetchone())
            cur.execute("INSERT INTO manual_feed_revision VALUES(?,?,?,?,?,?,?,?)", (new_id("REV"), record_id, "标记未完成", json.dumps(old, ensure_ascii=False), json.dumps(final, ensure_ascii=False), reason.strip(), operator.strip(), now_iso()))

    def list_for_batch(self, batch_id: str) -> list[dict]:
        return [dict(row) for row in self.db.q("SELECT m.*, p.pump_code, l.liquid_name FROM manual_feed_record m JOIN pump_info p ON p.pump_id=m.pump_id JOIN liquid_info l ON l.liquid_id=m.liquid_id WHERE m.batch_id=? ORDER BY m.created_at DESC", (batch_id,))]
