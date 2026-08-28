
from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class TyreItemMasterV30Tests(unittest.TestCase):
    def setUp(self):
        self.ui = (
            ROOT / "app" / "ui" / "tyre_item_master_page.py"
        ).read_text(encoding="utf-8-sig")
        self.service = (
            ROOT / "app" / "services" / "tyre_master_intelligence_service.py"
        ).read_text(encoding="utf-8-sig")

    def test_complete_syntax(self):
        ast.parse(self.ui)
        ast.parse(self.service)

    def test_v30_marker(self):
        self.assertIn(
            "# MPPS V30 TYRE ITEM MASTER PRO NONBLOCKING WORKSPACE",
            self.ui,
        )

    def test_legacy_constructor_is_not_used_by_v30_constructor(self):
        marker = "# MPPS V30 TYRE ITEM MASTER PRO NONBLOCKING WORKSPACE"
        v30 = self.ui[self.ui.index(marker):]
        constructor_start = v30.index("    def __init__(self, *args, **kwargs):")
        constructor_end = v30.index("\n    def _build_ui", constructor_start)
        constructor = v30[constructor_start:constructor_end]

        self.assertNotIn(
            "_TyreItemMasterLegacyV30(",
            constructor,
        )

    def test_background_workers_exist(self):
        for name in (
            "_V30DataWorker",
            "_V30AIWorker",
            "_V30TrainAllWorker",
        ):
            self.assertIn(
                f"class {name}",
                self.ui,
            )

    def test_chunk_rendering_exists(self):
        self.assertIn(
            "def _render_table_chunked",
            self.ui,
        )
        self.assertIn(
            "start + 120",
            self.ui,
        )

    def test_professional_tabs_exist(self):
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
            self.assertIn(label, self.ui)

    def test_ai_modules_and_train_all_exist(self):
        for key in (
            "MASTER_HEALTH",
            "DUPLICATE_IDENTITY",
            "CURING_TIME",
            "LINE_COMPATIBILITY",
            "MOLD_CASING",
            "GROUP_CLASSIFIER",
            "WEIGHT_ANOMALY",
        ):
            self.assertIn(key, self.service)

        self.assertIn(
            "SINGLE_PIPELINE_ALL_MODULES",
            self.service,
        )
        self.assertIn(
            "def request_train_all",
            self.service,
        )


if __name__ == "__main__":
    unittest.main()
