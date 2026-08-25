from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from math import ceil
from typing import Any

from sqlalchemy import Date, bindparam, text

from app.database import engine
from app.services.process_standard_resolution import (
    process_standard_complete,
    resolve_process_standard_from_connection,
)
from app.services.factory_resource_intelligence_service import (
    FactoryResourceIntelligenceService,
)

from app.services.master_data_normalization import (
    is_no_casing,
    normalize_casing_type,
    normalize_line_name,
    normalize_mold_key,
    normalize_sap_code,
    resource_identity,
    resource_key as canonical_resource_key,
)

OPEN_SHIPMENT_STATUSES = {"planned", "pending", "open", "saved", "in progress", "processing", ""}
# DELIVERY DATE INTEGRITY V6.3: no partial blocked resource reservations
# DELIVERY DATE INTEGRITY V6.3: no fabricated shipment receive dates
CLOSED_SHIPMENT_STATUSES = {"cancelled", "canceled", "closed", "complete", "completed", "shipped", "done", "draft", "draft import", "imported review", "review required", "on hold", "hold", "excel review hold"}
NO_CASING_VALUES = {"", "-", "no casing", "none", "n/a", "na", "not required"}

# AUTO FACTORY-OUT TARGET SCHEDULING V6.4
# PROCESS STANDARD PLANNING INTEGRITY V6.5
AUTO_TARGET_SOURCE = "Auto Earliest Feasible Factory Out"
AUTO_TARGET_SOURCE_VALUES = {
    "auto earliest feasible factory out",
    "automatic factory receive",
    "automatic factory out",
    "auto factory receive",
    "auto factory out",
    "auto suggested",
    "auto target",
}


def is_auto_target_source(value: Any) -> bool:
    normalized = str(value or "").strip().lower()
    return (
        not normalized
        or normalized in AUTO_TARGET_SOURCE_VALUES
        or normalized.startswith("auto ")
        or normalized.startswith("automatic ")
    )


def shipment_target_is_locked(shipment: dict[str, Any]) -> bool:
    if bool(shipment.get("target_date_is_manual")):
        return True
    if shipment.get("target_date") is None:
        return False
    return not is_auto_target_source(
        shipment.get("target_date_source")
    )


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
        self._preview_mode = False
        self._ignore_database_reservations = False

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
                    target_date_is_manual BOOLEAN NOT NULL DEFAULT FALSE,
                    target_date_source VARCHAR(80) NOT NULL DEFAULT 'Auto Earliest Feasible Factory Out',
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
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS target_date_is_manual BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS target_date_source VARCHAR(80) NOT NULL DEFAULT 'Auto Earliest Feasible Factory Out'",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS plan_date DATE",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS factory_can_receive_date DATE",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS factory_out_date DATE",
                "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS dispatch_buffer_days INTEGER NOT NULL DEFAULT 0",
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

            # V11 capacity intelligence schema is part of planning preflight so
            # operational callers can use one resolver without per-item DDL.
            FactoryResourceIntelligenceService.ensure_schema(conn)

    def replan_all_open_shipments(self, trigger_reason: str = "", created_by: str = "") -> PlanningRunResult:
        planning_version = int(datetime.utcnow().timestamp() * 1000)
        self._resource_usage.clear()
        self._preview_mode = False
        self._ignore_database_reservations = True
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
                SELECT
                    id,
                    shipment_no,
                    shipment_name,
                    customer_name,
                    shipment_date,
                    target_date,
                    plan_date,
                    status,
                    created_at,
                    note,
                    COALESCE(shipment_name, '') AS shipment_label,
                    COALESCE(target_date_is_manual, FALSE)
                        AS target_date_is_manual,
                    COALESCE(
                        NULLIF(target_date_source, ''),
                        :auto_target_source
                    ) AS target_date_source,
                    GREATEST(
                        0,
                        COALESCE(dispatch_buffer_days, 0)
                    ) AS dispatch_buffer_days
                FROM mpps_shipments
                WHERE COALESCE(LOWER(status), 'planned') NOT IN (
                    'cancelled',
                    'canceled',
                    'closed',
                    'complete',
                    'completed',
                    'shipped',
                    'done',
                    'draft',
                    'draft import',
                    'imported review',
                    'review required',
                    'on hold',
                    'hold',
                    'excel review hold'
                )
                ORDER BY
                    CASE
                        WHEN COALESCE(target_date_is_manual, FALSE)
                        THEN 0
                        WHEN target_date IS NOT NULL
                         AND LOWER(
                                COALESCE(target_date_source, '')
                             ) NOT LIKE 'auto%%'
                         AND LOWER(
                                COALESCE(target_date_source, '')
                             ) NOT LIKE 'automatic%%'
                        THEN 0
                        ELSE 1
                    END,
                    CASE
                        WHEN COALESCE(target_date_is_manual, FALSE)
                          OR (
                                target_date IS NOT NULL
                            AND LOWER(
                                    COALESCE(target_date_source, '')
                                ) NOT LIKE 'auto%%'
                            AND LOWER(
                                    COALESCE(target_date_source, '')
                                ) NOT LIKE 'automatic%%'
                          )
                        THEN COALESCE(
                            target_date,
                            DATE '9999-12-31'
                        )
                        ELSE DATE '9999-12-31'
                    END,
                    COALESCE(created_at, CURRENT_TIMESTAMP),
                    id
            """), {"auto_target_source": AUTO_TARGET_SOURCE})
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
                all_positive_items_dated = True

                for item in items:
                    item_id = int(item["id"])
                    sap_code = normalize_sap_code(
                        item.get("sap_code")
                    )
                    order_qty = max(0, int(item.get("quantity") or 0))
                    produced_qty = max(0, int(item.get("produced_qty") or 0))
                    total_qty += order_qty
                    if sap_code not in stock_remaining_by_sap:
                        stock_remaining_by_sap[sap_code] = self._get_available_stock(conn, sap_code)

                    stock_need = max(order_qty - produced_qty, 0)
                    stock_allocated_qty = min(stock_need, max(0, stock_remaining_by_sap[sap_code]))
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
                    latest_item_date = (
                        planned_item.item_receive_date
                        if (
                            planned_item.item_receive_date is not None
                            and (
                                latest_item_date is None
                                or planned_item.item_receive_date
                                    > latest_item_date
                            )
                        )
                        else latest_item_date
                    )
                    if (
                        order_qty > 0
                        and planned_item.item_receive_date is None
                    ):
                        all_positive_items_dated = False
                    item_statuses.append(planned_item.item_status)
                    if planned_item.item_status == "Blocked":
                        shipment_note_parts.append(f"{sap_code}: {planned_item.schedule_reason}")

                # A shipment-level receive date is valid only when every
                # positive-quantity item has a verified receive date. Never
                # substitute shipment_date, target_date, plan_date, or today for
                # an unresolved item schedule.
                factory_can_receive_date = (
                    latest_item_date
                    if item_results and all_positive_items_dated
                    else None
                )

                target_locked = shipment_target_is_locked(
                    shipment
                )
                auto_target = not target_locked
                dispatch_buffer_days = max(
                    0,
                    int(
                        shipment.get(
                            "dispatch_buffer_days"
                        )
                        or 0
                    ),
                )
                factory_out_date = (
                    factory_can_receive_date
                    + timedelta(
                        days=dispatch_buffer_days
                    )
                    if factory_can_receive_date
                    is not None
                    else None
                )
                effective_target_date = (
                    shipment.get("target_date")
                    if target_locked
                    else factory_out_date
                )
                target_source = (
                    str(
                        shipment.get(
                            "target_date_source"
                        )
                        or ""
                    ).strip()
                    if target_locked
                    else AUTO_TARGET_SOURCE
                )
                target_is_manual = bool(
                    shipment.get(
                        "target_date_is_manual"
                    )
                ) if target_locked else False

                shipment_status = (
                    self._evaluate_shipment_status(
                        item_statuses,
                        effective_target_date,
                    )
                )
                planning_status = shipment_status
                if (
                    auto_target
                    and shipment_status == "Planned"
                ):
                    planning_status = "Auto Planned"

                if auto_target:
                    if factory_out_date is not None:
                        delivery_status = "Auto Scheduled"
                    elif "blocked" in shipment_status.lower():
                        delivery_status = "Blocked"
                    else:
                        delivery_status = "Pending Planning"
                else:
                    delivery_status = self._evaluate_delivery_status(
                        effective_target_date,
                        factory_out_date,
                    )

                delay_days = 0
                early_days = 0
                if (
                    target_locked
                    and effective_target_date is not None
                    and factory_out_date is not None
                ):
                    if factory_out_date < effective_target_date:
                        early_days = (
                            effective_target_date
                            - factory_out_date
                        ).days
                    elif factory_out_date > effective_target_date:
                        delay_days = (
                            factory_out_date
                            - effective_target_date
                        ).days

                progress_pct = round((completed_qty / total_qty * 100) if total_qty else 0.0, 2)
                if shipment_note_parts:
                    planning_note = "; ".join(shipment_note_parts)
                elif factory_can_receive_date is None:
                    planning_note = (
                        "Planning is incomplete. Factory receive and factory-out "
                        "dates remain pending until every positive-quantity item "
                        "has a verified receive date."
                    )
                elif auto_target:
                    planning_note = (
                        "Auto Target was set to the earliest feasible Factory "
                        "Can Out date after cumulative stock, mold, casing and "
                        "cavity planning."
                    )
                else:
                    planning_note = (
                        "Planned within cumulative shipment priority and "
                        "available capacity."
                    )

                stmt = text("""
                    UPDATE mpps_shipments
                    SET target_date = :target_date,
                        plan_date = COALESCE(:plan_date, :plan_date_fallback),
                        target_date_is_manual = :target_date_is_manual,
                        target_date_source = :target_date_source,
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
                    "target_date": effective_target_date,
                    "plan_date": effective_target_date,
                    "plan_date_fallback": (
                        effective_target_date
                        or shipment.get("shipment_date")
                    ),
                    "target_date_is_manual": target_is_manual,
                    "target_date_source": target_source,
                    "factory_can_receive_date": factory_can_receive_date,
                    "factory_out_date": factory_out_date,
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
                    target_date=effective_target_date,
                    plan_date=effective_target_date,
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

        self._ignore_database_reservations = False
        return PlanningRunResult(planning_run_id=run_id, planning_version=planning_version, status="Completed", message="Planning completed", shipments=shipment_results)

    def replan_single_shipment_preview(self, shipment_id: int) -> ShipmentPlanResult:
        result = self.replan_all_open_shipments(trigger_reason=f"single_shipment_{shipment_id}", created_by="ui")
        for shipment in result.shipments:
            if shipment.shipment_id == shipment_id:
                return shipment
        raise ValueError(f"Shipment {shipment_id} was not found in planning output.")

    def calculate_cart_items(
        self,
        cart_items: list[dict[str, Any]],
        target_date: date | None = None,
        exclude_shipment_id: int | None = None,
        target_date_is_manual: bool | None = None,
        draft_created_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Preview a draft inside the complete active shipment queue."""
        manual_target = (
            bool(target_date_is_manual)
            if target_date_is_manual is not None
            else target_date is not None
        )
        self._resource_usage.clear()
        previous_preview_mode = self._preview_mode
        previous_ignore_mode = self._ignore_database_reservations
        self._preview_mode = True
        self._ignore_database_reservations = True
        try:
            with engine.begin() as conn:
                params: dict[str, Any] = {}
                exclude_sql = ""
                if exclude_shipment_id:
                    params["exclude_shipment_id"] = int(exclude_shipment_id)
                    exclude_sql = "AND shipment.id <> :exclude_shipment_id"

                existing_rows = conn.execute(text(f"""
                    SELECT
                        shipment.id,
                        shipment.shipment_no,
                        shipment.shipment_name,
                        shipment.customer_name,
                        shipment.shipment_date,
                        shipment.target_date,
                        shipment.plan_date,
                        shipment.status,
                        shipment.created_at,
                        shipment.note,
                        COALESCE(
                            shipment.target_date_is_manual,
                            CASE
                                WHEN shipment.target_date IS NOT NULL
                                 AND (
                                    shipment.factory_can_receive_date IS NULL
                                    OR shipment.target_date <> shipment.factory_can_receive_date
                                 )
                                THEN TRUE
                                ELSE FALSE
                            END
                        ) AS target_date_is_manual
                    FROM mpps_shipments shipment
                    WHERE COALESCE(LOWER(shipment.status), 'planned') NOT IN (
                        'cancelled', 'canceled', 'closed', 'complete',
                        'completed', 'shipped', 'done',
                        'draft', 'draft import', 'imported review',
                        'review required', 'on hold', 'hold',
                        'excel review hold'
                    )
                    {exclude_sql}
                """), params).mappings().all()

                queue: list[dict[str, Any]] = []
                for raw_shipment in existing_rows:
                    shipment = dict(raw_shipment)
                    items = conn.execute(text("""
                        SELECT id, sap_code, item_description, quantity, produced_qty
                        FROM mpps_shipment_items
                        WHERE shipment_id = :shipment_id
                        ORDER BY id
                    """), {"shipment_id": int(shipment["id"])}).mappings().all()
                    shipment["_items"] = [dict(item) for item in items]
                    shipment["_is_draft"] = False
                    queue.append(shipment)

                queue.append({
                    "id": 0,
                    "shipment_no": "DRAFT",
                    "shipment_name": "Current Draft",
                    "customer_name": "",
                    "shipment_date": self.start_date,
                    "target_date": target_date if manual_target else None,
                    "plan_date": target_date if manual_target else None,
                    "status": "Planned",
                    "created_at": (
                        draft_created_at
                        or datetime.max
                    ),
                    "note": "",
                    "target_date_is_manual": manual_target,
                    "_items": [
                        {
                            "id": None,
                            "sap_code": normalize_sap_code(
                                item.get("sap_code")
                            ),
                            "item_description": str(
                                item.get("item_description")
                                or item.get("description")
                                or ""
                            ),
                            "quantity": max(0, int(item.get("quantity") or item.get("order_qty") or 0)),
                            "produced_qty": max(
                                0,
                                int(
                                    item.get(
                                        "produced_qty"
                                    )
                                    or 0
                                ),
                            ),
                            "_source": item,
                        }
                        for item in cart_items
                    ],
                    "_is_draft": True,
                })
                queue.sort(key=self._shipment_priority_sort_key)

                stock_remaining_by_sap: dict[str, int] = {}
                draft_results: list[dict[str, Any]] = []
                for shipment in queue:
                    for item in shipment["_items"]:
                        sap_code = normalize_sap_code(
                            item.get("sap_code")
                        )
                        order_qty = max(0, int(item.get("quantity") or 0))
                        produced_qty = max(0, int(item.get("produced_qty") or 0))
                        if sap_code not in stock_remaining_by_sap:
                            stock_remaining_by_sap[sap_code] = self._get_available_stock(conn, sap_code)
                        stock_need = max(order_qty - produced_qty, 0)
                        stock_allocated_qty = min(
                            stock_need,
                            max(0, stock_remaining_by_sap[sap_code]),
                        )
                        stock_remaining_by_sap[sap_code] = max(
                            0,
                            stock_remaining_by_sap[sap_code] - stock_allocated_qty,
                        )
                        result = self._plan_shipment_item(
                            conn=conn,
                            run_id=None,
                            planning_version=0,
                            shipment=shipment,
                            shipment_item_id=(int(item["id"]) if item.get("id") is not None else None),
                            sap_code=sap_code,
                            description=str(item.get("item_description") or ""),
                            order_qty=order_qty,
                            stock_allocated_qty=stock_allocated_qty,
                            produced_qty=produced_qty,
                            preview=True,
                        )
                        if not shipment["_is_draft"]:
                            continue
                        source_item = dict(item.get("_source") or {})
                        source_item.update({
                            "sap_code": sap_code,
                            "description": result.description,
                            "item_description": result.description or str(item.get("item_description") or ""),
                            "order_qty": result.order_qty,
                            "quantity": result.order_qty,
                            "stock_allocated_qty": result.stock_allocated_qty,
                            "production_required_qty": result.remaining_qty,
                            "allocated_cavity_count": result.allocated_cavity_count,
                            "daily_capacity": result.daily_capacity,
                            "production_days": result.production_days,
                            "receive_date": result.item_receive_date,
                            "item_receive_date": result.item_receive_date,
                            "status": result.item_status,
                            "item_status": result.item_status,
                            "reason": result.schedule_reason or result.factory_out_reason,
                            "schedule_reason": result.schedule_reason or result.factory_out_reason,
                            "priority_preview": True,
                        })
                        draft_results.append(source_item)
                return draft_results
        finally:
            self._preview_mode = previous_preview_mode
            self._ignore_database_reservations = previous_ignore_mode

    def _shipment_priority_sort_key(
        self,
        shipment: dict[str, Any],
    ) -> tuple[Any, ...]:
        target_locked = shipment_target_is_locked(
            shipment
        )
        target = shipment.get("target_date")
        created = shipment.get("created_at") or datetime.max
        shipment_id = int(shipment.get("id") or 0)
        if target_locked:
            return (
                0,
                target or date.max,
                created,
                shipment_id,
            )
        return (
            1,
            date.max,
            created,
            shipment_id,
        )

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

        # V10.4: approval status no longer gates production planning.  Keep the
        # SMDS field for audit/UI history, but calculate from actual stock,
        # process standards and physical capacity.

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
        # V11: real learned capacity is the primary production-rate source.
        # The legacy SMDS total_plan remains a technical fallback/reference.
        line_hint = normalize_line_name(smds.get("line"))
        learned_capacity = FactoryResourceIntelligenceService.resolve_capacity(
            conn,
            sap_code,
            on_date=self.start_date,
            line_name=line_hint,
            ensure_schema=False,
        )
        stable_cavities = max(0, int(learned_capacity.stable_cavity_count or 0))
        learned_per_cavity = 0.0
        if learned_capacity.safe_capacity > 0:
            if stable_cavities > 0:
                learned_per_cavity = learned_capacity.safe_capacity / stable_cavities
            elif total_plan > 0:
                # With no learned stable-cavity count, never inflate the technical
                # per-cavity standard; use learned evidence as a conservative cap.
                learned_per_cavity = min(float(total_plan), float(learned_capacity.safe_capacity))
            else:
                learned_per_cavity = float(learned_capacity.safe_capacity)

        effective_per_cavity = learned_per_cavity if learned_per_cavity > 0 else total_plan
        smds["_v11_effective_per_cavity"] = effective_per_cavity
        smds["_v11_capacity_source"] = learned_capacity.source
        smds["_v11_capacity_confidence"] = learned_capacity.confidence_score
        smds["_v11_stable_cavities"] = stable_cavities
        smds["_v11_available_capacity"] = learned_capacity.available_capacity

        if effective_per_cavity <= 0:
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
                schedule_reason=(
                    "No learned real-capacity evidence or usable technical "
                    "capacity is available for this SAP. Import historical OVEN "
                    "plans/PROD actuals or maintain a technical baseline."
                ),
                factory_out_reason=(
                    "No learned or technical production-capacity evidence is available."
                ),
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
        total_plan = max(
            0.0,
            float(
                smds.get("_v11_effective_per_cavity")
                or smds.get("total_plan")
                or 0
            ),
        )
        capacity_source = str(smds.get("_v11_capacity_source") or "TECHNICAL")
        capacity_confidence = float(smds.get("_v11_capacity_confidence") or 0.0)
        stable_cavity_hint = max(0, int(smds.get("_v11_stable_cavities") or 0))
        mold_key = normalize_mold_key(
            smds.get("key_code"),
        )
        casing_type = normalize_casing_type(
            smds.get("casing_type"),
        )
        line_name = normalize_line_name(
            smds.get("line"),
        )
        sap_code = normalize_sap_code(
            sap_code
        )
        casing_required = not is_no_casing(
            casing_type
        )

        current_date = self.start_date
        allocation_total = 0
        allocated_cavity_count = 0
        production_days = 0
        daily_capacity = 0
        receive_date = None
        reason = ""
        tentative_allocations: list[
            tuple[date, int, int]
        ] = []

        mold_available_on_any_day = False
        casing_available_on_any_day = (
            not casing_required
        )
        line_available_on_any_day = False
        combined_capacity_on_any_day = False
        maximum_combined_cavities = 0

        for day_offset in range(
            self.planning_horizon_days + 1
        ):
            candidate_date = current_date + timedelta(days=day_offset)
            available_mold = self._available_mold_count(conn, mold_key, candidate_date, planning_version)
            available_casing = float("inf") if not casing_required else self._available_casing_count(conn, casing_type, candidate_date, planning_version)
            available_line = (
                self._available_line_cavity_count(
                    conn,
                    line_name,
                    candidate_date,
                    planning_version,
                )
            )

            mold_available_on_any_day = (
                mold_available_on_any_day
                or available_mold > 0
            )
            line_available_on_any_day = (
                line_available_on_any_day
                or available_line > 0
            )

            if casing_required:
                casing_available_on_any_day = (
                    casing_available_on_any_day
                    or available_casing > 0
                )

            available_resource_cavities = (
                int(
                    min(
                        available_mold,
                        available_casing,
                        available_line,
                    )
                )
                if available_casing != float("inf")
                else int(
                    min(
                        available_mold,
                        available_line,
                    )
                )
            )

            maximum_combined_cavities = max(
                maximum_combined_cavities,
                available_resource_cavities,
            )
            combined_capacity_on_any_day = (
                combined_capacity_on_any_day
                or available_resource_cavities > 0
            )

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
            receive_date = (
                candidate_date
                + timedelta(days=1)
            )
            tentative_allocations.append(
                (
                    candidate_date,
                    allocated_cavities,
                    daily_capacity,
                )
            )
            remaining_qty -= daily_production_qty
            if remaining_qty <= 0:
                break
        completed_qty = min(order_qty, stock_allocated_qty + produced_qty)
        if remaining_qty > 0:
            horizon_days = (
                self.planning_horizon_days + 1
            )

            if not mold_key:
                reason = (
                    "SMDS mold/key code is missing. "
                    "Assign the correct mold key code "
                    f"for SAP {sap_code}."
                )
            elif not line_name:
                reason = (
                    "SMDS compatible production line "
                    "is missing. Assign at least one "
                    f"production line for SAP {sap_code}."
                )
            elif not mold_available_on_any_day:
                reason = (
                    "No mold capacity is available for "
                    f"key code '{mold_key}' during the "
                    f"{horizon_days}-day planning horizon. "
                    "The mold is missing, inactive, or "
                    "fully reserved by higher-priority "
                    "shipments."
                )
            elif (
                casing_required
                and not casing_available_on_any_day
            ):
                reason = (
                    "No casing capacity is available for "
                    f"type '{casing_type}' during the "
                    f"{horizon_days}-day planning horizon. "
                    "The casing is missing, inactive, or "
                    "fully reserved by higher-priority "
                    "shipments."
                )
            elif not line_available_on_any_day:
                reason = (
                    "No compatible active cavity capacity "
                    f"is available for line(s) '{line_name}' "
                    f"during the {horizon_days}-day "
                    "planning horizon. The cavities are "
                    "missing, inactive, in breakdown, "
                    "assigned, or fully reserved."
                )
            elif not combined_capacity_on_any_day:
                resource_names = (
                    "mold, casing and cavity"
                    if casing_required
                    else "mold and cavity"
                )
                reason = (
                    f"The required {resource_names} "
                    "resources are not available together "
                    "on the same production date during "
                    f"the {horizon_days}-day planning "
                    "horizon."
                )
            else:
                reason = (
                    "The available combined capacity is "
                    "insufficient to complete this item "
                    f"within the {horizon_days}-day "
                    "planning horizon. "
                    f"Unplanned quantity: "
                    f"{int(remaining_qty)}. "
                    f"Maximum simultaneous cavities "
                    f"found: "
                    f"{maximum_combined_cavities}."
                )

            item_status = "Blocked"
            receive_date = None
            allocated_cavity_count = 0
            daily_capacity = 0
            production_days = 0
        else:
            # Commit resource reservations only after the whole production
            # requirement is feasible. A blocked/partial schedule must not
            # consume mold, casing, or cavity capacity.
            for (
                reservation_date,
                reservation_cavities,
                reservation_daily_capacity,
            ) in tentative_allocations:
                self._reserve_resource(
                    conn,
                    run_id,
                    planning_version,
                    shipment,
                    shipment_item_id,
                    reservation_date,
                    "mold",
                    mold_key,
                    reservation_cavities,
                    reservation_daily_capacity,
                    sap_code,
                    description,
                )
                self._reserve_resource(
                    conn,
                    run_id,
                    planning_version,
                    shipment,
                    shipment_item_id,
                    reservation_date,
                    "line_cavity",
                    line_name,
                    reservation_cavities,
                    reservation_daily_capacity,
                    sap_code,
                    description,
                )
                if casing_required:
                    self._reserve_resource(
                        conn,
                        run_id,
                        planning_version,
                        shipment,
                        shipment_item_id,
                        reservation_date,
                        "casing",
                        casing_type,
                        reservation_cavities,
                        reservation_daily_capacity,
                        sap_code,
                        description,
                    )

            item_status = "Planned"
            reason = (
                "Planned within physical resource limits using "
                f"{capacity_source} capacity"
                + (
                    f" ({capacity_confidence * 100:.0f}% confidence)"
                    if capacity_confidence > 0 else ""
                )
                + (
                    f"; learned stable cavity setup {stable_cavity_hint}."
                    if stable_cavity_hint > 0 else "."
                )
            )
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

    def _reserve_resource(
        self,
        conn,
        run_id: int | None,
        planning_version: int,
        shipment: dict[str, Any],
        shipment_item_id: int | None,
        reservation_date: date,
        resource_type: str,
        resource_key: str,
        reserved_qty: int,
        capacity_qty: int,
        sap_code: str,
        note: str,
    ) -> None:
        if reserved_qty <= 0:
            return

        canonical_key = canonical_resource_key(
            resource_type,
            resource_key,
        )
        identity = resource_identity(
            resource_type,
            canonical_key,
        )
        usage_key = (
            reservation_date,
            resource_type,
            identity,
        )
        self._resource_usage[usage_key] = int(
            self._resource_usage.get(
                usage_key,
                0,
            )
        ) + reserved_qty

        if (
            self._preview_mode
            or shipment_item_id is None
        ):
            return

        conn.execute(
            text(
                """
                INSERT INTO planning_resource_reservations (
                    planning_run_id,
                    planning_version,
                    shipment_id,
                    shipment_item_id,
                    reservation_date,
                    resource_type,
                    resource_key,
                    reserved_qty,
                    capacity_qty,
                    sap_code,
                    note
                )
                VALUES (
                    :planning_run_id,
                    :planning_version,
                    :shipment_id,
                    :shipment_item_id,
                    :reservation_date,
                    :resource_type,
                    :resource_key,
                    :reserved_qty,
                    :capacity_qty,
                    :sap_code,
                    :note
                )
                """
            ),
            {
                "planning_run_id": run_id,
                "planning_version": planning_version,
                "shipment_id": int(
                    shipment.get("id") or 0
                ),
                "shipment_item_id": shipment_item_id,
                "reservation_date": reservation_date,
                "resource_type": resource_type,
                "resource_key": canonical_key,
                "reserved_qty": reserved_qty,
                "capacity_qty": capacity_qty,
                "sap_code": normalize_sap_code(
                    sap_code
                ),
                "note": note,
            },
        )

    def _load_smds_item(
        self,
        conn,
        sap_code: str,
    ) -> dict[str, Any] | None:
        canonical_sap = normalize_sap_code(
            sap_code
        )
        try:
            row = conn.execute(
                text(
                    """
                    SELECT
                        sap_code,
                        material_description,
                        key_code,
                        casing_type,
                        line,
                        day_plan,
                        night_plan,
                        total_plan,
                        curing_cycle,
                        normal_curing_minutes,
                        normal_curing_time_text,
                        handling_time,
                        planning_manager_approval_status,
                        planning_manager_approval_note,
                        planning_manager_approved_at,
                        manager_approval_updated_at,
                        process_standard_source,
                        process_standard_confidence,
                        process_standard_peer_count
                    FROM smds
                    WHERE mpps_identifier_key(sap_code)
                        = mpps_identifier_key(:sap_code)
                    LIMIT 1
                    """
                ),
                {"sap_code": canonical_sap},
            ).mappings().first()

            if not row:
                return None

            result = dict(row)
            result["sap_code"] = normalize_sap_code(
                result.get("sap_code")
            )
            result["key_code"] = normalize_mold_key(
                result.get("key_code")
            )
            result["casing_type"] = (
                normalize_casing_type(
                    result.get("casing_type")
                )
            )
            result["line"] = normalize_line_name(
                result.get("line")
            )

            if not process_standard_complete(result):
                resolution = resolve_process_standard_from_connection(
                    conn,
                    result,
                )
                if resolution:
                    result.update(
                        resolution.as_smds_values()
                    )
                    result[
                        "process_standard_runtime_inferred"
                    ] = True

            return result
        except Exception:
            return None

    def _get_available_stock(
        self,
        conn,
        sap_code: str,
        exclude_shipment_id: int | None = None,
    ) -> int:
        canonical_sap = normalize_sap_code(sap_code)
        try:
            current_table = bool(
                conn.execute(
                    text("SELECT to_regclass('public.mpps_current_stock_snapshots') IS NOT NULL")
                ).scalar()
            )
            latest_run_id = None
            if current_table:
                latest_run_id = conn.execute(
                    text("SELECT MAX(import_run_id) FROM mpps_current_stock_snapshots")
                ).scalar()
            if latest_run_id is not None:
                stock = conn.execute(
                    text(
                        """
                        SELECT GREATEST(COALESCE(current_stock,0),0)
                        FROM mpps_current_stock_snapshots
                        WHERE UPPER(TRIM(sap_code))=UPPER(TRIM(:sap_code))
                          AND import_run_id=:run_id
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    ),
                    {"sap_code": canonical_sap, "run_id": latest_run_id},
                ).scalar_one_or_none()
                # Missing SAP in the authoritative snapshot is treated as zero.
                return max(0, int(stock or 0))

            stock = conn.execute(
                text(
                    """
                    SELECT
                        COALESCE(fg_stock, 0)
                        + COALESCE(qc_stock, 0)
                        - COALESCE(scrap_stock, 0)
                        - COALESCE(blocked_stock, 0)
                            AS available_qty
                    FROM mpps_sap_stock_items
                    WHERE mpps_identifier_key(sap_code)
                        = mpps_identifier_key(:sap_code)
                    LIMIT 1
                    """
                ),
                {"sap_code": canonical_sap},
            ).scalar_one_or_none()
            return max(0, int(stock or 0))
        except Exception:
            return 0

    def _available_mold_count(
        self,
        conn,
        key_code: str,
        reservation_date: date,
        planning_version: int,
    ) -> int:
        canonical_key = normalize_mold_key(
            key_code
        )
        if canonical_key == "-":
            return 0

        identity = resource_identity(
            "mold",
            canonical_key,
        )

        try:
            row = conn.execute(
                text(
                    """
                    SELECT
                        COALESCE(mold_count, 0)
                            AS total_count,
                        COALESCE(
                            production_mold_count,
                            0
                        ) AS production_count,
                        COALESCE(
                            breakdown_mold_count,
                            0
                        ) AS breakdown_count,
                        COALESCE(
                            planning_reserved_mold_count,
                            0
                        ) AS planning_reserved_count
                    FROM mold_master
                    WHERE mpps_identifier_key(
                            mold_key_code
                          )
                        = mpps_identifier_key(
                            :key_code
                          )
                      AND LOWER(
                            COALESCE(
                                status,
                                'Active'
                            )
                          ) = 'active'
                      AND COALESCE(
                            is_active,
                            TRUE
                          ) = TRUE
                    LIMIT 1
                    """
                ),
                {"key_code": canonical_key},
            ).mappings().first()

            if not row:
                return 0

            total_count = int(
                row.get("total_count") or 0
            )
            usage_key = (
                reservation_date,
                "mold",
                identity,
            )
            reserved_count = int(
                self._resource_usage.get(
                    usage_key,
                    0,
                )
            )
            reserved_from_db = 0

            if not self._ignore_database_reservations:
                reserved_from_db = int(
                    conn.execute(
                        text(
                            """
                            SELECT
                                COALESCE(
                                    SUM(reserved_qty),
                                    0
                                )
                            FROM
                                planning_resource_reservations
                            WHERE reservation_date
                                    = :reservation_date
                              AND resource_type = 'mold'
                              AND mpps_identifier_key(
                                    resource_key
                                  )
                                  = mpps_identifier_key(
                                    :resource_key
                                  )
                            """
                        ),
                        {
                            "reservation_date": (
                                reservation_date
                            ),
                            "resource_key": canonical_key,
                        },
                    ).scalar_one()
                    or 0
                )

            base_available = (
                total_count
                - int(
                    row.get("production_count")
                    or 0
                )
                - int(
                    row.get("breakdown_count")
                    or 0
                )
                - int(
                    row.get(
                        "planning_reserved_count"
                    )
                    or 0
                )
            )
            return max(
                0,
                base_available
                - reserved_count
                - reserved_from_db,
            )
        except Exception:
            return 0

    def _available_casing_count(
        self,
        conn,
        casing_type: str,
        reservation_date: date,
        planning_version: int,
    ) -> int:
        canonical_type = normalize_casing_type(
            casing_type
        )
        if is_no_casing(canonical_type):
            return 0
        if canonical_type == "-":
            return 0

        identity = resource_identity(
            "casing",
            canonical_type,
        )

        try:
            row = conn.execute(
                text(
                    """
                    SELECT
                        COALESCE(
                            total_casing_count,
                            0
                        ) AS total_count,
                        COALESCE(
                            available_casing_count,
                            0
                        ) AS available_count,
                        COALESCE(
                            production_casing_count,
                            0
                        ) AS production_count,
                        COALESCE(
                            breakdown_casing_count,
                            0
                        ) AS breakdown_count,
                        COALESCE(
                            planning_reserved_casing_count,
                            0
                        ) AS planning_reserved_count
                    FROM casing_master
                    WHERE mpps_identifier_key(
                            casing_type
                          )
                        = mpps_identifier_key(
                            :casing_type
                          )
                      AND LOWER(
                            COALESCE(
                                status,
                                'Active'
                            )
                          ) = 'active'
                      AND COALESCE(
                            is_active,
                            TRUE
                          ) = TRUE
                    LIMIT 1
                    """
                ),
                {"casing_type": canonical_type},
            ).mappings().first()

            if row:
                # available_casing_count is the physical
                # Active + Free count. Do not subtract
                # production/breakdown a second time.
                base_count = int(
                    row.get("available_count")
                    or 0
                )
            else:
                base_count = int(
                    conn.execute(
                        text(
                            """
                            SELECT COUNT(*)
                            FROM casing_units
                            WHERE mpps_identifier_key(
                                    casing_type
                                  )
                                = mpps_identifier_key(
                                    :casing_type
                                  )
                              AND LOWER(
                                    COALESCE(
                                        condition_status,
                                        'Active'
                                    )
                                  ) = 'active'
                              AND LOWER(
                                    COALESCE(
                                        stock_status,
                                        'Free'
                                    )
                                  ) = 'free'
                            """
                        ),
                        {"casing_type": canonical_type},
                    ).scalar_one()
                    or 0
                )

            usage_key = (
                reservation_date,
                "casing",
                identity,
            )
            reserved_count = int(
                self._resource_usage.get(
                    usage_key,
                    0,
                )
            )
            reserved_from_db = 0

            if not self._ignore_database_reservations:
                reserved_from_db = int(
                    conn.execute(
                        text(
                            """
                            SELECT
                                COALESCE(
                                    SUM(reserved_qty),
                                    0
                                )
                            FROM
                                planning_resource_reservations
                            WHERE reservation_date
                                    = :reservation_date
                              AND resource_type = 'casing'
                              AND mpps_identifier_key(
                                    resource_key
                                  )
                                  = mpps_identifier_key(
                                    :resource_key
                                  )
                            """
                        ),
                        {
                            "reservation_date": (
                                reservation_date
                            ),
                            "resource_key": canonical_type,
                        },
                    ).scalar_one()
                    or 0
                )

            return max(
                0,
                base_count
                - reserved_count
                - reserved_from_db,
            )
        except Exception:
            return 0

    def _available_line_cavity_count(
        self,
        conn,
        line_name: str,
        reservation_date: date,
        planning_version: int,
    ) -> int:
        canonical_line = normalize_line_name(
            line_name
        )
        if not canonical_line:
            return 0

        identity = resource_identity(
            "line_cavity",
            canonical_line,
        )

        try:
            total = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM production_line_cavities
                        WHERE mpps_line_key(line_name)
                            = mpps_line_key(:line_name)
                          AND LOWER(
                                COALESCE(
                                    status,
                                    'Active'
                                )
                              ) = 'active'
                          AND COALESCE(
                                is_active,
                                TRUE
                              ) = TRUE
                          AND TRIM(
                                COALESCE(
                                    assigned_tyre_item,
                                    ''
                                )
                              ) = ''
                        """
                    ),
                    {"line_name": canonical_line},
                ).scalar_one()
                or 0
            )
            usage_key = (
                reservation_date,
                "line_cavity",
                identity,
            )
            reserved_count = int(
                self._resource_usage.get(
                    usage_key,
                    0,
                )
            )
            reserved_from_db = 0

            if not self._ignore_database_reservations:
                reserved_from_db = int(
                    conn.execute(
                        text(
                            """
                            SELECT
                                COALESCE(
                                    SUM(reserved_qty),
                                    0
                                )
                            FROM
                                planning_resource_reservations
                            WHERE reservation_date
                                    = :reservation_date
                              AND resource_type
                                    = 'line_cavity'
                              AND mpps_line_key(
                                    resource_key
                                  )
                                  = mpps_line_key(
                                    :resource_key
                                  )
                            """
                        ),
                        {
                            "reservation_date": (
                                reservation_date
                            ),
                            "resource_key": canonical_line,
                        },
                    ).scalar_one()
                    or 0
                )

            return max(
                0,
                total
                - reserved_count
                - reserved_from_db,
            )
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


