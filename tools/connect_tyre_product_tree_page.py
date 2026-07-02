from pathlib import Path
import re

path = Path("app/ui/main_window.py")
text = path.read_text(encoding="utf-8")

import_line = "from app.ui.tire_stock_page import TireStockPage\n"
new_import = import_line + "from app.ui.tyre_product_tree_page import TyreProductTreePage\n"

if "from app.ui.tyre_product_tree_page import TyreProductTreePage" not in text:
    if import_line not in text:
        raise SystemExit("Could not find TireStockPage import line.")
    text = text.replace(import_line, new_import)

placeholder_pattern = re.compile(
    r'\s*self\.tyre_product_tree_page = PlaceholderPage\(\s*'
    r'"Tyre Product Tree Master",\s*'
    r'"Manage Resilient, Press-On and Cured-On tyre category rules, grades, layers, speed types and colours\.",\s*'
    r'\)',
    re.MULTILINE,
)

if "self.tyre_product_tree_page = TyreProductTreePage()" not in text:
    text, count = placeholder_pattern.subn(
        '\n        self.tyre_product_tree_page = TyreProductTreePage()',
        text,
    )

    if count != 1:
        raise SystemExit(f"Could not replace tyre product tree placeholder. Replacements: {count}")

path.write_text(text, encoding="utf-8")
print("Tyre Product Tree page connected.")
