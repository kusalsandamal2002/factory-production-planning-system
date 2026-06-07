from pathlib import Path
import re


file_path = Path("app/ui/details/shipment_details_page.py")

if not file_path.exists():
    raise FileNotFoundError("app/ui/details/shipment_details_page.py not found.")

code = file_path.read_text(encoding="utf-8")

backup_path = Path("app/ui/details/shipment_details_page_before_current_user_fix.py")
backup_path.write_text(code, encoding="utf-8")

# Remove current_user keyword arguments from shipment sub page constructors.
# Existing shipment sub pages do not accept current_user.
code = re.sub(
    r"\n\s*current_user\s*=\s*self\.current_user\s*,?",
    "",
    code,
)

file_path.write_text(code, encoding="utf-8")

print("shipment_details_page.py fixed successfully.")
print(f"Backup saved: {backup_path}")