# -*- coding: utf-8 -*-
"""配方计算服务：目标浓度、纯度修正、母液稀释与定容补足。"""
from __future__ import annotations

from typing import Any, Sequence

from .units import UnitError, concentration_to_g_l, volume_to_l


def calculate_line(detail: dict, target_volume_l: float) -> dict:
    """计算单个组分的理论用量、纯度修正用量与母液体积。

    detail 字段：target_concentration, concentration_unit, molecular_weight,
    purity_fraction, source_type, stock_concentration, stock_unit。
    """
    warnings: list[str] = []
    errors: list[str] = []
    result = {
        "detail_id": detail.get("detail_id"),
        "component_id": detail.get("component_id"),
        "component_code": detail.get("component_code", ""),
        "component_name": detail.get("component_name", ""),
        "target_concentration": detail.get("target_concentration"),
        "concentration_unit": detail.get("concentration_unit"),
        "source_type": detail.get("source_type", "直接称量"),
        "theoretical_amount_g": None,
        "corrected_amount_g": None,
        "stock_volume_ml": None,
        "warnings": warnings,
        "errors": errors,
    }
    try:
        target = float(detail.get("target_concentration") or 0)
    except (TypeError, ValueError):
        errors.append("目标浓度不是有效数值")
        return result
    if target <= 0:
        errors.append("目标浓度必须大于 0")
        return result
    if target_volume_l <= 0:
        errors.append("目标配制体积必须大于 0")
        return result

    mw = detail.get("molecular_weight")
    try:
        conc_g_l = concentration_to_g_l(target, detail.get("concentration_unit") or "", mw)
    except UnitError as exc:
        errors.append(str(exc))
        return result
    result["target_g_l"] = conc_g_l

    purity = detail.get("purity_fraction", 1.0)
    try:
        purity = float(purity if purity not in (None, "") else 1.0)
    except (TypeError, ValueError):
        purity = 1.0
        warnings.append("纯度不是有效数值，已按 100% 计算")
    if purity > 1 and purity <= 100:
        purity = purity / 100.0
        warnings.append("纯度按百分数输入，已换算为小数")
    if purity <= 0 or purity > 1:
        errors.append("纯度必须为 0~1 的小数（或 1~100 的百分数）")
        return result

    mass_g = conc_g_l * target_volume_l
    result["theoretical_amount_g"] = mass_g
    result["corrected_amount_g"] = mass_g / purity

    source = detail.get("source_type") or "直接称量"
    if source == "母液":
        stock_conc = detail.get("stock_concentration")
        stock_unit = detail.get("stock_unit") or ""
        try:
            stock_g_l = concentration_to_g_l(float(stock_conc or 0), stock_unit, mw)
        except (UnitError, TypeError, ValueError) as exc:
            errors.append(f"母液浓度无效：{exc}")
            return result
        if stock_g_l <= 0:
            errors.append("母液浓度必须大于 0")
            return result
        stock_l = mass_g / stock_g_l
        result["stock_volume_ml"] = stock_l * 1000.0
        result["stock_g_l"] = stock_g_l
    return result


def calculate_formula(details: Sequence[dict], target_volume: float, volume_unit: str) -> dict:
    """整张配方计算。返回行明细、合计、定容体积和全部警告。"""
    warnings: list[str] = []
    errors: list[str] = []
    try:
        volume_l = volume_to_l(float(target_volume), volume_unit)
    except (UnitError, TypeError, ValueError) as exc:
        return {"lines": [], "warnings": [], "errors": [f"目标体积无效：{exc}"],
                "target_volume_l": None, "total_stock_ml": None, "solvent_ml": None,
                "total_theoretical_g": None, "total_corrected_g": None}

    lines = []
    total_stock_ml = 0.0
    total_theoretical = 0.0
    total_corrected = 0.0
    for d in details:
        line = calculate_line(d, volume_l)
        lines.append(line)
        errors.extend(line["errors"])
        warnings.extend(f"{line['component_code'] or line['component_name']}：{w}" for w in line["warnings"])
        if line["stock_volume_ml"]:
            total_stock_ml += line["stock_volume_ml"]
        if line["theoretical_amount_g"] is not None:
            total_theoretical += line["theoretical_amount_g"]
        if line["corrected_amount_g"] is not None:
            total_corrected += line["corrected_amount_g"]

    solvent_ml = volume_l * 1000.0 - total_stock_ml
    if solvent_ml < -1e-6:
        errors.append(f"母液体积合计 {total_stock_ml:.2f} mL 已超过目标体积 {volume_l * 1000:.2f} mL")
        solvent_ml = 0.0
    elif solvent_ml < 0:
        solvent_ml = 0.0

    return {
        "lines": lines,
        "warnings": warnings,
        "errors": errors,
        "target_volume_l": volume_l,
        "total_stock_ml": total_stock_ml,
        "solvent_ml": solvent_ml,
        "total_theoretical_g": total_theoretical,
        "total_corrected_g": total_corrected,
    }
