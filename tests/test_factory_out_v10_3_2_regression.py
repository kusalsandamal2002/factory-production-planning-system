import unittest
from datetime import date, timedelta

from app.services.factory_out_forecast_service import (
    ItemFactoryOutForecast,
    aggregate_shipment_forecast,
)
from app.services.shipment_command_service import day_count


class FactoryOutV1032RegressionTests(unittest.TestCase):
    def test_day_count_accepts_python_timedelta(self):
        self.assertEqual(day_count(timedelta(days=5)), 5)
        self.assertEqual(day_count(timedelta(days=-3)), -3)

    def test_dispatch_buffer_accepts_interval_timedelta(self):
        item = ItemFactoryOutForecast(
            shipment_id=10,
            sap_code="60000139",
            ready_date=date(2026, 8, 12),
            source="LEARNED SAP SAFE CAPACITY",
            confidence=0.9,
        )
        result = aggregate_shipment_forecast(
            10,
            [item],
            dispatch_buffer_days=timedelta(days=1),
        )
        self.assertEqual(result.factory_out_date, date(2026, 8, 13))
        self.assertEqual(result.source, "ML CAPACITY FORECAST")

    def test_python_date_variance_is_normalized_to_integer_days(self):
        variance = date(2026, 8, 15) - date(2026, 8, 12)
        self.assertEqual(day_count(variance), 3)


if __name__ == "__main__":
    unittest.main()
