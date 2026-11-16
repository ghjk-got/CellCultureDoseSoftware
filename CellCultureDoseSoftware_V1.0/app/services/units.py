# -*- coding: utf-8 -*-
"""单位换算服务：所有计算先转换到内部标准单位。"""
from __future__ import annotations

import math
from typing import Any

ALIASES = {
    "克": "g", "毫克": "mg", "微克": "ug", "千克": "kg",
    "升": "L", "毫升": "mL", "微升": "uL",
    "小时": "h", "分钟": "min", "秒": "s", "天": "d",
    "转/分": "rpm", "转每分钟": "rpm", "%": "%",
}

MASS = {"g": 1.0, "mg": 1e-3, "ug": 1e-6, "kg": 1e3, "ng": 1e-9}
VOLUME = {"L": 1.0, "mL": 1e-3, "uL": 1e-6, "dL": 1e-1}
TIME = {"h": 1.0, "min": 1 / 60, "s": 1 / 3600, "d": 24.0}
MASS_CONC = {"g/L": 1.0, "mg/L": 1e-3, "ug/L": 1e-6, "ng/L": 1e-9,
             "g/mL": 1e3, "mg/mL": 1.0, "ug/mL": 1e-3, "ng/mL": 1e-6}
MOLAR_CONC = {"mol/L": 1.0, "M": 1.0, "mmol/L": 1e-3, "mM": 1e-3,
              "umol/L": 1e-6, "uM": 1e-6, "nmol/L": 1e-9, "nM": 1e-9}
FLOW = {"mL/h": 1.0, "mL/min": 60.0, "mL/s": 3600.0, "L/h": 1000.0,
        "L/min": 60000.0, "L/s": 3600000.0, "uL/min": 0.06, "uL/h": 0.001}
COUNT = {"rpm": 1.0, "%": 1.0, "Hz": 1.0, "档": 1.0}


class UnitError(ValueError):
    pass


def norm(unit: str | None) -> str:
    if unit is None:
        return ""
    u = str(unit).strip().replace("μ", "u").replace("µ", "u")
    u = ALIASES.get(u, u)
    if u.lower() == "ml":
        u = "mL"
    if u.lower() == "ul":
        u = "uL"
    if u.lower() == "l":
        u = "L"
    return u


def _factor(table: dict[str, float], unit: str, kind: str) -> float:
    u = norm(unit)
    if u not in table:
        raise UnitError(f"不支持{kind}单位：{unit or '空'}")
    return table[u]


def unit_kind(unit: str | None) -> str | None:
    u = norm(unit)
    if u in MASS:
        return "mass"
    if u in VOLUME:
        return "volume"
    if u in TIME:
        return "time"
    if u in MASS_CONC:
        return "mass_conc"
    if u in MOLAR_CONC:
        return "molar_conc"
    if u in FLOW:
        return "flow"
    if u in COUNT:
        return "count"
    return None


def mass_to_g(value: float, unit: str) -> float:
    return float(value) * _factor(MASS, unit, "质量")


def volume_to_l(value: float, unit: str) -> float:
    return float(value) * _factor(VOLUME, unit, "体积")


def volume_from_l(value_l: float, unit: str) -> float:
    return float(value_l) / _factor(VOLUME, unit, "体积")


def time_to_h(value: float, unit: str) -> float:
    return float(value) * _factor(TIME, unit, "时间")


def flow_to_ml_h(value: float, unit: str) -> float:
    return float(value) * _factor(FLOW, unit, "流速")


def flow_from_ml_h(value_ml_h: float, unit: str) -> float:
    return float(value_ml_h) / _factor(FLOW, unit, "流速")


def mass_conc_to_g_l(value: float, unit: str) -> float:
    return float(value) * _factor(MASS_CONC, unit, "质量浓度")


def molar_conc_to_mol_l(value: float, unit: str) -> float:
    return float(value) * _factor(MOLAR_CONC, unit, "摩尔浓度")


def concentration_to_g_l(value: float, unit: str, molecular_weight: float | None = None) -> float:
    """质量浓度或摩尔浓度统一换算为 g/L。摩尔浓度必须提供分子量。"""
    kind = unit_kind(unit)
    if kind == "mass_conc":
        return mass_conc_to_g_l(value, unit)
    if kind == "molar_conc":
        mw = float(molecular_weight or 0)
        if mw <= 0:
            raise UnitError("摩尔浓度换算需要有效的分子量（g/mol）")
        return molar_conc_to_mol_l(value, unit) * mw
    raise UnitError(f"不支持的浓度单位：{unit or '空'}")


def is_concentration(unit: str | None) -> bool:
    return unit_kind(unit) in ("mass_conc", "molar_conc")


def fmt(value: Any, digits: int = 4, unit: str = "") -> str:
    if value is None or value == "":
        return "—"
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    if math.isnan(v) or math.isinf(v):
        return "—"
    if abs(v) >= 1000:
        s = f"{v:,.2f}"
    elif abs(v) >= 10:
        s = f"{v:,.3f}".rstrip("0").rstrip(".")
    elif abs(v) >= 0.01:
        s = f"{v:.4f}".rstrip("0").rstrip(".")
    else:
        s = f"{v:.6g}"
    return f"{s} {unit}".strip()
