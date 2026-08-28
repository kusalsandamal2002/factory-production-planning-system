
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RemoveMonthlyOpeningStockContractTests(unittest.TestCase):
    def test_monthly_opening_stock_is_not_in_sidebar_or_factory(self):
        source = (ROOT / "app" / "ui" / "main_window.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('"Monthly Opening Stock"', source)
        self.assertNotIn("MonthlyStockCountPage(", source)
        self.assertNotIn(
            "from app.ui.monthly_stock_count_page import MonthlyStockCountPage",
            source,
        )

    def test_restricted_stock_roles_use_stock_master(self):
        source = (ROOT / "app" / "ui" / "main_window.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'subtitle = QLabel("Stock Master")',
            source,
        )
        self.assertIn(
            'self._add_nav_button(layout, "Stock Master", self.STOCK_MASTER_INDEX)',
            source,
        )
        self.assertIn(
            "self.STOCK_MASTER_INDEX\n"
            "            if self.monthly_stock_only_mode",
            source,
        )
        self.assertIn(
            '"stock_workspace_page"',
            source,
        )

    def test_old_index_redirects_to_stock_master(self):
        source = (ROOT / "app" / "ui" / "main_window.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "and index == self.MONTHLY_STOCK_COUNT_INDEX",
            source,
        )
        self.assertIn(
            "index = self.STOCK_MASTER_INDEX",
            source,
        )
        self.assertIn(
            '"Retired Legacy Module"',
            source,
        )

    def test_canonical_stock_master_is_the_visible_stock_workspace(self):
        source = (ROOT / "app" / "ui" / "main_window.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "from app.ui.stock_workspace_page import StockWorkspacePage",
            source,
        )
        start = source.index("self.STOCK_MASTER_INDEX,")
        end = source.index("self.BOM_MASTER_INDEX,", start)
        self.assertIn("StockWorkspacePage(", source[start:end])

    def test_master_data_stock_card_uses_canonical_route(self):
        source = (ROOT / "app" / "ui" / "master_data_hub_page.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('"Stock Master Hub",', source)
        self.assertIn('"Stock Master",', source)


if __name__ == "__main__":
    unittest.main()
