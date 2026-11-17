# -*- coding: utf-8 -*-
"""备份与恢复服务：数据库、原始导入文件、报告与配置打包。"""
from __future__ import annotations

import json
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from ..config import APP_VERSION, CONFIG_FILE
from ..db import Database, now_iso


class BackupError(RuntimeError):
    pass


class BackupService:
    def __init__(self, db: Database, settings):
        self.db = db
        self.settings = settings
        self.folder = settings.path("backups")
        self.folder.mkdir(parents=True, exist_ok=True)

    def create(self, note: str = "") -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = self.folder / f"backup_{stamp}.zip"
        counter = 1
        while target.exists():
            target = self.folder / f"backup_{stamp}_{counter}.zip"
            counter += 1
        counts = {}
        for table in ("batch_info", "formula_info", "preparation_record", "feed_plan", "pump_calibration",
                      "import_record", "dose_calculation", "manual_feed_record", "manual_feed_revision",
                      "commercial_medium_record", "dose_anomaly", "report_record"):
            counts[table] = int(self.db.scalar(f"SELECT COUNT(*) FROM {table}", (), 0))
        manifest = {
            "app": "CellCultureDoseSoftware",
            "app_version": APP_VERSION,
            "created_at": now_iso(),
            "note": note,
            "counts": counts,
            "data_dir": str(self.settings.data_dir),
        }
        with tempfile.TemporaryDirectory() as tmp:
            db_snapshot = Path(tmp) / "cell_culture.db"
            self.db.backup_to(db_snapshot)
            with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.write(db_snapshot, "database/cell_culture.db")
                for sub in ("imports", "reports"):
                    root = self.settings.path(sub)
                    if root.exists():
                        for file in root.rglob("*"):
                            if file.is_file():
                                zf.write(file, f"{sub}/{file.relative_to(root).as_posix()}")
                if CONFIG_FILE.exists():
                    zf.write(CONFIG_FILE, "config.json")
                zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        return target

    def list(self) -> list[Path]:
        return sorted(self.folder.glob("backup_*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)

    def verify(self, path: str | Path) -> dict:
        source = Path(path)
        if not source.exists():
            raise BackupError("备份文件不存在")
        try:
            with zipfile.ZipFile(source) as zf:
                names = set(zf.namelist())
                if "database/cell_culture.db" not in names:
                    raise BackupError("备份缺少数据库文件")
                for name in names:
                    if name.startswith("/") or ".." in Path(name).parts:
                        raise BackupError(f"备份包含不安全路径：{name}")
                manifest = {}
                if "manifest.json" in names:
                    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
                with tempfile.TemporaryDirectory() as tmp:
                    zf.extract("database/cell_culture.db", tmp)
                    db_path = Path(tmp) / "database" / "cell_culture.db"
                    conn = sqlite3.connect(str(db_path))
                    try:
                        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
                        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    finally:
                        conn.close()
                required = {"batch_info", "formula_info", "feed_plan", "import_record", "dose_calculation"}
                if integrity != "ok":
                    raise BackupError(f"数据库完整性检查失败：{integrity}")
                if not required.issubset(tables):
                    raise BackupError("备份数据库缺少必要数据表")
                return {"manifest": manifest, "integrity": integrity, "tables": len(tables)}
        except zipfile.BadZipFile as exc:
            raise BackupError("备份文件不是有效的 ZIP 包") from exc

    def restore(self, path: str | Path) -> Path:
        source = Path(path)
        info = self.verify(source)
        safety = self.create(note=f"恢复前自动备份（来源 {source.name}）")
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(source) as zf:
                zf.extractall(tmp)
            restored_db = Path(tmp) / "database" / "cell_culture.db"
            self.db.close()
            target_db = self.settings.db_path
            target_db.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(restored_db, target_db)
            for sub in ("imports", "reports"):
                src = Path(tmp) / sub
                if not src.exists():
                    continue
                dst = self.settings.path(sub)
                dst.mkdir(parents=True, exist_ok=True)
                for file in src.rglob("*"):
                    if file.is_file():
                        out = dst / file.relative_to(src)
                        out.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file, out)
        return safety
