from __future__ import annotations

from sqlalchemy import text

from app.database import engine


def run() -> None:
    statements = (
        """
        CREATE TABLE IF NOT EXISTS mpps_system_settings (
            id BIGSERIAL PRIMARY KEY,
            category VARCHAR(50) NOT NULL,
            setting_key VARCHAR(100) NOT NULL,
            setting_value TEXT NOT NULL,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(category, setting_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS factory_holidays (
            id SERIAL PRIMARY KEY,
            holiday_date DATE NOT NULL UNIQUE,
            holiday_name VARCHAR(200) NOT NULL,
            holiday_type VARCHAR(50) NOT NULL DEFAULT 'FACTORY_HOLIDAY',
            is_working_day_override BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_mpps_system_settings_category_key
        ON mpps_system_settings(category, setting_key)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_factory_holidays_date
        ON factory_holidays(holiday_date)
        """,
    )

    defaults = {
        "planning_horizon_days": "30",
        "packing_dispatch_buffer_days": "1",
        "safety_stock_pct": "0",
        "auto_replan_enabled": "true",
        "allow_overtime": "false",
        "replan_debounce_seconds": "5",
        "priority_policy": "TARGET_DATE_FIRST",
    }

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))

        for key, value in defaults.items():
            conn.execute(
                text(
                    """
                    INSERT INTO mpps_system_settings (
                        category,
                        setting_key,
                        setting_value
                    )
                    VALUES (
                        'PLANNING',
                        :setting_key,
                        :setting_value
                    )
                    ON CONFLICT (category, setting_key)
                    DO NOTHING
                    """
                ),
                {
                    "setting_key": key,
                    "setting_value": value,
                },
            )

    print("ADMIN CONTROL R4 DATABASE MIGRATION OK")


if __name__ == "__main__":
    run()
