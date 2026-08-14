from __future__ import annotations

import unittest
from datetime import date, timedelta

from app.services.ai_planning_service import AIPlanningService
from app.services.operational_source_service import OperationalSource


class AIPlanningV9Tests(unittest.TestCase):
    def _observations(self, ratios):
        start = date(2026, 1, 1)
        rows = []
        for index, ratio in enumerate(ratios):
            plan = 100
            actual = round(plan * ratio)
            rows.append(
                {
                    "production_date": start + timedelta(days=index),
                    "plan_total_qty": plan,
                    "actual_total_qty": actual,
                    "actual_day_qty": round(actual * 0.55),
                }
            )
        return rows

    def test_v9_model_exposes_champion_and_conservative_ratio(self):
        model = AIPlanningService._fit_item_model(
            self._observations([0.92, 0.95, 0.90, 0.96, 0.94, 0.93, 0.95, 0.94]),
            global_prior=0.90,
        )
        self.assertIn(model["champion_model"], {
            "GLOBAL_SHRINKAGE", "ROBUST_MEDIAN", "EWMA", "WEEKDAY_ENSEMBLE", "TREND_ENSEMBLE"
        })
        self.assertLessEqual(
            model["conservative_completion_ratio"],
            model["ewma_completion_ratio"],
        )
        self.assertGreaterEqual(model["validation_predictions"], 1)

    def test_v9_detects_recent_execution_drift(self):
        model = AIPlanningService._fit_item_model(
            self._observations([1.0] * 8 + [0.60] * 4),
            global_prior=0.95,
        )
        self.assertGreater(model["drift_score"], 0.5)
        self.assertIn(model["confidence_band"], {"DRIFT REVIEW", "LOW", "MEDIUM"})

    def test_operational_source_next_plan_date(self):
        source = OperationalSource(plan_date=date(2026, 8, 4), workbook_name="OVEN.xlsx")
        self.assertEqual(source.next_planning_date, date(2026, 8, 5))
        self.assertEqual(source.label, "Live OVEN: 2026-08-04")


if __name__ == "__main__":
    unittest.main()
