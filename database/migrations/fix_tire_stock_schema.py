from __future__ import annotations

from sqlalchemy import text

from app.database import engine, init_database


def run_sql(statement: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(statement))


def main() -> None:
    print("Starting tire stock schema update...")

    init_database()

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS tire_stock_movements (
            id SERIAL PRIMARY KEY,
            movement_date DATE NOT NULL,
            tire_type_id INTEGER NOT NULL REFERENCES tire_types(id),
            movement_type VARCHAR(40) NOT NULL,
            direction VARCHAR(10) NOT NULL,
            quantity INTEGER NOT NULL,
            source_ref VARCHAR(80),
            note TEXT,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_tire_stock_quantity_positive CHECK (quantity > 0),
            CONSTRAINT ck_tire_stock_direction CHECK (direction IN ('IN', 'OUT'))
        );
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_tire_stock_movements_date
        ON tire_stock_movements(movement_date);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_tire_stock_movements_tire_type
        ON tire_stock_movements(tire_type_id);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_tire_stock_movements_type
        ON tire_stock_movements(movement_type);
        """
    )

    print("Tire stock schema update completed successfully.")


if __name__ == "__main__":
    main()
