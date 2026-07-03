from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.database import engine

with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT
            pl.line_name,
            pl.status,
            COUNT(pc.id) AS cavity_count
        FROM production_lines pl
        LEFT JOIN production_line_cavities pc
            ON pc.line_name = pl.line_name
        GROUP BY pl.line_name, pl.status
        ORDER BY pl.line_name
    """)).mappings().all()

for row in rows:
    print(f"{row['line_name']} | {row['status']} | cavities: {row['cavity_count']}")
