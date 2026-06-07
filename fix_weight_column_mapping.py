from pathlib import Path


file_path = Path("map_raw_excel_to_clean_mpps.py")

if not file_path.exists():
    raise FileNotFoundError("map_raw_excel_to_clean_mpps.py not found.")

code = file_path.read_text(encoding="utf-8")

old = "MAX(CASE WHEN column_number = 208 THEN number_value END) AS average_weight"
new = "MAX(CASE WHEN column_number = 211 THEN number_value END) AS average_weight"

count = code.count(old)

if count == 0:
    print("Warning: old average weight mapping was not found. Maybe already patched.")
else:
    code = code.replace(old, new)
    file_path.write_text(code, encoding="utf-8")
    print(f"Average weight mapping patched successfully. Replaced {count} occurrence(s).")
    print("Average weight now maps from Stock sheet column 211 / HC instead of 208 / GZ.")