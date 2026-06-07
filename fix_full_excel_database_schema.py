from __future__ import annotations

from sqlalchemy import text

from app.database import engine, init_database


def run_sql(statement: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(statement))


def main() -> None:
    print("Starting full Excel data foundation schema update...")

    init_database()

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS excel_workbooks (
            id SERIAL PRIMARY KEY,
            workbook_key VARCHAR(120) NOT NULL UNIQUE,
            original_file_name VARCHAR(260) NOT NULL,
            workbook_type VARCHAR(80),
            file_hash VARCHAR(128),
            imported_at TIMESTAMP,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            note TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS excel_sheets (
            id SERIAL PRIMARY KEY,
            workbook_id INTEGER NOT NULL REFERENCES excel_workbooks(id) ON DELETE CASCADE,
            sheet_name VARCHAR(160) NOT NULL,
            sheet_index INTEGER NOT NULL,
            max_row INTEGER NOT NULL DEFAULT 0,
            max_column INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_excel_sheet UNIQUE (workbook_id, sheet_name)
        );
        """
    )

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS excel_raw_rows (
            id SERIAL PRIMARY KEY,
            sheet_id INTEGER NOT NULL REFERENCES excel_sheets(id) ON DELETE CASCADE,
            row_number INTEGER NOT NULL,
            is_empty BOOLEAN NOT NULL DEFAULT FALSE,
            row_text TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_excel_raw_row UNIQUE (sheet_id, row_number)
        );
        """
    )

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS excel_raw_cells (
            id SERIAL PRIMARY KEY,
            sheet_id INTEGER NOT NULL REFERENCES excel_sheets(id) ON DELETE CASCADE,
            row_number INTEGER NOT NULL,
            column_number INTEGER NOT NULL,
            column_letter VARCHAR(20) NOT NULL,
            cell_address VARCHAR(30) NOT NULL,

            raw_value TEXT,
            display_value TEXT,
            data_type VARCHAR(40),
            number_value NUMERIC(20, 6),
            date_value TIMESTAMP,
            formula_value TEXT,
            is_formula BOOLEAN NOT NULL DEFAULT FALSE,

            mapped_table VARCHAR(120),
            mapped_field VARCHAR(120),
            mapping_status VARCHAR(60) NOT NULL DEFAULT 'RAW_ONLY',

            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT uq_excel_raw_cell UNIQUE (sheet_id, row_number, column_number)
        );
        """
    )

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS excel_import_runs (
            id SERIAL PRIMARY KEY,
            workbook_id INTEGER REFERENCES excel_workbooks(id),
            import_type VARCHAR(80) NOT NULL,
            status VARCHAR(60) NOT NULL DEFAULT 'STARTED',
            started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP,
            message TEXT,
            created_by INTEGER REFERENCES users(id)
        );
        """
    )

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS mpps_data_quality_issues (
            id SERIAL PRIMARY KEY,
            issue_level VARCHAR(30) NOT NULL DEFAULT 'WARNING',
            issue_area VARCHAR(120) NOT NULL,
            source_workbook VARCHAR(260),
            source_sheet VARCHAR(160),
            source_row INTEGER,
            source_column VARCHAR(20),
            material_code VARCHAR(80),
            issue_message TEXT NOT NULL,
            is_resolved BOOLEAN NOT NULL DEFAULT FALSE,
            resolved_note TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP
        );
        """
    )

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS mpps_oven_plan (
            id SERIAL PRIMARY KEY,
            plan_date DATE,
            oven_code VARCHAR(80),
            shift_name VARCHAR(80),
            material_code VARCHAR(80),
            item_description VARCHAR(260),
            planned_qty INTEGER NOT NULL DEFAULT 0,
            planned_weight_kg NUMERIC(18, 4) NOT NULL DEFAULT 0,
            plan_status VARCHAR(60) NOT NULL DEFAULT 'PLANNED',
            source_workbook VARCHAR(260),
            source_sheet VARCHAR(160),
            source_row INTEGER,
            source_note TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_mpps_oven_plan_qty_non_negative CHECK (planned_qty >= 0)
        );
        """
    )

    run_sql(
        """
        ALTER TABLE mpps_stock_items
        ADD COLUMN IF NOT EXISTS source_workbook VARCHAR(260),
        ADD COLUMN IF NOT EXISTS source_sheet VARCHAR(160),
        ADD COLUMN IF NOT EXISTS source_row INTEGER,
        ADD COLUMN IF NOT EXISTS source_note TEXT;
        """
    )

    run_sql(
        """
        ALTER TABLE mpps_shipment_demand
        ADD COLUMN IF NOT EXISTS source_workbook VARCHAR(260),
        ADD COLUMN IF NOT EXISTS source_sheet VARCHAR(160),
        ADD COLUMN IF NOT EXISTS source_row INTEGER,
        ADD COLUMN IF NOT EXISTS source_column VARCHAR(20),
        ADD COLUMN IF NOT EXISTS source_note TEXT;
        """
    )

    run_sql(
        """
        ALTER TABLE mpps_bom_items
        ADD COLUMN IF NOT EXISTS source_workbook VARCHAR(260),
        ADD COLUMN IF NOT EXISTS source_sheet VARCHAR(160),
        ADD COLUMN IF NOT EXISTS source_row INTEGER,
        ADD COLUMN IF NOT EXISTS source_note TEXT;
        """
    )

    run_sql(
        """
        ALTER TABLE mpps_compound_master
        ADD COLUMN IF NOT EXISTS source_workbook VARCHAR(260),
        ADD COLUMN IF NOT EXISTS source_sheet VARCHAR(160),
        ADD COLUMN IF NOT EXISTS source_row INTEGER,
        ADD COLUMN IF NOT EXISTS source_note TEXT;
        """
    )

    run_sql(
        """
        ALTER TABLE mpps_bead_master
        ADD COLUMN IF NOT EXISTS source_workbook VARCHAR(260),
        ADD COLUMN IF NOT EXISTS source_sheet VARCHAR(160),
        ADD COLUMN IF NOT EXISTS source_row INTEGER,
        ADD COLUMN IF NOT EXISTS source_note TEXT;
        """
    )

    run_sql(
        """
        ALTER TABLE mpps_band_master
        ADD COLUMN IF NOT EXISTS source_workbook VARCHAR(260),
        ADD COLUMN IF NOT EXISTS source_sheet VARCHAR(160),
        ADD COLUMN IF NOT EXISTS source_row INTEGER,
        ADD COLUMN IF NOT EXISTS source_note TEXT;
        """
    )

    run_sql(
        """
        ALTER TABLE mpps_capacity_master
        ADD COLUMN IF NOT EXISTS source_workbook VARCHAR(260),
        ADD COLUMN IF NOT EXISTS source_sheet VARCHAR(160),
        ADD COLUMN IF NOT EXISTS source_row INTEGER,
        ADD COLUMN IF NOT EXISTS source_note TEXT;
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_excel_workbooks_key
        ON excel_workbooks(workbook_key);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_excel_sheets_workbook
        ON excel_sheets(workbook_id);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_excel_raw_cells_sheet_row_col
        ON excel_raw_cells(sheet_id, row_number, column_number);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_excel_raw_cells_mapping
        ON excel_raw_cells(mapped_table, mapped_field);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_mpps_oven_plan_material
        ON mpps_oven_plan(material_code);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_mpps_oven_plan_date
        ON mpps_oven_plan(plan_date);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_mpps_quality_issues_area
        ON mpps_data_quality_issues(issue_area, issue_level);
        """
    )

    print("Full Excel data foundation schema update completed successfully.")
    print("")
    print("Raw Excel preservation tables:")
    print("- excel_workbooks")
    print("- excel_sheets")
    print("- excel_raw_rows")
    print("- excel_raw_cells")
    print("- excel_import_runs")
    print("")
    print("Clean factory planning support tables:")
    print("- mpps_data_quality_issues")
    print("- mpps_oven_plan")
    print("")
    print("Existing app tables were not dropped.")
    print("Existing users and roles were not changed.")


if __name__ == '__main__':
    main()