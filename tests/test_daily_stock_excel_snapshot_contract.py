
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DailyStockExcelSnapshotContractTests(unittest.TestCase):
    def setUp(self):
        self.source = (
            ROOT / "app" / "ui" / "daily_stock_page.py"
        ).read_text(encoding="utf-8-sig")
        marker = "# MPPS V22 DAILY STOCK COMMITTED EXCEL SNAPSHOT"
        self.assertIn(marker, self.source)
        self.v22 = self.source[self.source.index(marker):]

    def test_no_user_action_buttons_in_v22(self):
        for label in ("Import Excel", "Export Excel", "Edit Selected", "Refresh"):
            self.assertNotIn(f'QPushButton("{label}")', self.v22)

    def test_calendar_and_latest_date(self):
        self.assertIn("self.date_input.setCalendarPopup(True)", self.v22)
        self.assertIn('self.date_input.setDisplayFormat("yyyy-MM-dd")', self.v22)
        self.assertIn("ORDER BY plan_date DESC, id DESC", self.v22)
        self.assertIn("self._latest_committed_excel_date()", self.v22)

    def test_exact_selected_date_and_latest_revision(self):
        self.assertIn("AND plan_date = :plan_date", self.v22)
        self.assertIn("ORDER BY id DESC", self.v22)
        self.assertIn("No committed OVEN Excel data for", self.v22)

    def test_no_fake_zero_seeding(self):
        start = self.v22.index("def _mpps_v22_daily_stock_refresh(self):")
        end = self.v22.index("def _mpps_v22_daily_stock_refresh_table", start)
        block = self.v22[start:end]
        self.assertNotIn("seed_date_from_final_stock", block)
        self.assertNotIn("ensure_daily_stock_table", block)

    def test_only_excel_backed_rows_are_visible(self):
        self.assertIn("source_file IS NOT NULL", self.v22)
        self.assertIn("source_file ILIKE :workbook_like", self.v22)
        self.assertIn("Excel-backed", self.v22)
        self.assertIn(
            "Daily Stock rows are stored for this date.",
            self.v22,
        )


if __name__ == "__main__":
    unittest.main()
