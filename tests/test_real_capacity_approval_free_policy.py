import unittest
from datetime import date
from pathlib import Path

from app.services.factory_out_forecast_service import forecast_item


class RealCapacityApprovalFreePolicyTests(unittest.TestCase):
    def test_learned_safe_capacity_wins_over_legacy_planner_capacity(self):
        result = forecast_item(
            {
                "shipment_id": 1,
                "sap_code": "60003417",
                "quantity": 100,
                "stock_allocated_qty": 0,
                "produced_qty": 0,
                "daily_capacity": 100,
                "factory_out_reason": "Planning manager approval is not Approved.",
            },
            as_of_date=date(2026, 8, 10),
            learned_capacity={
                "sample_days": 30,
                "safe_capacity_qty": 25,
                "expected_capacity_qty": 30,
                "confidence_score": 0.91,
            },
        )
        self.assertEqual(result.ready_date, date(2026, 8, 14))
        self.assertEqual(result.source, "LEARNED SAP SAFE CAPACITY")
        self.assertGreaterEqual(result.confidence, 0.9)

    def test_legacy_approval_reason_is_not_a_factory_out_blocker(self):
        result = forecast_item(
            {
                "shipment_id": 2,
                "sap_code": "60003417",
                "quantity": 10,
                "stock_allocated_qty": 0,
                "produced_qty": 0,
                "daily_capacity": 0,
                "factory_out_reason": "Planning manager approval is not Approved.",
            },
            as_of_date=date(2026, 8, 10),
        )
        self.assertIsNone(result.ready_date)
        self.assertNotIn("approval", result.blocker.lower())
        self.assertIn("capacity", result.blocker.lower())

    def test_operational_source_files_contain_no_approval_hard_block_message(self):
        root = Path(__file__).resolve().parents[1]
        files = [
            "app/services/factory_out_date_logic.py",
            "app/services/factory_planning_engine.py",
            "app/services/cavity_daily_plan_service.py",
            "app/services/excel_oven_plan_service.py",
            "app/ui/shipment_orders_page.py",
            "app/ui/existing_shipment_add_items_dialog.py",
            "app/ui/item_resource_control_center_page.py",
        ]
        banned = [
            "Planning Manager Approval is not Approved",
            "Planning manager approval is not Approved",
            "MASTER APPROVAL REQUIRED",
        ]
        for relative in files:
            text = (root / relative).read_text(encoding="utf-8")
            for token in banned:
                self.assertNotIn(token, text, f"{token!r} still gates {relative}")


if __name__ == "__main__":
    unittest.main()
