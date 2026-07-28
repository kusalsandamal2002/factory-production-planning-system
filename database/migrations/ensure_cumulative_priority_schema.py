from __future__ import annotations

from sqlalchemy import text

from app.database import engine


def main() -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                ALTER TABLE mpps_shipments
                ADD COLUMN IF NOT EXISTS
                    target_date_is_manual BOOLEAN
                    NOT NULL DEFAULT FALSE
                """
            )
        )
        connection.execute(
            text(
                """
                ALTER TABLE mpps_shipments
                ADD COLUMN IF NOT EXISTS
                    target_date_source VARCHAR(80)
                    NOT NULL DEFAULT
                    'Automatic Factory Receive'
                """
            )
        )

        connection.execute(
            text(
                """
                UPDATE mpps_shipments
                SET
                    target_date_is_manual = CASE
                        WHEN target_date IS NOT NULL
                         AND (
                            factory_can_receive_date IS NULL
                            OR target_date
                                <> factory_can_receive_date
                         )
                        THEN TRUE
                        ELSE FALSE
                    END,
                    target_date_source = CASE
                        WHEN target_date IS NOT NULL
                         AND (
                            factory_can_receive_date IS NULL
                            OR target_date
                                <> factory_can_receive_date
                         )
                        THEN 'Manual'
                        ELSE 'Automatic Factory Receive'
                    END
                WHERE target_date_source =
                    'Automatic Factory Receive'
                """
            )
        )

        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS
                    ix_mpps_shipments_manual_target
                ON mpps_shipments (
                    target_date_is_manual,
                    target_date,
                    created_at,
                    id
                )
                """
            )
        )

    print(
        "Cumulative shipment priority schema ready."
    )


if __name__ == "__main__":
    main()
