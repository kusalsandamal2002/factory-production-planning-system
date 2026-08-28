from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ShipmentOrdersR3ZeroFreeze(unittest.TestCase):
    def setUp(self):
        self.page = (ROOT / "app/ui/order_entry_async_page.py").read_text(encoding="utf-8-sig")
        self.service = (ROOT / "app/services/shipment_order_async_service.py").read_text(encoding="utf-8-sig")
        self.main = (ROOT / "app/ui/main_window.py").read_text(encoding="utf-8-sig")
        self.watchdog = (ROOT / "app/core/ui_watchdog.py").read_text(encoding="utf-8-sig")

    def test_python_syntax(self):
        for source in (self.page, self.service, self.main, self.watchdog):
            ast.parse(source)

    def test_no_legacy_order_entry_inheritance(self):
        self.assertIn("class ShipmentOrderAsyncPage(QWidget):", self.page)
        self.assertNotIn("from app.ui.order_entry_page import", self.page)
        self.assertNotIn("class ShipmentOrderAsyncPage(OrderEntryPage)", self.page)

    def test_no_full_master_preload_or_completer(self):
        self.assertNotIn("QCompleter", self.page)
        self.assertNotIn("load_master_items", self.page)
        self.assertIn("search_master_items", self.page)
        self.assertIn("LIMIT :limit", self.service)
        self.assertIn("len(query) < 2", self.service)

    def test_no_qtablewidget_or_ui_database_calls(self):
        self.assertNotIn("QTableWidget", self.page)
        self.assertNotIn("QTableWidgetItem", self.page)
        self.assertNotIn("engine.connect", self.page)
        self.assertNotIn("engine.begin", self.page)
        self.assertIn("QTableView", self.page)
        self.assertIn("QAbstractTableModel", self.page)

    def test_all_heavy_actions_use_task_manager(self):
        for key in (
            'self.TASK_PREFIX + "search"',
            'self.TASK_PREFIX + "stock"',
            'self.TASK_PREFIX + "cart-plan"',
            'self.TASK_PREFIX + "save"',
            '"planning:shipment-entry-replan"',
            'self.TASK_PREFIX + "history"',
        ):
            self.assertIn(key, self.page)

    def test_save_transaction_and_replan_are_separate(self):
        save_start = self.service.index("def save_shipment")
        replan_start = self.service.index("def replan_open_shipments")
        save_source = self.service[save_start:replan_start]
        self.assertNotIn("replan_all_open_shipments", save_source)
        self.assertIn("replan_all_open_shipments", self.service[replan_start:])

    def test_ui_watchdog_installed(self):
        self.assertIn("UIWatchdog", self.main)
        self.assertIn("self.ui_watchdog.start()", self.main)
        self.assertIn("[MPPS UI STALL]", self.watchdog)

    def test_search_and_plan_are_debounced(self):
        self.assertIn("self._search_timer.setInterval(280)", self.page)
        self.assertIn("self._plan_timer.setInterval(180)", self.page)


    def test_previous_shipment_limit_is_not_forced_to_five(self):
        self.assertIn(
            'max(1, min(50, int(limit)))',
            self.service,
        )
        self.assertNotIn(
            'max(5, min(50, int(limit)))',
            self.service,
        )


if __name__ == "__main__":
    unittest.main()
