from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import floor

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.material_requirement_service import PlanningAssumptions
from app.services.oven_capacity_service import CapacityAnalysisRow
from app.services.production_requirement_service import ProductionRequirementRow


@dataclass(frozen=True)
class OvenScheduleRow:
    plan_date: date
    material_code: str
    item_description: str
    oven_code: str
    line_category: str
    day_qty: int
    night_qty: int
    total_planned_qty: int
    remaining_qty: int
    planned_tons: float
    status: str
    risk_reason: str


@dataclass(frozen=True)
class OvenScheduleSummary:
    active_ovens: int
    production_required_qty: int
    planned_qty: int
    unplanned_qty: int
    planned_tons: float
    capacity_status: str
    risk_warning_count: int
    assumption_note: str


def build_daily_oven_schedule(
    session: Session,
    *,
    planning_date: date,
    production_rows: list[ProductionRequirementRow],
    capacity_rows: list[CapacityAnalysisRow],
    assumptions: PlanningAssumptions | None = None,
) -> tuple[list[OvenScheduleRow], OvenScheduleSummary]:
    assumptions = assumptions or PlanningAssumptions()
    if not 0.0 <= assumptions.day_shift_share <= 1.0:
        raise ValueError("Day shift share must be between 0 and 1.")

    capacity_map = {row.item_code: row for row in capacity_rows}
    mapping_rows = session.execute(
        text(
            """
            SELECT material_code, oven_code, SUM(planned_qty)::INTEGER AS historical_qty
            FROM mpps_oven_plan
            WHERE material_code IS NOT NULL
              AND oven_code IS NOT NULL
              AND planned_qty > 0
            GROUP BY material_code, oven_code
            ORDER BY material_code, historical_qty DESC, oven_code;
            """
        )
    ).mappings()
    compatibility: dict[str, list[tuple[str, int]]] = {}
    for row in mapping_rows:
        compatibility.setdefault(str(row["material_code"]), []).append(
            (str(row["oven_code"]), int(row["historical_qty"]))
        )

    active_ovens = int(
        session.execute(text("SELECT COUNT(*) FROM ovens WHERE is_active = TRUE")).scalar_one()
    )
    output: list[OvenScheduleRow] = []

    for production in production_rows:
        if production.production_required_qty <= 0:
            continue
        capacity = capacity_map.get(production.material_code)
        mappings = compatibility.get(production.material_code, [])

        if capacity is None or capacity.available_capacity <= 0:
            output.append(_unplanned(planning_date, production, "MISSING CAPACITY"))
            continue
        if not mappings:
            output.append(
                _unplanned(planning_date, production, "MISSING OVEN COMPATIBILITY")
            )
            continue

        daily_qty = min(
            production.production_required_qty,
            max(int(floor(capacity.available_capacity)), 0),
        )
        if daily_qty <= 0:
            output.append(_unplanned(planning_date, production, "ZERO DAILY CAPACITY"))
            continue

        allocations = _proportional_allocations(daily_qty, mappings)
        remaining_after_day = production.production_required_qty - daily_qty
        for oven_code, total_qty in allocations:
            day_qty = int(round(total_qty * assumptions.day_shift_share))
            day_qty = min(day_qty, total_qty)
            night_qty = total_qty - day_qty
            tons = total_qty * production.unit_weight_kg / 1000.0
            warnings = list(production.warnings)
            if production.unit_weight_kg <= 0:
                warnings.append("MISSING WEIGHT")
            warnings.append(
                f"DAY/NIGHT SPLIT USES VISIBLE {assumptions.day_shift_share:.0%} DAY SHARE"
            )
            output.append(
                OvenScheduleRow(
                    plan_date=planning_date,
                    material_code=production.material_code,
                    item_description=production.item_description,
                    oven_code=oven_code,
                    line_category=_line_category(oven_code),
                    day_qty=day_qty,
                    night_qty=night_qty,
                    total_planned_qty=total_qty,
                    remaining_qty=remaining_after_day,
                    planned_tons=round(tons, 4),
                    status="PLANNED" if remaining_after_day == 0 else "PARTIALLY PLANNED",
                    risk_reason="; ".join(dict.fromkeys(warnings)),
                )
            )

    required_qty = sum(
        row.production_required_qty for row in production_rows if row.production_required_qty > 0
    )
    planned_qty = sum(row.total_planned_qty for row in output)
    unplanned_qty = max(required_qty - planned_qty, 0)
    warnings = sum(bool(row.risk_reason) or row.status != "PLANNED" for row in output)
    if required_qty == 0:
        capacity_status = "NO PRODUCTION REQUIRED"
    elif unplanned_qty == 0:
        capacity_status = "FULLY PLANNED"
    elif planned_qty > 0:
        capacity_status = "PARTIALLY PLANNED"
    else:
        capacity_status = "UNPLANNED"

    summary = OvenScheduleSummary(
        active_ovens=active_ovens,
        production_required_qty=required_qty,
        planned_qty=planned_qty,
        unplanned_qty=unplanned_qty,
        planned_tons=round(sum(row.planned_tons for row in output), 4),
        capacity_status=capacity_status,
        risk_warning_count=warnings,
        assumption_note=(
            f"Day/night split: {assumptions.day_shift_share:.0%}/"
            f"{1.0 - assumptions.day_shift_share:.0%}; visible assumption because "
            "imported oven rows store TOTAL only."
        ),
    )
    return output, summary


def load_imported_oven_plan(
    session: Session,
    *,
    planning_date: date,
) -> list[OvenScheduleRow]:
    rows = session.execute(
        text(
            """
            SELECT plan_date, material_code, item_description, oven_code, shift_name,
                   planned_qty, planned_weight_kg, plan_status, source_note
            FROM mpps_oven_plan
            WHERE plan_date = :planning_date
            ORDER BY oven_code, material_code, id;
            """
        ),
        {"planning_date": planning_date},
    ).mappings()
    output: list[OvenScheduleRow] = []
    for row in rows:
        shift = str(row["shift_name"] or "TOTAL").upper()
        qty = int(row["planned_qty"] or 0)
        day_qty = qty if "DAY" in shift else 0
        night_qty = qty if "NIGHT" in shift else 0
        output.append(
            OvenScheduleRow(
                plan_date=row["plan_date"],
                material_code=str(row["material_code"] or "-"),
                item_description=str(row["item_description"] or "-"),
                oven_code=str(row["oven_code"] or "UNASSIGNED"),
                line_category=_line_category(str(row["oven_code"] or "")),
                day_qty=day_qty,
                night_qty=night_qty,
                total_planned_qty=qty,
                remaining_qty=0,
                planned_tons=round(float(row["planned_weight_kg"] or 0) / 1000.0, 4),
                status=str(row["plan_status"] or "IMPORTED"),
                risk_reason=(
                    "Imported source stores TOTAL quantity; day/night detail unavailable."
                    if shift == "TOTAL"
                    else str(row["source_note"] or "")
                ),
            )
        )
    return output


def _proportional_allocations(
    total_qty: int,
    mappings: list[tuple[str, int]],
) -> list[tuple[str, int]]:
    weight_total = sum(max(weight, 0) for _, weight in mappings)
    if weight_total <= 0:
        return [(mappings[0][0], total_qty)]
    allocations: list[list[object]] = []
    assigned = 0
    for oven_code, weight in mappings:
        qty = int(floor(total_qty * weight / weight_total))
        allocations.append([oven_code, qty, weight])
        assigned += qty
    remainder = total_qty - assigned
    for index in range(remainder):
        allocations[index % len(allocations)][1] = int(allocations[index % len(allocations)][1]) + 1
    return [(str(row[0]), int(row[1])) for row in allocations if int(row[1]) > 0]


def _unplanned(
    planning_date: date,
    production: ProductionRequirementRow,
    reason: str,
) -> OvenScheduleRow:
    return OvenScheduleRow(
        plan_date=planning_date,
        material_code=production.material_code,
        item_description=production.item_description,
        oven_code="UNASSIGNED",
        line_category=production.product_group,
        day_qty=0,
        night_qty=0,
        total_planned_qty=0,
        remaining_qty=production.production_required_qty,
        planned_tons=0.0,
        status="UNPLANNED",
        risk_reason=reason,
    )


def _line_category(oven_code: str) -> str:
    value = oven_code.upper()
    if "ORING" in value or "O-RING" in value:
        return "O-RING PRESS"
    if "800" in value:
        return "800 LINE"
    if "600" in value:
        return "600 PRESS"
    if "400" in value:
        return "400 LINE"
    if "200" in value:
        return "200 LINE"
    if "PRESS" in value:
        return "PRESS"
    return "OVEN"
