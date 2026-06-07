from __future__ import annotations

from sqlalchemy import text
from app.database import engine, init_database


def run_sql(statement: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(statement))


def main() -> None:
    print("Starting database migration for Audit Logs table...")
    
    # Initialize basic app models first
    init_database()

    # Create the mpps_audit_logs table safely
    run_sql(
        """
        CREATE TABLE IF NOT EXISTS mpps_audit_logs (
            id SERIAL PRIMARY KEY,
            action_timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            username VARCHAR(100) NOT NULL,
            action_type VARCHAR(100) NOT NULL, -- e.g., 'INSERT', 'UPDATE', 'DELETE', 'LOGIN', 'RESTORE'
            table_name VARCHAR(100) NOT NULL,  -- e.g., 'mpps_stock_items', 'orders', 'users'
            record_id VARCHAR(100),            -- e.g., material_code or primary key ID
            old_values TEXT,                   -- JSON or text representation of old state
            new_values TEXT,                   -- JSON or text representation of new state
            note TEXT                          -- Optional description of the action
        );
        """
    )
    
    # Add an index on columns commonly used for searching or filtering logs
    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_mpps_audit_logs_timestamp
        ON mpps_audit_logs(action_timestamp);
        """
    )
    
    run_sql(
        """
        CREATE INDEX IF NOT EXISTS ix_mpps_audit_logs_username
        ON mpps_audit_logs(username);
        """
    )

    print("Audit Logs database migration script successfully prepared.")


if __name__ == "__main__":
    main()
