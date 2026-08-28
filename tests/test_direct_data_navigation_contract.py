
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DirectDataNavigationContractTests(unittest.TestCase):
    def test_data_sidebar_is_direct(self):
        source = (ROOT / "app" / "ui" / "main_window.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn(
            '"Master Data", self.TYRE_PRODUCT_TREE_INDEX',
            source,
        )
        self.assertIn(
            '"Factory Capacity", self.FACTORY_CAPACITY_INDEX',
            source,
        )
        self.assertIn(
            '"Tyre Item Master", self.PRODUCT_MASTER_INDEX',
            source,
        )
        self.assertIn(
            '"Stock Master", self.STOCK_MASTER_INDEX',
            source,
        )

    def test_old_master_data_route_is_retired_and_redirected(self):
        source = (ROOT / "app" / "ui" / "main_window.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"Retired Master Data Hub"', source)
        nav_start = source.index("    def navigate(")
        nav_block = source[nav_start:nav_start + 1600]
        self.assertIn(
            "index == self.TYRE_PRODUCT_TREE_INDEX",
            nav_block,
        )
        self.assertIn(
            "index = self.FACTORY_CAPACITY_INDEX",
            nav_block,
        )

    def test_sidebar_selection_is_direct(self):
        source = (ROOT / "app" / "ui" / "main_window.py").read_text(
            encoding="utf-8"
        )
        start = source.index(
            "    def _sync_sidebar_selection(self, index):"
        )
        end = source.index("    def navigate(", start)
        block = source[start:end]
        self.assertNotIn("data_parent_index", block)
        self.assertNotIn("data_child_indexes", block)

    def test_visible_breadcrumbs_use_data_not_master_data(self):
        checks = (
            (
                "app/ui/stock_workspace_page.py",
                "Stock Master",
            ),
            (
                "app/ui/factory_capacity_page.py",
                "Factory Resource & Capacity",
            ),
            (
                "app/ui/tyre_item_master_page.py",
                "Tyre Item Master",
            ),
        )

        for rel, title in checks:
            source = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIsNone(
                re.search(
                    rf'Master Data\s*/\s*{re.escape(title)}',
                    source,
                ),
                msg=f"Legacy breadcrumb remains in {rel}",
            )
            self.assertIsNotNone(
                re.search(
                    rf'Data\s*/\s*{re.escape(title)}',
                    source,
                ),
                msg=f"Data breadcrumb missing in {rel}",
            )


if __name__ == "__main__":
    unittest.main()
