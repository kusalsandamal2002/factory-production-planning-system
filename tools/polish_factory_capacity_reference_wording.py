from pathlib import Path

path = Path("app/ui/factory_capacity_page.py")
text = path.read_text(encoding="utf-8")

replacements = {
    '("86", "Active Cavities", "200T, 400T, 800T and SuperSolid")':
        '("102", "Cavity Positions", "Factory oven / press positions")',

    '"Manage operational capacity master data used for shipment receive date calculation, production scheduling and line loading."':
        '"Manage factory capacity master data used for shipment receive date calculation, production scheduling and line loading."',

    '"Maintain 200T, 400T, 800T and SuperSolid production line capacity."':
        '"Maintain factory production line groups from the oven sheet reference."',

    '"Maintain cavity / press count for each production line."':
        '"Maintain cavity and press positions, breakdown status, assignment and availability."',

    '"Maintain mold availability, mold count and item compatibility."':
        '"Maintain mold availability, mold count and tyre item compatibility."',

    '"Maintain cavity capacity, production time, curing time and shift parameters."':
        '"Maintain production time, curing time, shift parameters and capacity rules."',

    '("5", "Capacity Modules", "Line, cavity, mold, casing and time masters")':
        '("5", "Capacity Modules", "Line, cavity, mold, casing and time masters")',
}

for old, new in replacements.items():
    if old in text:
        text = text.replace(old, new)

path.write_text(text, encoding="utf-8")
print("Factory Capacity wording polished for reference-based capacity setup.")
