from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class StockMasterCleanUIContractTests(unittest.TestCase):
    def test_unified_workspace_is_clean(self):
        source = (ROOT / "app" / "ui" / "stock_workspace_page.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('title = QLabel("Stock Master")', source)
        self.assertNotIn("Stock Master & Intelligence", source)
        self.assertNotIn("UNIFIED STOCK", source)
        self.assertNotIn("Refresh Current Tab", source)
        self.assertNotIn("Monthly Stock & ML", source)
        self.assertNotIn("Monthly Stock_ML", source)
        self.assertNotIn("root.addWidget(self._build_action_bar())", source)
        self.assertIn('"Monthly Stock"', source)
        self.assertIn('"Final Tyre Stock"', source)
        self.assertIn('"Daily Stock"', source)

    def test_monthly_stock_table_has_only_business_columns(self):
        source = (ROOT / "app" / "ui" / "monthly_stock_page.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("QTableWidget(0, 6)", source)
        expected_headers = (
            '"No.",',
            '"SAP Code",',
            '"Material Description",',
            '"Total Stock",',
            '"Scrap",',
            '"Block",',
        )
        for header in expected_headers:
            self.assertIn(header, source)

        self.assertNotIn('"ML Trend"', source)
        self.assertNotIn('"Next Month Forecast"', source)
        self.assertNotIn('"ML Risk"', source)
        self.assertNotIn("High ML Risk", source)
        self.assertNotIn("self.metric_risk", source)

    def test_stock_workspace_navigation_is_still_wired(self):
        source = (ROOT / "app" / "ui" / "main_window.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("StockWorkspacePage", source)
        self.assertIn('"Stock Master"', source)


if __name__ == "__main__":
    unittest.main()
