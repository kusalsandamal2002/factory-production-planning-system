from pathlib import Path

path = Path("app/ui/dashboard_page.py")
text = path.read_text(encoding="utf-8")

replacements = {
    "Open details": "View details",

    "Active Shipment Demands": "Customer Orders",
    "MPPS demand rows currently included in planning": "Orders currently included in production planning",

    "Production Required Items": "Production Orders",
    "Materials with a stock shortage for the selected date": "Items requiring production after stock verification",

    "Production Required Qty": "Required Production Qty",
    "Total quantity required after available stock": "Total quantity to be produced after stock check",

    "Planning Warnings": "Planning Alerts",
    "Missing due date, weight, capacity, or compatibility warnings": "Orders or items needing planning attention",

    "Selected Date Quantity Plan": "Daily Production Plan",
    "Excel-derived production requirement, mould/category capacity, and active historical oven compatibility.": (
        "Order-based production plan using line, mold, casing, cavity and capacity data."
    ),

    "Selected Date Planned Qty": "Planned Qty",
    "Quantity Capacity": "Available Production Capacity",
    "Capacity Usage": "Capacity Usage",
    "Active Ovens": "Active Press / Cavities",
    "Quantity-Based Plan Status": "Plan Status",

    "This dashboard uses quantity capacity. Verified cycle-time data is not available for minute-level utilization.": (
        "This dashboard summarizes the current production planning position for the selected date."
    ),

    "Selected Date Quantity Capacity Usage": "Production Capacity Usage",
    "Planned quantity compared with relevant available mould/category capacity for materials requiring production.": (
        "Planned production quantity compared with available line, mold and cavity capacity."
    ),
}

for old, new in replacements.items():
    text = text.replace(old, new)

path.write_text(text, encoding="utf-8")
print("Dashboard wording updated for production planning.")
