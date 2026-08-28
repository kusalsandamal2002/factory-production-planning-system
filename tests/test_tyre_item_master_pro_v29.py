
from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TyreItemMasterProV29Tests(unittest.TestCase):
    def setUp(self):
        self.ui_source = (
            ROOT / "app" / "ui" / "tyre_item_master_page.py"
        ).read_text(encoding="utf-8-sig")
        self.service_source = (
            ROOT / "app" / "services" / "tyre_master_intelligence_service.py"
        ).read_text(encoding="utf-8-sig")

    def test_python_syntax(self):
        ast.parse(self.ui_source)
        ast.parse(self.service_source)

    def test_pro_workspace_marker(self):
        self.assertIn(
            "# MPPS V29 TYRE ITEM MASTER PRO + AI/ML WORKSPACE",
            self.ui_source,
        )

    def test_factory_capacity_style_tabs_exist(self):
        for label in (
            "Tyre Items",
            "Tyre Size",
            "Process & Curing",
            "Line Mapping",
            "Mold & Casing",
            "Product Groups",
            "SMDS",
            "AI / ML",
        ):
            self.assertIn(label, self.ui_source)

    def test_existing_legacy_page_is_preserved(self):
        self.assertIn(
            "_LegacyTyreItemMasterPageV29 = TyreItemMasterPage",
            self.ui_source,
        )

    def test_ai_modules_exist(self):
        for key in (
            "MASTER_HEALTH",
            "DUPLICATE_IDENTITY",
            "CURING_TIME",
            "LINE_COMPATIBILITY",
            "MOLD_CASING",
            "GROUP_CLASSIFIER",
            "WEIGHT_ANOMALY",
        ):
            self.assertIn(key, self.service_source)

    def test_single_train_all_pipeline_exists(self):
        self.assertIn(
            "def request_train_all",
            self.service_source,
        )
        self.assertIn(
            "SINGLE_PIPELINE_ALL_MODULES",
            self.service_source,
        )

    def test_no_fake_training_policy(self):
        self.assertIn(
            "No fake models were created.",
            self.service_source,
        )
        self.assertIn(
            "Train All Models",
            self.ui_source,
        )


if __name__ == "__main__":
    unittest.main()
