from __future__ import annotations

import unittest
from datetime import date

from app.services.monthly_stock_snapshot_service import MonthlyStockSnapshotService


class MonthlyStockSnapshotServiceTests(unittest.TestCase):
    def test_previous_month_crosses_year_boundary(self):
        self.assertEqual(
            MonthlyStockSnapshotService.previous_month_key(date(2026, 1, 5)),
            "2025-12",
        )

    def test_final_uses_prod_d_and_live_uses_hs(self):
        source = [
            {
                "sap_code": "600001",
                "description": "TEST TYRE",
                "opening_stock_qty": 64,
                "scrap_stock": 2,
                "blocked_stock": 3,
                "total_available": 91,
                "source_row": 4,
            }
        ]
        final_row = MonthlyStockSnapshotService._build_lines(source, source_kind="FINAL")[0]
        live_row = MonthlyStockSnapshotService._build_lines(source, source_kind="LIVE")[0]
        self.assertEqual(final_row["total_stock"], 64)
        self.assertEqual(live_row["total_stock"], 91)
        self.assertEqual(final_row["scrap_qty"], 2)
        self.assertEqual(live_row["blocked_qty"], 3)

    def test_same_payload_hash_is_deterministic(self):
        rows = [
            {
                "sap_code": "600001",
                "item_description": "TEST",
                "total_stock": 10,
                "scrap_qty": 1,
                "blocked_qty": 0,
                "source_row": 4,
            }
        ]
        self.assertEqual(
            MonthlyStockSnapshotService._data_hash(rows),
            MonthlyStockSnapshotService._data_hash(list(rows)),
        )

    def test_falling_history_produces_downward_risk_signal(self):
        result = MonthlyStockSnapshotService.predict_stock([100, 80, 60, 40], 20)
        self.assertIn("DOWN", result["trend"])
        self.assertIn(result["risk"], {"MEDIUM", "HIGH"})
        self.assertLess(result["forecast"], 20)


if __name__ == "__main__":
    unittest.main()
