from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from math import ceil
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


ACTIVE_DEMAND_STATUSES = ("PENDING", "CONFIRMED", "PLANNED", "PARTIALLY_PLANNED")
EXCLUDED_DEMAND_STATUSES = ("CANCELLED", "COMPLETED", "REJECTED")


@dataclass(frozen=True)
class StockPlanningRow:
    item_id: int
    material_code: str
    item_description: str
    tire_type_id: int | None
    product_type: str
    size: str
    product_group: str
    fg_stock: int
    qc_stock: int
    scrap_stock: int
    blocked_stock: int
    total_stock: int
    available_stock: int
    shipment_demand: int
    ready_for_shipment: int
    shortage_qty: int
    production_required_qty: int
    status: str
    average_weight: float
    total_required_weight_kg: float
    total_required_weight_tons: float
    compound_weight: float
    bead_type: str
    band_type: str
    last_updated_date: date | None
    weight_missing: bool


@dataclass(frozen=True)
class StockSummary:
    total_items: int
    ready_items: int
    production_required_items: int
    shortage_items: int
    no_stock_items: int
    no_demand_items: int
    total_shipment_demand: int
    total_ready_for_shipment: int
    total_shortage_qty: int
    total_production_required_qty: int
    total_planned_weight_kg: float
    total_planned_tons: float


@dataclass(frozen=True)
class DemandBreakdownRow:
    source: str
    order_no: str
    customer_name: str
    demand_qty: int
    shipment_date: date | None
    status: str
    note: str


@dataclass(frozen=True)
class BomRequirementRow:
    finished_item_code: str
    raw_material_code: str
    raw_material_name: str
    usage_per_unit: float
    production_required_qty: int
    total_required_qty: float
    wastage_percentage: float
    final_required_qty: float
    unit: str


@dataclass(frozen=True)
class CompoundRequirementRow:
    item_code: str
    compound_code: str
    compound_name: str
    stage: str
    compound_weight_per_unit: float
    production_required_qty: int
    total_required_kg: float


@dataclass(frozen=True)
class BeadRequirementRow:
    item_code: str
    tire_size: str
    bead_type: str
    bead_per_tyre: float
    production_required_qty: int
    total_bead_required: float


@dataclass(frozen=True)
class BandRequirementRow:
    item_code: str
    tire_size: str
    band_code: str
    band_type: str
    band_usage_per_tyre: float
    production_required_qty: int
    total_band_required: float


@dataclass(frozen=True)
class TonnageRow:
    item_code: str
    item_description: str
    production_required_qty: int
    average_weight: float
    total_weight_kg: float
    total_weight_tons: float
    weight_status: str


@dataclass(frozen=True)
class CapacityPreviewRow:
    item_code: str
    item_description: str
    production_required_qty: int
    running_moulds: float
    per_mould_capacity: float
    daily_capacity: float
    production_days: int
    target_date: date | None
    capacity_status: str


@dataclass(frozen=True)
class ItemDetailSummary:
    stock: StockPlanningRow
    demand_breakdown: list[DemandBreakdownRow]
    bom_requirements: list[BomRequirementRow]
    compound_requirements: list[CompoundRequirementRow]
    bead_requirements: list[BeadRequirementRow]
    band_requirements: list[BandRequirementRow]
    tonnage: TonnageRow
    capacity_preview: CapacityPreviewRow
    warnings: list[str]


def calculate_available_stock(
    *,
    fg_stock: int,
    qc_stock: int,
    scrap_stock: int,
    blocked_stock: int,
) -> int:
    return int(fg_stock) + int(qc_stock) - int(scrap_stock) - int(blocked_stock)


def calculate_shortage(
    *,
    available_stock: int,
    shipment_demand: int,
) -> int:
    return max(int(shipment_demand) - max(int(available_stock), 0), 0)


def calculate_production_requirement(
    *,
    available_stock: int,
    shipment_demand: int,
) -> int:
    return calculate_shortage(
        available_stock=available_stock,
        shipment_demand=shipment_demand,
    )


def calculate_stock_status(
    *,
    available_stock: int,
    shipment_demand: int,
    blocked_stock: int = 0,
) -> str:
    available = max(int(available_stock), 0)
    demand = int(shipment_demand)

    if demand <= 0:
        return "NO_DEMAND"

    if available <= 0 and demand > 0:
        return "NO_STOCK_PRODUCTION_REQUIRED"

    if available >= demand:
        return "READY"

    if blocked_stock > 0 and available < demand:
        return "PARTIAL_READY"

    return "PRODUCTION_REQUIRED"


def calculate_weight_tonnage(
    *,
    production_required_qty: int,
    average_weight: float | Decimal | None,
) -> tuple[float, float]:
    weight = _to_float(average_weight)
    total_kg = float(int(production_required_qty)) * weight
    total_tons = total_kg / 1000.0
    return round(total_kg, 4), round(total_tons, 4)


def calculate_bom_requirements(
    *,
    production_required_qty: int,
    usage_per_unit: float | Decimal | None,
    wastage_percentage: float | Decimal | None = 0,
) -> tuple[float, float]:
    usage = _to_float(usage_per_unit)
    wastage = _to_float(wastage_percentage)
    total_required_qty = float(int(production_required_qty)) * usage
    final_required_qty = total_required_qty + (total_required_qty * wastage / 100.0)
    return round(total_required_qty, 6), round(final_required_qty, 6)


def calculate_compound_requirements(
    *,
    production_required_qty: int,
    compound_weight_per_unit: float | Decimal | None,
) -> float:
    return round(float(int(production_required_qty)) * _to_float(compound_weight_per_unit), 6)


def calculate_bead_requirements(
    *,
    production_required_qty: int,
    bead_per_tyre: float | Decimal | None,
) -> float:
    return round(float(int(production_required_qty)) * _to_float(bead_per_tyre), 6)


def calculate_band_requirements(
    *,
    production_required_qty: int,
    band_usage_per_tyre: float | Decimal | None,
) -> float:
    return round(float(int(production_required_qty)) * _to_float(band_usage_per_tyre), 6)


def load_stock_planning_rows(
    session: Session,
    *,
    search: str | None = None,
    status: str | None = None,
    product_group: str | None = None,
    shortage_only: bool = False,
    ready_only: bool = False,
) -> list[StockPlanningRow]:
    sql = """
        SELECT
            id,
            material_code,
            item_description,
            tire_type_id,
            product_type,
            size,
            product_group,
            fg_stock,
            qc_stock,
            scrap_stock,
            blocked_stock,
            total_stock,
            available_stock,
            shipment_demand,
            ready_for_shipment,
            shortage_qty,
            production_required_qty,
            status,
            average_weight,
            total_required_weight_kg,
            total_required_weight_tons,
            compound_weight,
            bead_type,
            band_type,
            last_updated_date,
            weight_missing
        FROM mpps_stock_planning_view
        WHERE 1 = 1
    """

    params: dict[str, Any] = {}

    if search:
        sql += """
            AND (
                LOWER(material_code) LIKE :search
                OR LOWER(item_description) LIKE :search
                OR LOWER(COALESCE(size, '')) LIKE :search
                OR LOWER(COALESCE(product_group, '')) LIKE :search
            )
        """
        params["search"] = f"%{search.strip().lower()}%"

    if status and status != "ALL":
        sql += " AND status = :status"
        params["status"] = status.strip().upper()

    if product_group and product_group != "ALL":
        sql += " AND COALESCE(product_group, '') = :product_group"
        params["product_group"] = product_group

    if shortage_only:
        sql += " AND shortage_qty > 0"

    if ready_only:
        sql += " AND status = 'READY'"

    sql += " ORDER BY shortage_qty DESC, shipment_demand DESC, material_code ASC;"

    rows = session.execute(text(sql), params).mappings()

    return [_map_stock_row(row) for row in rows]


def build_stock_planning_summary(session: Session) -> StockSummary:
    row = session.execute(
        text(
            """
            SELECT
                COUNT(*)::INTEGER AS total_items,
                SUM(CASE WHEN status = 'READY' THEN 1 ELSE 0 END)::INTEGER AS ready_items,
                SUM(CASE WHEN production_required_qty > 0 THEN 1 ELSE 0 END)::INTEGER AS production_required_items,
                SUM(CASE WHEN shortage_qty > 0 THEN 1 ELSE 0 END)::INTEGER AS shortage_items,
                SUM(CASE WHEN status = 'NO_STOCK_PRODUCTION_REQUIRED' THEN 1 ELSE 0 END)::INTEGER AS no_stock_items,
                SUM(CASE WHEN status = 'NO_DEMAND' THEN 1 ELSE 0 END)::INTEGER AS no_demand_items,
                COALESCE(SUM(shipment_demand), 0)::INTEGER AS total_shipment_demand,
                COALESCE(SUM(ready_for_shipment), 0)::INTEGER AS total_ready_for_shipment,
                COALESCE(SUM(shortage_qty), 0)::INTEGER AS total_shortage_qty,
                COALESCE(SUM(production_required_qty), 0)::INTEGER AS total_production_required_qty,
                COALESCE(SUM(total_required_weight_kg), 0)::NUMERIC(18, 4) AS total_planned_weight_kg,
                COALESCE(SUM(total_required_weight_tons), 0)::NUMERIC(18, 4) AS total_planned_tons
            FROM mpps_stock_planning_view;
            """
        )
    ).mappings().one()

    return StockSummary(
        total_items=_to_int(row["total_items"]),
        ready_items=_to_int(row["ready_items"]),
        production_required_items=_to_int(row["production_required_items"]),
        shortage_items=_to_int(row["shortage_items"]),
        no_stock_items=_to_int(row["no_stock_items"]),
        no_demand_items=_to_int(row["no_demand_items"]),
        total_shipment_demand=_to_int(row["total_shipment_demand"]),
        total_ready_for_shipment=_to_int(row["total_ready_for_shipment"]),
        total_shortage_qty=_to_int(row["total_shortage_qty"]),
        total_production_required_qty=_to_int(row["total_production_required_qty"]),
        total_planned_weight_kg=_to_float(row["total_planned_weight_kg"]),
        total_planned_tons=_to_float(row["total_planned_tons"]),
    )


def load_product_groups(session: Session) -> list[str]:
    rows = session.execute(
        text(
            """
            SELECT DISTINCT product_group
            FROM mpps_stock_items
            WHERE product_group IS NOT NULL
              AND TRIM(product_group) <> ''
              AND is_active = TRUE
            ORDER BY product_group ASC;
            """
        )
    ).scalars()

    return [str(row) for row in rows]


def get_stock_item_by_code(session: Session, material_code: str) -> StockPlanningRow | None:
    row = session.execute(
        text(
            """
            SELECT *
            FROM mpps_stock_planning_view
            WHERE material_code = :material_code
            LIMIT 1;
            """
        ),
        {"material_code": material_code},
    ).mappings().first()

    if row is None:
        return None

    return _map_stock_row(row)


def build_item_detail_summary(
    session: Session,
    *,
    material_code: str,
) -> ItemDetailSummary:
    stock = get_stock_item_by_code(session, material_code)

    if stock is None:
        raise ValueError("Selected stock item was not found.")

    demand_breakdown = load_demand_breakdown(session, material_code=material_code)
    bom_requirements = load_bom_requirements(
        session,
        material_code=material_code,
        production_required_qty=stock.production_required_qty,
    )
    compound_requirements = load_compound_requirements(
        session,
        material_code=material_code,
        production_required_qty=stock.production_required_qty,
    )
    bead_requirements = load_bead_requirements(
        session,
        material_code=material_code,
        production_required_qty=stock.production_required_qty,
        tire_size=stock.size,
    )
    band_requirements = load_band_requirements(
        session,
        material_code=material_code,
        production_required_qty=stock.production_required_qty,
        tire_size=stock.size,
    )
    tonnage = build_tonnage_row(stock)
    capacity_preview = build_capacity_preview(session, stock)
    warnings = build_item_warnings(
        stock=stock,
        bom_requirements=bom_requirements,
        compound_requirements=compound_requirements,
        bead_requirements=bead_requirements,
        band_requirements=band_requirements,
        capacity_preview=capacity_preview,
    )

    return ItemDetailSummary(
        stock=stock,
        demand_breakdown=demand_breakdown,
        bom_requirements=bom_requirements,
        compound_requirements=compound_requirements,
        bead_requirements=bead_requirements,
        band_requirements=band_requirements,
        tonnage=tonnage,
        capacity_preview=capacity_preview,
        warnings=warnings,
    )


def load_demand_breakdown(
    session: Session,
    *,
    material_code: str,
) -> list[DemandBreakdownRow]:
    rows: list[DemandBreakdownRow] = []

    manual_rows = session.execute(
        text(
            """
            SELECT
                'MPPS_SHIPMENT_DEMAND' AS source,
                '-' AS order_no,
                COALESCE(customer_name, '-') AS customer_name,
                demand_qty,
                shipment_date,
                status,
                COALESCE(note, '-') AS note
            FROM mpps_shipment_demand
            WHERE material_code = :material_code
              AND UPPER(status) IN ('PENDING', 'CONFIRMED', 'PLANNED', 'PARTIALLY_PLANNED')
            ORDER BY shipment_date ASC, id ASC;
            """
        ),
        {"material_code": material_code},
    ).mappings()

    for row in manual_rows:
        rows.append(
            DemandBreakdownRow(
                source=str(row["source"]),
                order_no=str(row["order_no"]),
                customer_name=str(row["customer_name"]),
                demand_qty=_to_int(row["demand_qty"]),
                shipment_date=row["shipment_date"],
                status=str(row["status"]),
                note=str(row["note"] or "-"),
            )
        )

    return rows


def load_bom_requirements(
    session: Session,
    *,
    material_code: str,
    production_required_qty: int,
) -> list[BomRequirementRow]:
    rows = session.execute(
        text(
            """
            SELECT
                finished_item_code,
                raw_material_code,
                raw_material_name,
                usage_per_unit,
                unit,
                wastage_percentage
            FROM mpps_bom_items
            WHERE finished_item_code = :material_code
              AND is_active = TRUE
            ORDER BY raw_material_code ASC;
            """
        ),
        {"material_code": material_code},
    ).mappings()

    output: list[BomRequirementRow] = []

    for row in rows:
        total_required_qty, final_required_qty = calculate_bom_requirements(
            production_required_qty=production_required_qty,
            usage_per_unit=row["usage_per_unit"],
            wastage_percentage=row["wastage_percentage"],
        )

        output.append(
            BomRequirementRow(
                finished_item_code=str(row["finished_item_code"]),
                raw_material_code=str(row["raw_material_code"]),
                raw_material_name=str(row["raw_material_name"]),
                usage_per_unit=_to_float(row["usage_per_unit"]),
                production_required_qty=int(production_required_qty),
                total_required_qty=total_required_qty,
                wastage_percentage=_to_float(row["wastage_percentage"]),
                final_required_qty=final_required_qty,
                unit=str(row["unit"] or "KG"),
            )
        )

    return output


def load_compound_requirements(
    session: Session,
    *,
    material_code: str,
    production_required_qty: int,
) -> list[CompoundRequirementRow]:
    rows = session.execute(
        text(
            """
            SELECT
                item_code,
                compound_code,
                compound_name,
                compound_weight_per_unit,
                stage
            FROM mpps_compound_master
            WHERE item_code = :material_code
              AND is_active = TRUE
            ORDER BY stage ASC, compound_code ASC;
            """
        ),
        {"material_code": material_code},
    ).mappings()

    output: list[CompoundRequirementRow] = []

    for row in rows:
        total_required_kg = calculate_compound_requirements(
            production_required_qty=production_required_qty,
            compound_weight_per_unit=row["compound_weight_per_unit"],
        )

        output.append(
            CompoundRequirementRow(
                item_code=str(row["item_code"]),
                compound_code=str(row["compound_code"]),
                compound_name=str(row["compound_name"]),
                stage=str(row["stage"] or "MAIN"),
                compound_weight_per_unit=_to_float(row["compound_weight_per_unit"]),
                production_required_qty=int(production_required_qty),
                total_required_kg=total_required_kg,
            )
        )

    return output


def load_bead_requirements(
    session: Session,
    *,
    material_code: str,
    production_required_qty: int,
    tire_size: str,
) -> list[BeadRequirementRow]:
    rows = session.execute(
        text(
            """
            SELECT
                item_code,
                bead_type,
                bead_per_tyre
            FROM mpps_bead_master
            WHERE item_code = :material_code
              AND is_active = TRUE
            ORDER BY bead_type ASC;
            """
        ),
        {"material_code": material_code},
    ).mappings()

    output: list[BeadRequirementRow] = []

    for row in rows:
        total_bead_required = calculate_bead_requirements(
            production_required_qty=production_required_qty,
            bead_per_tyre=row["bead_per_tyre"],
        )

        output.append(
            BeadRequirementRow(
                item_code=str(row["item_code"]),
                tire_size=tire_size or "-",
                bead_type=str(row["bead_type"]),
                bead_per_tyre=_to_float(row["bead_per_tyre"]),
                production_required_qty=int(production_required_qty),
                total_bead_required=total_bead_required,
            )
        )

    return output


def load_band_requirements(
    session: Session,
    *,
    material_code: str,
    production_required_qty: int,
    tire_size: str,
) -> list[BandRequirementRow]:
    rows = session.execute(
        text(
            """
            SELECT
                item_code,
                COALESCE(band_code, '-') AS band_code,
                band_type,
                band_usage_per_tyre
            FROM mpps_band_master
            WHERE item_code = :material_code
              AND is_active = TRUE
            ORDER BY band_type ASC, band_code ASC;
            """
        ),
        {"material_code": material_code},
    ).mappings()

    output: list[BandRequirementRow] = []

    for row in rows:
        total_band_required = calculate_band_requirements(
            production_required_qty=production_required_qty,
            band_usage_per_tyre=row["band_usage_per_tyre"],
        )

        output.append(
            BandRequirementRow(
                item_code=material_code,
                tire_size=tire_size or "-",
                band_code=str(row["band_code"] or "-"),
                band_type=str(row["band_type"]),
                band_usage_per_tyre=_to_float(row["band_usage_per_tyre"]),
                production_required_qty=int(production_required_qty),
                total_band_required=total_band_required,
            )
        )

    return output


def build_tonnage_row(stock: StockPlanningRow) -> TonnageRow:
    total_weight_kg, total_weight_tons = calculate_weight_tonnage(
        production_required_qty=stock.production_required_qty,
        average_weight=stock.average_weight,
    )

    weight_status = "OK"

    if stock.average_weight <= 0:
        weight_status = "WEIGHT_MISSING"

    return TonnageRow(
        item_code=stock.material_code,
        item_description=stock.item_description,
        production_required_qty=stock.production_required_qty,
        average_weight=stock.average_weight,
        total_weight_kg=total_weight_kg,
        total_weight_tons=total_weight_tons,
        weight_status=weight_status,
    )


def build_capacity_preview(
    session: Session,
    stock: StockPlanningRow,
) -> CapacityPreviewRow:
    row = session.execute(
        text(
            """
            SELECT
                item_code,
                running_moulds,
                per_mould_capacity,
                available_capacity_per_day,
                target_date
            FROM mpps_capacity_master
            WHERE item_code = :material_code
              AND is_active = TRUE
            LIMIT 1;
            """
        ),
        {"material_code": stock.material_code},
    ).mappings().first()

    if row is None:
        return CapacityPreviewRow(
            item_code=stock.material_code,
            item_description=stock.item_description,
            production_required_qty=stock.production_required_qty,
            running_moulds=0,
            per_mould_capacity=0,
            daily_capacity=0,
            production_days=0,
            target_date=None,
            capacity_status="CAPACITY_DATA_MISSING",
        )

    running_moulds = _to_float(row["running_moulds"])
    per_mould_capacity = _to_float(row["per_mould_capacity"])
    available_capacity_per_day = _to_float(row["available_capacity_per_day"])
    target_date = row["target_date"]

    calculated_daily_capacity = running_moulds * per_mould_capacity
    daily_capacity = available_capacity_per_day or calculated_daily_capacity

    production_days = 0

    if stock.production_required_qty > 0 and daily_capacity > 0:
        production_days = int(ceil(stock.production_required_qty / daily_capacity))

    capacity_status = "NO_PRODUCTION_REQUIRED"

    if stock.production_required_qty > 0 and daily_capacity <= 0:
        capacity_status = "CAPACITY_DATA_MISSING"
    elif stock.production_required_qty > 0:
        capacity_status = "CAPACITY_OK"

        if target_date is not None:
            days_available = (target_date - date.today()).days + 1

            if days_available < production_days:
                capacity_status = "CANNOT_COMPLETE_BY_TARGET"

    return CapacityPreviewRow(
        item_code=stock.material_code,
        item_description=stock.item_description,
        production_required_qty=stock.production_required_qty,
        running_moulds=round(running_moulds, 4),
        per_mould_capacity=round(per_mould_capacity, 4),
        daily_capacity=round(daily_capacity, 4),
        production_days=production_days,
        target_date=target_date,
        capacity_status=capacity_status,
    )


def build_item_warnings(
    *,
    stock: StockPlanningRow,
    bom_requirements: list[BomRequirementRow],
    compound_requirements: list[CompoundRequirementRow],
    bead_requirements: list[BeadRequirementRow],
    band_requirements: list[BandRequirementRow],
    capacity_preview: CapacityPreviewRow,
) -> list[str]:
    warnings: list[str] = []

    if stock.available_stock < 0:
        warnings.append("Available stock is negative. Check FG/QC/Scrap/Blocked stock values.")

    if stock.shipment_demand < 0:
        warnings.append("Shipment demand is negative. Check demand data.")

    if stock.production_required_qty > 0 and stock.average_weight <= 0:
        warnings.append("Weight Missing: average weight is required for tonnage calculation.")

    if stock.production_required_qty > 0 and not bom_requirements:
        warnings.append("BOM Missing: raw material requirement cannot be calculated.")

    if stock.production_required_qty > 0 and not compound_requirements:
        warnings.append("Compound Missing: compound requirement cannot be calculated.")

    if stock.production_required_qty > 0 and not bead_requirements:
        warnings.append("Bead Missing: bead requirement cannot be calculated.")

    if stock.production_required_qty > 0 and not band_requirements:
        warnings.append("Band Missing: band requirement cannot be calculated.")

    if capacity_preview.capacity_status == "CAPACITY_DATA_MISSING":
        warnings.append("Capacity Missing: capacity preview cannot be calculated.")

    if capacity_preview.capacity_status == "CANNOT_COMPLETE_BY_TARGET":
        warnings.append("Capacity Warning: production cannot complete by target date.")

    return warnings


def build_tonnage_summary(session: Session) -> list[TonnageRow]:
    stock_rows = load_stock_planning_rows(session)
    return [build_tonnage_row(stock) for stock in stock_rows]


def build_bom_requirement_report(session: Session) -> list[BomRequirementRow]:
    stock_rows = load_stock_planning_rows(session, shortage_only=True)
    output: list[BomRequirementRow] = []

    for stock in stock_rows:
        output.extend(
            load_bom_requirements(
                session,
                material_code=stock.material_code,
                production_required_qty=stock.production_required_qty,
            )
        )

    return output


def build_compound_requirement_report(session: Session) -> list[CompoundRequirementRow]:
    stock_rows = load_stock_planning_rows(session, shortage_only=True)
    output: list[CompoundRequirementRow] = []

    for stock in stock_rows:
        output.extend(
            load_compound_requirements(
                session,
                material_code=stock.material_code,
                production_required_qty=stock.production_required_qty,
            )
        )

    return output


def build_bead_requirement_report(session: Session) -> list[BeadRequirementRow]:
    stock_rows = load_stock_planning_rows(session, shortage_only=True)
    output: list[BeadRequirementRow] = []

    for stock in stock_rows:
        output.extend(
            load_bead_requirements(
                session,
                material_code=stock.material_code,
                production_required_qty=stock.production_required_qty,
                tire_size=stock.size,
            )
        )

    return output


def build_band_requirement_report(session: Session) -> list[BandRequirementRow]:
    stock_rows = load_stock_planning_rows(session, shortage_only=True)
    output: list[BandRequirementRow] = []

    for stock in stock_rows:
        output.extend(
            load_band_requirements(
                session,
                material_code=stock.material_code,
                production_required_qty=stock.production_required_qty,
                tire_size=stock.size,
            )
        )

    return output


def _map_stock_row(row: dict[str, Any]) -> StockPlanningRow:
    return StockPlanningRow(
        item_id=_to_int(row["id"]),
        material_code=str(row["material_code"]),
        item_description=str(row["item_description"]),
        tire_type_id=_to_int_or_none(row["tire_type_id"]),
        product_type=str(row["product_type"] or "-"),
        size=str(row["size"] or "-"),
        product_group=str(row["product_group"] or "-"),
        fg_stock=_to_int(row["fg_stock"]),
        qc_stock=_to_int(row["qc_stock"]),
        scrap_stock=_to_int(row["scrap_stock"]),
        blocked_stock=_to_int(row["blocked_stock"]),
        total_stock=_to_int(row["total_stock"]),
        available_stock=_to_int(row["available_stock"]),
        shipment_demand=_to_int(row["shipment_demand"]),
        ready_for_shipment=_to_int(row["ready_for_shipment"]),
        shortage_qty=_to_int(row["shortage_qty"]),
        production_required_qty=_to_int(row["production_required_qty"]),
        status=str(row["status"]),
        average_weight=_to_float(row["average_weight"]),
        total_required_weight_kg=_to_float(row["total_required_weight_kg"]),
        total_required_weight_tons=_to_float(row["total_required_weight_tons"]),
        compound_weight=_to_float(row["compound_weight"]),
        bead_type=str(row["bead_type"] or "-"),
        band_type=str(row["band_type"] or "-"),
        last_updated_date=row["last_updated_date"],
        weight_missing=bool(row["weight_missing"]),
    )


def _to_int(value: Any) -> int:
    if value is None:
        return 0

    return int(value)


def _to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None

    return int(value)


def _to_float(value: Any) -> float:
    if value is None:
        return 0.0

    if isinstance(value, Decimal):
        return float(value)

    return float(value)
