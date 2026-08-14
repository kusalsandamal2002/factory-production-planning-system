from __future__ import annotations

from datetime import date
from pathlib import Path
import unittest

from app.services.factory_out_forecast_service import forecast_item


class ShipmentItemMLForecastV1042Tests(unittest.TestCase):
    def test_missing_receive_date_gets_ml_forecast(self):
        item = forecast_item(
            {
                "id": 77,
                "shipment_id": 12,
                "sap_code": "60000770",
                "quantity": 32,
                "stock_allocated_qty": 0,
                "produced_qty": 0,
                "daily_capacity": 0,
                "allocated_cavity_count": 0,
            },
            as_of_date=date(2026, 8, 10),
            learned_capacity={
                "sample_days": 20,
                "safe_capacity_qty": 8,
                "expected_capacity_qty": 10,
                "confidence_score": 0.82,
            },
        )
        self.assertEqual(item.item_id, 77)
        self.assertEqual(item.ready_date, date(2026, 8, 14))
        self.assertEqual(item.source, "LEARNED SAP SAFE CAPACITY")
        self.assertAlmostEqual(item.effective_daily_capacity, 8.0)

    def test_item_detail_ui_uses_forecast_instead_of_plain_pending(self):
        source = Path("app/ui/shipment_orders_page.py").read_text(encoding="utf-8")
        service = Path("app/services/shipment_command_service.py").read_text(encoding="utf-8")
        self.assertIn("item_forecast_sink=detail_item_forecasts", source)
        self.assertIn("item_execution_timeline(", source)
        self.assertIn('"Receive / Finish"', source)
        self.assertIn('state = "ML FORECAST"', service)



if __name__ == "__main__":
    unittest.main()
