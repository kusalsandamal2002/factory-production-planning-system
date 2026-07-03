from pathlib import Path
import re

main_path = Path("app/ui/main_window.py")
text = main_path.read_text(encoding="utf-8")
lines = text.splitlines(keepends=True)

# Import CavitiesMasterPage.
if "from app.ui.cavities_master_page import CavitiesMasterPage" not in text:
    insert_at = None
    for i, line in enumerate(lines):
        if line.startswith("from app.ui."):
            insert_at = i + 1

    if insert_at is None:
        raise SystemExit("Could not locate app.ui imports.")

    lines.insert(insert_at, "from app.ui.cavities_master_page import CavitiesMasterPage\n")

text = "".join(lines)

# Add CAVITIES_MASTER_INDEX without shifting existing indexes.
if "CAVITIES_MASTER_INDEX" not in text:
    matches = list(re.finditer(r"^(?P<indent>\s+)(?P<name>[A-Z0-9_]+_INDEX)\s*=\s*(?P<num>\d+)\s*$", text, re.M))
    if not matches:
        raise SystemExit("Could not find page index constants.")

    max_index = max(int(match.group("num")) for match in matches)
    last_match = matches[-1]
    line_end = text.find("\n", last_match.end())
    if line_end == -1:
        line_end = len(text)

    indent = last_match.group("indent")
    text = text[:line_end + 1] + f"{indent}CAVITIES_MASTER_INDEX = {max_index + 1}\n" + text[line_end + 1:]

lines = text.splitlines(keepends=True)

# Add self.cavities_master_page assignment after factory_capacity_page assignment.
if "self.cavities_master_page = CavitiesMasterPage()" not in text:
    insert_at = None
    for i, line in enumerate(lines):
        if "self.factory_capacity_page = FactoryCapacityPage(" in line:
            balance = line.count("(") - line.count(")")
            j = i + 1
            while j < len(lines) and balance > 0:
                balance += lines[j].count("(") - lines[j].count(")")
                j += 1
            insert_at = j
            break

    if insert_at is None:
        raise SystemExit("Could not find factory_capacity_page assignment.")

    lines.insert(insert_at, "\n        self.cavities_master_page = CavitiesMasterPage()\n")

text = "".join(lines)

# Update Factory Capacity page mapping: Cavities should open Cavities Master, not Capacity / Time Master.
text = text.replace(
    '"Cavities": self.CAPACITY_MASTER_INDEX,',
    '"Cavities": self.CAVITIES_MASTER_INDEX,',
)

# If Cavities mapping does not exist, add it after Production Lines mapping.
if '"Cavities": self.CAVITIES_MASTER_INDEX,' not in text:
    text = text.replace(
        '"Production Lines": self.OVEN_MASTER_INDEX,',
        '"Production Lines": self.OVEN_MASTER_INDEX,\n                "Cavities": self.CAVITIES_MASTER_INDEX,',
        1,
    )

# Add page to stack at the end.
if "self.stack.addWidget(self._wrap_scroll(self.cavities_master_page))" not in text:
    lines = text.splitlines(keepends=True)
    stack_lines = [i for i, line in enumerate(lines) if "self.stack.addWidget(" in line]

    if not stack_lines:
        raise SystemExit("Could not find stack.addWidget calls.")

    lines.insert(stack_lines[-1] + 1, "        self.stack.addWidget(self._wrap_scroll(self.cavities_master_page))\n")
    text = "".join(lines)

main_path.write_text(text, encoding="utf-8")


# Ensure Factory Capacity page has Cavities card.
factory_path = Path("app/ui/factory_capacity_page.py")
factory_text = factory_path.read_text(encoding="utf-8")

factory_text = factory_text.replace(
    '("4", "Capacity Modules", "Line, mold, casing and time masters")',
    '("5", "Capacity Modules", "Line, cavity, mold, casing and time masters")',
)

if '"Cavities",' not in factory_text:
    factory_text = factory_text.replace(
'''            (
                "Production Lines",
                "LINE MASTER",
                "Maintain 200T, 400T, 800T and SuperSolid production line capacity.",
            ),
            (
                "Mold Master",
                "MOLD DATA",
                "Maintain mold availability, mold count and item compatibility.",
            ),''',
'''            (
                "Production Lines",
                "LINE MASTER",
                "Maintain 200T, 400T, 800T and SuperSolid production line capacity.",
            ),
            (
                "Cavities",
                "CAVITY DATA",
                "View and update each cavity by active, breakdown, used and free status.",
            ),
            (
                "Mold Master",
                "MOLD DATA",
                "Maintain mold availability, mold count and item compatibility.",
            ),''',
    )

factory_path.write_text(factory_text, encoding="utf-8")

print("Dedicated Cavities Master page connected.")
