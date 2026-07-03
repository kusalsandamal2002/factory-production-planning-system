from pathlib import Path
import re

factory_path = Path("app/ui/factory_capacity_page.py")
text = factory_path.read_text(encoding="utf-8")

# Update metric count from 4 to 5.
text = text.replace(
    '("4", "Capacity Modules", "Line, mold, casing and time masters")',
    '("5", "Capacity Modules", "Line, cavity, mold, casing and time masters")',
)

# Insert Cavities card after Production Lines card.
if '"Cavities",' not in text:
    old_block = '''            (
                "Production Lines",
                "LINE MASTER",
                "Maintain 200T, 400T, 800T and SuperSolid production line capacity.",
            ),
            (
                "Mold Master",
                "MOLD DATA",
                "Maintain mold availability, mold count and item compatibility.",
            ),'''

    new_block = '''            (
                "Production Lines",
                "LINE MASTER",
                "Maintain 200T, 400T, 800T and SuperSolid production line capacity.",
            ),
            (
                "Cavities",
                "CAVITY DATA",
                "Maintain cavity / press count for each production line.",
            ),
            (
                "Mold Master",
                "MOLD DATA",
                "Maintain mold availability, mold count and item compatibility.",
            ),'''

    if old_block not in text:
        raise SystemExit("Could not find Factory Capacity cards block.")

    text = text.replace(old_block, new_block)

factory_path.write_text(text, encoding="utf-8")


# Add navigation mapping in main_window.py.
main_path = Path("app/ui/main_window.py")
main_text = main_path.read_text(encoding="utf-8")

if '"Cavities": self.CAPACITY_MASTER_INDEX,' not in main_text:
    old_mapping = '''                "Production Lines": self.OVEN_MASTER_INDEX,
                "Mold Master": self.MOLD_MASTER_V2_INDEX,'''

    new_mapping = '''                "Production Lines": self.OVEN_MASTER_INDEX,
                "Cavities": self.CAPACITY_MASTER_INDEX,
                "Mold Master": self.MOLD_MASTER_V2_INDEX,'''

    if old_mapping not in main_text:
        raise SystemExit("Could not find Factory Capacity page_indexes mapping.")

    main_text = main_text.replace(old_mapping, new_mapping)

main_path.write_text(main_text, encoding="utf-8")

print("Cavities card added to Factory Capacity page.")
