from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DailyStockProfessionalV23Tests(unittest.TestCase):
    def setUp(self):
        source = (
            ROOT / "app" / "ui" / "daily_stock_page.py"
        ).read_text(encoding="utf-8-sig")
        marker = "# MPPS V23 DAILY STOCK PROFESSIONAL VIEW"
        self.assertIn(marker, source)
        self.v23 = source[source.index(marker):]

    def test_compact_controls_and_latest_badge(self):
        self.assertIn(
            "self.date_input.setMaximumWidth(230)",
            self.v23,
        )
        self.assertIn(
            'self.latest_badge = QLabel("LATEST DATA\\n—")',
            self.v23,
        )
        self.assertIn(
            "controls.addLayout(search_box, 1)",
            self.v23,
        )

    def test_no_summary_cards(self):
        self.assertNotIn("MetricCard", self.v23)
        self.assertNotIn("summary_card", self.v23)

    def test_filters_are_present(self):
        for label in (
            "All Items",
            "Produced Items",
            "Available Stock > 0",
            "Scrap / Blocked Items",
        ):
            self.assertIn(label, self.v23)

    def test_empty_state_is_date_specific(self):
        self.assertIn(
            'self.empty_state.setObjectName("DailyEmptyState")',
            self.v23,
        )
        self.assertIn("No Daily Stock Data", self.v23)
        self.assertIn(
            "Select another date from the calendar.",
            self.v23,
        )

    def test_technical_table_subtitle_is_removed_in_v23(self):
        start = self.v23.index(
            "def _mpps_v23_build_table_card"
        )
        end = self.v23.index(
            "def _mpps_v23_setup_table",
            start,
        )
        block = self.v23[start:end]
        self.assertNotIn(
            "Selected-date snapshot from the committed OVEN workbook",
            block,
        )

    def test_exception_colors_are_applied(self):
        self.assertIn(
            'warning_color = QColor("#b45309")',
            self.v23,
        )
        self.assertIn(
            'danger_color = QColor("#b91c1c")',
            self.v23,
        )
        self.assertIn(
            'positive_color = QColor("#047857")',
            self.v23,
        )


if __name__ == "__main__":
    unittest.main()
