from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from math import ceil

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.production_requirement_service import ProductionRequirementRow
from app.services.factory_resource_intelligence_service import (
    FactoryResourceIntelligenceService,
)


@dataclass(frozen=True)
class CapacityAnalysisRow:
    item_code: str
    item_description: str
    capacity_key: str
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


def _legacy_reference(session: Session, *keys: str) -> dict:
    normalized = {str(k or "").strip().upper() for k in keys if str(k or "").strip()}
    if not normalized:
        return {}
    try:
        with session.begin_nested():
            rows = session.execute(
                text(
                    """
                    SELECT item_code, running_moulds, per_mould_capacity,
                           available_capacity_per_day
                    FROM mpps_capacity_master
                    WHERE is_active=TRUE
                    """
                )
            ).mappings().all()
    except Exception:
        return {}
    for row in rows:
        if str(row.get("item_code") or "").strip().upper() in normalized:
            return dict(row)
    return {}


def build_capacity_analysis(
    session: Session,
    *,
    production_rows: list[ProductionRequirementRow],
    planning_date: date,
) -> list[CapacityAnalysisRow]:
    """Build capacity feasibility using the V11 authoritative resolver.

    Legacy running-mould/per-mould fields remain visible as labelled technical
    reference only; available capacity comes from learned real output adjusted by
    current mold/casing/cavity constraints.
    """
    required = [row for row in production_rows if row.production_required_qty > 0]
    if not required:
        return []

    FactoryResourceIntelligenceService.ensure_schema(session)
    output: list[CapacityAnalysisRow] = []

    for production in required:
        resolution = FactoryResourceIntelligenceService.resolve_capacity(
            session,
            production.material_code,
            on_date=planning_date,
            ensure_schema=False,
        )
        legacy = _legacy_reference(
            session,
            production.material_code,
            production.capacity_key,
            resolution.mold_key,
        )
        moulds = float(legacy.get("running_moulds") or 0.0)
        per_mould = float(legacy.get("per_mould_capacity") or 0.0)
        calculated = moulds * per_mould
        daily = float(
            resolution.available_capacity
            or resolution.safe_capacity
            or resolution.technical_capacity
            or 0
        )
        target = production.earliest_due_date

        if daily <= 0:
            required_days = None
            completion = None
            status = "CANNOT COMPLETE"
            warning = resolution.constraint_reason or "NO CAPACITY EVIDENCE"
        else:
            required_days = int(ceil(production.production_required_qty / daily))
            completion = planning_date + timedelta(days=max(required_days - 1, 0))
            status = "CAN COMPLETE"
            warning = ""
            if target is not None and completion > target:
                status = "CANNOT COMPLETE"
                warning = (
                    "CONSTRAINT-ADJUSTED CAPACITY COMPLETION AFTER DUE DATE. "
                    + resolution.constraint_reason
                ).strip()

        output.append(
            CapacityAnalysisRow(
                item_code=production.material_code,
                item_description=production.item_description,
                capacity_key=production.capacity_key,
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
