# -*- coding: utf-8 -*-
"""应用配置：数据目录、操作员与计算参数。"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

APP_NAME = "细胞培养基配制与补料剂量核算软件"
APP_VERSION = "1.0.0"
APP_TITLE = f"{APP_NAME} V{APP_VERSION.split('.')[0]}.0"

BASE_DIR = (Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False) else Path(__file__).resolve().parent.parent)
CONFIG_FILE = Path(os.environ.get("CCDS_CONFIG") or (BASE_DIR / "config.json"))


def _default_data_dir() -> str:
    return os.environ.get("CCDS_DATA_DIR") or str(BASE_DIR / "ApplicationData")


def _default_operator() -> str:
    return os.environ.get("USERNAME") or os.environ.get("USER") or "操作员"


@dataclass
class Settings:
    data_dir: str = field(default_factory=_default_data_dir)
    operator: str = field(default_factory=_default_operator)
    max_sample_gap_h: float = 2.0
    default_volume_unit: str = "mL"
    default_flow_unit: str = "mL/h"
    timezone_note: str = "本机时区"
    last_batch_id: str = ""

    # ---------- 路径 ----------
    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def db_path(self) -> Path:
        return self.data_path / "database" / "cell_culture.db"

    def path(self, *parts: str) -> Path:
        return self.data_path.joinpath(*parts)

    def ensure_dirs(self) -> None:
        for sub in ("database", "imports", "reports", "backups", "logs", "templates"):
            (self.data_path / sub).mkdir(parents=True, exist_ok=True)

    # ---------- 持久化 ----------
    @classmethod
    def load(cls) -> "Settings":
        data = {}
        if CONFIG_FILE.exists():
            try:
                data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                data = {}
        if os.environ.get("CCDS_DATA_DIR"):
            data["data_dir"] = os.environ["CCDS_DATA_DIR"]
        known = {f for f in cls.__dataclass_fields__}
        clean = {k: v for k, v in data.items() if k in known}
        obj = cls(**clean)
        obj.ensure_dirs()
        return obj

    def save(self) -> None:
        payload = {f: getattr(self, f) for f in self.__dataclass_fields__}
        CONFIG_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.ensure_dirs()