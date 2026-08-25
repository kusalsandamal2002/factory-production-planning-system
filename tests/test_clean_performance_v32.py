
from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CleanPerformanceV32Tests(unittest.TestCase):
    def setUp(self):
        self.main = (
            ROOT / "app" / "ui" / "main_window.py"
        ).read_text(encoding="utf-8-sig")
        self.pro = (
            ROOT / "app" / "ui" / "tyre_item_master_pro_page.py"
        ).read_text(encoding="utf-8-sig")
        self.schema = (
            ROOT / "app" / "services" / "smds_schema.py"
        ).read_text(encoding="utf-8-sig")
        self.curing = (
            ROOT / "app" / "services" / "smds_curing_time.py"
        ).read_text(encoding="utf-8-sig")
        self.repo = (
            ROOT / "app" / "services" / "smds_tyre_repository.py"
        ).read_text(encoding="utf-8-sig")

    def test_syntax(self):
        for source in (
            self.main,
            self.pro,
            self.schema,
            self.curing,
            self.repo,
        ):
            ast.parse(source)

    def test_main_window_uses_clean_pro_module(self):
        self.assertIn(
            "from app.ui.tyre_item_master_pro_page import "
            "TyreItemMasterProPage as TyreItemMasterPage",
            self.main,
        )

    def test_pro_page_never_imports_legacy_tyre_page(self):
        self.assertNotIn(
            "app.ui.tyre_item_master_page",
            self.pro,
        )
        self.assertIn(
            "class TyreItemMasterProPage",
            self.pro,
        )

    def test_read_path_is_background_and_chunked(self):
        self.assertIn(
            "class _LoadWorker(QThread)",
            self.pro,
        )
        self.assertIn(
            "start + 40",
            self.pro,
        )

    def test_tab_cache_exists(self):
        self.assertIn(
            "self._cache",
            self.pro,
        )
        self.assertIn(
            "rows • cached",
            self.pro,
        )

    def test_schema_is_ensure_once(self):
        self.assertIn(
            "# MPPS V32 SCHEMA ENSURE ONCE",
            self.schema,
        )
        self.assertIn(
            "_v32_schema_ready",
            self.schema,
        )
        self.assertIn(
            "# MPPS V32 CURING SCHEMA ENSURE ONCE",
            self.curing,
        )

    def test_repository_read_has_no_ddl(self):
        marker = "# MPPS V32 FAST READ PATH"
        self.assertIn(marker, self.repo)
        fast = self.repo[self.repo.index(marker):]
        self.assertIn(
            "TyreItemRepository.list_items = _v32_fast_list_items",
            fast,
        )
        self.assertNotIn(
            "ALTER TABLE",
            fast,
        )

    def test_main_cache_policy(self):
        self.assertIn(
            "# MPPS V32 APP CACHE + ASYNC SOURCE",
            self.main,
        )
        self.assertIn(
            "Loaded + clean = instant cached reuse",
            self.main,
        )
        self.assertIn(
            "class _V32SourceWorker",
            self.main,
        )


if __name__ == "__main__":
    unittest.main()
