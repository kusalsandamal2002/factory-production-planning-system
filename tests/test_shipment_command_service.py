from datetime import date
import unittest

from app.services.shipment_command_service import portfolio_metrics, shipment_risk_profile


class ShipmentCommandServiceTests(unittest.TestCase):
    def test_overdue_stock_gap_is_critical(self):
        row = {
            "total_quantity": 100,
            "stock_allocated": 20,
            "target_date": date(2026, 8, 5),
            "factory_can_receive_date": date(2026, 8, 12),
            "promise_state": "cannot_meet",
            "review_required": False,
        }
        profile = shipment_risk_profile(row, as_of_date=date(2026, 8, 10))
        self.assertEqual(profile.band, "critical")
        self.assertEqual(profile.production_gap, 80)
        self.assertLess(profile.delivery_variance_days, 0)
        self.assertTrue(profile.risk_drivers)
        self.assertTrue(any("Production gap" in driver for driver in profile.risk_drivers))

    def test_fully_covered_future_shipment_is_low_risk(self):
        row = {
            "total_quantity": 200,
            "stock_allocated": 200,
            "target_date": date(2026, 9, 10),
            "factory_can_receive_date": date(2026, 9, 8),
            "promise_state": "can_meet",
            "review_required": False,
        }
        profile = shipment_risk_profile(row, as_of_date=date(2026, 8, 10))
        self.assertEqual(profile.band, "healthy")
        self.assertEqual(profile.production_gap, 0)
        self.assertEqual(profile.stock_coverage_pct, 100.0)

    def test_review_is_never_silently_healthy(self):
        row = {
            "total_quantity": 10,
            "stock_allocated": 10,
            "target_date": date(2026, 8, 20),
            "factory_can_receive_date": None,
            "promise_state": "review_required",
            "review_required": True,
        }
        profile = shipment_risk_profile(row, as_of_date=date(2026, 8, 10))
        self.assertEqual(profile.band, "review")
        self.assertIn("REVIEW", profile.label)

    def test_portfolio_metrics(self):
        rows = [
            {
                "total_quantity": 100,
                "stock_allocated": 70,
                "production_gap": 30,
                "risk_band": "critical",
            },
            {
                "total_quantity": 50,
                "stock_allocated": 50,
                "production_gap": 0,
                "risk_band": "healthy",
            },
        ]
        metrics = portfolio_metrics(rows)
        self.assertEqual(metrics["total_shipments"], 2)
        self.assertEqual(metrics["total_qty"], 150)
        self.assertEqual(metrics["production_gap"], 30)
        self.assertEqual(metrics["critical"], 1)
        self.assertAlmostEqual(metrics["stock_coverage_pct"], 80.0)


if __name__ == "__main__":
    unittest.main()
