from __future__ import annotations

import unittest
from pathlib import Path


class StockWorkspaceWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(__file__).resolve().parents[1]

    def test_workspace_contains_all_three_stock_modules(self):
        source = (self.root / "app/ui/stock_workspace_page.py").read_text(encoding="utf-8")
        self.assertIn("Monthly Stock & ML", source)
        self.assertIn("Final Tyre Stock", source)
        self.assertIn("Daily Stock", source)
        self.assertIn("MonthlyStockPage", source)
        self.assertIn("StockMasterPage", source)
        self.assertIn("DailyStockPage", source)

    def test_main_window_routes_stock_index_to_unified_workspace(self):
        source = (self.root / "app/ui/main_window.py").read_text(encoding="utf-8")
        self.assertIn("from app.ui.stock_workspace_page import StockWorkspacePage", source)
        self.assertIn('lambda: StockWorkspacePage(', source)

    def test_master_data_stock_card_bypasses_old_intermediate_hub(self):
        source = (self.root / "app/ui/master_data_hub_page.py").read_text(encoding="utf-8")
        marker = 'if key == "Stock Master Hub":'
        start = source.index(marker)
        block = source[start:start + 400]
        self.assertIn('self.page_indexes.get("Final Tyre Stock")', block)
        self.assertNotIn("self.render_stock_view()", block)


if __name__ == "__main__":
    unittest.main()
