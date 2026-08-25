from __future__ import annotations

from sqlalchemy import text

from app.database import engine
from app.services.factory_planning_engine import FactoryPlanningEngine


FOUNDATION_SCHEMA_VERSION = "foundation_zero_freeze_r1"


def apply() -> None:
    # Run the legacy comprehensive preflight exactly once while the app is closed.
    # Operational code is patched so it no longer performs this DDL on page open.
    FactoryPlanningEngine().ensure_schema()

    with engine.begin() as connection:
        connection.execute(text("SET LOCAL lock_timeout='5s'"))
        connection.execute(text("SET LOCAL statement_timeout='60s'"))

        for sql in (
            "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS lifecycle_status VARCHAR(40) NOT NULL DEFAULT 'ACTIVE'",
            "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS actual_factory_out_date DATE",
            "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS actual_factory_out_at TIMESTAMP",
            "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS closure_reason TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS closure_decided_at TIMESTAMP",
            "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS closure_decided_by INTEGER",
            "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS hold_reason TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE mpps_shipments ADD COLUMN IF NOT EXISTS source_missing_from_latest BOOLEAN NOT NULL DEFAULT FALSE",
        ):
            connection.execute(text(sql))

        connection.execute(
            text(
                """
                UPDATE mpps_shipments
                SET lifecycle_status = CASE
                    WHEN LOWER(COALESCE(status,'')) IN ('shipped','complete','completed','closed','done') THEN 'SHIPPED'
                    WHEN LOWER(COALESCE(status,'')) IN ('cancelled','canceled') THEN 'CANCELLED'
                    WHEN LOWER(COALESCE(status,'')) IN ('on hold','hold') THEN 'HOLD'
                    WHEN COALESCE(source_missing_from_latest,FALSE)
                      OR LOWER(COALESCE(status,'')) IN ('review required','imported review','excel review hold')
                      OR LOWER(COALESCE(planning_status,'')) IN ('review required','missing from latest workbook')
                    THEN 'CLOSURE_REVIEW'
                    WHEN LOWER(COALESCE(status,'')) IN ('in progress','processing','in production') THEN 'IN_PROGRESS'
                    ELSE 'ACTIVE'
                END
                WHERE lifecycle_status IS NULL
                   OR lifecycle_status=''
                   OR lifecycle_status='ACTIVE'
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS mpps_shipment_lifecycle_audit (
                    id BIGSERIAL PRIMARY KEY,
                    shipment_id INTEGER NOT NULL REFERENCES mpps_shipments(id) ON DELETE CASCADE,
                    action VARCHAR(50) NOT NULL,
                    old_lifecycle VARCHAR(40) NOT NULL DEFAULT '',
                    new_lifecycle VARCHAR(40) NOT NULL DEFAULT '',
                    reason TEXT NOT NULL DEFAULT '',
                    decided_by INTEGER,
                    decided_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )

        indexes = (
            "CREATE INDEX IF NOT EXISTS ix_mpps_shipments_lifecycle_status ON mpps_shipments(lifecycle_status)",
            "CREATE INDEX IF NOT EXISTS ix_mpps_shipments_source_missing_latest ON mpps_shipments(source_missing_from_latest) WHERE source_missing_from_latest=TRUE",
            "CREATE INDEX IF NOT EXISTS ix_mpps_shipments_status_target ON mpps_shipments(status,target_date)",
            "CREATE INDEX IF NOT EXISTS ix_mpps_shipment_items_shipment_sap ON mpps_shipment_items(shipment_id,sap_code)",
            "CREATE INDEX IF NOT EXISTS ix_mpps_lifecycle_audit_shipment_date ON mpps_shipment_lifecycle_audit(shipment_id,decided_at DESC)",
        )
        for sql in indexes:
            connection.execute(text(sql))

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS mpps_schema_version (
                    version_key VARCHAR(120) PRIMARY KEY,
                    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO mpps_schema_version(version_key)
                VALUES(:version_key)
                ON CONFLICT(version_key) DO NOTHING
                """
            ),
            {"version_key": FOUNDATION_SCHEMA_VERSION},
        )


if __name__ == "__main__":
    apply()
    print("FOUNDATION R1 DATABASE MIGRATION OK")
