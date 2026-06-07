from __future__ import annotations

from sqlalchemy import text

from app.database import engine, init_database


def run_sql(statement: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(statement))


def main() -> None:
    print("Starting MPPS stock planning schema update...")

    init_database()

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS mpps_stock_items (
            id SERIAL PRIMARY KEY,
            material_code VARCHAR(60) NOT NULL UNIQUE,
            item_description VARCHAR(220) NOT NULL,
            tire_type_id INTEGER REFERENCES tire_types(id),
            product_type VARCHAR(120),
            size VARCHAR(80),
            product_group VARCHAR(120),

            fg_stock INTEGER NOT NULL DEFAULT 0,
            qc_stock INTEGER NOT NULL DEFAULT 0,
            scrap_stock INTEGER NOT NULL DEFAULT 0,
            blocked_stock INTEGER NOT NULL DEFAULT 0,

            average_weight NUMERIC(14, 4),
            compound_weight NUMERIC(14, 4),
            bead_type VARCHAR(120),
            band_type VARCHAR(120),

            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            last_updated_date DATE NOT NULL DEFAULT CURRENT_DATE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT ck_mpps_fg_stock_non_negative CHECK (fg_stock >= 0),
            CONSTRAINT ck_mpps_qc_stock_non_negative CHECK (qc_stock >= 0),
            CONSTRAINT ck_mpps_scrap_stock_non_negative CHECK (scrap_stock >= 0),
            CONSTRAINT ck_mpps_blocked_stock_non_negative CHECK (blocked_stock >= 0),
            CONSTRAINT ck_mpps_average_weight_non_negative CHECK (average_weight IS NULL OR average_weight >= 0),
            CONSTRAINT ck_mpps_compound_weight_non_negative CHECK (compound_weight IS NULL OR compound_weight >= 0)
        );
        """
    )

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS mpps_shipment_demand (
            id SERIAL PRIMARY KEY,
            material_code VARCHAR(60) NOT NULL,
            customer_id INTEGER REFERENCES customers(id),
            order_id INTEGER REFERENCES orders(id),
            customer_name VARCHAR(180),
            demand_qty INTEGER NOT NULL,
            shipment_date DATE,
            status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
            note TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT ck_mpps_demand_qty_non_negative CHECK (demand_qty >= 0)
        );
        """
    )

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS mpps_bom_items (
            id SERIAL PRIMARY KEY,
            finished_item_code VARCHAR(60) NOT NULL,
            raw_material_code VARCHAR(80) NOT NULL,
            raw_material_name VARCHAR(220) NOT NULL,
            usage_per_unit NUMERIC(14, 6) NOT NULL DEFAULT 0,
            unit VARCHAR(30) NOT NULL DEFAULT 'KG',
            wastage_percentage NUMERIC(8, 4) NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT ck_mpps_bom_usage_non_negative CHECK (usage_per_unit >= 0),
            CONSTRAINT ck_mpps_bom_wastage_non_negative CHECK (wastage_percentage >= 0)
        );
        """
    )

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS mpps_compound_master (
            id SERIAL PRIMARY KEY,
            item_code VARCHAR(60) NOT NULL,
            compound_code VARCHAR(80) NOT NULL,
            compound_name VARCHAR(220) NOT NULL,
            compound_weight_per_unit NUMERIC(14, 6) NOT NULL DEFAULT 0,
            stage VARCHAR(80) NOT NULL DEFAULT 'MAIN',
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT ck_mpps_compound_weight_non_negative CHECK (compound_weight_per_unit >= 0)
        );
        """
    )

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS mpps_bead_master (
            id SERIAL PRIMARY KEY,
            item_code VARCHAR(60) NOT NULL,
            bead_type VARCHAR(120) NOT NULL,
            bead_per_tyre NUMERIC(14, 6) NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT ck_mpps_bead_per_tyre_non_negative CHECK (bead_per_tyre >= 0)
        );
        """
    )

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS mpps_band_master (
            id SERIAL PRIMARY KEY,
            item_code VARCHAR(60) NOT NULL,
            band_code VARCHAR(80),
            band_type VARCHAR(120) NOT NULL,
            band_usage_per_tyre NUMERIC(14, 6) NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT ck_mpps_band_usage_non_negative CHECK (band_usage_per_tyre >= 0)
        );
        """
    )

    run_sql(
        """
        CREATE TABLE IF NOT EXISTS mpps_capacity_master (
            id SERIAL PRIMARY KEY,
            item_code VARCHAR(60) NOT NULL UNIQUE,
            running_moulds NUMERIC(14, 4) NOT NULL DEFAULT 0,
            per_mould_capacity NUMERIC(14, 4) NOT NULL DEFAULT 0,
            available_capacity_per_day NUMERIC(14, 4) NOT NULL DEFAULT 0,
            target_date DATE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT ck_mpps_capacity_running_moulds_non_negative CHECK (running_moulds >= 0),
            CONSTRAINT ck_mpps_capacity_per_mould_non_negative CHECK (per_mould_capacity >= 0),
            CONSTRAINT ck_mpps_capacity_daily_non_negative CHECK (available_capacity_per_day >= 0)
        );
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_mpps_stock_items_material_code
        ON mpps_stock_items(material_code);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_mpps_stock_items_group
        ON mpps_stock_items(product_group);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_mpps_shipment_demand_material_status
        ON mpps_shipment_demand(material_code, status);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_mpps_shipment_demand_date
        ON mpps_shipment_demand(shipment_date);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_mpps_bom_finished_item
        ON mpps_bom_items(finished_item_code);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_mpps_compound_item
        ON mpps_compound_master(item_code);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_mpps_bead_item
        ON mpps_bead_master(item_code);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_mpps_band_item
        ON mpps_band_master(item_code);
        """
    )

    run_sql(
        """
        INSERT INTO mpps_stock_items (
            material_code,
            item_description,
            tire_type_id,
            product_type,
            is_active
        )
        SELECT
            tt.tire_code,
            tt.tire_name,
            tt.id,
            'TYRE',
            tt.is_active
        FROM tire_types tt
        ON CONFLICT (material_code)
        DO UPDATE SET
            item_description = EXCLUDED.item_description,
            tire_type_id = EXCLUDED.tire_type_id,
            product_type = COALESCE(mpps_stock_items.product_type, EXCLUDED.product_type),
            is_active = EXCLUDED.is_active,
            updated_at = CURRENT_TIMESTAMP;
        """
    )

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

    print("MPPS stock planning schema update completed successfully.")
    print("Created/updated safe tables:")
    print("- mpps_stock_items")
    print("- mpps_shipment_demand")
    print("- mpps_bom_items")
    print("- mpps_compound_master")
    print("- mpps_bead_master")
    print("- mpps_band_master")
    print("- mpps_capacity_master")
    print("- mpps_stock_planning_view")
    print("Existing app data was not deleted or dropped.")


if __name__ == "__main__":
    main()
