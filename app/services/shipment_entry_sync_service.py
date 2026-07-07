from __future__ import annotations

from sqlalchemy import text

from app.database import engine


def ensure_shipment_entry_detail_table() -> None:
    """
    Creates and maintains a consolidated shipment entry detail table.

    mpps_shipment_entry_details stores shipment header + item details in one table.
    It is automatically rebuilt when mpps_shipments or mpps_shipment_items changes.
    """

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS mpps_shipments (
                    id SERIAL PRIMARY KEY,
                    shipment_no VARCHAR(100) NOT NULL UNIQUE,
                    customer_name VARCHAR(255) NOT NULL,
                    shipment_date DATE NOT NULL,
                    status VARCHAR(50) NOT NULL DEFAULT 'Planned',
                    note TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS mpps_shipment_items (
                    id SERIAL PRIMARY KEY,
                    shipment_id INTEGER NOT NULL REFERENCES mpps_shipments(id) ON DELETE CASCADE,
                    sap_code VARCHAR(100) NOT NULL,
                    item_description TEXT NOT NULL,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    start_date DATE,
                    end_date DATE,
                    item_status VARCHAR(50) NOT NULL DEFAULT 'Pending',
                    note TEXT,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS mpps_shipment_entry_details (
                    id SERIAL PRIMARY KEY,

                    shipment_id INTEGER NOT NULL,
                    shipment_item_id INTEGER,

                    shipment_no VARCHAR(100) NOT NULL,
                    customer_name VARCHAR(255) NOT NULL,
                    shipment_date DATE NOT NULL,
                    actual_receive_date DATE,
                    shipment_status VARCHAR(50),
                    shipment_note TEXT,

                    sap_code VARCHAR(100),
                    item_description TEXT,
                    quantity INTEGER NOT NULL DEFAULT 0,
                    item_start_date DATE,
                    item_end_date DATE,
                    item_status VARCHAR(50),
                    item_note TEXT,

                    source_table VARCHAR(100) NOT NULL DEFAULT 'shipment_entry',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )

        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_mpps_shipment_entry_details_shipment_id ON mpps_shipment_entry_details (shipment_id);"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_mpps_shipment_entry_details_shipment_date ON mpps_shipment_entry_details (shipment_date);"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_mpps_shipment_entry_details_sap_code ON mpps_shipment_entry_details (sap_code);"))

        connection.execute(
            text(
                """
                CREATE OR REPLACE FUNCTION mpps_rebuild_shipment_entry_details(p_shipment_id INTEGER)
                RETURNS VOID
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF p_shipment_id IS NULL THEN
                        RETURN;
                    END IF;

                    DELETE FROM mpps_shipment_entry_details
                    WHERE shipment_id = p_shipment_id;

                    INSERT INTO mpps_shipment_entry_details (
                        shipment_id,
                        shipment_item_id,
                        shipment_no,
                        customer_name,
                        shipment_date,
                        actual_receive_date,
                        shipment_status,
                        shipment_note,
                        sap_code,
                        item_description,
                        quantity,
                        item_start_date,
                        item_end_date,
                        item_status,
                        item_note,
                        source_table,
                        created_at,
                        updated_at
                    )
                    SELECT
                        s.id,
                        i.id,
                        s.shipment_no,
                        s.customer_name,
                        s.shipment_date,
                        NULL,
                        s.status,
                        s.note,
                        i.sap_code,
                        i.item_description,
                        i.quantity,
                        i.start_date,
                        i.end_date,
                        i.item_status,
                        i.note,
                        'mpps_shipments + mpps_shipment_items',
                        s.created_at,
                        CURRENT_TIMESTAMP
                    FROM mpps_shipments s
                    JOIN mpps_shipment_items i
                        ON i.shipment_id = s.id
                    WHERE s.id = p_shipment_id;

                    IF NOT FOUND THEN
                        INSERT INTO mpps_shipment_entry_details (
                            shipment_id,
                            shipment_item_id,
                            shipment_no,
                            customer_name,
                            shipment_date,
                            actual_receive_date,
                            shipment_status,
                            shipment_note,
                            sap_code,
                            item_description,
                            quantity,
                            item_start_date,
                            item_end_date,
                            item_status,
                            item_note,
                            source_table,
                            created_at,
                            updated_at
                        )
                        SELECT
                            s.id,
                            NULL,
                            s.shipment_no,
                            s.customer_name,
                            s.shipment_date,
                            NULL,
                            s.status,
                            s.note,
                            NULL,
                            NULL,
                            0,
                            NULL,
                            NULL,
                            NULL,
                            NULL,
                            'mpps_shipments',
                            s.created_at,
                            CURRENT_TIMESTAMP
                        FROM mpps_shipments s
                        WHERE s.id = p_shipment_id;
                    END IF;
                END;
                $$;
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE OR REPLACE FUNCTION mpps_shipments_entry_sync_trigger()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF TG_OP = 'DELETE' THEN
                        DELETE FROM mpps_shipment_entry_details
                        WHERE shipment_id = OLD.id;
                        RETURN OLD;
                    END IF;

                    PERFORM mpps_rebuild_shipment_entry_details(NEW.id);
                    RETURN NEW;
                END;
                $$;
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE OR REPLACE FUNCTION mpps_shipment_items_entry_sync_trigger()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                AS $$
                BEGIN
                    IF TG_OP = 'DELETE' THEN
                        PERFORM mpps_rebuild_shipment_entry_details(OLD.shipment_id);
                        RETURN OLD;
                    END IF;

                    PERFORM mpps_rebuild_shipment_entry_details(NEW.shipment_id);
                    RETURN NEW;
                END;
                $$;
                """
            )
        )

        connection.execute(text("DROP TRIGGER IF EXISTS trg_mpps_shipments_entry_sync ON mpps_shipments;"))
        connection.execute(
            text(
                """
                CREATE TRIGGER trg_mpps_shipments_entry_sync
                AFTER INSERT OR UPDATE OR DELETE ON mpps_shipments
                FOR EACH ROW
                EXECUTE FUNCTION mpps_shipments_entry_sync_trigger();
                """
            )
        )

        connection.execute(text("DROP TRIGGER IF EXISTS trg_mpps_shipment_items_entry_sync ON mpps_shipment_items;"))
        connection.execute(
            text(
                """
                CREATE TRIGGER trg_mpps_shipment_items_entry_sync
                AFTER INSERT OR UPDATE OR DELETE ON mpps_shipment_items
                FOR EACH ROW
                EXECUTE FUNCTION mpps_shipment_items_entry_sync_trigger();
                """
            )
        )

        connection.execute(
            text(
                """
                SELECT mpps_rebuild_shipment_entry_details(id)
                FROM mpps_shipments;
                """
            )
        )
