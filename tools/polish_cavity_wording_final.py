from pathlib import Path

path = Path("app/ui/cavities_master_page.py")
text = path.read_text(encoding="utf-8")

text = text.replace('("active", "Active", "Operational")', '("active", "Operational", "Working cavities")')
text = text.replace('"Load Status"', '"Availability"')
text = text.replace('load_label = QLabel("Assigned" if assigned_item else "Free")', 'load_label = QLabel("Assigned" if assigned_item else "Available")')
text = text.replace('Active + no assigned tyre item = Free.', 'Active + no assigned tyre item = Available.')

path.write_text(text, encoding="utf-8")
print("Final cavity wording polish applied.")
