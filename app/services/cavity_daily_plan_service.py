from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import Decimal
import json
import re
from typing import Any, Callable, Iterable

from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from app.services.operational_source_service import OperationalSourceService

from app.services.process_standard_resolution import (
    build_process_standard_index,
    process_standard_complete,
)

from app.services.master_data_normalization import (
    identifier_key,
    line_identity,
    normalize_casing_type,
    normalize_mold_key,
    normalize_sap_code,
)


# PROCESS STANDARD PLANNING INTEGRITY V6.5
# MPPS ULTRA PERFORMANCE + GLOBAL PROGRESS V7.2

ProgressCallback = Callable[[int, str], None]


def _emit_progress(
    callback: ProgressCallback | None,
    percent: int,
    message: str,
) -> None:
    if callback is None:
        return
    try:
        callback(
            max(0, min(100, int(percent))),
            str(message),
        )
    except Exception:
        # Progress reporting must never stop the production planner.
        pass

OPEN_SHIPMENT_STATUSES = {
    "",
    "open",
    "pending",
    "planned",
    "processing",
    "in progress",
    "saved",
}
CLOSED_SHIPMENT_STATUSES = {
    "cancelled",
    "canceled",
    "closed",
    "complete",
    "completed",
    "shipped",
    "done",
}
NO_CASING_VALUES = {
    "",
    "-",
    "no casing",
    "none",
    "n/a",
    "na",
    "not required",
}
BREAKDOWN_VALUES = {
    "breakdown",
    "broken",
    "inactive",
    "out of service",
    "out-of-service",
    "maintenance",
    "disabled",
}


@dataclass(frozen=True)
class CavityPlanSettings:
    planning_date: date
    day_shift_minutes: int = 720
    night_shift_minutes: int = 720
    changeover_minutes: int = 0

    @property
    def total_minutes(self) -> int:
        return max(
            1,
            int(self.day_shift_minutes)
            + int(self.night_shift_minutes),
        )


@dataclass
class CavityPlanRow:
    cavity_id: int
    line_name: str
    oven_no: str
    oven_status: str
    tyre_code: str = ""
    description: str = ""
    heel: str = "-"
    soft: str = "-"
    tred: str = "-"
    remark: str = "-"
    total_to_be_produced: int = 0
    today_qty: int = 0
    day_plan_pcs: int = 0
    night_plan_pcs: int = 0
    core: str = "-"
    next_day_plan: int = 0
    total: int = 0
    weight_per_tyre_kg: float = 0.0
    day_plan_weight: float = 0.0
    night_plan_weight: float = 0.0
    total_plan: int = 0
    balance: int = 0
    casing_type: str = "-"
    mold_type: str = "-"
    cavity_no: int = 0
    sequence_no: int = 1
    start_minute: int = 0
    end_minute: int = 0
    shift_name: str = ""
    shipment_id: int | None = None
    shipment_item_id: int | None = None
    priority_no: int | None = None
    allocation_status: str = ""
    risk_reason: str = ""


@dataclass(frozen=True)
class BlockedDemand:
    sap_code: str
    description: str
    required_qty: int
    approval_status: str
    reason: str
    due_date: date | None


@dataclass(frozen=True)
class CavityPlanSummary:
    total_cavities: int
    breakdown_cavities: int
    currently_assigned_cavities: int
    planned_cavities: int
    free_cavities: int
    production_required_qty: int
    today_planned_qty: int
    next_day_planned_qty: int
    remaining_balance_qty: int
    planned_tons: float
    blocked_items: int
    warning_items: int
    status_text: str


@dataclass
class _Demand:
    sap_code: str
    description: str
    due_date: date | None
    required_qty: int
    remaining_qty: int
    shipment_id: int | None
    shipment_item_id: int | None
    priority_no: int | None
    approval_status: str
    line_names: set[str]
    mold_type: str
    casing_type: str
    effective_cycle_minutes: int
    weight_per_tyre_kg: float
    heel: str
    soft: str
    tred: str
    remark: str
    core: str
    source: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Cavity:
    cavity_id: int
    line_name: str
    cavity_no: int
    oven_no: str
    database_status: str
    assigned_tyre_item: str
    remarks: str
    is_active: bool
    cursor: int = 0
    last_sap_code: str = ""


@dataclass
class _UnitAllocation:
    cavity_id: int
    line_name: str
    cavity_no: int
    oven_no: str
    sap_code: str
    start_minute: int
    end_minute: int
    shift_name: str
    demand: _Demand


def ensure_cavity_plan_schema(session: Session) -> None:
    session.execute(
        text(
            """
            ALTER TABLE smds
            ADD COLUMN IF NOT EXISTS core TEXT
            """
        )
    )

    session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS database_migrations (
                id BIGSERIAL PRIMARY KEY,
                version VARCHAR(32) UNIQUE NOT NULL,
                description TEXT NOT NULL,
                source_database VARCHAR(128),
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    )
    session.execute(
        text(
            """
            INSERT INTO database_migrations (
                version,
                description,
                source_database
            )
            VALUES (
                '3.0.0',
                'Added cavity-level time-based daily production planning',
                current_database()
            )
            ON CONFLICT (version)
            DO UPDATE SET
                description = EXCLUDED.description,
                source_database = EXCLUDED.source_database,
                applied_at = NOW()
            """
        )
    )

    session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS mpps_cavity_plan_runs (
                id BIGSERIAL PRIMARY KEY,
                plan_date DATE NOT NULL,
                planning_version BIGINT NOT NULL,
                day_shift_minutes INTEGER NOT NULL DEFAULT 720,
                night_shift_minutes INTEGER NOT NULL DEFAULT 720,
                changeover_minutes INTEGER NOT NULL DEFAULT 0,
                status VARCHAR(40) NOT NULL DEFAULT 'Saved',
                source VARCHAR(40) NOT NULL DEFAULT 'AUTO',
                created_by TEXT NOT NULL DEFAULT '',
                summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                blocked_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (plan_date, planning_version)
            )
            """
        )
    )
    session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS mpps_cavity_plan_rows (
                id BIGSERIAL PRIMARY KEY,
                run_id BIGINT NOT NULL
                    REFERENCES mpps_cavity_plan_runs(id)
                    ON DELETE CASCADE,
                plan_date DATE NOT NULL,
                cavity_id BIGINT NOT NULL,
                line_name VARCHAR(255) NOT NULL,
                cavity_no INTEGER NOT NULL,
                oven_no VARCHAR(255) NOT NULL,
                sequence_no INTEGER NOT NULL DEFAULT 1,
                oven_status VARCHAR(40) NOT NULL,
                start_minute INTEGER NOT NULL DEFAULT 0,
                end_minute INTEGER NOT NULL DEFAULT 0,
                shift_name VARCHAR(20) NOT NULL DEFAULT '',
                shipment_id INTEGER,
                shipment_item_id INTEGER,
                tyre_code VARCHAR(128) NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                heel TEXT NOT NULL DEFAULT '-',
                soft TEXT NOT NULL DEFAULT '-',
                tred TEXT NOT NULL DEFAULT '-',
                remark TEXT NOT NULL DEFAULT '-',
                total_to_be_produced INTEGER NOT NULL DEFAULT 0,
                today_qty INTEGER NOT NULL DEFAULT 0,
                day_plan_pcs INTEGER NOT NULL DEFAULT 0,
                night_plan_pcs INTEGER NOT NULL DEFAULT 0,
                core TEXT NOT NULL DEFAULT '-',
                next_day_plan INTEGER NOT NULL DEFAULT 0,
                total_qty INTEGER NOT NULL DEFAULT 0,
                weight_per_tyre_kg NUMERIC(14, 3)
                    NOT NULL DEFAULT 0,
                day_plan_weight NUMERIC(14, 3)
                    NOT NULL DEFAULT 0,
                night_plan_weight NUMERIC(14, 3)
                    NOT NULL DEFAULT 0,
                total_plan INTEGER NOT NULL DEFAULT 0,
                balance INTEGER NOT NULL DEFAULT 0,
                casing_type TEXT NOT NULL DEFAULT '-',
                mold_type TEXT NOT NULL DEFAULT '-',
                allocation_status VARCHAR(40)
                    NOT NULL DEFAULT '',
                risk_reason TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL
                    DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (run_id, cavity_id, sequence_no)
            )
            """
        )
    )
    session.execute(
        text(
            """
            ALTER TABLE mpps_cavity_plan_rows
            ADD COLUMN IF NOT EXISTS priority_no INTEGER
            """
        )
    )

    for statement in [
        (
            "CREATE INDEX IF NOT EXISTS "
            "ix_mpps_cavity_plan_runs_date "
            "ON mpps_cavity_plan_runs(plan_date, created_at DESC)"
        ),
        (
            "CREATE INDEX IF NOT EXISTS "
            "ix_mpps_cavity_plan_rows_run "
            "ON mpps_cavity_plan_rows(run_id)"
        ),
        (
            "CREATE INDEX IF NOT EXISTS "
            "ix_mpps_cavity_plan_rows_date_cavity "
            "ON mpps_cavity_plan_rows(plan_date, cavity_id)"
        ),
        (
            "CREATE INDEX IF NOT EXISTS "
            "ix_mpps_cavity_plan_rows_sap "
            "ON mpps_cavity_plan_rows(tyre_code)"
        ),
        (
            "CREATE INDEX IF NOT EXISTS "
            "ix_mpps_cavity_plan_rows_priority "
            "ON mpps_cavity_plan_rows(plan_date, priority_no, shipment_id)"
        ),
    ]:
        session.execute(text(statement))


def generate_cavity_plan(
    session: Session,
    *,
    settings: CavityPlanSettings,
    progress_callback: ProgressCallback | None = None,
) -> tuple[
    list[CavityPlanRow],
    CavityPlanSummary,
    list[BlockedDemand],
]:
    _emit_progress(progress_callback, 1, "Preparing planner schema")
    ensure_cavity_plan_schema(session)

    _emit_progress(progress_callback, 5, "Loading factory cavities")
    cavities = _load_cavities(session)

    _emit_progress(progress_callback, 10, "Loading approved SMDS master data")
    smds_rows = _load_smds_rows(session)

    _emit_progress(progress_callback, 17, "Loading shipment demand and stock")
    demands, stock_map = _load_production_demands(
        session,
        smds_rows=smds_rows,
    )

    _emit_progress(progress_callback, 24, "Loading mold and casing capacity")
    mold_capacity = _load_mold_capacity(session)
    casing_capacity = _load_casing_capacity(session)

    eligible: list[_Demand] = []
    blocked: list[BlockedDemand] = []
    available_lines = {
        _norm_line(cavity.line_name)
        for cavity in cavities
        if _cavity_operational_status(cavity) == "AVAILABLE / FREE"
    }

    total_demands = max(1, len(demands))
    for index, demand in enumerate(demands, start=1):
        reason = _validate_demand(
            demand,
            mold_capacity=mold_capacity,
            casing_capacity=casing_capacity,
            cavities=cavities,
            available_lines=available_lines,
        )
        if reason:
            blocked.append(
                BlockedDemand(
                    sap_code=demand.sap_code,
                    description=demand.description,
                    required_qty=demand.required_qty,
                    approval_status=demand.approval_status,
                    reason=reason,
                    due_date=demand.due_date,
                )
            )
        else:
            eligible.append(demand)

        if index == total_demands or index % 25 == 0:
            _emit_progress(
                progress_callback,
                25 + int(7 * index / total_demands),
                f"Validating production demand {index}/{total_demands}",
            )

    eligible.sort(key=_demand_sort_key)

    first_day_demands = [
        _copy_demand(demand) for demand in eligible
    ]

    def first_day_progress(local_percent: int, message: str) -> None:
        _emit_progress(
            progress_callback,
            32 + int(local_percent * 0.38),
            f"Today plan — {message}",
        )

    _emit_progress(progress_callback, 32, "Scheduling today's cavities")
    first_units = _schedule_day(
        cavities=cavities,
        demands=first_day_demands,
        settings=settings,
        mold_capacity=mold_capacity,
        casing_capacity=casing_capacity,
        progress_callback=first_day_progress,
    )

    first_remaining = {
        _demand_key(demand): demand.remaining_qty
        for demand in first_day_demands
    }

    next_day_demands: list[_Demand] = []
    for original in eligible:
        remaining = first_remaining.get(
            _demand_key(original),
            original.required_qty,
        )
        if remaining <= 0:
            continue
        copied = _copy_demand(original)
        copied.required_qty = remaining
        copied.remaining_qty = remaining
        next_day_demands.append(copied)

    next_settings = CavityPlanSettings(
        planning_date=date.fromordinal(
            settings.planning_date.toordinal() + 1
        ),
        day_shift_minutes=settings.day_shift_minutes,
        night_shift_minutes=settings.night_shift_minutes,
        changeover_minutes=settings.changeover_minutes,
    )

    def next_day_progress(local_percent: int, message: str) -> None:
        _emit_progress(
            progress_callback,
            70 + int(local_percent * 0.20),
            f"Next-day plan — {message}",
        )

    _emit_progress(progress_callback, 70, "Scheduling next-day cavities")
    next_units = _schedule_day(
        cavities=cavities,
        demands=next_day_demands,
        settings=next_settings,
        mold_capacity=mold_capacity,
        casing_capacity=casing_capacity,
        progress_callback=next_day_progress,
    )

    _emit_progress(progress_callback, 91, "Building production-plan display rows")
    rows = _build_display_rows(
        cavities=cavities,
        first_units=first_units,
        next_units=next_units,
        demands=demands,
        smds_rows=smds_rows,
        settings=settings,
    )

    total_required = sum(max(0, demand.required_qty) for demand in demands)
    total_today = len(first_units)
    total_next = len(next_units)
    total_balance = max(0, total_required - total_today - total_next)

    planned_cavity_ids = {
        unit.cavity_id for unit in first_units
    }
    breakdown_count = sum(
        _cavity_operational_status(cavity)
        == "BREAKDOWN"
        for cavity in cavities
    )
    assigned_count = sum(
        _cavity_operational_status(cavity)
        == "CURRENTLY ASSIGNED"
        for cavity in cavities
    )
    free_count = sum(
        _cavity_operational_status(cavity) == "AVAILABLE / FREE"
        and cavity.cavity_id not in planned_cavity_ids
        for cavity in cavities
    )
    planned_tons = round(
        sum(
            unit.demand.weight_per_tyre_kg
            for unit in first_units
        )
        / 1000.0,
        3,
    )
    warnings = len(blocked) + sum(
        row.oven_status in {
            "BREAKDOWN",
            "CURRENTLY ASSIGNED",
        }
        for row in rows
    )

    if total_required <= 0:
        status_text = "NO PRODUCTION REQUIRED"
    elif total_today <= 0:
        status_text = "UNPLANNED"
    elif total_balance <= 0:
        status_text = "TWO-DAY PLAN COMPLETE"
    elif blocked:
        status_text = "PARTIALLY BLOCKED"
    else:
        status_text = "PARTIALLY PLANNED"

    _emit_progress(progress_callback, 97, "Finalizing production summary")
    summary = CavityPlanSummary(
        total_cavities=len(cavities),
        breakdown_cavities=breakdown_count,
        currently_assigned_cavities=assigned_count,
        planned_cavities=len(planned_cavity_ids),
        free_cavities=free_count,
        production_required_qty=total_required,
        today_planned_qty=total_today,
        next_day_planned_qty=total_next,
        remaining_balance_qty=total_balance,
        planned_tons=planned_tons,
        blocked_items=len(blocked),
        warning_items=warnings,
        status_text=status_text,
    )
    _emit_progress(progress_callback, 100, "Production plan ready")
    return rows, summary, blocked


def save_cavity_plan(
    session: Session,
    *,
    settings: CavityPlanSettings,
    rows: list[CavityPlanRow],
    summary: CavityPlanSummary,
    blocked: list[BlockedDemand],
    created_by: str = "",
) -> int:
    ensure_cavity_plan_schema(session)
    version = int(datetime.utcnow().timestamp() * 1000)

    run_id = int(
        session.execute(
            text(
                """
                INSERT INTO mpps_cavity_plan_runs (
                    plan_date,
                    planning_version,
                    day_shift_minutes,
                    night_shift_minutes,
                    changeover_minutes,
                    status,
                    source,
                    created_by,
                    summary_json,
                    blocked_json
                )
                VALUES (
                    :plan_date,
                    :planning_version,
                    :day_shift_minutes,
                    :night_shift_minutes,
                    :changeover_minutes,
                    'Saved',
                    'AUTO',
                    :created_by,
                    CAST(:summary_json AS JSONB),
                    CAST(:blocked_json AS JSONB)
                )
                RETURNING id
                """
            ),
            {
                "plan_date": settings.planning_date,
                "planning_version": version,
                "day_shift_minutes": (
                    settings.day_shift_minutes
                ),
                "night_shift_minutes": (
                    settings.night_shift_minutes
                ),
                "changeover_minutes": (
                    settings.changeover_minutes
                ),
                "created_by": created_by,
                "summary_json": json.dumps(
                    asdict(summary),
                    default=_json_default,
                ),
                "blocked_json": json.dumps(
                    [asdict(item) for item in blocked],
                    default=_json_default,
                ),
            },
        ).scalar_one()
    )

    insert_sql = text(
        """
        INSERT INTO mpps_cavity_plan_rows (
            run_id,
            plan_date,
            cavity_id,
            line_name,
            cavity_no,
            oven_no,
            sequence_no,
            oven_status,
            start_minute,
            end_minute,
            shift_name,
            shipment_id,
            shipment_item_id,
            priority_no,
            tyre_code,
            description,
            heel,
            soft,
            tred,
            remark,
            total_to_be_produced,
            today_qty,
            day_plan_pcs,
            night_plan_pcs,
            core,
            next_day_plan,
            total_qty,
            weight_per_tyre_kg,
            day_plan_weight,
            night_plan_weight,
            total_plan,
            balance,
            casing_type,
            mold_type,
            allocation_status,
            risk_reason
        )
        VALUES (
            :run_id,
            :plan_date,
            :cavity_id,
            :line_name,
            :cavity_no,
            :oven_no,
            :sequence_no,
            :oven_status,
            :start_minute,
            :end_minute,
            :shift_name,
            :shipment_id,
            :shipment_item_id,
            :priority_no,
            :tyre_code,
            :description,
            :heel,
            :soft,
            :tred,
            :remark,
            :total_to_be_produced,
            :today_qty,
            :day_plan_pcs,
            :night_plan_pcs,
            :core,
            :next_day_plan,
            :total,
            :weight_per_tyre_kg,
            :day_plan_weight,
            :night_plan_weight,
            :total_plan,
            :balance,
            :casing_type,
            :mold_type,
            :allocation_status,
            :risk_reason
        )
        """
    )

    payloads = []
    for row in rows:
        payload = asdict(row)
        payload["run_id"] = run_id
        payload["plan_date"] = settings.planning_date
        payloads.append(payload)

    if payloads:
        session.execute(insert_sql, payloads)

    return run_id


def load_latest_saved_plan(
    session: Session,
    *,
    planning_date: date,
) -> tuple[
    list[CavityPlanRow],
    CavityPlanSummary,
    list[BlockedDemand],
    CavityPlanSettings,
    int,
] | None:
    ensure_cavity_plan_schema(session)

    run = session.execute(
        text(
            """
            SELECT *
            FROM mpps_cavity_plan_runs
            WHERE plan_date = :plan_date
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ),
        {"plan_date": planning_date},
    ).mappings().first()

    if not run:
        return None

    row_records = session.execute(
        text(
            """
            SELECT *
            FROM mpps_cavity_plan_rows
            WHERE run_id = :run_id
            ORDER BY
                line_name,
                cavity_no,
                sequence_no,
                id
            """
        ),
        {"run_id": int(run["id"])},
    ).mappings().all()

    rows = [
        CavityPlanRow(
            cavity_id=int(record["cavity_id"]),
            line_name=str(record["line_name"]),
            oven_no=str(record["oven_no"]),
            oven_status=str(record["oven_status"]),
            tyre_code=str(record["tyre_code"] or ""),
            description=str(record["description"] or ""),
            heel=str(record["heel"] or "-"),
            soft=str(record["soft"] or "-"),
            tred=str(record["tred"] or "-"),
            remark=str(record["remark"] or "-"),
            total_to_be_produced=int(
                record["total_to_be_produced"] or 0
            ),
            today_qty=int(record["today_qty"] or 0),
            day_plan_pcs=int(
                record["day_plan_pcs"] or 0
            ),
            night_plan_pcs=int(
                record["night_plan_pcs"] or 0
            ),
            core=str(record["core"] or "-"),
            next_day_plan=int(
                record["next_day_plan"] or 0
            ),
            total=int(record["total_qty"] or 0),
            weight_per_tyre_kg=float(
                record["weight_per_tyre_kg"] or 0
            ),
            day_plan_weight=float(
                record["day_plan_weight"] or 0
            ),
            night_plan_weight=float(
                record["night_plan_weight"] or 0
            ),
            total_plan=int(record["total_plan"] or 0),
            balance=int(record["balance"] or 0),
            casing_type=str(
                record["casing_type"] or "-"
            ),
            mold_type=str(record["mold_type"] or "-"),
            cavity_no=int(record["cavity_no"] or 0),
            sequence_no=int(record["sequence_no"] or 1),
            start_minute=int(record["start_minute"] or 0),
            end_minute=int(record["end_minute"] or 0),
            shift_name=str(record["shift_name"] or ""),
            shipment_id=record["shipment_id"],
            shipment_item_id=record["shipment_item_id"],
            priority_no=(int(record["priority_no"]) if record.get("priority_no") is not None else None),
            allocation_status=str(
                record["allocation_status"] or ""
            ),
            risk_reason=str(record["risk_reason"] or ""),
        )
        for record in row_records
    ]

    raw_summary = run["summary_json"] or {}
    if isinstance(raw_summary, str):
        raw_summary = json.loads(raw_summary)
    summary = CavityPlanSummary(
        total_cavities=int(
            raw_summary.get("total_cavities", 0)
        ),
        breakdown_cavities=int(
            raw_summary.get("breakdown_cavities", 0)
        ),
        currently_assigned_cavities=int(
            raw_summary.get(
                "currently_assigned_cavities",
                0,
            )
        ),
        planned_cavities=int(
            raw_summary.get("planned_cavities", 0)
        ),
        free_cavities=int(
            raw_summary.get("free_cavities", 0)
        ),
        production_required_qty=int(
            raw_summary.get(
                "production_required_qty",
                0,
            )
        ),
        today_planned_qty=int(
            raw_summary.get("today_planned_qty", 0)
        ),
        next_day_planned_qty=int(
            raw_summary.get(
                "next_day_planned_qty",
                0,
            )
        ),
        remaining_balance_qty=int(
            raw_summary.get(
                "remaining_balance_qty",
                0,
            )
        ),
        planned_tons=float(
            raw_summary.get("planned_tons", 0.0)
        ),
        blocked_items=int(
            raw_summary.get("blocked_items", 0)
        ),
        warning_items=int(
            raw_summary.get("warning_items", 0)
        ),
        status_text=str(
            raw_summary.get("status_text", "SAVED")
        ),
    )

    raw_blocked = run["blocked_json"] or []
    if isinstance(raw_blocked, str):
        raw_blocked = json.loads(raw_blocked)
    blocked = [
        BlockedDemand(
            sap_code=str(item.get("sap_code", "")),
            description=str(
                item.get("description", "")
            ),
            required_qty=int(
                item.get("required_qty", 0)
            ),
            approval_status=str(
                item.get("approval_status", "")
            ),
            reason=str(item.get("reason", "")),
            due_date=_parse_date(
                item.get("due_date")
            ),
        )
        for item in raw_blocked
    ]

    settings = CavityPlanSettings(
        planning_date=planning_date,
        day_shift_minutes=int(
            run["day_shift_minutes"] or 720
        ),
        night_shift_minutes=int(
            run["night_shift_minutes"] or 720
        ),
        changeover_minutes=int(
            run["changeover_minutes"] or 0
        ),
    )
    return (
        rows,
        summary,
        blocked,
        settings,
        int(run["id"]),
    )


def _load_cavities(session: Session) -> list[_Cavity]:
    records = session.execute(
        text(
            """
            SELECT *
            FROM production_line_cavities
            ORDER BY
                line_name,
                COALESCE(display_order, cavity_no),
                cavity_no,
                id
            """
        )
    ).mappings().all()

    cavities: list[_Cavity] = []
    for record in records:
        data = dict(record)
        line_name = str(
            data.get("line_name") or ""
        ).strip()
        cavity_no = _to_int(data.get("cavity_no"))
        oven_no = str(
            data.get("cavity_code") or ""
        ).strip()
        if not oven_no:
            oven_no = (
                f"{line_name}-"
                f"{cavity_no:03d}"
            )

        cavities.append(
            _Cavity(
                cavity_id=_to_int(data.get("id")),
                line_name=line_name,
                cavity_no=cavity_no,
                oven_no=oven_no,
                database_status=str(
                    data.get("status") or "Active"
                ).strip(),
                assigned_tyre_item=str(
                    data.get("assigned_tyre_item") or ""
                ).strip(),
                remarks=str(
                    data.get("remarks") or ""
                ).strip(),
                is_active=bool(
                    data.get("is_active", True)
                ),
            )
        )
    return cavities


def _load_smds_rows(
    session: Session,
) -> dict[str, dict[str, Any]]:
    rows = session.execute(
        text("SELECT * FROM smds")
    ).mappings().all()
    return {
        _norm_code(row["sap_code"]): dict(row)
        for row in rows
        if row.get("sap_code")
    }


def _load_production_demands(
    session: Session,
    *,
    smds_rows: dict[str, dict[str, Any]],
) -> tuple[list[_Demand], dict[str, int]]:
    """Load one demand per shipment item in shipment-priority order."""
    item_rows = session.execute(text("""
        WITH ranked_shipments AS (
            SELECT
                shipment.*,
                ROW_NUMBER() OVER (
                    ORDER BY
                        CASE
                            WHEN COALESCE(shipment.target_date_is_manual, FALSE) THEN 0
                            WHEN shipment.target_date IS NOT NULL
                             AND shipment.target_date < DATE '2060-01-01'
                             AND LOWER(COALESCE(shipment.target_date_source,'')) NOT LIKE 'auto%'
                             AND LOWER(COALESCE(shipment.target_date_source,'')) NOT LIKE 'automatic%'
                            THEN 0
                            ELSE 1
                        END,
                        CASE
                            WHEN NOT COALESCE(shipment.target_date_is_manual, FALSE)
                             AND shipment.target_date >= DATE '2060-01-01'
                            THEN NULL
                            ELSE shipment.target_date
                        END ASC NULLS LAST,
                        COALESCE(shipment.created_at, CURRENT_TIMESTAMP),
                        shipment.id
                )::INTEGER AS dynamic_priority_no
            FROM mpps_shipments shipment
            WHERE LOWER(TRIM(COALESCE(shipment.status, 'Planned'))) NOT IN (
                'cancelled', 'canceled', 'closed', 'complete',
                'completed', 'shipped', 'done', 'hold', 'on hold'
            )
              AND UPPER(COALESCE(shipment.lifecycle_status,'ACTIVE')) NOT IN (
                'SHIPPED','CANCELLED','HOLD','CLOSURE_REVIEW'
              )
        )
        SELECT
            item.id AS shipment_item_id,
            shipment.id AS shipment_id,
            shipment.dynamic_priority_no AS priority_no,
            TRIM(item.sap_code) AS sap_code,
            COALESCE(NULLIF(TRIM(item.item_description), ''), '') AS item_description,
            GREATEST(COALESCE(item.quantity, 0), 0) AS order_qty,
            GREATEST(COALESCE(item.produced_qty, 0), 0) AS produced_qty,
            COALESCE(
                CASE
                    WHEN NOT COALESCE(shipment.target_date_is_manual, FALSE)
                     AND shipment.target_date >= DATE '2060-01-01'
                    THEN NULL
                    ELSE shipment.target_date
                END,
                shipment.factory_out_date,
                CASE
                    WHEN NOT COALESCE(shipment.target_date_is_manual, FALSE)
                     AND shipment.plan_date >= DATE '2060-01-01'
                    THEN NULL
                    ELSE shipment.plan_date
                END,
                shipment.shipment_date
            ) AS due_date,
            COALESCE(shipment.target_date_is_manual, FALSE) AS target_date_is_manual,
            COALESCE(shipment.status, 'Planned') AS shipment_status
        FROM mpps_shipment_items item
        JOIN ranked_shipments shipment ON shipment.id = item.shipment_id
        WHERE TRIM(COALESCE(item.sap_code, '')) <> ''
          AND COALESCE(item.quantity, 0) > 0
        ORDER BY shipment.dynamic_priority_no, item.id
    """)).mappings().all()

    stock_map = _load_stock_map(session)
    stock_remaining = dict(stock_map)
    process_standard_index = build_process_standard_index(
        smds_rows.values()
    )
    demands: list[_Demand] = []
    for raw in item_rows:
        row = dict(raw)
        sap_code = normalize_sap_code(
            row.get("sap_code")
        )
        key = _norm_code(sap_code)
        net_qty = max(0, _to_int(row.get("order_qty")) - _to_int(row.get("produced_qty")))
        available_stock = stock_remaining.get(key, 0)
        stock_used = min(net_qty, available_stock)
        stock_remaining[key] = max(0, available_stock - stock_used)
        production_qty = max(0, net_qty - stock_used)
        if production_qty <= 0:
            continue
        smds = dict(smds_rows.get(key, {}))
        if smds and not process_standard_complete(smds):
            resolution = process_standard_index.resolve(
                smds
            )
            if resolution:
                smds.update(
                    resolution.as_smds_values()
                )
        description = str(_pick(smds, "material_description", "item_description", "description") or row.get("item_description") or sap_code).strip()
        approval = str(_pick(smds, "planning_manager_approval_status", "approval_status") or "Pending").strip()
        line_names = _compatible_lines(smds)
        mold_type = normalize_mold_key(
            _pick(
                smds,
                "key_code",
                "mold_key_code",
                "mould_key_code",
            )
        )
        casing_type = normalize_casing_type(
            _pick(
                smds,
                "casing_type",
                "casing",
            )
            or "No Casing"
        )
        demands.append(_Demand(
            sap_code=sap_code,
            description=description,
            due_date=row.get("due_date"),
            required_qty=production_qty,
            remaining_qty=production_qty,
            shipment_id=row.get("shipment_id"),
            shipment_item_id=row.get("shipment_item_id"),
            priority_no=_to_int(row.get("priority_no")) or None,
            approval_status=approval,
            line_names=line_names,
            mold_type=mold_type,
            casing_type=casing_type,
            effective_cycle_minutes=_effective_cycle_minutes(smds),
            weight_per_tyre_kg=_to_float(_pick(smds, "weight_per_tyre_kg", "weight", "tyre_weight", "average_weight")),
            heel=_display(_pick(smds, "heel")),
            soft=_display(_pick(smds, "soft")),
            tred=_display(_pick(smds, "tred", "tread")),
            remark=_display(_pick(smds, "remark", "remarks")),
            core=_display(_pick(smds, "core", "core_type", "core_qty")),
            source=smds,
        ))
    return demands, stock_map

def _load_stock_map(
    session: Session,
) -> dict[str, int]:
    has_snapshot = bool(
        session.execute(
            text("SELECT to_regclass('public.mpps_current_stock_snapshots') IS NOT NULL")
        ).scalar()
    )
    if has_snapshot:
        source = OperationalSourceService.latest(session)
        if source.import_run_id is not None:
            rows = session.execute(
                text(
                    """
                    SELECT TRIM(sap_code) AS sap_code,
                           GREATEST(COALESCE(current_stock,0),0) AS available_qty
                    FROM mpps_current_stock_snapshots
                    WHERE import_run_id=:run_id
                    """
                ),
                {"run_id": int(source.import_run_id)},
            ).mappings().all()
            if rows:
                return {
                    _norm_code(row["sap_code"]): _to_int(row["available_qty"])
                    for row in rows
                    if row.get("sap_code")
                }

    rows = session.execute(
        text(
            """
            SELECT
                TRIM(sap_code) AS sap_code,
                GREATEST(
                    COALESCE(fg_stock, 0)
                    + COALESCE(qc_stock, 0)
                    - COALESCE(scrap_stock, 0)
                    - COALESCE(blocked_stock, 0),
                    0
                ) AS available_qty
            FROM mpps_sap_stock_items
            """
        )
    ).mappings().all()
    return {
        _norm_code(row["sap_code"]): _to_int(row["available_qty"])
        for row in rows
        if row.get("sap_code")
    }


def _load_mold_capacity(
    session: Session,
) -> dict[str, int]:
    rows = session.execute(
        text("SELECT * FROM mold_master")
    ).mappings().all()
    capacities: dict[str, int] = {}
    for raw in rows:
        row = dict(raw)
        key = _norm_resource(
            _pick(
                row,
                "mold_key_code",
                "mould_key_code",
                "key_code",
            )
        )
        if not key:
            continue
        status = _norm_resource(
            _pick(row, "status") or "Active"
        )
        is_active = bool(row.get("is_active", True))
        if (
            not is_active
            or status in BREAKDOWN_VALUES
        ):
            capacities[key] = 0
            continue

        total = _to_int(
            _pick(
                row,
                "mold_count",
                "total_mold_count",
            )
        )
        unavailable = (
            _to_int(
                _pick(
                    row,
                    "production_mold_count",
                )
            )
            + _to_int(
                _pick(
                    row,
                    "breakdown_mold_count",
                )
            )
            + _to_int(
                _pick(
                    row,
                    "planning_reserved_mold_count",
                )
            )
        )
        capacities[key] = max(
            capacities.get(key, 0),
            max(0, total - unavailable),
        )
    return capacities


def _load_casing_capacity(
    session: Session,
) -> dict[str, int]:
    """Load physical free casing capacity without double-counting.

    casing_units is authoritative when physical unit records exist.
    casing_master is a legacy fallback only for types without unit rows.
    mold_master.casing_count is not treated as live casing inventory.
    """
    capacities: dict[str, int] = {}
    types_with_units: set[str] = set()

    unit_rows = session.execute(
        text(
            """
            SELECT
                casing_type,
                COUNT(*) FILTER (
                    WHERE LOWER(
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
                ) AS available_count,
                COUNT(*) AS total_count
            FROM casing_units
            GROUP BY casing_type
            """
        )
    ).mappings().all()

    for row in unit_rows:
        key = _norm_resource(
            row["casing_type"]
        )
        if not key:
            continue
        types_with_units.add(key)
        capacities[key] = max(
            0,
            _to_int(row["available_count"]),
        )

    master_rows = session.execute(
        text(
            """
            SELECT *
            FROM casing_master
            """
        )
    ).mappings().all()

    for raw in master_rows:
        row = dict(raw)
        casing_value = _pick(
            row,
            "casing_type",
            "casing_code",
        )
        key = _norm_resource(
            casing_value
        )

        if (
            not key
            or not _casing_required(
                str(casing_value or "")
            )
        ):
            continue

        if key in types_with_units:
            continue

        status = _norm_resource(
            _pick(row, "status")
            or "Active"
        )
        is_active = bool(
            row.get("is_active", True)
        )

        if (
            not is_active
            or status in BREAKDOWN_VALUES
        ):
            capacities[key] = 0
            continue

        available = _to_int(
            row.get(
                "available_casing_count"
            )
        )

        if available <= 0:
            total = max(
                _to_int(
                    row.get(
                        "total_casing_count"
                    )
                ),
                _to_int(
                    row.get("casing_count")
                ),
            )
            unavailable = (
                _to_int(
                    row.get(
                        "production_casing_count"
                    )
                )
                + _to_int(
                    row.get(
                        "breakdown_casing_count"
                    )
                )
                + _to_int(
                    row.get(
                        "planning_reserved_casing_count"
                    )
                )
            )
            available = max(
                0,
                total - unavailable,
            )

        capacities[key] = max(
            0,
            available,
        )

    return capacities

def _validate_demand(
    demand: _Demand,
    *,
    mold_capacity: dict[str, int],
    casing_capacity: dict[str, int],
    cavities: list[_Cavity],
    available_lines: set[str] | None = None,
) -> str:
    if not demand.source:
        return "SMDS technical data was not found."
    # Planning-manager approval is intentionally non-blocking.  Cavity
    # feasibility is validated from technical/process/resource evidence only.
    if not demand.line_names:
        return "No compatible production line is defined."
    if demand.effective_cycle_minutes <= 0:
        return (
            "Curing cycle and handling time are missing "
            "or invalid."
        )
    mold_key = _norm_resource(demand.mold_type)
    if not mold_key:
        return "Mold type is missing in SMDS."
    if mold_capacity.get(mold_key, 0) <= 0:
        return (
            "No available mold matches the SMDS mold type."
        )
    if _casing_required(demand.casing_type):
        casing_key = _norm_resource(
            demand.casing_type
        )
        if casing_capacity.get(casing_key, 0) <= 0:
            return (
                "No available casing matches the SMDS "
                "casing type."
            )
    if available_lines is None:
        available_lines = {
            _norm_line(cavity.line_name)
            for cavity in cavities
            if _cavity_operational_status(cavity) == "AVAILABLE / FREE"
        }
    if not (
        {
            _norm_line(line)
            for line in demand.line_names
        }
        & available_lines
    ):
        return (
            "No active free cavity matches the compatible "
            "production line."
        )
    return ""


def _schedule_day(
    *,
    cavities: list[_Cavity],
    demands: list[_Demand],
    settings: CavityPlanSettings,
    mold_capacity: dict[str, int],
    casing_capacity: dict[str, int],
    progress_callback: ProgressCallback | None = None,
) -> list[_UnitAllocation]:
    """Plan fixed factory shifts with indexed compatible-demand scanning.

    V7.2 preserves the original candidate ordering, resource-concurrency rules
    and same-SAP cavity reuse. The expensive all-demands scan is replaced by a
    per-line candidate index rebuilt from the same globally sorted demand list.
    """
    states = [
        _Cavity(**asdict(cavity))
        for cavity in cavities
        if _cavity_operational_status(cavity)
        == "AVAILABLE / FREE"
    ]
    states.sort(
        key=lambda cavity: (
            _norm_line(cavity.line_name),
            cavity.cavity_no,
            cavity.cavity_id,
        )
    )

    mold_intervals: dict[
        str,
        list[tuple[int, int]],
    ] = defaultdict(list)
    casing_intervals: dict[
        str,
        list[tuple[int, int]],
    ] = defaultdict(list)
    allocations: list[_UnitAllocation] = []

    active_demands = [
        demand
        for demand in demands
        if demand.remaining_qty > 0
    ]
    active_demands.sort(key=_demand_sort_key)

    # Static normalization is intentionally done once outside the hot loops.
    cavity_line_key = {
        cavity.cavity_id: _norm_line(cavity.line_name)
        for cavity in states
    }
    demand_line_keys = {
        id(demand): {
            _norm_line(line)
            for line in demand.line_names
        }
        for demand in active_demands
    }
    demand_mold_key = {
        id(demand): _norm_resource(demand.mold_type)
        for demand in active_demands
    }
    demand_casing_key = {
        id(demand): (
            _norm_resource(demand.casing_type)
            if _casing_required(demand.casing_type)
            else ""
        )
        for demand in active_demands
    }

    total_requested_units = max(
        1,
        sum(demand.remaining_qty for demand in active_demands),
    )
    _emit_progress(progress_callback, 0, "Preparing cavity/resource indexes")

    day_enabled = int(settings.day_shift_minutes) > 0
    night_enabled = int(settings.night_shift_minutes) > 0

    shift_windows: list[tuple[str, int, int]] = []
    if day_enabled:
        shift_windows.append(("DAY", 0, 720))
    if night_enabled:
        shift_windows.append(("NIGHT", 720, 1440))

    for shift_index, (shift_name, shift_start, shift_end) in enumerate(
        shift_windows,
        start=1,
    ):
        if not active_demands:
            break

        for cavity in states:
            cavity.cursor = shift_start

        while active_demands:
            # Same dynamic demand ordering as V7.1, but one compatible-line
            # index prevents every cavity from scanning every demand.
            active_demands.sort(key=_demand_sort_key)
            compatible_by_line: dict[
                str,
                list[tuple[int, _Demand]],
            ] = defaultdict(list)
            for priority, demand in enumerate(active_demands):
                for line_key in demand_line_keys.get(id(demand), set()):
                    compatible_by_line[line_key].append(
                        (priority, demand)
                    )

            best: tuple[
                tuple[Any, ...],
                _Cavity,
                _Demand,
                int,
                int,
            ] | None = None

            for cavity in states:
                if cavity.cursor >= shift_end:
                    continue

                line_key = cavity_line_key.get(
                    cavity.cavity_id,
                    _norm_line(cavity.line_name),
                )
                candidates = compatible_by_line.get(
                    line_key,
                    (),
                )

                for priority, demand in candidates:
                    if demand.remaining_qty <= 0:
                        continue

                    changeover = (
                        settings.changeover_minutes
                        if cavity.last_sap_code
                        and cavity.last_sap_code != demand.sap_code
                        else 0
                    )
                    requested_start = max(
                        shift_start,
                        cavity.cursor + changeover,
                    )
                    duration = demand.effective_cycle_minutes
                    mold_key = demand_mold_key[id(demand)]
                    casing_key = demand_casing_key[id(demand)]

                    start = _find_resource_start(
                        requested_start=requested_start,
                        duration=duration,
                        total_minutes=shift_end,
                        mold_key=mold_key,
                        mold_capacity=mold_capacity.get(mold_key, 0),
                        mold_intervals=mold_intervals,
                        casing_key=casing_key,
                        casing_capacity=(
                            casing_capacity.get(casing_key, 0)
                            if casing_key
                            else 10**9
                        ),
                        casing_intervals=casing_intervals,
                    )
                    if start is None or start < shift_start:
                        continue

                    if cavity.last_sap_code == demand.sap_code:
                        reuse_rank = 0
                    elif cavity.last_sap_code:
                        reuse_rank = 1
                    else:
                        reuse_rank = 2

                    candidate_key = (
                        start,
                        reuse_rank,
                        priority,
                        _demand_sort_key(demand),
                        line_key,
                        cavity.cavity_no,
                        cavity.cavity_id,
                    )
                    candidate = (
                        candidate_key,
                        cavity,
                        demand,
                        start,
                        changeover,
                    )
                    if best is None or candidate_key < best[0]:
                        best = candidate

            if best is None:
                break

            (
                _candidate_key,
                cavity,
                demand,
                start,
                _changeover,
            ) = best
            end = start + demand.effective_cycle_minutes

            if end > shift_end:
                cavity.cursor = shift_end
                continue

            mold_key = demand_mold_key[id(demand)]
            mold_intervals[mold_key].append((start, end))
            casing_key = demand_casing_key[id(demand)]
            if casing_key:
                casing_intervals[casing_key].append((start, end))

            allocations.append(
                _UnitAllocation(
                    cavity_id=cavity.cavity_id,
                    line_name=cavity.line_name,
                    cavity_no=cavity.cavity_no,
                    oven_no=cavity.oven_no,
                    sap_code=demand.sap_code,
                    start_minute=start,
                    end_minute=end,
                    shift_name=shift_name,
                    demand=demand,
                )
            )
            cavity.cursor = end
            cavity.last_sap_code = demand.sap_code
            demand.remaining_qty -= 1

            active_demands = [
                item
                for item in active_demands
                if item.remaining_qty > 0
            ]

            if len(allocations) % 4 == 0:
                allocation_percent = min(
                    96,
                    int(100 * len(allocations) / total_requested_units),
                )
                _emit_progress(
                    progress_callback,
                    allocation_percent,
                    (
                        f"{shift_name} shift — allocated "
                        f"{len(allocations):,} pcs"
                    ),
                )

        if shift_windows:
            _emit_progress(
                progress_callback,
                min(98, int(100 * shift_index / len(shift_windows))),
                f"{shift_name} shift completed",
            )

    _emit_progress(
        progress_callback,
        100,
        f"Allocated {len(allocations):,} cavity cycles",
    )
    return allocations


def _find_resource_start(
    *,
    requested_start: int,
    duration: int,
    total_minutes: int,
    mold_key: str,
    mold_capacity: int,
    mold_intervals: dict[
        str,
        list[tuple[int, int]],
    ],
    casing_key: str,
    casing_capacity: int,
    casing_intervals: dict[
        str,
        list[tuple[int, int]],
    ],
) -> int | None:
    if duration <= 0:
        return None
    if mold_capacity <= 0:
        return None
    if casing_key and casing_capacity <= 0:
        return None

    start = max(0, requested_start)
    while start + duration <= total_minutes:
        end = start + duration
        mold_conflicts = _overlapping_intervals(
            mold_intervals.get(mold_key, []),
            start,
            end,
        )
        casing_conflicts = (
            _overlapping_intervals(
                casing_intervals.get(
                    casing_key,
                    [],
                ),
                start,
                end,
            )
            if casing_key
            else []
        )

        mold_ok = _interval_capacity_available(
            mold_conflicts,
            start,
            end,
            mold_capacity,
        )
        casing_ok = (
            not casing_key
            or _interval_capacity_available(
                casing_conflicts,
                start,
                end,
                casing_capacity,
            )
        )
        if mold_ok and casing_ok:
            return start

        next_times = [
            conflict_end
            for _conflict_start, conflict_end
            in mold_conflicts + casing_conflicts
            if conflict_end > start
        ]
        if not next_times:
            start += 1
        else:
            start = min(next_times)
    return None



def _interval_capacity_available(
    intervals: list[tuple[int, int]],
    start: int,
    end: int,
    capacity: int,
) -> bool:
    """Return True when one additional interval fits for its full span."""
    if capacity <= 0:
        return False
    if not intervals:
        return True

    points = {start, end}
    for interval_start, interval_end in intervals:
        points.add(max(start, interval_start))
        points.add(min(end, interval_end))

    ordered = sorted(
        point
        for point in points
        if start <= point <= end
    )
    for left, right in zip(ordered, ordered[1:]):
        if right <= left:
            continue
        probe = (left + right) / 2.0
        active = sum(
            interval_start <= probe < interval_end
            for interval_start, interval_end
            in intervals
        )
        if active >= capacity:
            return False
    return True

def _overlapping_intervals(
    intervals: Iterable[tuple[int, int]],
    start: int,
    end: int,
) -> list[tuple[int, int]]:
    return [
        interval
        for interval in intervals
        if interval[0] < end
        and interval[1] > start
    ]


def _build_display_rows(
    *,
    cavities: list[_Cavity],
    first_units: list[_UnitAllocation],
    next_units: list[_UnitAllocation],
    demands: list[_Demand],
    smds_rows: dict[str, dict[str, Any]],
    settings: CavityPlanSettings,
) -> list[CavityPlanRow]:
    grouped: dict[
        int,
        list[list[_UnitAllocation]],
    ] = defaultdict(list)

    for cavity_id, units in _group_by_cavity(
        first_units
    ).items():
        units.sort(
            key=lambda unit: (
                unit.start_minute,
                unit.end_minute,
            )
        )
        current: list[_UnitAllocation] = []
        for unit in units:
            if (
                current
                and current[-1].sap_code
                != unit.sap_code
            ):
                grouped[cavity_id].append(current)
                current = []
            current.append(unit)
        if current:
            grouped[cavity_id].append(current)

    next_by_cavity_demand: dict[
        tuple[int, tuple[Any, ...]],
        int,
    ] = defaultdict(int)
    next_by_demand: dict[tuple[Any, ...], int] = defaultdict(int)
    for unit in next_units:
        key = _demand_key(unit.demand)
        next_by_cavity_demand[(unit.cavity_id, key)] += 1
        next_by_demand[key] += 1

    today_by_demand: dict[tuple[Any, ...], int] = defaultdict(int)
    for unit in first_units:
        today_by_demand[_demand_key(unit.demand)] += 1

    next_assigned: dict[tuple[Any, ...], int] = defaultdict(int)
    rows: list[CavityPlanRow] = []

    for cavity in sorted(
        cavities,
        key=lambda item: (
            _norm_line(item.line_name),
            item.cavity_no,
            item.cavity_id,
        ),
    ):
        operational = _cavity_operational_status(
            cavity
        )
        allocations = grouped.get(
            cavity.cavity_id,
            [],
        )

        if operational == "BREAKDOWN":
            rows.append(
                _blank_cavity_row(
                    cavity,
                    oven_status="BREAKDOWN",
                    risk_reason=(
                        cavity.remarks
                        or cavity.database_status
                    ),
                )
            )
            continue

        if operational == "CURRENTLY ASSIGNED":
            assigned_code = (
                cavity.assigned_tyre_item
            )
            smds = smds_rows.get(
                _norm_code(assigned_code),
                {},
            )
            rows.append(
                CavityPlanRow(
                    cavity_id=cavity.cavity_id,
                    line_name=cavity.line_name,
                    oven_no=cavity.oven_no,
                    oven_status=(
                        "CURRENTLY ASSIGNED"
                    ),
                    tyre_code=assigned_code,
                    description=str(
                        _pick(
                            smds,
                            "material_description",
                        )
                        or ""
                    ),
                    heel=_display(
                        _pick(smds, "heel")
                    ),
                    soft=_display(
                        _pick(smds, "soft")
                    ),
                    tred=_display(
                        _pick(smds, "tred", "tread")
                    ),
                    remark=(
                        cavity.remarks
                        or "Existing operational assignment"
                    ),
                    core=_display(
                        _pick(smds, "core")
                    ),
                    casing_type=_display(
                        _pick(smds, "casing_type")
                    ),
                    mold_type=_display(
                        _pick(smds, "key_code")
                    ),
                    cavity_no=cavity.cavity_no,
                    sequence_no=1,
                    allocation_status=(
                        "CURRENTLY ASSIGNED"
                    ),
                    risk_reason=(
                        "Cavity excluded from automatic "
                        "planning because assigned_tyre_item "
                        "is already set."
                    ),
                )
            )
            continue

        if not allocations:
            rows.append(
                _blank_cavity_row(
                    cavity,
                    oven_status="AVAILABLE / FREE",
                    risk_reason=(
                        "No approved compatible demand "
                        "was allocated."
                    ),
                )
            )
            continue

        for sequence_no, group in enumerate(
            allocations,
            start=1,
        ):
            demand = group[0].demand
            today_qty = len(group)
            day_qty = sum(
                unit.shift_name == "DAY"
                for unit in group
            )
            night_qty = today_qty - day_qty

            demand_key = _demand_key(demand)
            planned_next = next_by_cavity_demand.get(
                (cavity.cavity_id, demand_key),
                0,
            )
            if planned_next <= 0:
                unassigned_next = max(
                    0,
                    next_by_demand.get(demand_key, 0)
                    - next_assigned[demand_key],
                )
                planned_next = unassigned_next if sequence_no == 1 else 0
            next_assigned[demand_key] += planned_next

            total_required = demand.required_qty
            total_today_for_demand = today_by_demand.get(demand_key, 0)
            total_next_for_demand = next_by_demand.get(demand_key, 0)
            balance = max(
                0,
                total_required
                - total_today_for_demand
                - total_next_for_demand,
            )
            total = today_qty + planned_next
            start = group[0].start_minute
            end = group[-1].end_minute
            shift_name = (
                "DAY"
                if night_qty == 0
                else (
                    "NIGHT"
                    if day_qty == 0
                    else "DAY + NIGHT"
                )
            )
            day_units = [
                unit
                for unit in group
                if unit.shift_name == "DAY"
            ]
            night_units = [
                unit
                for unit in group
                if unit.shift_name == "NIGHT"
            ]
            schedule_parts: list[str] = []
            if day_units:
                schedule_parts.append(
                    "DAY "
                    f"{_format_minute(day_units[0].start_minute)}-"
                    f"{_format_minute(day_units[-1].end_minute)}"
                )
            if night_units:
                schedule_parts.append(
                    "NIGHT "
                    f"{_format_minute(night_units[0].start_minute)}-"
                    f"{_format_minute(night_units[-1].end_minute)}"
                )
            schedule_text = "; ".join(
                schedule_parts
            )
            base_remark = (
                ""
                if demand.remark == "-"
                else demand.remark
            )
            remark = "; ".join(
                item
                for item in [
                    base_remark,
                    schedule_text,
                    (
                        f"Due "
                        f"{demand.due_date.isoformat()}"
                        if demand.due_date
                        else "Due date missing"
                    ),
                ]
                if item
            )

            rows.append(
                CavityPlanRow(
                    cavity_id=cavity.cavity_id,
                    line_name=cavity.line_name,
                    oven_no=cavity.oven_no,
                    oven_status="ASSIGNED",
                    tyre_code=demand.sap_code,
                    description=demand.description,
                    heel=demand.heel,
                    soft=demand.soft,
                    tred=demand.tred,
                    remark=remark or "-",
                    total_to_be_produced=(
                        total_required
                    ),
                    today_qty=today_qty,
                    day_plan_pcs=day_qty,
                    night_plan_pcs=night_qty,
                    core=demand.core,
                    next_day_plan=planned_next,
                    total=total,
                    weight_per_tyre_kg=(
                        demand.weight_per_tyre_kg
                    ),
                    day_plan_weight=round(
                        day_qty
                        * demand.weight_per_tyre_kg,
                        3,
                    ),
                    night_plan_weight=round(
                        night_qty
                        * demand.weight_per_tyre_kg,
                        3,
                    ),
                    total_plan=total,
                    balance=balance,
                    casing_type=(
                        demand.casing_type or "-"
                    ),
                    mold_type=(
                        demand.mold_type or "-"
                    ),
                    cavity_no=cavity.cavity_no,
                    sequence_no=sequence_no,
                    start_minute=start,
                    end_minute=end,
                    shift_name=shift_name,
                    shipment_id=demand.shipment_id,
                    shipment_item_id=(
                        demand.shipment_item_id
                    ),
                    priority_no=demand.priority_no,
                    allocation_status="PLANNED",
                    risk_reason=(
                        "Planned with compatible line, "
                        "available mold, casing and cavity "
                        "time."
                    ),
                )
            )
    return rows


def _blank_cavity_row(
    cavity: _Cavity,
    *,
    oven_status: str,
    risk_reason: str,
) -> CavityPlanRow:
    return CavityPlanRow(
        cavity_id=cavity.cavity_id,
        line_name=cavity.line_name,
        oven_no=cavity.oven_no,
        oven_status=oven_status,
        remark=cavity.remarks or "-",
        cavity_no=cavity.cavity_no,
        sequence_no=1,
        allocation_status=oven_status,
        risk_reason=risk_reason,
    )


def _group_by_cavity(
    units: list[_UnitAllocation],
) -> dict[int, list[_UnitAllocation]]:
    grouped: dict[
        int,
        list[_UnitAllocation],
    ] = defaultdict(list)
    for unit in units:
        grouped[unit.cavity_id].append(unit)
    return grouped


def _cavity_operational_status(
    cavity: _Cavity,
) -> str:
    status = _norm_resource(
        cavity.database_status
    )
    if (
        not cavity.is_active
        or status in BREAKDOWN_VALUES
    ):
        return "BREAKDOWN"
    if cavity.assigned_tyre_item.strip():
        return "CURRENTLY ASSIGNED"
    return "AVAILABLE / FREE"


def _compatible_lines(
    smds: dict[str, Any],
) -> set[str]:
    result: set[str] = set()
    line_value = str(
        _pick(smds, "line", "production_line")
        or ""
    )
    for part in re.split(
        r"[,;/|]+",
        line_value,
    ):
        cleaned = part.strip()
        if cleaned and cleaned not in {"-", "0"}:
            result.add(cleaned)

    flag_map = {
        "line_400": "Line-400",
        "line_800": "Line-800",
        "press_line": "Press -LINE",
        "nancy_press": "NANCY PRESS",
        "press_400_t": "400 T PRESS",
        "t_600_01_press": "T 600 -01 PRESS",
        "t_600_02_press": "T 600 -02 PRESS",
        "l_press_1250": "L-PRESS-1250",
        "l_press_1500": "L-PRESS-1500",
        "l_press_1800": "L-PRESS-1800",
        "oring_press": "ORING-PRESS",
        "new_press": "NEW PRESS",
    }
    for column, line_name in flag_map.items():
        value = str(smds.get(column) or "").strip()
        if _truthy_compatibility(value):
            result.add(line_name)
    return result


def _truthy_compatibility(value: str) -> bool:
    normalized = _norm_resource(value)
    return normalized not in {
        "",
        "-",
        "0",
        "no",
        "false",
        "n/a",
        "na",
        "none",
    }


def _effective_cycle_minutes(
    smds: dict[str, Any],
) -> int:
    normal_minutes = _to_int(
        _pick(
            smds,
            "normal_curing_minutes",
            "curing_minutes",
        )
    )
    if normal_minutes <= 0:
        normal_minutes = _parse_duration_minutes(
            _pick(smds, "curing_cycle")
        )
    handling_minutes = _to_int(
        _pick(smds, "handling_time")
    )
    return max(
        0,
        normal_minutes + handling_minutes,
    )


def _parse_duration_minutes(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, (int, float, Decimal)):
        numeric = float(value)
        if numeric <= 0:
            return 0
        # Excel time fractions are represented as a fraction of a day.
        if numeric < 1:
            return int(round(numeric * 24 * 60))
        return int(round(numeric))

    text_value = str(value).strip().lower()
    if not text_value or text_value in {"-", "n/a"}:
        return 0

    hours_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:h|hr|hrs|hour|hours)",
        text_value,
    )
    minutes_match = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:m|min|mins|minute|minutes)",
        text_value,
    )
    hours = (
        float(hours_match.group(1))
        if hours_match
        else 0.0
    )
    minutes = (
        float(minutes_match.group(1))
        if minutes_match
        else 0.0
    )
    if hours or minutes:
        return int(round(hours * 60 + minutes))

    colon_match = re.fullmatch(
        r"\s*(\d{1,2}):(\d{1,2})\s*",
        text_value,
    )
    if colon_match:
        return (
            int(colon_match.group(1)) * 60
            + int(colon_match.group(2))
        )

    compact_match = re.fullmatch(
        r"\s*(\d+)\s*",
        text_value,
    )
    if compact_match:
        return int(compact_match.group(1))
    return 0


def _casing_required(value: str) -> bool:
    return _norm_resource(value) not in {
        _norm_resource(item)
        for item in NO_CASING_VALUES
    }


def _line_compatible(
    line_name: str,
    allowed_lines: set[str],
) -> bool:
    normalized = _norm_line(line_name)
    return normalized in {
        _norm_line(line)
        for line in allowed_lines
    }


def _demand_key(demand: _Demand) -> tuple[Any, ...]:
    if demand.shipment_item_id is not None:
        return ("ITEM", int(demand.shipment_item_id))
    return (
        "FALLBACK",
        int(demand.shipment_id or 0),
        demand.sap_code,
        demand.due_date,
    )


def _demand_sort_key(
    demand: _Demand,
) -> tuple[Any, ...]:
    return (
        demand.priority_no is None,
        demand.priority_no or 10**9,
        demand.due_date is None,
        demand.due_date or date.max,
        -demand.remaining_qty,
        demand.sap_code,
    )


def _copy_demand(demand: _Demand) -> _Demand:
    return _Demand(
        sap_code=demand.sap_code,
        description=demand.description,
        due_date=demand.due_date,
        required_qty=demand.required_qty,
        remaining_qty=demand.remaining_qty,
        shipment_id=demand.shipment_id,
        shipment_item_id=demand.shipment_item_id,
        priority_no=demand.priority_no,
        approval_status=demand.approval_status,
        line_names=set(demand.line_names),
        mold_type=demand.mold_type,
        casing_type=demand.casing_type,
        effective_cycle_minutes=(
            demand.effective_cycle_minutes
        ),
        weight_per_tyre_kg=(
            demand.weight_per_tyre_kg
        ),
        heel=demand.heel,
        soft=demand.soft,
        tred=demand.tred,
        remark=demand.remark,
        core=demand.core,
        source=dict(demand.source),
    )


def _pick(
    mapping: dict[str, Any],
    *names: str,
) -> Any:
    if not mapping:
        return None
    lowered = {
        str(key).lower(): value
        for key, value in mapping.items()
    }
    for name in names:
        value = mapping.get(name)
        if value not in (None, ""):
            return value
        value = lowered.get(name.lower())
        if value not in (None, ""):
            return value
    return None


def _display(value: Any) -> str:
    text_value = str(value or "").strip()
    return text_value if text_value else "-"


def _norm_code(value: Any) -> str:
    return normalize_sap_code(value)


def _norm_resource(value: Any) -> str:
    return identifier_key(value).lower()


def _norm_line(value: Any) -> str:
    return line_identity(value).lower()


def _to_int(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _format_minute(value: int) -> str:
    minute = (420 + max(0, int(value))) % 1440
    hours = minute // 60
    minutes = minute % 60
    return f"{hours:02d}:{minutes:02d}"


def _json_default(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError(
        f"Object of type {type(value).__name__} "
        "is not JSON serializable"
    )


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None

