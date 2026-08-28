from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import bindparam, text

from app.database import engine
from app.services.shipment_details_async_service import (
    load_shipment_detail,
    load_shipment_portfolio,
)


CLOSED_LIFECYCLES = {"SHIPPED", "CANCELLED"}
PRIORITY_STATUSES = {
    "NOT_PLANNED",
    "PLANNED",
    "IN_PRODUCTION",
    "READY_FOR_DISPATCH",
}


def _lifecycle_from_row(row: dict[str, Any]) -> str:
    explicit = str(row.get("lifecycle_status") or "").strip().upper()
    if explicit:
        return explicit

    status = str(row.get("shipment_status") or row.get("status") or "").strip().lower()
    planning = str(row.get("planning_status") or "").strip().lower()

    if bool(row.get("source_missing_from_latest")) or status in {
        "review required",
        "imported review",
        "closure review",
    }:
        return "CLOSURE_REVIEW"
    if status in {"shipped", "complete", "completed", "closed", "done"}:
        return "SHIPPED"
    if status in {"cancelled", "canceled"}:
        return "CANCELLED"
    if status in {"hold", "on hold"}:
        return "HOLD"
    if planning in {"in progress", "processing", "in production"}:
        return "IN_PROGRESS"
    return "ACTIVE"


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def derive_operational_status(row: dict[str, Any]) -> str:
    """Return the user-facing shipment stage without duplicating lifecycle facts.

    The stage is derived from authoritative shipment, planning and stock fields.
    R6 keeps this richer R2 behavior while the canonical planner remains the
    authority for persisted priority and Factory Can Out calculations.
    """

    lifecycle = str(row.get("lifecycle") or _lifecycle_from_row(row)).upper()
    if lifecycle == "CLOSURE_REVIEW":
        return "CLOSURE_REVIEW"
    if lifecycle == "SHIPPED":
        return "SHIPPED"
    if lifecycle == "CANCELLED":
        return "CANCELLED"
    if lifecycle == "HOLD":
        return "HOLD"
    if lifecycle == "IN_PROGRESS":
        return "IN_PRODUCTION"

    total = max(_int(row.get("total_quantity")), 0)
    stock_pct = max(
        0.0,
        min(
            100.0,
            _float(
                row.get("stock_coverage_pct")
                if row.get("stock_coverage_pct") is not None
                else row.get("stock_progress_pct")
            ),
        ),
    )
    gap = max(_int(row.get("production_gap")), 0)
    planning = str(row.get("planning_status") or "").strip().lower()
    shipment_status = str(
        row.get("shipment_status") or row.get("status") or ""
    ).strip().lower()
    factory_out = row.get("factory_can_receive_date")

    if planning in {"in progress", "processing", "in production"} or shipment_status in {
        "in progress",
        "processing",
        "in production",
    }:
        return "IN_PRODUCTION"

    # Preserve R2's "ready" interpretation, but accept canonical stock coverage.
    if gap <= 0 and stock_pct >= 99.999 and (total > 0 or stock_pct > 0):
        return "READY_FOR_DISPATCH"

    if planning in {
        "pending",
        "pending planning",
        "pending replan",
        "blocked",
        "partially blocked",
        "not planned",
        "unplanned",
        "draft",
        "",
    }:
        if factory_out is None:
            return "NOT_PLANNED"

    if shipment_status in {"draft", "new", "pending"} and factory_out is None:
        return "NOT_PLANNED"

    if factory_out is None:
        return "NOT_PLANNED"

    return "PLANNED"


# Backward-compatible internal name used by the R6 target design.
_operational_status = derive_operational_status


def _priority_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    """Match the canonical R6 planning priority order exactly.

    Manual/manager targets are first. Then earliest target date and creation/id
    order are used. Risk and stock remain attention signals, not hidden priority
    overrides, so Shipment Details and the canonical planner cannot disagree.
    """

    manual = bool(row.get("target_date_is_manual"))
    source = str(row.get("target_date_source") or "").lower()
    locked = manual or (
        row.get("target_date") is not None
        and not source.startswith("auto")
        and not source.startswith("automatic")
    )
    return (
        0 if locked else 1,
        row.get("target_date") or date.max,
        row.get("created_at") or date.max,
        int(row.get("shipment_pk") or 0),
    )


def _priority_reason(row: dict[str, Any]) -> str:
    if bool(row.get("target_date_is_manual")):
        return "Manual/manager target date priority"
    source = str(row.get("target_date_source") or "").lower()
    if (
        row.get("target_date") is not None
        and not source.startswith("auto")
        and not source.startswith("automatic")
    ):
        return "Committed target date priority"
    return "Earliest active shipment target / creation order"


def annotate_portfolio_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Annotate rows with workflow stage and canonical dynamic priority number."""

    annotated: list[dict[str, Any]] = []
    for original in rows:
        row = dict(original)
        row["lifecycle"] = _lifecycle_from_row(row)
        row["operational_status"] = derive_operational_status(row)
        risk_band = str(row.get("risk_band") or "").strip().lower()
        risk_score = _int(row.get("risk_score"))
        gap = max(_int(row.get("production_gap")), 0)

        row["needs_attention"] = bool(
            row["operational_status"] == "CLOSURE_REVIEW"
            or risk_band in {"critical", "at_risk"}
            or risk_score >= 70
            or (
                row["operational_status"] in {"NOT_PLANNED", "HOLD"}
                and (
                    row.get("factory_can_receive_date") is None
                    or gap > 0
                )
            )
        )

        # Any previously persisted values are refreshed below from the same
        # deterministic canonical ordering used by PlanningAuthorityService.
        row["priority_no"] = None
        row["priority_reason"] = ""
        annotated.append(row)

    active_for_priority = [
        row for row in annotated if row.get("operational_status") in PRIORITY_STATUSES
    ]
    active_for_priority.sort(key=_priority_sort_key)

    for number, row in enumerate(active_for_priority, start=1):
        row["priority_no"] = number
        row["priority_reason"] = _priority_reason(row)

    stage_rank = {
        "CLOSURE_REVIEW": 0,
        "NOT_PLANNED": 1,
        "PLANNED": 1,
        "IN_PRODUCTION": 1,
        "READY_FOR_DISPATCH": 1,
        "HOLD": 2,
        "SHIPPED": 3,
        "CANCELLED": 4,
    }
    annotated.sort(
        key=lambda row: (
            stage_rank.get(str(row.get("operational_status") or ""), 9),
            row.get("priority_no") if row.get("priority_no") is not None else 10**9,
            row.get("target_date") or date.max,
            int(row.get("shipment_pk") or 0),
        )
    )
    return annotated


def load_portfolio(filters: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = load_shipment_portfolio(filters or {})
    rows = list(payload.get("rows") or [])
    ids = [
        int(row.get("shipment_pk") or 0)
        for row in rows
        if int(row.get("shipment_pk") or 0) > 0
    ]
    lifecycle_map: dict[int, dict[str, Any]] = {}

    if ids:
        stmt = text(
            """
            SELECT
                id,
                lifecycle_status,
                source_missing_from_latest,
                actual_factory_out_date,
                closure_reason,
                closure_decided_at,
                hold_reason,
                priority_no,
                priority_reason,
                priority_updated_at,
                created_at
            FROM mpps_shipments
            WHERE id IN :ids
            """
        ).bindparams(bindparam("ids", expanding=True))

        with engine.connect() as connection:
            extra = connection.execute(stmt, {"ids": ids}).mappings().all()
        lifecycle_map = {int(row["id"]): dict(row) for row in extra}

    merged: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item.update(lifecycle_map.get(int(item.get("shipment_pk") or 0), {}))
        merged.append(item)

    rows = annotate_portfolio_rows(merged)
    payload["rows"] = rows
    payload["closure_review_count"] = sum(
        1 for row in rows if row.get("operational_status") == "CLOSURE_REVIEW"
    )
    payload["status_counts"] = {
        status: sum(1 for row in rows if row.get("operational_status") == status)
        for status in (
            "CLOSURE_REVIEW",
            "NOT_PLANNED",
            "PLANNED",
            "IN_PRODUCTION",
            "READY_FOR_DISPATCH",
            "HOLD",
            "SHIPPED",
            "CANCELLED",
        )
    }
    payload["needs_attention_count"] = sum(
        1 for row in rows if bool(row.get("needs_attention"))
    )
    return payload


def load_detail(shipment_id: int) -> dict[str, Any]:
    payload = load_shipment_detail(int(shipment_id))
    shipment = payload.get("shipment") or {}
    items = payload.get("items") or []

    row = dict(shipment)
    row["shipment_status"] = row.get("status")
    row["lifecycle"] = _lifecycle_from_row(row)
    item_rows = [dict(item) for item in items]

    total_qty = sum(int(item.get("quantity") or 0) for item in item_rows)
    stock = sum(
        min(int(item.get("quantity") or 0), int(item.get("stock_allocated_qty") or 0))
        for item in item_rows
    )
    produced = sum(
        min(int(item.get("quantity") or 0), int(item.get("produced_qty") or 0))
        for item in item_rows
    )
    completed = sum(
        min(
            int(item.get("quantity") or 0),
            max(
                int(item.get("completed_qty") or 0),
                int(item.get("produced_qty") or 0),
            ),
        )
        for item in item_rows
    )
    gap = max(total_qty - stock - produced, 0)

    status_basis = dict(row)
    status_basis.update(
        {
            "total_quantity": total_qty,
            "stock_progress_pct": (stock / total_qty * 100.0) if total_qty else 0.0,
            "production_gap": gap,
        }
    )
    row["operational_status"] = derive_operational_status(status_basis)

    target = row.get("target_date")
    factory_out = (
        row.get("actual_factory_out_date")
        or row.get("factory_out_date")
        or row.get("factory_can_receive_date")
    )
    variance = None
    if target is not None and factory_out is not None:
        variance = (factory_out - target).days

    payload["shipment"] = row
    payload["items"] = item_rows
    payload["progress"] = {
        "total_qty": total_qty,
        "stock_qty": stock,
        "produced_qty": produced,
        "completed_qty": completed,
        "production_gap": gap,
        "stock_pct": (stock / total_qty * 100.0) if total_qty else 0.0,
        "production_pct": (produced / total_qty * 100.0) if total_qty else 0.0,
        "completed_pct": (completed / total_qty * 100.0) if total_qty else 0.0,
        "variance_days": variance,
    }
    return payload


def _audit(
    connection,
    shipment_id: int,
    action: str,
    old_lifecycle: str,
    new_lifecycle: str,
    reason: str,
    user_id: int | None,
) -> None:
    connection.execute(
        text(
            """
            INSERT INTO mpps_shipment_lifecycle_audit (
                shipment_id, action, old_lifecycle, new_lifecycle,
                reason, user_id, created_at
            )
            VALUES (
                :shipment_id, :action, :old_lifecycle, :new_lifecycle,
                :reason, :user_id, CURRENT_TIMESTAMP
            )
            """
        ),
        {
            "shipment_id": shipment_id,
            "action": action,
            "old_lifecycle": old_lifecycle,
            "new_lifecycle": new_lifecycle,
            "reason": reason,
            "user_id": user_id,
        },
    )


def set_lifecycle(
    shipment_id: int,
    lifecycle: str,
    *,
    reason: str = "",
    user_id: int | None = None,
) -> dict[str, Any]:
    shipment_id = int(shipment_id)
    lifecycle = str(lifecycle or "").strip().upper()
    allowed = {
        "ACTIVE",
        "IN_PROGRESS",
        "HOLD",
        "CLOSURE_REVIEW",
        "SHIPPED",
        "CANCELLED",
    }
    if lifecycle not in allowed:
        raise ValueError(f"Unsupported shipment lifecycle: {lifecycle}")

    with engine.begin() as connection:
        current = connection.execute(
            text(
                "SELECT id,status,lifecycle_status "
                "FROM mpps_shipments WHERE id=:id FOR UPDATE"
            ),
            {"id": shipment_id},
        ).mappings().first()
        if not current:
            raise ValueError(f"Shipment {shipment_id} was not found.")

        old_lifecycle = _lifecycle_from_row(dict(current))
        params = {
            "id": shipment_id,
            "lifecycle": lifecycle,
            "reason": str(reason or ""),
        }

        if lifecycle == "SHIPPED":
            connection.execute(
                text(
                    """
                    UPDATE mpps_shipments
                    SET lifecycle_status='SHIPPED',
                        status='Shipped',
                        planning_status='Completed',
                        actual_factory_out_date=COALESCE(
                            actual_factory_out_date,
                            factory_out_date,
                            factory_can_receive_date,
                            CURRENT_DATE
                        ),
                        closure_reason=:reason,
                        closure_decided_at=CURRENT_TIMESTAMP,
                        source_missing_from_latest=FALSE,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=:id
                    """
                ),
                params,
            )
        elif lifecycle == "CANCELLED":
            connection.execute(
                text(
                    """
                    UPDATE mpps_shipments
                    SET lifecycle_status='CANCELLED',
                        status='Cancelled',
                        planning_status='Cancelled',
                        closure_reason=:reason,
                        closure_decided_at=CURRENT_TIMESTAMP,
                        source_missing_from_latest=FALSE,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=:id
                    """
                ),
                params,
            )
        elif lifecycle == "HOLD":
            connection.execute(
                text(
                    """
                    UPDATE mpps_shipments
                    SET lifecycle_status='HOLD',
                        status='Hold',
                        hold_reason=:reason,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=:id
                    """
                ),
                params,
            )
        elif lifecycle == "CLOSURE_REVIEW":
            connection.execute(
                text(
                    """
                    UPDATE mpps_shipments
                    SET lifecycle_status='CLOSURE_REVIEW',
                        status='Review Required',
                        source_missing_from_latest=TRUE,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=:id
                    """
                ),
                params,
            )
        else:
            connection.execute(
                text(
                    """
                    UPDATE mpps_shipments
                    SET lifecycle_status=:lifecycle,
                        status=CASE
                            WHEN :lifecycle='IN_PROGRESS' THEN 'In Production'
                            ELSE 'Active'
                        END,
                        source_missing_from_latest=FALSE,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=:id
                    """
                ),
                params,
            )

        _audit(
            connection,
            shipment_id,
            lifecycle,
            old_lifecycle,
            lifecycle,
            str(reason or ""),
            user_id,
        )

    replan_warning = ""
    try:
        from app.services.factory_can_out_service import FactoryCanOutService
        from app.services.planning_authority_service import PlanningAuthorityService

        FactoryCanOutService.replan_open_shipments(
            trigger_reason=f"shipment_lifecycle_{lifecycle.lower()}",
            created_by="shipment_lifecycle_r6",
        )
        PlanningAuthorityService.persist_snapshot()
    except Exception as exc:
        # Lifecycle state is an operational fact and must not be rolled back merely
        # because a secondary canonical replan failed. The UI can surface this
        # retry warning while the next planning refresh reconciles the schedule.
        replan_warning = str(exc)

    detail = load_detail(shipment_id)
    detail["replan_warning"] = replan_warning
    return detail
