from pathlib import Path


file_path = Path("map_raw_excel_to_clean_mpps.py")

if not file_path.exists():
    raise FileNotFoundError("map_raw_excel_to_clean_mpps.py not found.")

code = file_path.read_text(encoding="utf-8")


old_1 = """        SELECT
            material_code,
            item_description,
            30,
            TRUE
        FROM valid_rows
        ON CONFLICT (tire_code)
"""

new_1 = """        SELECT
            material_code,
            item_description,
            30,
            TRUE
        FROM (
            SELECT DISTINCT ON (material_code)
                *
            FROM valid_rows
            ORDER BY material_code, row_number
        ) valid_rows
        ON CONFLICT (tire_code)
"""

old_2 = """        FROM valid_rows vr
        LEFT JOIN tire_types tt
"""

new_2 = """        FROM (
            SELECT DISTINCT ON (material_code)
                *
            FROM valid_rows
            ORDER BY material_code, row_number
        ) vr
        LEFT JOIN tire_types tt
"""

old_3 = """        SELECT
            NULLIF(TRIM(key_cell.display_value), '') AS item_code,
            COALESCE(running_moulds_cell.number_value, 0) AS running_moulds,
"""

new_3 = """        SELECT DISTINCT ON (NULLIF(TRIM(key_cell.display_value), ''))
            NULLIF(TRIM(key_cell.display_value), '') AS item_code,
            COALESCE(running_moulds_cell.number_value, 0) AS running_moulds,
"""

old_4 = """        SELECT
            'WARNING',
            'WEIGHT',
            source_workbook,
            source_sheet,
            source_row,
            material_code,
            'Average weight is missing or zero while production is required.'
        FROM mpps_stock_planning_view
        WHERE production_required_qty > 0
          AND COALESCE(average_weight, 0) <= 0;
"""

new_4 = """        SELECT
            'WARNING',
            'WEIGHT',
            si.source_workbook,
            si.source_sheet,
            si.source_row,
            spv.material_code,
            'Average weight is missing or zero while production is required.'
        FROM mpps_stock_planning_view spv
        JOIN mpps_stock_items si
            ON si.material_code = spv.material_code
        WHERE spv.production_required_qty > 0
          AND COALESCE(spv.average_weight, 0) <= 0;
"""


replacements = [
    (old_1, new_1),
    (old_2, new_2),
    (old_3, new_3),
    (old_4, new_4),
]

for old, new in replacements:
    if old not in code:
        print("Warning: expected block not found. Maybe already patched.")
    else:
        code = code.replace(old, new)

file_path.write_text(code, encoding="utf-8")

print("map_raw_excel_to_clean_mpps.py patched successfully.")
print("Duplicate material codes will now be deduped during clean mapping.")