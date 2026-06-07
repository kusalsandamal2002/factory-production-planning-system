from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class ShipmentDemandRow:
    demand_id: int
    customer_name: str
    material_code: str
    item_description: str
    demand_qty: int
    due_date: date | None
    priority: str
    status: str
    manager_note: str


def load_shipment_demands(session: Session) -> list[ShipmentDemandRow]:
    rows = session.execute(
        text(
            """
            SELECT
                demand.id,
                COALESCE(demand.customer_name, 'EXCEL DEMAND') AS customer_name,
                demand.material_code,
                COALESCE(stock.item_description, 'MISSING STOCK ITEM')
                    AS item_description,
                demand.demand_qty,
                demand.shipment_date,
                demand.status,
                COALESCE(demand.note, '-') AS manager_note
            FROM mpps_shipment_demand demand
            LEFT JOIN mpps_stock_items stock
                ON stock.material_code = demand.material_code
            ORDER BY
                demand.shipment_date NULLS LAST,
                demand.customer_name,
                demand.material_code,
                demand.id;
            """
        )
    ).mappings()
    return [
        ShipmentDemandRow(
            demand_id=int(row["id"]),
            customer_name=str(row["customer_name"]),
            material_code=str(row["material_code"]),
            item_description=str(row["item_description"]),
            demand_qty=int(row["demand_qty"] or 0),
            due_date=row["shipment_date"],
            priority="UNSPECIFIED",
            status=str(row["status"] or "PENDING").upper(),
            manager_note=str(row["manager_note"] or "-"),
        )
        for row in rows
    ]
