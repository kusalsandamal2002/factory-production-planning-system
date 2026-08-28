from __future__ import annotations

import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class AdminControlR4Contract(unittest.TestCase):
    def setUp(self):
        self.ui = (
            ROOT / "app/ui/admin_control_center_page.py"
        ).read_text(encoding="utf-8-sig")
        self.service = (
            ROOT / "app/services/admin_control_service.py"
        ).read_text(encoding="utf-8-sig")
        self.hub = (
            ROOT / "app/ui/module_hub_page.py"
        ).read_text(encoding="utf-8-sig")
        self.migration = (
            ROOT / "database/migrations/ensure_admin_control_r4.py"
        ).read_text(encoding="utf-8-sig")

    def test_python_syntax(self):
        for source in (
            self.ui,
            self.service,
            self.hub,
            self.migration,
        ):
            ast.parse(source)

    def test_final_admin_cards(self):
        for label in (
            "Users & Roles",
            "Factory Calendar",
            "Planning Rules",
            "Data Sources & Integrations",
            "Backup & Restore",
            "Audit Log",
            "System Health",
            "Advanced Database Tools",
        ):
            self.assertIn(label, self.ui)

    def test_removed_legacy_admin_cards(self):
        self.assertNotIn('"Data Quality Issues"', self.ui)
        self.assertNotIn('"Raw Excel Data Viewer"', self.ui)
        self.assertNotIn('"Factory Out Date Logic"', self.ui)

    def test_ui_has_no_direct_database_calls(self):
        self.assertNotIn("from app.database", self.ui)
        self.assertNotIn("engine.connect", self.ui)
        self.assertNotIn("engine.begin", self.ui)
        self.assertIn("TaskManager.instance()", self.ui)

    def test_no_runtime_schema_creation_in_admin_ui_or_service(self):
        self.assertNotIn("CREATE TABLE", self.ui.upper())
        self.assertNotIn("ALTER TABLE", self.ui.upper())
        self.assertNotIn("CREATE TABLE", self.service.upper())
        self.assertNotIn("ALTER TABLE", self.service.upper())
        self.assertIn("CREATE TABLE IF NOT EXISTS", self.migration.upper())

    def test_planning_rules_are_real_persisted_settings(self):
        self.assertIn("mpps_system_settings", self.service)
        self.assertIn("save_planning_rules", self.ui)
        self.assertIn("planning_horizon_days", self.service)
        self.assertIn("packing_dispatch_buffer_days", self.service)
        self.assertIn("auto_replan_enabled", self.service)

    def test_factory_calendar_is_migration_backed(self):
        self.assertIn("factory_holidays", self.service)
        self.assertIn("set_calendar_day", self.ui)
        self.assertIn("factory_holidays", self.migration)

    def test_admin_hub_routes_to_professional_page(self):
        self.assertIn(
            "from app.ui.admin_control_center_page import AdminControlCenterPage",
            self.hub,
        )


if __name__ == "__main__":
    unittest.main()
