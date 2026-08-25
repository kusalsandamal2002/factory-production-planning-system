from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import re
from typing import Any, Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.production_requirement_service import load_production_requirements


DEMAND_BASIS_OVEN = "OVEN_DAY_NIGHT"
DEMAND_BASIS_SHORTAGE = "SHIPMENT_SHORTAGE"


@dataclass(frozen=True)
class PlanningAssumptions:
    compound_allowance_rate: float = 0.25
    band_allowance_rate: float = 0.15
    day_shift_share: float = 0.50
    source: str = "OVEN workbook / visible planning assumption"


@dataclass(frozen=True)
class MaterialDemandRow:
    material_code: str
    item_description: str
    planned_qty: int
    day_qty: int
    night_qty: int
    source: str


@dataclass(frozen=True)
class MaterialRequirementRow:
    finished_item_code: str
    finished_item_description: str
    production_required_qty: int
    day_production_qty: int
    night_production_qty: int
    component_type: str
    raw_material_code: str
    raw_material_name: str
    planning_key: str
    usage_per_unit: float
    base_required_qty: float
    allowance_rate: float
    required_qty: float
    day_required_qty: float
    night_required_qty: float
    unit: str
    demand_source: str
    master_source: str
    warning: str


@dataclass(frozen=True)
class ExcelMaterialPlanRow:
    plan_date: date | None
    material_type: str
    material_key: str
    material_description: str
    day_qty: float
    night_qty: float
    total_qty: float
    produced_qty: float
    stock_qty: float
    next_day_qty: float
    unit: str
    source: str
    workbook_name: str

    @property
    def net_gap_qty(self) -> float:
        return round(
            max(self.total_qty - max(self.stock_qty, 0.0) - max(self.produced_qty, 0.0), 0.0),
            6,
        )


@dataclass(frozen=True)
class ConsolidatedMaterialRow:
    component_type: str
    material_code: str
    material_name: str
    planning_key: str
    unit: str
    calculated_required_qty: float
    excel_plan_qty: float
    excel_stock_qty: float
    excel_produced_qty: float
    excel_next_day_qty: float
    net_to_prepare_qty: float
    variance_qty: float
    finished_item_count: int
    warning_count: int
    status: str
    source: str


_PSEUDO_BOM_NAMES = {
    "compound weight",
    "bead wire weight",
    "total tyre weight",
    "total tire weight",
    "band",
    "bead weight",
    "key 01",
    "key 02",
    "total prodution",
    "total production",
    "inner core",
}


def latest_material_planning_date(session: Session) -> date | None:
    candidates: list[date] = []
    if _table_exists(session, "mpps_cavity_plan_runs"):
        saved_date = session.execute(
            text(
                """
                SELECT MAX(plan_date)
                FROM mpps_cavity_plan_runs
                WHERE UPPER(COALESCE(status,'SAVED')) NOT IN ('CANCELLED','VOID','REJECTED')
                """
            )
        ).scalar()
        if saved_date:
            candidates.append(saved_date)
    oven_date = session.execute(
        text("SELECT MAX(plan_date) FROM mpps_oven_plan WHERE planned_qty > 0")
    ).scalar()
    if oven_date:
        candidates.append(oven_date)
    if _table_exists(session, "excel_import_material_plans"):
        excel_date = session.execute(
            text("SELECT MAX(plan_date) FROM excel_import_material_plans WHERE total_qty > 0 OR day_qty > 0 OR night_qty > 0")
        ).scalar()
        if excel_date:
            candidates.append(excel_date)
    return max(candidates) if candidates else None


def load_material_demands(
    session: Session,
    *,
    planning_date: date,
    basis: str = DEMAND_BASIS_OVEN,
) -> list[MaterialDemandRow]:
    if basis == DEMAND_BASIS_SHORTAGE:
        production = load_production_requirements(
            session,
            planning_date=planning_date,
            production_required_only=True,
        )
        return [
            MaterialDemandRow(
                material_code=row.material_code,
                item_description=row.item_description,
                planned_qty=row.production_required_qty,
                day_qty=0,
                night_qty=0,
                source="Shipment shortage / production requirement",
            )
            for row in production
            if row.production_required_qty > 0
        ]

    if basis != DEMAND_BASIS_OVEN:
        raise ValueError(f"Unsupported material demand basis: {basis}")

    # R6: the approved saved cavity plan is the primary MRP demand authority.
    # OVEN/Excel remains a fallback for dates that do not yet have a saved app plan.
    if (
        _table_exists(session, "mpps_cavity_plan_runs")
        and _table_exists(session, "mpps_cavity_plan_rows")
    ):
        run_id = session.execute(
            text(
                """
                SELECT id
                FROM mpps_cavity_plan_runs
                WHERE plan_date=:planning_date
                  AND UPPER(COALESCE(status,'SAVED')) NOT IN ('CANCELLED','VOID','REJECTED')
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"planning_date": planning_date},
        ).scalar()
        if run_id:
            saved_rows = session.execute(
                text(
                    """
                    SELECT
                        tyre_code AS material_code,
                        COALESCE(MAX(NULLIF(description,'')),tyre_code) AS item_description,
                        SUM(GREATEST(COALESCE(day_plan_pcs,0),0))::INTEGER AS day_qty,
                        SUM(GREATEST(COALESCE(night_plan_pcs,0),0))::INTEGER AS night_qty,
                        SUM(GREATEST(COALESCE(today_qty,0),0))::INTEGER AS planned_qty
                    FROM mpps_cavity_plan_rows
                    WHERE run_id=:run_id
                      AND TRIM(COALESCE(tyre_code,'')) <> ''
                      AND GREATEST(COALESCE(today_qty,0),0) > 0
                    GROUP BY tyre_code
                    HAVING SUM(GREATEST(COALESCE(today_qty,0),0)) > 0
                    ORDER BY tyre_code
                    """
                ),
                {"run_id": int(run_id)},
            ).mappings().all()
            if saved_rows:
                return [
                    MaterialDemandRow(
                        material_code=str(row["material_code"]),
                        item_description=str(row["item_description"] or row["material_code"]),
                        planned_qty=_to_int(row["planned_qty"]),
                        day_qty=_to_int(row["day_qty"]),
                        night_qty=_to_int(row["night_qty"]),
                        source="Approved saved cavity production plan",
                    )
                    for row in saved_rows
                ]

    rows = session.execute(
        text(
            """
            SELECT
                material_code,
                COALESCE(MAX(NULLIF(item_description, '')), material_code) AS item_description,
                SUM(CASE WHEN UPPER(COALESCE(shift_name, '')) = 'DAY' THEN planned_qty ELSE 0 END)::INTEGER AS day_qty,
                SUM(CASE WHEN UPPER(COALESCE(shift_name, '')) = 'NIGHT' THEN planned_qty ELSE 0 END)::INTEGER AS night_qty,
                SUM(CASE WHEN UPPER(COALESCE(shift_name, '')) IN ('DAY', 'NIGHT') THEN planned_qty ELSE 0 END)::INTEGER AS planned_qty
            FROM mpps_oven_plan
            WHERE plan_date = :planning_date
              AND planned_qty > 0
              AND UPPER(COALESCE(plan_status, '')) NOT IN ('CANCELLED', 'REJECTED', 'VOID')
            GROUP BY material_code
            HAVING SUM(CASE WHEN UPPER(COALESCE(shift_name, '')) IN ('DAY', 'NIGHT') THEN planned_qty ELSE 0 END) > 0
            ORDER BY material_code
            """
        ),
        {"planning_date": planning_date},
    ).mappings()
    return [
        MaterialDemandRow(
            material_code=str(row["material_code"]),
            item_description=str(row["item_description"] or row["material_code"]),
            planned_qty=_to_int(row["planned_qty"]),
            day_qty=_to_int(row["day_qty"]),
            night_qty=_to_int(row["night_qty"]),
            source="Oven day + night plan",
        )
        for row in rows
    ]


def build_material_requirements(
    session: Session,
    *,
    demand_rows: list[MaterialDemandRow] | None = None,
    production_rows: Iterable[Any] | None = None,
    assumptions: PlanningAssumptions | None = None,
) -> list[MaterialRequirementRow]:
    """Build detailed MRP rows.

    ``production_rows`` is retained for compatibility with older callers. New code
    should pass ``demand_rows`` so day/night production can be carried through.
    """
    assumptions = assumptions or PlanningAssumptions()
    if demand_rows is None:
        demand_rows = [
            MaterialDemandRow(
                material_code=str(row.material_code),
                item_description=str(row.item_description),
                planned_qty=int(row.production_required_qty),
                day_qty=0,
                night_qty=0,
                source="Shipment shortage / production requirement",
            )
            for row in (production_rows or [])
            if int(row.production_required_qty) > 0
        ]

    required = [row for row in demand_rows if row.planned_qty > 0]
    if not required:
        return []

    item_codes = sorted({row.material_code for row in required})
    masters = _load_masters(session, item_codes)
    item_keys = _load_item_keys(session, item_codes)
    output: list[MaterialRequirementRow] = []

    for demand in required:
        code = demand.material_code
        compound_rows = _dedupe_master_rows(
            masters["compound"].get(code, []),
            lambda row: (_normalize(row.get("compound_code")), _normalize(row.get("compound_name"))),
        )
        compound_names = {
            _normalize(row.get("compound_name")) for row in compound_rows if row.get("compound_name")
        }

        for row in compound_rows:
            usage = _to_float(row["compound_weight_per_unit"])
            if usage <= 0:
                continue
            output.append(
                _row(
                    demand,
                    "COMPOUND",
                    row["compound_code"],
                    f"{row['compound_name']} ({row['stage'] or 'MAIN'})",
                    row["compound_name"],
                    usage,
                    assumptions.compound_allowance_rate,
                    "KG",
                    _source_text(row),
                )
            )

        # Some legacy MPPS imports store the wide compound matrix in BOM. Use
        # those rows only when they are not already represented by the compound
        # master. This prevents the old screen from double-counting the same kg.
        for row in _dedupe_master_rows(
            masters["bom"].get(code, []),
            lambda value: (_normalize(value.get("raw_material_code")), _normalize(value.get("raw_material_name"))),
        ):
            material_name = str(row.get("raw_material_name") or "").strip()
            normalized_name = _normalize(material_name)
            if not material_name or normalized_name in _PSEUDO_BOM_NAMES:
                continue
            looks_compound = "compound" in normalized_name
            if looks_compound and normalized_name in compound_names:
                continue
            usage = _to_float(row["usage_per_unit"])
            if usage <= 0:
                continue
            component_type = "COMPOUND" if looks_compound else "BOM"
            allowance = (
                assumptions.compound_allowance_rate
                if component_type == "COMPOUND"
                else _to_float(row["wastage_percentage"]) / 100.0
            )
            output.append(
                _row(
                    demand,
                    component_type,
                    row["raw_material_code"],
                    material_name,
                    material_name,
                    usage,
                    allowance,
                    row["unit"] or "KG",
                    _source_text(row),
                )
            )

        keys = item_keys.get(code, {})
        bead_key, bead_rows = _resolve_keyed_master(
            masters["bead"],
            [code, keys.get("bead_type"), keys.get("product_group")],
        )
        for row in _dedupe_master_rows(
            bead_rows,
            lambda value: (_normalize(value.get("bead_type")), _to_float(value.get("bead_per_tyre"))),
        ):
            usage = _to_float(row["bead_per_tyre"])
            if usage <= 0:
                continue
            output.append(
                _row(
                    demand,
                    "BEAD",
                    row["bead_type"],
                    f"Bead {row['bead_type']}",
                    row["bead_type"],
                    usage,
                    0.0,
                    "PCS",
                    _source_text(row),
                )
            )

        band_key, band_rows = _resolve_keyed_master(
            masters["band"],
            [code, keys.get("band_type")],
        )
        for row in _dedupe_master_rows(
            band_rows,
            lambda value: (_normalize(value.get("band_code")), _normalize(value.get("band_type"))),
        ):
            usage = _to_float(row["band_usage_per_tyre"])
            if usage <= 0:
                continue
            output.append(
                _row(
                    demand,
                    "BAND",
                    row["band_code"] or "-",
                    str(row["band_type"] or band_key or "Band"),
                    str(band_key or row["band_type"] or row["band_code"] or "Band"),
                    usage,
                    assumptions.band_allowance_rate,
                    "PCS",
                    _source_text(row),
                )
            )

        if not compound_rows and not any(
            row.component_type == "COMPOUND" and row.finished_item_code == code
            for row in output
        ):
            output.append(_missing_row(demand, "COMPOUND", "MISSING COMPOUND MASTER"))
        if not bead_rows:
            key_note = str(keys.get("bead_type") or "-")
            output.append(_missing_row(demand, "BEAD", f"MISSING BEAD MASTER ({key_note})"))
        if not band_rows and _valid_key(keys.get("band_type")):
            output.append(
                _missing_row(
                    demand,
                    "BAND",
                    f"MISSING BAND MASTER ({keys.get('band_type')})",
                )
            )

    return output


def load_excel_material_plan_snapshot(
    session: Session,
    *,
    planning_date: date,
) -> tuple[list[ExcelMaterialPlanRow], date | None, str]:
    if not _table_exists(session, "excel_import_material_plans"):
        return [], None, ""

    snapshot_date = session.execute(
        text(
            """
            SELECT MAX(plan_date)
            FROM excel_import_material_plans
            WHERE plan_date <= :planning_date
              AND (total_qty <> 0 OR day_qty <> 0 OR night_qty <> 0 OR stock_qty <> 0 OR next_day_qty <> 0)
            """
        ),
        {"planning_date": planning_date},
    ).scalar()
    if snapshot_date is None:
        snapshot_date = session.execute(
            text("SELECT MAX(plan_date) FROM excel_import_material_plans")
        ).scalar()
    if snapshot_date is None:
        return [], None, ""

    run_id = session.execute(
        text(
            """
            SELECT MAX(run_id)
            FROM excel_import_material_plans
            WHERE plan_date = :snapshot_date
            """
        ),
        {"snapshot_date": snapshot_date},
    ).scalar()
    if run_id is None:
        return [], snapshot_date, ""

    workbook_name = ""
    if _table_exists(session, "excel_import_runs"):
        workbook_name = str(
            session.execute(
                text("SELECT COALESCE(workbook_name, '') FROM excel_import_runs WHERE id = :run_id"),
                {"run_id": run_id},
            ).scalar()
            or ""
        )

    rows = session.execute(
        text(
            """
            SELECT
                plan_date, material_type, material_key, material_description,
                day_qty, night_qty, total_qty, produced_qty, stock_qty,
                next_day_qty, unit, source_sheet, source_row
            FROM excel_import_material_plans
            WHERE run_id = :run_id
              AND plan_date = :snapshot_date
            ORDER BY material_type, material_key, id
            """
        ),
        {"run_id": run_id, "snapshot_date": snapshot_date},
    ).mappings()

    output = [
        ExcelMaterialPlanRow(
            plan_date=row["plan_date"],
            material_type=str(row["material_type"] or "").upper(),
            material_key=str(row["material_key"] or "-"),
            material_description=str(row["material_description"] or ""),
            day_qty=_to_float(row["day_qty"]),
            night_qty=_to_float(row["night_qty"]),
            total_qty=_to_float(row["total_qty"]),
            produced_qty=_to_float(row["produced_qty"]),
            stock_qty=_to_float(row["stock_qty"]),
            next_day_qty=_to_float(row["next_day_qty"]),
            unit=str(row["unit"] or "-"),
            source=f"{row['source_sheet']}:{row['source_row']}",
            workbook_name=workbook_name,
        )
        for row in rows
    ]
    return output, snapshot_date, workbook_name


def consolidate_material_requirements(
    rows: list[MaterialRequirementRow],
    excel_rows: list[ExcelMaterialPlanRow] | None = None,
) -> list[ConsolidatedMaterialRow]:
    grouped: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            row.component_type,
            _normalize(row.planning_key or row.raw_material_name),
            row.raw_material_code,
            row.raw_material_name,
            row.unit,
        )
        bucket = grouped.setdefault(
            key,
            {
                "calculated": 0.0,
                "items": set(),
                "warnings": 0,
                "sources": set(),
            },
        )
        bucket["calculated"] += row.required_qty
        bucket["items"].add(row.finished_item_code)
        bucket["warnings"] += int(bool(row.warning))
        if row.master_source:
            bucket["sources"].add(row.master_source)

    excel_map: dict[tuple[str, str], list[ExcelMaterialPlanRow]] = defaultdict(list)
    for row in excel_rows or []:
        excel_map[(row.material_type.upper(), _normalize(row.material_key))].append(row)

    output: list[ConsolidatedMaterialRow] = []
    consumed_excel: set[int] = set()
    for key, bucket in grouped.items():
        component_type, normalized_key, material_code, material_name, unit = key
        matches = excel_map.get((component_type, normalized_key), [])
        excel_plan = sum(item.total_qty for item in matches)
        excel_stock = sum(item.stock_qty for item in matches)
        excel_produced = sum(item.produced_qty for item in matches)
        excel_next = sum(item.next_day_qty for item in matches)
        for item in matches:
            consumed_excel.add(id(item))

        calculated = round(bucket["calculated"], 6)
        variance = round(excel_plan - calculated, 6) if matches else 0.0
        net_to_prepare = round(
            max(
                (excel_plan if matches else calculated)
                - max(excel_stock, 0.0)
                - max(excel_produced, 0.0),
                0.0,
            ),
            6,
        )
        status = _reconciliation_status(
            calculated=calculated,
            excel_plan=excel_plan,
            has_excel=bool(matches),
            warning_count=bucket["warnings"],
        )
        sources = sorted(bucket["sources"])
        if matches:
            sources.extend(sorted({item.source for item in matches if item.source}))
        output.append(
            ConsolidatedMaterialRow(
                component_type=component_type,
                material_code=material_code,
                material_name=material_name,
                planning_key=key[1],
                unit=unit,
                calculated_required_qty=calculated,
                excel_plan_qty=round(excel_plan, 6),
                excel_stock_qty=round(excel_stock, 6),
                excel_produced_qty=round(excel_produced, 6),
                excel_next_day_qty=round(excel_next, 6),
                net_to_prepare_qty=net_to_prepare,
                variance_qty=variance,
                finished_item_count=len(bucket["items"]),
                warning_count=bucket["warnings"],
                status=status,
                source="; ".join(dict.fromkeys(sources)) or "Calculated master data",
            )
        )

    # CORE has no reliable per-tyre master in the MPPS workbook. Keep the Excel
    # plan visible as an auditable operational requirement instead of inventing a
    # formula. Any other Excel-only material is also surfaced rather than hidden.
    for excel in excel_rows or []:
        if id(excel) in consumed_excel:
            continue
        if excel.total_qty == 0 and excel.day_qty == 0 and excel.night_qty == 0:
            continue
        output.append(
            ConsolidatedMaterialRow(
                component_type=excel.material_type,
                material_code=excel.material_key,
                material_name=excel.material_description or excel.material_key,
                planning_key=_normalize(excel.material_key),
                unit=excel.unit,
                calculated_required_qty=0.0,
                excel_plan_qty=round(excel.total_qty, 6),
                excel_stock_qty=round(excel.stock_qty, 6),
                excel_produced_qty=round(excel.produced_qty, 6),
                excel_next_day_qty=round(excel.next_day_qty, 6),
                net_to_prepare_qty=excel.net_gap_qty,
                variance_qty=0.0,
                finished_item_count=0,
                warning_count=0,
                status="EXCEL PLAN",
                source=excel.source,
            )
        )

    return sorted(
        output,
        key=lambda row: (
            row.status not in {"CHECK VARIANCE", "MASTER WARNING"},
            row.component_type,
            row.material_name.lower(),
        ),
    )


def _load_masters(session: Session, item_codes: list[str]) -> dict[str, dict[str, list[dict]]]:
    statements = {
        "bom": """
            SELECT id, finished_item_code AS item_code, raw_material_code, raw_material_name,
                   usage_per_unit, wastage_percentage, unit,
                   source_workbook, source_sheet, source_row, source_note
            FROM mpps_bom_items
            WHERE is_active = TRUE AND finished_item_code = ANY(:item_codes)
            ORDER BY id DESC
        """,
        "compound": """
            SELECT id, item_code, compound_code, compound_name, compound_weight_per_unit, stage,
                   source_workbook, source_sheet, source_row, source_note
            FROM mpps_compound_master
            WHERE is_active = TRUE AND item_code = ANY(:item_codes)
            ORDER BY id DESC
        """,
        "bead": """
            SELECT id, item_code, bead_type, bead_per_tyre,
                   source_workbook, source_sheet, source_row, source_note
            FROM mpps_bead_master
            WHERE is_active = TRUE
            ORDER BY id DESC
        """,
        "band": """
            SELECT id, item_code, band_code, band_type, band_usage_per_tyre,
                   source_workbook, source_sheet, source_row, source_note
            FROM mpps_band_master
            WHERE is_active = TRUE
            ORDER BY id DESC
        """,
    }
    result: dict[str, dict[str, list[dict]]] = {}
    for key, sql in statements.items():
        grouped: dict[str, list[dict]] = defaultdict(list)
        params = {"item_codes": item_codes} if ":item_codes" in sql else {}
        for row in session.execute(text(sql), params).mappings():
            grouped[str(row["item_code"])].append(dict(row))
        result[key] = dict(grouped)
    return result


def _load_item_keys(session: Session, item_codes: list[str]) -> dict[str, dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT material_code, bead_type, band_type, product_group, size
            FROM mpps_stock_items
            WHERE material_code = ANY(:item_codes)
            """
        ),
        {"item_codes": item_codes},
    ).mappings()
    return {str(row["material_code"]): dict(row) for row in rows}


def _resolve_keyed_master(
    masters: dict[str, list[dict]], candidates: Iterable[Any]
) -> tuple[str, list[dict]]:
    normalized_lookup = {_normalize(key): key for key in masters}
    for candidate in candidates:
        if not _valid_key(candidate):
            continue
        candidate_text = str(candidate).strip()
        if candidate_text in masters:
            return candidate_text, masters[candidate_text]
        normalized = _normalize(candidate_text)
        if normalized in normalized_lookup:
            actual = normalized_lookup[normalized]
            return str(actual), masters[actual]
    return "", []


def _row(
    demand: MaterialDemandRow,
    component_type: str,
    material_code: Any,
    material_name: Any,
    planning_key: Any,
    usage: float,
    allowance: float,
    unit: Any,
    master_source: str,
) -> MaterialRequirementRow:
    base = demand.planned_qty * usage
    day_base = demand.day_qty * usage
    night_base = demand.night_qty * usage
    factor = 1.0 + allowance
    return MaterialRequirementRow(
        finished_item_code=demand.material_code,
        finished_item_description=demand.item_description,
        production_required_qty=demand.planned_qty,
        day_production_qty=demand.day_qty,
        night_production_qty=demand.night_qty,
        component_type=component_type,
        raw_material_code=str(material_code or "-"),
        raw_material_name=str(material_name or "-"),
        planning_key=str(planning_key or material_name or material_code or "-"),
        usage_per_unit=round(usage, 6),
        base_required_qty=round(base, 6),
        allowance_rate=round(allowance, 4),
        required_qty=round(base * factor, 6),
        day_required_qty=round(day_base * factor, 6),
        night_required_qty=round(night_base * factor, 6),
        unit=str(unit or "-"),
        demand_source=demand.source,
        master_source=master_source,
        warning="",
    )


def _missing_row(
    demand: MaterialDemandRow,
    component_type: str,
    warning: str,
) -> MaterialRequirementRow:
    return MaterialRequirementRow(
        finished_item_code=demand.material_code,
        finished_item_description=demand.item_description,
        production_required_qty=demand.planned_qty,
        day_production_qty=demand.day_qty,
        night_production_qty=demand.night_qty,
        component_type=component_type,
        raw_material_code="-",
        raw_material_name="-",
        planning_key="-",
        usage_per_unit=0.0,
        base_required_qty=0.0,
        allowance_rate=0.0,
        required_qty=0.0,
        day_required_qty=0.0,
        night_required_qty=0.0,
        unit="-",
        demand_source=demand.source,
        master_source="",
        warning=warning,
    )


def _reconciliation_status(
    *, calculated: float, excel_plan: float, has_excel: bool, warning_count: int
) -> str:
    if warning_count:
        return "MASTER WARNING"
    if not has_excel:
        return "CALCULATED"
    tolerance = max(1.0, abs(calculated) * 0.02)
    if abs(excel_plan - calculated) <= tolerance:
        return "MATCH"
    return "CHECK VARIANCE"


def _dedupe_master_rows(rows: list[dict], key_fn) -> list[dict]:
    output: list[dict] = []
    seen: set[Any] = set()
    for row in rows:
        key = key_fn(row)
        if key in seen:
            continue
        seen.add(key)
        output.append(row)
    return output


def _source_text(row: dict[str, Any]) -> str:
    workbook = str(row.get("source_workbook") or "").strip()
    sheet = str(row.get("source_sheet") or "").strip()
    source_row = row.get("source_row")
    parts: list[str] = []
    if workbook:
        parts.append(workbook)
    if sheet:
        ref = f"{sheet}:{source_row}" if source_row else sheet
        parts.append(ref)
    return " / ".join(parts)


def _table_exists(session: Session, table_name: str) -> bool:
    return bool(
        session.execute(
            text("SELECT to_regclass(:qualified_name) IS NOT NULL"),
            {"qualified_name": f"public.{table_name}"},
        ).scalar()
    )


def _valid_key(value: Any) -> bool:
    if value is None:
        return False
    text_value = str(value).strip()
    return text_value not in {"", "-", "0", "0.0", "NONE", "NULL"}


def _normalize(value: Any) -> str:
    text_value = str(value or "").strip().lower()
    text_value = re.sub(r"\s+", " ", text_value)
    return text_value


def _to_int(value: Any) -> int:
    return int(value or 0)


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
