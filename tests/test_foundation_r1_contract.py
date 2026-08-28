from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FoundationR1Contract(unittest.TestCase):
    def read(self, rel: str) -> str:
        return (ROOT / rel).read_text(encoding="utf-8-sig")

    def test_modified_python_syntax(self):
        for rel in (
            "app/ui/main_window.py",
            "app/core/task_manager.py",
            "app/core/events.py",
            "app/core/source_versions.py",
            "app/services/shipment_order_async_service.py",
            "app/ui/order_entry_async_page.py",
            "app/services/shipment_lifecycle_service.py",
            "app/ui/shipment_details_pro_page.py",
            "database/migrations/ensure_foundation_zero_freeze_r1.py",
        ):
            ast.parse(self.read(rel), filename=rel)

    def test_main_window_is_clean_not_monkey_patch_stack(self):
        source = self.read("app/ui/main_window.py")
        self.assertNotIn("MPPS V36", source)
        self.assertNotIn("MainWindow.navigate =", source)
        self.assertNotIn("_v35_", source)
        self.assertIn("ShipmentOrderAsyncPage", source)
        self.assertIn("ShipmentDetailsProPage", source)
        self.assertIn('self._nav(layout, "AI / ML"', source)
        self.assertNotIn('self._nav(layout, "Reports"', source)
        self.assertNotIn('self._nav(layout, "Factory Intelligence"', source)
        self.assertNotIn('self._nav(layout, "Intelligent Excel Import"', source)

    def test_shipment_order_constructor_does_not_run_schema(self):
        source = self.read("app/ui/order_entry_async_page.py")
        self.assertIn("def ensure_tables(self) -> None", source)
        self.assertIn("return\n\n    # ------------------------------------------------------------------ master data", source)
        self.assertIn("TaskManager.instance()", source)
        self.assertIn("load_master_items", source)
        self.assertIn("calculate_cart_plan", source)

    def test_planner_no_per_action_schema_preflight(self):
        source = self.read("app/services/factory_planning_engine.py")
        calc = source[source.index("    def calculate_cart_items"):]
        calc = calc[: calc.find("\n    def ", 10) if calc.find("\n    def ", 10) > 0 else len(calc)]
        self.assertNotIn("self.ensure_schema()", calc)

    def test_shipment_lifecycle(self):
        migration = self.read("database/migrations/ensure_foundation_zero_freeze_r1.py")
        service = self.read("app/services/shipment_lifecycle_service.py")
        page = self.read("app/ui/shipment_details_pro_page.py")
        for value in ("SHIPPED", "CANCELLED", "CLOSURE_REVIEW", "HOLD"):
            self.assertIn(value, migration + service + page)
        self.assertIn("Mark Shipped", page)
        self.assertIn("Cancel Shipment", page)
        self.assertIn("NEEDS CLOSURE REVIEW", page)

    def test_missing_workbook_sets_closure_review(self):
        source = self.read("app/services/workbook_continuous_sync_service.py")
        self.assertIn('"lifecycle_status": "CLOSURE_REVIEW"', source)

    def test_tyre_user_tabs_are_collapsed(self):
        source = self.read("app/ui/tyre_item_master_pro_page.py")
        self.assertIn('TABS=(("Tyre Master","MATRIX"),)', source)
        self.assertNotIn("QTimer.singleShot(500,self.load_dashboard)", source)


if __name__ == "__main__":
    unittest.main()
