from __future__ import annotations

import argparse
from datetime import datetime

from sqlalchemy import text

from app.database import engine, init_database


CONFIRM_TEXT = "YES_DELETE_DUMMY_DATA"

SYSTEM_TABLES_TO_KEEP = {
    "roles",
    "users",
}

TABLES_TO_CLEAR = [
    "order_status_history",
    "schedule_change_log",
    "oven_schedule",
    "order_item_priority_log",
    "order_items",
    "orders",

    "tire_stock_movements",

    "mpps_shipment_demand",
    "mpps_bom_items",
    "mpps_compound_master",
    "mpps_bead_master",
    "mpps_band_master",
    "mpps_capacity_master",
    "mpps_stock_items",

    "excel_raw_cells",
    "excel_raw_rows",
    "excel_sheets",
    "excel_workbooks",

    "mpps_products",
    "mpps_stock_balances",
    "mpps_compounds",
    "mpps_beads",
    "mpps_bands",
    "mpps_capacity",
    "mpps_oven_plan",
    "mpps_planning_results",

    "customers",
    "tire_types",
    "ovens",
    "shifts",
    "production_rules",
]


def quote_identifier(name: str) -> str:
    if not name.replace("_", "").isalnum():
        raise ValueError(f"Unsafe identifier: {name}")
    return f'"{name}"'


def get_public_base_tables() -> list[str]:
    with engine.begin() as connection:
        rows = connection.execute(
            text(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_type = 'BASE TABLE'
                ORDER BY table_name;
                """
            )
        ).scalars().all()

    return [str(row) for row in rows]


def get_table_count(table_name: str) -> int:
    with engine.begin() as connection:
        return int(
            connection.execute(
                text(f'SELECT COUNT(*) FROM public.{quote_identifier(table_name)};')
            ).scalar()
            or 0
        )


def create_backup_schema(public_tables: list[str]) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_schema = f"backup_before_dummy_cleanup_{timestamp}"

    with engine.begin() as connection:
        connection.execute(text(f"CREATE SCHEMA {quote_identifier(backup_schema)};"))

        connection.execute(
            text(
                f"""
                CREATE TABLE {quote_identifier(backup_schema)}.backup_manifest (
                    table_name TEXT NOT NULL,
                    row_count BIGINT NOT NULL,
                    backed_up_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        for table_name in public_tables:
            row_count = int(
                connection.execute(
                    text(f'SELECT COUNT(*) FROM public.{quote_identifier(table_name)};')
                ).scalar()
                or 0
            )

            connection.execute(
                text(
                    f"""
                    CREATE TABLE {quote_identifier(backup_schema)}.{quote_identifier(table_name)}
                    AS TABLE public.{quote_identifier(table_name)};
                    """
                )
            )

            connection.execute(
                text(
                    f"""
                    INSERT INTO {quote_identifier(backup_schema)}.backup_manifest (
                        table_name,
                        row_count
                    )
                    VALUES (
                        :table_name,
                        :row_count
                    );
                    """
                ),
                {
                    "table_name": table_name,
                    "row_count": row_count,
                },
            )

    return backup_schema


def clear_dummy_data(existing_tables: set[str]) -> list[str]:
    tables = [
        table_name
        for table_name in TABLES_TO_CLEAR
        if table_name in existing_tables and table_name not in SYSTEM_TABLES_TO_KEEP
    ]

    if not tables:
        return []

    table_sql = ", ".join(
        f"public.{quote_identifier(table_name)}"
        for table_name in tables
    )

    with engine.begin() as connection:
        connection.execute(
            text(
                f"""
                TRUNCATE TABLE {table_sql}
                RESTART IDENTITY
                CASCADE;
                """
            )
        )

    return tables


def print_counts(title: str, tables: list[str]) -> None:
    print("")
    print(title)
    print("-" * len(title))

    for table_name in tables:
        try:
            print(f"{table_name}: {get_table_count(table_name)}")
        except Exception as exc:
            print(f"{table_name}: count failed ({exc})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=False, default="")
    args = parser.parse_args()

    if args.confirm != CONFIRM_TEXT:
        print("Cleanup cancelled.")
        print("")
        print("This script deletes dummy business/master/planning data.")
        print("It keeps users and roles so you can still login.")
        print("")
        print("Run again with:")
        print(
            "python -m tools.maintenance.clean_dummy_data "
            f"--confirm {CONFIRM_TEXT}"
        )
        return

    print("Starting safe dummy data cleanup...")
    print("Creating/validating database tables...")
    init_database()

    public_tables = get_public_base_tables()
    existing_tables = set(public_tables)

    print("")
    print("Creating full database table backup before cleanup...")
    backup_schema = create_backup_schema(public_tables)
    print(f"Backup created in PostgreSQL schema: {backup_schema}")

    tables_to_show = [
        table_name
        for table_name in TABLES_TO_CLEAR
        if table_name in existing_tables
    ]

    print_counts("Before cleanup row counts", tables_to_show)

    cleared_tables = clear_dummy_data(existing_tables)

    print_counts("After cleanup row counts", tables_to_show)

    print("")
    print("Dummy data cleanup completed successfully.")
    print("")
    print("Tables cleared:")

    for table_name in cleared_tables:
        print(f"- {table_name}")

    print("")
    print("Tables kept:")
    print("- roles")
    print("- users")
    print("")
    print(f"Backup schema: {backup_schema}")
    print("Existing table structures were not dropped.")
    print("App login users were not deleted.")


if __name__ == "__main__":
    main()
