
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DailyStockCleanHeaderContractTests(unittest.TestCase):
    def setUp(self):
        source = (
            ROOT / "app" / "ui" / "daily_stock_page.py"
        ).read_text(encoding="utf-8-sig")
        marker = "# MPPS V22.2 DAILY STOCK CLEAN HEADER"
        self.assertIn(marker, source)
        self.v22_2 = source[source.index(marker):]

    def test_top_subtitle_is_not_in_clean_control_card(self):
        start = self.v22_2.index(
            "def _mpps_v22_2_build_control_card"
        )
        end = self.v22_2.index(
            "def _mpps_v22_2_build_table_card",
            start,
        )
        block = self.v22_2[start:end]
        self.assertNotIn(
            "Read-only daily stock snapshots",
            block,
        )
        self.assertNotIn(
            "source_status",
            block,
        )

    def test_date_and_search_remain(self):
        self.assertIn(
            "form.addWidget(self.date_input",
            self.v22_2,
        )
        self.assertIn(
            "form.addWidget(self.search_input",
            self.v22_2,
        )

    def test_no_data_requirement_is_preserved(self):
        self.assertIn(
            "self.no_data_label",
            self.v22_2,
        )
        self.assertIn(
            'status.startswith("NO DATA")',
            self.v22_2,
        )

    def test_normal_source_status_is_hidden(self):
        self.assertIn(
            "self.source_status.hide()",
            self.v22_2,
        )


if __name__ == "__main__":
    unittest.main()
