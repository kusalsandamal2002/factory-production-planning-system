from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.production_requirement_service import ProductionRequirementRow


@dataclass(frozen=True)
class PlanningAssumptions:
    compound_allowance_rate: float = 0.25
    band_allowance_rate: float = 0.15
    day_shift_share: float = 0.50
    source: str = "OVEN workbook / visible planning assumption"


@dataclass(frozen=True)
class MaterialRequirementRow:
    finished_item_code: str
    finished_item_description: str
    production_required_qty: int
    component_type: str
    raw_material_code: str
    raw_material_name: str
    usage_per_unit: float
    base_required_qty: float
    allowance_rate: float
    required_qty: float
    unit: str
    warning: str


def build_material_requirements(
    session: Session,
    *,
    production_rows: list[ProductionRequirementRow],
    assumptions: PlanningAssumptions | None = None,
) -> list[MaterialRequirementRow]:
    assumptions = assumptions or PlanningAssumptions()
    required = [row for row in production_rows if row.production_required_qty > 0]
    if not required:
        return []

    item_codes = [row.material_code for row in required]
    masters = _load_masters(session, item_codes)
    output: list[MaterialRequirementRow] = []

    for production in required:
        code = production.material_code

        for row in masters["bom"].get(code, []):
            usage = _to_float(row["usage_per_unit"])
            wastage = _to_float(row["wastage_percentage"]) / 100.0
            base = production.production_required_qty * usage
            output.append(
                _row(
                    production,
                    "BOM",
                    row["raw_material_code"],
                    row["raw_material_name"],
                    usage,
                    base,
                    wastage,
                    row["unit"] or "KG",
                )
            )

        for row in masters["compound"].get(code, []):
            usage = _to_float(row["compound_weight_per_unit"])
            base = production.production_required_qty * usage
            name = f"{row['compound_name']} ({row['stage'] or 'MAIN'})"
            output.append(
                _row(
                    production,
                    "COMPOUND",
                    row["compound_code"],
                    name,
                    usage,
                    base,
                    assumptions.compound_allowance_rate,
                    "KG",
                )
            )

        for row in masters["bead"].get(code, []):
            usage = _to_float(row["bead_per_tyre"])
            base = production.production_required_qty * usage
            output.append(
                _row(
                    production,
                    "BEAD",
                    row["bead_type"],
                    f"Bead type: {row['bead_type']}",
                    usage,
                    base,
                    0.0,
                    "PCS",
                )
            )

        for row in masters["band"].get(code, []):
            usage = _to_float(row["band_usage_per_tyre"])
            base = production.production_required_qty * usage
            output.append(
                _row(
                    production,
                    "BAND",
                    row["band_code"] or "-",
                    f"Band type: {row['band_type']}",
                    usage,
                    base,
                    assumptions.band_allowance_rate,
                    "PCS",
                )
            )

        if not masters["bom"].get(code):
            output.append(_missing_row(production, "BOM", "MISSING BOM"))
        if not masters["compound"].get(code):
            output.append(_missing_row(production, "COMPOUND", "MISSING COMPOUND"))
        if not masters["bead"].get(code):
            output.append(_missing_row(production, "BEAD", "MISSING BEAD"))
        if not masters["band"].get(code):
            output.append(_missing_row(production, "BAND", "MISSING BAND"))
    return output


def _load_masters(session: Session, item_codes: list[str]) -> dict[str, dict[str, list[dict]]]:
    statements = {
        "bom": """
            SELECT finished_item_code AS item_code, raw_material_code, raw_material_name,
                   usage_per_unit, wastage_percentage, unit
            FROM mpps_bom_items
            WHERE is_active = TRUE AND finished_item_code = ANY(:item_codes)
        """,
        "compound": """
            SELECT item_code, compound_code, compound_name, compound_weight_per_unit, stage
            FROM mpps_compound_master
            WHERE is_active = TRUE AND item_code = ANY(:item_codes)
        """,
        "bead": """
            SELECT item_code, bead_type, bead_per_tyre
            FROM mpps_bead_master
            WHERE is_active = TRUE AND item_code = ANY(:item_codes)
        """,
        "band": """
            SELECT item_code, band_code, band_type, band_usage_per_tyre
            FROM mpps_band_master
            WHERE is_active = TRUE AND item_code = ANY(:item_codes)
        """,
    }
    result: dict[str, dict[str, list[dict]]] = {}
    for key, sql in statements.items():
        grouped: dict[str, list[dict]] = {}
        for row in session.execute(text(sql), {"item_codes": item_codes}).mappings():
            grouped.setdefault(str(row["item_code"]), []).append(dict(row))
        result[key] = grouped
    return result


def _row(
    production: ProductionRequirementRow,
    component_type: str,
    material_code: Any,
    material_name: Any,
    usage: float,
    base: float,
    allowance: float,
    unit: Any,
) -> MaterialRequirementRow:
    return MaterialRequirementRow(
        finished_item_code=production.material_code,
        finished_item_description=production.item_description,
        production_required_qty=production.production_required_qty,
        component_type=component_type,
        raw_material_code=str(material_code or "-"),
        raw_material_name=str(material_name or "-"),
        usage_per_unit=round(usage, 6),
        base_required_qty=round(base, 6),
        allowance_rate=round(allowance, 4),
        required_qty=round(base * (1.0 + allowance), 6),
        unit=str(unit or "-"),
        warning="",
    )


def _missing_row(
    production: ProductionRequirementRow,
    component_type: str,
    warning: str,
) -> MaterialRequirementRow:
    return MaterialRequirementRow(
        finished_item_code=production.material_code,
        finished_item_description=production.item_description,
        production_required_qty=production.production_required_qty,
        component_type=component_type,
        raw_material_code="-",
        raw_material_name="-",
        usage_per_unit=0.0,
        base_required_qty=0.0,
        allowance_rate=0.0,
        required_qty=0.0,
        unit="-",
        warning=warning,
    )


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)
