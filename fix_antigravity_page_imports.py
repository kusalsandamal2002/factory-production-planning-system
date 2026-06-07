from pathlib import Path
import re


file_path = Path("app/ui/main_window.py")

if not file_path.exists():
    raise FileNotFoundError("app/ui/main_window.py not found.")

code = file_path.read_text(encoding="utf-8")

backup_path = Path("app/ui/main_window_before_import_resolver_fix.py")
backup_path.write_text(code, encoding="utf-8")


# Add import_module import
if "from importlib import import_module" not in code:
    code = code.replace(
        "from __future__ import annotations\n\n",
        "from __future__ import annotations\n\nfrom importlib import import_module\n\n",
        1,
    )


# Remove direct imports that may fail because class names differ
modules_to_remove = [
    "production_entry_page",
    "band_master_page",
    "capacity_master_page",
    "oven_master_page",
    "material_requirement_page",
    "capacity_analysis_page",
    "shipment_risk_page",
    "data_quality_warnings_page",
    "raw_excel_viewer_page",
    "users_roles_page",
    "backup_restore_page",
    "audit_log_page",
]

for module_name in modules_to_remove:
    code = re.sub(
        rf"from app\.ui\.{module_name} import .*\n",
        "",
        code,
    )


resolver_block = r'''
def _resolve_page_class(module_path: str, candidates: list[str]):
    module = import_module(module_path)

    for candidate in candidates:
        page_class = getattr(module, candidate, None)
        if page_class is not None:
            return page_class

    available = [
        name
        for name in dir(module)
        if name.endswith("Page") or name.endswith("Widget")
    ]

    raise ImportError(
        f"No matching page class found in {module_path}. "
        f"Tried: {candidates}. Available: {available}"
    )


ProductionEntryPage = _resolve_page_class(
    "app.ui.production_entry_page",
    ["ProductionEntryPage", "DailyProductionEntryPage", "DailyProductionPage"],
)

BandMasterPage = _resolve_page_class(
    "app.ui.band_master_page",
    ["BandMasterPage", "BandPage"],
)

CapacityMasterPage = _resolve_page_class(
    "app.ui.capacity_master_page",
    ["CapacityMasterPage", "CapacityPage"],
)

OvenMasterPage = _resolve_page_class(
    "app.ui.oven_master_page",
    ["OvenMasterPage", "OvenPage", "MachineMasterPage"],
)

MaterialRequirementPage = _resolve_page_class(
    "app.ui.material_requirement_page",
    ["MaterialRequirementPage", "MaterialRequirementsPage"],
)

CapacityAnalysisPage = _resolve_page_class(
    "app.ui.capacity_analysis_page",
    ["CapacityAnalysisPage", "CapacityAnalyzerPage"],
)

ShipmentRiskPage = _resolve_page_class(
    "app.ui.shipment_risk_page",
    ["ShipmentRiskPage", "ShipmentRiskAnalysisPage"],
)

DataQualityWarningsPage = _resolve_page_class(
    "app.ui.data_quality_warnings_page",
    ["DataQualityWarningsPage", "DataQualityIssuesPage", "DataQualityPage"],
)

RawExcelViewerPage = _resolve_page_class(
    "app.ui.raw_excel_viewer_page",
    ["RawExcelViewerPage", "RawExcelDataViewerPage", "ExcelRawViewerPage"],
)

UsersRolesPage = _resolve_page_class(
    "app.ui.users_roles_page",
    ["UsersRolesPage", "UserRolesPage", "UsersAndRolesPage"],
)

BackupRestorePage = _resolve_page_class(
    "app.ui.backup_restore_page",
    ["BackupRestorePage", "BackupAndRestorePage"],
)

AuditLogPage = _resolve_page_class(
    "app.ui.audit_log_page",
    ["AuditLogPage", "AuditLogsPage"],
)
'''


if "_resolve_page_class(" not in code:
    marker = "from app.ui.tire_stock_page import TireStockPage\n"
    if marker not in code:
        raise RuntimeError("Could not find import marker in main_window.py.")

    code = code.replace(marker, marker + resolver_block + "\n", 1)


file_path.write_text(code, encoding="utf-8")

print("Antigravity page import resolver fixed successfully.")
print(f"Backup saved: {backup_path}")