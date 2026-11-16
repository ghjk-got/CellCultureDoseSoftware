# -*- coding: utf-8 -*-
"""实际剂量核算服务：计数区段、累计体积差、梯形积分、偏差与完成率。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from .units import UnitError, flow_to_ml_h

RESET_WORDS = {"RESET", "CLEAR", "归零", "清零", "重置"}


def parse_ts(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.astimezone()
    text = str(value).strip().replace("Z", "+00:00")
    text = text.replace("/", "-")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
            try:
                dt = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return dt if dt.tzinfo else dt.astimezone()


def iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone().replace(microsecond=0).isoformat()


def _num(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def dedupe_and_flag(rows: Sequence[dict]) -> tuple[list[dict], list[dict]]:
    """按时间排序，重复时间保留最后一条并记录异常。"""
    parsed = []
    for row in rows:
        dt = parse_ts(row.get("timestamp_utc"))
        if dt is None:
            continue
        copy = dict(row)
        copy["_dt"] = dt
        parsed.append(copy)
    parsed.sort(key=lambda r: r["_dt"])
    result: list[dict] = []
    issues: list[dict] = []
    for row in parsed:
        if result and row["_dt"] == result[-1]["_dt"]:
            issues.append({
                "anomaly_type": "重复时间戳",
                "severity": "警告",
                "description": f"时间 {iso(row['_dt'])} 存在重复记录，核算时保留最后一条",
            })
            result[-1] = row
        else:
            result.append(row)
    return result, issues


def detect_segments(rows: Sequence[dict]) -> tuple[list[dict], list[dict]]:
    """识别累计体积下降或泵状态重置形成的计数区段。"""
    clean, issues = dedupe_and_flag(rows)
    segment = 1
    prev_total: float | None = None
    prev_dt: datetime | None = None
    out: list[dict] = []
    for row in clean:
        total = _num(row.get("total_volume"))
        status = str(row.get("pump_status") or "").strip().upper()
        flags = str(row.get("quality_flags") or "").upper()
        reset = any(word in status for word in RESET_WORDS) or "RESET" in flags
        decreased = (prev_total is not None and total is not None and total < prev_total - max(0.001, abs(prev_total) * 1e-6))
        if reset or decreased:
            segment += 1
            reason = "泵状态重置" if reset else f"累计体积下降（{prev_total:g} → {total:g}）"
            issues.append({
                "anomaly_type": "计数器重置/分段",
                "severity": "警告",
                "description": f"{iso(row['_dt'])} 检测到{reason}，已切分为第 {segment} 计数区段",
            })
        copy = dict(row)
        copy["counter_segment"] = segment
        out.append(copy)
        if total is not None:
            prev_total = total
        prev_dt = row["_dt"]
    return out, issues


def cumulative_volume(rows: Sequence[dict]) -> dict:
    """同一计数区段内计算末值减首值，跨区段求和。"""
    groups: dict[int, list[dict]] = {}
    for row in rows:
        groups.setdefault(int(row.get("counter_segment") or 1), []).append(row)
    total = 0.0
    used_groups = 0
    parts: list[dict] = []
    for seg, items in sorted(groups.items()):
        vals = [(r["_dt"], _num(r.get("total_volume"))) for r in items]
        vals = [(dt, v) for dt, v in vals if v is not None]
        if len(vals) < 2:
            continue
        first_dt, first_v = vals[0]
        last_dt, last_v = vals[-1]
        diff = last_v - first_v
        if diff < 0:
            continue
        total += diff
        used_groups += 1
        parts.append({"segment": seg, "start": iso(first_dt), "end": iso(last_dt),
                      "start_volume": first_v, "end_volume": last_v, "volume_ml": diff})
    return {"volume_ml": total if used_groups else None, "segments_used": used_groups, "parts": parts}


def flow_integral(rows: Sequence[dict], max_gap_h: float = 2.0) -> dict:
    """梯形积分：V = Σ (Q_i + Q_i+1)/2 * Δt。长时间断点跳过并记录。"""
    total = 0.0
    used = 0
    gaps: list[dict] = []
    skipped = 0
    previous: tuple[datetime, float] | None = None
    for row in rows:
        flow = _num(row.get("flow_rate"))
        if flow is None:
            previous = None
            skipped += 1
            continue
        try:
            flow_ml_h = flow_to_ml_h(flow, row.get("flow_unit") or "mL/h")
        except UnitError:
            previous = None
            skipped += 1
            continue
        dt = row["_dt"]
        if previous is not None:
            dt_h = (dt - previous[0]).total_seconds() / 3600.0
            if dt_h < 0:
                previous = (dt, flow_ml_h)
                continue
            if dt_h > max_gap_h:
                gaps.append({"from": iso(previous[0]), "to": iso(dt), "hours": round(dt_h, 4)})
                previous = (dt, flow_ml_h)
                continue
            total += (previous[1] + flow_ml_h) / 2.0 * dt_h
            used += 1
        previous = (dt, flow_ml_h)
    return {"volume_ml": total if used else None, "interval_count": used,
            "gaps": gaps, "skipped_points": skipped}


def calculate(rows: Sequence[dict], planned_ml: float | None,
              start: str | None = None, end: str | None = None,
              max_gap_h: float = 2.0) -> dict:
    """完整核算。rows 为标准化剂量数据；start/end 可限制时间窗口。"""
    start_dt, end_dt = parse_ts(start), parse_ts(end)
    if start_dt and end_dt and start_dt > end_dt:
        return {"quality_status": "无效", "message": "核算开始时间晚于结束时间",
                "anomalies": [{"anomaly_type": "时间窗口无效", "severity": "错误",
                               "description": "核算开始时间晚于结束时间"}]}
    window = []
    for row in rows:
        dt = parse_ts(row.get("timestamp_utc"))
        if dt is None:
            continue
        if start_dt and dt < start_dt:
            continue
        if end_dt and dt > end_dt:
            continue
        copy = dict(row)
        copy["_dt"] = dt
        window.append(copy)

    segments, seg_issues = detect_segments(window)
    anomalies = list(seg_issues)
    cumulative = cumulative_volume(segments)
    integral = flow_integral(segments, max_gap_h)
    for gap in integral["gaps"]:
        anomalies.append({
            "anomaly_type": "数据断点",
            "severity": "警告",
            "description": f"{gap['from']} 至 {gap['to']} 采样间隔 {gap['hours']} h 超过允许值 {max_gap_h:g} h，"
                           f"流速积分跳过该区间",
        })

    actual = cumulative["volume_ml"]
    integral_ml = integral["volume_ml"]
    warnings: list[str] = []
    if actual is not None and integral_ml is not None and actual > 1e-9:
        ratio = abs(integral_ml - actual) / actual
        if ratio > 0.2:
            warnings.append(f"累计体积差与流速积分相差 {ratio * 100:.1f}%，建议核对校准与数据源")
            anomalies.append({
                "anomaly_type": "核算方法差异",
                "severity": "警告",
                "description": f"累计体积差 {actual:.3f} mL 与流速积分 {integral_ml:.3f} mL 相差 {ratio * 100:.1f}%",
            })

    planned = _num(planned_ml)
    deviation = completion = deviation_pct = None
    if actual is not None and planned is not None and planned > 0:
        deviation = actual - planned
        deviation_pct = deviation / planned * 100.0
        completion = actual / planned * 100.0

    if not window:
        quality = "无效"
        method = "无数据"
    elif actual is None and integral_ml is None:
        quality = "无效"
        method = "数据不足"
    elif actual is None:
        quality = "估算"
        method = "流速积分"
    else:
        method = "累计体积差" + ("+流速积分校验" if integral_ml is not None else "")
        blocking = any(a["severity"] in ("错误", "警告") for a in anomalies)
        quality = "待审核" if blocking else "有效"

    first = segments[0]["_dt"] if segments else None
    last = segments[-1]["_dt"] if segments else None
    return {
        "quality_status": quality,
        "calculation_method": method,
        "actual_volume_ml": actual,
        "flow_integral_ml": integral_ml,
        "planned_volume_ml": planned,
        "deviation_ml": deviation,
        "deviation_percent": deviation_pct,
        "completion_percent": completion,
        "point_count": len(window),
        "segment_count": cumulative["segments_used"],
        "segments": cumulative["parts"],
        "coverage_start": iso(first),
        "coverage_end": iso(last),
        "gaps": integral["gaps"],
        "warnings": warnings,
        "anomalies": anomalies,
        "message": "；".join(warnings) if warnings else "",
    }
