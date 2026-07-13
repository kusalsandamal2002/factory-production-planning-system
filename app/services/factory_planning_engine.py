from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from math import ceil
from typing import Any

from sqlalchemy import Date, bindparam, text

from app.database import engine

OPEN_SHIPMENT_STATUSES = {"planned", "pending", "open", "saved", "in progress", "processing", ""}
CLOSED_SHIPMENT_STATUSES = {"cancelled", "canceled", "closed", "complete", "completed", "shipped", "done"}
NO_CASING_VALUES = {"", "-", "no casing", "none", "n/a", "na", "not required"}


@dataclass
class ShipmentItemPlanResult:
    shipment_id: int
    shipment_item_id: int | None
    sap_code: str
    description: str
    order_qty: int
    stock_allocated_qty: int
    produced_qty: int
    completed_qty: int
    remaining_qty: int
    allocated_cavity_count: int
    daily_capacity: int
    production_days: int
    item_receive_date: date | None
    receive_date: date | None
    progress_pct: float
    item_status: str
    schedule_reason: str
    factory_out_reason: str


@dataclass
class ShipmentPlanResult:
    shipment_id: int
    shipment_no: str
    shipment_name: str
    target_date: date | None
    plan_date: date | None
    factory_can_receive_date: date | None
    delivery_status: str
    delay_days: int
    early_days: int
    total_qty: int
    completed_qty: int
    progress_pct: float
    planning_status: str
    planning_note: str
    items: list[ShipmentItemPlanResult]


@dataclass
class PlanningRunResult:
    planning_run_id: int | None
    planning_version: int
    status: str
    message: str
    shipments: list[ShipmentPlanResult]


class FactoryPlanningEngine:
    def __init__(self, start_date: date | None = None, planning_horizon_days: int = 365) -> None:
        self.start_date = start_date or date.today()
        self.planning_horizon_days = planning_horizon_days
        self._resource_usage: dict[tuple[date, str, str], int] = {}

    def ensure_schema(self) -> None:
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            conn.execute(text("SET LOCAL statement_timeout = '30s'"))
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS mpps_sap_stock_items (
                    id BIGSERIAL PRIMARY KEY,
                    sap_code VARCHAR(100) NOT NULL UNIQUE,
                    tyre_description TEXT NOT NULL DEFAULT '',
                    item_description TEXT NOT NULL DEFAULT '',
                    fg_stock INTEGER NOT NULL DEFAULT 0,
                    qc_stock INTEGER NOT NULL DEFAULT 0,
                    scrap_stock INTEGER NOT NULL DEFAULT 0,
                    blocked_stock INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            for sql in [
                "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS tyre_description TEXT",
                "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS item_description TEXT",
                "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS fg_stock INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS qc_stock INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS scrap_stock INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS blocked_stock INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_sap_stock_items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
                "UPDATE mpps_sap_stock_items SET tyre_description = COALESCE(NULLIF(TRIM(COALESCE(tyre_description, '')), ''), NULLIF(TRIM(COALESCE(item_description, '')), ''), sap_code, '') WHERE COALESCE(NULLIF(TRIM(COALESCE(tyre_description, '')), ''), '') = ''",
                "UPDATE mpps_sap_stock_items SET item_description = COALESCE(NULLIF(TRIM(COALESCE(item_description, '')), ''), NULLIF(TRIM(COALESCE(tyre_description, '')), ''), sap_code, '') WHERE COALESCE(NULLIF(TRIM(COALESCE(item_description, '')), ''), '') = ''",
                "ALTER TABLE mpps_sap_stock_items ALTER COLUMN tyre_description SET DEFAULT ''",
                "ALTER TABLE mpps_sap_stock_items ALTER COLUMN item_description SET DEFAULT ''",
            ]:
                conn.execute(text(sql))

            conn.execute(text("""
                CREATE OR REPLACE FUNCTION sync_stock_item_descriptions()
                RETURNS TRIGGER AS $$
                BEGIN
                    IF NEW.tyre_description IS NULL OR TRIM(COALESCE(NEW.tyre_description, '')) = '' THEN
                        NEW.tyre_description := COALESCE(NULLIF(TRIM(COALESCE(NEW.item_description, '')), ''), NEW.sap_code, '');
                    END IF;
                    IF NEW.item_description IS NULL OR TRIM(COALESCE(NEW.item_description, '')) = '' THEN
                        NEW.item_description := COALESCE(NULLIF(TRIM(COALESCE(NEW.tyre_description, '')), ''), NEW.sap_code, '');
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """))
            conn.execute(text("""
                DROP TRIGGER IF EXISTS trg_sync_stock_item_descriptions ON mpps_sap_stock_items
            """))
            conn.execute(text("""
                CREATE TRIGGER trg_sync_stock_item_descriptions
                BEFORE INSERT OR UPDATE OF sap_code, tyre_description, item_description ON mpps_sap_stock_items
                FOR EACH ROW EXECUTE FUNCTION sync_stock_item_descriptions()
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS mpps_shipments (
                    id SERIAL PRIMARY KEY,
                    shipment_no VARCHAR(100) NOT NULL UNIQUE,
                    shipment_name VARCHAR(255) NOT NULL DEFAULT '',
                    customer_name VARCHAR(255) NOT NULL DEFAULT '',
                    shipment_date DATE NOT NULL,
                    target_date DATE,
                    plan_date DATE,
                    factory_can_receive_date DATE,
                    factory_out_date DATE,
                    delivery_status VARCHAR(80) NOT NULL DEFAULT '',
                    delay_days INTEGER NOT NULL DEFAULT 0,
                    early_days INTEGER NOT NULL DEFAULT 0,
                    total_qty INTEGER NOT NULL DEFAULT 0,
                    completed_qty INTEGER NOT NULL DEFAULT 0,
                    progress_pct NUMERIC(6,2) NOT NULL DEFAULT 0,
                    planning_status VARCHAR(80) NOT NULL DEFAULT '',
                    planning_note TEXT NOT NULL DEFAULT '',
                    planning_version BIGINT NOT NULL DEFAULT 0,
                    last_replanned_at TIMESTAMP,
                    status VARCHAR(50) NOT NULL DEFAULT 'Planned',
                    note TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS mpps_shipment_items (
                    id SERIAL PRIMARY KEY,
                    shipment_id INTEGER NOT NULL REFERENCES mpps_shipments(id) ON DELETE CASCADE,
                    sap_code VARCHAR(100) NOT NULL,
                    item_description TEXT NOT NULL DEFAULT '',
                    quantity INTEGER NOT NULL DEFAULT 0,
                    stock_allocated_qty INTEGER NOT NULL DEFAULT 0,
                    produced_qty INTEGER NOT NULL DEFAULT 0,
                    completed_qty INTEGER NOT NULL DEFAULT 0,
                    production_required_qty INTEGER NOT NULL DEFAULT 0,
                    remaining_qty INTEGER NOT NULL DEFAULT 0,
                    allocated_cavity_count INTEGER NOT NULL DEFAULT 0,
                    daily_capacity INTEGER NOT NULL DEFAULT 0,
                    production_days INTEGER NOT NULL DEFAULT 0,
                    item_receive_date DATE,
                    receive_date DATE,
                    progress_pct NUMERIC(6,2) NOT NULL DEFAULT 0,
                    item_status VARCHAR(80) NOT NULL DEFAULT '',
                    schedule_reason TEXT NOT NULL DEFAULT '',
                    factory_out_reason TEXT NOT NULL DEFAULT '',
                    planning_version BIGINT NOT NULL DEFAULT 0,
                    start_date DATE,
                    end_date DATE,
                    item_status_old VARCHAR(80),
                    note TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            for sql in [
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS target_date DATE",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS plan_date DATE",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS factory_can_receive_date DATE",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS factory_out_date DATE",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(80) NOT NULL DEFAULT ''",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS delay_days INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS early_days INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS total_qty INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS completed_qty INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS progress_pct NUMERIC(6,2) NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS planning_status VARCHAR(80) NOT NULL DEFAULT ''",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS planning_note TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS planning_version BIGINT NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS last_replanned_at TIMESTAMP",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS stock_allocated_qty INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS produced_qty INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS completed_qty INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS production_required_qty INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS remaining_qty INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS allocated_cavity_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS daily_capacity INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS production_days INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS item_receive_date DATE",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS receive_date DATE",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS progress_pct NUMERIC(6,2) NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS item_status VARCHAR(80) NOT NULL DEFAULT ''",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS schedule_reason TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS factory_out_reason TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS planning_version BIGINT NOT NULL DEFAULT 0",
                "ALTER TABLE mpps_shipment_items ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            ]:
                conn.execute(text(sql))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS planning_runs (
                    id BIGSERIAL PRIMARY KEY,
                    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    finished_at TIMESTAMP,
                    trigger_reason TEXT NOT NULL DEFAULT '',
                    status VARCHAR(50) NOT NULL DEFAULT 'Running',
                    message TEXT NOT NULL DEFAULT '',
                    planning_version BIGINT NOT NULL,
                    created_by TEXT NOT NULL DEFAULT ''
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS shipment_stock_allocations (
                    id BIGSERIAL PRIMARY KEY,
                    planning_run_id BIGINT REFERENCES planning_runs(id) ON DELETE SET NULL,
                    shipment_id INTEGER NOT NULL REFERENCES mpps_shipments(id) ON DELETE CASCADE,
                    shipment_item_id INTEGER REFERENCES mpps_shipment_items(id) ON DELETE CASCADE,
                    sap_code VARCHAR(100) NOT NULL,
                    allocated_stock_qty INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS planning_resource_reservations (
                    id BIGSERIAL PRIMARY KEY,
                    planning_run_id BIGINT REFERENCES planning_runs(id) ON DELETE SET NULL,
                    planning_version BIGINT NOT NULL DEFAULT 0,
                    shipment_id INTEGER,
                    shipment_item_id INTEGER,
                    reservation_date DATE NOT NULL,
                    resource_type VARCHAR(30) NOT NULL,
                    resource_key VARCHAR(255) NOT NULL,
                    reserved_qty INTEGER NOT NULL DEFAULT 0,
                    capacity_qty INTEGER NOT NULL DEFAULT 0,
                    sap_code VARCHAR(100) NOT NULL DEFAULT '',
                    note TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            for sql in [
                "ALTER TABLE planning_resource_reservations ALTER COLUMN shipment_id DROP NOT NULL",
                "ALTER TABLE planning_resource_reservations ALTER COLUMN shipment_item_id DROP NOT NULL",
                "ALTER TABLE planning_resource_reservations DROP CONSTRAINT IF EXISTS planning_resource_reservations_shipment_id_fkey",
                "ALTER TABLE planning_resource_reservations DROP CONSTRAINT IF EXISTS planning_resource_reservations_shipment_item_id_fkey",
            ]:
                conn.execute(text(sql))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS mold_master (
                    id BIGSERIAL PRIMARY KEY,
                    mold_key_code VARCHAR(255) NOT NULL UNIQUE,
                    mold_count INTEGER NOT NULL DEFAULT 0,
                    production_mold_count INTEGER NOT NULL DEFAULT 0,
                    breakdown_mold_count INTEGER NOT NULL DEFAULT 0,
                    planning_reserved_mold_count INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(32) NOT NULL DEFAULT 'Active',
                    remarks TEXT NOT NULL DEFAULT '',
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS casing_master (
                    id BIGSERIAL PRIMARY KEY,
                    casing_type VARCHAR(255) NOT NULL UNIQUE,
                    total_casing_count INTEGER NOT NULL DEFAULT 0,
                    available_casing_count INTEGER NOT NULL DEFAULT 0,
                    production_casing_count INTEGER NOT NULL DEFAULT 0,
                    breakdown_casing_count INTEGER NOT NULL DEFAULT 0,
                    planning_reserved_casing_count INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(32) NOT NULL DEFAULT 'Active',
                    remarks TEXT NOT NULL DEFAULT '',
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS casing_units (
                    id BIGSERIAL PRIMARY KEY,
                    casing_type VARCHAR(255) NOT NULL,
                    casing_no INTEGER NOT NULL,
                    casing_code VARCHAR(255) NOT NULL,
                    condition_status VARCHAR(32) NOT NULL DEFAULT 'Active',
                    stock_status VARCHAR(32) NOT NULL DEFAULT 'Free',
                    remarks TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS production_line_cavities (
                    id BIGSERIAL PRIMARY KEY,
                    line_name VARCHAR(255) NOT NULL,
                    cavity_no INTEGER NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'Active',
                    assigned_tyre_item VARCHAR(255) NOT NULL DEFAULT '',
                    remarks TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(line_name, cavity_no)
                )
            """))

            for sql in [
                "ALTER TABLE mold_master ADD COLUMN IF NOT EXISTS production_mold_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mold_master ADD COLUMN IF NOT EXISTS breakdown_mold_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mold_master ADD COLUMN IF NOT EXISTS planning_reserved_mold_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE casing_master ADD COLUMN IF NOT EXISTS total_casing_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE casing_master ADD COLUMN IF NOT EXISTS available_casing_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE casing_master ADD COLUMN IF NOT EXISTS production_casing_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE casing_master ADD COLUMN IF NOT EXISTS breakdown_casing_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE casing_master ADD COLUMN IF NOT EXISTS planning_reserved_casing_count INTEGER NOT NULL DEFAULT 0",
            ]:
                conn.execute(text(sql))

            for sql in [
                "CREATE INDEX IF NOT EXISTS ix_mpps_shipments_status ON mpps_shipments (status)",
                "CREATE INDEX IF NOT EXISTS ix_mpps_shipments_target_date ON mpps_shipments (target_date)",
                "CREATE INDEX IF NOT EXISTS ix_mpps_shipments_factory_can_receive_date ON mpps_shipments (factory_can_receive_date)",
                "CREATE INDEX IF NOT EXISTS ix_mpps_shipment_items_shipment_id ON mpps_shipment_items (shipment_id)",
                "CREATE INDEX IF NOT EXISTS ix_mpps_shipment_items_sap_code ON mpps_shipment_items (sap_code)",
                "CREATE INDEX IF NOT EXISTS ix_shipment_stock_allocations_sap_code ON shipment_stock_allocations (sap_code)",
                "CREATE INDEX IF NOT EXISTS ix_shipment_stock_allocations_shipment_id ON shipment_stock_allocations (shipment_id)",
                "CREATE INDEX IF NOT EXISTS ix_planning_resource_reservations_reservation_date ON planning_resource_reservations (reservation_date)",
                "CREATE INDEX IF NOT EXISTS ix_planning_resource_reservations_resource_type_key_date ON planning_resource_reservations (resource_type, resource_key, reservation_date)",
                "CREATE INDEX IF NOT EXISTS ix_planning_resource_reservations_shipment_id ON planning_resource_reservations (shipment_id)",
                "CREATE INDEX IF NOT EXISTS ix_planning_resource_reservations_shipment_item_id ON planning_resource_reservations (shipment_item_id)",
            ]:
                conn.execute(text(sql))

    def replan_all_open_shipments(self, trigger_reason: str = "", created_by: str = "") -> PlanningRunResult:
        self.ensure_schema()
        planning_version = int(datetime.utcnow().timestamp() * 1000)
        self._resource_usage.clear()
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL lock_timeout = '5s'"))
            conn.execute(text("SET LOCAL statement_timeout = '30s'"))
            run_id = int(conn.execute(text("""
                INSERT INTO planning_runs (trigger_reason, status, message, planning_version, created_by)
                VALUES (:trigger_reason, 'Running', 'Planning started', :version, :created_by)
                RETURNING id
            """), {"trigger_reason": trigger_reason, "version": planning_version, "created_by": created_by}).scalar_one())

            conn.execute(text("DELETE FROM planning_resource_reservations"))
            conn.execute(text("DELETE FROM shipment_stock_allocations"))

            open_shipments = conn.execute(text("""
                SELECT id, shipment_no, shipment_name, customer_name, shipment_date, target_date, plan_date, status, created_at, note, COALESCE(shipment_name, '') AS shipment_label
                FROM mpps_shipments
                WHERE COALESCE(LOWER(status), 'planned') NOT IN ('cancelled', 'canceled', 'closed', 'complete', 'completed', 'shipped', 'done')
                ORDER BY CASE WHEN target_date IS NULL THEN 1 ELSE 0 END, COALESCE(target_date, DATE '9999-12-31') ASC, COALESCE(created_at, CURRENT_TIMESTAMP) ASC, id ASC
            """))
            shipment_rows = [dict(row) for row in open_shipments.mappings().all()]

            stock_remaining_by_sap: dict[str, int] = {}
            shipment_results: list[ShipmentPlanResult] = []
            for shipment in shipment_rows:
                shipment_id = int(shipment["id"])
                items = conn.execute(text("""
                    SELECT id, sap_code, item_description, quantity, produced_qty, stock_allocated_qty, completed_qty,
                           production_required_qty, remaining_qty, allocated_cavity_count, daily_capacity,
                           production_days, item_receive_date, receive_date, progress_pct, item_status,
                           schedule_reason, factory_out_reason
                    FROM mpps_shipment_items
                    WHERE shipment_id = :shipment_id
                    ORDER BY id ASC
                """), {"shipment_id": shipment_id}).mappings().all()

                item_results: list[ShipmentItemPlanResult] = []
                total_qty = 0
                completed_qty = 0
                shipment_note_parts: list[str] = []
                latest_item_date: date | None = None
                item_statuses: list[str] = []

                for item in items:
                    item_id = int(item["id"])
                    sap_code = str(item.get("sap_code") or "").strip()
                    order_qty = max(0, int(item.get("quantity") or 0))
                    produced_qty = max(0, int(item.get("produced_qty") or 0))
                    total_qty += order_qty
                    if sap_code not in stock_remaining_by_sap:
                        stock_remaining_by_sap[sap_code] = self._get_available_stock(conn, sap_code)

                    stock_allocated_qty = min(order_qty, max(0, stock_remaining_by_sap[sap_code]))
                    stock_remaining_by_sap[sap_code] = max(0, stock_remaining_by_sap[sap_code] - stock_allocated_qty)
                    planned_item = self._plan_shipment_item(
                        conn=conn,
                        run_id=run_id,
                        planning_version=planning_version,
                        shipment=shipment,
                        shipment_item_id=item_id,
                        sap_code=sap_code,
                        description=str(item.get("item_description") or ""),
                        order_qty=order_qty,
                        stock_allocated_qty=stock_allocated_qty,
                        produced_qty=produced_qty,
                    )
                    item_results.append(planned_item)
                    completed_qty += planned_item.completed_qty
                    latest_item_date = planned_item.item_receive_date if planned_item.item_receive_date is not None and (latest_item_date is None or planned_item.item_receive_date > latest_item_date) else latest_item_date
                    item_statuses.append(planned_item.item_status)
                    if planned_item.item_status == "Blocked":
                        shipment_note_parts.append(f"{sap_code}: {planned_item.schedule_reason}")

                factory_can_receive_date = latest_item_date or shipment.get("shipment_date") or shipment.get("plan_date") or shipment.get("target_date") or self.start_date
                if not item_results:
                    factory_can_receive_date = shipment.get("shipment_date") or self.start_date
                shipment_status = self._evaluate_shipment_status(item_statuses, shipment.get("target_date"))
                planning_status = shipment_status
                delivery_status = self._evaluate_delivery_status(shipment.get("target_date"), factory_can_receive_date)
                if shipment.get("target_date") is None:
                    delivery_status = "Flexible / No Target Date"
                delay_days = 0
                early_days = 0
                if shipment.get("target_date") is not None:
                    if factory_can_receive_date is None:
                        delay_days = 0
                        early_days = 0
                    elif factory_can_receive_date < shipment.get("target_date"):
                        early_days = (shipment.get("target_date") - factory_can_receive_date).days
                    elif factory_can_receive_date > shipment.get("target_date"):
                        delay_days = (factory_can_receive_date - shipment.get("target_date")).days

                progress_pct = round((completed_qty / total_qty * 100) if total_qty else 0.0, 2)
                planning_note = "; ".join(shipment_note_parts) if shipment_note_parts else "Planned within available capacity."

                stmt = text("""
                    UPDATE mpps_shipments
                    SET target_date = :target_date,
                        plan_date = COALESCE(:plan_date, :plan_date_fallback),
                        factory_can_receive_date = :factory_can_receive_date,
                        factory_out_date = :factory_out_date,
                        delivery_status = :delivery_status,
                        delay_days = :delay_days,
                        early_days = :early_days,
                        total_qty = :total_qty,
                        completed_qty = :completed_qty,
                        progress_pct = :progress_pct,
                        planning_status = :planning_status,
                        planning_note = :planning_note,
                        planning_version = :planning_version,
                        last_replanned_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :shipment_id
                """).bindparams(
                    bindparam("target_date", type_=Date),
                    bindparam("plan_date", type_=Date),
                    bindparam("plan_date_fallback", type_=Date),
                    bindparam("factory_can_receive_date", type_=Date),
                    bindparam("factory_out_date", type_=Date),
                )
                conn.execute(stmt, {
                    "shipment_id": shipment_id,
                    "target_date": shipment.get("target_date"),
                    "plan_date": shipment.get("plan_date"),
                    "plan_date_fallback": shipment.get("target_date") or shipment.get("shipment_date"),
                    "factory_can_receive_date": factory_can_receive_date,
                    "factory_out_date": factory_can_receive_date,
                    "delivery_status": delivery_status,
                    "delay_days": delay_days,
                    "early_days": early_days,
                    "total_qty": total_qty,
                    "completed_qty": completed_qty,
                    "progress_pct": progress_pct,
                    "planning_status": planning_status,
                    "planning_note": planning_note,
                    "planning_version": planning_version,
                })

                shipment_results.append(ShipmentPlanResult(
                    shipment_id=shipment_id,
                    shipment_no=str(shipment.get("shipment_no") or ""),
                    shipment_name=str(shipment.get("shipment_name") or shipment.get("shipment_no") or ""),
                    target_date=shipment.get("target_date"),
                    plan_date=shipment.get("plan_date") or shipment.get("target_date"),
                    factory_can_receive_date=factory_can_receive_date,
                    delivery_status=delivery_status,
                    delay_days=delay_days,
                    early_days=early_days,
                    total_qty=total_qty,
                    completed_qty=completed_qty,
                    progress_pct=progress_pct,
                    planning_status=planning_status,
                    planning_note=planning_note,
                    items=item_results,
                ))

            conn.execute(text("UPDATE planning_runs SET status = 'Completed', finished_at = CURRENT_TIMESTAMP, message = :message WHERE id = :id"), {
                "id": run_id,
                "message": f"Planned {len(shipment_results)} shipments.",
            })

        return PlanningRunResult(planning_run_id=run_id, planning_version=planning_version, status="Completed", message="Planning completed", shipments=shipment_results)

    def replan_single_shipment_preview(self, shipment_id: int) -> ShipmentPlanResult:
        self.ensure_schema()
        result = self.replan_all_open_shipments(trigger_reason=f"single_shipment_{shipment_id}", created_by="ui")
        for shipment in result.shipments:
            if shipment.shipment_id == shipment_id:
                return shipment
        raise ValueError(f"Shipment {shipment_id} was not found in planning output.")

    def calculate_cart_items(self, cart_items: list[dict[str, Any]], target_date: date | None = None, exclude_shipment_id: int | None = None) -> list[dict[str, Any]]:
        self.ensure_schema()
        results: list[dict[str, Any]] = []
        with engine.begin() as conn:
            stock_remaining_by_sap: dict[str, int] = {}
            for source_item in cart_items:
                sap_code = str(source_item.get("sap_code") or "").strip()
                order_qty = max(0, int(source_item.get("quantity") or 0))
                description = str(source_item.get("item_description") or "")
                if sap_code not in stock_remaining_by_sap:
                    stock_remaining_by_sap[sap_code] = self._get_available_stock(conn, sap_code, exclude_shipment_id=exclude_shipment_id)
                stock_allocated_qty = min(order_qty, max(0, stock_remaining_by_sap[sap_code]))
                stock_remaining_by_sap[sap_code] = max(0, stock_remaining_by_sap[sap_code] - stock_allocated_qty)
                result = self._plan_shipment_item(
                    conn=conn,
                    run_id=None,
                    planning_version=0,
                    shipment={"id": 0, "target_date": target_date, "shipment_no": "", "shipment_name": "", "shipment_date": self.start_date},
                    shipment_item_id=None,
                    sap_code=sap_code,
                    description=description,
                    order_qty=order_qty,
                    stock_allocated_qty=stock_allocated_qty,
                    produced_qty=0,
                    preview=True,
                )
                enriched = dict(source_item)
                enriched.update({
                    "sap_code": sap_code,
                    "description": result.description,
                    "order_qty": result.order_qty,
                    "stock_allocated_qty": result.stock_allocated_qty,
                    "production_required_qty": result.remaining_qty,
                    "allocated_cavity_count": result.allocated_cavity_count,
                    "daily_capacity": result.daily_capacity,
                    "production_days": result.production_days,
                    "receive_date": result.item_receive_date,
                    "item_receive_date": result.item_receive_date,
                    "status": result.item_status,
                    "reason": result.schedule_reason or result.factory_out_reason,
                    "item_description": result.description or description,
                    "quantity": result.order_qty,
                })
                results.append(enriched)
        return results

    def final_shipment_date(self, cart_items: list[dict[str, Any]]) -> date | None:
        dates = []
        for item in cart_items:
            value = item.get("receive_date") or item.get("item_receive_date")
            if isinstance(value, date):
                dates.append(value)
        return max(dates) if dates else None

    def _plan_shipment_item(
        self,
        conn,
        run_id: int | None,
        planning_version: int,
        shipment: dict[str, Any],
        shipment_item_id: int | None,
        sap_code: str,
        description: str,
        order_qty: int,
        stock_allocated_qty: int,
        produced_qty: int,
        preview: bool = False,
    ) -> ShipmentItemPlanResult:
        if not sap_code or order_qty <= 0:
            result = ShipmentItemPlanResult(
                shipment_id=int(shipment.get("id") or 0),
                shipment_item_id=shipment_item_id,
                sap_code=sap_code,
                description=description,
                order_qty=order_qty,
                stock_allocated_qty=0,
                produced_qty=0,
                completed_qty=0,
                remaining_qty=0,
                allocated_cavity_count=0,
                daily_capacity=0,
                production_days=0,
                item_receive_date=None,
                receive_date=None,
                progress_pct=0.0,
                item_status="Blocked",
                schedule_reason="Invalid SAP code or quantity.",
                factory_out_reason="Invalid SAP code or quantity.",
            )
            if not preview:
                self._persist_item_result(conn, shipment, shipment_item_id, result, planning_version)
            return result

        smds = self._load_smds_item(conn, sap_code)
        if not smds:
            result = ShipmentItemPlanResult(
                shipment_id=int(shipment.get("id") or 0),
                shipment_item_id=shipment_item_id,
                sap_code=sap_code,
                description=description,
                order_qty=order_qty,
                stock_allocated_qty=stock_allocated_qty,
                produced_qty=produced_qty,
                completed_qty=min(order_qty, stock_allocated_qty + produced_qty),
                remaining_qty=max(order_qty - stock_allocated_qty - produced_qty, 0),
                allocated_cavity_count=0,
                daily_capacity=0,
                production_days=0,
                item_receive_date=None,
                receive_date=None,
                progress_pct=0.0,
                item_status="Blocked",
                schedule_reason="SMDS item data not found.",
                factory_out_reason="SMDS item data not found.",
            )
            if not preview:
                self._persist_item_result(conn, shipment, shipment_item_id, result, planning_version)
            return result

        approval = str(smds.get("planning_manager_approval_status") or "Pending").strip().lower()
        if approval != "approved":
            result = ShipmentItemPlanResult(
                shipment_id=int(shipment.get("id") or 0),
                shipment_item_id=shipment_item_id,
                sap_code=sap_code,
                description=str(smds.get("material_description") or description),
                order_qty=order_qty,
                stock_allocated_qty=stock_allocated_qty,
                produced_qty=produced_qty,
                completed_qty=min(order_qty, stock_allocated_qty + produced_qty),
                remaining_qty=max(order_qty - stock_allocated_qty - produced_qty, 0),
                allocated_cavity_count=0,
                daily_capacity=0,
                production_days=0,
                item_receive_date=None,
                receive_date=None,
                progress_pct=0.0,
                item_status="Blocked",
                schedule_reason="Planning manager approval is not Approved.",
                factory_out_reason="Planning manager approval is not Approved.",
            )
            if not preview:
                self._persist_item_result(conn, shipment, shipment_item_id, result, planning_version)
            return result

        completed_qty = min(order_qty, stock_allocated_qty + produced_qty)
        remaining_qty = max(order_qty - stock_allocated_qty - produced_qty, 0)
        if remaining_qty <= 0:
            result = ShipmentItemPlanResult(
                shipment_id=int(shipment.get("id") or 0),
                shipment_item_id=shipment_item_id,
                sap_code=sap_code,
                description=str(smds.get("material_description") or description),
                order_qty=order_qty,
                stock_allocated_qty=stock_allocated_qty,
                produced_qty=produced_qty,
                completed_qty=completed_qty,
                remaining_qty=0,
                allocated_cavity_count=0,
                daily_capacity=0,
                production_days=0,
                item_receive_date=self.start_date,
                receive_date=self.start_date,
                progress_pct=round((completed_qty / order_qty * 100) if order_qty else 0.0, 2),
                item_status="Stock Ready",
                schedule_reason="Covered by stock allocation.",
                factory_out_reason="",
            )
            if not preview:
                self._persist_item_result(conn, shipment, shipment_item_id, result, planning_version)
            return result

        total_plan = max(0.0, float(smds.get("total_plan") or 0))
        if total_plan <= 0:
            result = ShipmentItemPlanResult(
                shipment_id=int(shipment.get("id") or 0),
                shipment_item_id=shipment_item_id,
                sap_code=sap_code,
                description=str(smds.get("material_description") or description),
                order_qty=order_qty,
                stock_allocated_qty=stock_allocated_qty,
                produced_qty=produced_qty,
                completed_qty=completed_qty,
                remaining_qty=remaining_qty,
                allocated_cavity_count=0,
                daily_capacity=0,
                production_days=0,
                item_receive_date=None,
                receive_date=None,
                progress_pct=round((completed_qty / order_qty * 100) if order_qty else 0.0, 2),
                item_status="Blocked",
                schedule_reason="SMDS total plan is missing or zero.",
                factory_out_reason="SMDS total plan is missing or zero.",
            )
            if not preview:
                self._persist_item_result(conn, shipment, shipment_item_id, result, planning_version)
            return result

        cae = self._schedule_item(
            conn=conn,
            run_id=run_id,
            planning_version=planning_version,
            shipment=shipment,
            shipment_item_id=shipment_item_id,
            sap_code=sap_code,
            description=str(smds.get("material_description") or description),
            remaining_qty=remaining_qty,
            stock_allocated_qty=stock_allocated_qty,
            produced_qty=produced_qty,
            order_qty=order_qty,
            smds=smds,
            preview=preview,
        )
        return cae

    def _schedule_item(
        self,
        conn,
        run_id: int | None,
        planning_version: int,
        shipment: dict[str, Any],
        shipment_item_id: int | None,
        sap_code: str,
        description: str,
        remaining_qty: int,
        stock_allocated_qty: int,
        produced_qty: int,
        order_qty: int,
        smds: dict[str, Any],
        preview: bool = False,
    ) -> ShipmentItemPlanResult:
        total_plan = max(0.0, float(smds.get("total_plan") or 0))
        mold_key = str(smds.get("key_code") or "").strip()
        casing_type = str(smds.get("casing_type") or "").strip()
        line_name = str(smds.get("line") or "").strip()
        casing_required = casing_type.lower() not in NO_CASING_VALUES

        current_date = self.start_date
        allocation_total = 0
        allocated_cavity_count = 0
        production_days = 0
        daily_capacity = 0
        receive_date = None
        reason = ""
        for day_offset in range(self.planning_horizon_days + 1):
            candidate_date = current_date + timedelta(days=day_offset)
            available_mold = self._available_mold_count(conn, mold_key, candidate_date, planning_version)
            available_casing = float("inf") if not casing_required else self._available_casing_count(conn, casing_type, candidate_date, planning_version)
            available_line = self._available_line_cavity_count(conn, line_name, candidate_date, planning_version)
            available_resource_cavities = int(min(available_mold, available_casing, available_line)) if available_casing != float("inf") else int(min(available_mold, available_line))
            if available_resource_cavities <= 0:
                continue
            required_cavities = max(1, ceil(remaining_qty / total_plan)) if total_plan > 0 else 0
            allocated_cavities = min(required_cavities, available_resource_cavities)
            if allocated_cavities <= 0:
                continue
            daily_production_qty = min(remaining_qty, allocated_cavities * total_plan)
            if daily_production_qty <= 0:
                continue
            allocation_total += daily_production_qty
            allocated_cavity_count = max(allocated_cavity_count, allocated_cavities)
            production_days += 1
            daily_capacity = max(daily_capacity, int(ceil(allocated_cavities * total_plan)))
            receive_date = candidate_date + timedelta(days=1)
            self._reserve_resource(conn, run_id, planning_version, shipment, shipment_item_id, candidate_date, "mold", mold_key, allocated_cavities, daily_capacity, sap_code, description)
            self._reserve_resource(conn, run_id, planning_version, shipment, shipment_item_id, candidate_date, "line_cavity", line_name, allocated_cavities, daily_capacity, sap_code, description)
            if casing_required:
                self._reserve_resource(conn, run_id, planning_version, shipment, shipment_item_id, candidate_date, "casing", casing_type, allocated_cavities, daily_capacity, sap_code, description)
            remaining_qty -= daily_production_qty
            if remaining_qty <= 0:
                break
        completed_qty = min(order_qty, stock_allocated_qty + produced_qty)
        if remaining_qty > 0:
            reason = "No resource available within planning horizon."
            item_status = "Blocked"
            receive_date = None
            allocated_cavity_count = 0
            daily_capacity = 0
            production_days = 0
        else:
            item_status = "Planned"
            reason = "Planned within available capacity."
        progress_pct = round((completed_qty / order_qty * 100) if order_qty else 0.0, 2)
        result = ShipmentItemPlanResult(
            shipment_id=int(shipment.get("id") or 0),
            shipment_item_id=shipment_item_id,
            sap_code=sap_code,
            description=description,
            order_qty=order_qty,
            stock_allocated_qty=stock_allocated_qty,
            produced_qty=produced_qty,
            completed_qty=completed_qty,
            remaining_qty=max(order_qty - completed_qty, 0),
            allocated_cavity_count=allocated_cavity_count,
            daily_capacity=daily_capacity,
            production_days=production_days,
            item_receive_date=receive_date,
            receive_date=receive_date,
            progress_pct=progress_pct,
            item_status=item_status,
            schedule_reason=reason,
            factory_out_reason=reason,
        )
        if not preview:
            self._persist_item_result(conn, shipment, shipment_item_id, result, planning_version)
        return result

    def _persist_item_result(self, conn, shipment: dict[str, Any], shipment_item_id: int | None, result: ShipmentItemPlanResult, planning_version: int) -> None:
        if shipment_item_id is None:
            return
        conn.execute(text("""
            UPDATE mpps_shipment_items
            SET stock_allocated_qty = :stock_allocated_qty,
                produced_qty = :produced_qty,
                completed_qty = :completed_qty,
                production_required_qty = :production_required_qty,
                remaining_qty = :remaining_qty,
                allocated_cavity_count = :allocated_cavity_count,
                daily_capacity = :daily_capacity,
                production_days = :production_days,
                item_receive_date = :item_receive_date,
                receive_date = :receive_date,
                progress_pct = :progress_pct,
                item_status = :item_status,
                schedule_reason = :schedule_reason,
                factory_out_reason = :factory_out_reason,
                planning_version = :planning_version,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :shipment_item_id
        """), {
            "stock_allocated_qty": result.stock_allocated_qty,
            "produced_qty": result.produced_qty,
            "completed_qty": result.completed_qty,
            "production_required_qty": result.remaining_qty if result.item_status != "Stock Ready" else 0,
            "remaining_qty": result.remaining_qty,
            "allocated_cavity_count": result.allocated_cavity_count,
            "daily_capacity": result.daily_capacity,
            "production_days": result.production_days,
            "item_receive_date": result.item_receive_date,
            "receive_date": result.item_receive_date,
            "progress_pct": result.progress_pct,
            "item_status": result.item_status,
            "schedule_reason": result.schedule_reason,
            "factory_out_reason": result.factory_out_reason,
            "planning_version": planning_version,
            "shipment_item_id": shipment_item_id,
        })

    def _reserve_resource(self, conn, run_id: int | None, planning_version: int, shipment: dict[str, Any], shipment_item_id: int | None, reservation_date: date, resource_type: str, resource_key: str, reserved_qty: int, capacity_qty: int, sap_code: str, note: str) -> None:
        if reserved_qty <= 0 or shipment_item_id is None:
            return
        key = (reservation_date, resource_type, resource_key)
        self._resource_usage[key] = int(self._resource_usage.get(key, 0)) + reserved_qty
        conn.execute(text("""
            INSERT INTO planning_resource_reservations (
                planning_run_id, planning_version, shipment_id, shipment_item_id, reservation_date,
                resource_type, resource_key, reserved_qty, capacity_qty, sap_code, note
            ) VALUES (
                :planning_run_id, :planning_version, :shipment_id, :shipment_item_id, :reservation_date,
                :resource_type, :resource_key, :reserved_qty, :capacity_qty, :sap_code, :note
            )
        """), {
            "planning_run_id": run_id,
            "planning_version": planning_version,
            "shipment_id": int(shipment.get("id") or 0),
            "shipment_item_id": shipment_item_id,
            "reservation_date": reservation_date,
            "resource_type": resource_type,
            "resource_key": resource_key,
            "reserved_qty": reserved_qty,
            "capacity_qty": capacity_qty,
            "sap_code": sap_code,
            "note": note,
        })

    def _load_smds_item(self, conn, sap_code: str) -> dict[str, Any] | None:
        try:
            row = conn.execute(text("""
                SELECT sap_code, material_description, key_code, casing_type, line, day_plan, night_plan, total_plan, planning_manager_approval_status
                FROM smds
                WHERE sap_code = :sap_code
                LIMIT 1
            """), {"sap_code": sap_code}).mappings().first()
            return dict(row) if row else None
        except Exception:
            return None

    def _get_available_stock(self, conn, sap_code: str, exclude_shipment_id: int | None = None) -> int:
        try:
            stock = conn.execute(text("""
                SELECT COALESCE(fg_stock, 0) + COALESCE(qc_stock, 0) - COALESCE(scrap_stock, 0) - COALESCE(blocked_stock, 0) AS available_qty
                FROM mpps_sap_stock_items
                WHERE sap_code = :sap_code
                LIMIT 1
            """), {"sap_code": sap_code}).scalar_one_or_none()
            if stock is None:
                return 0
            return max(0, int(stock))
        except Exception:
            return 0

    def _available_mold_count(self, conn, key_code: str, reservation_date: date, planning_version: int) -> int:
        if not key_code:
            return 0
        try:
            row = conn.execute(text("""
                SELECT COALESCE(mold_count, 0) AS total_count,
                       COALESCE(production_mold_count, 0) AS production_count,
                       COALESCE(breakdown_mold_count, 0) AS breakdown_count,
                       COALESCE(planning_reserved_mold_count, 0) AS planning_reserved_count
                FROM mold_master
                WHERE LOWER(TRIM(mold_key_code)) = LOWER(TRIM(:key_code))
                LIMIT 1
            """), {"key_code": key_code}).mappings().first()
            if not row:
                return 0
            total_count = int(row.get("total_count") or 0)
            reserved_count = self._resource_usage.get((reservation_date, "mold", key_code), 0)
            reserved_from_db = int(conn.execute(text("""
                SELECT COALESCE(SUM(reserved_qty), 0)
                FROM planning_resource_reservations
                WHERE reservation_date = :reservation_date
                  AND resource_type = 'mold'
                  AND resource_key = :resource_key
            """), {"reservation_date": reservation_date, "resource_key": key_code}).scalar_one() or 0)
            base_available = total_count - int(row.get("production_count") or 0) - int(row.get("breakdown_count") or 0) - int(row.get("planning_reserved_count") or 0)
            return max(0, base_available - reserved_count - reserved_from_db)
        except Exception:
            return 0

    def _available_casing_count(self, conn, casing_type: str, reservation_date: date, planning_version: int) -> int:
        if not casing_type:
            return 0
        try:
            row = conn.execute(text("""
                SELECT COALESCE(total_casing_count, 0) AS total_count,
                       COALESCE(available_casing_count, 0) AS available_count,
                       COALESCE(production_casing_count, 0) AS production_count,
                       COALESCE(breakdown_casing_count, 0) AS breakdown_count,
                       COALESCE(planning_reserved_casing_count, 0) AS planning_reserved_count
                FROM casing_master
                WHERE LOWER(TRIM(casing_type)) = LOWER(TRIM(:casing_type))
                LIMIT 1
            """), {"casing_type": casing_type}).mappings().first()
            if row:
                base_count = int(row.get("available_count") or row.get("total_count") or 0)
            else:
                base_count = int(conn.execute(text("""
                    SELECT COUNT(*)
                    FROM casing_units
                    WHERE LOWER(TRIM(casing_type)) = LOWER(TRIM(:casing_type))
                      AND LOWER(COALESCE(condition_status, 'Active')) = 'active'
                      AND LOWER(COALESCE(stock_status, 'Free')) = 'free'
                """), {"casing_type": casing_type}).scalar_one() or 0)
            reserved_count = self._resource_usage.get((reservation_date, "casing", casing_type), 0)
            reserved_from_db = int(conn.execute(text("""
                SELECT COALESCE(SUM(reserved_qty), 0)
                FROM planning_resource_reservations
                WHERE reservation_date = :reservation_date
                  AND resource_type = 'casing'
                  AND resource_key = :resource_key
            """), {"reservation_date": reservation_date, "resource_key": casing_type}).scalar_one() or 0)
            return max(0, base_count - reserved_count - reserved_from_db)
        except Exception:
            return 0

    def _available_line_cavity_count(self, conn, line_name: str, reservation_date: date, planning_version: int) -> int:
        if not line_name:
            return 0
        try:
            total = int(conn.execute(text("""
                SELECT COUNT(*)
                FROM production_line_cavities
                WHERE LOWER(TRIM(line_name)) = LOWER(TRIM(:line_name))
                  AND LOWER(COALESCE(status, 'Active')) = 'active'
                  AND TRIM(COALESCE(assigned_tyre_item, '')) = ''
            """), {"line_name": line_name}).scalar_one() or 0)
            reserved_count = self._resource_usage.get((reservation_date, "line_cavity", line_name), 0)
            reserved_from_db = int(conn.execute(text("""
                SELECT COALESCE(SUM(reserved_qty), 0)
                FROM planning_resource_reservations
                WHERE reservation_date = :reservation_date
                  AND resource_type = 'line_cavity'
                  AND resource_key = :resource_key
            """), {"reservation_date": reservation_date, "resource_key": line_name}).scalar_one() or 0)
            return max(0, total - reserved_count - reserved_from_db)
        except Exception:
            return 0

    def _evaluate_shipment_status(self, item_statuses: list[str], target_date: date | None) -> str:
        if not item_statuses:
            return "Planned"
        if all(status == "Blocked" for status in item_statuses):
            return "Blocked"
        if any(status == "Blocked" for status in item_statuses):
            return "Partially Blocked"
        if target_date is None:
            return "Flexible / No Target Date"
        return "Planned"

    def _evaluate_delivery_status(self, target_date: date | None, factory_can_receive_date: date | None) -> str:
        if target_date is None:
            return "Flexible / No Target Date"
        if factory_can_receive_date is None:
            return "Pending"
        if factory_can_receive_date < target_date:
            return "Can Deliver Early"
        if factory_can_receive_date == target_date:
            return "On Time"
        return "Delayed"


FactoryOutDateCalculator = FactoryPlanningEngine

