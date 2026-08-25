from __future__ import annotations

import ast
from datetime import date
from pathlib import Path
import unittest

from app.services.shipment_lifecycle_service import annotate_portfolio_rows


ROOT = Path(__file__).resolve().parents[1]


class ShipmentDetailsR2Contract(unittest.TestCase):
    def setUp(self):
        self.ui = (ROOT / "app/ui/shipment_details_pro_page.py").read_text(
            encoding="utf-8-sig"
        )
        self.service = (
            ROOT / "app/services/shipment_lifecycle_service.py"
        ).read_text(encoding="utf-8-sig")

    def test_python_syntax(self):
        ast.parse(self.ui)
        ast.parse(self.service)

    def test_portfolio_columns_are_clean(self):
        self.assertIn('("Priority No.", "priority_no", _priority_text)', self.ui)
        self.assertIn('("Shipment", "shipment_name", None)', self.ui)
        self.assertIn('("Status", "operational_status", _status_text)', self.ui)
        portfolio_block = self.ui.split("PORTFOLIO_COLUMNS = [", 1)[1].split("]", 1)[0]
        self.assertNotIn('"Lifecycle"', portfolio_block)
        self.assertNotIn('"Customer"', portfolio_block)
        self.assertNotIn('"Risk"', portfolio_block)

    def test_all_shipments_lifecycle_filters_exist(self):
        for text in (
            "All Shipments",
            "Needs Attention",
            "Closure Review",
            "Not Planned",
            "Planned",
            "In Production",
            "Ready",
            "Hold",
            "Shipped",
            "Cancelled",
        ):
            self.assertIn(text, self.ui)

    def test_priority_is_only_for_active_workflow(self):
        rows = annotate_portfolio_rows(
            [
                {
                    "shipment_pk": 1,
                    "shipment_name": "Urgent",
                    "lifecycle_status": "ACTIVE",
                    "planning_status": "Pending Planning",
                    "total_quantity": 100,
                    "production_gap": 100,
                    "stock_progress_pct": 0,
                    "target_date": date(2026, 8, 21),
                    "target_date_is_manual": True,
                    "risk_score": 90,
                    "risk_band": "critical",
                    "factory_can_receive_date": None,
                },
                {
                    "shipment_pk": 2,
                    "shipment_name": "Ready",
                    "lifecycle_status": "ACTIVE",
                    "planning_status": "Planned",
                    "total_quantity": 100,
                    "production_gap": 0,
                    "stock_progress_pct": 100,
                    "target_date": date(2026, 8, 25),
                    "target_date_is_manual": True,
                    "risk_score": 10,
                    "risk_band": "healthy",
                    "factory_can_receive_date": date(2026, 8, 24),
                },
                {
                    "shipment_pk": 3,
                    "shipment_name": "Hold",
                    "lifecycle_status": "HOLD",
                    "planning_status": "On Hold",
                    "total_quantity": 100,
                    "production_gap": 50,
                    "stock_progress_pct": 50,
                    "target_date": date(2026, 8, 22),
                    "risk_score": 50,
                    "risk_band": "at_risk",
                    "factory_can_receive_date": None,
                },
                {
                    "shipment_pk": 4,
                    "shipment_name": "Shipped",
                    "lifecycle_status": "SHIPPED",
                    "planning_status": "Closed",
                    "total_quantity": 100,
                    "production_gap": 0,
                    "stock_progress_pct": 100,
                    "target_date": date(2026, 8, 10),
                    "risk_score": 0,
                    "risk_band": "healthy",
                    "factory_can_receive_date": date(2026, 8, 9),
                },
                {
                    "shipment_pk": 5,
                    "shipment_name": "Review",
                    "lifecycle_status": "CLOSURE_REVIEW",
                    "source_missing_from_latest": True,
                    "total_quantity": 100,
                    "production_gap": 0,
                    "stock_progress_pct": 100,
                    "target_date": date(2026, 8, 20),
                    "risk_score": 0,
                    "risk_band": "review",
                    "factory_can_receive_date": None,
                },
            ]
        )
        by_name = {row["shipment_name"]: row for row in rows}
        self.assertEqual(by_name["Urgent"]["operational_status"], "NOT_PLANNED")
        self.assertEqual(by_name["Urgent"]["priority_no"], 1)
        self.assertEqual(by_name["Ready"]["operational_status"], "READY_FOR_DISPATCH")
        self.assertEqual(by_name["Ready"]["priority_no"], 2)
        self.assertIsNone(by_name["Hold"]["priority_no"])
        self.assertIsNone(by_name["Shipped"]["priority_no"])
        self.assertIsNone(by_name["Review"]["priority_no"])
        self.assertEqual(rows[0]["operational_status"], "CLOSURE_REVIEW")

    def test_no_ui_thread_db_load_was_added(self):
        self.assertIn("self.task_manager.submit", self.ui)
        self.assertNotIn("engine.connect", self.ui)
        self.assertNotIn("engine.begin", self.ui)


if __name__ == "__main__":
    unittest.main()
