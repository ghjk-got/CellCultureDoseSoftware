# -*- coding: utf-8 -*-
"""应用上下文：集中装配数据库、仓储、服务与当前操作员。"""
from __future__ import annotations

from .config import Settings
from .db import Database
from .importers.calibration_importer import CalibrationImportService
from .importers.dose_importer import DoseImportService
from .repositories import Repositories
from .services.backup import BackupService
from .services.reporting import ReportService


class AppContext:
    def __init__(self):
        self.settings = Settings.load()
        self.db = Database(self.settings.db_path)
        self.db.seed_defaults()
        self.repos = Repositories(self.db)
        self.reports = ReportService(self.repos, self.settings)
        self.backups = BackupService(self.db, self.settings)
        self.dose_import = DoseImportService(self.repos, self.settings)
        self.calibration_import = CalibrationImportService(self.repos, self.settings)

    @property
    def operator(self) -> str:
        return self.settings.operator or "操作员"

    def audit(self, action: str, object_type: str = "", object_id: str = "",
              before=None, after=None, reason: str = "") -> None:
        self.repos.logs.add(self.operator, action, object_type, object_id, before, after, reason)

    def close(self) -> None:
        self.db.close()
