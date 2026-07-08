import os
import unittest
from datetime import date, datetime, timedelta

from sqlalchemy import text

from app.database import engine
from app.services.factory_planning_engine import FactoryPlanningEngine


class FactoryPlanningEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = FactoryPlanningEngine(start_date=date.today())
        self.engine.ensure_schema()
        self.prefix = f"TEST_{int(datetime.utcnow().timestamp())}"
        self._cleanup()

    def tearDown(self) -> None:
        self._cleanup()

    def _cleanup(self) -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM planning_resource_reservations"))
            conn.execute(text("DELETE FROM shipment_stock_allocations"))
            conn.execute(text("DELETE FROM mpps_shipment_items"))
            conn.execute(text("DELETE FROM mpps_shipments"))
            conn.execute(text("DELETE FROM mpps_sap_stock_items"))
            conn.execute(text("DELETE FROM smds"))
            conn.execute(text("DELETE FROM mold_master"))
            conn.execute(text("DELETE FROM casing_master"))
            conn.execute(text("DELETE FROM casing_units"))
            conn.execute(text("DELETE FROM production_line_cavities"))
            conn.execute(text("DELETE FROM planning_runs"))

    def _insert_smds(self, sap_code: str, total_plan: int = 2, approval: str = "Approved") -> None:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO smds (sap_code, material_description, key_code, casing_type, line, day_plan, night_plan, total_plan, planning_manager_approval_status)
                    VALUES (:sap_code, :material_description, :key_code, :casing_type, :line, :day_plan, :night_plan, :total_plan, :approval)
                """),
                {
                    "sap_code": sap_code,
                    "material_description": f"Test Tire {sap_code}",
                    "key_code": f"{self.prefix}-MOLD",
                    "casing_type": "",
                    "line": f"{self.prefix}-LINE",
                    "day_plan": total_plan,
                    "night_plan": 0,
                    "total_plan": total_plan,
                    "approval": approval,
                },
            )

    def _insert_stock(self, sap_code: str, qty: int) -> None:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO mpps_sap_stock_items (sap_code, fg_stock, qc_stock, scrap_stock, blocked_stock, item_description)
                    VALUES (:sap_code, :fg, :qc, :scrap, :blocked, :description)
                """),
                {
                    "sap_code": sap_code,
                    "fg": qty,
                    "qc": 0,
                    "scrap": 0,
                    "blocked": 0,
                    "description": f"Stock {sap_code}",
                },
            )

    def _insert_mold(self, key_code: str, count: int) -> None:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO mold_master (mold_key_code, mold_count, production_mold_count, breakdown_mold_count, planning_reserved_mold_count, status, remarks)
                    VALUES (:key_code, :count, 0, 0, 0, 'Active', 'test')
                """),
                {"key_code": key_code, "count": count},
            )

    def _insert_line(self, line_name: str, count: int) -> None:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO production_line_cavities (line_name, cavity_no, status, assigned_tyre_item, remarks)
                    VALUES (:line_name, 1, 'Active', '', 'test')
                """),
                {"line_name": line_name},
            )
            for idx in range(2, count + 1):
                conn.execute(
                    text("""
                        INSERT INTO production_line_cavities (line_name, cavity_no, status, assigned_tyre_item, remarks)
                        VALUES (:line_name, :cavity_no, 'Active', '', 'test')
                    """),
                    {"line_name": line_name, "cavity_no": idx},
                )

    def _create_shipment(self, shipment_no: str, target_date: date | None, item_qty: int, sap_code: str) -> int:
        with engine.begin() as conn:
            shipment_id = conn.execute(
                text("""
                    INSERT INTO mpps_shipments (shipment_no, shipment_name, customer_name, shipment_date, status, target_date, plan_date, factory_out_date, delivery_status, total_qty, completed_qty, progress_pct, planning_status, planning_note)
                    VALUES (:shipment_no, :shipment_name, :customer_name, :shipment_date, 'Planned', :target_date, :plan_date, :factory_out_date, '', 0, 0, 0, '', '')
                    RETURNING id
                """),
                {
                    "shipment_no": shipment_no,
                    "shipment_name": shipment_no,
                    "customer_name": "Test Customer",
                    "shipment_date": date.today(),
                    "target_date": target_date,
                    "plan_date": target_date,
                    "factory_out_date": None,
                },
            ).scalar_one()
            conn.execute(
                text("""
                    INSERT INTO mpps_shipment_items (shipment_id, sap_code, item_description, quantity, stock_allocated_qty, produced_qty, completed_qty, production_required_qty, remaining_qty, allocated_cavity_count, daily_capacity, production_days, item_receive_date, receive_date, progress_pct, item_status, schedule_reason, factory_out_reason)
                    VALUES (:shipment_id, :sap_code, :item_description, :qty, 0, 0, 0, :qty, :qty, 0, 0, 0, NULL, NULL, 0, '', '', '')
                """),
                {"shipment_id": shipment_id, "sap_code": sap_code, "item_description": f"Item {sap_code}", "qty": item_qty},
            )
            return int(shipment_id)

    def test_stock_allocation_priority(self) -> None:
        sap_code = f"{self.prefix}-STOCK"
        self._insert_smds(sap_code, total_plan=2)
        self._insert_stock(sap_code, 10)
        self._insert_mold(f"{self.prefix}-MOLD", 2)
        self._insert_line(f"{self.prefix}-LINE", 2)

        first_id = self._create_shipment(f"{self.prefix}-A", None, 8, sap_code)
        second_id = self._create_shipment(f"{self.prefix}-B", None, 5, sap_code)

        result = self.engine.replan_all_open_shipments(trigger_reason="test", created_by="tests")

        self.assertEqual(len(result.shipments), 2)
        with engine.connect() as conn:
            item_a = conn.execute(text("SELECT stock_allocated_qty FROM mpps_shipment_items WHERE shipment_id = :shipment_id"), {"shipment_id": first_id}).mappings().one()
            item_b = conn.execute(text("SELECT stock_allocated_qty FROM mpps_shipment_items WHERE shipment_id = :shipment_id"), {"shipment_id": second_id}).mappings().one()
        self.assertEqual(int(item_a["stock_allocated_qty"]), 8)
        self.assertEqual(int(item_b["stock_allocated_qty"]), 2)

    def test_target_date_priority_sorting(self) -> None:
        sap_code = f"{self.prefix}-PRIORITY"
        self._insert_smds(sap_code, total_plan=2)
        self._insert_stock(sap_code, 0)
        self._insert_mold(f"{self.prefix}-MOLD", 2)
        self._insert_line(f"{self.prefix}-LINE", 2)

        earlier_id = self._create_shipment(f"{self.prefix}-EARLY", date.today() + timedelta(days=2), 4, sap_code)
        later_id = self._create_shipment(f"{self.prefix}-LATE", date.today() + timedelta(days=5), 4, sap_code)
        flex_id = self._create_shipment(f"{self.prefix}-FLEX", None, 4, sap_code)

        result = self.engine.replan_all_open_shipments(trigger_reason="test", created_by="tests")
        ordered_ids = [item.shipment_id for item in result.shipments]
        self.assertLess(ordered_ids.index(earlier_id), ordered_ids.index(later_id))
        self.assertGreater(ordered_ids.index(flex_id), ordered_ids.index(later_id))

    def test_target_date_null_goes_after_dated_orders(self) -> None:
        sap_code = f"{self.prefix}-NULL"
        self._insert_smds(sap_code, total_plan=2)
        self._insert_stock(sap_code, 0)
        self._insert_mold(f"{self.prefix}-MOLD", 2)
        self._insert_line(f"{self.prefix}-LINE", 2)

        dated_id = self._create_shipment(f"{self.prefix}-DATED", date.today() + timedelta(days=1), 2, sap_code)
        no_target_id = self._create_shipment(f"{self.prefix}-NOTARGET", None, 2, sap_code)

        result = self.engine.replan_all_open_shipments(trigger_reason="test", created_by="tests")
        ordered_ids = [item.shipment_id for item in result.shipments]
        self.assertLess(ordered_ids.index(dated_id), ordered_ids.index(no_target_id))

    def test_progress_includes_stock_and_produced(self) -> None:
        sap_code = f"{self.prefix}-PROGRESS"
        self._insert_smds(sap_code, total_plan=2)
        self._insert_stock(sap_code, 6)
        self._insert_mold(f"{self.prefix}-MOLD", 2)
        self._insert_line(f"{self.prefix}-LINE", 2)

        shipment_id = self._create_shipment(f"{self.prefix}-PROG", None, 10, sap_code)
        with engine.begin() as conn:
            conn.execute(text("UPDATE mpps_shipment_items SET produced_qty = 2 WHERE shipment_id = :id"), {"id": shipment_id})

        self.engine.replan_all_open_shipments(trigger_reason="test", created_by="tests")
        with engine.connect() as conn:
            row = conn.execute(text("SELECT completed_qty, progress_pct FROM mpps_shipment_items WHERE shipment_id = :id"), {"id": shipment_id}).mappings().one()
        self.assertEqual(int(row["completed_qty"]), 8)
        self.assertEqual(float(row["progress_pct"]), 80.0)

    def test_shipment_progress_is_weighted_by_quantity(self) -> None:
        sap_code = f"{self.prefix}-WEIGHT"
        self._insert_smds(sap_code, total_plan=2)
        self._insert_stock(sap_code, 10)
        self._insert_mold(f"{self.prefix}-MOLD", 2)
        self._insert_line(f"{self.prefix}-LINE", 2)

        shipment_id = self._create_shipment(f"{self.prefix}-WEIGHT", None, 10, sap_code)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO mpps_shipment_items (shipment_id, sap_code, item_description, quantity, stock_allocated_qty, produced_qty, completed_qty, production_required_qty, remaining_qty, allocated_cavity_count, daily_capacity, production_days, item_receive_date, receive_date, progress_pct, item_status, schedule_reason, factory_out_reason) VALUES (:shipment_id, :sap_code, :item_description, :qty, 0, 0, 0, :qty, :qty, 0, 0, 0, NULL, NULL, 0, '', '', '')"), {"shipment_id": shipment_id, "sap_code": f"{sap_code}-2", "item_description": "Second item", "qty": 20})

        self.engine.replan_all_open_shipments(trigger_reason="test", created_by="tests")
        with engine.connect() as conn:
            row = conn.execute(text("SELECT progress_pct FROM mpps_shipments WHERE id = :id"), {"id": shipment_id}).mappings().one()
        self.assertEqual(float(row["progress_pct"]), 33.33)

    def test_cavity_allocation_does_not_over_allocate(self) -> None:
        sap_code = f"{self.prefix}-CAVITY"
        self._insert_smds(sap_code, total_plan=2)
        self._insert_stock(sap_code, 0)
        self._insert_mold(f"{self.prefix}-MOLD", 1)
        self._insert_line(f"{self.prefix}-LINE", 1)

        shipment_id = self._create_shipment(f"{self.prefix}-CAV", None, 10, sap_code)
        self.engine.replan_all_open_shipments(trigger_reason="test", created_by="tests")
        with engine.connect() as conn:
            row = conn.execute(text("SELECT allocated_cavity_count, daily_capacity, production_required_qty FROM mpps_shipment_items WHERE shipment_id = :id"), {"id": shipment_id}).mappings().one()
        self.assertEqual(int(row["allocated_cavity_count"]), 1)
        self.assertEqual(int(row["daily_capacity"]), 2)

    def test_resource_unavailable_today_searches_future_dates(self) -> None:
        sap_code = f"{self.prefix}-FUTURE"
        self._insert_smds(sap_code, total_plan=2)
        self._insert_stock(sap_code, 0)
        self._insert_mold(f"{self.prefix}-MOLD", 1)
        self._insert_line(f"{self.prefix}-LINE", 1)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO planning_resource_reservations (planning_version, shipment_id, shipment_item_id, reservation_date, resource_type, resource_key, reserved_qty, capacity_qty, sap_code, note) VALUES (0, 0, 0, :date, 'line_cavity', :line, 1, 1, :sap, 'reserved')"), {"date": date.today(), "line": f"{self.prefix}-LINE", "sap": sap_code})

        shipment_id = self._create_shipment(f"{self.prefix}-FUT", None, 5, sap_code)
        self.engine.replan_all_open_shipments(trigger_reason="test", created_by="tests")
        with engine.connect() as conn:
            row = conn.execute(text("SELECT item_receive_date, item_status FROM mpps_shipment_items WHERE shipment_id = :id"), {"id": shipment_id}).mappings().one()
        self.assertEqual(row["item_status"], "Planned")
        self.assertGreaterEqual(row["item_receive_date"], date.today() + timedelta(days=1))

    def test_factory_can_receive_date_is_latest_item_receive_date(self) -> None:
        sap_code = f"{self.prefix}-RECEIVE"
        self._insert_smds(sap_code, total_plan=2)
        self._insert_stock(sap_code, 0)
        self._insert_mold(f"{self.prefix}-MOLD", 2)
        self._insert_line(f"{self.prefix}-LINE", 2)

        shipment_id = self._create_shipment(f"{self.prefix}-RECV", None, 10, sap_code)
        self.engine.replan_all_open_shipments(trigger_reason="test", created_by="tests")
        with engine.connect() as conn:
            row = conn.execute(text("SELECT factory_can_receive_date FROM mpps_shipments WHERE id = :id"), {"id": shipment_id}).mappings().one()
        self.assertEqual(row["factory_can_receive_date"], date.today() + timedelta(days=3))


if __name__ == "__main__":
    unittest.main()
