from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from app.services.shipment_command_service import shipment_execution_state


class ShipmentDetailV106LogicTests(unittest.TestCase):
    def test_all_remaining_items_with_forecasts_are_not_blocked(self):
        state = shipment_execution_state([
            {
                "quantity": 4,
                "ready_qty": 0,
                "remaining_qty": 4,
                "forecast_receive_date": date(2026, 8, 5),
            },
            {
                "quantity": 4,
                "ready_qty": 3,
                "remaining_qty": 1,
                "forecast_receive_date": date(2026, 8, 12),
            },
        ])
        self.assertEqual(state.label, "FORECAST")
        self.assertEqual(state.blocked_items, 0)
        self.assertEqual(state.ready_qty, 3)
        self.assertEqual(state.remaining_qty, 5)

    def test_real_unresolved_item_creates_partial_block(self):
        state = shipment_execution_state([
            {
                "quantity": 10,
                "ready_qty": 0,
                "remaining_qty": 10,
                "forecast_receive_date": date(2026, 8, 15),
            },
            {
                "quantity": 5,
                "ready_qty": 0,
                "remaining_qty": 5,
                "blocker": "No usable technical capacity evidence",
            },
        ])
        self.assertEqual(state.label, "PARTIALLY BLOCKED")
        self.assertEqual(state.forecast_items, 1)
        self.assertEqual(state.blocked_items, 1)

    def test_fully_covered_shipment_is_ready(self):
        state = shipment_execution_state([
            {"quantity": 8, "ready_qty": 8, "remaining_qty": 0},
            {"quantity": 12, "ready_qty": 12, "remaining_qty": 0},
        ])
        self.assertEqual(state.label, "READY")
        self.assertEqual(state.ready_qty, 20)
        self.assertEqual(state.remaining_qty, 0)

    def test_verified_future_dates_are_scheduled_not_pending(self):
        state = shipment_execution_state([
            {
                "quantity": 7,
                "ready_qty": 2,
                "remaining_qty": 5,
                "verified_receive_date": date(2026, 8, 20),
            }
        ])
        self.assertEqual(state.label, "SCHEDULED")


class ShipmentDetailV106UIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("app/ui/shipment_orders_page.py").read_text(encoding="utf-8")

    def test_detail_kpis_use_ready_covered_language(self):
        self.assertIn('"Ready / Covered Qty"', self.source)
        self.assertIn('"Coverage Progress"', self.source)

    def test_detail_table_is_compact_and_execution_focused(self):
        self.assertIn("self.detail_table = QTableWidget(0, 9)", self.source)
        self.assertIn('"Stock Allocated"', self.source)
        self.assertIn('"Shortage"', self.source)
        self.assertIn('"Production Start"', self.source)
        self.assertIn('"Receive / Finish"', self.source)
        self.assertIn('"State"', self.source)
        self.assertIn("table.verticalHeader().setDefaultSectionSize(\n            34", self.source)

    def test_detail_actions_are_compacted_into_menu(self):
        self.assertIn('QPushButton("Actions ▾")', self.source)
        self.assertIn('addAction("Edit Shipment Header")', self.source)
        self.assertIn('addAction("Change Target Date")', self.source)
        self.assertIn('addAction("Add Item")', self.source)

    def test_live_execution_state_overrides_stale_persisted_status(self):
        self.assertIn("planning_status = execution_state.label", self.source)
        self.assertIn("execution_state = shipment_execution_state(execution_items)", self.source)


if __name__ == "__main__":
    unittest.main()
