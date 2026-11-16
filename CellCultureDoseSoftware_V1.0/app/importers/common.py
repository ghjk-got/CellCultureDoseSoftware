# -*- coding: utf-8 -*-
"""导入公共工具：哈希、归档、时间与数值标准化。"""
from __future__ import annotations

import hashlib
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..services.dose_calc import parse_ts


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(name: str) -> str:
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name).strip(" .")
    return name or "file"


def archive_copy(path: str | Path, data_dir: str | Path, batch_code: str,
                 source_type: str) -> Path:
    source = Path(path)
    folder = Path(data_dir) / "imports" / safe_name(batch_code or "UNASSIGNED") / safe_name(source_type)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = folder / f"{stamp}_{safe_name(source.name)}"
    counter = 1
    while target.exists():
        target = folder / f"{stamp}_{counter}_{safe_name(source.name)}"
        counter += 1
    shutil.copy2(source, target)
    return target


def excel_serial_to_datetime(value: float) -> datetime:
    base = datetime(1899, 12, 30)
    return (base + timedelta(days=float(value))).astimezone()


def normalize_timestamp(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.astimezone()
    elif isinstance(value, (int, float)) and 20000 <= float(value) <= 80000:
        dt = excel_serial_to_datetime(float(value))
    else:
        dt = parse_ts(value)
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone().replace(microsecond=0).isoformat()
