from __future__ import annotations

from datetime import date
from sqlalchemy import text

from app.database import engine, init_database


MPPS_WORKBOOK_KEY = "MPPS_MAY_2026"
OVEN_WORKBOOK_KEY = "OVEN_PLAN_JUNE_2026"


def run_sql(statement: str, params: dict | None = None) -> None:
    with engine.begin() as connection:
        connection.execute(text(statement), params or {})


def fetch_one(statement: str, params: dict | None = None):
    with engine.begin() as connection:
        return connection.execute(text(statement), params or {}).mappings().first()


def fetch_scalar(statement: str, params: dict | None = None):
    with engine.begin() as connection:
        return connection.execute(text(statement), params or {}).scalar()


def get_sheet_id(workbook_key: str, sheet_name: str) -> int:
    row = fetch_one(
        """
        SELECT es.id
        FROM excel_sheets es
        JOIN excel_workbooks ew
            ON ew.id = es.workbook_id
        WHERE ew.workbook_key = :workbook_key
          AND es.sheet_name = :sheet_name
        LIMIT 1;
        """,
        {
            "workbook_key": workbook_key,
            "sheet_name": sheet_name,
        },
    )

    if row is None:
        raise ValueError(f"Sheet not found: {workbook_key} / {sheet_name}")

    return int(row["id"])


def get_date_cell(sheet_id: int, cell_address: str):
    return fetch_scalar(
        """
        SELECT date_value
        FROM excel_raw_cells
        WHERE sheet_id = :sheet_id
          AND cell_address = :cell_address
        LIMIT 1;
        """,
        {
            "sheet_id": sheet_id,
            "cell_address": cell_address,
        },
    )


def count_table(table_name: str) -> int:
    return int(fetch_scalar(f"SELECT COUNT(*) FROM {table_name};") or 0)


def clean_target_tables() -> None:
    print("Cleaning clean MPPS target tables...")

    run_sql(
        """
        TRUNCATE TABLE
            mpps_data_quality_issues,
            mpps_oven_plan,
            mpps_shipment_demand,
            mpps_bom_items,
            mpps_compound_master,
            mpps_bead_master,
            mpps_band_master,
            mpps_capacity_master,
            mpps_stock_items,
            tire_stock_movements,
            oven_schedule,
            order_item_priority_log,
            order_status_history,
            schedule_change_log,
            order_items,
            orders,
            tire_types,
            ovens,
            shifts,
            production_rules
        RESTART IDENTITY CASCADE;
        """
    )


def seed_shift_and_rules() -> None:
    print("Creating base shifts and production rules...")

    run_sql(
        """
        INSERT INTO shifts (
            shift_name,
            start_time,
            end_time,
            max_working_minutes,
            is_active
        )
        VALUES
            ('Day Shift', '07:00:00', '19:00:00', 720, TRUE),
            ('Night Shift', '19:00:00', '07:00:00', 720, TRUE)
        ON CONFLICT (shift_name)
        DO UPDATE SET
            start_time = EXCLUDED.start_time,
            end_time = EXCLUDED.end_time,
            max_working_minutes = EXCLUDED.max_working_minutes,
            is_active = TRUE;
        """
    )

    run_sql(
        """
        INSERT INTO production_rules (
            rule_name,
            rule_value,
            unit
        )
        VALUES (
            'BREAK_BETWEEN_TIRES',
            20,
            'minutes'
        )
        ON CONFLICT (rule_name)
        DO UPDATE SET
            rule_value = EXCLUDED.rule_value,
            unit = EXCLUDED.unit;
        """
    )


def map_stock_sheet() -> None:
    print("Mapping MPPS Stock sheet...")

    stock_sheet_id = get_sheet_id(MPPS_WORKBOOK_KEY, "Stock")

    run_sql(
        """
        WITH stock_rows AS (
            SELECT
                row_number,

                NULLIF(TRIM(MAX(CASE WHEN column_number = 1 THEN COALESCE(display_value, raw_value) END)), '') AS material_code,
                NULLIF(TRIM(MAX(CASE WHEN column_number = 2 THEN COALESCE(display_value, raw_value) END)), '') AS item_description,

                ROUND(COALESCE(MAX(CASE WHEN column_number = 3 THEN number_value END), 0))::INTEGER AS fg_stock,
                ROUND(COALESCE(MAX(CASE WHEN column_number = 4 THEN number_value END), 0))::INTEGER AS qc_stock,
                ROUND(COALESCE(MAX(CASE WHEN column_number = 5 THEN number_value END), 0))::INTEGER AS scrap_stock,
                ROUND(COALESCE(MAX(CASE WHEN column_number = 6 THEN number_value END), 0))::INTEGER AS blocked_stock,

                ROUND(COALESCE(MAX(CASE WHEN column_number = 204 THEN number_value END), 0))::INTEGER AS shipment_demand,
                ROUND(COALESCE(MAX(CASE WHEN column_number = 205 THEN number_value END), 0))::INTEGER AS need_to_be_produced,

                MAX(CASE WHEN column_number = 211 THEN number_value END) AS average_weight,
                NULLIF(TRIM(MAX(CASE WHEN column_number = 212 THEN COALESCE(display_value, raw_value) END)), '') AS product_group,
                MAX(CASE WHEN column_number = 219 THEN number_value END) AS compound_weight,
                NULLIF(TRIM(MAX(CASE WHEN column_number = 221 THEN COALESCE(display_value, raw_value) END)), '') AS band_type,
                NULLIF(TRIM(MAX(CASE WHEN column_number = 222 THEN COALESCE(display_value, raw_value) END)), '') AS bead_type
            FROM excel_raw_cells
            WHERE sheet_id = :sheet_id
              AND row_number >= 4
            GROUP BY row_number
        ),
        valid_rows AS (
            SELECT *
            FROM stock_rows
            WHERE material_code IS NOT NULL
              AND item_description IS NOT NULL
              AND material_code !~* 'total|shipment|dummy'
        )
        INSERT INTO tire_types (
            tire_code,
            tire_name,
            curing_minutes,
            is_active
        )
        SELECT
            material_code,
            item_description,
            30,
            TRUE
        FROM (
            SELECT DISTINCT ON (material_code)
                *
            FROM valid_rows
            ORDER BY material_code, row_number
        ) valid_rows
        ON CONFLICT (tire_code)
        DO UPDATE SET
            tire_name = EXCLUDED.tire_name,
            is_active = TRUE;
        """,
        {"sheet_id": stock_sheet_id},
    )

    run_sql(
        """
        WITH stock_rows AS (
            SELECT
                row_number,

                NULLIF(TRIM(MAX(CASE WHEN column_number = 1 THEN COALESCE(display_value, raw_value) END)), '') AS material_code,
                NULLIF(TRIM(MAX(CASE WHEN column_number = 2 THEN COALESCE(display_value, raw_value) END)), '') AS item_description,

                ROUND(COALESCE(MAX(CASE WHEN column_number = 3 THEN number_value END), 0))::INTEGER AS fg_stock,
                ROUND(COALESCE(MAX(CASE WHEN column_number = 4 THEN number_value END), 0))::INTEGER AS qc_stock,
                ROUND(COALESCE(MAX(CASE WHEN column_number = 5 THEN number_value END), 0))::INTEGER AS scrap_stock,
                ROUND(COALESCE(MAX(CASE WHEN column_number = 6 THEN number_value END), 0))::INTEGER AS blocked_stock,

                ROUND(COALESCE(MAX(CASE WHEN column_number = 204 THEN number_value END), 0))::INTEGER AS shipment_demand,
                ROUND(COALESCE(MAX(CASE WHEN column_number = 205 THEN number_value END), 0))::INTEGER AS need_to_be_produced,

                MAX(CASE WHEN column_number = 211 THEN number_value END) AS average_weight,
                NULLIF(TRIM(MAX(CASE WHEN column_number = 212 THEN COALESCE(display_value, raw_value) END)), '') AS product_group,
                MAX(CASE WHEN column_number = 219 THEN number_value END) AS compound_weight,
                NULLIF(TRIM(MAX(CASE WHEN column_number = 221 THEN COALESCE(display_value, raw_value) END)), '') AS band_type,
                NULLIF(TRIM(MAX(CASE WHEN column_number = 222 THEN COALESCE(display_value, raw_value) END)), '') AS bead_type
            FROM excel_raw_cells
            WHERE sheet_id = :sheet_id
              AND row_number >= 4
            GROUP BY row_number
        ),
        valid_rows AS (
            SELECT *
            FROM stock_rows
            WHERE material_code IS NOT NULL
              AND item_description IS NOT NULL
              AND material_code !~* 'total|shipment|dummy'
        )
        INSERT INTO mpps_stock_items (
            material_code,
            item_description,
            tire_type_id,
            product_type,
            size,
            product_group,
            fg_stock,
            qc_stock,
            scrap_stock,
            blocked_stock,
            average_weight,
            compound_weight,
            bead_type,
            band_type,
            is_active,
            last_updated_date,
            source_workbook,
            source_sheet,
            source_row,
            source_note
        )
        SELECT
            vr.material_code,
            vr.item_description,
            tt.id,
            'TYRE',
            NULL,
            vr.product_group,
            GREATEST(vr.fg_stock, 0),
            GREATEST(vr.qc_stock, 0),
            GREATEST(vr.scrap_stock, 0),
            GREATEST(vr.blocked_stock, 0),
            CASE
                WHEN vr.average_weight IS NOT NULL AND vr.average_weight >= 0
                    THEN vr.average_weight
                ELSE NULL
            END AS average_weight,
            CASE
                WHEN vr.compound_weight IS NOT NULL AND vr.compound_weight >= 0
                    THEN vr.compound_weight
                ELSE NULL
            END AS compound_weight,
            vr.bead_type,
            vr.band_type,
            TRUE,
            CURRENT_DATE,
            'MPPS Ver-04  MAY 2026.xlsx',
            'Stock',
            vr.row_number,
            'Mapped from MPPS Stock sheet.'
        FROM (
            SELECT DISTINCT ON (material_code)
                *
            FROM valid_rows
            ORDER BY material_code, row_number
        ) vr
        LEFT JOIN tire_types tt
            ON tt.tire_code = vr.material_code
        ON CONFLICT (material_code)
        DO UPDATE SET
            item_description = EXCLUDED.item_description,
            tire_type_id = EXCLUDED.tire_type_id,
            product_type = EXCLUDED.product_type,
            product_group = EXCLUDED.product_group,
            fg_stock = EXCLUDED.fg_stock,
            qc_stock = EXCLUDED.qc_stock,
            scrap_stock = EXCLUDED.scrap_stock,
            blocked_stock = EXCLUDED.blocked_stock,
            average_weight = EXCLUDED.average_weight,
            compound_weight = EXCLUDED.compound_weight,
            bead_type = EXCLUDED.bead_type,
            band_type = EXCLUDED.band_type,
            is_active = TRUE,
            last_updated_date = CURRENT_DATE,
            source_workbook = EXCLUDED.source_workbook,
            source_sheet = EXCLUDED.source_sheet,
            source_row = EXCLUDED.source_row,
            source_note = EXCLUDED.source_note,
            updated_at = CURRENT_TIMESTAMP;
        """,
        {"sheet_id": stock_sheet_id},
    )

    run_sql(
        """
        WITH stock_rows AS (
            SELECT
                row_number,
                NULLIF(TRIM(MAX(CASE WHEN column_number = 1 THEN COALESCE(display_value, raw_value) END)), '') AS material_code,
                ROUND(COALESCE(MAX(CASE WHEN column_number = 204 THEN number_value END), 0))::INTEGER AS shipment_demand
            FROM excel_raw_cells
            WHERE sheet_id = :sheet_id
              AND row_number >= 4
            GROUP BY row_number
        )
        INSERT INTO mpps_shipment_demand (
            material_code,
            customer_name,
            demand_qty,
            shipment_date,
            status,
            note,
            source_workbook,
            source_sheet,
            source_row,
            source_column,
            source_note
        )
        SELECT
            material_code,
            'EXCEL_TOTAL_TO_BE_SHIPPED',
            shipment_demand,
            NULL,
            'CONFIRMED',
            'Demand mapped from MPPS Stock column: Total to be shipped.',
            'MPPS Ver-04  MAY 2026.xlsx',
            'Stock',
            row_number,
            'GR',
            'Column 204: Total to be shipped.'
        FROM stock_rows
        WHERE material_code IS NOT NULL
          AND shipment_demand > 0;
        """,
        {"sheet_id": stock_sheet_id},
    )


def map_bom_sheet() -> None:
    print("Mapping MPPS BOM sheet...")

    bom_sheet_id = get_sheet_id(MPPS_WORKBOOK_KEY, "BOM")

    run_sql(
        """
        INSERT INTO mpps_bom_items (
            finished_item_code,
            raw_material_code,
            raw_material_name,
            usage_per_unit,
            unit,
            wastage_percentage,
            is_active,
            source_workbook,
            source_sheet,
            source_row,
            source_note
        )
        SELECT
            NULLIF(TRIM(material_cell.display_value), '') AS finished_item_code,
            LEFT(TRIM(header_cell.display_value), 80) AS raw_material_code,
            TRIM(header_cell.display_value) AS raw_material_name,
            data_cell.number_value AS usage_per_unit,
            'KG',
            0,
            TRUE,
            'MPPS Ver-04  MAY 2026.xlsx',
            'BOM',
            data_cell.row_number,
            'Mapped from wide BOM compound/material columns.'
        FROM excel_raw_cells data_cell
        JOIN excel_raw_cells material_cell
            ON material_cell.sheet_id = data_cell.sheet_id
           AND material_cell.row_number = data_cell.row_number
           AND material_cell.column_number = 3
        JOIN excel_raw_cells header_cell
            ON header_cell.sheet_id = data_cell.sheet_id
           AND header_cell.row_number = 1
           AND header_cell.column_number = data_cell.column_number
        WHERE data_cell.sheet_id = :sheet_id
          AND data_cell.row_number >= 2
          AND data_cell.column_number >= 9
          AND data_cell.number_value IS NOT NULL
          AND data_cell.number_value > 0
          AND material_cell.display_value IS NOT NULL
          AND header_cell.display_value IS NOT NULL;
        """,
        {"sheet_id": bom_sheet_id},
    )


def map_compound_sheet() -> None:
    print("Mapping MPPS compound sheet...")

    compound_sheet_id = get_sheet_id(MPPS_WORKBOOK_KEY, "compound ")

    run_sql(
        """
        INSERT INTO mpps_compound_master (
            item_code,
            compound_code,
            compound_name,
            compound_weight_per_unit,
            stage,
            is_active,
            source_workbook,
            source_sheet,
            source_row,
            source_note
        )
        SELECT
            NULLIF(TRIM(material_cell.display_value), '') AS item_code,
            LEFT(TRIM(header_cell.display_value), 80) AS compound_code,
            TRIM(header_cell.display_value) AS compound_name,
            data_cell.number_value AS compound_weight_per_unit,
            CASE
                WHEN LOWER(header_cell.display_value) LIKE '%2nd%' THEN '2ND_STAGE'
                WHEN LOWER(header_cell.display_value) LIKE '%1st%' THEN '1ST_STAGE'
                WHEN LOWER(header_cell.display_value) LIKE '%rework%' THEN 'REWORK'
                WHEN LOWER(header_cell.display_value) LIKE '%recycle%' THEN 'RECYCLE'
                ELSE 'MAIN'
            END AS stage,
            TRUE,
            'MPPS Ver-04  MAY 2026.xlsx',
            'compound ',
            data_cell.row_number,
            'Mapped from MPPS compound matrix.'
        FROM excel_raw_cells data_cell
        JOIN excel_raw_cells material_cell
            ON material_cell.sheet_id = data_cell.sheet_id
           AND material_cell.row_number = data_cell.row_number
           AND material_cell.column_number = 1
        JOIN excel_raw_cells header_cell
            ON header_cell.sheet_id = data_cell.sheet_id
           AND header_cell.row_number = 3
           AND header_cell.column_number = data_cell.column_number
        WHERE data_cell.sheet_id = :sheet_id
          AND data_cell.row_number >= 4
          AND data_cell.column_number >= 5
          AND data_cell.number_value IS NOT NULL
          AND data_cell.number_value > 0
          AND material_cell.display_value IS NOT NULL
          AND header_cell.display_value IS NOT NULL;
        """,
        {"sheet_id": compound_sheet_id},
    )


def map_bead_sheet() -> None:
    print("Mapping MPPS Total Bead sheet...")

    bead_sheet_id = get_sheet_id(MPPS_WORKBOOK_KEY, "Total Bead")

    run_sql(
        """
        INSERT INTO mpps_bead_master (
            item_code,
            bead_type,
            bead_per_tyre,
            is_active,
            source_workbook,
            source_sheet,
            source_row,
            source_note
        )
        SELECT
            NULLIF(TRIM(size_cell.display_value), '') AS item_code,
            COALESCE(NULLIF(TRIM(bead_type_cell.display_value), ''), 'UNKNOWN') AS bead_type,
            bead_per_cell.number_value AS bead_per_tyre,
            TRUE,
            'MPPS Ver-04  MAY 2026.xlsx',
            'Total Bead',
            size_cell.row_number,
            'Mapped from Total Bead sheet. item_code is tyre size.'
        FROM excel_raw_cells size_cell
        JOIN excel_raw_cells bead_per_cell
            ON bead_per_cell.sheet_id = size_cell.sheet_id
           AND bead_per_cell.row_number = size_cell.row_number
           AND bead_per_cell.column_number = 2
        LEFT JOIN excel_raw_cells bead_type_cell
            ON bead_type_cell.sheet_id = size_cell.sheet_id
           AND bead_type_cell.row_number = size_cell.row_number
           AND bead_type_cell.column_number = 5
        WHERE size_cell.sheet_id = :sheet_id
          AND size_cell.row_number >= 5
          AND size_cell.column_number = 1
          AND size_cell.display_value IS NOT NULL
          AND bead_per_cell.number_value IS NOT NULL
          AND bead_per_cell.number_value > 0;
        """,
        {"sheet_id": bead_sheet_id},
    )


def map_band_sheet() -> None:
    print("Mapping MPPS TOTAL BAND sheet...")

    band_sheet_id = get_sheet_id(MPPS_WORKBOOK_KEY, "TOTAL BAND")

    run_sql(
        """
        INSERT INTO mpps_band_master (
            item_code,
            band_code,
            band_type,
            band_usage_per_tyre,
            is_active,
            source_workbook,
            source_sheet,
            source_row,
            source_note
        )
        SELECT
            NULLIF(TRIM(size_cell.display_value), '') AS item_code,
            COALESCE(NULLIF(TRIM(band_code_cell.display_value), ''), '-') AS band_code,
            NULLIF(TRIM(size_cell.display_value), '') AS band_type,
            1,
            TRUE,
            'MPPS Ver-04  MAY 2026.xlsx',
            'TOTAL BAND',
            size_cell.row_number,
            'Mapped from TOTAL BAND sheet. Usage per tyre was not explicit, defaulted to 1. Raw Excel is preserved for audit.'
        FROM excel_raw_cells size_cell
        LEFT JOIN excel_raw_cells band_code_cell
            ON band_code_cell.sheet_id = size_cell.sheet_id
           AND band_code_cell.row_number = size_cell.row_number
           AND band_code_cell.column_number = 4
        WHERE size_cell.sheet_id = :sheet_id
          AND size_cell.row_number >= 4
          AND size_cell.column_number = 1
          AND size_cell.display_value IS NOT NULL
          AND TRIM(size_cell.display_value) <> '';
        """,
        {"sheet_id": band_sheet_id},
    )


def map_capacity_sheet() -> None:
    print("Mapping MPPS Capacity sheet...")

    capacity_sheet_id = get_sheet_id(MPPS_WORKBOOK_KEY, "Capacity")

    run_sql(
        """
        INSERT INTO mpps_capacity_master (
            item_code,
            running_moulds,
            per_mould_capacity,
            available_capacity_per_day,
            target_date,
            is_active,
            source_workbook,
            source_sheet,
            source_row,
            source_note
        )
        SELECT DISTINCT ON (NULLIF(TRIM(key_cell.display_value), ''))
            NULLIF(TRIM(key_cell.display_value), '') AS item_code,
            COALESCE(running_moulds_cell.number_value, 0) AS running_moulds,
            COALESCE(per_mould_capacity_cell.number_value, 0) AS per_mould_capacity,
            CASE
                WHEN daily_capacity_cell.number_value IS NOT NULL
                     AND daily_capacity_cell.number_value > 0
                    THEN daily_capacity_cell.number_value
                ELSE COALESCE(running_moulds_cell.number_value, 0)
                     * COALESCE(per_mould_capacity_cell.number_value, 0)
            END AS available_capacity_per_day,
            NULL,
            TRUE,
            'MPPS Ver-04  MAY 2026.xlsx',
            'Capacity',
            key_cell.row_number,
            'Mapped from Capacity sheet. item_code is KEY 2 / size group.'
        FROM excel_raw_cells key_cell
        LEFT JOIN excel_raw_cells running_moulds_cell
            ON running_moulds_cell.sheet_id = key_cell.sheet_id
           AND running_moulds_cell.row_number = key_cell.row_number
           AND running_moulds_cell.column_number = 18
        LEFT JOIN excel_raw_cells per_mould_capacity_cell
            ON per_mould_capacity_cell.sheet_id = key_cell.sheet_id
           AND per_mould_capacity_cell.row_number = key_cell.row_number
           AND per_mould_capacity_cell.column_number = 19
        LEFT JOIN excel_raw_cells daily_capacity_cell
            ON daily_capacity_cell.sheet_id = key_cell.sheet_id
           AND daily_capacity_cell.row_number = key_cell.row_number
           AND daily_capacity_cell.column_number = 20
        WHERE key_cell.sheet_id = :sheet_id
          AND key_cell.row_number >= 3
          AND key_cell.column_number = 1
          AND key_cell.display_value IS NOT NULL
          AND TRIM(key_cell.display_value) <> ''
        ON CONFLICT (item_code)
        DO UPDATE SET
            running_moulds = EXCLUDED.running_moulds,
            per_mould_capacity = EXCLUDED.per_mould_capacity,
            available_capacity_per_day = EXCLUDED.available_capacity_per_day,
            target_date = EXCLUDED.target_date,
            is_active = TRUE,
            source_workbook = EXCLUDED.source_workbook,
            source_sheet = EXCLUDED.source_sheet,
            source_row = EXCLUDED.source_row,
            source_note = EXCLUDED.source_note,
            updated_at = CURRENT_TIMESTAMP;
        """,
        {"sheet_id": capacity_sheet_id},
    )


def map_oven_master_and_plan() -> None:
    print("Mapping OVEN sheet to oven master and oven plan...")

    oven_sheet_id = get_sheet_id(OVEN_WORKBOOK_KEY, "OVEN")

    try:
        daily_plan_sheet_id = get_sheet_id(OVEN_WORKBOOK_KEY, "Daily  Plan")
        plan_date = get_date_cell(daily_plan_sheet_id, "C3")
    except Exception:
        plan_date = None

    if plan_date is None:
        plan_date = date(2026, 6, 1)

    run_sql(
        """
        INSERT INTO ovens (
            oven_code,
            oven_name,
            is_active
        )
        SELECT DISTINCT
            TRIM(oven_cell.display_value) AS oven_code,
            TRIM(oven_cell.display_value) AS oven_name,
            TRUE
        FROM excel_raw_cells oven_cell
        WHERE oven_cell.sheet_id = :sheet_id
          AND oven_cell.row_number >= 3
          AND oven_cell.column_number = 3
          AND oven_cell.display_value IS NOT NULL
          AND TRIM(oven_cell.display_value) <> ''
        ON CONFLICT (oven_code)
        DO UPDATE SET
            oven_name = EXCLUDED.oven_name,
            is_active = TRUE;
        """,
        {"sheet_id": oven_sheet_id},
    )

    run_sql(
        """
        INSERT INTO mpps_oven_plan (
            plan_date,
            oven_code,
            shift_name,
            material_code,
            item_description,
            planned_qty,
            planned_weight_kg,
            plan_status,
            source_workbook,
            source_sheet,
            source_row,
            source_note
        )
        SELECT
            :plan_date,
            TRIM(oven_cell.display_value) AS oven_code,
            'TOTAL',
            TRIM(material_cell.display_value) AS material_code,
            TRIM(description_cell.display_value) AS item_description,
            ROUND(COALESCE(total_plan_cell.number_value, total_cell.number_value, 0))::INTEGER AS planned_qty,
            COALESCE(day_weight_cell.number_value, 0) + COALESCE(night_weight_cell.number_value, 0) AS planned_weight_kg,
            'PLANNED',
            'OVEN SHEET PLAN  JUNE 01-2026.xlsx',
            'OVEN',
            oven_cell.row_number,
            'Mapped from OVEN sheet. Planned qty uses Total Plan / Total column.'
        FROM excel_raw_cells oven_cell
        LEFT JOIN excel_raw_cells material_cell
            ON material_cell.sheet_id = oven_cell.sheet_id
           AND material_cell.row_number = oven_cell.row_number
           AND material_cell.column_number = 4
        LEFT JOIN excel_raw_cells description_cell
            ON description_cell.sheet_id = oven_cell.sheet_id
           AND description_cell.row_number = oven_cell.row_number
           AND description_cell.column_number = 5
        LEFT JOIN excel_raw_cells total_cell
            ON total_cell.sheet_id = oven_cell.sheet_id
           AND total_cell.row_number = oven_cell.row_number
           AND total_cell.column_number = 16
        LEFT JOIN excel_raw_cells day_weight_cell
            ON day_weight_cell.sheet_id = oven_cell.sheet_id
           AND day_weight_cell.row_number = oven_cell.row_number
           AND day_weight_cell.column_number = 18
        LEFT JOIN excel_raw_cells night_weight_cell
            ON night_weight_cell.sheet_id = oven_cell.sheet_id
           AND night_weight_cell.row_number = oven_cell.row_number
           AND night_weight_cell.column_number = 19
        LEFT JOIN excel_raw_cells total_plan_cell
            ON total_plan_cell.sheet_id = oven_cell.sheet_id
           AND total_plan_cell.row_number = oven_cell.row_number
           AND total_plan_cell.column_number = 20
        WHERE oven_cell.sheet_id = :sheet_id
          AND oven_cell.row_number >= 3
          AND oven_cell.column_number = 3
          AND oven_cell.display_value IS NOT NULL
          AND material_cell.display_value IS NOT NULL
          AND COALESCE(total_plan_cell.number_value, total_cell.number_value, 0) > 0;
        """,
        {
            "sheet_id": oven_sheet_id,
            "plan_date": plan_date,
        },
    )


def create_data_quality_issues() -> None:
    print("Creating MPPS data quality warnings...")

    run_sql(
        """
        INSERT INTO mpps_data_quality_issues (
            issue_level,
            issue_area,
            source_workbook,
            source_sheet,
            source_row,
            material_code,
            issue_message
        )
        SELECT
            'WARNING',
            'WEIGHT',
            si.source_workbook,
            si.source_sheet,
            si.source_row,
            spv.material_code,
            'Average weight is missing or zero while production is required.'
        FROM mpps_stock_planning_view spv
        JOIN mpps_stock_items si
            ON si.material_code = spv.material_code
        WHERE spv.production_required_qty > 0
          AND COALESCE(spv.average_weight, 0) <= 0;
        """
    )

    run_sql(
        """
        INSERT INTO mpps_data_quality_issues (
            issue_level,
            issue_area,
            source_workbook,
            source_sheet,
            source_row,
            material_code,
            issue_message
        )
        SELECT
            'WARNING',
            'BOM',
            si.source_workbook,
            si.source_sheet,
            si.source_row,
            si.material_code,
            'BOM data is missing for this item while production is required.'
        FROM mpps_stock_planning_view spv
        JOIN mpps_stock_items si
            ON si.material_code = spv.material_code
        WHERE spv.production_required_qty > 0
          AND NOT EXISTS (
              SELECT 1
              FROM mpps_bom_items bi
              WHERE bi.finished_item_code = spv.material_code
          );
        """
    )

    run_sql(
        """
        INSERT INTO mpps_data_quality_issues (
            issue_level,
            issue_area,
            source_workbook,
            source_sheet,
            source_row,
            material_code,
            issue_message
        )
        SELECT
            'WARNING',
            'COMPOUND',
            si.source_workbook,
            si.source_sheet,
            si.source_row,
            si.material_code,
            'Compound data is missing for this item while production is required.'
        FROM mpps_stock_planning_view spv
        JOIN mpps_stock_items si
            ON si.material_code = spv.material_code
        WHERE spv.production_required_qty > 0
          AND NOT EXISTS (
              SELECT 1
              FROM mpps_compound_master cm
              WHERE cm.item_code = spv.material_code
          );
        """
    )


def print_counts() -> None:
    print("")
    print("Clean MPPS mapping result:")
    print("--------------------------")
    tables = [
        "tire_types",
        "mpps_stock_items",
        "mpps_shipment_demand",
        "mpps_bom_items",
        "mpps_compound_master",
        "mpps_bead_master",
        "mpps_band_master",
        "mpps_capacity_master",
        "ovens",
        "shifts",
        "production_rules",
        "mpps_oven_plan",
        "mpps_data_quality_issues",
    ]

    for table_name in tables:
        print(f"{table_name}: {count_table(table_name)}")


def main() -> None:
    print("Starting raw Excel to clean MPPS mapping...")
    init_database()

    clean_target_tables()
    seed_shift_and_rules()

    map_stock_sheet()
    map_bom_sheet()
    map_compound_sheet()
    map_bead_sheet()
    map_band_sheet()
    map_capacity_sheet()
    map_oven_master_and_plan()
    create_data_quality_issues()

    print_counts()

    print("")
    print("Raw Excel to clean MPPS mapping completed successfully.")
    print("Existing users and roles were not changed.")
    print("Next step: run app and check MPPS Stock Planning page.")


if __name__ == "__main__":
    main()