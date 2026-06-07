from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import floor

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.material_requirement_service import PlanningAssumptions
from app.services.oven_capacity_service import CapacityAnalysisRow, build_capacity_analysis
from app.services.production_requirement_service import (
    ProductionRequirementRow,
    load_production_requirements,
)


@dataclass(frozen=True)
class OvenScheduleRow:
    plan_date: date
    material_code: str
    item_description: str
    due_date: date | None
    demand_qty: int
    available_stock: int
    shortage_qty: int
    production_required_qty: int
    effective_daily_capacity: float
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
    missing_capacity_items: int
    missing_compatibility_items: int
    missing_due_date_items: int
    missing_weight_items: int
    capacity_status: str
    risk_warning_count: int
    assumption_note: str


def calculate_daily_oven_plan(
    session: Session,
    *,
    planning_date: date,
    assumptions: PlanningAssumptions | None = None,
) -> tuple[list[OvenScheduleRow], OvenScheduleSummary]:
    production_rows = load_production_requirements(
        session,
        planning_date=planning_date,
        production_required_only=True,
    )
    capacity_rows = build_capacity_analysis(
        session,
        production_rows=production_rows,
        planning_date=planning_date,
    )
    return build_daily_oven_schedule(
        session,
        planning_date=planning_date,
        production_rows=production_rows,
        capacity_rows=capacity_rows,
        assumptions=assumptions,
    )


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
    compatibility = _load_active_compatibility(session)
    active_ovens = int(
        session.execute(
            text(
                """
                SELECT COUNT(DISTINCT oven.id)
                FROM ovens oven
                JOIN mpps_oven_plan plan
                  ON plan.oven_code = oven.oven_code
                WHERE oven.is_active = TRUE
                  AND plan.planned_qty > 0;
                """
            )
        ).scalar_one()
    )

    capacity_remaining: dict[str, int] = {}
    for capacity in capacity_rows:
        if capacity.capacity_key and capacity.available_capacity > 0:
            capacity_remaining.setdefault(
                capacity.capacity_key,
                max(int(floor(capacity.available_capacity)), 0),
            )

    ordered_production = sorted(
        (row for row in production_rows if row.production_required_qty > 0),
        key=lambda row: (
            row.earliest_due_date is None,
            row.earliest_due_date or date.max,
            -row.production_required_qty,
            row.material_code,
        ),
    )

    output: list[OvenScheduleRow] = []
    missing_capacity_codes: set[str] = set()
    missing_compatibility_codes: set[str] = set()

    for production in ordered_production:
        capacity = capacity_map.get(production.material_code)
        mappings = compatibility.get(production.material_code, [])

        if capacity is None or capacity.available_capacity <= 0:
            missing_capacity_codes.add(production.material_code)
            output.append(
                _unplanned(
                    planning_date,
                    production,
                    capacity=capacity,
                    status="MISSING CAPACITY",
                    reason=capacity.warning if capacity is not None else "MISSING CAPACITY",
                )
            )
            continue

        if not mappings:
            missing_compatibility_codes.add(production.material_code)
            output.append(
                _unplanned(
                    planning_date,
                    production,
                    capacity=capacity,
                    status="MISSING COMPATIBILITY",
                    reason="No active oven/press compatibility exists in mpps_oven_plan.",
                )
            )
            continue

        shared_capacity = capacity_remaining.get(capacity.capacity_key, 0)
        if shared_capacity <= 0:
            output.append(
                _unplanned(
                    planning_date,
                    production,
                    capacity=capacity,
                    status="UNPLANNED",
                    reason=(
                        "Shared mould/category capacity was allocated to higher-priority "
                        "items for this planning date."
                    ),
                )
            )
            continue

        daily_qty = min(production.production_required_qty, shared_capacity)
        capacity_remaining[capacity.capacity_key] = shared_capacity - daily_qty
        remaining_after_day = production.production_required_qty - daily_qty
        base_status = "PLANNED" if remaining_after_day == 0 else "PARTIAL"
        display_status = _warning_status(production, base_status)
        warnings = list(production.warnings)
        if base_status == "PARTIAL":
            warnings.append("PARTIAL_DAILY_CAPACITY")

        for oven_code, total_qty in _proportional_allocations(daily_qty, mappings):
            day_qty = min(int(round(total_qty * assumptions.day_shift_share)), total_qty)
            night_qty = total_qty - day_qty
            output.append(
                OvenScheduleRow(
                    plan_date=planning_date,
                    material_code=production.material_code,
                    item_description=production.item_description,
                    due_date=production.earliest_due_date,
                    demand_qty=production.eligible_shipment_demand,
                    available_stock=production.available_stock_at_date,
                    shortage_qty=production.shortage_qty,
                    production_required_qty=production.production_required_qty,
                    effective_daily_capacity=capacity.available_capacity,
                    oven_code=oven_code,
                    line_category=_line_category(oven_code),
                    day_qty=day_qty,
                    night_qty=night_qty,
                    total_planned_qty=total_qty,
                    remaining_qty=remaining_after_day,
                    planned_tons=round(
                        total_qty * production.unit_weight_kg / 1000.0, 4
                    ),
                    status=display_status,
                    risk_reason="; ".join(dict.fromkeys(warnings)) or "-",
                )
            )

    required_qty = sum(row.production_required_qty for row in ordered_production)
    planned_qty = sum(row.total_planned_qty for row in output)
    unplanned_qty = max(required_qty - planned_qty, 0)
    warning_items = {
        row.material_code
        for row in output
        if row.status not in {"PLANNED", "PARTIAL"} or row.risk_reason not in {"", "-"}
    }

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
        missing_capacity_items=len(missing_capacity_codes),
        missing_compatibility_items=len(missing_compatibility_codes),
        missing_due_date_items=sum(row.missing_due_date for row in ordered_production),
        missing_weight_items=sum(row.missing_weight for row in ordered_production),
        capacity_status=capacity_status,
        risk_warning_count=len(warning_items),
        assumption_note=(
            "This schedule uses Excel-derived quantity/mould/day planning. "
            "Minute-level curing utilization is not shown because verified "
            "cycle-time data is not available. "
            f"Compound allowance {assumptions.compound_allowance_rate:.0%}; "
            f"band allowance {assumptions.band_allowance_rate:.0%}; "
            f"day/night split {assumptions.day_shift_share:.0%}/"
            f"{1.0 - assumptions.day_shift_share:.0%}."
        ),
    )
    return output, summary


def load_imported_oven_plan(
    session: Session,
    *,
    planning_date: date,
) -> list[OvenScheduleRow]:
    """Read preserved imported plan rows without modifying them."""
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
        output.append(
            OvenScheduleRow(
                plan_date=row["plan_date"],
                material_code=str(row["material_code"] or "-"),
                item_description=str(row["item_description"] or "-"),
                due_date=None,
                demand_qty=0,
                available_stock=0,
                shortage_qty=0,
                production_required_qty=0,
                effective_daily_capacity=0.0,
                oven_code=str(row["oven_code"] or "UNASSIGNED"),
                line_category=_line_category(str(row["oven_code"] or "")),
                day_qty=qty if "DAY" in shift else 0,
                night_qty=qty if "NIGHT" in shift else 0,
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


def _load_active_compatibility(
    session: Session,
) -> dict[str, list[tuple[str, int]]]:
    rows = session.execute(
        text(
            """
            SELECT op.material_code, op.oven_code,
                   SUM(op.planned_qty)::INTEGER AS historical_qty
            FROM mpps_oven_plan op
            JOIN ovens oven ON oven.oven_code = op.oven_code
            WHERE op.material_code IS NOT NULL
              AND op.oven_code IS NOT NULL
              AND op.planned_qty > 0
              AND oven.is_active = TRUE
            GROUP BY op.material_code, op.oven_code
            ORDER BY op.material_code, historical_qty DESC, op.oven_code;
            """
        )
    ).mappings()
    compatibility: dict[str, list[tuple[str, int]]] = {}
    for row in rows:
        compatibility.setdefault(str(row["material_code"]), []).append(
            (str(row["oven_code"]), int(row["historical_qty"]))
        )
    return compatibility


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
        allocations.append([oven_code, qty])
        assigned += qty
    for index in range(total_qty - assigned):
        allocations[index % len(allocations)][1] = (
            int(allocations[index % len(allocations)][1]) + 1
        )
    return [
        (str(allocation[0]), int(allocation[1]))
        for allocation in allocations
        if int(allocation[1]) > 0
    ]


def _warning_status(production: ProductionRequirementRow, base_status: str) -> str:
    if production.missing_weight:
        return "MISSING WEIGHT"
    if production.missing_due_date:
        return "MISSING DUE DATE"
    return base_status


def _unplanned(
    planning_date: date,
    production: ProductionRequirementRow,
    *,
    capacity: CapacityAnalysisRow | None,
    status: str,
    reason: str,
) -> OvenScheduleRow:
    warnings = list(production.warnings)
    warnings.append(reason)
    return OvenScheduleRow(
        plan_date=planning_date,
        material_code=production.material_code,
        item_description=production.item_description,
        due_date=production.earliest_due_date,
        demand_qty=production.eligible_shipment_demand,
        available_stock=production.available_stock_at_date,
        shortage_qty=production.shortage_qty,
        production_required_qty=production.production_required_qty,
        effective_daily_capacity=capacity.available_capacity if capacity else 0.0,
        oven_code="UNASSIGNED",
        line_category=production.product_group,
        day_qty=0,
        night_qty=0,
        total_planned_qty=0,
        remaining_qty=production.production_required_qty,
        planned_tons=0.0,
        status=status,
        risk_reason="; ".join(dict.fromkeys(warnings)),
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
