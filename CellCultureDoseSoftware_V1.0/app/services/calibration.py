# -*- coding: utf-8 -*-
"""泵校准服务：测量区间内线性插值、范围检查与单位一致性检查。"""
from __future__ import annotations

from typing import Sequence

from .units import UnitError, flow_to_ml_h, norm


def point_flow_ml_h(point: dict) -> float | None:
    flow = point.get("measured_flow")
    unit = point.get("flow_unit") or "mL/h"
    try:
        if flow not in (None, ""):
            return flow_to_ml_h(float(flow), unit)
    except (UnitError, TypeError, ValueError):
        return None
    vol = point.get("measured_volume")
    dur = point.get("run_duration")
    dunit = point.get("duration_unit") or "h"
    if vol not in (None, "") and dur not in (None, ""):
        try:
            seconds = float(dur)
            if dunit in ("s", "sec", "秒"):
                hours = seconds / 3600.0
            elif dunit in ("min", "分钟"):
                hours = seconds / 60.0
            else:
                hours = float(dur)
            if hours > 0:
                return flow_to_ml_h(float(vol) / hours, unit)
        except (UnitError, TypeError, ValueError, ZeroDivisionError):
            return None
    return None


def interpolate(points: Sequence[dict], setpoint: float) -> dict:
    """返回 {flow_ml_h, in_range, message, x1,x2,y1,y2}；超出范围不插值。"""
    if not points:
        return {"flow_ml_h": None, "in_range": False, "message": "没有校准点，无法插值"}
    units = {norm(p.get("setpoint_unit") or "") for p in points}
    if len(units) != 1:
        return {"flow_ml_h": None, "in_range": False,
                "message": f"校准点设置值单位不一致：{'、'.join(sorted(units))}"}
    prepared = []
    for p in points:
        flow = point_flow_ml_h(p)
        try:
            x = float(p.get("setpoint_value"))
        except (TypeError, ValueError):
            continue
        if flow is None:
            continue
        prepared.append((x, flow))
    prepared.sort(key=lambda t: t[0])
    if len(prepared) < 2:
        return {"flow_ml_h": None, "in_range": False, "message": "有效校准点不足 2 个，无法插值"}
    xs = [p[0] for p in prepared]
    if len(set(xs)) != len(xs):
        return {"flow_ml_h": None, "in_range": False, "message": "存在重复的设置值，无法插值"}
    if setpoint < xs[0] - 1e-12 or setpoint > xs[-1] + 1e-12:
        return {"flow_ml_h": None, "in_range": False,
                "message": f"设置值 {setpoint:g} 超出校准范围 {xs[0]:g}~{xs[-1]:g}，不进行外推"}
    for i in range(len(prepared) - 1):
        x1, y1 = prepared[i]
        x2, y2 = prepared[i + 1]
        if x1 <= setpoint <= x2:
            if abs(x2 - x1) < 1e-12:
                return {"flow_ml_h": None, "in_range": False, "message": "相邻校准点设置值相同"}
            flow = y1 + (setpoint - x1) / (x2 - x1) * (y2 - y1)
            return {"flow_ml_h": flow, "in_range": True,
                    "message": f"在校准区间 {x1:g}~{x2:g} 内线性插值",
                    "x1": x1, "x2": x2, "y1": y1, "y2": y2}
    return {"flow_ml_h": None, "in_range": False, "message": "无法定位校准区间"}
