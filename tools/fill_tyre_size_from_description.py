import re
from sqlalchemy import text
from app.database import engine


def guess_tyre_size(description: str) -> str:
    desc = re.sub(r"\s+", " ", str(description or "").strip())

    if not desc:
        return ""

    parts = desc.split()

    if not parts:
        return ""

    # Examples:
    # 14X4 1/2-8 BB SM NM -> 14X4 1/2-8
    if len(parts) >= 2 and re.match(r"^\d+(\.\d+)?X\d+(\.\d+)?$", parts[0], re.I) and re.match(r"^\d+/\d+-\d+", parts[1]):
        return f"{parts[0]} {parts[1]}"

    # Examples:
    # 10X4-6 1/2 LA SM -> 10X4-6 1/2
    if len(parts) >= 2 and re.match(r".*-\d+$", parts[0]) and re.fullmatch(r"\d+/\d+", parts[1]):
        return f"{parts[0]} {parts[1]}"

    # Examples:
    # 10.00-20 7.50" NOR -> 10.00-20
    # 140/55-9 4.00" EF -> 140/55-9
    return parts[0]


with engine.begin() as conn:
    conn.execute(text("""
        ALTER TABLE tyre_item_master
        ADD COLUMN IF NOT EXISTS tyre_size VARCHAR(128) NOT NULL DEFAULT ''
    """))

    rows = conn.execute(text("""
        SELECT id, description
        FROM tyre_item_master
        ORDER BY sap_code
    """)).all()

    updated = 0

    for row in rows:
        tyre_size = guess_tyre_size(row.description)

        conn.execute(
            text("""
                UPDATE tyre_item_master
                SET tyre_size = :tyre_size,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """),
            {
                "id": row.id,
                "tyre_size": tyre_size,
            },
        )
        updated += 1

with engine.connect() as conn:
    total = conn.execute(text("SELECT COUNT(*) FROM tyre_item_master")).scalar_one()
    with_size = conn.execute(text("""
        SELECT COUNT(*)
        FROM tyre_item_master
        WHERE tyre_size <> ''
    """)).scalar_one()

    print("Total tyre items:", total)
    print("Tyre size filled:", with_size)

    print("")
    print("Sample:")
    rows = conn.execute(text("""
        SELECT sap_code, description, tyre_size
        FROM tyre_item_master
        ORDER BY sap_code
        LIMIT 20
    """)).all()

    for row in rows:
        print(row.sap_code, "|", row.tyre_size, "|", row.description)
