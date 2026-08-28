
from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TyreItemMasterV291Tests(unittest.TestCase):
    def setUp(self):
        self.path = (
            ROOT / "app" / "ui" / "tyre_item_master_page.py"
        )
        self.source = self.path.read_text(
            encoding="utf-8-sig"
        )

    def test_complete_python_syntax(self):
        ast.parse(self.source)

    def test_v291_marker(self):
        self.assertIn(
            "# MPPS V29.1 TYRE ITEM MASTER TAB CONTENT FIX",
            self.source,
        )

    def test_each_pro_tab_routes_to_real_module_method(self):
        for method in (
            "_open_item_data",
            "_open_tyre_size",
            "_open_curing_time",
            "_open_tyre_group_key",
            "_open_mold_casing_rules",
            "_open_line_process_mapping",
            "_open_smds_master",
        ):
            self.assertIn(
                f'"{method}"',
                self.source,
            )

    def test_current_module_is_forced_visible(self):
        self.assertIn(
            "def _show_legacy_current_v291",
            self.source,
        )
        self.assertIn(
            "current.show()",
            self.source,
        )
        self.assertIn(
            "self._legacy.stack.show()",
            self.source,
        )

    def test_ai_ml_tab_is_preserved(self):
        self.assertIn(
            'if name == "AI / ML":',
            self.source,
        )
        self.assertIn(
            "self._refresh_ai()",
            self.source,
        )

    def test_existing_v29_intelligence_is_preserved(self):
        self.assertIn(
            "# MPPS V29 TYRE ITEM MASTER PRO + AI/ML WORKSPACE",
            self.source,
        )
        self.assertIn(
            "Train All Models",
            self.source,
        )


if __name__ == "__main__":
    unittest.main()
