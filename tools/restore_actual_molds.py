import os
from datetime import datetime
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
        "PGPASSWORD is not set. "
        "Run: $env:PGPASSWORD = 'your_password'"
    )


def make_url(database_name: str) -> str:
    password = quote_plus(PASSWORD)

    return (
        f"postgresql+psycopg://{USER}:{password}"
        f"@{HOST}:{PORT}/{database_name}"
    )


source_engine = create_engine(
    make_url(SOURCE_DB),
    future=True,
)

target_engine = create_engine(
    make_url(TARGET_DB),
    future=True,
)


with source_engine.connect() as conn:
    source_rows = conn.execute(
        text(
            """
            SELECT
                mold_key_code,
                mold_count,
                casing_type,
                casing_count,
                status,
                remarks,
                source_file,
                source_sheet,
                source_rows,
                created_at,
                updated_at
            FROM mold_master
            ORDER BY mold_key_code
            """
        )
    ).mappings().all()


if not source_rows:
    raise SystemExit("No mold records found in source database.")


source_keys = [
    str(row["mold_key_code"]).strip()
    for row in source_rows
    if row["mold_key_code"] is not None
]


if len(source_keys) != len(source_rows):
    raise SystemExit("Source contains empty mold key codes.")


if len(set(source_keys)) != len(source_keys):
    raise SystemExit("Source contains duplicate mold key codes.")


source_total_molds = sum(
    int(row["mold_count"] or 0)
    for row in source_rows
)

source_total_casings = sum(
    int(row["casing_count"] or 0)
    for row in source_rows
)


print("=== SOURCE MOLD SUMMARY ===")
print(f"Mold key codes: {len(source_rows)}")
print(f"Total molds: {source_total_molds}")
print(f"Total linked casings: {source_total_casings}")


target_columns = {
    column["name"]
    for column in inspect(target_engine).get_columns("mold_master")
}


required_target_columns = {
    "mold_key_code",
    "mold_count",
}

missing_columns = required_target_columns - target_columns

if missing_columns:
    raise SystemExit(
        "Target mold_master is missing required columns: "
        f"{sorted(missing_columns)}"
    )


prepared_rows = []

for source_row in source_rows:
    key_code = str(source_row["mold_key_code"]).strip()
    mold_count = int(source_row["mold_count"] or 0)
    status = source_row["status"] or "Active"

    target_row = {}

    direct_columns = [
        "mold_key_code",
        "mold_count",
        "casing_type",
        "casing_count",
        "status",
        "remarks",
        "source_file",
        "source_sheet",
        "source_rows",
        "created_at",
        "updated_at",
    ]

    for column in direct_columns:
        if column in target_columns:
            target_row[column] = source_row[column]

    if "key_code" in target_columns:
        target_row["key_code"] = key_code

    if "description" in target_columns:
        target_row["description"] = key_code

    if "is_active" in target_columns:
        target_row["is_active"] = (
            str(status).strip().lower() == "active"
        )

    if "production_mold_count" in target_columns:
        target_row["production_mold_count"] = 0

    if "breakdown_mold_count" in target_columns:
        target_row["breakdown_mold_count"] = 0

    if "planning_reserved_mold_count" in target_columns:
        target_row["planning_reserved_mold_count"] = 0

    if "available_mold_count" in target_columns:
        target_row["available_mold_count"] = mold_count

    if "total_mold_count" in target_columns:
        target_row["total_mold_count"] = mold_count

    prepared_rows.append(target_row)


insert_columns = list(prepared_rows[0].keys())

column_sql = ", ".join(
    f'"{column}"'
    for column in insert_columns
)

values_sql = ", ".join(
    f":{column}"
    for column in insert_columns
)

insert_statement = text(
    f"""
    INSERT INTO mold_master ({column_sql})
    VALUES ({values_sql})
    """
)


backup_table = (
    "mold_master_backup_before_actual_restore_"
    + datetime.now().strftime("%Y%m%d_%H%M%S")
)


with target_engine.begin() as conn:
    current_count = conn.execute(
        text("SELECT COUNT(*) FROM mold_master")
    ).scalar_one()

    print(f"\nCurrent target records: {current_count}")
    print(f"Internal backup table: {backup_table}")

    conn.execute(
        text(
            f"""
            CREATE TABLE "{backup_table}" AS
            TABLE mold_master
            """
        )
    )

    conn.execute(
        text("DELETE FROM mold_master")
    )

    conn.execute(
        insert_statement,
        prepared_rows,
    )

    conn.execute(
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

    conn.execute(
        text(
            """
            INSERT INTO database_migrations (
                version,
                description,
                source_database
            )
            VALUES (
                '2.0.2',
                'Replaced incorrect mold records with actual mold master data',
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


with target_engine.connect() as conn:
    final_rows = conn.execute(
        text(
            """
            SELECT
                COUNT(*) AS mold_key_codes,
                SUM(COALESCE(mold_count, 0)) AS total_molds,
                SUM(COALESCE(production_mold_count, 0))
                    AS production_molds,
                SUM(COALESCE(breakdown_mold_count, 0))
                    AS breakdown_molds,
                SUM(COALESCE(planning_reserved_mold_count, 0))
                    AS reserved_molds
            FROM mold_master
            """
        )
    ).mappings().one()

    samples = conn.execute(
        text(
            """
            SELECT
                mold_key_code,
                mold_count,
                casing_type,
                casing_count
            FROM mold_master
            ORDER BY mold_key_code
            LIMIT 10
            """
        )
    ).all()


print("\n=== FINAL TARGET SUMMARY ===")

for name, value in final_rows.items():
    print(f"{name}: {value}")


print("\n=== SAMPLE RECORDS ===")

for row in samples:
    print(row)


if final_rows["mold_key_codes"] != len(source_rows):
    raise SystemExit(
        "Migration verification failed: "
        f"expected {len(source_rows)} records, "
        f"found {final_rows['mold_key_codes']}."
    )


if final_rows["total_molds"] != source_total_molds:
    raise SystemExit(
        "Migration verification failed: "
        f"expected {source_total_molds} molds, "
        f"found {final_rows['total_molds']}."
    )


print("\nActual mold data migration completed successfully.")
