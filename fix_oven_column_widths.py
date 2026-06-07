from __future__ import annotations

from sqlalchemy import text

from app.database import engine


def run_sql(sql: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(sql))


def main() -> None:
    print("Starting oven column width fix...")

    run_sql(
        """
        ALTER TABLE ovens
        ALTER COLUMN oven_code TYPE VARCHAR(260),
        ALTER COLUMN oven_name TYPE VARCHAR(500);
        """
    )

    run_sql(
        """
        ALTER TABLE shifts
        ALTER COLUMN shift_name TYPE VARCHAR(160);
        """
    )

    print("Oven column width fix completed successfully.")
    print("Core ovens table can now accept long Excel oven codes/names.")


if __name__ == "__main__":
    main()