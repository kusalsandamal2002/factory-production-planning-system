from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.production_requirement_service import ProductionRequirementRow


@dataclass(frozen=True)
class CapacityAnalysisRow:
    item_code: str
    item_description: str
    production_required_qty: int
    running_moulds: float
    per_mould_capacity: float
    calculated_daily_capacity: float
    available_capacity: float
    required_days: int | None
    capacity_gap: float
    target_date: date | None
    estimated_completion_date: date | None
    status: str
    warning: str


def build_capacity_analysis(
    session: Session,
    *,
    production_rows: list[ProductionRequirementRow],
    planning_date: date,
) -> list[CapacityAnalysisRow]:
    required = [row for row in production_rows if row.production_required_qty > 0]
    if not required:
        return []

    capacity_keys = sorted({row.capacity_key for row in required if row.capacity_key})
    capacity_rows = session.execute(
        text(
            """
            SELECT item_code, running_moulds, per_mould_capacity,
                   available_capacity_per_day, target_date
            FROM mpps_capacity_master
            WHERE is_active = TRUE
              AND item_code = ANY(:capacity_keys);
            """
        ),
        {"capacity_keys": capacity_keys},
    ).mappings()
    capacity_map = {str(row["item_code"]): row for row in capacity_rows}
    output: list[CapacityAnalysisRow] = []

    for production in required:
        master = capacity_map.get(production.capacity_key)
        if master is None:
            output.append(
                CapacityAnalysisRow(
                    item_code=production.material_code,
                    item_description=production.item_description,
                    production_required_qty=production.production_required_qty,
                    running_moulds=0.0,
                    per_mould_capacity=0.0,
                    calculated_daily_capacity=0.0,
                    available_capacity=0.0,
                    required_days=None,
                    capacity_gap=-float(production.production_required_qty),
                    target_date=production.earliest_due_date,
                    estimated_completion_date=None,
                    status="CANNOT COMPLETE",
                    warning=(
                        "MISSING CAPACITY KEY"
                        if not production.capacity_key
                        else f"MISSING CAPACITY FOR {production.capacity_key}"
                    ),
                )
            )
            continue

        moulds = float(master["running_moulds"] or 0)
        per_mould = float(master["per_mould_capacity"] or 0)
        calculated = moulds * per_mould
        approved = float(master["available_capacity_per_day"] or 0)
        daily = approved if approved > 0 else calculated
        target = production.earliest_due_date or master["target_date"]

        if daily <= 0:
            required_days = None
            completion = None
            status = "CANNOT COMPLETE"
            warning = "ZERO CAPACITY"
        else:
            required_days = int(ceil(production.production_required_qty / daily))
            completion = planning_date + timedelta(days=max(required_days - 1, 0))
            status = "CAN COMPLETE"
            warning = ""
            if target is not None and completion > target:
                status = "CANNOT COMPLETE"
                warning = "CAPACITY COMPLETION AFTER DUE DATE"

        output.append(
            CapacityAnalysisRow(
                item_code=production.material_code,
                item_description=production.item_description,
                production_required_qty=production.production_required_qty,
                running_moulds=round(moulds, 4),
                per_mould_capacity=round(per_mould, 4),
                calculated_daily_capacity=round(calculated, 4),
                available_capacity=round(daily, 4),
                required_days=required_days,
                capacity_gap=round(daily - production.production_required_qty, 4),
                target_date=target,
                estimated_completion_date=completion,
                status=status,
                warning=warning,
            )
        )
    return output
