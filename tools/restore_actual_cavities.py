import os
from urllib.parse import quote_plus

from sqlalchemy import create_engine, inspect, text


HOST = "127.0.0.1"
PORT = 5434
USER = "postgres"
PASSWORD = os.environ.get("PGPASSWORD")

SOURCE_DB = "factory_planner_restore"
TARGET_DB = "factory_planner_v2"

if not PASSWORD:
    raise SystemExit(
        "PGPASSWORD is not set. Run: $env:PGPASSWORD = 'your_password'"
    )


def database_url(database_name: str) -> str:
    return (
        f"postgresql+psycopg://{USER}:{quote_plus(PASSWORD)}"
        f"@{HOST}:{PORT}/{database_name}"
    )


source_engine = create_engine(
    database_url(SOURCE_DB),
    future=True,
)

target_engine = create_engine(
    database_url(TARGET_DB),
    future=True,
)


source_columns = [
    "line_name",
    "cavity_no",
    "status",
    "assigned_tyre_item",
    "remarks",
    "created_at",
    "updated_at",
    "cavity_code",
    "display_order",
]


with source_engine.connect() as source_conn:
    source_rows = source_conn.execute(
        text(
            """
            SELECT
                line_name,
                cavity_no,
                status,
                assigned_tyre_item,
                remarks,
                created_at,
                updated_at,
                cavity_code,
                display_order
            FROM production_line_cavities
            ORDER BY line_name, cavity_no
            """
        )
    ).mappings().all()

    source_counts = source_conn.execute(
        text(
            """
            SELECT line_name, COUNT(*) AS cavity_count
            FROM production_line_cavities
            GROUP BY line_name
            ORDER BY line_name
            """
        )
    ).all()


print("=== SOURCE CAVITY COUNTS ===")
for line_name, count in source_counts:
    print(f"{line_name}: {count}")

print(f"\nSource total: {len(source_rows)}")

if len(source_rows) != 102:
    raise SystemExit(
        f"Safety check failed: expected 102 source cavities, found {len(source_rows)}"
    )


duplicate_check = {
    (row["line_name"], row["cavity_no"])
    for row in source_rows
}

if len(duplicate_check) != len(source_rows):
    raise SystemExit(
        "Safety check failed: duplicate line_name/cavity_no records found."
    )


target_inspector = inspect(target_engine)

target_columns = {
    column["name"]
    for column in target_inspector.get_columns("production_line_cavities")
}

required_columns = {
    "line_name",
    "cavity_no",
    "status",
}

missing_required = required_columns - target_columns

if missing_required:
    raise SystemExit(
        f"Target table is missing required columns: {sorted(missing_required)}"
    )


with target_engine.connect() as target_conn:
    valid_lines = {
        row[0]
        for row in target_conn.execute(
            text(
                """
                SELECT line_name
                FROM production_lines
                """
            )
        ).all()
    }

source_lines = {row["line_name"] for row in source_rows}
missing_lines = source_lines - valid_lines

if missing_lines:
    raise SystemExit(
        f"Target production_lines table is missing: {sorted(missing_lines)}"
    )


insert_columns = [
    column
    for column in source_columns
    if column in target_columns
]

if "is_active" in target_columns:
    insert_columns.append("is_active")


prepared_rows = []

for source_row in source_rows:
    target_row = {
        column: source_row[column]
        for column in source_columns
        if column in target_columns
    }

    if "is_active" in target_columns:
        target_row["is_active"] = True

    prepared_rows.append(target_row)


column_sql = ", ".join(f'"{column}"' for column in insert_columns)
value_sql = ", ".join(f":{column}" for column in insert_columns)

insert_sql = text(
    f"""
    INSERT INTO production_line_cavities ({column_sql})
    VALUES ({value_sql})
    """
)


with target_engine.begin() as target_conn:
    previous_count = target_conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM production_line_cavities
            """
        )
    ).scalar_one()

    print(f"\nPrevious target cavity count: {previous_count}")

    target_conn.execute(
        text(
            """
            TRUNCATE TABLE production_line_cavities
            RESTART IDENTITY
            """
        )
    )

    target_conn.execute(
        insert_sql,
        prepared_rows,
    )

    target_conn.execute(
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

    target_conn.execute(
        text(
            """
            INSERT INTO database_migrations (
                version,
                description,
                source_database
            )
            VALUES (
                '2.0.1',
                'Replaced placeholder cavity records with 102 actual cavity positions',
                :source_database
            )
            ON CONFLICT (version)
            DO UPDATE SET
                description = EXCLUDED.description,
                source_database = EXCLUDED.source_database,
                applied_at = NOW()
            """
        ),
        {
            "source_database": SOURCE_DB,
        },
    )


with target_engine.connect() as target_conn:
    final_count = target_conn.execute(
        text(
            """
            SELECT COUNT(*)
            FROM production_line_cavities
            """
        )
    ).scalar_one()

    final_counts = target_conn.execute(
        text(
            """
            SELECT
                line_name,
                COUNT(*) AS total,
                COUNT(*) FILTER (
                    WHERE LOWER(COALESCE(status, 'active')) = 'active'
                      AND TRIM(COALESCE(assigned_tyre_item, '')) = ''
                ) AS free,
                COUNT(*) FILTER (
                    WHERE LOWER(COALESCE(status, '')) = 'breakdown'
                ) AS breakdown,
                COUNT(*) FILTER (
                    WHERE TRIM(COALESCE(assigned_tyre_item, '')) <> ''
                ) AS used
            FROM production_line_cavities
            GROUP BY line_name
            ORDER BY line_name
            """
        )
    ).all()


print("\n=== FINAL TARGET CAVITY COUNTS ===")

for line_name, total, free, breakdown, used in final_counts:
    print(
        f"{line_name}: "
        f"total={total}, free={free}, "
        f"breakdown={breakdown}, used={used}"
    )

print(f"\nFinal total: {final_count}")

if final_count != 102:
    raise SystemExit(
        f"Migration failed: expected 102 target cavities, found {final_count}"
    )

print("\nActual cavity migration completed successfully.")
