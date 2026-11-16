# -*- coding: utf-8 -*-
"""补料计划服务: 时长、结束时间、泵时间冲突与累计量。"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence


def duration_h(volume_ml: float | None, flow_ml_h: float | None) -> float | None:
    try:
        v, q = float(volume_ml or 0), float(flow_ml_h or 0)
    except (TypeError, ValueError):
        return None
    if v <= 0 or q <= 0:
        return None
    return v / q


def end_time(start_iso: str | None, hours: float | None) -> str | None:
    if not start_iso or hours is None:
        return None
    try:
        start = datetime.fromisoformat(start_iso)
    except ValueError:
        return None
    return (start + timedelta(hours=float(hours))).replace(microsecond=0).isoformat()


def _overlap(a_start, a_end, b_start, b_end) -> bool:
    if not all((a_start, a_end, b_start, b_end)):
        return False
    return a_start < b_end and b_start < a_end


def find_conflicts(events: Sequence[dict]) -> list[str]:
    """检测同一泵的时间重叠和同泵不同液体。返回可读警告。"""
    messages: list[str] = []
    for i, a in enumerate(events):
        if not a.get("planned_start") or not a.get("planned_end"):
            continue
        for b in events[i + 1:]:
            if a.get("pump_id") != b.get("pump_id"):
                continue
            if _overlap(a["planned_start"], a["planned_end"], b.get("planned_start"), b.get("planned_end")):
                messages.append(
                    f"泵 {a.get('pump_code', a.get('pump_id'))} 的计划时间重叠："
                    f"{a['planned_start']}~{a['planned_end']} 与 {b.get('planned_start')}~{b.get('planned_end')}"
                )
            if a.get("liquid_id") != b.get("liquid_id"):
                messages.append(
                    f"泵 {a.get('pump_code', a.get('pump_id'))} 在同一计划中绑定了不同液体，请确认换液时间"
                )
    return messages


def summarize(events: Sequence[dict]) -> list[dict]:
    totals: dict[str, dict] = {}
    for ev in events:
        key = ev.get("liquid_id") or ""
        item = totals.setdefault(key, {"liquid_id": key, "liquid_name": ev.get("liquid_name", ""),
                                       "volume_ml": 0.0, "events": 0})
        item["volume_ml"] += float(ev.get("planned_volume_ml") or 0)
        item["events"] += 1
    return list(totals.values())
