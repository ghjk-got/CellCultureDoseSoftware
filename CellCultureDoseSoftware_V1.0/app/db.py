# -*- coding: utf-8 -*-
"""SQLite 数据访问基础设施：连接、建表、事务、编号与初始化数据。"""
from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

SCHEMA_VERSION = "1.0"


def now_iso() -> str:
    """本地时区 ISO 8601 时间，精确到秒。"""
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


SCHEMA_SQL = r"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS app_setting (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS reactor_info (
    reactor_id TEXT PRIMARY KEY,
    reactor_code TEXT NOT NULL UNIQUE,
    reactor_name TEXT,
    working_volume_ml REAL,
    notes TEXT,
    status TEXT NOT NULL DEFAULT '启用',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS component_info (
    component_id TEXT PRIMARY KEY,
    component_code TEXT NOT NULL UNIQUE,
    component_name TEXT NOT NULL,
    category TEXT,
    default_unit TEXT DEFAULT 'g',
    molecular_weight REAL,
    purity_default REAL DEFAULT 1.0,
    stock_concentration REAL,
    stock_unit TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT '启用',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS liquid_info (
    liquid_id TEXT PRIMARY KEY,
    liquid_code TEXT NOT NULL UNIQUE,
    liquid_name TEXT NOT NULL,
    liquid_type TEXT,
    concentration_value REAL,
    concentration_unit TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT '启用',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pump_info (
    pump_id TEXT PRIMARY KEY,
    pump_code TEXT NOT NULL UNIQUE,
    pump_name TEXT,
    pump_type TEXT,
    flow_unit TEXT DEFAULT 'mL/h',
    status TEXT NOT NULL DEFAULT '启用',
    notes TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS formula_info (
    formula_id TEXT PRIMARY KEY,
    formula_code TEXT NOT NULL,
    formula_name TEXT NOT NULL,
    formula_type TEXT,
    version_no INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT '草稿',
    effective_date TEXT,
    change_note TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT,
    parent_formula_id TEXT,
    UNIQUE(formula_code, version_no)
);

CREATE TABLE IF NOT EXISTS formula_detail (
    detail_id TEXT PRIMARY KEY,
    formula_id TEXT NOT NULL REFERENCES formula_info(formula_id) ON DELETE CASCADE,
    component_id TEXT NOT NULL REFERENCES component_info(component_id),
    target_concentration REAL,
    concentration_unit TEXT,
    molecular_weight REAL,
    purity_fraction REAL DEFAULT 1.0,
    source_type TEXT NOT NULL DEFAULT '直接称量',
    stock_concentration REAL,
    stock_unit TEXT,
    sort_order INTEGER DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS batch_info (
    batch_id TEXT PRIMARY KEY,
    batch_code TEXT NOT NULL UNIQUE,
    project_name TEXT,
    culture_system TEXT,
    reactor_id TEXT REFERENCES reactor_info(reactor_id),
    working_volume_ml REAL,
    start_time TEXT,
    end_time TEXT,
    status TEXT NOT NULL DEFAULT '进行中',
    notes TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT
);

CREATE TABLE IF NOT EXISTS batch_stage (
    stage_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batch_info(batch_id) ON DELETE CASCADE,
    stage_name TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    sort_order INTEGER DEFAULT 0,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS culture_parameter (
    param_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batch_info(batch_id) ON DELETE CASCADE,
    stage_id TEXT REFERENCES batch_stage(stage_id) ON DELETE SET NULL,
    param_name TEXT NOT NULL,
    param_value REAL,
    unit TEXT,
    recorded_at TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS batch_pump_mapping (
    mapping_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batch_info(batch_id) ON DELETE CASCADE,
    pump_id TEXT NOT NULL REFERENCES pump_info(pump_id),
    liquid_id TEXT NOT NULL REFERENCES liquid_info(liquid_id),
    valid_from TEXT,
    valid_to TEXT,
    mapping_note TEXT,
    UNIQUE(batch_id, pump_id, valid_from)
);

CREATE TABLE IF NOT EXISTS pump_calibration (
    calibration_id TEXT PRIMARY KEY,
    pump_id TEXT NOT NULL REFERENCES pump_info(pump_id),
    calibration_date TEXT NOT NULL,
    source_file_id TEXT REFERENCES import_record(import_id),
    calibration_status TEXT NOT NULL DEFAULT '待审核',
    calibration_method TEXT,
    notes TEXT,
    created_at TEXT NOT NULL,
    created_by TEXT
);

CREATE TABLE IF NOT EXISTS pump_calibration_point (
    point_id TEXT PRIMARY KEY,
    calibration_id TEXT NOT NULL REFERENCES pump_calibration(calibration_id) ON DELETE CASCADE,
    setpoint_value REAL NOT NULL,
    setpoint_unit TEXT NOT NULL,
    measured_flow REAL,
    flow_unit TEXT,
    measured_volume REAL,
    run_duration REAL,
    duration_unit TEXT,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS feed_plan (
    plan_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batch_info(batch_id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT '草稿',
    created_at TEXT NOT NULL,
    created_by TEXT,
    notes TEXT,
    UNIQUE(batch_id, version_no)
);

CREATE TABLE IF NOT EXISTS feed_plan_event (
    event_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES feed_plan(plan_id) ON DELETE CASCADE,
    stage_id TEXT REFERENCES batch_stage(stage_id) ON DELETE SET NULL,
    liquid_id TEXT NOT NULL REFERENCES liquid_info(liquid_id),
    pump_id TEXT NOT NULL REFERENCES pump_info(pump_id),
    planned_start TEXT,
    planned_end TEXT,
    planned_volume_ml REAL,
    target_flow_ml_h REAL,
    duration_h REAL,
    concentration_value REAL,
    concentration_unit TEXT,
    status TEXT NOT NULL DEFAULT '计划',
    notes TEXT,
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS import_record (
    import_id TEXT PRIMARY KEY,
    batch_id TEXT REFERENCES batch_info(batch_id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    archived_path TEXT,
    file_hash TEXT,
    imported_at TEXT NOT NULL,
    imported_by TEXT,
    row_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    error_count INTEGER DEFAULT 0,
    mapping_config TEXT,
    import_status TEXT NOT NULL DEFAULT '成功',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS dose_data_normalized (
    dose_row_id TEXT PRIMARY KEY,
    import_id TEXT NOT NULL REFERENCES import_record(import_id) ON DELETE CASCADE,
    batch_id TEXT NOT NULL REFERENCES batch_info(batch_id) ON DELETE CASCADE,
    pump_id TEXT NOT NULL REFERENCES pump_info(pump_id),
    timestamp_utc TEXT NOT NULL,
    flow_rate REAL,
    flow_unit TEXT,
    total_volume REAL,
    volume_unit TEXT,
    pump_status TEXT,
    counter_segment INTEGER DEFAULT 1,
    quality_flags TEXT,
    raw_row_no INTEGER
);

CREATE TABLE IF NOT EXISTS preparation_record (
    preparation_id TEXT PRIMARY KEY,
    batch_id TEXT REFERENCES batch_info(batch_id) ON DELETE SET NULL,
    formula_id TEXT NOT NULL REFERENCES formula_info(formula_id),
    target_volume REAL NOT NULL,
    volume_unit TEXT NOT NULL,
    theoretical_amount REAL,
    corrected_amount REAL,
    actual_weighed_amount REAL,
    actual_final_volume REAL,
    calculated_actual_concentration REAL,
    prepared_at TEXT,
    operator TEXT,
    notes TEXT,
    detail_snapshot TEXT
);

CREATE TABLE IF NOT EXISTS dose_calculation (
    calculation_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batch_info(batch_id) ON DELETE CASCADE,
    event_id TEXT REFERENCES feed_plan_event(event_id) ON DELETE SET NULL,
    pump_id TEXT NOT NULL REFERENCES pump_info(pump_id),
    liquid_id TEXT REFERENCES liquid_info(liquid_id),
    time_start TEXT NOT NULL,
    time_end TEXT NOT NULL,
    planned_volume_ml REAL,
    actual_volume_ml REAL,
    flow_integral_ml REAL,
    deviation_ml REAL,
    deviation_percent REAL,
    completion_percent REAL,
    calculation_method TEXT,
    quality_status TEXT NOT NULL DEFAULT '待审核',
    calculation_version INTEGER DEFAULT 1,
    calculated_at TEXT NOT NULL,
    data_import_id TEXT,
    notes TEXT
);

-- 手工抄录保留原始文本与核算快照，不把设备估算量写成独立实测量。
CREATE TABLE IF NOT EXISTS manual_feed_record (
    record_id TEXT PRIMARY KEY,
    batch_id TEXT NOT NULL REFERENCES batch_info(batch_id),
    event_id TEXT REFERENCES feed_plan_event(event_id),
    pump_id TEXT NOT NULL REFERENCES pump_info(pump_id),
    liquid_id TEXT NOT NULL REFERENCES liquid_info(liquid_id),
    start_time TEXT, end_time TEXT, start_reading TEXT, end_reading TEXT,
    reading_unit TEXT, intermediate_readings TEXT NOT NULL DEFAULT '[]',
    known_reset INTEGER NOT NULL DEFAULT 0,
    measured_value TEXT, measured_unit TEXT, measured_method TEXT,
    planned_volume_ml REAL, estimate_ml REAL, measured_ml REAL,
    quality_status TEXT NOT NULL, issues TEXT NOT NULL,
    equipment_notes TEXT, notes TEXT, created_at TEXT NOT NULL, created_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_manual_feed_batch ON manual_feed_record(batch_id);

CREATE TABLE IF NOT EXISTS manual_feed_revision (
    revision_id TEXT PRIMARY KEY,
    record_id TEXT NOT NULL REFERENCES manual_feed_record(record_id),
    action TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL,
    reason TEXT NOT NULL, operator TEXT NOT NULL, created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commercial_medium_record (
    record_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES batch_info(batch_id),
    medium_name TEXT NOT NULL, product_lot TEXT, volume REAL NOT NULL,
    volume_unit TEXT NOT NULL, used_at TEXT NOT NULL, operator TEXT NOT NULL, notes TEXT
);

CREATE TABLE IF NOT EXISTS dose_anomaly (
    anomaly_id TEXT PRIMARY KEY,
    batch_id TEXT REFERENCES batch_info(batch_id) ON DELETE CASCADE,
    calculation_id TEXT REFERENCES dose_calculation(calculation_id) ON DELETE SET NULL,
    import_id TEXT REFERENCES import_record(import_id) ON DELETE SET NULL,
    anomaly_type TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT '警告',
    description TEXT,
    status TEXT NOT NULL DEFAULT '未解决',
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    resolution_note TEXT
);

CREATE TABLE IF NOT EXISTS report_record (
    report_id TEXT PRIMARY KEY,
    batch_id TEXT REFERENCES batch_info(batch_id) ON DELETE CASCADE,
    report_type TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT,
    generated_at TEXT NOT NULL,
    generated_by TEXT,
    version_no INTEGER DEFAULT 1,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS operation_log (
    log_id TEXT PRIMARY KEY,
    user_id TEXT,
    action_type TEXT NOT NULL,
    object_type TEXT,
    object_id TEXT,
    before_value TEXT,
    after_value TEXT,
    reason TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_info (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT,
    password_hash TEXT,
    role TEXT DEFAULT '操作员',
    status TEXT DEFAULT '启用',
    created_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_formula_detail_formula ON formula_detail(formula_id);
CREATE INDEX IF NOT EXISTS idx_batch_stage_batch ON batch_stage(batch_id);
CREATE INDEX IF NOT EXISTS idx_batch_param_batch ON culture_parameter(batch_id);
CREATE INDEX IF NOT EXISTS idx_mapping_batch ON batch_pump_mapping(batch_id);
CREATE INDEX IF NOT EXISTS idx_calibration_pump ON pump_calibration(pump_id);
CREATE INDEX IF NOT EXISTS idx_plan_batch ON feed_plan(batch_id);
CREATE INDEX IF NOT EXISTS idx_event_plan ON feed_plan_event(plan_id);
CREATE INDEX IF NOT EXISTS idx_import_batch ON import_record(batch_id);
CREATE INDEX IF NOT EXISTS idx_dose_import ON dose_data_normalized(import_id);
CREATE INDEX IF NOT EXISTS idx_dose_batch_pump_time ON dose_data_normalized(batch_id, pump_id, timestamp_utc);
CREATE INDEX IF NOT EXISTS idx_calc_batch ON dose_calculation(batch_id);
CREATE INDEX IF NOT EXISTS idx_anomaly_batch ON dose_anomaly(batch_id);
CREATE INDEX IF NOT EXISTS idx_report_batch ON report_record(batch_id);
CREATE INDEX IF NOT EXISTS idx_log_time ON operation_log(created_at);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        self.init_schema()

    # ---------- 基础查询 ----------
    def q(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        return list(self.conn.execute(sql, params))

    def q1(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
        return self.conn.execute(sql, params).fetchone()

    def scalar(self, sql: str, params: Sequence[Any] = (), default: Any = None) -> Any:
        row = self.q1(sql, params)
        return default if row is None else row[0]

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> None:
        self.conn.executemany(sql, rows)
        self.conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Cursor]:
        cur = self.conn.cursor()
        try:
            yield cur
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # ---------- 元数据 ----------
    def init_schema(self) -> None:
        self.conn.executescript(SCHEMA_SQL)
        columns = {row[1] for row in self.conn.execute("PRAGMA table_info(dose_calculation)")}
        if "value_source" not in columns:
            self.conn.execute("ALTER TABLE dose_calculation ADD COLUMN value_source TEXT NOT NULL DEFAULT '来源待核实'")
        manual_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(manual_feed_record)")}
        if "known_reset" not in manual_columns:
            self.conn.execute("ALTER TABLE manual_feed_record ADD COLUMN known_reset INTEGER NOT NULL DEFAULT 0")
        if "lifecycle_status" not in manual_columns:
            self.conn.execute("ALTER TABLE manual_feed_record ADD COLUMN lifecycle_status TEXT NOT NULL DEFAULT '已完成'")
        self.conn.commit()
        self.set_setting("schema_version", SCHEMA_VERSION)

    def get_setting(self, key: str, default: str | None = None) -> str | None:
        row = self.q1("SELECT value FROM app_setting WHERE key = ?", (key,))
        return default if row is None else row["value"]

    def set_setting(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO app_setting(key, value, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, value, now_iso()),
        )
        self.conn.commit()

    def backup_to(self, target: str | Path) -> None:
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        dest = sqlite3.connect(str(target))
        try:
            self.conn.backup(dest)
        finally:
            dest.close()

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass

    # ---------- 初始化种子数据 ----------
    def seed_defaults(self) -> None:
        if self.get_setting("seeded_v1") == "1":
            return
        ts = now_iso()
        with self.transaction() as cur:
            pumps = [
                ("PUMP_01", "补料泵 1", "蠕动泵"),
                ("PUMP_02", "补料泵 2", "蠕动泵"),
                ("PUMP_03", "补料泵 3", "蠕动泵"),
                ("PUMP_04", "补料泵 4", "蠕动泵"),
            ]
            for code, name, ptype in pumps:
                cur.execute(
                    "INSERT OR IGNORE INTO pump_info(pump_id,pump_code,pump_name,pump_type,flow_unit,status,notes,created_at) "
                    "VALUES(?,?,?,?,?,?,?,?)",
                    (new_id("PMP"), code, name, ptype, "mL/h", "启用", "系统初始化示例，可在基础数据中修改", ts),
                )
            liquids = [
                ("FEED_A", "Feed A", "Feed"),
                ("FEED_B", "Feed B", "Feed"),
                ("ALKALI", "碱液", "碱液"),
                ("ANTIFOAM", "消泡剂", "消泡剂"),
            ]
            for code, name, ltype in liquids:
                cur.execute(
                    "INSERT OR IGNORE INTO liquid_info(liquid_id,liquid_code,liquid_name,liquid_type,status,notes,created_at) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (new_id("LIQ"), code, name, ltype, "启用", "系统初始化示例，可在基础数据中修改", ts),
                )
            cur.execute(
                "INSERT OR IGNORE INTO reactor_info(reactor_id,reactor_code,reactor_name,working_volume_ml,notes,status,created_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (new_id("RCT"), "R-3L", "3 L 生物反应器", 3000.0, "系统初始化示例", "启用", ts),
            )
            cur.execute(
                "INSERT INTO app_setting(key,value,updated_at) VALUES('seeded_v1','1',?) "
                "ON CONFLICT(key) DO UPDATE SET value='1'",
                (ts,),
            )
