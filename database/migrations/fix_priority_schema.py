from __future__ import annotations

from sqlalchemy import text

from app.database import engine, init_database


def run_sql(statement: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(statement))


def main() -> None:
    print("Starting priority schema update...")

    # Create any new tables from SQLAlchemy models if they do not exist.
    init_database()

    # Add manager tire priority columns to existing order_items table.
    run_sql(
        """
        ALTER TABLE order_items
        ADD COLUMN IF NOT EXISTS manager_priority INTEGER NOT NULL DEFAULT 0;
        """
    )

    run_sql(
        """
        ALTER TABLE order_items
        ADD COLUMN IF NOT EXISTS manager_priority_label VARCHAR(30) NOT NULL DEFAULT 'NORMAL';
        """
    )

    run_sql(
        """
        ALTER TABLE order_items
        ADD COLUMN IF NOT EXISTS priority_reason TEXT;
        """
    )

    run_sql(
        """
        ALTER TABLE order_items
        ADD COLUMN IF NOT EXISTS priority_updated_by INTEGER;
        """
    )

    run_sql(
        """
        ALTER TABLE order_items
        ADD COLUMN IF NOT EXISTS priority_updated_at TIMESTAMP;
        """
    )

    # Keep existing order item data safe and normalized.
    run_sql(
        """
        UPDATE order_items
        SET manager_priority = 0
        WHERE manager_priority IS NULL;
        """
    )

    run_sql(
        """
        UPDATE order_items
        SET manager_priority_label = 'NORMAL'
        WHERE manager_priority_label IS NULL OR TRIM(manager_priority_label) = '';
        """
    )

    # Create audit log table if it does not already exist.
    run_sql(
        """
        CREATE TABLE IF NOT EXISTS order_item_priority_log (
            id SERIAL PRIMARY KEY,
            order_item_id INTEGER NOT NULL REFERENCES order_items(id) ON DELETE CASCADE,
            old_priority INTEGER,
            new_priority INTEGER NOT NULL,
            old_priority_label VARCHAR(30),
            new_priority_label VARCHAR(30) NOT NULL,
            reason TEXT,
            changed_by INTEGER REFERENCES users(id),
            changed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    # Helpful indexes for future schedule rebuild and history review.
    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_order_items_manager_priority
        ON order_items(manager_priority DESC);
        """
    )

    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_order_item_priority_log_order_item_id
        ON order_item_priority_log(order_item_id);
        """
    )

    print("Priority schema update completed successfully.")


if __name__ == "__main__":
    main()

