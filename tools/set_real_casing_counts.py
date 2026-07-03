from datetime import datetime
from sqlalchemy import text
from app.database import engine

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

real_casing_data = [
    ("B2", 21),
    ("B3", 13),
    ("B4", 14),
    ("B5", 11),
    ("B5 Special 01", 2),
    ("B5 Special 02", 4),
    ("B5 Special 03", 2),
    ("B7", 4),
]

with engine.begin() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS casing_master (
            id BIGSERIAL PRIMARY KEY,
            casing_type VARCHAR(255) NOT NULL UNIQUE,
            available_casing_count INTEGER NOT NULL DEFAULT 0,
            status VARCHAR(32) NOT NULL DEFAULT 'Active',
            remarks TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))

    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS casing_master_backup_real_counts_{timestamp}
        AS SELECT * FROM casing_master
    """))

    conn.execute(text("DELETE FROM casing_master"))

    for casing_type, count in real_casing_data:
        conn.execute(
            text("""
                INSERT INTO casing_master (
                    casing_type,
                    available_casing_count,
                    status,
                    remarks,
                    updated_at
                )
                VALUES (
                    :casing_type,
                    :available_casing_count,
                    'Active',
                    'From Master File (3) / Casing type sheet',
                    CURRENT_TIMESTAMP
                )
            """),
            {
                "casing_type": casing_type,
                "available_casing_count": count,
            },
        )

    rows = conn.execute(text("""
        SELECT casing_type, available_casing_count
        FROM casing_master
        ORDER BY casing_type
    """)).mappings().all()

    total = conn.execute(text("""
        SELECT COALESCE(SUM(available_casing_count), 0)
        FROM casing_master
    """)).scalar_one()

print("Casing Master real counts updated.")
print("Backup table: casing_master_backup_real_counts_" + timestamp)
print("Total casing types:", len(rows))
print("Total available casings:", total)
print("")
for row in rows:
    print(row["casing_type"], "|", row["available_casing_count"])
