# -*- coding: utf-8 -*-
"""手工记录、历史数据库升级和设备数据质量的隔离验证。"""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.db import Database, SCHEMA_SQL
from app.repositories import Repositories
from app.services.manual_feed import ManualFeedService, evaluate
from app.services import dose_calc
from app.services.reporting import ReportService
from app.importers.dose_importer import DoseImportService


class ManualFeedTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ccds_manual_")
        self.settings = Settings(data_dir=self.temp.name)
        self.settings.ensure_dirs()
        self.db = Database(self.settings.db_path)
        self.db.seed_defaults()
        self.repos = Repositories(self.db)
        self.batch = self.repos.batches.create({"batch_code": "TEST", "status": "进行中", "created_by": "test"})
        self.pump = self.repos.pumps.active()[0]['pump_id']
        self.liquid = self.repos.liquids.active()[0]['liquid_id']
        self.data = {"batch_id": self.batch, "pump_id": self.pump, "liquid_id": self.liquid,
                     "start_time": "2026-11-17 08:00", "end_time": "2026-11-17 10:00",
                     "start_reading": "0.1", "end_reading": "0.14", "reading_unit": "L"}
        self.service = ManualFeedService(self.db)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_manual_plan_and_measurement_report(self):
        plan = self.repos.plans.create(self.batch, "test", copy_latest=False)
        event = self.repos.plans.add_event(plan, {"pump_id": self.pump, "liquid_id": self.liquid, "planned_volume_ml": 50})
        self.data.update(event_id=event, intermediate_readings="2026-11-17 09:00,0.12",
                         measured_value="38", measured_unit="mL", measured_method="量筒")
        self.service.save(self.data, "test")
        row = self.service.list_for_batch(self.batch)[0]
        self.assertAlmostEqual(row['estimate_ml'], 40)
        self.assertEqual(row['measured_ml'], 38)
        self.assertEqual(row['planned_volume_ml'], 50)
        report = ReportService(self.repos, self.settings)
        xlsx = report.generate_excel(self.batch, "test")
        pdf = report.generate_pdf(self.batch, "test")
        from openpyxl import load_workbook
        wb = load_workbook(xlsx, read_only=True, data_only=True)
        self.assertIn("手工补料记录", wb.sheetnames)
        cells = list(wb["手工补料记录"].values)
        self.assertTrue(any("设备估算量(mL)" in row for row in cells))
        self.assertTrue(pdf.stat().st_size > 5000)
        wb.close()

    def test_review_preserves_raw_and_no_estimate(self):
        self.data.update(end_reading="0.01", intermediate_readings="2026-11-17 09:00,0.12")
        self.service.save(self.data, "test")
        row = self.service.list_for_batch(self.batch)[0]
        self.assertEqual(row['end_reading'], "0.01")
        self.assertIsNone(row['estimate_ml'])
        self.assertIsNone(row['measured_ml'])
        self.assertEqual(row['quality_status'], "待审核")
        self.assertIn("归零", row['issues'])
        for changes in ({"end_reading": ""}, {"end_time": "2026-11-17 07:00"}, {"reading_unit": ""}):
            self.assertIsNone(evaluate({**self.data, **changes})['estimate_ml'])
        self.assertIsNone(evaluate({**self.data, "end_reading": "0.2", "known_reset": True})['estimate_ml'])
        self.assertEqual(evaluate({**self.data, "start_reading": 0, "end_reading": 1})['estimate_ml'], 1000)

    def test_cumulative_gap_and_window(self):
        rows = [{"timestamp_utc": "2026-11-17T08:30:00+08:00", "total_volume": 10},
                {"timestamp_utc": "2026-11-17T14:30:00+08:00", "total_volume": 20}]
        result = dose_calc.calculate(rows, 20, "2026-11-17T08:00:00+08:00", "2026-11-17T15:00:00+08:00")
        self.assertEqual(result['quality_status'], '待审核')
        self.assertEqual({a['anomaly_type'] for a in result['anomalies']}, {'数据断点', '时间窗口覆盖不足'})

    def test_import_requires_units(self):
        path = Path(self.temp.name) / 'dose.csv'
        pump = self.repos.pumps.active()[0]['pump_code']
        path.write_text(f'time,pump,total\n2026-11-17 08:00,{pump},1\n', encoding='utf-8')
        service = DoseImportService(self.repos, self.settings)
        mapping = service.suggest_mapping(service.read(path).headers)
        self.assertTrue(service.preview(self.batch, path, None, 1, mapping).errors)
        self.assertFalse(service.preview(self.batch, path, None, 1, mapping, default_volume_unit='L').errors)

    def test_migration_marks_legacy_unknown(self):
        path = Path(self.temp.name) / 'old.db'
        old = sqlite3.connect(path)
        old.executescript(SCHEMA_SQL)
        old.execute("INSERT INTO batch_info(batch_id,batch_code,created_at) VALUES ('b','b','x')")
        old.execute("INSERT INTO pump_info(pump_id,pump_code,created_at) VALUES ('p','p','x')")
        old.execute("INSERT INTO dose_calculation(calculation_id,batch_id,pump_id,time_start,time_end,actual_volume_ml,calculated_at) VALUES ('c','b','p','a','b',12,'x')")
        old.commit()
        old.close()
        upgraded = Database(path)
        row = upgraded.q1("SELECT actual_volume_ml,value_source FROM dose_calculation WHERE calculation_id='c'")
        self.assertEqual(tuple(row), (12, '来源待核实'))
        upgraded.close()

    def test_backup_restore_preserves_manual_record(self):
        from app.services.backup import BackupService
        self.service.save(self.data, "test")
        backup = BackupService(self.db, self.settings)
        path = backup.create("manual test")
        self.assertEqual(backup.verify(path)['manifest']['counts']['manual_feed_record'], 1)
        self.db.execute("DELETE FROM manual_feed_record")
        backup.restore(path)
        self.db = Database(self.settings.db_path)
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM manual_feed_record"), 1)

    def test_lifecycle_correction_and_batch_guards(self):
        data = {**self.data, "end_time": "", "end_reading": ""}
        rid = self.service.save(data, "operator", start_only=True)
        row = self.service.list_for_batch(self.batch)[0]
        self.assertEqual((row['lifecycle_status'], row['quality_status']), ('进行中', '进行中'))
        with self.assertRaises(ValueError):
            self.repos.batches.create({'batch_code': 'OTHER', 'status': '进行中'})
        with self.assertRaises(ValueError):
            self.repos.batches.update(self.batch, {'status': '已完成'})
        with self.assertRaises(ValueError):
            self.service.update_record(rid, {}, 'operator')
        self.service.update_record(rid, {'end_time': '2026-11-17 10:00', 'end_reading': '0.14'}, 'operator')
        with self.assertRaises(ValueError):
            self.service.update_record(rid, {'end_reading': '0.15'}, 'operator')
        self.service.update_record(rid, {'end_reading': '0.15'}, 'operator', '更正抄录')
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM manual_feed_revision WHERE record_id=?", (rid,)), 2)
        revision = self.db.q1("SELECT * FROM manual_feed_revision WHERE record_id=? AND action='更正'", (rid,))
        self.assertEqual((json.loads(revision['before_json'])['end_reading'], json.loads(revision['after_json'])['end_reading'], revision['reason'], revision['operator']), ('0.14', '0.15', '更正抄录', 'operator'))
        self.assertAlmostEqual(self.service.list_for_batch(self.batch)[0]['estimate_ml'], 50)
        self.repos.batches.update(self.batch, {'status': '已完成'})
        self.repos.batches.create({'batch_code': 'OTHER', 'status': '进行中'})

    def test_incomplete_requires_reason_and_preserves_start(self):
        rid = self.service.save({**self.data, 'end_time': '', 'end_reading': ''}, 'operator', start_only=True)
        with self.assertRaises(ValueError):
            self.service.mark_incomplete(rid, 'operator', '')
        self.service.mark_incomplete(rid, 'operator', '中止补料')
        row = self.service.list_for_batch(self.batch)[0]
        self.assertEqual(row['lifecycle_status'], '未完成')
        self.assertEqual(row['start_reading'], '0.1')
        self.assertIsNone(row['estimate_ml'])
        self.repos.batches.update(self.batch, {'status': '已完成'})

    def test_existing_multiple_batches_are_not_changed(self):
        self.db.execute("INSERT INTO batch_info(batch_id,batch_code,status,created_at) VALUES('legacy','OLD','进行中','x')")
        with self.assertRaises(ValueError):
            self.repos.batches.create({'batch_code': 'OTHER', 'status': '进行中'})
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM batch_info WHERE status='进行中'"), 2)
        self.repos.batches.update('legacy', {'status': '已完成'})
        self.assertEqual(self.db.scalar("SELECT COUNT(*) FROM batch_info WHERE status='进行中'"), 1)

    def test_commercial_medium_is_in_batch_report(self):
        self.db.execute("INSERT INTO commercial_medium_record VALUES(?,?,?,?,?,?,?,?,?)", ('med', self.batch, '示例成品', 'LOT-1', 500, 'mL', '2026-11-17 08:00', 'operator', ''))
        report = ReportService(self.repos, self.settings)
        self.assertEqual(report.collect(self.batch)['commercial'][0]['product_lot'], 'LOT-1')
        from openpyxl import load_workbook
        wb = load_workbook(report.generate_excel(self.batch, 'operator'), read_only=True)
        self.assertIn('成品培养基', wb.sheetnames)
        wb.close()


if __name__ == '__main__':
    unittest.main()
