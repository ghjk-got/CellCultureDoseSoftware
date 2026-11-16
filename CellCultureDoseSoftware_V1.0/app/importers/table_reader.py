# -*- coding: utf-8 -*-
"""CSV/XLSX 通用读取：编码探测、工作表、表头行与字段映射。"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence


class ImportFileError(ValueError):
    pass


@dataclass
class TableData:
    path: Path
    sheet: str
    header_row: int
    headers: list[str]
    rows: list[list[Any]] = field(default_factory=list)

    def records(self) -> list[dict[str, Any]]:
        out = []
        for row in self.rows:
            rec = {}
            for i, header in enumerate(self.headers):
                rec[header] = row[i] if i < len(row) else None
            out.append(rec)
        return out


def list_sheets(path: str | Path) -> list[str]:
    p = Path(path)
    if p.suffix.lower() not in (".xlsx", ".xlsm"):
        return []
    try:
        from openpyxl import load_workbook
        wb = load_workbook(p, read_only=True, data_only=True)
        try:
            return list(wb.sheetnames)
        finally:
            wb.close()
    except Exception as exc:
        raise ImportFileError(f"无法读取 Excel 工作表：{exc}") from exc


def _decode_csv(raw: bytes) -> str:
    for enc in ("utf-8-sig", "gb18030", "utf-16", "utf-8"):
        try:
            text = raw.decode(enc)
            if text.count("\ufffd") <= 2:
                return text
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _sniff_delimiter(sample: str) -> str:
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        return dialect.delimiter
    except csv.Error:
        counts = {d: sample.count(d) for d in (",", "\t", ";", "|")}
        return max(counts, key=counts.get) if max(counts.values()) > 0 else ","


def read_table(path: str | Path, sheet: str | None = None, header_row: int = 1) -> TableData:
    p = Path(path)
    if not p.exists():
        raise ImportFileError(f"文件不存在：{p}")
    suffix = p.suffix.lower()
    if suffix in (".xlsx", ".xlsm"):
        try:
            from openpyxl import load_workbook
            wb = load_workbook(p, read_only=True, data_only=True)
        except Exception as exc:
            raise ImportFileError(f"无法打开 Excel 文件：{exc}") from exc
        try:
            ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb[wb.sheetnames[0]]
            rows_iter = ws.iter_rows(values_only=True)
            all_rows = [list(r) for r in rows_iter]
            actual_sheet = ws.title
        finally:
            wb.close()
    elif suffix in (".csv", ".txt", ".tsv"):
        text = _decode_csv(p.read_bytes())
        delimiter = "\t" if suffix == ".tsv" else _sniff_delimiter(text[:8192])
        all_rows = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)]
        actual_sheet = "CSV"
    else:
        raise ImportFileError("仅支持 CSV、TXT、TSV、XLSX 文件")

    # 去掉尾部全空行
    while all_rows and all(v in (None, "") for v in all_rows[-1]):
        all_rows.pop()
    if header_row < 1 or header_row > len(all_rows):
        raise ImportFileError(f"表头行 {header_row} 超出文件范围（共 {len(all_rows)} 行）")
    raw_headers = all_rows[header_row - 1]
    width = max((len(r) for r in all_rows[header_row - 1:]), default=0)
    headers: list[str] = []
    seen: dict[str, int] = {}
    for i in range(width):
        value = raw_headers[i] if i < len(raw_headers) else None
        name = str(value).strip() if value not in (None, "") else f"列{i + 1}"
        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        headers.append(name)
    data_rows = []
    for row in all_rows[header_row:]:
        row = list(row) + [None] * (width - len(row))
        if all(v in (None, "") for v in row):
            continue
        data_rows.append(row[:width])
    return TableData(path=p, sheet=actual_sheet, header_row=header_row, headers=headers, rows=data_rows)


def guess_header_row(path: str | Path, sheet: str | None = None, max_scan: int = 20) -> int:
    """在前若干行中选择“非空文本列最多”的一行作为表头。"""
    p = Path(path)
    try:
        if p.suffix.lower() in (".xlsx", ".xlsm"):
            from openpyxl import load_workbook
            wb = load_workbook(p, read_only=True, data_only=True)
            try:
                ws = wb[sheet] if sheet and sheet in wb.sheetnames else wb[wb.sheetnames[0]]
                rows = []
                for i, row in enumerate(ws.iter_rows(values_only=True)):
                    rows.append(list(row))
                    if i >= max_scan:
                        break
            finally:
                wb.close()
        else:
            text = _decode_csv(p.read_bytes())
            delimiter = "\t" if p.suffix.lower() == ".tsv" else _sniff_delimiter(text[:8192])
            rows = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter)][:max_scan]
    except Exception:
        return 1
    best_row, best_score = 1, -1
    for idx, row in enumerate(rows):
        strings = [v for v in row if isinstance(v, str) and v.strip() and not _is_number(v)]
        score = len(strings) * 2 + len(set(str(v).strip() for v in row if v not in (None, "")))
        if score > best_score:
            best_row, best_score = idx + 1, score
    return best_row


def _is_number(value: Any) -> bool:
    try:
        float(str(value).replace(",", ""))
        return True
    except (TypeError, ValueError):
        return False


DOSE_SYNONYMS = {
    "timestamp": ["timestamp", "time", "datetime", "date time", "时间", "日期时间", "时间戳", "采集时间", "记录时间", "日期"],
    "pump_code": ["pump code", "pump id", "pump", "channel", "泵编号", "泵号", "泵", "通道号", "通道"],
    "flow_rate": ["flow rate", "flow", "rate", "流速", "流量", "瞬时流量", "泵流速"],
    "flow_unit": ["flow unit", "流速单位", "流量单位"],
    "total_volume": ["total volume", "accumulated volume", "cumulative volume", "total", "累计体积", "累计量", "累计流量", "总量", "累积量", "累计值"],
    "volume_unit": ["volume unit", "体积单位", "累计单位"],
    "pump_status": ["pump status", "status", "泵状态", "运行状态", "状态"],
}

CALIBRATION_SYNONYMS = {
    "setpoint_value": ["setpoint", "set point", "rpm", "speed", "setting", "设置值", "转速", "设定值", "泵速"],
    "setpoint_unit": ["setpoint unit", "speed unit", "设置值单位", "转速单位", "单位"],
    "measured_flow": ["measured flow", "flow", "actual flow", "实测流量", "实测流速", "流量", "流速"],
    "flow_unit": ["flow unit", "流量单位", "流速单位"],
    "measured_volume": ["measured volume", "volume", "实测体积", "收集体积", "体积"],
    "run_duration": ["duration", "run duration", "time", "运行时长", "时长", "时间"],
    "duration_unit": ["duration unit", "time unit", "时长单位", "时间单位"],
}


def auto_map(headers: Sequence[str], synonyms: dict[str, list[str]] | None = None) -> dict[str, int]:
    synonyms = synonyms or DOSE_SYNONYMS
    normalized = [str(h).strip().lower().replace("_", " ") for h in headers]
    mapping: dict[str, int] = {}
    used: set[int] = set()
    for field, words in synonyms.items():
        # 先精确匹配
        for word in words:
            w = word.lower()
            for idx, header in enumerate(normalized):
                if idx in used:
                    continue
                if header == w:
                    mapping[field] = idx
                    used.add(idx)
                    break
            if field in mapping:
                break
        if field in mapping:
            continue
        # 再包含匹配，取最短表头，避免“累计体积”误配“体积单位”
        candidates = []
        for word in words:
            w = word.lower()
            for idx, header in enumerate(normalized):
                if idx in used:
                    continue
                if w in header:
                    candidates.append((len(header), idx))
        if candidates:
            candidates.sort()
            mapping[field] = candidates[0][1]
            used.add(candidates[0][1])
    return mapping


NUMBER_UNIT_RE = re.compile(r"^\s*([-+]?[\d,]*\.?\d+(?:[eE][-+]?\d+)?)\s*([^\d\s.].*?)?\s*$")


def split_number_unit(value: Any) -> tuple[float | None, str | None]:
    """解析 "10.5 mL/h"、"1,200" 这类混合内容。"""
    if value is None or value == "":
        return None, None
    if isinstance(value, (int, float)):
        return float(value), None
    text = str(value).strip()
    match = NUMBER_UNIT_RE.match(text)
    if match:
        try:
            unit = match.group(2)
            return float(match.group(1).replace(",", "")), (unit.strip() if unit else None)
        except ValueError:
            return None, None
    try:
        return float(text.replace(",", "")), None
    except ValueError:
        return None, None
