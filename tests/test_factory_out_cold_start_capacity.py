import unittest
from datetime import date

from app.services.factory_out_forecast_service import forecast_item


class FactoryOutColdStartCapacityTests(unittest.TestCase):
    def setUp(self):
        self.as_of = date(2026, 8, 10)

    def test_sparse_sap_actual_history_produces_low_confidence_forecast(self):
        result = forecast_item(
            {
                "shipment_id": 10,
                "sap_code": "60003444",
                "quantity": 80,
                "stock_allocated_qty": 39,
                "produced_qty": 0,
                "daily_capacity": 0,
                "allocated_cavity_count": 0,
                "smds_total_plan": 0,
            },
            as_of_date=self.as_of,
            learned_capacity={
                "sample_days": 2,
                "safe_capacity_qty": 18,
                "expected_capacity_qty": 20,
                "recent_capacity_qty": 16,
                "confidence_score": 0.31,
            },
        )
        self.assertIsNotNone(result.ready_date)
        self.assertEqual(result.source, "LEARNED SAP SPARSE CAPACITY")
        self.assertGreater(result.effective_daily_capacity, 0)
        self.assertLessEqual(result.confidence, 0.45)

    def test_factory_actual_baseline_prevents_sparse_sap_hard_block(self):
        result = forecast_item(
            {
                "shipment_id": 11,
                "sap_code": "60003444",
                "quantity": 80,
                "stock_allocated_qty": 39,
                "produced_qty": 0,
                "daily_capacity": 0,
                "allocated_cavity_count": 0,
                "smds_total_plan": 0,
            },
            as_of_date=self.as_of,
            fallback_capacity={
                "sample_days": 12,
                "safe_capacity_qty": 14,
                "expected_capacity_qty": 18,
                "confidence_score": 0.34,
                "model_level": "FACTORY_PER_ACTIVE_SAP",
            },
        )
        self.assertIsNotNone(result.ready_date)
        self.assertNotEqual(result.source, "BLOCKED")
        self.assertEqual(result.source, "LEARNED FACTORY PER-SAP BASELINE")
        self.assertEqual(result.ready_date, date(2026, 8, 13))
        self.assertLessEqual(result.confidence, 0.45)

    def test_true_zero_evidence_can_still_block_instead_of_inventing_capacity(self):
        result = forecast_item(
            {
                "shipment_id": 12,
                "sap_code": "UNRESOLVED-SAP",
                "quantity": 20,
                "stock_allocated_qty": 0,
                "produced_qty": 0,
                "daily_capacity": 0,
                "allocated_cavity_count": 0,
                "smds_total_plan": 0,
            },
            as_of_date=self.as_of,
        )
        self.assertIsNone(result.ready_date)
        self.assertEqual(result.source, "BLOCKED")


if __name__ == "__main__":
    unittest.main()
