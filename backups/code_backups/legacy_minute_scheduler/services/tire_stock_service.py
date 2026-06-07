from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class TireStockRow:
    tire_type_id: int
    tire_code: str
    tire_name: str
    current_stock: int
    total_produced: int
    total_out: int
    last_movement_date: date | None


@dataclass(frozen=True)
class DailyProductionRow:
    movement_id: int
    movement_date: date
    tire_code: str
    tire_name: str
    quantity: int
    note: str
    created_at: datetime


def load_current_tire_stock(session: Session) -> list[TireStockRow]:
    rows = session.execute(
        text(
            """
            SELECT
                tt.id AS tire_type_id,
                tt.tire_code AS tire_code,
                tt.tire_name AS tire_name,
                COALESCE(
                    SUM(
                        CASE
                            WHEN tsm.direction = 'IN' THEN tsm.quantity
                            WHEN tsm.direction = 'OUT' THEN -tsm.quantity
                            ELSE 0
                        END
                    ),
                    0
                ) AS current_stock,
                COALESCE(
                    SUM(
                        CASE
                            WHEN tsm.direction = 'IN' THEN tsm.quantity
                            ELSE 0
                        END
                    ),
                    0
                ) AS total_produced,
                COALESCE(
                    SUM(
                        CASE
                            WHEN tsm.direction = 'OUT' THEN tsm.quantity
                            ELSE 0
                        END
                    ),
                    0
                ) AS total_out,
                MAX(tsm.movement_date) AS last_movement_date
            FROM tire_types tt
            LEFT JOIN tire_stock_movements tsm
                ON tsm.tire_type_id = tt.id
            WHERE tt.is_active = TRUE
            GROUP BY tt.id, tt.tire_code, tt.tire_name
            ORDER BY tt.tire_code ASC;
            """
        )
    ).mappings()

    return [
        TireStockRow(
            tire_type_id=int(row["tire_type_id"]),
            tire_code=str(row["tire_code"]),
            tire_name=str(row["tire_name"]),
            current_stock=int(row["current_stock"] or 0),
            total_produced=int(row["total_produced"] or 0),
            total_out=int(row["total_out"] or 0),
            last_movement_date=row["last_movement_date"],
        )
        for row in rows
    ]


def load_daily_production_history(
    session: Session,
    *,
    production_date: date | None = None,
) -> list[DailyProductionRow]:
    sql = """
        SELECT
            tsm.id AS movement_id,
            tsm.movement_date AS movement_date,
            tt.tire_code AS tire_code,
            tt.tire_name AS tire_name,
            tsm.quantity AS quantity,
            COALESCE(tsm.note, '-') AS note,
            tsm.created_at AS created_at
        FROM tire_stock_movements tsm
        JOIN tire_types tt
            ON tt.id = tsm.tire_type_id
        WHERE tsm.movement_type = 'DAILY_PRODUCTION'
          AND tsm.direction = 'IN'
    """

    params: dict[str, object] = {}

    if production_date is not None:
        sql += " AND tsm.movement_date = :production_date"
        params["production_date"] = production_date

    sql += " ORDER BY tsm.movement_date DESC, tsm.id DESC;"

    rows = session.execute(text(sql), params).mappings()

    return [
        DailyProductionRow(
            movement_id=int(row["movement_id"]),
            movement_date=row["movement_date"],
            tire_code=str(row["tire_code"]),
            tire_name=str(row["tire_name"]),
            quantity=int(row["quantity"]),
            note=str(row["note"] or "-"),
            created_at=row["created_at"],
        )
        for row in rows
    ]


def add_daily_tire_production(
    session: Session,
    *,
    movement_date: date,
    tire_type_id: int,
    quantity: int,
    note: str | None,
    created_by: int | None,
) -> None:
    if quantity <= 0:
        raise ValueError("Production quantity must be greater than zero.")

    tire_exists = session.execute(
        text(
            """
            SELECT id
            FROM tire_types
            WHERE id = :tire_type_id
              AND is_active = TRUE;
            """
        ),
        {"tire_type_id": tire_type_id},
    ).scalar_one_or_none()

    if tire_exists is None:
        raise ValueError("Selected tire type was not found or inactive.")

    session.execute(
        text(
            """
            INSERT INTO tire_stock_movements (
                movement_date,
                tire_type_id,
                movement_type,
                direction,
                quantity,
                source_ref,
                note,
                created_by
            )
            VALUES (
                :movement_date,
                :tire_type_id,
                'DAILY_PRODUCTION',
                'IN',
                :quantity,
                :source_ref,
                :note,
                :created_by
            );
            """
        ),
        {
            "movement_date": movement_date,
            "tire_type_id": tire_type_id,
            "quantity": quantity,
            "source_ref": f"DAILY-PRODUCTION-{movement_date.strftime('%Y%m%d')}",
            "note": note.strip() if note else None,
            "created_by": created_by,
        },
    )


def delete_daily_production_entry(
    session: Session,
    *,
    movement_id: int,
) -> None:
    result = session.execute(
        text(
            """
            DELETE FROM tire_stock_movements
            WHERE id = :movement_id
              AND movement_type = 'DAILY_PRODUCTION'
              AND direction = 'IN';
            """
        ),
        {"movement_id": movement_id},
    )

    if result.rowcount == 0:
        raise ValueError("Selected daily production entry was not found.")
