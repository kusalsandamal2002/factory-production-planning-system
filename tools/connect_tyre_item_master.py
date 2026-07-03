from pathlib import Path
import re

main_path = Path("app/ui/main_window.py")
text = main_path.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)

# Import page.
if "from app.ui.tyre_item_master_page import TyreItemMasterPage" not in text:
    insert_at = None
    for i, line in enumerate(lines):
        if line.startswith("from app.ui."):
            insert_at = i + 1

    if insert_at is None:
        raise SystemExit("Could not find app.ui imports.")

    lines.insert(insert_at, "from app.ui.tyre_item_master_page import TyreItemMasterPage\n")

text = "".join(lines)

# Add index without shifting existing pages.
if "TYRE_ITEM_MASTER_INDEX" not in text:
    matches = list(re.finditer(r"^(?P<indent>\s+)(?P<name>[A-Z0-9_]+_INDEX)\s*=\s*(?P<num>\d+)\s*$", text, re.M))
    if not matches:
        raise SystemExit("Could not find page index constants.")

    max_index = max(int(match.group("num")) for match in matches)
    last = matches[-1]
    line_end = text.find("\n", last.end())
    indent = last.group("indent")
    text = text[:line_end + 1] + f"{indent}TYRE_ITEM_MASTER_INDEX = {max_index + 1}\n" + text[line_end + 1:]

# Create page instance before stack widgets are added.
if "self.tyre_item_master_page = TyreItemMasterPage()" not in text:
    first_stack = text.find("        self.stack.addWidget(")
    if first_stack == -1:
        raise SystemExit("Could not find stack.addWidget calls.")

    text = text[:first_stack] + "        self.tyre_item_master_page = TyreItemMasterPage()\n" + text[first_stack:]

# Add to stack at the end.
if "self.stack.addWidget(self._wrap_scroll(self.tyre_item_master_page))" not in text:
    lines = text.splitlines(keepends=True)
    stack_lines = [i for i, line in enumerate(lines) if "self.stack.addWidget(" in line]

    if not stack_lines:
        raise SystemExit("Could not find stack.addWidget calls.")

    lines.insert(stack_lines[-1] + 1, "        self.stack.addWidget(self._wrap_scroll(self.tyre_item_master_page))\n")
    text = "".join(lines)

# Route Master Data Hub card.
new_mapping = '"Tyre Item Master": self.TYRE_ITEM_MASTER_INDEX,'

if '"Tyre Item Master"' in text:
    text = re.sub(
        r'"Tyre Item Master"\s*:\s*self\.[A-Z0-9_]+,\n',
        f'{new_mapping}\n',
        text,
        count=1,
    )
else:
    text = text.replace(
        '"Factory Capacity": self.FACTORY_CAPACITY_INDEX,',
        '"Factory Capacity": self.FACTORY_CAPACITY_INDEX,\n                "Tyre Item Master": self.TYRE_ITEM_MASTER_INDEX,',
        1,
    )

# Keep sidebar selection on Master Data when this page is open.
if "self.TYRE_ITEM_MASTER_INDEX" in text and "TYRE_ITEM_MASTER_INDEX," not in text:
    text = text.replace(
        "self.FACTORY_CAPACITY_INDEX,",
        "self.FACTORY_CAPACITY_INDEX,\n            self.TYRE_ITEM_MASTER_INDEX,",
        1,
    )

main_path.write_text(text, encoding="utf-8")

# Ensure Master Data hub has the card if the file exists.
hub_path = Path("app/ui/master_data_hub_page.py")
if hub_path.exists():
    hub_text = hub_path.read_text(encoding="utf-8")

    if "Tyre Item Master" not in hub_text and "Factory Capacity" in hub_text:
        hub_text = hub_text.replace(
'''            (
                "Factory Capacity",
                "FACTORY CAPACITY",
                "Manage production lines, cavities, molds, casing and timing capacity.",
            ),''',
'''            (
                "Factory Capacity",
                "FACTORY CAPACITY",
                "Manage production lines, cavities, molds, casing and timing capacity.",
            ),
            (
                "Tyre Item Master",
                "TYRE ITEMS",
                "Maintain tyre item production rules, line mapping and curing times.",
            ),''',
        )

    hub_path.write_text(hub_text, encoding="utf-8")

print("Tyre Item Master connected.")
