# -*- coding: utf-8 -*-
"""数据仓储：把 SQL 细节集中在此，界面层只调用仓储方法。"""
from __future__ import annotations

import json
from typing import Any, Iterable, Sequence

from .db import Database, new_id, now_iso


def rows_to_dicts(rows: Iterable[Any]) -> list[dict]:
    return [dict(r) for r in rows]


class CrudRepo:
    table = ""
    pk = ""
    fields: tuple[str, ...] = ()

    def __init__(self, db: Database):
        self.db = db

    def list(self, where: str = "", params: Sequence[Any] = (), order: str | None = None) -> list[dict]:
        sql = f"SELECT * FROM {self.table}"
        if where:
            sql += f" WHERE {where}"
        sql += f" ORDER BY {order or self.pk}"
        return rows_to_dicts(self.db.q(sql, params))

    def get(self, key: str) -> dict | None:
        row = self.db.q1(f"SELECT * FROM {self.table} WHERE {self.pk}=?", (key,))
        return None if row is None else dict(row)

    def insert(self, data: dict) -> str:
        data = dict(data)
        if self.pk not in data or not data[self.pk]:
            data[self.pk] = new_id(self.table.split("_")[0][:3].upper())
        cols = [c for c in self.fields if c in data]
        placeholders = ",".join("?" for _ in cols)
        self.db.execute(
            f"INSERT INTO {self.table}({','.join(cols)}) VALUES({placeholders})",
            [data[c] for c in cols],
        )
        return data[self.pk]

    def update(self, key: str, data: dict) -> None:
        cols = [c for c in self.fields if c in data]
        if not cols:
            return
        assignments = ",".join(f"{c}=?" for c in cols)
        self.db.execute(
            f"UPDATE {self.table} SET {assignments} WHERE {self.pk}=?",
            [data[c] for c in cols] + [key],
        )

    def delete(self, key: str) -> None:
        self.db.execute(f"DELETE FROM {self.table} WHERE {self.pk}=?", (key,))

    def count(self, where: str = "", params: Sequence[Any] = ()) -> int:
        return int(self.db.scalar(f"SELECT COUNT(*) FROM {self.table}" + (f" WHERE {where}" if where else ""), params, 0))


class ComponentRepo(CrudRepo):
    table = "component_info"
    pk = "component_id"
    fields = ("component_id", "component_code", "component_name", "category", "default_unit",
              "molecular_weight", "purity_default", "stock_concentration", "stock_unit",
              "notes", "status", "created_at")

    def search(self, keyword: str = "", active_only: bool = False) -> list[dict]:
        clauses, params = [], []
        if keyword:
            clauses.append("(component_code LIKE ? OR component_name LIKE ? OR category LIKE ?)")
            params += [f"%{keyword}%"] * 3
        if active_only:
            clauses.append("status='启用'")
        return self.list(" AND ".join(clauses), params, "component_code")

    def code_exists(self, code: str, exclude: str = "") -> bool:
        row = self.db.q1("SELECT component_id FROM component_info WHERE component_code=? AND component_id<>?",
                         (code, exclude))
        return row is not None


class LiquidRepo(CrudRepo):
    table = "liquid_info"
    pk = "liquid_id"
    fields = ("liquid_id", "liquid_code", "liquid_name", "liquid_type", "concentration_value",
              "concentration_unit", "notes", "status", "created_at")

    def active(self) -> list[dict]:
        return self.list("status='启用'", (), "liquid_code")

    def code_exists(self, code: str, exclude: str = "") -> bool:
        return self.db.q1("SELECT liquid_id FROM liquid_info WHERE liquid_code=? AND liquid_id<>?",
                          (code, exclude)) is not None


class PumpRepo(CrudRepo):
    table = "pump_info"
    pk = "pump_id"
    fields = ("pump_id", "pump_code", "pump_name", "pump_type", "flow_unit", "status", "notes", "created_at")

    def active(self) -> list[dict]:
        return self.list("status='启用'", (), "pump_code")

    def code_exists(self, code: str, exclude: str = "") -> bool:
        return self.db.q1("SELECT pump_id FROM pump_info WHERE pump_code=? AND pump_id<>?",
                          (code, exclude)) is not None

    def by_code(self, code: str) -> dict | None:
        row = self.db.q1("SELECT * FROM pump_info WHERE pump_code=? COLLATE NOCASE", (code.strip(),))
        return None if row is None else dict(row)


class ReactorRepo(CrudRepo):
    table = "reactor_info"
    pk = "reactor_id"
    fields = ("reactor_id", "reactor_code", "reactor_name", "working_volume_ml", "notes", "status", "created_at")

    def active(self) -> list[dict]:
        return self.list("status='启用'", (), "reactor_code")


class FormulaRepo(CrudRepo):
    table = "formula_info"
    pk = "formula_id"
    fields = ("formula_id", "formula_code", "formula_name", "formula_type", "version_no",
              "status", "effective_date", "change_note", "created_at", "created_by", "parent_formula_id")

    def list_with_counts(self, keyword: str = "") -> list[dict]:
        sql = """
        SELECT f.*, (SELECT COUNT(*) FROM formula_detail d WHERE d.formula_id=f.formula_id) AS detail_count
        FROM formula_info f
        """
        params: list[Any] = []
        if keyword:
            sql += " WHERE f.formula_code LIKE ? OR f.formula_name LIKE ?"
            params = [f"%{keyword}%", f"%{keyword}%"]
        sql += " ORDER BY f.formula_code, f.version_no DESC"
        return rows_to_dicts(self.db.q(sql, params))

    def details(self, formula_id: str) -> list[dict]:
        sql = """
        SELECT d.*, c.component_code, c.component_name, c.category
        FROM formula_detail d
        JOIN component_info c ON c.component_id=d.component_id
        WHERE d.formula_id=?
        ORDER BY d.sort_order, c.component_code
        """
        return rows_to_dicts(self.db.q(sql, (formula_id,)))

    def create(self, header: dict, details: Sequence[dict]) -> str:
        fid = new_id("FRM")
        ts = now_iso()
        with self.db.transaction() as cur:
            cur.execute(
                "INSERT INTO formula_info(formula_id,formula_code,formula_name,formula_type,version_no,status,"
                "effective_date,change_note,created_at,created_by,parent_formula_id) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (fid, header["formula_code"], header["formula_name"], header.get("formula_type", ""),
                 int(header.get("version_no", 1)), header.get("status", "草稿"),
                 header.get("effective_date") or None, header.get("change_note", ""), ts,
                 header.get("created_by", ""), header.get("parent_formula_id")),
            )
            for i, d in enumerate(details):
                cur.execute(
                    "INSERT INTO formula_detail(detail_id,formula_id,component_id,target_concentration,"
                    "concentration_unit,molecular_weight,purity_fraction,source_type,stock_concentration,"
                    "stock_unit,sort_order,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (new_id("FD"), fid, d["component_id"], d.get("target_concentration"),
                     d.get("concentration_unit"), d.get("molecular_weight"), d.get("purity_fraction", 1.0),
                     d.get("source_type", "直接称量"), d.get("stock_concentration"), d.get("stock_unit"),
                     i, d.get("notes", "")),
                )
        return fid

    def replace_details(self, formula_id: str, details: Sequence[dict]) -> None:
        with self.db.transaction() as cur:
            cur.execute("DELETE FROM formula_detail WHERE formula_id=?", (formula_id,))
            for i, d in enumerate(details):
                cur.execute(
                    "INSERT INTO formula_detail(detail_id,formula_id,component_id,target_concentration,"
                    "concentration_unit,molecular_weight,purity_fraction,source_type,stock_concentration,"
                    "stock_unit,sort_order,notes) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (new_id("FD"), formula_id, d["component_id"], d.get("target_concentration"),
                     d.get("concentration_unit"), d.get("molecular_weight"), d.get("purity_fraction", 1.0),
                     d.get("source_type", "直接称量"), d.get("stock_concentration"), d.get("stock_unit"),
                     i, d.get("notes", "")),
                )

    def update_header(self, formula_id: str, header: dict) -> None:
        allowed = {k: header[k] for k in ("formula_name", "formula_type", "status", "effective_date", "change_note") if k in header}
        if allowed:
            self.update(formula_id, allowed)

    def new_version(self, formula_id: str, change_note: str, user: str) -> str:
        src = self.get(formula_id)
        if not src:
            raise ValueError("原配方不存在")
        nxt = int(self.db.scalar("SELECT COALESCE(MAX(version_no),0)+1 FROM formula_info WHERE formula_code=?",
                                 (src["formula_code"],), 1))
        header = dict(src)
        header.update({"version_no": nxt, "status": "草稿", "change_note": change_note,
                       "parent_formula_id": formula_id, "created_by": user})
        return self.create(header, self.details(formula_id))

    def delete_draft(self, formula_id: str) -> None:
        row = self.get(formula_id)
        if row and row["status"] != "草稿":
            raise ValueError("只能删除草稿版本")
        self.delete(formula_id)


class BatchRepo(CrudRepo):
    table = "batch_info"
    pk = "batch_id"
    fields = ("batch_id", "batch_code", "project_name", "culture_system", "reactor_id",
              "working_volume_ml", "start_time", "end_time", "status", "notes", "created_at", "created_by")

    def list_with_reactor(self, keyword: str = "") -> list[dict]:
        sql = """
        SELECT b.*, r.reactor_code, r.reactor_name
        FROM batch_info b LEFT JOIN reactor_info r ON r.reactor_id=b.reactor_id
        """
        params: list[Any] = []
        if keyword:
            sql += " WHERE b.batch_code LIKE ? OR b.project_name LIKE ?"
            params = [f"%{keyword}%"] * 2
        sql += " ORDER BY b.created_at DESC"
        return rows_to_dicts(self.db.q(sql, params))

    def create(self, data: dict) -> str:
        bid = new_id("BAT")
        ts = now_iso()
        with self.db.transaction() as cur:
            if data.get("status", "进行中") == "进行中" and cur.execute("SELECT 1 FROM batch_info WHERE status='进行中' LIMIT 1").fetchone():
                raise ValueError("已有进行中的批次，请先结束后再创建新的进行中批次")
            cur.execute(
                "INSERT INTO batch_info(batch_id,batch_code,project_name,culture_system,reactor_id,"
                "working_volume_ml,start_time,end_time,status,notes,created_at,created_by) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (bid, data["batch_code"], data.get("project_name", ""), data.get("culture_system", ""),
                 data.get("reactor_id") or None, data.get("working_volume_ml"),
                 data.get("start_time") or ts, data.get("end_time") or None,
                 data.get("status", "进行中"), data.get("notes", ""), ts, data.get("created_by", "")),
            )
            for i, (name, note) in enumerate((("接种", "接种与初始培养"), ("培养", "补料培养阶段"), ("收获", "收获与结束"))):
                cur.execute(
                    "INSERT INTO batch_stage(stage_id,batch_id,stage_name,start_time,end_time,sort_order,notes) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (new_id("STG"), bid, name, None, None, i, note),
                )
        return bid

    def update(self, key: str, data: dict) -> None:
        """批次状态变更时检查其他批次和未结束的手工补料。"""
        cols = [c for c in self.fields if c in data]
        if not cols:
            return
        with self.db.transaction() as cur:
            current = cur.execute("SELECT status FROM batch_info WHERE batch_id=?", (key,)).fetchone()
            if not current:
                raise ValueError("批次不存在")
            target = data.get("status", current["status"])
            if target == "进行中" and current["status"] != "进行中" and cur.execute("SELECT 1 FROM batch_info WHERE status='进行中' AND batch_id<>?", (key,)).fetchone():
                raise ValueError("已有进行中的批次，无法将此批次设为进行中")
            if current["status"] == "进行中" and target != "进行中" and cur.execute("SELECT 1 FROM manual_feed_record WHERE batch_id=? AND lifecycle_status='进行中'", (key,)).fetchone():
                raise ValueError("存在进行中的补料，请先结束或注明原因标记为未完成")
            cur.execute("UPDATE batch_info SET " + ",".join(f"{c}=?" for c in cols) + " WHERE batch_id=?", [data[c] for c in cols] + [key])

    def code_exists(self, code: str, exclude: str = "") -> bool:
        return self.db.q1("SELECT batch_id FROM batch_info WHERE batch_code=? AND batch_id<>?",
                          (code, exclude)) is not None

    def stages(self, batch_id: str) -> list[dict]:
        return rows_to_dicts(self.db.q("SELECT * FROM batch_stage WHERE batch_id=? ORDER BY sort_order,stage_name",
                                       (batch_id,)))

    def add_stage(self, batch_id: str, data: dict) -> str:
        sid = new_id("STG")
        sort = int(self.db.scalar("SELECT COALESCE(MAX(sort_order),-1)+1 FROM batch_stage WHERE batch_id=?", (batch_id,), 0))
        self.db.execute(
            "INSERT INTO batch_stage(stage_id,batch_id,stage_name,start_time,end_time,sort_order,notes) VALUES(?,?,?,?,?,?,?)",
            (sid, batch_id, data["stage_name"], data.get("start_time"), data.get("end_time"), sort, data.get("notes", "")),
        )
        return sid

    def update_stage(self, stage_id: str, data: dict) -> None:
        self.db.execute(
            "UPDATE batch_stage SET stage_name=?,start_time=?,end_time=?,notes=? WHERE stage_id=?",
            (data["stage_name"], data.get("start_time"), data.get("end_time"), data.get("notes", ""), stage_id),
        )

    def delete_stage(self, stage_id: str) -> None:
        self.db.execute("DELETE FROM batch_stage WHERE stage_id=?", (stage_id,))

    def parameters(self, batch_id: str) -> list[dict]:
        return rows_to_dicts(self.db.q(
            "SELECT p.*, s.stage_name FROM culture_parameter p LEFT JOIN batch_stage s ON s.stage_id=p.stage_id "
            "WHERE p.batch_id=? ORDER BY p.recorded_at DESC", (batch_id,)))

    def add_parameter(self, batch_id: str, data: dict) -> str:
        pid = new_id("PAR")
        self.db.execute(
            "INSERT INTO culture_parameter(param_id,batch_id,stage_id,param_name,param_value,unit,recorded_at,notes) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (pid, batch_id, data.get("stage_id") or None, data["param_name"], data.get("param_value"),
             data.get("unit", ""), data.get("recorded_at") or now_iso(), data.get("notes", "")),
        )
        return pid

    def delete_parameter(self, param_id: str) -> None:
        self.db.execute("DELETE FROM culture_parameter WHERE param_id=?", (param_id,))

    def mappings(self, batch_id: str) -> list[dict]:
        sql = """
        SELECT m.*, p.pump_code, p.pump_name, l.liquid_code, l.liquid_name
        FROM batch_pump_mapping m
        JOIN pump_info p ON p.pump_id=m.pump_id
        JOIN liquid_info l ON l.liquid_id=m.liquid_id
        WHERE m.batch_id=? ORDER BY p.pump_code
        """
        return rows_to_dicts(self.db.q(sql, (batch_id,)))

    def add_mapping(self, batch_id: str, data: dict) -> str:
        mid = new_id("MAP")
        self.db.execute(
            "INSERT INTO batch_pump_mapping(mapping_id,batch_id,pump_id,liquid_id,valid_from,valid_to,mapping_note) "
            "VALUES(?,?,?,?,?,?,?)",
            (mid, batch_id, data["pump_id"], data["liquid_id"], data.get("valid_from") or now_iso(),
             data.get("valid_to") or None, data.get("mapping_note", "")),
        )
        return mid

    def delete_mapping(self, mapping_id: str) -> None:
        self.db.execute("DELETE FROM batch_pump_mapping WHERE mapping_id=?", (mapping_id,))

    def mapping_for_pump(self, batch_id: str, pump_id: str, at_time: str | None = None) -> dict | None:
        sql = ("SELECT m.*, l.liquid_code, l.liquid_name FROM batch_pump_mapping m "
               "JOIN liquid_info l ON l.liquid_id=m.liquid_id WHERE m.batch_id=? AND m.pump_id=? "
               "AND (m.valid_to IS NULL OR m.valid_to>?) ORDER BY m.valid_from DESC LIMIT 1")
        row = self.db.q1(sql, (batch_id, pump_id, at_time or now_iso()))
        return None if row is None else dict(row)


class PlanRepo(CrudRepo):
    table = "feed_plan"
    pk = "plan_id"
    fields = ("plan_id", "batch_id", "version_no", "status", "created_at", "created_by", "notes")

    def plans_for_batch(self, batch_id: str) -> list[dict]:
        return rows_to_dicts(self.db.q("SELECT * FROM feed_plan WHERE batch_id=? ORDER BY version_no DESC", (batch_id,)))

    def latest(self, batch_id: str) -> dict | None:
        row = self.db.q1("SELECT * FROM feed_plan WHERE batch_id=? ORDER BY version_no DESC LIMIT 1", (batch_id,))
        return None if row is None else dict(row)

    def create(self, batch_id: str, user: str, copy_latest: bool = True, notes: str = "") -> str:
        nxt = int(self.db.scalar("SELECT COALESCE(MAX(version_no),0)+1 FROM feed_plan WHERE batch_id=?", (batch_id,), 1))
        pid = new_id("PLAN")
        with self.db.transaction() as cur:
            cur.execute("INSERT INTO feed_plan(plan_id,batch_id,version_no,status,created_at,created_by,notes) "
                        "VALUES(?,?,?,?,?,?,?)", (pid, batch_id, nxt, "草稿", now_iso(), user, notes))
            if copy_latest:
                prev = cur.execute("SELECT plan_id FROM feed_plan WHERE batch_id=? AND plan_id<>? "
                                   "ORDER BY version_no DESC LIMIT 1", (batch_id, pid)).fetchone()
                if prev:
                    for ev in cur.execute("SELECT * FROM feed_plan_event WHERE plan_id=? ORDER BY sort_order", (prev[0],)).fetchall():
                        cur.execute(
                            "INSERT INTO feed_plan_event(event_id,plan_id,stage_id,liquid_id,pump_id,planned_start,"
                            "planned_end,planned_volume_ml,target_flow_ml_h,duration_h,concentration_value,"
                            "concentration_unit,status,notes,sort_order) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (new_id("EVT"), pid, ev["stage_id"], ev["liquid_id"], ev["pump_id"], ev["planned_start"],
                             ev["planned_end"], ev["planned_volume_ml"], ev["target_flow_ml_h"], ev["duration_h"],
                             ev["concentration_value"], ev["concentration_unit"], "计划", ev["notes"], ev["sort_order"]),
                        )
        return pid

    def events(self, plan_id: str) -> list[dict]:
        sql = """
        SELECT e.*, l.liquid_code, l.liquid_name, p.pump_code, p.pump_name, s.stage_name
        FROM feed_plan_event e
        JOIN liquid_info l ON l.liquid_id=e.liquid_id
        JOIN pump_info p ON p.pump_id=e.pump_id
        LEFT JOIN batch_stage s ON s.stage_id=e.stage_id
        WHERE e.plan_id=? ORDER BY e.planned_start, e.sort_order
        """
        return rows_to_dicts(self.db.q(sql, (plan_id,)))

    def add_event(self, plan_id: str, data: dict) -> str:
        eid = new_id("EVT")
        sort = int(self.db.scalar("SELECT COALESCE(MAX(sort_order),-1)+1 FROM feed_plan_event WHERE plan_id=?", (plan_id,), 0))
        self.db.execute(
            "INSERT INTO feed_plan_event(event_id,plan_id,stage_id,liquid_id,pump_id,planned_start,planned_end,"
            "planned_volume_ml,target_flow_ml_h,duration_h,concentration_value,concentration_unit,status,notes,sort_order) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (eid, plan_id, data.get("stage_id") or None, data["liquid_id"], data["pump_id"],
             data.get("planned_start"), data.get("planned_end"), data.get("planned_volume_ml"),
             data.get("target_flow_ml_h"), data.get("duration_h"), data.get("concentration_value"),
             data.get("concentration_unit"), data.get("status", "计划"), data.get("notes", ""), sort),
        )
        return eid

    def update_event(self, event_id: str, data: dict) -> None:
        self.db.execute(
            "UPDATE feed_plan_event SET stage_id=?,liquid_id=?,pump_id=?,planned_start=?,planned_end=?,"
            "planned_volume_ml=?,target_flow_ml_h=?,duration_h=?,concentration_value=?,concentration_unit=?,"
            "status=?,notes=? WHERE event_id=?",
            (data.get("stage_id") or None, data["liquid_id"], data["pump_id"], data.get("planned_start"),
             data.get("planned_end"), data.get("planned_volume_ml"), data.get("target_flow_ml_h"),
             data.get("duration_h"), data.get("concentration_value"), data.get("concentration_unit"),
             data.get("status", "计划"), data.get("notes", ""), event_id),
        )

    def delete_event(self, event_id: str) -> None:
        self.db.execute("DELETE FROM feed_plan_event WHERE event_id=?", (event_id,))

    def set_status(self, plan_id: str, status: str) -> None:
        self.db.execute("UPDATE feed_plan SET status=? WHERE plan_id=?", (status, plan_id))

    def event(self, event_id: str) -> dict | None:
        row = self.db.q1("SELECT * FROM feed_plan_event WHERE event_id=?", (event_id,))
        return None if row is None else dict(row)


class CalibrationRepo(CrudRepo):
    table = "pump_calibration"
    pk = "calibration_id"
    fields = ("calibration_id", "pump_id", "calibration_date", "source_file_id", "calibration_status",
              "calibration_method", "notes", "created_at", "created_by")

    def records(self, pump_id: str = "") -> list[dict]:
        sql = """SELECT c.*, p.pump_code, p.pump_name,
                 (SELECT COUNT(*) FROM pump_calibration_point pt WHERE pt.calibration_id=c.calibration_id) AS point_count
                 FROM pump_calibration c JOIN pump_info p ON p.pump_id=c.pump_id"""
        params: list[Any] = []
        if pump_id:
            sql += " WHERE c.pump_id=?"
            params.append(pump_id)
        sql += " ORDER BY c.calibration_date DESC, c.created_at DESC"
        return rows_to_dicts(self.db.q(sql, params))

    def points(self, calibration_id: str) -> list[dict]:
        return rows_to_dicts(self.db.q(
            "SELECT * FROM pump_calibration_point WHERE calibration_id=? ORDER BY setpoint_value",
            (calibration_id,)))

    def create(self, pump_id: str, data: dict, points: Sequence[dict], user: str) -> str:
        cid = new_id("CAL")
        with self.db.transaction() as cur:
            cur.execute(
                "INSERT INTO pump_calibration(calibration_id,pump_id,calibration_date,source_file_id,"
                "calibration_status,calibration_method,notes,created_at,created_by) VALUES(?,?,?,?,?,?,?,?,?)",
                (cid, pump_id, data.get("calibration_date") or now_iso(), data.get("source_file_id"),
                 data.get("calibration_status", "待审核"), data.get("calibration_method", "手工录入"),
                 data.get("notes", ""), now_iso(), user),
            )
            for i, pt in enumerate(points):
                cur.execute(
                    "INSERT INTO pump_calibration_point(point_id,calibration_id,setpoint_value,setpoint_unit,"
                    "measured_flow,flow_unit,measured_volume,run_duration,duration_unit,sort_order) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (new_id("CPT"), cid, pt["setpoint_value"], pt.get("setpoint_unit", "rpm"),
                     pt.get("measured_flow"), pt.get("flow_unit", "mL/h"), pt.get("measured_volume"),
                     pt.get("run_duration"), pt.get("duration_unit"), i),
                )
        return cid

    def set_status(self, calibration_id: str, status: str) -> None:
        with self.db.transaction() as cur:
            if status == "有效":
                pump = cur.execute("SELECT pump_id FROM pump_calibration WHERE calibration_id=?", (calibration_id,)).fetchone()
                if pump:
                    cur.execute("UPDATE pump_calibration SET calibration_status='过期' WHERE pump_id=? AND calibration_id<>? "
                                "AND calibration_status='有效'", (pump[0], calibration_id))
            cur.execute("UPDATE pump_calibration SET calibration_status=? WHERE calibration_id=?", (status, calibration_id))

    def effective(self, pump_id: str) -> dict | None:
        row = self.db.q1("SELECT * FROM pump_calibration WHERE pump_id=? AND calibration_status='有效' "
                         "ORDER BY calibration_date DESC LIMIT 1", (pump_id,))
        return None if row is None else dict(row)


class ImportRepo(CrudRepo):
    table = "import_record"
    pk = "import_id"
    fields = ("import_id", "batch_id", "source_type", "original_filename", "archived_path", "file_hash",
              "imported_at", "imported_by", "row_count", "success_count", "error_count", "mapping_config",
              "import_status", "notes")

    def list_recent(self, batch_id: str = "", limit: int = 200) -> list[dict]:
        sql = "SELECT i.*, b.batch_code FROM import_record i LEFT JOIN batch_info b ON b.batch_id=i.batch_id"
        params: list[Any] = []
        if batch_id:
            sql += " WHERE i.batch_id=?"
            params.append(batch_id)
        sql += " ORDER BY i.imported_at DESC LIMIT ?"
        params.append(limit)
        return rows_to_dicts(self.db.q(sql, params))

    def create(self, data: dict) -> str:
        iid = new_id("IMP")
        self.db.execute(
            "INSERT INTO import_record(import_id,batch_id,source_type,original_filename,archived_path,file_hash,"
            "imported_at,imported_by,row_count,success_count,error_count,mapping_config,import_status,notes) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (iid, data.get("batch_id") or None, data["source_type"], data["original_filename"],
             data.get("archived_path"), data.get("file_hash"), now_iso(), data.get("imported_by"),
             data.get("row_count", 0), data.get("success_count", 0), data.get("error_count", 0),
             json.dumps(data.get("mapping_config", {}), ensure_ascii=False), data.get("import_status", "成功"),
             data.get("notes", "")),
        )
        return iid

    def update_counts(self, import_id: str, **kw: Any) -> None:
        allowed = {k: kw[k] for k in ("row_count", "success_count", "error_count", "import_status", "notes") if k in kw}
        if allowed:
            self.update(import_id, allowed)

    def normalized(self, import_id: str) -> list[dict]:
        return rows_to_dicts(self.db.q(
            "SELECT n.*, p.pump_code FROM dose_data_normalized n JOIN pump_info p ON p.pump_id=n.pump_id "
            "WHERE n.import_id=? ORDER BY n.timestamp_utc", (import_id,)))

    def insert_normalized(self, rows: Sequence[dict]) -> None:
        if not rows:
            return
        payload = [(r["dose_row_id"], r["import_id"], r["batch_id"], r["pump_id"], r["timestamp_utc"],
                    r.get("flow_rate"), r.get("flow_unit"), r.get("total_volume"), r.get("volume_unit"),
                    r.get("pump_status"), r.get("counter_segment", 1), r.get("quality_flags", ""),
                    r.get("raw_row_no")) for r in rows]
        self.db.executemany(
            "INSERT INTO dose_data_normalized(dose_row_id,import_id,batch_id,pump_id,timestamp_utc,flow_rate,"
            "flow_unit,total_volume,volume_unit,pump_status,counter_segment,quality_flags,raw_row_no) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", payload)

    def data_for(self, batch_id: str, pump_id: str, start: str, end: str) -> list[dict]:
        return rows_to_dicts(self.db.q(
            "SELECT * FROM dose_data_normalized WHERE batch_id=? AND pump_id=? AND timestamp_utc BETWEEN ? AND ? "
            "ORDER BY timestamp_utc", (batch_id, pump_id, start, end)))

    def imports_for_pump(self, batch_id: str, pump_id: str) -> list[dict]:
        sql = """SELECT DISTINCT i.* FROM import_record i
                 JOIN dose_data_normalized n ON n.import_id=i.import_id
                 WHERE i.batch_id=? AND n.pump_id=? ORDER BY i.imported_at DESC"""
        return rows_to_dicts(self.db.q(sql, (batch_id, pump_id)))


class DoseRepo(CrudRepo):
    table = "dose_calculation"
    pk = "calculation_id"
    fields = ("calculation_id", "batch_id", "event_id", "pump_id", "liquid_id", "time_start", "time_end",
              "planned_volume_ml", "actual_volume_ml", "flow_integral_ml", "deviation_ml",
              "deviation_percent", "completion_percent", "calculation_method", "quality_status",
              "calculation_version", "calculated_at", "data_import_id", "notes")

    def list_for_batch(self, batch_id: str) -> list[dict]:
        sql = """SELECT c.*, p.pump_code, l.liquid_name,
                 (SELECT COUNT(*) FROM dose_anomaly a WHERE a.calculation_id=c.calculation_id) AS anomaly_count
                 FROM dose_calculation c JOIN pump_info p ON p.pump_id=c.pump_id
                 LEFT JOIN liquid_info l ON l.liquid_id=c.liquid_id
                 WHERE c.batch_id=? ORDER BY c.calculated_at DESC, c.calculation_version DESC"""
        return rows_to_dicts(self.db.q(sql, (batch_id,)))

    def create(self, data: dict) -> str:
        cid = new_id("CALC")
        ver = int(self.db.scalar(
            "SELECT COALESCE(MAX(calculation_version),0)+1 FROM dose_calculation WHERE batch_id=? AND pump_id=? AND time_start=?",
            (data["batch_id"], data["pump_id"], data["time_start"]), 1))
        self.db.execute(
            "INSERT INTO dose_calculation(calculation_id,batch_id,event_id,pump_id,liquid_id,time_start,time_end,"
            "planned_volume_ml,actual_volume_ml,flow_integral_ml,deviation_ml,deviation_percent,completion_percent,"
            "calculation_method,quality_status,calculation_version,calculated_at,data_import_id,notes,value_source) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (cid, data["batch_id"], data.get("event_id") or None, data["pump_id"], data.get("liquid_id"),
             data["time_start"], data["time_end"], data.get("planned_volume_ml"), data.get("actual_volume_ml"),
             data.get("flow_integral_ml"), data.get("deviation_ml"), data.get("deviation_percent"),
             data.get("completion_percent"), data.get("calculation_method"), data.get("quality_status"),
             ver, now_iso(), data.get("data_import_id"), data.get("notes", ""), data.get("value_source", "来源待核实")),
        )
        return cid

    def get_full(self, calculation_id: str) -> dict | None:
        sql = """SELECT c.*, p.pump_code, p.pump_name, l.liquid_name, b.batch_code
                 FROM dose_calculation c JOIN pump_info p ON p.pump_id=c.pump_id
                 LEFT JOIN liquid_info l ON l.liquid_id=c.liquid_id
                 JOIN batch_info b ON b.batch_id=c.batch_id WHERE c.calculation_id=?"""
        row = self.db.q1(sql, (calculation_id,))
        return None if row is None else dict(row)


class AnomalyRepo(CrudRepo):
    table = "dose_anomaly"
    pk = "anomaly_id"
    fields = ("anomaly_id", "batch_id", "calculation_id", "import_id", "anomaly_type", "severity",
              "description", "status", "created_at", "resolved_at", "resolution_note")

    def list_for_batch(self, batch_id: str = "", status: str = "") -> list[dict]:
        sql = """SELECT a.*, b.batch_code FROM dose_anomaly a LEFT JOIN batch_info b ON b.batch_id=a.batch_id"""
        clauses, params = [], []
        if batch_id:
            clauses.append("a.batch_id=?")
            params.append(batch_id)
        if status:
            clauses.append("a.status=?")
            params.append(status)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY CASE a.status WHEN '未解决' THEN 0 ELSE 1 END, a.created_at DESC"
        return rows_to_dicts(self.db.q(sql, params))

    def create(self, data: dict) -> str:
        aid = new_id("ANOM")
        self.db.execute(
            "INSERT INTO dose_anomaly(anomaly_id,batch_id,calculation_id,import_id,anomaly_type,severity,"
            "description,status,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (aid, data.get("batch_id"), data.get("calculation_id"), data.get("import_id"),
             data["anomaly_type"], data.get("severity", "警告"), data.get("description", ""), "未解决", now_iso()),
        )
        return aid

    def resolve(self, anomaly_id: str, note: str) -> None:
        if not note.strip():
            raise ValueError("解决异常必须填写说明")
        self.db.execute("UPDATE dose_anomaly SET status='已解决',resolved_at=?,resolution_note=? WHERE anomaly_id=?",
                        (now_iso(), note.strip(), anomaly_id))


class ReportRepo(CrudRepo):
    table = "report_record"
    pk = "report_id"
    fields = ("report_id", "batch_id", "report_type", "file_path", "file_hash", "generated_at",
              "generated_by", "version_no", "notes")

    def list_for_batch(self, batch_id: str = "") -> list[dict]:
        sql = """SELECT r.*, b.batch_code FROM report_record r LEFT JOIN batch_info b ON b.batch_id=r.batch_id"""
        params: list[Any] = []
        if batch_id:
            sql += " WHERE r.batch_id=?"
            params.append(batch_id)
        sql += " ORDER BY r.generated_at DESC"
        return rows_to_dicts(self.db.q(sql, params))

    def create(self, data: dict) -> str:
        rid = new_id("RPT")
        ver = int(self.db.scalar("SELECT COALESCE(MAX(version_no),0)+1 FROM report_record WHERE batch_id=? AND report_type=?",
                                 (data["batch_id"], data["report_type"]), 1))
        self.db.execute(
            "INSERT INTO report_record(report_id,batch_id,report_type,file_path,file_hash,generated_at,"
            "generated_by,version_no,notes) VALUES(?,?,?,?,?,?,?,?,?)",
            (rid, data["batch_id"], data["report_type"], data["file_path"], data.get("file_hash"),
             now_iso(), data.get("generated_by"), ver, data.get("notes", "")),
        )
        return rid


class LogRepo(CrudRepo):
    table = "operation_log"
    pk = "log_id"
    fields = ("log_id", "user_id", "action_type", "object_type", "object_id", "before_value",
              "after_value", "reason", "created_at")

    def recent(self, limit: int = 200) -> list[dict]:
        return rows_to_dicts(self.db.q("SELECT * FROM operation_log ORDER BY created_at DESC LIMIT ?", (limit,)))

    def add(self, user: str, action: str, object_type: str = "", object_id: str = "",
            before: Any = None, after: Any = None, reason: str = "") -> None:
        self.db.execute(
            "INSERT INTO operation_log(log_id,user_id,action_type,object_type,object_id,before_value,"
            "after_value,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
            (new_id("LOG"), user, action, object_type, object_id,
             None if before is None else json.dumps(before, ensure_ascii=False, default=str),
             None if after is None else json.dumps(after, ensure_ascii=False, default=str),
             reason, now_iso()),
        )


class Repositories:
    """仓储容器，随 Database 一起传给界面层。"""
    def __init__(self, db: Database):
        self.db = db
        self.components = ComponentRepo(db)
        self.liquids = LiquidRepo(db)
        self.pumps = PumpRepo(db)
        self.reactors = ReactorRepo(db)
        self.formulas = FormulaRepo(db)
        self.batches = BatchRepo(db)
        self.plans = PlanRepo(db)
        self.calibrations = CalibrationRepo(db)
        self.imports = ImportRepo(db)
        self.doses = DoseRepo(db)
        self.anomalies = AnomalyRepo(db)
        self.reports = ReportRepo(db)
        self.logs = LogRepo(db)
