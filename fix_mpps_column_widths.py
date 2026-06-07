from __future__ import annotations

from sqlalchemy import text

from app.database import engine


def run_sql(sql: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(sql))


def main() -> None:
    print("Starting MPPS column width fix with view rebuild...")

    print("Dropping dependent view...")
    run_sql("DROP VIEW IF EXISTS mpps_stock_planning_view;")

    print("Expanding clean MPPS table text columns...")

    run_sql(
        """
        ALTER TABLE mpps_stock_items
        ALTER COLUMN material_code TYPE VARCHAR(260),
        ALTER COLUMN item_description TYPE VARCHAR(500),
        ALTER COLUMN product_type TYPE VARCHAR(260),
        ALTER COLUMN size TYPE VARCHAR(260),
        ALTER COLUMN product_group TYPE VARCHAR(260),
        ALTER COLUMN bead_type TYPE VARCHAR(500),
        ALTER COLUMN band_type TYPE VARCHAR(500),
        ALTER COLUMN source_workbook TYPE VARCHAR(500),
        ALTER COLUMN source_sheet TYPE VARCHAR(260),
        ALTER COLUMN source_note TYPE TEXT;
        """
    )

    run_sql(
        """
        ALTER TABLE mpps_shipment_demand
        ALTER COLUMN material_code TYPE VARCHAR(260),
        ALTER COLUMN customer_name TYPE VARCHAR(500),
        ALTER COLUMN status TYPE VARCHAR(160),
        ALTER COLUMN source_workbook TYPE VARCHAR(500),
        ALTER COLUMN source_sheet TYPE VARCHAR(260),
        ALTER COLUMN source_column TYPE VARCHAR(80),
        ALTER COLUMN source_note TYPE TEXT;
        """
    )

    run_sql(
        """
        ALTER TABLE mpps_bom_items
        ALTER COLUMN finished_item_code TYPE VARCHAR(260),
        ALTER COLUMN raw_material_code TYPE VARCHAR(260),
        ALTER COLUMN raw_material_name TYPE VARCHAR(500),
        ALTER COLUMN unit TYPE VARCHAR(80),
        ALTER COLUMN source_workbook TYPE VARCHAR(500),
        ALTER COLUMN source_sheet TYPE VARCHAR(260),
        ALTER COLUMN source_note TYPE TEXT;
        """
    )

    run_sql(
        """
        ALTER TABLE mpps_compound_master
        ALTER COLUMN item_code TYPE VARCHAR(260),
        ALTER COLUMN compound_code TYPE VARCHAR(260),
        ALTER COLUMN compound_name TYPE VARCHAR(500),
        ALTER COLUMN stage TYPE VARCHAR(160),
        ALTER COLUMN source_workbook TYPE VARCHAR(500),
        ALTER COLUMN source_sheet TYPE VARCHAR(260),
        ALTER COLUMN source_note TYPE TEXT;
        """
    )

    run_sql(
        """
        ALTER TABLE mpps_bead_master
        ALTER COLUMN item_code TYPE VARCHAR(260),
        ALTER COLUMN bead_type TYPE VARCHAR(500),
        ALTER COLUMN source_workbook TYPE VARCHAR(500),
        ALTER COLUMN source_sheet TYPE VARCHAR(260),
        ALTER COLUMN source_note TYPE TEXT;
        """
    )

    run_sql(
        """
        ALTER TABLE mpps_band_master
        ALTER COLUMN item_code TYPE VARCHAR(260),
        ALTER COLUMN band_code TYPE VARCHAR(260),
        ALTER COLUMN band_type TYPE VARCHAR(500),
        ALTER COLUMN source_workbook TYPE VARCHAR(500),
        ALTER COLUMN source_sheet TYPE VARCHAR(260),
        ALTER COLUMN source_note TYPE TEXT;
        """
    )

    run_sql(
        """
        ALTER TABLE mpps_capacity_master
        ALTER COLUMN item_code TYPE VARCHAR(260),
        ALTER COLUMN source_workbook TYPE VARCHAR(500),
        ALTER COLUMN source_sheet TYPE VARCHAR(260),
        ALTER COLUMN source_note TYPE TEXT;
        """
    )

    run_sql(
        """
        ALTER TABLE mpps_oven_plan
        ALTER COLUMN oven_code TYPE VARCHAR(260),
        ALTER COLUMN shift_name TYPE VARCHAR(160),
        ALTER COLUMN material_code TYPE VARCHAR(260),
        ALTER COLUMN item_description TYPE VARCHAR(500),
        ALTER COLUMN plan_status TYPE VARCHAR(160),
        ALTER COLUMN source_workbook TYPE VARCHAR(500),
        ALTER COLUMN source_sheet TYPE VARCHAR(260),
        ALTER COLUMN source_note TYPE TEXT;
        """
    )

    print("Recreating mpps_stock_planning_view...")

    run_sql(
        """
        CREATE OR REPLACE VIEW mpps_stock_planning_view AS
        WITH existing_order_demand AS (
            SELECT
                tt.tire_code AS material_code,
                SUM(oi.quantity)::INTEGER AS demand_qty
            FROM order_items oi
            JOIN orders o
                ON o.id = oi.order_id
            JOIN tire_types tt
                ON tt.id = oi.tire_type_id
            WHERE UPPER(o.status) IN ('PENDING', 'CONFIRMED', 'PLANNED', 'PARTIALLY_PLANNED')
            GROUP BY tt.tire_code
        ),
        manual_demand AS (
            SELECT
                material_code,
                SUM(demand_qty)::INTEGER AS demand_qty
            FROM mpps_shipment_demand
            WHERE UPPER(status) IN ('PENDING', 'CONFIRMED', 'PLANNED', 'PARTIALLY_PLANNED')
            GROUP BY material_code
        ),
        combined_demand AS (
            SELECT
                material_code,
                SUM(demand_qty)::INTEGER AS shipment_demand
            FROM (
                SELECT material_code, demand_qty FROM existing_order_demand
                UNION ALL
                SELECT material_code, demand_qty FROM manual_demand
            ) demand_union
            GROUP BY material_code
        ),
        stock_calc AS (
            SELECT
                si.id,
                si.material_code,
                si.item_description,
                si.tire_type_id,
                si.product_type,
                si.size,
                si.product_group,
                si.fg_stock,
                si.qc_stock,
                si.scrap_stock,
                si.blocked_stock,
                (si.fg_stock + si.qc_stock - si.scrap_stock - si.blocked_stock)::INTEGER AS total_stock,
                (si.fg_stock + si.qc_stock - si.scrap_stock - si.blocked_stock)::INTEGER AS available_stock,
                COALESCE(cd.shipment_demand, 0)::INTEGER AS shipment_demand,
                si.average_weight,
                si.compound_weight,
                si.bead_type,
                si.band_type,
                si.last_updated_date,
                si.is_active
            FROM mpps_stock_items si
            LEFT JOIN combined_demand cd
                ON cd.material_code = si.material_code
            WHERE si.is_active = TRUE
        )
        SELECT
            sc.*,
            CASE
                WHEN sc.shipment_demand <= 0 THEN 0
                WHEN GREATEST(sc.available_stock, 0) >= sc.shipment_demand THEN sc.shipment_demand
                ELSE GREATEST(sc.available_stock, 0)
            END::INTEGER AS ready_for_shipment,
            GREATEST(sc.shipment_demand - GREATEST(sc.available_stock, 0), 0)::INTEGER AS shortage_qty,
            GREATEST(sc.shipment_demand - GREATEST(sc.available_stock, 0), 0)::INTEGER AS production_required_qty,
            CASE
                WHEN sc.shipment_demand <= 0 THEN 'NO_DEMAND'
                WHEN GREATEST(sc.available_stock, 0) <= 0 AND sc.shipment_demand > 0 THEN 'NO_STOCK_PRODUCTION_REQUIRED'
                WHEN GREATEST(sc.available_stock, 0) >= sc.shipment_demand THEN 'READY'
                WHEN GREATEST(sc.available_stock, 0) > 0 AND GREATEST(sc.available_stock, 0) < sc.shipment_demand THEN 'PARTIAL_READY'
                ELSE 'PRODUCTION_REQUIRED'
            END AS status,
            (
                GREATEST(sc.shipment_demand - GREATEST(sc.available_stock, 0), 0)
                * COALESCE(sc.average_weight, 0)
            )::NUMERIC(18, 4) AS total_required_weight_kg,
            (
                GREATEST(sc.shipment_demand - GREATEST(sc.available_stock, 0), 0)
                * COALESCE(sc.average_weight, 0)
                / 1000.0
            )::NUMERIC(18, 4) AS total_required_weight_tons,
            CASE
                WHEN sc.average_weight IS NULL OR sc.average_weight = 0 THEN TRUE
                ELSE FALSE
            END AS weight_missing
        FROM stock_calc sc;
        """
    )

    print("MPPS column width fix completed successfully.")
    print("mpps_stock_planning_view rebuilt successfully.")
    print("Clean MPPS tables can now accept long Excel text values.")


if __name__ == "__main__":
    main()