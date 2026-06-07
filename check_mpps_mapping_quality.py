from __future__ import annotations

from sqlalchemy import text

from app.database import engine


def print_rows(title: str, sql: str) -> None:
    print("")
    print(title)
    print("-" * len(title))

    with engine.begin() as connection:
        rows = connection.execute(text(sql)).mappings().all()

    if not rows:
        print("No records found.")
        return

    for row in rows:
        print(dict(row))


def print_scalar(title: str, sql: str) -> None:
    with engine.begin() as connection:
        value = connection.execute(text(sql)).scalar()

    print(f"{title}: {value}")


def main() -> None:
    print("MPPS Mapping Quality Check")
    print("==========================")

    print_scalar("Total stock items", "SELECT COUNT(*) FROM mpps_stock_items;")
    print_scalar("Total demand rows", "SELECT COUNT(*) FROM mpps_shipment_demand;")
    print_scalar("Total BOM rows", "SELECT COUNT(*) FROM mpps_bom_items;")
    print_scalar("Total compound rows", "SELECT COUNT(*) FROM mpps_compound_master;")
    print_scalar("Total bead rows", "SELECT COUNT(*) FROM mpps_bead_master;")
    print_scalar("Total band rows", "SELECT COUNT(*) FROM mpps_band_master;")
    print_scalar("Total capacity rows", "SELECT COUNT(*) FROM mpps_capacity_master;")
    print_scalar("Total oven plan rows", "SELECT COUNT(*) FROM mpps_oven_plan;")
    print_scalar("Total data quality issues", "SELECT COUNT(*) FROM mpps_data_quality_issues;")

    print_rows(
        "Stock planning status summary",
        """
        SELECT
            status,
            COUNT(*) AS item_count,
            SUM(shipment_demand) AS shipment_demand,
            SUM(ready_for_shipment) AS ready_for_shipment,
            SUM(shortage_qty) AS shortage_qty,
            SUM(production_required_qty) AS production_required_qty,
            SUM(total_required_weight_kg) AS total_required_weight_kg,
            SUM(total_required_weight_tons) AS total_required_weight_tons
        FROM mpps_stock_planning_view
        GROUP BY status
        ORDER BY item_count DESC;
        """,
    )

    print_rows(
        "Weight quality summary",
        """
        SELECT
            COUNT(*) AS total_items,
            SUM(CASE WHEN average_weight IS NULL THEN 1 ELSE 0 END) AS average_weight_null,
            SUM(CASE WHEN average_weight = 0 THEN 1 ELSE 0 END) AS average_weight_zero,
            SUM(CASE WHEN average_weight > 0 THEN 1 ELSE 0 END) AS average_weight_positive,
            MIN(average_weight) AS min_average_weight,
            MAX(average_weight) AS max_average_weight,
            AVG(average_weight) AS avg_average_weight
        FROM mpps_stock_items;
        """,
    )

    print_rows(
        "Production required items with missing weight",
        """
        SELECT
            material_code,
            item_description,
            shipment_demand,
            available_stock,
            production_required_qty,
            average_weight,
            total_required_weight_tons,
            status
        FROM mpps_stock_planning_view
        WHERE production_required_qty > 0
          AND (average_weight IS NULL OR average_weight = 0)
        ORDER BY production_required_qty DESC
        LIMIT 20;
        """,
    )

    print_rows(
        "Top production required items",
        """
        SELECT
            material_code,
            item_description,
            fg_stock,
            qc_stock,
            scrap_stock,
            blocked_stock,
            available_stock,
            shipment_demand,
            production_required_qty,
            average_weight,
            total_required_weight_tons,
            status
        FROM mpps_stock_planning_view
        WHERE production_required_qty > 0
        ORDER BY production_required_qty DESC
        LIMIT 20;
        """,
    )

    print_rows(
        "Data quality issue summary",
        """
        SELECT
            issue_area,
            issue_level,
            COUNT(*) AS issue_count
        FROM mpps_data_quality_issues
        GROUP BY issue_area, issue_level
        ORDER BY issue_count DESC;
        """,
    )

    print_rows(
        "Sample data quality issues",
        """
        SELECT
            issue_area,
            issue_level,
            material_code,
            source_sheet,
            source_row,
            issue_message
        FROM mpps_data_quality_issues
        ORDER BY id
        LIMIT 20;
        """,
    )

    print_rows(
        "Raw Stock sheet candidate weight columns check",
        """
        SELECT
            column_number,
            column_letter,
            COUNT(*) FILTER (WHERE number_value IS NOT NULL) AS numeric_count,
            COUNT(*) FILTER (WHERE number_value > 0) AS positive_count,
            COUNT(*) FILTER (WHERE number_value < 0) AS negative_count,
            MIN(number_value) AS min_value,
            MAX(number_value) AS max_value,
            AVG(number_value) AS avg_value
        FROM excel_raw_cells
        WHERE sheet_id = (
            SELECT es.id
            FROM excel_sheets es
            JOIN excel_workbooks ew
                ON ew.id = es.workbook_id
            WHERE ew.workbook_key = 'MPPS_MAY_2026'
              AND es.sheet_name = 'Stock'
            LIMIT 1
        )
          AND row_number >= 4
          AND column_number BETWEEN 200 AND 225
        GROUP BY column_number, column_letter
        ORDER BY column_number;
        """,
    )

    print("")
    print("Check completed.")


if __name__ == "__main__":
    main()