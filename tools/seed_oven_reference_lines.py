from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text

from app.database import engine


REFERENCE_LINES = [
    {
        "line_name": "ORING-PRESS",
        "cavities": ["ORING-PRESS-001", "ORING-PRESS-002"],
    },
    {
        "line_name": "NEW PRESS",
        "cavities": ["NEW PRESS 001"],
    },
    {
        "line_name": "NANCY PRESS",
        "cavities": ["NANCY -UP", "NANCY -DOWN"],
    },
    {
        "line_name": "400 T PRESS",
        "cavities": ["PRESS - UP - 001", "PRESS - DOWN - 001"],
    },
    {
        "line_name": "T 600 -01 PRESS",
        "cavities": ["L-PRESS-600/01 Up", "L-PRESS-600/1 Down"],
    },
    {
        "line_name": "T 600 -02 PRESS",
        "cavities": ["L-PRESS-600/02 Up", "L-PRESS-600/2 Down"],
    },
    {
        "line_name": "L-PRESS-1250",
        "cavities": ["L-PRESS-1250-001"],
    },
    {
        "line_name": "L-PRESS-1500",
        "cavities": ["L-PRESS-1500-001"],
    },
    {
        "line_name": "L-PRESS-1800",
        "cavities": ["L-PRESS-1800-001"],
    },
    {
        "line_name": "Press -LINE",
        "cavities": [
            "L-PRESS-001",
            "L-PRESS-002",
            "L-PRESS-003",
            "L-PRESS-004",
            "L-PRESS-005",
            "L-PRESS-006",
            "L-PRESS-007",
            "L-PRESS-008",
            "L-PRESS-009",
            "L-PRESS-010",
            "L-PRESS-011",
            "L-PRESS-012",
            "L-PRESS-013",
            "L-PRESS-014",
            "DOUBLE-PRESS-001",
            "DOUBLE-PRESS-002",
            "DOUBLE-PRESS-003",
            "DOUBLE-PRESS-004",
            "DOUBLE-PRESS-005",
            "DOUBLE-PRESS-006",
        ],
    },
    {
        "line_name": "Line-400",
        "cavities": [
            "T400-001",
            "T400-002",
            "T400-003",
            "T400-004",
            "T400-005",
            "T400-006",
            "T400-007",
            "T400-008",
            "T400-009",
            "T400-010",
            "T400-011",
            "T400-012",
            "T400-013",
            "T400-014",
            "T400-015",
            "T400-016",
            "T400-017",
            "T400-018",
            "T400-019",
            "T400-020",
            "T400-021",
            "T400-022",
            "T400-023",
            "T400-024",
            "T400-025",
            "T400-026",
            "T400-027",
            "T400-028",
            "T400-029",
            "T400-030",
            "T400-031",
            "T400-032",
            "T400-033",
            "T400-034",
            "T400-035",
            "T400-036",
            "T400-037",
            "T400-038",
            "L-OVEN-039",
            "L-OVEN-040",
            "L-OVEN-041",
        ],
    },
    {
        "line_name": "Line-800",
        "cavities": [
            "T800-001",
            "T800-002",
            "T800-003",
            "T800-004",
            "T800-005",
            "T800-006",
            "T800-007",
            "T800-008",
            "T800-009",
            "T800-010",
            "T800-011",
            "T800-012",
            "T800-013",
            "T800-014",
            "T800-015",
            "T800-016",
            "T800-017",
            "T800-018",
            "T800-019",
            "T800-020",
            "T800-021",
            "T800-022",
            "T800-023",
            "T800-024",
            "T800-025",
            "T800-026",
            "T800-027",
        ],
    },
]


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return str(value)


def table_exists(conn, table_name: str) -> bool:
    return bool(
        conn.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                )
            """),
            {"table_name": table_name},
        ).scalar_one()
    )


def read_table(conn, table_name: str) -> list[dict]:
    if not table_exists(conn, table_name):
        return []

    return [
        dict(row)
        for row in conn.execute(text(f'SELECT * FROM public."{table_name}"')).mappings().all()
    ]


def ensure_tables() -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS production_lines (
                id VARCHAR(64) PRIMARY KEY,
                line_name VARCHAR(255) NOT NULL UNIQUE,
                status VARCHAR(32) NOT NULL DEFAULT 'Active',
                remarks TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS production_line_cavities (
                id BIGSERIAL PRIMARY KEY,
                line_name VARCHAR(255) NOT NULL,
                cavity_no INTEGER NOT NULL,
                status VARCHAR(32) NOT NULL DEFAULT 'Active',
                assigned_tyre_item VARCHAR(255) NOT NULL DEFAULT '',
                remarks TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(line_name, cavity_no)
            )
        """))

        conn.execute(text("""
            ALTER TABLE production_line_cavities
            ADD COLUMN IF NOT EXISTS cavity_code VARCHAR(255) NOT NULL DEFAULT ''
        """))

        conn.execute(text("""
            ALTER TABLE production_line_cavities
            ADD COLUMN IF NOT EXISTS display_order INTEGER NOT NULL DEFAULT 0
        """))


def patch_cavities_default_counts() -> None:
    page_path = PROJECT_ROOT / "app" / "ui" / "cavities_master_page.py"

    if not page_path.exists():
        print("Skipped code patch: app/ui/cavities_master_page.py not found.")
        return

    text_content = page_path.read_text(encoding="utf-8")

    new_dict_lines = ["DEFAULT_CAVITY_COUNTS = {\n"]
    for item in REFERENCE_LINES:
        new_dict_lines.append(f'    "{item["line_name"]}": {len(item["cavities"])},\n')
    new_dict_lines.append("}\n\n")
    new_dict = "".join(new_dict_lines)

    if "DEFAULT_CAVITY_COUNTS" in text_content:
        text_content = re.sub(
            r"DEFAULT_CAVITY_COUNTS\s*=\s*\{.*?\}\n\n",
            new_dict,
            text_content,
            flags=re.S,
        )
        page_path.write_text(text_content, encoding="utf-8")
        print("Patched Cavities page default line/cavity counts.")
    else:
        print("Skipped code patch: DEFAULT_CAVITY_COUNTS not found.")


def main() -> None:
    ensure_tables()

    backup_dir = PROJECT_ROOT / "backups" / "db"
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"before_seed_oven_reference_lines_{timestamp}.json"

    with engine.connect() as conn:
        backup_data = {
            "production_lines": read_table(conn, "production_lines"),
            "production_line_cavities": read_table(conn, "production_line_cavities"),
        }

    backup_path.write_text(
        json.dumps(backup_data, indent=2, default=json_default),
        encoding="utf-8",
    )

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM production_line_cavities"))
        conn.execute(text("DELETE FROM production_lines"))

        for line_order, item in enumerate(REFERENCE_LINES, start=1):
            line_name = item["line_name"]
            cavities = item["cavities"]

            conn.execute(
                text("""
                    INSERT INTO production_lines
                        (id, line_name, status, remarks)
                    VALUES
                        (:id, :line_name, 'Active', :remarks)
                """),
                {
                    "id": str(uuid4()),
                    "line_name": line_name,
                    "remarks": f"Seeded from OVEN sheet reference. Cavities: {len(cavities)}",
                },
            )

            for cavity_no, cavity_code in enumerate(cavities, start=1):
                conn.execute(
                    text("""
                        INSERT INTO production_line_cavities
                            (line_name, cavity_no, cavity_code, display_order, status, assigned_tyre_item, remarks)
                        VALUES
                            (:line_name, :cavity_no, :cavity_code, :display_order, 'Active', '', '')
                    """),
                    {
                        "line_name": line_name,
                        "cavity_no": cavity_no,
                        "cavity_code": cavity_code,
                        "display_order": cavity_no,
                    },
                )

    patch_cavities_default_counts()

    total_lines = len(REFERENCE_LINES)
    total_cavities = sum(len(item["cavities"]) for item in REFERENCE_LINES)

    print("")
    print(f"Backup created: {backup_path}")
    print(f"Seeded production lines: {total_lines}")
    print(f"Seeded cavities / ovens: {total_cavities}")
    print("")

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
            ORDER BY
                CASE pl.line_name
                    WHEN 'ORING-PRESS' THEN 1
                    WHEN 'NEW PRESS' THEN 2
                    WHEN 'NANCY PRESS' THEN 3
                    WHEN '400 T PRESS' THEN 4
                    WHEN 'T 600 -01 PRESS' THEN 5
                    WHEN 'T 600 -02 PRESS' THEN 6
                    WHEN 'L-PRESS-1250' THEN 7
                    WHEN 'L-PRESS-1500' THEN 8
                    WHEN 'L-PRESS-1800' THEN 9
                    WHEN 'Press -LINE' THEN 10
                    WHEN 'Line-400' THEN 11
                    WHEN 'Line-800' THEN 12
                    ELSE 99
                END
        """)).mappings().all()

    for row in rows:
        print(f"{row['line_name']} | {row['status']} | cavities: {row['cavity_count']}")


if __name__ == "__main__":
    main()
