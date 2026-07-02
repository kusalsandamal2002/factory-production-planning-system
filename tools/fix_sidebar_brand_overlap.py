from pathlib import Path
import re

path = Path("app/ui/main_window.py")
text = path.read_text(encoding="utf-8")

# Repair any broken multiline brand strings.
text = re.sub(
    r'brand\s*=\s*QLabel\("Factory Production\s*\r?\n\s*Planner"\)',
    'brand = QLabel("Factory Planner")',
    text,
)

text = re.sub(
    r'brand\s*=\s*QLabel\("Factory\s*\r?\n\s*Planner V2"\)',
    'brand = QLabel("Factory Planner")',
    text,
)

# Replace all known brand variants with a clean single-line brand.
text = text.replace('brand = QLabel("Factory Production\\\\nPlanner")', 'brand = QLabel("Factory Planner")')
text = text.replace('brand = QLabel("Factory\\\\nPlanner V2")', 'brand = QLabel("Factory Planner")')
text = text.replace('brand = QLabel("Factory Planning\\\\nSystem V2")', 'brand = QLabel("Factory Planner")')
text = text.replace('brand = QLabel("MPPS Factory\\\\nPlanner")', 'brand = QLabel("Factory Planner")')

# Keep professional subtitle.
text = text.replace(
    'subtitle = QLabel("Excel-Derived Stock, Material and Quantity Planning")',
    'subtitle = QLabel("Industrial Tyre Production Planning")',
)
text = text.replace(
    'subtitle = QLabel("Order-based Production Planning and Delivery Commitment")',
    'subtitle = QLabel("Industrial Tyre Production Planning")',
)

# Prevent title wrapping and reduce brand height.
text = text.replace("brand.setWordWrap(True)", "brand.setWordWrap(False)")
text = text.replace("brand.setMinimumHeight(105)", "brand.setMinimumHeight(42)")
text = text.replace("brand.setMinimumHeight(96)", "brand.setMinimumHeight(42)")
text = text.replace("brand.setMinimumHeight(88)", "brand.setMinimumHeight(42)")
text = text.replace("brand.setMinimumHeight(72)", "brand.setMinimumHeight(42)")

# Sidebar width.
text = text.replace("sidebar.setFixedWidth(380)", "sidebar.setFixedWidth(340)")
text = text.replace("sidebar.setFixedWidth(360)", "sidebar.setFixedWidth(340)")
text = text.replace("sidebar.setFixedWidth(320)", "sidebar.setFixedWidth(340)")

# Make injected sidebar styles calmer if present.
text = text.replace("font-size: 18pt;", "font-size: 16pt;")
text = text.replace("font-size: 20pt;", "font-size: 16pt;")
text = text.replace("font-size: 8.5pt;", "font-size: 8pt;")
text = text.replace("line-height: 1.05;", "line-height: 1.1;")
text = text.replace("line-height: 1.15;", "line-height: 1.1;")

path.write_text(text, encoding="utf-8")
print("Sidebar brand overlap fixed.")
