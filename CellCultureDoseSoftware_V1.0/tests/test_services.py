# -*- coding: utf-8 -*-
"""核心计算与导入服务单元测试。"""
from __future__ import annotations
import os, sys, tempfile, unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.units import (concentration_to_g_l, flow_to_ml_h, volume_to_l,
                                mass_conc_to_g_l, molar_conc_to_mol_l)
from app.services.formula_calc import calculate_line, calculate_formula
from app.services.calibration import interpolate
from app.services import dose_calc
from app.importers.table_reader import split_number_unit


class UnitsTest(unittest.TestCase):
    def test_conversions(self):
        self.assertAlmostEqual(volume_to_l(1000, "mL"), 1.0)
        self.assertAlmostEqual(flow_to_ml_h(2, "mL/min"), 120.0)
        self.assertAlmostEqual(mass_conc_to_g_l(5, "mg/mL"), 5.0)
        self.assertAlmostEqual(molar_conc_to_mol_l(10, "mM"), 0.01)
        self.assertAlmostEqual(concentration_to_g_l(10, "mM", 180.16), 1.8016)

    def test_split_number_unit(self):
        self.assertEqual(split_number_unit("0.000"), (0.0, None))
        self.assertEqual(split_number_unit("10 mL/h"), (10.0, "mL/h"))
        self.assertEqual(split_number_unit("1,200"), (1200.0, None))

    def test_bad_unit(self):
        with self.assertRaises(Exception):
            concentration_to_g_l(1, "banana")


class FormulaTest(unittest.TestCase):
    def test_direct_with_purity(self):
        line = calculate_line({"target_concentration": 4, "concentration_unit": "g/L",
                               "purity_fraction": 0.8, "source_type": "直接称量"}, 1.0)
        self.assertAlmostEqual(line["theoretical_amount_g"], 4.0)
        self.assertAlmostEqual(line["corrected_amount_g"], 5.0)

    def test_stock_volume(self):
        line = calculate_line({"target_concentration": 5, "concentration_unit": "mg/L",
                               "molecular_weight": 5807.6, "purity_fraction": 1.0,
                               "source_type": "母液", "stock_concentration": 10,
                               "stock_unit": "g/L"}, 1.0)
        self.assertAlmostEqual(line["stock_volume_ml"], 0.5)

    def test_molar(self):
        line = calculate_line({"target_concentration": 1, "concentration_unit": "mM",
                               "molecular_weight": 180.16, "purity_fraction": 1.0,
                               "source_type": "直接称量"}, 1.0)
        self.assertAlmostEqual(line["theoretical_amount_g"], 0.18016)

    def test_solvent(self):
        result = calculate_formula([
            {"component_id": "c1", "target_concentration": 10, "concentration_unit": "g/L",
             "molecular_weight": 100, "purity_fraction": 1.0, "source_type": "母液",
             "stock_concentration": 100, "stock_unit": "g/L"},
        ], 1000, "mL")
        self.assertAlmostEqual(result["total_stock_ml"], 100.0)
        self.assertAlmostEqual(result["solvent_ml"], 900.0)


class CalibrationTest(unittest.TestCase):
    def setUp(self):
        self.points = [
            {"setpoint_value": 10, "setpoint_unit": "rpm", "measured_flow": 2, "flow_unit": "mL/h"},
            {"setpoint_value": 30, "setpoint_unit": "rpm", "measured_flow": 6, "flow_unit": "mL/h"},
        ]

    def test_interpolation(self):
        result = interpolate(self.points, 20)
        self.assertAlmostEqual(result["flow_ml_h"], 4.0)
        self.assertTrue(result["in_range"])

    def test_out_of_range(self):
        result = interpolate(self.points, 40)
        self.assertIsNone(result["flow_ml_h"])
        self.assertFalse(result["in_range"])

    def test_duplicate_setpoint(self):
        points = self.points + [{"setpoint_value": 30, "setpoint_unit": "rpm",
                                 "measured_flow": 7, "flow_unit": "mL/h"}]
        self.assertIsNone(interpolate(points, 20)["flow_ml_h"])

    def test_unit_mismatch(self):
        points = [dict(self.points[0]), dict(self.points[1], setpoint_unit="%")]
        self.assertIsNone(interpolate(points, 20)["flow_ml_h"])


def make_rows():
    start = datetime(2026, 1, 1, 8, 0).astimezone()
    rows = []
    for i, (total, flow) in enumerate([(0, 10), (10, 10), (25, 15)]):
        rows.append({"timestamp_utc": (start + timedelta(hours=i)).isoformat(),
                     "total_volume": total, "volume_unit": "mL",
                     "flow_rate": flow, "flow_unit": "mL/h", "pump_status": "RUN"})
    return rows


class DoseTest(unittest.TestCase):
    def test_basic(self):
        result = dose_calc.calculate(make_rows(), 25)
        self.assertAlmostEqual(result["actual_volume_ml"], 25.0)
        self.assertAlmostEqual(result["flow_integral_ml"], 22.5)
        self.assertEqual(result["quality_status"], "有效")
        self.assertAlmostEqual(result["completion_percent"], 100.0)

    def test_reset_segments(self):
        start = datetime(2026, 1, 1, 8, 0).astimezone()
        rows = []
        for i, total in enumerate([0, 10, 5, 15]):
            rows.append({"timestamp_utc": (start + timedelta(hours=i)).isoformat(),
                         "total_volume": total, "volume_unit": "mL",
                         "flow_rate": 10, "flow_unit": "mL/h", "pump_status": "RUN"})
        result = dose_calc.calculate(rows, 20)
        self.assertAlmostEqual(result["actual_volume_ml"], 20.0)
        self.assertEqual(result["quality_status"], "待审核")
        self.assertTrue(result["anomalies"])

    def test_gap_marks_review(self):
        rows = make_rows()
        rows[2]["timestamp_utc"] = (dose_calc.parse_ts(rows[0]["timestamp_utc"]) + timedelta(hours=5)).isoformat()
        result = dose_calc.calculate(rows, 25, max_gap_h=2)
        self.assertEqual(result["quality_status"], "待审核")
        self.assertTrue(result["gaps"])

    def test_zero_planned(self):
        result = dose_calc.calculate(make_rows(), 0)
        self.assertIsNone(result["deviation_percent"])
        self.assertIsNone(result["completion_percent"])


class ImportNormalizationTest(unittest.TestCase):
    def test_liter_and_flow_units(self):
        from app.config import Settings
        from app.db import Database
        from app.repositories import Repositories
        from app.importers.dose_importer import DoseImportService
        tmp = Path(tempfile.mkdtemp(prefix="ccds_unit_"))
        settings = Settings(data_dir=str(tmp))
        settings.ensure_dirs()
        db = Database(settings.db_path); db.seed_defaults()
        repos = Repositories(db)
        batch_id = repos.batches.create({"batch_code": "B-U-1", "status": "进行中", "created_by": "t"})
        pump = repos.pumps.active()[0]
        path = tmp / "dose_units.csv"
        path.write_text("time,pump,flow,total\n2026-11-11 08:00:00,%s,120,0.1\n2026-11-11 09:00:00,%s,120,0.2\n"
                        % (pump["pump_code"], pump["pump_code"]), encoding="utf-8")
        service = DoseImportService(repos, settings)
        table = service.read(path)
        mapping = service.suggest_mapping(table.headers)
        pv = service.preview(batch_id, path, None, 1, mapping,
                             default_flow_unit="mL/min", default_volume_unit="L")
        self.assertFalse(pv.errors, pv.errors)
        self.assertEqual(pv.normalized[0]["flow_rate"], 7200.0)
        self.assertEqual(pv.normalized[0]["flow_unit"], "mL/h")
        self.assertEqual(pv.normalized[0]["total_volume"], 100.0)
        self.assertEqual(pv.normalized[0]["volume_unit"], "mL")
        db.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
