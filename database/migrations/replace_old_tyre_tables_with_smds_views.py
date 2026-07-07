from __future__ import annotations

from datetime import datetime

from sqlalchemy import text

from app.database import engine
from app.services.smds_schema import ensure_smds_table


OLD_TABLES = [
    "tyre_item_master",
    "tyre_process_group_items",
    "tyre_process_groups",
]


def _relation_kind(conn, table_name: str) -> str | None:
    return conn.execute(
        text("""
            SELECT c.relkind
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
              AND c.relname = :table_name
        """),
        {"table_name": table_name},
    ).scalar()


def _drop_existing_relation(conn, table_name: str) -> None:
    conn.execute(text(f"DROP VIEW IF EXISTS public.{table_name} CASCADE"))
    conn.execute(text(f"DROP MATERIALIZED VIEW IF EXISTS public.{table_name} CASCADE"))


def _backup_and_drop_if_table(conn, table_name: str, stamp: str) -> None:
    kind = _relation_kind(conn, table_name)

    if kind is None:
        return

    # relkind: r = table, p = partitioned table, v = view, m = materialized view
    if kind in {"r", "p"}:
        backup_name = f"{table_name}_before_smds_{stamp}"
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS smds_backup"))
        conn.execute(text(f"CREATE TABLE smds_backup.{backup_name} AS TABLE public.{table_name}"))
        conn.execute(text(f"DROP TABLE public.{table_name}"))
        print(f"Backed up and dropped old table: public.{table_name} -> smds_backup.{backup_name}")
        return

    if kind in {"v", "m"}:
        _drop_existing_relation(conn, table_name)
        print(f"Dropped old view/materialized view: public.{table_name}")


def replace_old_tyre_tables_with_smds_views() -> None:
    """Remove old physical tyre item tables and expose SMDS-backed compatibility views."""
    ensure_smds_table()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    with engine.begin() as conn:
        smds_count = int(conn.execute(text("SELECT COUNT(*) FROM smds")).scalar() or 0)

        if smds_count <= 0:
            raise RuntimeError("SMDS table is empty. Refusing to remove old tyre item tables.")

        for table_name in OLD_TABLES:
            _backup_and_drop_if_table(conn, table_name, stamp)

        for table_name in ["tyre_process_group_items", "tyre_process_groups", "tyre_item_master"]:
            _drop_existing_relation(conn, table_name)

        conn.execute(text("""
            CREATE VIEW public.tyre_item_master AS
            SELECT
                id,
                sap_code,
                material_description AS description,
                split_part(material_description, ' ', 1) AS tyre_size,
                curing_cycle AS normal_curing_minutes,
                0::numeric AS short_cycle_curing_minutes,
                handling_time AS handling_minutes,
                'Active'::varchar(32) AS status,
                COALESCE(remark, '') AS remarks,
                imported_at AS created_at,
                updated_at
            FROM public.smds;
        """))

        conn.execute(text("""
            CREATE VIEW public.tyre_process_groups AS
            WITH grouped AS (
                SELECT
                    COALESCE(NULLIF(TRIM(key_code), ''), 'NO_KEY') AS group_key,
                    MIN(split_part(material_description, ' ', 1)) AS tyre_size,
                    MIN(NULLIF(TRIM(line), '')) AS rim_width,
                    MIN(NULLIF(TRIM(casing_type), '')) AS aperture_type,
                    MIN(NULLIF(TRIM(tred), '')) AS pattern,
                    MIN(NULLIF(TRIM(heel), '')) AS layer,
                    MIN(NULLIF(TRIM(soft), '')) AS color
                FROM public.smds
                GROUP BY COALESCE(NULLIF(TRIM(key_code), ''), 'NO_KEY')
            )
            SELECT
                row_number() OVER (ORDER BY group_key)::bigint AS id,
                group_key,
                COALESCE(tyre_size, '') AS tyre_size,
                COALESCE(rim_width, '') AS rim_width,
                COALESCE(aperture_type, '') AS aperture_type,
                COALESCE(pattern, '') AS pattern,
                COALESCE(layer, '') AS layer,
                COALESCE(color, '') AS color
            FROM grouped;
        """))

        conn.execute(text("""
            CREATE VIEW public.tyre_process_group_items AS
            WITH grouped AS (
                SELECT
                    row_number() OVER (ORDER BY group_key)::bigint AS group_id,
                    group_key
                FROM (
                    SELECT DISTINCT COALESCE(NULLIF(TRIM(key_code), ''), 'NO_KEY') AS group_key
                    FROM public.smds
                ) g
            )
            SELECT
                g.group_id,
                s.sap_code,
                s.material_description AS description
            FROM public.smds s
            JOIN grouped g
              ON g.group_key = COALESCE(NULLIF(TRIM(s.key_code), ''), 'NO_KEY');
        """))

    print("Old physical tyre item tables were removed. SMDS-backed compatibility views are active.")


def main() -> None:
    replace_old_tyre_tables_with_smds_views()


if __name__ == "__main__":
    main()
