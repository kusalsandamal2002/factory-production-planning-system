import unittest
from datetime import date
from pathlib import Path

from openpyxl import Workbook

from app.services.ai_planning_service import AIPlanningService
from app.services.intelligent_excel_import_service import IntelligentExcelImportService
from app.services.stock_planning_service import calculate_available_stock


class AIPlanningV8InvariantTests(unittest.TestCase):
    def test_workbook_filename_is_plan_date_authority_when_daily_plan_cell_missing(self):
        wb = Workbook()
        wb.active.title = "PROD"
        detected = IntelligentExcelImportService()._detect_plan_date(
            wb, Path("OVEN SHEET PLAN NOVEMBER 30-2025.xlsx")
        )
        self.assertEqual(detected, date(2025, 11, 30))

    def test_scrap_and_blocked_are_not_double_subtracted_from_usable_stock(self):
        self.assertEqual(
            calculate_available_stock(
                fg_stock=0, qc_stock=0, scrap_stock=0, blocked_stock=12
            ),
            0,
        )
        self.assertEqual(
            calculate_available_stock(
                fg_stock=10, qc_stock=2, scrap_stock=4, blocked_stock=3
            ),
            12,
        )

    def test_date_aware_completion_uses_weekday_signal_only_with_enough_samples(self):
        model = {
            "ewma_completion_ratio": 0.90,
            "median_completion_ratio": 0.92,
            "model_json": {
                "weekday_completion": {
                    "0": {"ratio": 1.05, "samples": 4},
                    "1": {"ratio": 0.70, "samples": 1},
                }
            },
        }
        monday = AIPlanningService._completion_for_date(model, date(2026, 8, 10))
        tuesday = AIPlanningService._completion_for_date(model, date(2026, 8, 11))
        self.assertGreater(monday, tuesday)
        self.assertGreater(monday, 0.92)


if __name__ == "__main__":
    unittest.main()
