from __future__ import annotations

from sqlalchemy import text

from app.database import engine


SMDS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS smds (
    id BIGSERIAL PRIMARY KEY,
    sap_code VARCHAR(128) NOT NULL UNIQUE,
    material_description TEXT NOT NULL DEFAULT '',
    line TEXT,
    heel TEXT,
    soft TEXT,
    tred TEXT,
    remark TEXT,
    weight_per_tyre_kg NUMERIC(14, 3),
    line_400 TEXT,
    line_800 TEXT,
    press_line TEXT,
    nancy_press TEXT,
    press_400_t TEXT,
    t_600_01_press TEXT,
    t_600_02_press TEXT,
    l_press_1250 TEXT,
    l_press_1500 TEXT,
    l_press_1800 TEXT,
    oring_press TEXT,
    new_press TEXT,
    key_code TEXT,
    casing_type TEXT,
    curing_cycle TEXT,
    handling_time NUMERIC(14, 2),
    day_plan NUMERIC(14, 3),
    night_plan NUMERIC(14, 3),
    total_plan NUMERIC(14, 3),
    planning_manager_approval_status TEXT NOT NULL DEFAULT 'Pending',
    manager_approval_updated_at TIMESTAMP,
    source_file TEXT,
    source_sheet TEXT NOT NULL DEFAULT 'ALL',
    source_row_number INTEGER,
    imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

SMDS_ALTER_SQL = [
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS sap_code VARCHAR(128) NOT NULL DEFAULT ''",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS material_description TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS line TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS heel TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS soft TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS tred TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS remark TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS weight_per_tyre_kg NUMERIC(14, 3)",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS line_400 TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS line_800 TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS press_line TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS nancy_press TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS press_400_t TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS t_600_01_press TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS t_600_02_press TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS l_press_1250 TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS l_press_1500 TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS l_press_1800 TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS oring_press TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS new_press TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS key_code TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS casing_type TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS curing_cycle TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS handling_time NUMERIC(14, 2)",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS day_plan NUMERIC(14, 3)",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS night_plan NUMERIC(14, 3)",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS total_plan NUMERIC(14, 3)",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS planning_manager_approval_status TEXT NOT NULL DEFAULT 'Pending'",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS manager_approval_updated_at TIMESTAMP",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS source_file TEXT",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS source_sheet TEXT NOT NULL DEFAULT 'ALL'",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS source_row_number INTEGER",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "ALTER TABLE smds ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
]

SMDS_INDEX_SQL = [
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_smds_sap_code ON smds (sap_code)",
    "CREATE INDEX IF NOT EXISTS ix_smds_key_code ON smds (key_code)",
    "CREATE INDEX IF NOT EXISTS ix_smds_casing_type ON smds (casing_type)",
    "CREATE INDEX IF NOT EXISTS ix_smds_manager_approval ON smds (planning_manager_approval_status)",
    "CREATE INDEX IF NOT EXISTS ix_smds_material_description ON smds USING gin (to_tsvector('simple', material_description))",
]

EXCEL_FOUNDATION_SQL = [
    """
    CREATE TABLE IF NOT EXISTS excel_workbooks (
        id BIGSERIAL PRIMARY KEY,
        workbook_key TEXT NOT NULL UNIQUE,
        original_file_name TEXT NOT NULL,
        file_path TEXT,
        file_hash TEXT,
        imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        imported_by TEXT,
        remarks TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS excel_sheets (
        id BIGSERIAL PRIMARY KEY,
        workbook_id BIGINT REFERENCES excel_workbooks(id) ON DELETE CASCADE,
        sheet_name TEXT NOT NULL,
        sheet_index INTEGER NOT NULL DEFAULT 0,
        max_row INTEGER,
        max_column INTEGER,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(workbook_id, sheet_name)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS excel_raw_cells (
        id BIGSERIAL PRIMARY KEY,
        sheet_id BIGINT REFERENCES excel_sheets(id) ON DELETE CASCADE,
        row_number INTEGER NOT NULL,
        column_number INTEGER NOT NULL,
        column_letter TEXT NOT NULL,
        cell_address TEXT NOT NULL,
        raw_value TEXT,
        display_value TEXT,
        formula_value TEXT,
        is_formula BOOLEAN NOT NULL DEFAULT FALSE,
        data_type TEXT,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(sheet_id, row_number, column_number)
    )
    """,
]

EXCEL_FOUNDATION_ALTER_SQL = [
    "ALTER TABLE excel_workbooks ADD COLUMN IF NOT EXISTS workbook_key TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE excel_workbooks ADD COLUMN IF NOT EXISTS original_file_name TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE excel_workbooks ADD COLUMN IF NOT EXISTS file_path TEXT",
    "ALTER TABLE excel_workbooks ADD COLUMN IF NOT EXISTS file_hash TEXT",
    "ALTER TABLE excel_workbooks ADD COLUMN IF NOT EXISTS imported_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "ALTER TABLE excel_workbooks ADD COLUMN IF NOT EXISTS imported_by TEXT",
    "ALTER TABLE excel_workbooks ADD COLUMN IF NOT EXISTS remarks TEXT",
    "ALTER TABLE excel_sheets ADD COLUMN IF NOT EXISTS workbook_id BIGINT",
    "ALTER TABLE excel_sheets ADD COLUMN IF NOT EXISTS sheet_name TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE excel_sheets ADD COLUMN IF NOT EXISTS sheet_index INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE excel_sheets ADD COLUMN IF NOT EXISTS max_row INTEGER",
    "ALTER TABLE excel_sheets ADD COLUMN IF NOT EXISTS max_column INTEGER",
    "ALTER TABLE excel_sheets ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
    "ALTER TABLE excel_raw_cells ADD COLUMN IF NOT EXISTS sheet_id BIGINT",
    "ALTER TABLE excel_raw_cells ADD COLUMN IF NOT EXISTS row_number INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE excel_raw_cells ADD COLUMN IF NOT EXISTS column_number INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE excel_raw_cells ADD COLUMN IF NOT EXISTS column_letter TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE excel_raw_cells ADD COLUMN IF NOT EXISTS cell_address TEXT NOT NULL DEFAULT ''",
    "ALTER TABLE excel_raw_cells ADD COLUMN IF NOT EXISTS raw_value TEXT",
    "ALTER TABLE excel_raw_cells ADD COLUMN IF NOT EXISTS display_value TEXT",
    "ALTER TABLE excel_raw_cells ADD COLUMN IF NOT EXISTS formula_value TEXT",
    "ALTER TABLE excel_raw_cells ADD COLUMN IF NOT EXISTS is_formula BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE excel_raw_cells ADD COLUMN IF NOT EXISTS data_type TEXT",
    "ALTER TABLE excel_raw_cells ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
]

EXCEL_FOUNDATION_INDEX_SQL = [
    "CREATE INDEX IF NOT EXISTS ix_excel_sheets_workbook_id ON excel_sheets (workbook_id)",
    "CREATE INDEX IF NOT EXISTS ix_excel_raw_cells_sheet_row_col ON excel_raw_cells (sheet_id, row_number, column_number)",
    "CREATE INDEX IF NOT EXISTS ix_excel_raw_cells_cell_address ON excel_raw_cells (cell_address)",
]


def ensure_smds_table() -> None:
    """Create or upgrade the central SMDS table used by planning modules."""
    with engine.begin() as conn:
        conn.execute(text(SMDS_TABLE_SQL))

        for statement in SMDS_ALTER_SQL:
            conn.execute(text(statement))

        conn.execute(
            text(
                """
                ALTER TABLE smds
                ALTER COLUMN planning_manager_approval_status
                SET DEFAULT 'Pending'
                """
            )
        )

        conn.execute(
            text(
                """
                UPDATE smds
                SET planning_manager_approval_status = 'Pending'
                WHERE planning_manager_approval_status IS NULL
                   OR BTRIM(planning_manager_approval_status) = ''
                """
            )
        )

        conn.execute(
            text(
                """
                ALTER TABLE smds
                ALTER COLUMN planning_manager_approval_status
                SET NOT NULL
                """
            )
        )

        for statement in SMDS_INDEX_SQL:
            conn.execute(text(statement))


def ensure_excel_foundation_tables() -> None:
    """Create legacy raw Excel viewer tables for older databases."""
    with engine.begin() as conn:
        for statement in EXCEL_FOUNDATION_SQL:
            conn.execute(text(statement))

        for statement in EXCEL_FOUNDATION_ALTER_SQL:
            conn.execute(text(statement))

        for statement in EXCEL_FOUNDATION_INDEX_SQL:
            conn.execute(text(statement))


def ensure_smds_and_legacy_tables() -> None:
    ensure_excel_foundation_tables()
    ensure_smds_table()

# MPPS V32 SCHEMA ENSURE ONCE
import threading as _v32_schema_threading

_v32_original_ensure_smds_table = ensure_smds_table
_v32_schema_lock = _v32_schema_threading.Lock()
_v32_schema_ready = False


def ensure_smds_table() -> None:
    """Run schema migration at most once per application process.

    Normal page reads must not execute 30+ ALTER/INDEX statements repeatedly.
    """
    global _v32_schema_ready

    if _v32_schema_ready:
        return

    with _v32_schema_lock:
        if _v32_schema_ready:
            return

        _v32_original_ensure_smds_table()
        _v32_schema_ready = True
