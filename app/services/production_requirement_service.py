from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


ACTIVE_DEMAND_STATUSES = ("PENDING", "CONFIRMED", "PLANNED", "PARTIALLY_PLANNED")


@dataclass(frozen=True)
class ProductionRequirementRow:
    material_code: str
    item_description: str
    product_group: str
    capacity_key: str
    fg_stock: int
    qc_stock: int
    scrap_stock: int
    blocked_stock: int
    opening_available_stock: int
    confirmed_production_qty: int
    completed_shipment_qty: int
    available_stock_at_date: int
    eligible_shipment_demand: int
    shortage_qty: int
    production_required_qty: int
    unit_weight_kg: float
    production_required_tons: float
    earliest_due_date: date | None
    missing_due_date: bool
    missing_weight: bool
    negative_available_stock: bool
    status: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ProductionRequirementSummary:
    total_items: int
    ready_items: int
    production_required_items: int
    out_of_stock_items: int
    missing_weight_items: int
    missing_due_date_items: int
    missing_demand_items: int
    total_shortage_qty: int
    total_production_required_qty: int
    total_production_required_tons: float
    warning_count: int


def load_production_requirements(
    session: Session,
    *,
    planning_date: date,
    production_required_only: bool = False,
) -> list[ProductionRequirementRow]:
    status_params = {f"status_{i}": value for i, value in enumerate(ACTIVE_DEMAND_STATUSES)}
    status_sql = ", ".join(f":status_{i}" for i in range(len(ACTIVE_DEMAND_STATUSES)))
    params: dict[str, Any] = {"planning_date": planning_date, **status_params}

    sql = f"""
        WITH manual_demand AS (
            SELECT
                material_code,
                SUM(demand_qty)::INTEGER AS demand_qty,
                MIN(shipment_date) FILTER (WHERE shipment_date IS NOT NULL) AS earliest_due_date,
                COUNT(*) FILTER (WHERE shipment_date IS NULL)::INTEGER AS missing_due_dates
            FROM mpps_shipment_demand
            WHERE UPPER(status) IN ({status_sql})
              AND (shipment_date IS NULL OR shipment_date <= :planning_date)
              AND demand_qty > 0
            GROUP BY material_code
        ),
        combined_demand AS (
            SELECT
                material_code,
                SUM(demand_qty)::INTEGER AS demand_qty,
                MIN(earliest_due_date) AS earliest_due_date,
                SUM(missing_due_dates)::INTEGER AS missing_due_dates
            FROM manual_demand
            GROUP BY material_code
        )
        SELECT
            si.material_code,
            si.item_description,
            COALESCE(si.product_group, '-') AS product_group,
            COALESCE(si.bead_type, '') AS capacity_key,
            si.fg_stock,
            si.qc_stock,
            si.scrap_stock,
            si.blocked_stock,
            (si.fg_stock + si.qc_stock - si.scrap_stock - si.blocked_stock)::INTEGER
                AS opening_available_stock,
            0::INTEGER AS confirmed_production_qty,
            0::INTEGER AS completed_shipment_qty,
            (si.fg_stock + si.qc_stock - si.scrap_stock - si.blocked_stock)::INTEGER
                AS available_stock_at_date,
            COALESCE(cd.demand_qty, 0)::INTEGER AS eligible_shipment_demand,
            GREATEST(
                COALESCE(cd.demand_qty, 0)
                - GREATEST(si.fg_stock + si.qc_stock - si.scrap_stock - si.blocked_stock, 0),
                0
            )::INTEGER AS shortage_qty,
            COALESCE(si.average_weight, 0) AS unit_weight_kg,
            cd.earliest_due_date,
            COALESCE(cd.missing_due_dates, 0)::INTEGER AS missing_due_dates
        FROM mpps_stock_items si
        LEFT JOIN combined_demand cd ON cd.material_code = si.material_code
        WHERE si.is_active = TRUE
        ORDER BY
            GREATEST(
                COALESCE(cd.demand_qty, 0)
                - GREATEST(si.fg_stock + si.qc_stock - si.scrap_stock - si.blocked_stock, 0),
                0
            ) DESC,
            cd.earliest_due_date NULLS LAST,
            si.material_code;
    """

    mapped: list[ProductionRequirementRow] = []
    for raw in session.execute(text(sql), params).mappings():
        row = _map_requirement(raw)
        if production_required_only and row.production_required_qty <= 0:
            continue
        mapped.append(row)
    return mapped


def summarize_production_requirements(
    rows: list[ProductionRequirementRow],
) -> ProductionRequirementSummary:
    return ProductionRequirementSummary(
        total_items=len(rows),
        ready_items=sum(row.status == "READY" for row in rows),
        production_required_items=sum(row.production_required_qty > 0 for row in rows),
        out_of_stock_items=sum(row.status == "OUT OF STOCK" for row in rows),
        missing_weight_items=sum(row.status == "MISSING WEIGHT" for row in rows),
        missing_due_date_items=sum(row.missing_due_date for row in rows),
        missing_demand_items=sum(row.status == "MISSING DEMAND" for row in rows),
        total_shortage_qty=sum(row.shortage_qty for row in rows),
        total_production_required_qty=sum(row.production_required_qty for row in rows),
        total_production_required_tons=round(
            sum(row.production_required_tons for row in rows), 4
        ),
        warning_count=sum(len(row.warnings) for row in rows),
    )


def _map_requirement(raw: dict[str, Any]) -> ProductionRequirementRow:
    available = _to_int(raw["available_stock_at_date"])
    demand = _to_int(raw["eligible_shipment_demand"])
    shortage = _to_int(raw["shortage_qty"])
    weight = _to_float(raw["unit_weight_kg"])
    missing_due_date = _to_int(raw["missing_due_dates"]) > 0
    missing_weight = shortage > 0 and weight <= 0
    negative_available_stock = available < 0
    warnings: list[str] = []

    if missing_due_date:
        warnings.append("MISSING_DUE_DATE")
    if negative_available_stock:
        warnings.append("NEGATIVE_AVAILABLE_STOCK")
    if _to_int(raw["confirmed_production_qty"]) > 0:
        warnings.append("PRODUCTION_MOVEMENT_ALREADY_POSTED_TO_FG")
    if _to_int(raw["completed_shipment_qty"]) > 0:
        warnings.append("SHIPMENT_MOVEMENT_INFORMATIONAL_ONLY")

    if demand <= 0:
        status = "MISSING DEMAND"
    elif shortage <= 0:
        status = "READY"
    elif missing_weight:
        status = "MISSING WEIGHT"
        warnings.append("MISSING_WEIGHT")
    elif available <= 0:
        status = "OUT OF STOCK"
    elif available < demand:
        status = "PARTIAL READY"
    else:
        status = "PRODUCTION REQUIRED"

    tons = round(shortage * weight / 1000.0, 4) if weight > 0 else 0.0
    return ProductionRequirementRow(
        material_code=str(raw["material_code"]),
        item_description=str(raw["item_description"]),
        product_group=str(raw["product_group"] or "-"),
        capacity_key=str(raw["capacity_key"] or ""),
        fg_stock=_to_int(raw["fg_stock"]),
        qc_stock=_to_int(raw["qc_stock"]),
        scrap_stock=_to_int(raw["scrap_stock"]),
        blocked_stock=_to_int(raw["blocked_stock"]),
        opening_available_stock=_to_int(raw["opening_available_stock"]),
        confirmed_production_qty=_to_int(raw["confirmed_production_qty"]),
        completed_shipment_qty=_to_int(raw["completed_shipment_qty"]),
        available_stock_at_date=available,
        eligible_shipment_demand=demand,
        shortage_qty=shortage,
        production_required_qty=shortage,
        unit_weight_kg=weight,
        production_required_tons=tons,
        earliest_due_date=raw["earliest_due_date"],
        missing_due_date=missing_due_date,
        missing_weight=missing_weight,
        negative_available_stock=negative_available_stock,
        status=status,
        warnings=tuple(warnings),
    )


def _to_int(value: Any) -> int:
    return int(value or 0)


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)
