
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class RemoveFinalTyreStockContractTests(unittest.TestCase):
    def test_stock_workspace_has_exact_three_business_tabs(self):
        source = (
            ROOT / "app" / "ui" / "stock_workspace_page.py"
        ).read_text(encoding="utf-8")

        class_pos = source.index("class StockWorkspacePage")
        active = source[class_pos:]

        self.assertIn('"Monthly Stock"', active)
        self.assertIn('"Current Stock"', active)
        self.assertIn('"Daily Stock"', active)
        self.assertNotIn('"Final Tyre Stock"', active)

    def test_final_tyre_page_is_not_instantiated_in_workspace(self):
        source = (
            ROOT / "app" / "ui" / "stock_workspace_page.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn(
            "from app.ui.stock_master_page import StockMasterPage",
            source,
        )
        self.assertNotIn("StockMasterPage()", source)
        self.assertNotIn("TAB_FINAL", source)
        self.assertIn(
            "TAB_DAILY = 2",
            source,
        )
        self.assertIn(
            'StockWorkspacePage.TAB_DAILY: "Daily Stock"',
            source,
        )

    def test_legacy_final_tyre_shortcut_redirects_to_stock_master(self):
        path = ROOT / "app" / "ui" / "master_data_hub_page.py"
        if not path.exists():
            self.skipTest("Legacy Master Data Hub file not present.")

        source = path.read_text(encoding="utf-8")
        marker = 'if key == "Final Tyre Stock":'
        self.assertIn(marker, source)

        pos = source.index(marker)
        block = source[pos:pos + 160]
        self.assertIn('key = "Stock Master"', block)

    def test_canonical_stock_master_is_preserved(self):
        source = (ROOT / "app" / "ui" / "main_window.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("StockWorkspacePage", source)
        self.assertIn(
            '"Stock Master", self.STOCK_MASTER_INDEX',
            source,
        )


if __name__ == "__main__":
    unittest.main()
