from __future__ import annotations

import sys
from datetime import datetime

from sqlalchemy import text

from app.database import engine
from app.services.smds_schema import ensure_smds_table


CONFIRMATION_ARGUMENT = "--confirm-reset-all"


def main() -> None:
    if CONFIRMATION_ARGUMENT not in sys.argv:
        raise SystemExit(
            "This one-time migration resets every current "
            "SMDS approval to Pending.\n\n"
            "Run:\n"
            "python -m database.migrations."
            "reset_smds_approvals_to_pending "
            "--confirm-reset-all"
        )

    ensure_smds_table()
    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )
    backup_table = (
        "smds_approval_backup_"
        + timestamp
    )

    with engine.begin() as conn:
        conn.execute(
            text(
                f"""
                CREATE TABLE "{backup_table}" AS
                SELECT
                    id,
                    sap_code,
                    planning_manager_approval_status,
                    manager_approval_updated_at,
                    updated_at
                FROM smds
                """
            )
        )

        before = conn.execute(
            text(
                """
                SELECT
                    planning_manager_approval_status,
                    COUNT(*) AS row_count
                FROM smds
                GROUP BY
                    planning_manager_approval_status
                ORDER BY
                    planning_manager_approval_status
                """
            )
        ).all()

        result = conn.execute(
            text(
                """
                UPDATE smds
                SET
                    planning_manager_approval_status
                        = 'Pending',
                    manager_approval_updated_at
                        = NULL,
                    updated_at
                        = CURRENT_TIMESTAMP
                """
            )
        )

        after = conn.execute(
            text(
                """
                SELECT
                    planning_manager_approval_status,
                    COUNT(*) AS row_count
                FROM smds
                GROUP BY
                    planning_manager_approval_status
                ORDER BY
                    planning_manager_approval_status
                """
            )
        ).all()

    print("Backup table:", backup_table)
    print("Rows reset:", int(result.rowcount or 0))
    print("Before:", before)
    print("After:", after)


if __name__ == "__main__":
    main()
