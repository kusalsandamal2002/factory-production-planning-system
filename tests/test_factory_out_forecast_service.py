import unittest
from datetime import date

from app.services.factory_out_forecast_service import (
    aggregate_shipment_forecast,
    forecast_item,
)


class FactoryOutForecastServiceTests(unittest.TestCase):
    def setUp(self):
        self.as_of = date(2026, 8, 10)

    def test_stock_covered_item_is_ready_on_operational_date(self):
        result = forecast_item(
            {
                "shipment_id": 1,
                "sap_code": "60000139",
                "quantity": 20,
                "stock_allocated_qty": 20,
                "produced_qty": 0,
            },
            as_of_date=self.as_of,
        )
        self.assertEqual(result.ready_date, self.as_of)
        self.assertEqual(result.source, "STOCK / PRODUCED READY")

    def test_planner_capacity_forecasts_missing_item_date(self):
        result = forecast_item(
            {
                "shipment_id": 1,
                "sap_code": "60000139",
                "quantity": 100,
                "stock_allocated_qty": 20,
                "produced_qty": 0,
                "daily_capacity": 40,
            },
            as_of_date=self.as_of,
        )
        self.assertEqual(result.ready_date, date(2026, 8, 12))
        self.assertEqual(result.source, "PLANNER DAILY CAPACITY")

    def test_learned_safe_capacity_is_used_when_planner_capacity_missing(self):
        result = forecast_item(
            {
                "shipment_id": 1,
                "sap_code": "60000139",
                "quantity": 70,
                "stock_allocated_qty": 10,
                "produced_qty": 0,
                "daily_capacity": 0,
            },
            as_of_date=self.as_of,
            learned_capacity={
                "sample_days": 20,
                "safe_capacity_qty": 30,
                "expected_capacity_qty": 36,
                "confidence_score": 0.82,
            },
        )
        self.assertEqual(result.ready_date, date(2026, 8, 12))
        self.assertEqual(result.source, "LEARNED SAP SAFE CAPACITY")

    def test_unresolved_capacity_is_explicit_blocker_not_fake_date(self):
        result = forecast_item(
            {
                "shipment_id": 1,
                "sap_code": "BAD-SAP",
                "quantity": 10,
                "stock_allocated_qty": 0,
                "produced_qty": 0,
                "daily_capacity": 0,
                "schedule_reason": "SMDS process standard is missing.",
            },
            as_of_date=self.as_of,
        )
        self.assertIsNone(result.ready_date)
        self.assertEqual(result.source, "BLOCKED")
        self.assertIn("SMDS", result.blocker)

    def test_shipment_out_is_slowest_item_plus_dispatch_buffer(self):
        first = forecast_item(
            {
                "shipment_id": 9,
                "sap_code": "A",
                "quantity": 20,
                "stock_allocated_qty": 20,
            },
            as_of_date=self.as_of,
        )
        second = forecast_item(
            {
                "shipment_id": 9,
                "sap_code": "B",
                "quantity": 60,
                "daily_capacity": 30,
            },
            as_of_date=self.as_of,
        )
        result = aggregate_shipment_forecast(
            9,
            [first, second],
            dispatch_buffer_days=1,
        )
        self.assertEqual(result.factory_out_date, date(2026, 8, 13))
        self.assertEqual(result.source, "PLANNER FORECAST")


if __name__ == "__main__":
    unittest.main()


class _FakeMappings:
    def __init__(self, rows):
        self._rows = rows
    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows
    def mappings(self):
        return _FakeMappings(self._rows)


class _NestedTx:
    def __init__(self, owner):
        self.owner = owner
    def __enter__(self):
        self.owner.savepoints += 1
        return self
    def __exit__(self, exc_type, exc, tb):
        return False


class _CompatConnection:
    def __init__(self, *, fail_model=False, fail_full=False):
        self.fail_model = fail_model
        self.fail_full = fail_full
        self.savepoints = 0
    def begin_nested(self):
        return _NestedTx(self)
    def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM mpps_factory_capacity_models" in sql:
            if self.fail_model:
                raise RuntimeError("optional V10 model table missing")
            return _FakeResult([])
        if "item.factory_out_reason" in sql:
            if self.fail_full:
                raise RuntimeError("optional reason column missing")
            return _FakeResult([
                {
                    "shipment_id": 77,
                    "sap_code": "60000139",
                    "quantity": 20,
                    "stock_allocated_qty": 20,
                    "produced_qty": 0,
                    "daily_capacity": 0,
                    "allocated_cavity_count": 0,
                    "item_receive_date": None,
                    "receive_date": None,
                    "end_date": None,
                    "start_date": None,
                    "factory_out_reason": "",
                    "schedule_reason": "",
                    "planning_note": "",
                    "smds_total_plan": 0,
                    "dispatch_buffer_days": 0,
                }
            ])
        if "'' AS factory_out_reason" in sql:
            return _FakeResult([
                {
                    "shipment_id": 77,
                    "sap_code": "60000139",
                    "quantity": 20,
                    "stock_allocated_qty": 20,
                    "produced_qty": 0,
                    "daily_capacity": 0,
                    "allocated_cavity_count": 0,
                    "item_receive_date": None,
                    "receive_date": None,
                    "end_date": None,
                    "start_date": None,
                    "factory_out_reason": "",
                    "schedule_reason": "",
                    "planning_note": "",
                    "smds_total_plan": 0,
                    "dispatch_buffer_days": 0,
                }
            ])
        raise AssertionError(sql)


class FactoryOutTransactionSafetyTests(unittest.TestCase):
    def test_missing_optional_model_table_does_not_abort_forecast_load(self):
        from app.services.factory_out_forecast_service import load_shipment_forecasts
        conn = _CompatConnection(fail_model=True)
        result = load_shipment_forecasts(conn, [77], as_of_date=date(2026, 8, 10))
        self.assertEqual(result[77].factory_out_date, date(2026, 8, 10))
        self.assertGreaterEqual(conn.savepoints, 2)

    def test_missing_optional_item_columns_falls_back_without_poisoning_transaction(self):
        from app.services.factory_out_forecast_service import load_shipment_forecasts
        conn = _CompatConnection(fail_full=True)
        result = load_shipment_forecasts(conn, [77], as_of_date=date(2026, 8, 10))
        self.assertEqual(result[77].factory_out_date, date(2026, 8, 10))
        self.assertGreaterEqual(conn.savepoints, 3)
