import unittest
from datetime import date, timedelta

from app.services.ai_planning_service import AIPlanningService


class AIPlanningServiceTests(unittest.TestCase):
    def test_execution_model_learns_stable_completion_ratio(self):
        start = date(2026, 1, 1)
        rows = []
        for i in range(12):
            rows.append({
                "production_date": start + timedelta(days=i),
                "plan_total_qty": 100,
                "actual_total_qty": 95,
                "actual_day_qty": 55,
                "actual_night_qty": 40,
            })
        model = AIPlanningService._fit_item_model(rows)
        self.assertEqual(model["sample_days"], 12)
        self.assertAlmostEqual(model["ewma_completion_ratio"], 0.95, places=3)
        self.assertGreater(model["validation_accuracy_pct"], 99.0)
        self.assertGreater(model["day_share"], 0.55)

    def test_execution_model_is_leakage_safe(self):
        start = date(2026, 2, 1)
        rows = [
            {"production_date": start, "plan_total_qty": 100, "actual_total_qty": 50, "actual_day_qty": 30, "actual_night_qty": 20},
            {"production_date": start + timedelta(days=1), "plan_total_qty": 100, "actual_total_qty": 50, "actual_day_qty": 30, "actual_night_qty": 20},
            {"production_date": start + timedelta(days=2), "plan_total_qty": 100, "actual_total_qty": 100, "actual_day_qty": 60, "actual_night_qty": 40},
        ]
        model = AIPlanningService._fit_item_model(rows)
        # The final 100% observation must not be used to predict itself.
        self.assertLess(model["validation_accuracy_pct"], 100.0)
        self.assertEqual(model["sample_days"], 3)


if __name__ == "__main__":
    unittest.main()
