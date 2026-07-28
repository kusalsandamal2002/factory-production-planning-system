from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import re
from typing import Any

from sqlalchemy import inspect, text

from app.database import engine
from app.services.master_data_normalization import (
    identifier_key,
    is_no_casing,
    line_identity,
    normalize_casing_type,
    normalize_line_name,
    normalize_mold_key,
    normalize_sap_code,
)


BACKUP_TABLES = (
    "smds",
    "mold_master",
    "casing_master",
    "casing_units",
    "planning_resource_reservations",
    "production_lines",
    "production_line_cavities",
    "mpps_shipment_items",
    "mpps_sap_stock_items",
)


def _safe_identifier(value: str) -> str:
    if not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]*",
        value,
    ):
        raise ValueError(
            f"Unsafe SQL identifier: {value}"
        )
    return f'"{value}"'


def _table_exists(conn, table_name: str) -> bool:
    return (
        conn.execute(
            text(
                """
                SELECT to_regclass(
                    :qualified_name
                )
                """
            ),
            {
                "qualified_name": (
                    f"public.{table_name}"
                )
            },
        ).scalar_one()
        is not None
    )


def _columns(
    inspector,
    table_name: str,
) -> set[str]:
    return {
        str(column["name"])
        for column
        in inspector.get_columns(table_name)
    }


def _install_normalization_functions(
    conn,
) -> None:
    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.mpps_clean_text(value TEXT)
            RETURNS TEXT
            LANGUAGE SQL
            IMMUTABLE
            PARALLEL SAFE
            AS $$
                SELECT regexp_replace(
                    btrim(
                        replace(
                            COALESCE(value, ''),
                            chr(160),
                            ' '
                        )
                    ),
                    '\s+',
                    ' ',
                    'g'
                )
            $$
            """
        )
    )

    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.mpps_identifier_key(value TEXT)
            RETURNS TEXT
            LANGUAGE SQL
            IMMUTABLE
            PARALLEL SAFE
            AS $$
                SELECT UPPER(
                    regexp_replace(
                        regexp_replace(
                            regexp_replace(
                                regexp_replace(
                                    regexp_replace(
                                        regexp_replace(
                                            regexp_replace(
                                                regexp_replace(
                                                    regexp_replace(
                                                        public.mpps_clean_text(value),
                                                        '‐',
                                                        '-',
                                                        'g'
                                                    ),
                                                    '‑',
                                                    '-',
                                                    'g'
                                                ),
                                                '–',
                                                '-',
                                                'g'
                                            ),
                                            '—',
                                            '-',
                                            'g'
                                        ),
                                        '−',
                                        '-',
                                        'g'
                                    ),
                                    '×|✕',
                                    'X',
                                    'g'
                                ),
                                '([0-9])\s*[Xx]\s*([0-9])',
                                '\1X\2',
                                'g'
                            ),
                            '\s*-\s*',
                            '-',
                            'g'
                        ),
                        '\s*/\s*',
                        '/',
                        'g'
                    )
                )
            $$
            """
        )
    )

    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.mpps_line_key(value TEXT)
            RETURNS TEXT
            LANGUAGE SQL
            IMMUTABLE
            PARALLEL SAFE
            AS $$
                SELECT regexp_replace(
                    regexp_replace(
                        public.mpps_identifier_key(value),
                        '[^A-Z0-9]+',
                        ' ',
                        'g'
                    ),
                    '\s+',
                    ' ',
                    'g'
                )
            $$
            """
        )
    )

    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.mpps_canonical_sap(value TEXT)
            RETURNS TEXT
            LANGUAGE SQL
            IMMUTABLE
            PARALLEL SAFE
            AS $$
                SELECT public.mpps_identifier_key(value)
            $$
            """
        )
    )

    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.mpps_canonical_mold_key(value TEXT)
            RETURNS TEXT
            LANGUAGE SQL
            IMMUTABLE
            PARALLEL SAFE
            AS $$
                SELECT CASE
                    WHEN public.mpps_identifier_key(value)
                         IN (
                            '',
                            '-',
                            '--',
                            'N/A',
                            'NA',
                            'NONE',
                            'NULL',
                            'UNKNOWN',
                            'NOT AVAILABLE'
                         )
                    THEN '-'
                    ELSE public.mpps_identifier_key(value)
                END
            $$
            """
        )
    )

    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.mpps_canonical_casing(value TEXT)
            RETURNS TEXT
            LANGUAGE SQL
            IMMUTABLE
            PARALLEL SAFE
            AS $$
                SELECT CASE
                    WHEN public.mpps_identifier_key(value)
                         IN (
                            '',
                            '-',
                            '--',
                            'UNKNOWN',
                            'NULL'
                         )
                    THEN '-'
                    WHEN regexp_replace(
                            public.mpps_identifier_key(value),
                            '[^A-Z0-9]+',
                            '',
                            'g'
                         )
                         IN (
                            'NOCASING',
                            'WITHOUTCASING',
                            'WITHOUTTYRECASING',
                            'NOTREQUIRED',
                            'NONE',
                            'NA'
                         )
                    THEN 'No Casing'
                    ELSE public.mpps_clean_text(value)
                END
            $$
            """
        )
    )

    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.mpps_resolve_mold_key(value TEXT)
            RETURNS TEXT
            LANGUAGE plpgsql
            STABLE
            AS $$
            DECLARE
                resolved_value TEXT;
                canonical_value TEXT;
            BEGIN
                canonical_value :=
                    public.mpps_canonical_mold_key(value);

                SELECT mold_key_code
                INTO resolved_value
                FROM mold_master
                WHERE public.mpps_identifier_key(
                        mold_key_code
                      )
                    = public.mpps_identifier_key(
                        canonical_value
                      )
                ORDER BY id
                LIMIT 1;

                RETURN COALESCE(
                    resolved_value,
                    canonical_value
                );
            END;
            $$
            """
        )
    )

    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.mpps_resolve_casing_type(value TEXT)
            RETURNS TEXT
            LANGUAGE plpgsql
            STABLE
            AS $$
            DECLARE
                resolved_value TEXT;
                canonical_value TEXT;
            BEGIN
                canonical_value :=
                    public.mpps_canonical_casing(value);

                SELECT casing_type
                INTO resolved_value
                FROM casing_master
                WHERE public.mpps_identifier_key(
                        casing_type
                      )
                    = public.mpps_identifier_key(
                        canonical_value
                      )
                ORDER BY id
                LIMIT 1;

                RETURN COALESCE(
                    resolved_value,
                    canonical_value
                );
            END;
            $$
            """
        )
    )

    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.mpps_resolve_line_name(value TEXT)
            RETURNS TEXT
            LANGUAGE plpgsql
            STABLE
            AS $$
            DECLARE
                resolved_value TEXT;
                cleaned_value TEXT;
            BEGIN
                cleaned_value := public.mpps_clean_text(value);

                SELECT line_name
                INTO resolved_value
                FROM production_lines
                WHERE public.mpps_line_key(line_name)
                    = public.mpps_line_key(cleaned_value)
                ORDER BY line_name
                LIMIT 1;

                RETURN COALESCE(
                    resolved_value,
                    cleaned_value
                );
            END;
            $$
            """
        )
    )


def _ensure_schema_columns(
    conn,
) -> None:
    statements = (
        """
        ALTER TABLE mold_master
        ADD COLUMN IF NOT EXISTS
            key_code TEXT
        """,
        """
        ALTER TABLE mold_master
        ADD COLUMN IF NOT EXISTS
            description TEXT
        """,
        """
        ALTER TABLE mold_master
        ADD COLUMN IF NOT EXISTS
            is_active BOOLEAN DEFAULT TRUE
        """,
        """
        ALTER TABLE casing_master
        ADD COLUMN IF NOT EXISTS
            total_casing_count INTEGER
            NOT NULL DEFAULT 0
        """,
        """
        ALTER TABLE casing_master
        ADD COLUMN IF NOT EXISTS
            production_casing_count INTEGER
            NOT NULL DEFAULT 0
        """,
        """
        ALTER TABLE casing_master
        ADD COLUMN IF NOT EXISTS
            breakdown_casing_count INTEGER
            NOT NULL DEFAULT 0
        """,
        """
        ALTER TABLE casing_master
        ADD COLUMN IF NOT EXISTS
            planning_reserved_casing_count INTEGER
            NOT NULL DEFAULT 0
        """,
        """
        ALTER TABLE casing_master
        ADD COLUMN IF NOT EXISTS
            casing_code TEXT
        """,
        """
        ALTER TABLE casing_master
        ADD COLUMN IF NOT EXISTS
            description TEXT
        """,
        """
        ALTER TABLE casing_master
        ADD COLUMN IF NOT EXISTS
            casing_count INTEGER DEFAULT 0
        """,
        """
        ALTER TABLE casing_master
        ADD COLUMN IF NOT EXISTS
            is_active BOOLEAN DEFAULT TRUE
        """,
    )

    for statement in statements:
        conn.execute(text(statement))


def _create_backups(
    conn,
    stamp: str,
) -> None:
    conn.execute(
        text(
            """
            CREATE SCHEMA IF NOT EXISTS
                mpps_integrity_backup
            """
        )
    )

    for table_name in BACKUP_TABLES:
        if not _table_exists(
            conn,
            table_name,
        ):
            continue

        backup_name = (
            f"{table_name}_{stamp}"
        )
        conn.execute(
            text(
                f"""
                CREATE TABLE
                    mpps_integrity_backup.{_safe_identifier(backup_name)}
                AS TABLE
                    public.{_safe_identifier(table_name)}
                """
            )
        )


def _precheck_normalized_uniqueness(
    conn,
) -> None:
    checks = (
        (
            "smds",
            "sap_code",
            "mpps_identifier_key",
        ),
        (
            "mpps_sap_stock_items",
            "sap_code",
            "mpps_identifier_key",
        ),
        (
            "production_lines",
            "line_name",
            "mpps_line_key",
        ),
    )

    for table_name, column_name, function_name in checks:
        if not _table_exists(
            conn,
            table_name,
        ):
            continue

        duplicates = conn.execute(
            text(
                f"""
                SELECT
                    {function_name}(
                        {_safe_identifier(column_name)}
                    ) AS normalized_value,
                    COUNT(*) AS row_count,
                    array_agg(
                        {_safe_identifier(column_name)}
                    ) AS variants
                FROM {_safe_identifier(table_name)}
                WHERE public.mpps_clean_text(
                        {_safe_identifier(column_name)}
                      ) <> ''
                GROUP BY
                    {function_name}(
                        {_safe_identifier(column_name)}
                    )
                HAVING COUNT(*) > 1
                LIMIT 20
                """
            )
        ).mappings().all()

        if duplicates:
            raise RuntimeError(
                "Cannot safely normalize "
                f"{table_name}.{column_name}. "
                "Duplicate normalized identifiers: "
                f"{[dict(row) for row in duplicates]}"
            )


def _casing_code(
    casing_type: str,
    casing_no: int,
) -> str:
    prefix = re.sub(
        r"[^A-Z0-9]+",
        "-",
        identifier_key(casing_type),
    ).strip("-")
    return (
        f"{prefix or 'CASING'}-"
        f"{int(casing_no):03d}"
    )


def _merge_and_normalize_casing(
    conn,
) -> None:
    rows = conn.execute(
        text(
            """
            SELECT *
            FROM casing_master
            ORDER BY id
            """
        )
    ).mappings().all()

    grouped: dict[str, list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for raw in rows:
        row = dict(raw)
        grouped[
            identifier_key(
                row.get("casing_type")
            )
        ].append(row)

    for identity, group in grouped.items():
        if not identity:
            continue

        normalized_values = [
            normalize_casing_type(
                row.get("casing_type")
            )
            for row in group
        ]
        canonical = (
            "No Casing"
            if any(
                is_no_casing(value)
                for value in normalized_values
            )
            else normalized_values[0]
        )

        keeper = next(
            (
                row
                for row in group
                if str(
                    row.get("casing_type")
                    or ""
                )
                == canonical
            ),
            group[0],
        )
        keeper_id = int(keeper["id"])

        # Move unit rows to temporary values first so
        # unique (type, number/code) indexes cannot clash.
        unit_rows = conn.execute(
            text(
                """
                SELECT id, casing_no
                FROM casing_units
                WHERE public.mpps_identifier_key(
                        casing_type
                      ) = :identity
                ORDER BY casing_no, id
                """
            ),
            {"identity": identity},
        ).mappings().all()

        for unit in unit_rows:
            unit_id = int(unit["id"])
            conn.execute(
                text(
                    """
                    UPDATE casing_units
                    SET
                        casing_type = :temporary_type,
                        casing_code = :temporary_code
                    WHERE id = :id
                    """
                ),
                {
                    "id": unit_id,
                    "temporary_type": (
                        f"__MPPS_CASING_MERGE_"
                        f"{keeper_id}_{unit_id}"
                    ),
                    "temporary_code": (
                        f"TMP-{keeper_id}-"
                        f"{unit_id}"
                    ),
                },
            )

        if is_no_casing(canonical):
            conn.execute(
                text(
                    """
                    DELETE FROM casing_units
                    WHERE LEFT(
                            casing_type,
                            20
                          ) = '__MPPS_CASING_MERGE_'
                    """
                )
            )
        else:
            for index, unit in enumerate(
                unit_rows,
                start=1,
            ):
                conn.execute(
                    text(
                        """
                        UPDATE casing_units
                        SET
                            casing_type =
                                :casing_type,
                            casing_no =
                                :casing_no,
                            casing_code =
                                :casing_code,
                            updated_at =
                                CURRENT_TIMESTAMP
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": int(unit["id"]),
                        "casing_type": canonical,
                        "casing_no": index,
                        "casing_code": _casing_code(
                            canonical,
                            index,
                        ),
                    },
                )

        for table_name, column_name in (
            ("smds", "casing_type"),
            ("mold_master", "casing_type"),
        ):
            if _table_exists(
                conn,
                table_name,
            ):
                conn.execute(
                    text(
                        f"""
                        UPDATE
                            {_safe_identifier(table_name)}
                        SET
                            {_safe_identifier(column_name)}
                                = :canonical
                        WHERE public.mpps_identifier_key(
                                {_safe_identifier(column_name)}
                              )
                            = :identity
                        """
                    ),
                    {
                        "canonical": canonical,
                        "identity": identity,
                    },
                )

        if _table_exists(
            conn,
            "planning_resource_reservations",
        ):
            conn.execute(
                text(
                    """
                    UPDATE
                        planning_resource_reservations
                    SET resource_key = :canonical
                    WHERE resource_type = 'casing'
                      AND public.mpps_identifier_key(
                            resource_key
                          ) = :identity
                    """
                ),
                {
                    "canonical": canonical,
                    "identity": identity,
                },
            )

        duplicate_ids = [
            int(row["id"])
            for row in group
            if int(row["id"]) != keeper_id
        ]

        for duplicate_id in duplicate_ids:
            conn.execute(
                text(
                    """
                    DELETE FROM casing_master
                    WHERE id = :id
                    """
                ),
                {"id": duplicate_id},
            )

        conn.execute(
            text(
                """
                UPDATE casing_master
                SET
                    casing_type =
                        :canonical_casing_type,
                    casing_code =
                        :canonical_casing_code,
                    description =
                        :canonical_description,
                    is_active = TRUE,
                    status = COALESCE(
                        NULLIF(status, ''),
                        'Active'
                    ),
                    updated_at =
                        CURRENT_TIMESTAMP
                WHERE id = :keeper_id
                """
            ),
            {
                "canonical_casing_type": canonical,
                "canonical_casing_code": canonical,
                "canonical_description": canonical,
                "keeper_id": keeper_id,
            },
        )

    # Canonicalize unresolved casing values as well.
    conn.execute(
        text(
            """
            UPDATE smds
            SET casing_type =
                public.mpps_resolve_casing_type(
                    casing_type
                )
            """
        )
    )
    conn.execute(
        text(
            """
            UPDATE mold_master
            SET casing_type =
                public.mpps_resolve_casing_type(
                    casing_type
                )
            """
        )
    )
    conn.execute(
        text(
            """
            UPDATE casing_units
            SET casing_type =
                public.mpps_resolve_casing_type(
                    casing_type
                )
            """
        )
    )
    conn.execute(
        text(
            """
            UPDATE planning_resource_reservations
            SET resource_key =
                public.mpps_resolve_casing_type(
                    resource_key
                )
            WHERE resource_type = 'casing'
            """
        )
    )

    no_casing_id = conn.execute(
        text(
            """
            SELECT id
            FROM casing_master
            WHERE public.mpps_identifier_key(
                    casing_type
                  ) = 'NO CASING'
            LIMIT 1
            """
        )
    ).scalar_one_or_none()

    if no_casing_id is None:
        conn.execute(
            text(
                """
                INSERT INTO casing_master (
                    casing_type,
                    casing_code,
                    description,
                    available_casing_count,
                    total_casing_count,
                    production_casing_count,
                    breakdown_casing_count,
                    planning_reserved_casing_count,
                    casing_count,
                    status,
                    is_active,
                    remarks
                )
                VALUES (
                    'No Casing',
                    'No Casing',
                    'No Casing',
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    'Active',
                    TRUE,
                    'Planning rule; no physical unit.'
                )
                """
            )
        )

    # Physical casing units are authoritative.
    # Never invent physical units from old aggregate counters.
    # The counters below are rebuilt only from casing_units.

    # Recompute authoritative counters.
    conn.execute(
        text(
            """
            UPDATE casing_master master
            SET
                total_casing_count = CASE
                    WHEN public.mpps_identifier_key(
                            master.casing_type
                         ) = 'NO CASING'
                    THEN 0
                    ELSE (
                        SELECT COUNT(*)
                        FROM casing_units unit
                        WHERE public.mpps_identifier_key(
                                unit.casing_type
                              )
                            = public.mpps_identifier_key(
                                master.casing_type
                              )
                    )
                END,
                available_casing_count = CASE
                    WHEN public.mpps_identifier_key(
                            master.casing_type
                         ) = 'NO CASING'
                    THEN 0
                    ELSE (
                        SELECT COUNT(*)
                        FROM casing_units unit
                        WHERE public.mpps_identifier_key(
                                unit.casing_type
                              )
                            = public.mpps_identifier_key(
                                master.casing_type
                              )
                          AND LOWER(
                                COALESCE(
                                    unit.condition_status,
                                    'Active'
                                )
                              ) = 'active'
                          AND LOWER(
                                COALESCE(
                                    unit.stock_status,
                                    'Free'
                                )
                              ) = 'free'
                    )
                END,
                production_casing_count = CASE
                    WHEN public.mpps_identifier_key(
                            master.casing_type
                         ) = 'NO CASING'
                    THEN 0
                    ELSE (
                        SELECT COUNT(*)
                        FROM casing_units unit
                        WHERE public.mpps_identifier_key(
                                unit.casing_type
                              )
                            = public.mpps_identifier_key(
                                master.casing_type
                              )
                          AND LOWER(
                                COALESCE(
                                    unit.stock_status,
                                    ''
                                )
                              ) = 'in use'
                    )
                END,
                breakdown_casing_count = CASE
                    WHEN public.mpps_identifier_key(
                            master.casing_type
                         ) = 'NO CASING'
                    THEN 0
                    ELSE (
                        SELECT COUNT(*)
                        FROM casing_units unit
                        WHERE public.mpps_identifier_key(
                                unit.casing_type
                              )
                            = public.mpps_identifier_key(
                                master.casing_type
                              )
                          AND LOWER(
                                COALESCE(
                                    unit.condition_status,
                                    ''
                                )
                              ) = 'breakdown'
                    )
                END,
                planning_reserved_casing_count = CASE
                    WHEN public.mpps_identifier_key(
                            master.casing_type
                         ) = 'NO CASING'
                    THEN 0
                    ELSE (
                        SELECT COUNT(*)
                        FROM casing_units unit
                        WHERE public.mpps_identifier_key(
                                unit.casing_type
                              )
                            = public.mpps_identifier_key(
                                master.casing_type
                              )
                          AND LOWER(
                                COALESCE(
                                    unit.stock_status,
                                    ''
                                )
                              ) = 'reserved'
                    )
                END,
                casing_count = CASE
                    WHEN public.mpps_identifier_key(
                            master.casing_type
                         ) = 'NO CASING'
                    THEN 0
                    ELSE (
                        SELECT COUNT(*)
                        FROM casing_units unit
                        WHERE public.mpps_identifier_key(
                                unit.casing_type
                              )
                            = public.mpps_identifier_key(
                                master.casing_type
                              )
                    )
                END,
                updated_at = CURRENT_TIMESTAMP
            """
        )
    )


def _merge_and_normalize_molds(
    conn,
) -> None:
    rows = conn.execute(
        text(
            """
            SELECT *
            FROM mold_master
            ORDER BY id
            """
        )
    ).mappings().all()

    grouped: dict[str, list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for raw in rows:
        row = dict(raw)
        grouped[
            identifier_key(
                row.get("mold_key_code")
                or row.get("key_code")
            )
        ].append(row)

    for identity, group in grouped.items():
        if not identity:
            continue

        canonical = normalize_mold_key(
            group[0].get("mold_key_code")
            or group[0].get("key_code")
        )
        keeper = group[0]
        keeper_id = int(keeper["id"])

        # Use max rather than sum to avoid overstating
        # physical inventory when duplicate import rows
        # differ only by formatting.
        mold_count = max(
            int(row.get("mold_count") or 0)
            for row in group
        )
        production_count = max(
            int(
                row.get(
                    "production_mold_count"
                )
                or 0
            )
            for row in group
        )
        breakdown_count = max(
            int(
                row.get(
                    "breakdown_mold_count"
                )
                or 0
            )
            for row in group
        )
        reserved_count = max(
            int(
                row.get(
                    "planning_reserved_mold_count"
                )
                or 0
            )
            for row in group
        )
        casing_value = next(
            (
                normalize_casing_type(
                    row.get("casing_type")
                )
                for row in group
                if normalize_casing_type(
                    row.get("casing_type")
                )
                not in {"", "-"}
            ),
            "No Casing",
        )

        duplicate_ids = [
            int(row["id"])
            for row in group
            if int(row["id"]) != keeper_id
        ]

        for duplicate_id in duplicate_ids:
            conn.execute(
                text(
                    """
                    DELETE FROM mold_master
                    WHERE id = :id
                    """
                ),
                {"id": duplicate_id},
            )

        conn.execute(
            text(
                """
                UPDATE mold_master
                SET
                    mold_key_code =
                        :canonical_mold_key_code,
                    key_code =
                        :canonical_key_code,
                    description = COALESCE(
                        NULLIF(
                            public.mpps_clean_text(description),
                            ''
                        ),
                        :canonical_description
                    ),
                    mold_count = :mold_count,
                    production_mold_count =
                        :production_count,
                    breakdown_mold_count =
                        :breakdown_count,
                    planning_reserved_mold_count =
                        :reserved_count,
                    casing_type =
                        public.mpps_resolve_casing_type(
                            :casing_type
                        ),
                    status = COALESCE(
                        NULLIF(status, ''),
                        'Active'
                    ),
                    is_active = COALESCE(
                        is_active,
                        TRUE
                    ),
                    updated_at =
                        CURRENT_TIMESTAMP
                WHERE id = :keeper_id
                """
            ),
            {
                "canonical_mold_key_code": canonical,
                "canonical_key_code": canonical,
                "canonical_description": canonical,
                "mold_count": mold_count,
                "production_count": production_count,
                "breakdown_count": breakdown_count,
                "reserved_count": reserved_count,
                "casing_type": casing_value,
                "keeper_id": keeper_id,
            },
        )

        conn.execute(
            text(
                """
                UPDATE smds
                SET
                    key_code = :canonical,
                    updated_at =
                        CURRENT_TIMESTAMP
                WHERE public.mpps_identifier_key(
                        key_code
                      ) = :identity
                """
            ),
            {
                "canonical": canonical,
                "identity": identity,
            },
        )
        conn.execute(
            text(
                """
                UPDATE planning_resource_reservations
                SET resource_key = :canonical
                WHERE resource_type = 'mold'
                  AND public.mpps_identifier_key(
                        resource_key
                      ) = :identity
                """
            ),
            {
                "canonical": canonical,
                "identity": identity,
            },
        )

    conn.execute(
        text(
            """
            UPDATE smds
            SET
                key_code =
                    public.mpps_resolve_mold_key(
                        key_code
                    ),
                sap_code =
                    public.mpps_canonical_sap(
                        sap_code
                    ),
                line =
                    public.mpps_resolve_line_name(
                        line
                    )
            """
        )
    )
    conn.execute(
        text(
            """
            UPDATE planning_resource_reservations
            SET
                resource_key =
                    public.mpps_resolve_mold_key(
                        resource_key
                    )
            WHERE resource_type = 'mold'
            """
        )
    )


def _normalize_lines_and_sap(
    conn,
) -> None:
    if _table_exists(
        conn,
        "production_lines",
    ):
        line_rows = conn.execute(
            text(
                """
                SELECT id, line_name
                FROM production_lines
                ORDER BY line_name
                """
            )
        ).mappings().all()

        for row in line_rows:
            canonical = normalize_line_name(
                row["line_name"]
            )
            conn.execute(
                text(
                    """
                    UPDATE production_lines
                    SET
                        line_name = :canonical,
                        updated_at =
                            CURRENT_TIMESTAMP
                    WHERE id = :id
                    """
                ),
                {
                    "id": row["id"],
                    "canonical": canonical,
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE production_line_cavities
                    SET
                        line_name = :canonical,
                        updated_at =
                            CURRENT_TIMESTAMP
                    WHERE public.mpps_line_key(
                            line_name
                          ) = public.mpps_line_key(
                            :original
                          )
                    """
                ),
                {
                    "canonical": canonical,
                    "original": row["line_name"],
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE smds
                    SET line = :canonical
                    WHERE public.mpps_line_key(line)
                        = public.mpps_line_key(
                            :original
                          )
                    """
                ),
                {
                    "canonical": canonical,
                    "original": row["line_name"],
                },
            )
            conn.execute(
                text(
                    """
                    UPDATE
                        planning_resource_reservations
                    SET resource_key = :canonical
                    WHERE resource_type =
                            'line_cavity'
                      AND public.mpps_line_key(
                            resource_key
                          ) = public.mpps_line_key(
                            :original
                          )
                    """
                ),
                {
                    "canonical": canonical,
                    "original": row["line_name"],
                },
            )

    for table_name in (
        "mpps_shipment_items",
        "mpps_sap_stock_items",
    ):
        if _table_exists(
            conn,
            table_name,
        ):
            conn.execute(
                text(
                    f"""
                    UPDATE
                        {_safe_identifier(table_name)}
                    SET sap_code =
                        public.mpps_canonical_sap(
                            sap_code
                        )
                    """
                )
            )

    if _table_exists(
        conn,
        "planning_resource_reservations",
    ):
        conn.execute(
            text(
                """
                UPDATE
                    planning_resource_reservations
                SET
                    resource_type =
                        LOWER(
                            public.mpps_clean_text(
                                resource_type
                            )
                        ),
                    sap_code =
                        public.mpps_canonical_sap(
                            sap_code
                        ),
                    resource_key = CASE
                        WHEN LOWER(
                                public.mpps_clean_text(
                                    resource_type
                                )
                             ) = 'mold'
                        THEN public.mpps_resolve_mold_key(
                                resource_key
                             )
                        WHEN LOWER(
                                public.mpps_clean_text(
                                    resource_type
                                )
                             ) = 'casing'
                        THEN public.mpps_resolve_casing_type(
                                resource_key
                             )
                        WHEN LOWER(
                                public.mpps_clean_text(
                                    resource_type
                                )
                             ) IN (
                                'line',
                                'line_cavity',
                                'production_line'
                             )
                        THEN public.mpps_resolve_line_name(
                                resource_key
                             )
                        ELSE public.mpps_clean_text(
                                resource_key
                             )
                    END
                """
            )
        )


def _install_triggers(
    conn,
) -> None:
    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.trg_mpps_normalize_smds()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
                NEW.sap_code :=
                    public.mpps_canonical_sap(
                        NEW.sap_code
                    );
                NEW.key_code :=
                    public.mpps_resolve_mold_key(
                        NEW.key_code
                    );
                NEW.casing_type :=
                    public.mpps_resolve_casing_type(
                        NEW.casing_type
                    );
                NEW.line :=
                    public.mpps_resolve_line_name(
                        NEW.line
                    );
                RETURN NEW;
            END;
            $$
            """
        )
    )
    conn.execute(
        text(
            """
            DROP TRIGGER IF EXISTS
                trg_normalize_smds_identifiers
            ON smds
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER
                trg_normalize_smds_identifiers
            BEFORE INSERT OR UPDATE OF
                sap_code,
                key_code,
                casing_type,
                line
            ON smds
            FOR EACH ROW
            EXECUTE FUNCTION
                public.trg_mpps_normalize_smds()
            """
        )
    )

    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.trg_mpps_normalize_mold_master()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
                NEW.mold_key_code :=
                    public.mpps_canonical_mold_key(
                        COALESCE(
                            NULLIF(
                                public.mpps_clean_text(
                                    NEW.mold_key_code
                                ),
                                ''
                            ),
                            NEW.key_code
                        )
                    );
                NEW.key_code :=
                    NEW.mold_key_code;
                NEW.description :=
                    COALESCE(
                        NULLIF(
                            public.mpps_clean_text(
                                NEW.description
                            ),
                            ''
                        ),
                        NEW.mold_key_code
                    );
                NEW.casing_type :=
                    public.mpps_resolve_casing_type(
                        NEW.casing_type
                    );
                NEW.is_active :=
                    COALESCE(
                        NEW.is_active,
                        TRUE
                    );
                RETURN NEW;
            END;
            $$
            """
        )
    )
    conn.execute(
        text(
            """
            DROP TRIGGER IF EXISTS
                trg_normalize_mold_master
            ON mold_master
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER
                trg_normalize_mold_master
            BEFORE INSERT OR UPDATE OF
                mold_key_code,
                key_code,
                casing_type,
                description
            ON mold_master
            FOR EACH ROW
            EXECUTE FUNCTION
                public.trg_mpps_normalize_mold_master()
            """
        )
    )

    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.trg_mpps_normalize_casing_master()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
                NEW.casing_type :=
                    public.mpps_canonical_casing(
                        NEW.casing_type
                    );
                NEW.casing_code :=
                    NEW.casing_type;
                NEW.description :=
                    COALESCE(
                        NULLIF(
                            public.mpps_clean_text(
                                NEW.description
                            ),
                            ''
                        ),
                        NEW.casing_type
                    );
                NEW.is_active :=
                    COALESCE(
                        NEW.is_active,
                        TRUE
                    );

                IF public.mpps_identifier_key(
                        NEW.casing_type
                   ) = 'NO CASING'
                THEN
                    NEW.available_casing_count := 0;
                    NEW.total_casing_count := 0;
                    NEW.production_casing_count := 0;
                    NEW.breakdown_casing_count := 0;
                    NEW.planning_reserved_casing_count := 0;
                    NEW.casing_count := 0;
                END IF;

                RETURN NEW;
            END;
            $$
            """
        )
    )
    conn.execute(
        text(
            """
            DROP TRIGGER IF EXISTS
                trg_normalize_casing_master
            ON casing_master
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER
                trg_normalize_casing_master
            BEFORE INSERT OR UPDATE OF
                casing_type,
                casing_code,
                description
            ON casing_master
            FOR EACH ROW
            EXECUTE FUNCTION
                public.trg_mpps_normalize_casing_master()
            """
        )
    )

    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.trg_mpps_normalize_casing_unit()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
                NEW.casing_type :=
                    public.mpps_resolve_casing_type(
                        NEW.casing_type
                    );
                NEW.casing_code :=
                    public.mpps_clean_text(
                        NEW.casing_code
                    );

                IF public.mpps_identifier_key(
                        NEW.casing_type
                   ) = 'NO CASING'
                THEN
                    RAISE EXCEPTION
                        'Physical casing units cannot use No Casing';
                END IF;

                IF NOT EXISTS (
                    SELECT 1
                    FROM casing_master master
                    WHERE public.mpps_identifier_key(
                            master.casing_type
                          )
                        = public.mpps_identifier_key(
                            NEW.casing_type
                          )
                )
                THEN
                    RAISE EXCEPTION
                        'Casing type % does not exist in Casing Master',
                        NEW.casing_type;
                END IF;

                RETURN NEW;
            END;
            $$
            """
        )
    )
    conn.execute(
        text(
            """
            DROP TRIGGER IF EXISTS
                trg_normalize_casing_unit
            ON casing_units
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER
                trg_normalize_casing_unit
            BEFORE INSERT OR UPDATE OF
                casing_type,
                casing_code
            ON casing_units
            FOR EACH ROW
            EXECUTE FUNCTION
                public.trg_mpps_normalize_casing_unit()
            """
        )
    )

    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.trg_mpps_normalize_reservation()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
                NEW.resource_type :=
                    LOWER(
                        public.mpps_clean_text(
                            NEW.resource_type
                        )
                    );
                NEW.sap_code :=
                    public.mpps_canonical_sap(
                        NEW.sap_code
                    );

                IF NEW.resource_type = 'mold'
                THEN
                    NEW.resource_key :=
                        public.mpps_resolve_mold_key(
                            NEW.resource_key
                        );
                ELSIF NEW.resource_type = 'casing'
                THEN
                    NEW.resource_key :=
                        public.mpps_resolve_casing_type(
                            NEW.resource_key
                        );
                ELSIF NEW.resource_type IN (
                    'line',
                    'line_cavity',
                    'production_line'
                )
                THEN
                    NEW.resource_key :=
                        public.mpps_resolve_line_name(
                            NEW.resource_key
                        );
                ELSE
                    NEW.resource_key :=
                        public.mpps_clean_text(
                            NEW.resource_key
                        );
                END IF;

                RETURN NEW;
            END;
            $$
            """
        )
    )
    conn.execute(
        text(
            """
            DROP TRIGGER IF EXISTS
                trg_normalize_planning_reservation
            ON planning_resource_reservations
            """
        )
    )
    conn.execute(
        text(
            """
            CREATE TRIGGER
                trg_normalize_planning_reservation
            BEFORE INSERT OR UPDATE OF
                resource_type,
                resource_key,
                sap_code
            ON planning_resource_reservations
            FOR EACH ROW
            EXECUTE FUNCTION
                public.trg_mpps_normalize_reservation()
            """
        )
    )

    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.trg_mpps_normalize_line()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
                NEW.line_name :=
                    public.mpps_clean_text(
                        NEW.line_name
                    );
                RETURN NEW;
            END;
            $$
            """
        )
    )

    for table_name in (
        "production_lines",
        "production_line_cavities",
    ):
        conn.execute(
            text(
                f"""
                DROP TRIGGER IF EXISTS
                    trg_normalize_line_name
                ON {_safe_identifier(table_name)}
                """
            )
        )
        conn.execute(
            text(
                f"""
                CREATE TRIGGER
                    trg_normalize_line_name
                BEFORE INSERT OR UPDATE OF
                    line_name
                ON {_safe_identifier(table_name)}
                FOR EACH ROW
                EXECUTE FUNCTION
                    public.trg_mpps_normalize_line()
                """
            )
        )

    conn.execute(
        text(
            r"""
            CREATE OR REPLACE FUNCTION
                public.trg_mpps_normalize_sap()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
                NEW.sap_code :=
                    public.mpps_canonical_sap(
                        NEW.sap_code
                    );
                RETURN NEW;
            END;
            $$
            """
        )
    )

    for table_name in (
        "mpps_shipment_items",
        "mpps_sap_stock_items",
    ):
        if not _table_exists(
            conn,
            table_name,
        ):
            continue

        conn.execute(
            text(
                f"""
                DROP TRIGGER IF EXISTS
                    trg_normalize_sap_code
                ON {_safe_identifier(table_name)}
                """
            )
        )
        conn.execute(
            text(
                f"""
                CREATE TRIGGER
                    trg_normalize_sap_code
                BEFORE INSERT OR UPDATE OF
                    sap_code
                ON {_safe_identifier(table_name)}
                FOR EACH ROW
                EXECUTE FUNCTION
                    public.trg_mpps_normalize_sap()
                """
            )
        )


def _install_indexes(
    conn,
) -> None:
    statements = (
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            ux_mold_master_normalized_key
        ON mold_master (
            public.mpps_identifier_key(
                mold_key_code
            )
        )
        WHERE public.mpps_clean_text(
                mold_key_code
              ) <> ''
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            ux_casing_master_normalized_type
        ON casing_master (
            public.mpps_identifier_key(
                casing_type
            )
        )
        WHERE public.mpps_clean_text(
                casing_type
              ) <> ''
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            ux_smds_normalized_sap
        ON smds (
            public.mpps_identifier_key(
                sap_code
            )
        )
        WHERE public.mpps_clean_text(
                sap_code
              ) <> ''
        """,
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
            ux_production_lines_normalized_name
        ON production_lines (
            public.mpps_line_key(
                line_name
            )
        )
        WHERE public.mpps_clean_text(
                line_name
              ) <> ''
        """,
        """
        CREATE INDEX IF NOT EXISTS
            ix_reservations_normalized_resource
        ON planning_resource_reservations (
            resource_type,
            public.mpps_identifier_key(
                resource_key
            ),
            reservation_date
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS
            ix_cavities_normalized_line
        ON production_line_cavities (
            public.mpps_line_key(
                line_name
            )
        )
        """,
    )

    for statement in statements:
        conn.execute(text(statement))


def _refresh_issue_table(
    conn,
) -> None:
    conn.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS
                mpps_master_data_issues (
                    id BIGSERIAL PRIMARY KEY,
                    issue_code VARCHAR(100)
                        NOT NULL,
                    severity VARCHAR(20)
                        NOT NULL,
                    entity_type VARCHAR(80)
                        NOT NULL,
                    entity_key TEXT
                        NOT NULL DEFAULT '',
                    affected_count INTEGER
                        NOT NULL DEFAULT 0,
                    details TEXT
                        NOT NULL DEFAULT '',
                    resolution_hint TEXT
                        NOT NULL DEFAULT '',
                    detected_at TIMESTAMP
                        NOT NULL DEFAULT
                        CURRENT_TIMESTAMP
                )
            """
        )
    )
    conn.execute(
        text(
            """
            TRUNCATE TABLE
                mpps_master_data_issues
            RESTART IDENTITY
            """
        )
    )

    conn.execute(
        text(
            """
            INSERT INTO mpps_master_data_issues (
                issue_code,
                severity,
                entity_type,
                entity_key,
                affected_count,
                details,
                resolution_hint
            )
            SELECT
                'INVALID_SMDS_MOLD_KEY',
                CASE
                    WHEN COUNT(*) FILTER (
                        WHERE LOWER(
                            COALESCE(
                                planning_manager_approval_status,
                                ''
                            )
                        ) = 'approved'
                    ) > 0
                    THEN 'CRITICAL'
                    ELSE 'HIGH'
                END,
                'SMDS Mold Key',
                public.mpps_canonical_mold_key(
                    key_code
                ),
                COUNT(*),
                (
                    'Invalid or placeholder mold key. '
                    || 'Approved rows: '
                    || COUNT(*) FILTER (
                        WHERE LOWER(
                            COALESCE(
                                planning_manager_approval_status,
                                ''
                            )
                        ) = 'approved'
                    )
                ),
                (
                    'Assign the correct physical Mold '
                    || 'Master key. Do not create a '
                    || 'mold from a placeholder.'
                )
            FROM smds
            WHERE public.mpps_canonical_mold_key(
                    key_code
                  ) = '-'
               OR public.mpps_canonical_mold_key(
                    key_code
                  ) ~ '^-[0-9]+$'
            GROUP BY
                public.mpps_canonical_mold_key(
                    key_code
                )
            """
        )
    )

    conn.execute(
        text(
            """
            INSERT INTO mpps_master_data_issues (
                issue_code,
                severity,
                entity_type,
                entity_key,
                affected_count,
                details,
                resolution_hint
            )
            SELECT
                'MISSING_MOLD_MASTER',
                CASE
                    WHEN COUNT(*) FILTER (
                        WHERE LOWER(
                            COALESCE(
                                s.planning_manager_approval_status,
                                ''
                            )
                        ) = 'approved'
                    ) > 0
                    THEN 'CRITICAL'
                    ELSE 'HIGH'
                END,
                'SMDS Mold Key',
                public.mpps_canonical_mold_key(
                    s.key_code
                ),
                COUNT(*),
                (
                    'No physical Mold Master record. '
                    || 'Approved rows: '
                    || COUNT(*) FILTER (
                        WHERE LOWER(
                            COALESCE(
                                s.planning_manager_approval_status,
                                ''
                            )
                        ) = 'approved'
                    )
                ),
                (
                    'Verify the actual factory mold '
                    || 'register. Add the mold only when '
                    || 'its physical count is confirmed, '
                    || 'or correct the SMDS key.'
                )
            FROM smds s
            WHERE public.mpps_canonical_mold_key(
                    s.key_code
                  ) <> '-'
              AND NOT EXISTS (
                    SELECT 1
                    FROM mold_master m
                    WHERE public.mpps_identifier_key(
                            m.mold_key_code
                          )
                        = public.mpps_identifier_key(
                            s.key_code
                          )
              )
            GROUP BY
                public.mpps_canonical_mold_key(
                    s.key_code
                )
            """
        )
    )

    conn.execute(
        text(
            """
            INSERT INTO mpps_master_data_issues (
                issue_code,
                severity,
                entity_type,
                entity_key,
                affected_count,
                details,
                resolution_hint
            )
            SELECT
                'MISSING_CASING_MASTER',
                CASE
                    WHEN COUNT(*) FILTER (
                        WHERE LOWER(
                            COALESCE(
                                s.planning_manager_approval_status,
                                ''
                            )
                        ) = 'approved'
                    ) > 0
                    THEN 'CRITICAL'
                    ELSE 'HIGH'
                END,
                'SMDS Casing Type',
                public.mpps_canonical_casing(
                    s.casing_type
                ),
                COUNT(*),
                (
                    'Casing type does not resolve to '
                    || 'Casing Master. Approved rows: '
                    || COUNT(*) FILTER (
                        WHERE LOWER(
                            COALESCE(
                                s.planning_manager_approval_status,
                                ''
                            )
                        ) = 'approved'
                    )
                ),
                (
                    'Correct the casing name or create '
                    || 'the confirmed physical casing '
                    || 'type and units.'
                )
            FROM smds s
            WHERE public.mpps_canonical_casing(
                    s.casing_type
                  ) NOT IN (
                    '-',
                    'No Casing'
                  )
              AND NOT EXISTS (
                    SELECT 1
                    FROM casing_master c
                    WHERE public.mpps_identifier_key(
                            c.casing_type
                          )
                        = public.mpps_identifier_key(
                            s.casing_type
                          )
              )
            GROUP BY
                public.mpps_canonical_casing(
                    s.casing_type
                )
            """
        )
    )

    conn.execute(
        text(
            """
            INSERT INTO mpps_master_data_issues (
                issue_code,
                severity,
                entity_type,
                entity_key,
                affected_count,
                details,
                resolution_hint
            )
            SELECT
                'APPROVED_SMDS_INVALID_LINE',
                'CRITICAL',
                'SMDS Production Line',
                COALESCE(
                    NULLIF(
                        public.mpps_clean_text(s.line),
                        ''
                    ),
                    '-'
                ),
                COUNT(*),
                (
                    'Approved SMDS rows have no matching '
                    || 'Production Line.'
                ),
                (
                    'Assign a valid compatible line '
                    || 'before production planning.'
                )
            FROM smds s
            WHERE LOWER(
                    COALESCE(
                        s.planning_manager_approval_status,
                        ''
                    )
                  ) = 'approved'
              AND (
                    public.mpps_clean_text(s.line)
                        IN ('', '-')
                    OR NOT EXISTS (
                        SELECT 1
                        FROM production_lines line
                        WHERE public.mpps_line_key(
                                line.line_name
                              )
                            = public.mpps_line_key(
                                s.line
                              )
                    )
                  )
            GROUP BY
                COALESCE(
                    NULLIF(
                        public.mpps_clean_text(s.line),
                        ''
                    ),
                    '-'
                )
            """
        )
    )

    conn.execute(
        text(
            """
            INSERT INTO mpps_master_data_issues (
                issue_code,
                severity,
                entity_type,
                entity_key,
                affected_count,
                details,
                resolution_hint
            )
            SELECT
                'APPROVED_SMDS_INVALID_TOTAL_PLAN',
                'CRITICAL',
                'SMDS SAP',
                s.sap_code,
                1,
                (
                    'Approved SMDS item has Total Plan '
                    || 'less than or equal to zero.'
                ),
                (
                    'Correct curing/handling and day/'
                    || 'night plan before approval.'
                )
            FROM smds s
            WHERE LOWER(
                    COALESCE(
                        s.planning_manager_approval_status,
                        ''
                    )
                  ) = 'approved'
              AND COALESCE(
                    s.total_plan,
                    0
                  ) <= 0
            """
        )
    )

    conn.execute(
        text(
            """
            INSERT INTO mpps_master_data_issues (
                issue_code,
                severity,
                entity_type,
                entity_key,
                affected_count,
                details,
                resolution_hint
            )
            SELECT
                'CASING_COUNTER_MISMATCH',
                'HIGH',
                'Casing Master',
                master.casing_type,
                1,
                (
                    'Stored total/free counters do not '
                    || 'match physical casing units.'
                ),
                (
                    'Recalculate counters from '
                    || 'casing_units.'
                )
            FROM casing_master master
            WHERE (
                public.mpps_identifier_key(
                    master.casing_type
                ) <> 'NO CASING'
                AND (
                    COALESCE(
                        master.total_casing_count,
                        0
                    ) <> (
                        SELECT COUNT(*)
                        FROM casing_units unit
                        WHERE public.mpps_identifier_key(
                                unit.casing_type
                              )
                            = public.mpps_identifier_key(
                                master.casing_type
                              )
                    )
                    OR COALESCE(
                        master.available_casing_count,
                        0
                    ) <> (
                        SELECT COUNT(*)
                        FROM casing_units unit
                        WHERE public.mpps_identifier_key(
                                unit.casing_type
                              )
                            = public.mpps_identifier_key(
                                master.casing_type
                              )
                          AND LOWER(
                                COALESCE(
                                    unit.condition_status,
                                    'Active'
                                )
                              ) = 'active'
                          AND LOWER(
                                COALESCE(
                                    unit.stock_status,
                                    'Free'
                                )
                              ) = 'free'
                    )
                )
            )
            OR (
                public.mpps_identifier_key(
                    master.casing_type
                ) = 'NO CASING'
                AND (
                    COALESCE(
                        master.total_casing_count,
                        0
                    ) <> 0
                    OR COALESCE(
                        master.available_casing_count,
                        0
                    ) <> 0
                )
            )
            """
        )
    )


def refresh_master_data_issues() -> None:
    """Refresh the persistent manager-review issue register."""
    with engine.begin() as conn:
        _refresh_issue_table(conn)


def _verify_integrity(
    conn,
) -> dict[str, int]:
    result = {
        "duplicate_mold_keys": int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT
                            public.mpps_identifier_key(
                                mold_key_code
                            )
                        FROM mold_master
                        GROUP BY
                            public.mpps_identifier_key(
                                mold_key_code
                            )
                        HAVING COUNT(*) > 1
                    ) duplicates
                    """
                )
            ).scalar_one()
            or 0
        ),
        "duplicate_casing_types": int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM (
                        SELECT
                            public.mpps_identifier_key(
                                casing_type
                            )
                        FROM casing_master
                        GROUP BY
                            public.mpps_identifier_key(
                                casing_type
                            )
                        HAVING COUNT(*) > 1
                    ) duplicates
                    """
                )
            ).scalar_one()
            or 0
        ),
        "unresolved_casing_types": int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM mpps_master_data_issues
                    WHERE issue_code =
                        'MISSING_CASING_MASTER'
                    """
                )
            ).scalar_one()
            or 0
        ),
        "unresolved_mold_keys": int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM mpps_master_data_issues
                    WHERE issue_code IN (
                        'MISSING_MOLD_MASTER',
                        'INVALID_SMDS_MOLD_KEY'
                    )
                    """
                )
            ).scalar_one()
            or 0
        ),
        "critical_issues": int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM mpps_master_data_issues
                    WHERE severity = 'CRITICAL'
                    """
                )
            ).scalar_one()
            or 0
        ),
        "high_issues": int(
            conn.execute(
                text(
                    """
                    SELECT COUNT(*)
                    FROM mpps_master_data_issues
                    WHERE severity = 'HIGH'
                    """
                )
            ).scalar_one()
            or 0
        ),
    }

    if (
        result["duplicate_mold_keys"] > 0
        or result["duplicate_casing_types"] > 0
        or result["unresolved_casing_types"] > 0
    ):
        raise RuntimeError(
            "Master-data normalization verification "
            f"failed: {result}"
        )

    return result


def main() -> None:
    stamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    inspector = inspect(engine)

    with engine.begin() as conn:
        conn.execute(
            text(
                "SET LOCAL lock_timeout = '10s'"
            )
        )
        conn.execute(
            text(
                "SET LOCAL statement_timeout = '180s'"
            )
        )
        conn.execute(
            text(
                "SET LOCAL search_path = public, pg_catalog"
            )
        )

        _install_normalization_functions(
            conn
        )
        _ensure_schema_columns(conn)
        _create_backups(conn, stamp)
        _precheck_normalized_uniqueness(
            conn
        )
        _merge_and_normalize_casing(
            conn
        )
        _merge_and_normalize_molds(
            conn
        )
        _normalize_lines_and_sap(conn)
        _install_triggers(conn)
        _install_indexes(conn)
        _refresh_issue_table(conn)
        result = _verify_integrity(conn)

    print(
        "MASTER DATA INTEGRITY MIGRATION PASSED"
    )
    print(
        "Deterministic spacing/case variants "
        "were normalized."
    )
    print(
        "Casing Master counters were rebuilt "
        "from physical units."
    )
    print(
        "Future imports and UI saves are "
        "protected by database triggers."
    )
    print(
        "Unresolved physical mold references "
        "were not invented."
    )
    print(result)


if __name__ == "__main__":
    main()
