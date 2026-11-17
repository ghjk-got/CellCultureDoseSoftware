# -*- coding: utf-8 -*-
import os, sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.config import Settings
from app.db import Database
from app.repositories import Repositories
from app.services.backup import BackupService

tmp = Path(tempfile.mkdtemp(prefix="ccds_backup_"))
settings = Settings(data_dir=str(tmp)); settings.ensure_dirs()
db = Database(settings.db_path); db.seed_defaults()
repos = Repositories(db)
repos.batches.create({"batch_code": "B-1", "status": "进行中", "created_by": "t"})
service = BackupService(db, settings)
path = service.create("test")
print("backup", path, path.stat().st_size)
info = service.verify(path); print("verify", info)
assert info["integrity"] == "ok"
repos.batches.create({"batch_code": "B-2", "status": "草稿", "created_by": "t"})
assert db.scalar("SELECT COUNT(*) FROM batch_info") == 2
safety = service.restore(path)
print("restored, safety", safety.name)
db2 = Database(settings.db_path)
count = db2.scalar("SELECT COUNT(*) FROM batch_info")
print("count", count)
assert count == 1
db2.close()
print("BACKUP OK")
