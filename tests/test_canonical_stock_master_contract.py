
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CanonicalStockMasterContractTests(unittest.TestCase):
    def test_sidebar_routes_to_unified_stock_workspace(self):
        source = (ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
        self.assertIn(
            'self._add_nav_button(layout, "Stock Master", self.STOCK_MASTER_INDEX)',
            source,
        )
        self.assertNotIn(
            'self._add_nav_button(layout, "Stock Control", self.STOCK_MASTER_INDEX)',
            source,
        )
        self.assertIn(
            'from app.ui.stock_workspace_page import StockWorkspacePage',
            source,
        )

        start = source.index("self.STOCK_MASTER_INDEX,")
        end = source.index("self.BOM_MASTER_INDEX,", start)
        block = source[start:end]
        self.assertIn("StockWorkspacePage(", block)
        self.assertIn('"Stock Master"', block)

    def test_master_data_card_uses_same_stock_master_index(self):
        source = (ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
        start = source.index("lambda: MasterDataHubPage(")
        end = source.index("                    },", start)
        block = " ".join(source[start:end].split())
        self.assertIn('"Stock Master": ( self.STOCK_MASTER_INDEX )', block)

    def test_master_data_hub_uses_canonical_key(self):
        source = (ROOT / "app" / "ui" / "master_data_hub_page.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn('"Stock Master Hub",', source)
        self.assertIn('key = "Stock Master"', source)
        self.assertIn('index = self.page_indexes.get("Stock Master")', source)
        self.assertNotIn(
            'if key == "Stock Master Hub":\n'
            '            index = self.page_indexes.get("Final Tyre Stock")',
            source,
        )
        self.assertNotIn(
            'if key == "Stock Master Hub":\n'
            '            self.render_stock_view()',
            source,
        )

    def test_workspace_breadcrumb_matches_primary_navigation(self):
        source = (ROOT / "app" / "ui" / "stock_workspace_page.py").read_text(
            encoding="utf-8"
        )
        self.assertTrue(
            'QLabel("Data  /  Stock Master")' in source
            or 'QLabel("Data / Stock Master")' in source
        )


if __name__ == "__main__":
    unittest.main()
