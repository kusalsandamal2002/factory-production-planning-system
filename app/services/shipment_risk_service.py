from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.oven_capacity_service import CapacityAnalysisRow
from app.services.oven_schedule_service import OvenScheduleRow
from app.services.production_requirement_service import ProductionRequirementRow


@dataclass(frozen=True)
class ShipmentRiskRow:
    demand_reference: str
    customer_name: str
    material_code: str
    due_date: date | None
    demand_qty: int
    available_stock: int
    shortage_qty: int
    production_required_qty: int
    planned_qty: int
    unplanned_qty: int
    estimated_completion_date: date | None
    risk_status: str
    risk_reason: str


def build_shipment_risks(
    session: Session,
    *,
    planning_date: date,
    production_rows: list[ProductionRequirementRow],
    capacity_rows: list[CapacityAnalysisRow],
    schedule_rows: list[OvenScheduleRow],
) -> list[ShipmentRiskRow]:
    production_map = {row.material_code: row for row in production_rows}
    capacity_map = {row.item_code: row for row in capacity_rows}
    planned_by_item: dict[str, int] = {}
    for row in schedule_rows:
        planned_by_item[row.material_code] = (
            planned_by_item.get(row.material_code, 0) + row.total_planned_qty
        )

    demands = session.execute(
        text(
            """
            SELECT
                'MPPS-' || id::TEXT AS demand_reference,
                COALESCE(customer_name, 'EXCEL DEMAND') AS customer_name,
                material_code,
                shipment_date AS due_date,
                demand_qty
            FROM mpps_shipment_demand
            WHERE UPPER(status) IN ('PENDING', 'CONFIRMED', 'PLANNED', 'PARTIALLY_PLANNED')
              AND demand_qty > 0
              AND (shipment_date IS NULL OR shipment_date <= :planning_date)
            ORDER BY due_date NULLS LAST, demand_reference;
            """
        ),
        {"planning_date": planning_date},
    ).mappings()

    stock_remaining = {
        code: max(row.available_stock_at_date, 0) for code, row in production_map.items()
    }
    plan_remaining = dict(planned_by_item)
    output: list[ShipmentRiskRow] = []

    for demand in demands:
        code = str(demand["material_code"])
        qty = int(demand["demand_qty"] or 0)
        available = min(stock_remaining.get(code, 0), qty)
        stock_remaining[code] = max(stock_remaining.get(code, 0) - available, 0)
        shortage = max(qty - available, 0)
        planned = min(plan_remaining.get(code, 0), shortage)
        plan_remaining[code] = max(plan_remaining.get(code, 0) - planned, 0)
        unplanned = max(shortage - planned, 0)
        capacity = capacity_map.get(code)
        due_date = demand["due_date"]
        completion = capacity.estimated_completion_date if capacity else None

        reasons: list[str] = []
        if due_date is None:
            reasons.append("MISSING DUE DATE")
        if code not in production_map:
            reasons.append("MISSING STOCK ITEM")
        if shortage > 0 and (capacity is None or capacity.available_capacity <= 0):
            reasons.append("MISSING CAPACITY")
        if shortage > 0 and planned <= 0:
            reasons.append("NO OVEN PLAN")
        elif unplanned > 0:
            reasons.append("PART OF SHORTAGE REMAINS UNPLANNED")

        if reasons and ("MISSING DUE DATE" in reasons or "MISSING STOCK ITEM" in reasons):
            status = "DATA MISSING"
        elif shortage <= 0:
            status = "LOW RISK"
        elif capacity is None or capacity.available_capacity <= 0:
            status = "CANNOT COMPLETE"
        elif due_date is not None and completion is not None and completion > due_date:
            status = "HIGH RISK"
            reasons.append("ESTIMATED COMPLETION AFTER DUE DATE")
        elif unplanned > 0:
            status = "HIGH RISK"
        elif completion is None:
            status = "DATA MISSING"
            reasons.append("COMPLETION DATE UNAVAILABLE")
        elif due_date is not None and (due_date - completion).days <= 1:
            status = "MEDIUM RISK"
            reasons.append("ONE DAY OR LESS CAPACITY BUFFER")
        else:
            status = "LOW RISK"

        output.append(
            ShipmentRiskRow(
                demand_reference=str(demand["demand_reference"]),
                customer_name=str(demand["customer_name"]),
                material_code=code,
                due_date=due_date,
                demand_qty=qty,
                available_stock=available,
                shortage_qty=shortage,
                production_required_qty=shortage,
                planned_qty=planned,
                unplanned_qty=unplanned,
                estimated_completion_date=completion,
                risk_status=status,
                risk_reason="; ".join(dict.fromkeys(reasons)) or "Stock and plan cover demand.",
            )
        )
    return output
