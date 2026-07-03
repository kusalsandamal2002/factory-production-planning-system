from pathlib import Path
import re

path = Path("app/ui/main_window.py")
text = path.read_text(encoding="utf-8")

# Import TyreItemMasterPage.
if "from app.ui.tyre_item_master_page import TyreItemMasterPage" not in text:
    lines = text.splitlines(keepends=True)
    insert_at = None
    for i, line in enumerate(lines):
        if line.startswith("from app.ui."):
            insert_at = i + 1
    if insert_at is None:
        raise SystemExit("Could not find app.ui import section.")
    lines.insert(insert_at, "from app.ui.tyre_item_master_page import TyreItemMasterPage\n")
    text = "".join(lines)

# IMPORTANT:
# Use existing PRODUCT_MASTER_INDEX / product_master_page slot.
# Do NOT create TYRE_ITEM_MASTER_INDEX.
text = re.sub(
    r'\n\s*TYRE_ITEM_MASTER_INDEX\s*=\s*\d+\s*\n',
    '\n',
    text,
)

text = re.sub(
    r'\n\s*self\.tyre_item_master_page\s*=\s*TyreItemMasterPage\(\)\s*\n',
    '\n',
    text,
)

text = re.sub(
    r'\n\s*self\.stack\.addWidget\(self\._wrap_scroll\(self\.tyre_item_master_page\)\)\s*\n',
    '\n',
    text,
)

# Replace product master page assignment block with TyreItemMasterPage.
lines = text.splitlines(keepends=True)
start = None

for i, line in enumerate(lines):
    if "self.product_master_page" in line and "=" in line:
        start = i
        break

if start is None:
    raise SystemExit("Could not find self.product_master_page assignment.")

end = start + 1
paren_balance = lines[start].count("(") - lines[start].count(")")
while end < len(lines) and paren_balance > 0:
    paren_balance += lines[end].count("(") - lines[end].count(")")
    end += 1

lines[start:end] = ["        self.product_master_page = TyreItemMasterPage()\n"]
text = "".join(lines)

# Route Master Data Hub card to existing PRODUCT_MASTER_INDEX.
text = re.sub(
    r'"Tyre Item Master"\s*:\s*self\.[A-Z0-9_]+,',
    '"Tyre Item Master": self.PRODUCT_MASTER_INDEX,',
    text,
)

# Remove accidental references to self.TYRE_ITEM_MASTER_INDEX in sidebar-sync blocks.
text = text.replace("            self.TYRE_ITEM_MASTER_INDEX,\n", "")

path.write_text(text, encoding="utf-8")
print("Tyre Item Master connected through existing PRODUCT_MASTER_INDEX.")
