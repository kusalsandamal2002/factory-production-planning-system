
from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TyreMasterV33Tests(unittest.TestCase):
    def setUp(self):
        self.page = (
            ROOT / "app" / "ui" / "tyre_item_master_pro_page.py"
        ).read_text(encoding="utf-8-sig")
        self.service = (
            ROOT
            / "app"
            / "services"
            / "tyre_master_auto_intelligence_service.py"
        ).read_text(encoding="utf-8-sig")
        self.main = (
            ROOT / "app" / "ui" / "main_window.py"
        ).read_text(encoding="utf-8-sig")

    def test_python_syntax(self):
        ast.parse(self.page)
        ast.parse(self.service)
        ast.parse(self.main)

    def test_four_professional_tabs_only(self):
        for label in (
            "Master Items",
            "Process & Factory",
            "Data Quality",
            "AI / ML",
        ):
            self.assertIn(label, self.page)

        self.assertNotIn(
            '("Tyre Size", "size")',
            self.page,
        )
        self.assertNotIn(
            '("SMDS", "smds")',
            self.page,
        )

    def test_tableview_and_server_pagination(self):
        self.assertIn(
            "QTableView",
            self.page,
        )
        self.assertIn(
            "class _RowsModel(QAbstractTableModel)",
            self.page,
        )
        self.assertIn(
            "PAGE_SIZE = 200",
            self.page,
        )
        self.assertIn(
            "LIMIT :limit OFFSET :offset",
            self.service,
        )

    def test_daily_workbook_sources_are_parsed(self):
        for token in (
            '"Daily Plan"',
            '"OVEN"',
            '"PROD"',
            "column=227",
            "day_produced",
            "night_produced",
        ):
            self.assertIn(
                token,
                self.service,
            )

    def test_auto_sync_updates_smds_and_history(self):
        self.assertIn(
            "INSERT INTO smds",
            self.service,
        )
        self.assertIn(
            "mpps_tyre_workbook_observation",
            self.service,
        )
        self.assertIn(
            "mpps_tyre_factory_mapping",
            self.service,
        )

    def test_eight_ml_modules_exist(self):
        for key in (
            "MASTER_HEALTH",
            "SIMILAR_TYRE",
            "CURING_TIME",
            "LINE_OVEN_COMPATIBILITY",
            "WEIGHT_BASELINE",
            "SHIFT_PRODUCTIVITY",
            "PLAN_ACHIEVEMENT",
            "STOCK_PRODUCTION_RISK",
        ):
            self.assertIn(
                key,
                self.service,
            )

    def test_main_window_runs_background_auto_sync(self):
        self.assertIn(
            "# MPPS V33 TYRE MASTER AUTO EXCEL LEARNING",
            self.main,
        )
        self.assertIn(
            "class _V33TyreSyncWorker",
            self.main,
        )
        self.assertIn(
            "setInterval(20000)",
            self.main,
        )


if __name__ == "__main__":
    unittest.main()
