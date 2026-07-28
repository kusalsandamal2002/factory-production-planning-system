from __future__ import annotations

from sqlalchemy import text

from app.database import engine


ALTER_STATEMENTS = [
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS manager_order_date DATE
    """,
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS target_date DATE
    """,
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS plan_date DATE
    """,
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS factory_out_date DATE
    """,
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS factory_can_receive_date DATE
    """,
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS delivery_status VARCHAR(80)
    NOT NULL DEFAULT ''
    """,
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS delay_days INTEGER
    NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS early_days INTEGER
    NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS total_qty INTEGER
    NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS completed_qty INTEGER
    NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS progress_pct NUMERIC(6,2)
    NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS planning_status VARCHAR(80)
    NOT NULL DEFAULT ''
    """,
    """
    ALTER TABLE mpps_shipments
    ADD COLUMN IF NOT EXISTS planning_note TEXT
    NOT NULL DEFAULT ''
    """,
]


def main() -> None:
    with engine.begin() as connection:
        for statement in ALTER_STATEMENTS:
            connection.execute(text(statement))

        connection.execute(
            text(
                """
                UPDATE mpps_shipments
                SET
                    factory_can_receive_date = COALESCE(
                        factory_can_receive_date,
                        factory_out_date
                    ),
                    target_date = COALESCE(
                        target_date,
                        plan_date,
                        manager_order_date,
                        factory_can_receive_date,
                        factory_out_date
                    ),
                    plan_date = COALESCE(
                        plan_date,
                        target_date,
                        manager_order_date,
                        factory_can_receive_date,
                        factory_out_date
                    ),
                    manager_order_date = COALESCE(
                        manager_order_date,
                        target_date,
                        plan_date,
                        factory_can_receive_date,
                        factory_out_date
                    )
                """
            )
        )

        connection.execute(
            text(
                """
                UPDATE mpps_shipments
                SET
                    delivery_status = CASE
                        WHEN target_date IS NULL
                          OR factory_can_receive_date IS NULL
                            THEN 'Pending Calculation'
                        WHEN factory_can_receive_date < target_date
                            THEN 'Can Deliver Early'
                        WHEN factory_can_receive_date = target_date
                            THEN 'On Time'
                        ELSE 'Delayed'
                    END,
                    delay_days = CASE
                        WHEN target_date IS NOT NULL
                          AND factory_can_receive_date IS NOT NULL
                          AND factory_can_receive_date > target_date
                            THEN factory_can_receive_date - target_date
                        ELSE 0
                    END,
                    early_days = CASE
                        WHEN target_date IS NOT NULL
                          AND factory_can_receive_date IS NOT NULL
                          AND factory_can_receive_date < target_date
                            THEN target_date - factory_can_receive_date
                        ELSE 0
                    END
                """
            )
        )

    print(
        "Shipment target-date schema is ready."
    )


if __name__ == "__main__":
    main()
