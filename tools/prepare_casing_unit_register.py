from sqlalchemy import text
from app.database import engine
from app.ui.casing_master_page import CasingRepository

repo = CasingRepository()

with engine.begin() as conn:
    conn.execute(text("DELETE FROM casing_units WHERE LOWER(TRIM(casing_type)) = 'no casing'"))
    conn.execute(text("DELETE FROM casing_master WHERE LOWER(TRIM(casing_type)) = 'no casing'"))

repo.ensure_units_from_counts()

with engine.connect() as conn:
    rows = conn.execute(text("""
        SELECT
            c.casing_type,
            COUNT(u.id) AS unit_count
        FROM casing_master c
        LEFT JOIN casing_units u ON u.casing_type = c.casing_type
        GROUP BY c.casing_type
        ORDER BY c.casing_type
    """)).mappings().all()

    total_units = conn.execute(text("SELECT COUNT(*) FROM casing_units")).scalar_one()

print("Casing unit register prepared.")
print("Total casing types:", len(rows))
print("Total casing units:", total_units)

for row in rows:
    print(row["casing_type"], "| Units:", row["unit_count"])
