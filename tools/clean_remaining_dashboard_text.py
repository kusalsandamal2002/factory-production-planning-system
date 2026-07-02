from pathlib import Path
import re

path = Path("app/ui/dashboard_page.py")
text = path.read_text(encoding="utf-8")

# Fix split/concatenated hint text in daily production panel.
text = re.sub(
    r'hint = QLabel\(\s*"Excel-derived production requirement, mould/category capacity, "\s*"and active historical oven compatibility\."\s*\)',
    'hint = QLabel("Order-based daily production plan using line, mold, casing, cavity and capacity data.")',
    text,
)

# Fix split/concatenated dashboard note.
text = re.sub(
    r'self\.summary_note = QLabel\(\s*"This dashboard uses quantity capacity\. Verified cycle-time data is "\s*"not available for minute-level utilization\."\s*\)',
    'self.summary_note = QLabel("This dashboard summarizes the current production planning position for the selected date.")',
    text,
)

# Fix capacity panel title that became awkward after earlier replacement.
text = text.replace(
    'title = QLabel("Selected Date Available Production Capacity Usage")',
    'title = QLabel("Production Capacity Usage")',
)

text = text.replace(
    'title = QLabel("Selected Date Quantity Capacity Usage")',
    'title = QLabel("Production Capacity Usage")',
)

# Fix split/concatenated capacity hint.
text = re.sub(
    r'hint = QLabel\(\s*"Planned quantity compared with relevant available mould/category "\s*"capacity for materials requiring production\."\s*\)',
    'hint = QLabel("Planned production quantity compared with available line, mold and cavity capacity.")',
    text,
)

# Clean remaining visible wording.
text = text.replace("mould/category", "line, mold and cavity")
text = text.replace("Excel-derived", "Order-based")
text = text.replace("Quantity-Based", "Production")
text = text.replace("Ovens", "Press / Cavities")

path.write_text(text, encoding="utf-8")
print("Remaining dashboard wording cleaned.")
