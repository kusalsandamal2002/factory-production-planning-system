from pathlib import Path


file_path = Path("map_raw_excel_to_clean_mpps.py")

if not file_path.exists():
    raise FileNotFoundError("map_raw_excel_to_clean_mpps.py not found.")

code = file_path.read_text(encoding="utf-8")


replacements = [
    (
        """            vr.average_weight,
            vr.compound_weight,
            vr.bead_type,
            vr.band_type,
""",
        """            CASE
                WHEN vr.average_weight IS NOT NULL AND vr.average_weight >= 0
                    THEN vr.average_weight
                ELSE NULL
            END AS average_weight,
            CASE
                WHEN vr.compound_weight IS NOT NULL AND vr.compound_weight >= 0
                    THEN vr.compound_weight
                ELSE NULL
            END AS compound_weight,
            vr.bead_type,
            vr.band_type,
""",
    ),
    (
        """            average_weight = EXCLUDED.average_weight,
            compound_weight = EXCLUDED.compound_weight,
""",
        """            average_weight = EXCLUDED.average_weight,
            compound_weight = EXCLUDED.compound_weight,
""",
    ),
]

changed = False

for old, new in replacements:
    if old in code:
        code = code.replace(old, new)
        changed = True

if not changed:
    print("Warning: expected negative-value block was not found. Maybe already patched.")
else:
    file_path.write_text(code, encoding="utf-8")
    print("map_raw_excel_to_clean_mpps.py patched successfully.")
    print("Negative average/compound weights will now be saved as NULL in clean tables.")
    print("Original negative values remain preserved in excel_raw_cells.")