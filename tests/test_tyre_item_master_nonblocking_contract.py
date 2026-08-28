
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TyreItemMasterNonBlockingContractTests(unittest.TestCase):
    def test_heavy_child_pages_are_not_eagerly_constructed(self):
        source = (ROOT / "app" / "ui" / "tyre_item_master_page.py").read_text(
            encoding="utf-8"
        )

        class_start = source.index("class TyreItemMasterPage(QWidget):")
        init_start = source.index("    def __init__(self):", class_start)
        end = source.index("    def _build_overview_page", init_start)
        init_block = source[init_start:end]

        self.assertNotIn(
            "SMDSMasterPage(on_back=self._back_to_overview)",
            init_block,
        )
        self.assertNotIn(
            "SmdsMoldCasingPage(on_back=self._back_to_overview)",
            init_block,
        )
        self.assertIn("lazy_smds_master", init_block)
        self.assertIn("lazy_smds_mold_casing", init_block)

    def test_v19_lazy_openers_are_final_aliases(self):
        source = (ROOT / "app" / "ui" / "tyre_item_master_page.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "# MPPS V19 LAZY TYRE ITEM MASTER CHILD WORKSPACES",
            source,
        )
        self.assertIn(
            "TyreItemMasterPage._open_smds_master = _mpps_v19_open_smds_master",
            source,
        )
        self.assertIn(
            "TyreItemMasterPage._open_mold_casing_rules = _mpps_v19_open_mold_casing_rules",
            source,
        )

    def test_main_window_does_not_lock_cursor_for_tyre_item_master(self):
        source = (ROOT / "app" / "ui" / "main_window.py").read_text(
            encoding="utf-8"
        )
        start = source.index("use_wait_cursor =")
        block = source[start:start + 400]
        self.assertIn("self.SHIPMENT_DETAILS_INDEX", block)
        self.assertIn("self.PRODUCT_MASTER_INDEX", block)


if __name__ == "__main__":
    unittest.main()
