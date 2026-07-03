from pathlib import Path
import re

path = Path("app/ui/main_window.py")
text = path.read_text(encoding="utf-8")

# Remove any incorrectly inserted tyre item page instance lines.
text = re.sub(
    r'\n\s*self\.tyre_item_master_page\s*=\s*TyreItemMasterPage\(\)\s*\n',
    '\n',
    text,
)

# Ensure import exists.
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

# Ensure index exists.
if "TYRE_ITEM_MASTER_INDEX" not in text:
    matches = list(re.finditer(r"^(?P<indent>\s+)(?P<name>[A-Z0-9_]+_INDEX)\s*=\s*(?P<num>\d+)\s*$", text, re.M))
    if not matches:
        raise SystemExit("Could not find page index constants.")

    max_index = max(int(m.group("num")) for m in matches)
    last = matches[-1]
    line_end = text.find("\n", last.end())
    if line_end == -1:
        line_end = len(text)
    indent = last.group("indent")
    text = text[:line_end + 1] + f"{indent}TYRE_ITEM_MASTER_INDEX = {max_index + 1}\n" + text[line_end + 1:]

# Insert page instance directly before stack addWidget section.
# This avoids putting it before layout.addWidget(self.stack).
marker = "        self.stack.addWidget("
idx = text.find(marker)
if idx == -1:
    raise SystemExit("Could not find stack.addWidget section.")

text = text[:idx] + "        self.tyre_item_master_page = TyreItemMasterPage()\n" + text[idx:]

# Add stack widget at end if missing.
if "self.stack.addWidget(self._wrap_scroll(self.tyre_item_master_page))" not in text:
    lines = text.splitlines(keepends=True)
    stack_lines = [i for i, line in enumerate(lines) if "self.stack.addWidget(" in line]
    if not stack_lines:
        raise SystemExit("Could not find stack.addWidget calls.")

    lines.insert(stack_lines[-1] + 1, "        self.stack.addWidget(self._wrap_scroll(self.tyre_item_master_page))\n")
    text = "".join(lines)

# Route Master Data Hub card mapping.
if '"Tyre Item Master": self.TYRE_ITEM_MASTER_INDEX,' not in text:
    text = text.replace(
        '"Factory Capacity": self.FACTORY_CAPACITY_INDEX,',
        '"Factory Capacity": self.FACTORY_CAPACITY_INDEX,\n                "Tyre Item Master": self.TYRE_ITEM_MASTER_INDEX,',
        1,
    )

path.write_text(text, encoding="utf-8")
print("main_window.py repaired for Tyre Item Master.")
