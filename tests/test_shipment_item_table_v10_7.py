from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.services.shipment_command_service import item_execution_timeline


class ShipmentItemTimelineV107Tests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 8, 11)

    def test_fully_stock_allocated_has_no_production_start_and_today_receive(self):
        timeline = item_execution_timeline(
            {
                "quantity": 8,
                "stock_allocated_qty": 8,
                "produced_qty": 0,
                "production_start_date": date(2026, 8, 4),
                "item_receive_date": date(2026, 8, 4),
            },
            today=self.today,
        )
        self.assertEqual(timeline.stock_allocated, 8)
        self.assertEqual(timeline.shortage_qty, 0)
        self.assertEqual(timeline.completion_pct, 100.0)
        self.assertIsNone(timeline.production_start_date)
        self.assertEqual(timeline.receive_date, self.today)
        self.assertEqual(timeline.state, "STOCK ALLOCATED")

    def test_partial_stock_uses_shortage_and_ml_forecast(self):
        forecast = SimpleNamespace(
            ready_date=date(2026, 8, 13),
            source="LEARNED SAP SAFE CAPACITY",
            effective_daily_capacity=5.0,
            confidence=0.82,
            blocker="",
        )
        timeline = item_execution_timeline(
            {
                "quantity": 10,
                "stock_allocated_qty": 4,
                "produced_qty": 1,
            },
            today=self.today,
            forecast=forecast,
        )
        self.assertEqual(timeline.shortage_qty, 5)
        self.assertAlmostEqual(timeline.completion_pct, 50.0)
        self.assertEqual(timeline.production_start_date, self.today)
        self.assertEqual(timeline.receive_date, date(2026, 8, 13))
        self.assertEqual(timeline.state, "ML FORECAST")

    def test_stale_forecast_is_reanchored_to_today_for_live_display(self):
        forecast = SimpleNamespace(
            ready_date=date(2026, 8, 5),
            source="LEARNED FACTORY PER-SAP BASELINE",
            effective_daily_capacity=2.0,
            confidence=0.35,
            blocker="",
        )
        timeline = item_execution_timeline(
            {
                "quantity": 4,
                "stock_allocated_qty": 0,
                "produced_qty": 0,
            },
            today=self.today,
            forecast=forecast,
        )
        self.assertEqual(timeline.production_start_date, self.today)
        self.assertEqual(timeline.receive_date, date(2026, 8, 13))

    def test_verified_schedule_remains_authoritative(self):
        timeline = item_execution_timeline(
            {
                "quantity": 10,
                "stock_allocated_qty": 3,
                "produced_qty": 0,
                "production_start_date": date(2026, 8, 12),
                "item_receive_date": date(2026, 8, 15),
            },
            today=self.today,
        )
        self.assertEqual(timeline.shortage_qty, 7)
        self.assertEqual(timeline.production_start_date, date(2026, 8, 12))
        self.assertEqual(timeline.receive_date, date(2026, 8, 15))
        self.assertEqual(timeline.state, "SCHEDULED")


class ShipmentItemTableV107UIContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = Path("app/ui/shipment_orders_page.py").read_text(encoding="utf-8")

    def test_requested_nine_columns_are_visible(self):
        self.assertIn("self.detail_table = QTableWidget(0, 9)", self.source)
        for label in (
            '"SAP Code"',
            '"Item Description"',
            '"Qty"',
            '"Stock Allocated"',
            '"Shortage"',
            '"Complete %"',
            '"Production Start"',
            '"Receive / Finish"',
            '"State"',
        ):
            self.assertIn(label, self.source)

    def test_stock_ready_rule_is_visible_in_ui_contract(self):
        self.assertIn('timeline.state == "STOCK ALLOCATED"', self.source)
        self.assertIn('production_start_text', self.source)
        self.assertIn('ready/receive date is today', self.source)


if __name__ == "__main__":
    unittest.main()
