from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from math import ceil
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session


NO_CASING_VALUES = {
    "",
    "-",
    "no casing",
    "none",
    "n/a",
    "na",
    "not required",
}


@dataclass(frozen=True)
class ExcelOvenPlanRow:
    planning_date: date
    line_name: str
    oven_no: str
    sap_code: str
    description: str
    due_date: date | None
    heel: str
    soft: str
    tread: str
    remark: str
    total_to_be_produced: int
    today_qty: int
    day_plan_qty: int
    night_plan_qty: int
    core: str
    next_day_plan_qty: int
    total_plan_qty: int
    weight_per_tyre_kg: float
    day_plan_weight_kg: float
    night_plan_weight_kg: float
    total_plan_weight_kg: float
    balance_qty: int
    casing_type: str
    mold_key: str
    allocated_cavities: int
    daily_capacity: int
    status: str
    risk_reason: str


@dataclass(frozen=True)
class ExcelOvenPlanSummary:
    production_required_qty: int
    selected_date_planned_qty: int
    remaining_qty_after_selected_date: int
    planned_tons: float
    planned_items: int
    partial_items: int
    blocked_items: int
    missing_weight_items: int
    warning_items: int
    active_lines: int
    used_cavities: int
    status_text: str


def calculate_excel_oven_plan(
    session: Session,
    *,
    planning_date: date,
) -> tuple[list[ExcelOvenPlanRow], ExcelOvenPlanSummary]:
    """Build an Excel OVEN-sheet style plan from the live shipment workflow.

    This reads current mpps_shipments/mpps_shipment_items demand, SAP stock,
    SMDS capacity/mapping and the restored mold, casing and cavity masters.
    It does not overwrite shipment records or imported workbook evidence.
    """

    demand_rows = _load_open_shipment_demand(session)
    smds_map = _load_smds_map(session)
    stock_map = _load_stock_map(session)
    mold_remaining = _load_mold_availability(session)
    casing_remaining = _load_casing_availability(session)
    cavity_pool = _load_free_cavity_pool(session)

    ordered_demand = sorted(
        demand_rows,
        key=lambda row: (
            row.get("due_date") is None,
            row.get("due_date") or date.max,
            -_to_int(row.get("demand_qty")),
            str(row.get("sap_code") or ""),
        ),
    )

    output: list[ExcelOvenPlanRow] = []
    stock_remaining = dict(stock_map)
    used_cavities = 0
    no_casing_norms = {_norm(value) for value in NO_CASING_VALUES}

    for demand in ordered_demand:
        sap_code = str(demand.get("sap_code") or "").strip()
        demand_qty = max(0, _to_int(demand.get("demand_qty")))
        produced_qty = max(0, _to_int(demand.get("produced_qty")))
        net_demand = max(0, demand_qty - produced_qty)

        stock_qty = max(0, stock_remaining.get(sap_code, 0))
        stock_allocated = min(net_demand, stock_qty)
        stock_remaining[sap_code] = max(0, stock_qty - stock_allocated)
        production_required = max(0, net_demand - stock_allocated)

        if production_required <= 0:
            continue

        smds = smds_map.get(_norm(sap_code), {})
        description = str(
            _pick(
                smds,
                "material_description",
                "item_description",
                "description",
            )
            or demand.get("item_description")
            or sap_code
        ).strip()

        line_name = str(
            _pick(
                smds,
                "line",
                "line_name",
                "production_line",
                "machine_line",
            )
            or "UNASSIGNED"
        ).strip()

        mold_key = str(
            _pick(
                smds,
                "key_code",
                "mold_key_code",
                "mould_key_code",
                "mold_key",
            )
            or ""
        ).strip()

        casing_type = str(
            _pick(smds, "casing_type", "casing", "casing_code")
            or "No Casing"
        ).strip()

        approval = str(
            _pick(
                smds,
                "planning_manager_approval_status",
                "approval_status",
                "status",
            )
            or "Pending"
        ).strip()

        day_capacity_raw = _to_float(
            _pick(smds, "day_plan", "day_capacity")
        )
        night_capacity_raw = _to_float(
            _pick(smds, "night_plan", "night_capacity")
        )
        total_capacity_raw = _to_float(
            _pick(
                smds,
                "total_plan",
                "daily_capacity",
                "total_capacity",
            )
        )
        if total_capacity_raw <= 0:
            total_capacity_raw = day_capacity_raw + night_capacity_raw

        weight = _to_float(
            _pick(
                smds,
                "weight",
                "tyre_weight",
                "average_weight",
                "unit_weight",
            )
        )

        heel = _display_optional(
            _pick(smds, "heel", "heel_compound", "heel_material")
        )
        soft = _display_optional(
            _pick(smds, "soft", "soft_compound", "soft_material")
        )
        tread = _display_optional(
            _pick(
                smds,
                "tread",
                "tred",
                "tread_compound",
                "tred_compound",
            )
        )
        core = _display_optional(
            _pick(smds, "core", "core_type", "core_count", "core_qty")
        )

        due_date = demand.get("due_date")
        due_note = (
            f"Due {due_date.isoformat()}"
            if due_date
            else "Due date missing"
        )
        base_remark = str(
            _pick(smds, "remarks", "remark") or ""
        ).strip()
        remark = "; ".join(
            part for part in [base_remark, due_note] if part
        )

        status = "PLANNED"
        risk_parts: list[str] = []
        allocated_cavities = 0
        assigned_codes: list[str] = []
        today_qty = 0
        next_day_qty = 0
        day_qty = 0
        night_qty = 0
        daily_capacity = 0

        normalized_line = _norm(line_name)
        normalized_mold = _norm(mold_key)
        normalized_casing = _norm(casing_type)

        line_cavities = cavity_pool.get(normalized_line, [])
        mold_available = mold_remaining.get(normalized_mold, 0)
        casing_required = normalized_casing not in no_casing_norms
        casing_available = (
            casing_remaining.get(normalized_casing, 0)
            if casing_required
            else 10**9
        )

        if approval.lower() != "approved":
            status = "NOT APPROVED"
            risk_parts.append(
                "Planning manager approval is not Approved"
            )
        elif not smds:
            status = "MISSING SMDS"
            risk_parts.append("SMDS mapping was not found")
        elif total_capacity_raw <= 0:
            status = "MISSING CAPACITY"
            risk_parts.append(
                "SMDS day/night/total capacity is zero"
            )
        elif not mold_key:
            status = "MISSING MOLD"
            risk_parts.append("SMDS mold key is missing")
        elif mold_available <= 0:
            status = "MISSING MOLD"
            risk_parts.append(
                "No available mold matches the SMDS mold key"
            )
        elif not line_name or line_name == "UNASSIGNED":
            status = "MISSING LINE"
            risk_parts.append("SMDS production line is missing")
        elif not line_cavities:
            status = "MISSING CAVITY"
            risk_parts.append(
                "No active free cavity matches the SMDS line"
            )
        elif casing_required and casing_available <= 0:
            status = "MISSING CASING"
            risk_parts.append(
                "No available casing matches the SMDS casing type"
            )
        else:
            available_resources = min(
                mold_available,
                len(line_cavities),
                casing_available,
            )

            if available_resources <= 0:
                status = "BLOCKED"
                risk_parts.append(
                    "Required resources are not available"
                )
            else:
                needed_cavities = max(
                    1,
                    int(
                        ceil(
                            production_required
                            / total_capacity_raw
                        )
                    ),
                )
                allocated_cavities = min(
                    needed_cavities,
                    available_resources,
                )

                daily_capacity = max(
                    1,
                    int(
                        ceil(
                            allocated_cavities
                            * total_capacity_raw
                        )
                    ),
                )
                today_qty = min(
                    production_required,
                    daily_capacity,
                )

                if day_capacity_raw + night_capacity_raw > 0:
                    day_share = (
                        day_capacity_raw
                        / (
                            day_capacity_raw
                            + night_capacity_raw
                        )
                    )
                else:
                    day_share = 0.5

                day_qty = min(
                    today_qty,
                    int(round(today_qty * day_share)),
                )
                night_qty = max(0, today_qty - day_qty)
                remaining_after_today = max(
                    0,
                    production_required - today_qty,
                )
                next_day_qty = min(
                    remaining_after_today,
                    daily_capacity,
                )

                assigned = line_cavities[:allocated_cavities]
                del line_cavities[:allocated_cavities]
                assigned_codes = [
                    code for code in assigned if code
                ]
                used_cavities += allocated_cavities

                mold_remaining[normalized_mold] = max(
                    0,
                    mold_available - allocated_cavities,
                )
                if casing_required:
                    casing_remaining[normalized_casing] = max(
                        0,
                        casing_available - allocated_cavities,
                    )

                status = (
                    "PLANNED"
                    if remaining_after_today == 0
                    else "PARTIAL"
                )
                if status == "PARTIAL":
                    risk_parts.append(
                        f"{remaining_after_today:,} pcs remain "
                        "after selected date"
                    )
                if weight <= 0:
                    risk_parts.append("Tyre weight is missing")

        total_plan_qty = today_qty + next_day_qty
        balance_qty = max(
            0,
            production_required - total_plan_qty,
        )

        output.append(
            ExcelOvenPlanRow(
                planning_date=planning_date,
                line_name=line_name,
                oven_no=_summarize_codes(assigned_codes),
                sap_code=sap_code,
                description=description,
                due_date=due_date,
                heel=heel,
                soft=soft,
                tread=tread,
                remark=remark or "-",
                total_to_be_produced=production_required,
                today_qty=today_qty,
                day_plan_qty=day_qty,
                night_plan_qty=night_qty,
                core=core,
                next_day_plan_qty=next_day_qty,
                total_plan_qty=total_plan_qty,
                weight_per_tyre_kg=weight,
                day_plan_weight_kg=round(
                    day_qty * weight,
                    3,
                ),
                night_plan_weight_kg=round(
                    night_qty * weight,
                    3,
                ),
                total_plan_weight_kg=round(
                    total_plan_qty * weight,
                    3,
                ),
                balance_qty=balance_qty,
                casing_type=casing_type or "No Casing",
                mold_key=mold_key or "-",
                allocated_cavities=allocated_cavities,
                daily_capacity=daily_capacity,
                status=status,
                risk_reason=(
                    "; ".join(risk_parts)
                    or "Planned within available resources"
                ),
            )
        )

    required_total = sum(
        row.total_to_be_produced for row in output
    )
    planned_total = sum(row.today_qty for row in output)
    remaining_total = max(
        0,
        required_total - planned_total,
    )
    planned_tons = round(
        sum(
            row.today_qty * row.weight_per_tyre_kg
            for row in output
        )
        / 1000.0,
        3,
    )
    planned_items = sum(
        row.status == "PLANNED" for row in output
    )
    partial_items = sum(
        row.status == "PARTIAL" for row in output
    )
    blocked_items = sum(
        row.status not in {"PLANNED", "PARTIAL"}
        for row in output
    )
    missing_weight_items = sum(
        row.today_qty > 0
        and row.weight_per_tyre_kg <= 0
        for row in output
    )
    warning_items = sum(
        row.status != "PLANNED"
        or row.risk_reason
        != "Planned within available resources"
        for row in output
    )
    active_lines = len(
        {
            row.line_name
            for row in output
            if row.line_name != "UNASSIGNED"
        }
    )

    if not output:
        status_text = "NO PRODUCTION REQUIRED"
    elif blocked_items == 0 and partial_items == 0:
        status_text = "FULLY PLANNED"
    elif planned_total > 0:
        status_text = "PARTIALLY PLANNED"
    else:
        status_text = "UNPLANNED"

    summary = ExcelOvenPlanSummary(
        production_required_qty=required_total,
        selected_date_planned_qty=planned_total,
        remaining_qty_after_selected_date=remaining_total,
        planned_tons=planned_tons,
        planned_items=planned_items,
        partial_items=partial_items,
        blocked_items=blocked_items,
        missing_weight_items=missing_weight_items,
        warning_items=warning_items,
        active_lines=active_lines,
        used_cavities=used_cavities,
        status_text=status_text,
    )
    return output, summary


def _load_open_shipment_demand(
    session: Session,
) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT
                TRIM(item.sap_code) AS sap_code,
                MAX(
                    NULLIF(
                        TRIM(item.item_description),
                        ''
                    )
                ) AS item_description,
                SUM(
                    GREATEST(
                        COALESCE(item.quantity, 0),
                        0
                    )
                )::INTEGER AS demand_qty,
                SUM(
                    GREATEST(
                        COALESCE(item.produced_qty, 0),
                        0
                    )
                )::INTEGER AS produced_qty,
                MIN(
                    COALESCE(
                        shipment.target_date,
                        shipment.factory_out_date,
                        shipment.plan_date,
                        shipment.shipment_date
                    )
                ) AS due_date
            FROM mpps_shipment_items item
            JOIN mpps_shipments shipment
              ON shipment.id = item.shipment_id
            WHERE TRIM(
                    COALESCE(item.sap_code, '')
                  ) <> ''
              AND COALESCE(item.quantity, 0) > 0
              AND LOWER(
                    TRIM(
                        COALESCE(
                            shipment.status,
                            'planned'
                        )
                    )
                  ) NOT IN (
                    'cancelled',
                    'canceled',
                    'closed',
                    'complete',
                    'completed',
                    'shipped',
                    'done'
                  )
            GROUP BY TRIM(item.sap_code)
            ORDER BY due_date NULLS LAST, sap_code
            """
        )
    ).mappings()
    return [dict(row) for row in rows]


def _load_smds_map(
    session: Session,
) -> dict[str, dict[str, Any]]:
    if not _table_exists(session, "smds"):
        return {}

    rows = session.execute(
        text("SELECT * FROM smds")
    ).mappings()

    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        data = dict(row)
        sap_code = str(
            _pick(
                data,
                "sap_code",
                "material_code",
                "item_code",
                "code",
            )
            or ""
        ).strip()

        if sap_code:
            output[_norm(sap_code)] = data

    return output


def _load_stock_map(
    session: Session,
) -> dict[str, int]:
    if not _table_exists(
        session,
        "mpps_sap_stock_items",
    ):
        return {}

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
                )::INTEGER AS available_qty
            FROM mpps_sap_stock_items
            """
        )
    ).mappings()

    return {
        str(row["sap_code"]): _to_int(
            row["available_qty"]
        )
        for row in rows
        if row["sap_code"]
    }


def _load_mold_availability(
    session: Session,
) -> dict[str, int]:
    if not _table_exists(session, "mold_master"):
        return {}

    rows = session.execute(
        text("SELECT * FROM mold_master")
    ).mappings()

    output: dict[str, int] = {}
    for raw in rows:
        row = dict(raw)
        key = str(
            _pick(
                row,
                "mold_key_code",
                "mould_key_code",
                "key_code",
                "mold_code",
            )
            or ""
        ).strip()

        if not key:
            continue

        total = _to_int(
            _pick(
                row,
                "mold_count",
                "total_mold_count",
                "total_molds",
                "total_count",
            )
        )
        production = _to_int(
            _pick(
                row,
                "production_mold_count",
                "production_count",
            )
        )
        breakdown = _to_int(
            _pick(
                row,
                "breakdown_mold_count",
                "breakdown_count",
            )
        )
        reserved = _to_int(
            _pick(
                row,
                "planning_reserved_mold_count",
                "reserved_mold_count",
            )
        )
        output[_norm(key)] = max(
            0,
            total - production - breakdown - reserved,
        )

    return output


def _load_casing_availability(
    session: Session,
) -> dict[str, int]:
    output: dict[str, int] = {}

    if _table_exists(session, "casing_master"):
        rows = session.execute(
            text("SELECT * FROM casing_master")
        ).mappings()

        for raw in rows:
            row = dict(raw)
            key = str(
                _pick(
                    row,
                    "casing_type",
                    "casing",
                    "casing_code",
                )
                or ""
            ).strip()

            if not key:
                continue

            available = _to_int(
                _pick(
                    row,
                    "available_casing_count",
                    "total_casing_count",
                    "casing_count",
                    "available_count",
                )
            )
            production = _to_int(
                _pick(
                    row,
                    "production_casing_count",
                )
            )
            breakdown = _to_int(
                _pick(
                    row,
                    "breakdown_casing_count",
                )
            )
            reserved = _to_int(
                _pick(
                    row,
                    "planning_reserved_casing_count",
                )
            )

            output[_norm(key)] = max(
                0,
                (
                    available
                    - production
                    - breakdown
                    - reserved
                ),
            )

    if _table_exists(session, "casing_units"):
        unit_rows = session.execute(
            text(
                """
                SELECT
                    casing_type,
                    COUNT(*)::INTEGER AS available_count
                FROM casing_units
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
                GROUP BY casing_type
                """
            )
        ).mappings()

        for row in unit_rows:
            key = _norm(row["casing_type"])
            output[key] = max(
                output.get(key, 0),
                _to_int(row["available_count"]),
            )

    return output


def _load_free_cavity_pool(
    session: Session,
) -> dict[str, list[str]]:
    if not _table_exists(
        session,
        "production_line_cavities",
    ):
        return {}

    rows = session.execute(
        text(
            """
            SELECT
                line_name,
                cavity_no,
                cavity_code
            FROM production_line_cavities
            WHERE LOWER(
                    COALESCE(status, 'Active')
                  ) = 'active'
              AND TRIM(
                    COALESCE(
                        assigned_tyre_item,
                        ''
                    )
                  ) = ''
            ORDER BY line_name, cavity_no
            """
        )
    ).mappings()

    output: dict[str, list[str]] = {}
    for row in rows:
        line_name = str(
            row["line_name"] or ""
        ).strip()

        if not line_name:
            continue

        cavity_code = str(
            row.get("cavity_code") or ""
        ).strip()

        if not cavity_code:
            cavity_code = (
                f"{line_name}-"
                f"{_to_int(row.get('cavity_no')):03d}"
            )

        output.setdefault(
            _norm(line_name),
            [],
        ).append(cavity_code)

    return output


def _table_exists(
    session: Session,
    table_name: str,
) -> bool:
    return bool(
        session.execute(
            text(
                "SELECT "
                "to_regclass(:table_name) IS NOT NULL"
            ),
            {
                "table_name": (
                    f"public.{table_name}"
                )
            },
        ).scalar_one()
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
        if (
            name in mapping
            and mapping[name] is not None
            and mapping[name] != ""
        ):
            return mapping[name]

        value = lowered.get(name.lower())
        if value is not None and value != "":
            return value

    return None


def _display_optional(value: Any) -> str:
    text_value = str(value or "").strip()
    return text_value if text_value else "-"


def _summarize_codes(
    codes: Iterable[str],
) -> str:
    values = [
        str(code).strip()
        for code in codes
        if str(code).strip()
    ]

    if not values:
        return "UNASSIGNED"

    if len(values) <= 3:
        return ", ".join(values)

    return (
        ", ".join(values[:3])
        + f" +{len(values) - 3}"
    )


def _norm(value: Any) -> str:
    return " ".join(
        str(value or "")
        .strip()
        .lower()
        .split()
    )


def _to_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _to_float(value: Any) -> float:
    try:
        if value is None or value == "":
            return 0.0
        if isinstance(value, Decimal):
            return float(value)
        return float(value)
    except (TypeError, ValueError):
        return 0.0
