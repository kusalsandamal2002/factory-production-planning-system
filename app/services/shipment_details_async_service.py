from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Mapping

from sqlalchemy import text

from app.database import engine
from app.services.operational_source_service import OperationalSourceService
from app.services.shipment_command_service import portfolio_metrics, shipment_risk_profile

ProgressCallback = Callable[[int, str], None]


def _emit(progress: ProgressCallback | None, percent: int, message: str) -> None:
    if progress is not None:
        progress(max(0, min(100, int(percent))), str(message))


def load_shipment_portfolio(
    filters: Mapping[str, Any] | None = None,
    *,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Load Shipment Details portfolio data without touching Qt widgets.

    This function is intentionally UI-free so it can run safely inside a QThread.
    It returns plain Python/SQLAlchemy result data that the GUI can render later in
    small chunks.  Database I/O, forecast lookup, risk scoring and portfolio
    aggregation therefore never need to block the Qt event loop.
    """

    filters = dict(filters or {})
    search = str(filters.get("search") or "").strip()
    risk_filter = str(filters.get("risk_filter") or "all")
    promise_filter = str(filters.get("promise_filter") or "all")
    stock_filter = str(filters.get("stock_filter") or "all")
    date_window = str(filters.get("date_window") or "all")

    _emit(progress, 8, "Reading live OVEN authority...")
    with engine.begin() as connection:
        source = OperationalSourceService.latest(connection)

    as_of_date = source.plan_date or date.today()
    params: dict[str, Any] = {"as_of_date": as_of_date}
    conditions = ["1 = 1"]

    if search:
        params["search"] = f"%{search}%"
        conditions.append(
            """
            (
                shipment_no ILIKE :search
                OR shipment_name ILIKE :search
                OR customer_name ILIKE :search
                OR item_search_text ILIKE :search
            )
            """
        )

    if promise_filter != "all":
        params["promise_filter"] = promise_filter
        conditions.append("promise_state = :promise_filter")

    if stock_filter == "full":
        conditions.append("stock_progress_pct >= 100")
    elif stock_filter == "partial":
        conditions.append("stock_progress_pct > 0 AND stock_progress_pct < 100")
    elif stock_filter == "zero":
        conditions.append("stock_progress_pct <= 0")
    elif stock_filter == "gap":
        conditions.append("stock_progress_pct < 100")

    if date_window == "next_2":
        conditions.append(
            "target_date BETWEEN CAST(:as_of_date AS DATE) AND CAST(:as_of_date AS DATE) + 2"
        )
    elif date_window == "next_7":
        conditions.append(
            "target_date BETWEEN CAST(:as_of_date AS DATE) AND CAST(:as_of_date AS DATE) + 7"
        )
    elif date_window == "next_30":
        conditions.append(
            "target_date BETWEEN CAST(:as_of_date AS DATE) AND CAST(:as_of_date AS DATE) + 30"
        )
    elif date_window == "past_due":
        conditions.append("target_date < CAST(:as_of_date AS DATE)")
    elif date_window == "no_target":
        conditions.append("target_date IS NULL")

    where_sql = " AND ".join(conditions)

    query = f"""
        WITH item_summary AS (
            SELECT
                shipment_id,
                COUNT(*) AS item_count,
                COALESCE(SUM(quantity), 0) AS total_quantity,
                COALESCE(
                    SUM(
                        GREATEST(
                            0,
                            LEAST(
                                COALESCE(quantity, 0),
                                COALESCE(stock_allocated_qty, 0)
                            )
                        )
                    ),
                    0
                ) AS stock_allocated,
                COUNT(*) FILTER (
                    WHERE COALESCE(quantity, 0) > 0
                      AND COALESCE(
                            item_receive_date,
                            receive_date,
                            end_date,
                            start_date
                          ) IS NULL
                ) AS missing_receive_count,
                MAX(
                    COALESCE(
                        item_receive_date,
                        receive_date,
                        end_date,
                        start_date
                    )
                ) AS latest_receive_date,
                STRING_AGG(
                    COALESCE(sap_code, '')
                    || ' '
                    || COALESCE(item_description, ''),
                    ' '
                ) AS item_search_text
            FROM mpps_shipment_items
            GROUP BY shipment_id
        ),
        shipment_base AS (
            SELECT
                shipment.id AS shipment_pk,
                shipment.shipment_no,
                COALESCE(
                    NULLIF(shipment.shipment_name, ''),
                    shipment.shipment_no
                ) AS shipment_name,
                shipment.customer_name,
                CASE
                    WHEN NOT COALESCE(shipment.target_date_is_manual, FALSE)
                     AND shipment.target_date >= DATE '2060-01-01'
                    THEN NULL
                    ELSE shipment.target_date
                END AS target_date,
                CASE
                    WHEN NOT COALESCE(shipment.target_date_is_manual, FALSE)
                     AND shipment.target_date >= DATE '2060-01-01'
                    THEN 'Auto Earliest Feasible Factory Out'
                    ELSE COALESCE(
                        NULLIF(shipment.target_date_source, ''),
                        'Auto Earliest Feasible Factory Out'
                    )
                END AS target_date_source,
                COALESCE(shipment.target_date_is_manual, FALSE) AS target_date_is_manual,
                (
                    NOT COALESCE(shipment.target_date_is_manual, FALSE)
                    AND (
                        shipment.target_date IS NULL
                        OR shipment.target_date >= DATE '2060-01-01'
                        OR LOWER(COALESCE(shipment.target_date_source, '')) LIKE 'auto%'
                        OR LOWER(COALESCE(shipment.target_date_source, '')) LIKE 'automatic%'
                    )
                ) AS auto_target,
                CASE
                    WHEN (
                        LOWER(COALESCE(shipment.status, '')) IN (
                            'imported review',
                            'review required',
                            'draft import',
                            'excel review hold'
                        )
                        OR LOWER(COALESCE(shipment.planning_status, '')) = 'review required'
                        OR LOWER(COALESCE(shipment.target_date_source, '')) = 'excel import - date missing'
                    )
                    THEN NULL
                    WHEN COALESCE(item.missing_receive_count, 0) > 0
                    THEN NULL
                    ELSE COALESCE(
                        shipment.factory_out_date,
                        (
                            item.latest_receive_date
                            + GREATEST(0, COALESCE(shipment.dispatch_buffer_days, 0))
                        ),
                        (
                            shipment.factory_can_receive_date
                            + GREATEST(0, COALESCE(shipment.dispatch_buffer_days, 0))
                        )
                    )
                END AS factory_can_receive_date,
                COALESCE(item.item_count, 0) AS item_count,
                COALESCE(item.total_quantity, shipment.total_qty, 0) AS total_quantity,
                COALESCE(item.stock_allocated, 0) AS stock_allocated,
                COALESCE(item.item_search_text, '') AS item_search_text,
                COALESCE(NULLIF(shipment.status, ''), 'Planned') AS shipment_status,
                COALESCE(NULLIF(shipment.planning_status, ''), 'Pending') AS planning_status,
                COALESCE(NULLIF(shipment.lifecycle_status, ''), 'ACTIVE') AS lifecycle_status,
                COALESCE(shipment.source_missing_from_latest, FALSE) AS source_missing_from_latest,
                shipment.actual_factory_out_date,
                COALESCE(shipment.closure_reason, '') AS closure_reason,
                (
                    LOWER(COALESCE(shipment.status, '')) IN (
                        'imported review',
                        'review required',
                        'draft import',
                        'excel review hold'
                    )
                    OR LOWER(COALESCE(shipment.planning_status, '')) = 'review required'
                    OR LOWER(COALESCE(shipment.target_date_source, '')) = 'excel import - date missing'
                ) AS review_required
            FROM mpps_shipments shipment
            LEFT JOIN item_summary item ON item.shipment_id = shipment.id
        ),
        shipment_ranked AS (
            SELECT
                shipment_base.*,
                CASE
                    WHEN LOWER(shipment_status) IN ('cancelled', 'canceled')
                    THEN 'cancelled'
                    WHEN review_required
                    THEN 'review_required'
                    WHEN auto_target
                     AND target_date IS NOT NULL
                     AND factory_can_receive_date IS NOT NULL
                    THEN 'auto_scheduled'
                    WHEN target_date IS NULL OR factory_can_receive_date IS NULL
                    THEN 'pending'
                    WHEN LOWER(planning_status) IN (
                        'blocked',
                        'partially blocked',
                        'pending replan',
                        'pending planning'
                    )
                    THEN 'pending'
                    WHEN factory_can_receive_date <= target_date
                    THEN 'can_meet'
                    ELSE 'cannot_meet'
                END AS promise_state,
                CASE
                    WHEN review_required OR target_date IS NULL OR factory_can_receive_date IS NULL
                    THEN 0
                    ELSE (target_date - factory_can_receive_date)
                END AS variance_days,
                CASE
                    WHEN total_quantity > 0
                    THEN GREATEST(
                        0,
                        LEAST(
                            100,
                            ROUND((stock_allocated::NUMERIC / total_quantity) * 100, 1)
                        )
                    )
                    ELSE 0
                END AS stock_progress_pct
            FROM shipment_base
        )
        SELECT *
        FROM shipment_ranked
        WHERE {where_sql}
        ORDER BY
            target_date ASC NULLS LAST,
            factory_can_receive_date ASC NULLS LAST,
            shipment_pk ASC
    """

    _emit(progress, 24, "Loading shipment portfolio from PostgreSQL...")
    with engine.begin() as connection:
        raw_rows = connection.execute(text(query), params).mappings().all()

    _emit(progress, 62, "Reading canonical Factory Can Out and delivery state...")
    rows: list[dict[str, Any]] = []
    total_raw = max(1, len(raw_rows))

    for row_index, raw in enumerate(raw_rows):
        row = dict(raw)
        row["factory_out_forecast"] = False
        if row.get("factory_can_receive_date") is not None:
            row["factory_out_source"] = "R6_CANONICAL"
            row["factory_out_confidence"] = 1.0
        elif row.get("review_required"):
            row["factory_out_source"] = "CLOSURE_REVIEW"
            row["factory_out_confidence"] = 0.0
        else:
            row["factory_out_source"] = "PENDING_CANONICAL_REPLAN"
            row["factory_out_confidence"] = 0.0

        target = row.get("target_date")
        factory_out = row.get("factory_can_receive_date")
        if row.get("review_required"):
            row["promise_state"] = "review_required"
            row["variance_days"] = 0
        elif str(row.get("shipment_status") or "").lower() in {
            "cancelled",
            "canceled",
        }:
            row["promise_state"] = "cancelled"
            row["variance_days"] = 0
        elif target is None or factory_out is None:
            row["promise_state"] = "pending"
            row["variance_days"] = 0
        elif row.get("auto_target"):
            row["promise_state"] = "auto_scheduled"
            row["variance_days"] = (target - factory_out).days
        elif factory_out <= target:
            row["promise_state"] = "can_meet"
            row["variance_days"] = (target - factory_out).days
        else:
            row["promise_state"] = "cannot_meet"
            row["variance_days"] = (target - factory_out).days

        profile = shipment_risk_profile(row, as_of_date=as_of_date)
        row.update(
            {
                "risk_score": profile.score,
                "risk_band": profile.band,
                "risk_label": profile.label,
                "production_gap": profile.production_gap,
                "stock_coverage_pct": profile.stock_coverage_pct,
                "days_to_target": profile.days_to_target,
                "delivery_variance_days": profile.delivery_variance_days,
                "recommended_action": profile.action,
                "risk_drivers": profile.risk_drivers,
            }
        )
        rows.append(row)

        if row_index and row_index % 100 == 0:
            pct = 62 + int(14 * (row_index / total_raw))
            _emit(progress, pct, f"Scoring shipments {row_index:,}/{len(raw_rows):,}...")

    if risk_filter == "critical":
        rows = [row for row in rows if row["risk_band"] == "critical"]
    elif risk_filter == "at_risk":
        rows = [
            row
            for row in rows
            if row["risk_band"] in {"critical", "at_risk"}
        ]
    elif risk_filter in {"watch", "healthy", "review"}:
        rows = [row for row in rows if row["risk_band"] == risk_filter]

    risk_rank = {
        "critical": 0,
        "at_risk": 1,
        "review": 2,
        "watch": 3,
        "healthy": 4,
        "cancelled": 5,
    }
    rows.sort(
        key=lambda row: (
            risk_rank.get(str(row.get("risk_band")), 9),
            row.get("target_date") or date.max,
            -int(row.get("risk_score") or 0),
            int(row.get("shipment_pk") or 0),
        )
    )

    _emit(progress, 80, "Aggregating shipment metrics...")
    metrics = portfolio_metrics(rows)
    metrics = dict(metrics)
    metrics["can_meet"] = sum(
        1 for row in rows if row["promise_state"] == "can_meet"
    )
    metrics["cannot_meet"] = sum(
        1 for row in rows if row["promise_state"] == "cannot_meet"
    )

    receive_dates = [
        row["factory_can_receive_date"]
        for row in rows
        if row["factory_can_receive_date"] is not None
        and row["promise_state"] not in {"cancelled"}
    ]
    next_receive_date = min(receive_dates) if receive_dates else None

    _emit(progress, 88, "Preparing responsive table snapshot...")
    return {
        "rows": rows,
        "metrics": metrics,
        "source": source,
        "as_of_date": as_of_date,
        "next_receive_date": next_receive_date,
        "refreshed_at": datetime.now(),
        "filters": filters,
    }

# MPPS R7463 HOTFIX SHIPMENT DETAIL API
def load_shipment_detail(shipment_id: int, *, progress=None):
    shipment_id = int(shipment_id)
    if shipment_id <= 0:
        raise ValueError("A valid shipment id is required.")

    _emit(progress, 10, "Reading shipment header...")
    with engine.connect() as connection:
        shipment = connection.execute(
            text("SELECT * FROM mpps_shipments WHERE id=:id"),
            {"id": shipment_id},
        ).mappings().first()
        if not shipment:
            raise ValueError(f"Shipment {shipment_id} was not found.")

        rows = connection.execute(
            text("SELECT * FROM mpps_shipment_items WHERE shipment_id=:id ORDER BY id"),
            {"id": shipment_id},
        ).mappings().all()

        try:
            source = OperationalSourceService.latest(connection)
        except Exception:
            source = None

    items = []
    for raw in rows:
        item = dict(raw)

        def q(name):
            try:
                return max(0, int(float(item.get(name) or 0)))
            except Exception:
                return 0

        qty = q("quantity")
        stock = min(qty, q("stock_allocated_qty"))
        produced = min(qty, q("produced_qty"))
        completed = min(qty, max(q("completed_qty"), produced))

        item.setdefault("production_required_qty", max(qty - stock - produced, 0))
        item.setdefault("remaining_qty", max(qty - completed, 0))
        item.setdefault("production_start", item.get("start_date"))
        item.setdefault(
            "expected_finish",
            item.get("end_date") or item.get("receive_date") or item.get("item_receive_date"),
        )
        if qty > 0 and completed >= qty:
            item.setdefault("item_status", "COMPLETED")
        elif produced > 0:
            item.setdefault("item_status", "IN PRODUCTION")
        elif qty > 0 and stock >= qty:
            item.setdefault("item_status", "STOCK COVERED")
        else:
            item.setdefault("item_status", "PENDING")
        items.append(item)

    return {
        "shipment": dict(shipment),
        "items": items,
        "source": source,
        "refreshed_at": datetime.now(),
    }

