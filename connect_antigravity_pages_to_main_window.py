from pathlib import Path


file_path = Path("app/ui/main_window.py")

if not file_path.exists():
    raise FileNotFoundError("app/ui/main_window.py not found.")

backup_path = Path("app/ui/main_window_before_antigravity_page_connect.py")
backup_path.write_text(file_path.read_text(encoding="utf-8"), encoding="utf-8")

code = file_path.read_text(encoding="utf-8")


def replace_once(old: str, new: str, label: str) -> None:
    global code
    if old not in code:
        print(f"SKIP: {label} block not found. It may already be patched.")
        return
    code = code.replace(old, new, 1)
    print(f"OK: {label}")


replace_once(
    """from app.ui.bead_master_page import BeadMasterPage
""",
    """from app.ui.bead_master_page import BeadMasterPage
from app.ui.production_entry_page import ProductionEntryPage
from app.ui.band_master_page import BandMasterPage
from app.ui.capacity_master_page import CapacityMasterPage
from app.ui.oven_master_page import OvenMasterPage
from app.ui.material_requirement_page import MaterialRequirementPage
from app.ui.capacity_analysis_page import CapacityAnalysisPage
from app.ui.shipment_risk_page import ShipmentRiskPage
from app.ui.data_quality_warnings_page import DataQualityWarningsPage
from app.ui.raw_excel_viewer_page import RawExcelViewerPage
from app.ui.users_roles_page import UsersRolesPage
from app.ui.backup_restore_page import BackupRestorePage
from app.ui.audit_log_page import AuditLogPage
""",
    "imports",
)

replace_once(
    """    PRODUCT_MASTER_INDEX = 10
    STOCK_MASTER_INDEX = 11
    BOM_MASTER_INDEX = 12
    COMPOUND_MASTER_INDEX = 13
    BEAD_MASTER_INDEX = 14
    PLACEHOLDER_INDEX = 15
""",
    """    PRODUCT_MASTER_INDEX = 10
    STOCK_MASTER_INDEX = 11
    BOM_MASTER_INDEX = 12
    COMPOUND_MASTER_INDEX = 13
    BEAD_MASTER_INDEX = 14
    PRODUCTION_ENTRY_INDEX = 15
    BAND_MASTER_INDEX = 16
    CAPACITY_MASTER_INDEX = 17
    OVEN_MASTER_INDEX = 18
    MATERIAL_REQUIREMENT_INDEX = 19
    CAPACITY_ANALYSIS_INDEX = 20
    SHIPMENT_RISK_INDEX = 21
    DATA_QUALITY_INDEX = 22
    RAW_EXCEL_VIEWER_INDEX = 23
    USERS_ROLES_INDEX = 24
    BACKUP_RESTORE_INDEX = 25
    AUDIT_LOG_INDEX = 26
    PLACEHOLDER_INDEX = 27
""",
    "page indexes",
)

replace_once(
    """        self._add_caption(layout, "Operations")
        self._add_nav_button(layout, "+   Customer / Shipment Demand", self.ORDER_ENTRY_INDEX)
        self._add_nav_button(layout, "▣   Daily Oven Schedule", self.SCHEDULE_INDEX)
        self._add_nav_button(layout, "↳   Shipment Management", self.SHIPMENT_DETAILS_INDEX)
""",
    """        self._add_caption(layout, "Operations")
        self._add_nav_button(layout, "+   Customer / Shipment Demand", self.ORDER_ENTRY_INDEX)
        self._add_nav_button(layout, "▣   Daily Production Entry", self.PRODUCTION_ENTRY_INDEX)
        self._add_nav_button(layout, "▣   Daily Oven Schedule", self.SCHEDULE_INDEX)
        self._add_nav_button(layout, "↳   Shipment Management", self.SHIPMENT_DETAILS_INDEX)
""",
    "sidebar operations production entry",
)

replace_once(
    """        self.compound_master_page = CompoundMasterPage()
        self.bead_master_page = BeadMasterPage()
        self.placeholder_page = PlaceholderPage(
""",
    """        self.compound_master_page = CompoundMasterPage()
        self.bead_master_page = BeadMasterPage()

        self.production_entry_page = self._safe_create_page(ProductionEntryPage, self.current_user)
        self.band_master_page = self._safe_create_page(BandMasterPage)
        self.capacity_master_page = self._safe_create_page(CapacityMasterPage)
        self.oven_master_page = self._safe_create_page(OvenMasterPage)
        self.material_requirement_page = self._safe_create_page(MaterialRequirementPage)
        self.capacity_analysis_page = self._safe_create_page(CapacityAnalysisPage)
        self.shipment_risk_page = self._safe_create_page(ShipmentRiskPage)
        self.data_quality_page = self._safe_create_page(DataQualityWarningsPage)
        self.raw_excel_viewer_page = self._safe_create_page(RawExcelViewerPage)
        self.users_roles_page = self._safe_create_page(UsersRolesPage)
        self.backup_restore_page = self._safe_create_page(BackupRestorePage)
        self.audit_log_page = self._safe_create_page(AuditLogPage)

        self.placeholder_page = PlaceholderPage(
""",
    "create page objects",
)

replace_once(
    """        self.stack.addWidget(self._wrap_scroll(self.compound_master_page))
        self.stack.addWidget(self._wrap_scroll(self.bead_master_page))
        self.stack.addWidget(self._wrap_scroll(self.placeholder_page))
""",
    """        self.stack.addWidget(self._wrap_scroll(self.compound_master_page))
        self.stack.addWidget(self._wrap_scroll(self.bead_master_page))
        self.stack.addWidget(self._wrap_scroll(self.production_entry_page))
        self.stack.addWidget(self._wrap_scroll(self.band_master_page))
        self.stack.addWidget(self._wrap_scroll(self.capacity_master_page))
        self.stack.addWidget(self._wrap_scroll(self.oven_master_page))
        self.stack.addWidget(self._wrap_scroll(self.material_requirement_page))
        self.stack.addWidget(self._wrap_scroll(self.capacity_analysis_page))
        self.stack.addWidget(self._wrap_scroll(self.shipment_risk_page))
        self.stack.addWidget(self._wrap_scroll(self.data_quality_page))
        self.stack.addWidget(self._wrap_scroll(self.raw_excel_viewer_page))
        self.stack.addWidget(self._wrap_scroll(self.users_roles_page))
        self.stack.addWidget(self._wrap_scroll(self.backup_restore_page))
        self.stack.addWidget(self._wrap_scroll(self.audit_log_page))
        self.stack.addWidget(self._wrap_scroll(self.placeholder_page))
""",
    "add pages to stack",
)

replace_once(
    """    def _create_dashboard_page(self) -> DashboardPage:
""",
    """    def _safe_create_page(self, page_class, *args) -> QWidget:
        try:
            return page_class(*args)
        except TypeError:
            return page_class()

    def _create_dashboard_page(self) -> DashboardPage:
""",
    "safe page creation helper",
)

replace_once(
    """        nav_map = {
            self.DASHBOARD_INDEX: 0,
            self.ORDER_ENTRY_INDEX: 1,
            self.SCHEDULE_INDEX: 2,
            self.SHIPMENT_DETAILS_INDEX: 3,
            self.STOCK_PLANNING_INDEX: 4,
            self.MANAGER_OUTPUT_INDEX: 5,
            self.FACTORY_DATA_CENTER_INDEX: 6,
            self.TIRE_DETAILS_INDEX: 7,
            self.TIRE_STOCK_INDEX: 8,
            self.ADMIN_CONTROL_INDEX: 9,
        }
""",
    """        nav_map = {
            self.DASHBOARD_INDEX: 0,
            self.ORDER_ENTRY_INDEX: 1,
            self.PRODUCTION_ENTRY_INDEX: 2,
            self.SCHEDULE_INDEX: 3,
            self.SHIPMENT_DETAILS_INDEX: 4,
            self.STOCK_PLANNING_INDEX: 5,
            self.MANAGER_OUTPUT_INDEX: 6,
            self.FACTORY_DATA_CENTER_INDEX: 7,
            self.TIRE_DETAILS_INDEX: 8,
            self.TIRE_STOCK_INDEX: 9,
            self.ADMIN_CONTROL_INDEX: 10,
        }
""",
    "nav active map",
)

replace_once(
    """            self.COMPOUND_MASTER_INDEX: self.compound_master_page,
            self.BEAD_MASTER_INDEX: self.bead_master_page,
        }
""",
    """            self.COMPOUND_MASTER_INDEX: self.compound_master_page,
            self.BEAD_MASTER_INDEX: self.bead_master_page,
            self.PRODUCTION_ENTRY_INDEX: self.production_entry_page,
            self.BAND_MASTER_INDEX: self.band_master_page,
            self.CAPACITY_MASTER_INDEX: self.capacity_master_page,
            self.OVEN_MASTER_INDEX: self.oven_master_page,
            self.MATERIAL_REQUIREMENT_INDEX: self.material_requirement_page,
            self.CAPACITY_ANALYSIS_INDEX: self.capacity_analysis_page,
            self.SHIPMENT_RISK_INDEX: self.shipment_risk_page,
            self.DATA_QUALITY_INDEX: self.data_quality_page,
            self.RAW_EXCEL_VIEWER_INDEX: self.raw_excel_viewer_page,
            self.USERS_ROLES_INDEX: self.users_roles_page,
            self.BACKUP_RESTORE_INDEX: self.backup_restore_page,
            self.AUDIT_LOG_INDEX: self.audit_log_page,
        }
""",
    "refresh map",
)

module_replacements = [
    (
        """            "band_master": (
                self.PLACEHOLDER_INDEX,
                "Band Master",
                "Manage band code, band type and band usage per tyre.",
            ),
""",
        """            "band_master": (self.BAND_MASTER_INDEX, None, None),
""",
        "band master action",
    ),
    (
        """            "capacity_master": (
                self.PLACEHOLDER_INDEX,
                "Capacity Master",
                "Manage running moulds, per mould capacity and daily capacity.",
            ),
""",
        """            "capacity_master": (self.CAPACITY_MASTER_INDEX, None, None),
""",
        "capacity master action",
    ),
    (
        """            "oven_master": (
                self.PLACEHOLDER_INDEX,
                "Oven Master",
                "Manage oven codes, oven names and active/inactive machine status.",
            ),
""",
        """            "oven_master": (self.OVEN_MASTER_INDEX, None, None),
""",
        "oven master action",
    ),
    (
        """            "material_requirement": (
                self.PLACEHOLDER_INDEX,
                "Material Requirement",
                "View BOM, compound, bead and band requirement from production demand.",
            ),
""",
        """            "material_requirement": (self.MATERIAL_REQUIREMENT_INDEX, None, None),
""",
        "material requirement action",
    ),
    (
        """            "capacity_analysis": (
                self.PLACEHOLDER_INDEX,
                "Capacity Analysis",
                "Compare production requirement with mould and oven capacity.",
            ),
""",
        """            "capacity_analysis": (self.CAPACITY_ANALYSIS_INDEX, None, None),
""",
        "capacity analysis action",
    ),
    (
        """            "shipment_risk": (
                self.PLACEHOLDER_INDEX,
                "Shipment Risk",
                "View cannot-complete items, late risk, shortage reason and priority impact.",
            ),
""",
        """            "shipment_risk": (self.SHIPMENT_RISK_INDEX, None, None),
""",
        "shipment risk action",
    ),
    (
        """            "data_quality": (
                self.PLACEHOLDER_INDEX,
                "Data Quality Warnings",
                "Review missing weight, BOM, compound and capacity data issues.",
            ),
""",
        """            "data_quality": (self.DATA_QUALITY_INDEX, None, None),
""",
        "data quality action",
    ),
    (
        """            "raw_excel_viewer": (
                self.PLACEHOLDER_INDEX,
                "Raw Excel Data Viewer",
                "Trace app values back to workbook, sheet, row and cell.",
            ),
""",
        """            "raw_excel_viewer": (self.RAW_EXCEL_VIEWER_INDEX, None, None),
""",
        "raw excel viewer action",
    ),
    (
        """            "users_roles": (
                self.PLACEHOLDER_INDEX,
                "Users & Roles",
                "Manage admin, manager, operator and viewer access levels.",
            ),
""",
        """            "users_roles": (self.USERS_ROLES_INDEX, None, None),
""",
        "users roles action",
    ),
    (
        """            "backup_restore": (
                self.PLACEHOLDER_INDEX,
                "Backup / Restore",
                "Backup PostgreSQL data and restore previous safe snapshots.",
            ),
""",
        """            "backup_restore": (self.BACKUP_RESTORE_INDEX, None, None),
""",
        "backup restore action",
    ),
    (
        """            "audit_log": (
                self.PLACEHOLDER_INDEX,
                "Audit Log",
                "Track who changed master data, stock, demand and schedule records.",
            ),
""",
        """            "audit_log": (self.AUDIT_LOG_INDEX, None, None),
""",
        "audit log action",
    ),
]

for old, new, label in module_replacements:
    replace_once(old, new, label)

old_navigation_block = """        if index == self.STOCK_PLANNING_INDEX:
            self.navigate(self.STOCK_PLANNING_INDEX)
            return

        if index == self.PRODUCT_MASTER_INDEX:
            self.navigate(self.PRODUCT_MASTER_INDEX)
            return

        if index == self.STOCK_MASTER_INDEX:
            self.navigate(self.STOCK_MASTER_INDEX)
            return

        if index == self.BOM_MASTER_INDEX:
            self.navigate(self.BOM_MASTER_INDEX)
            return

        if index == self.COMPOUND_MASTER_INDEX:
            self.navigate(self.COMPOUND_MASTER_INDEX)
            return

        if index == self.BEAD_MASTER_INDEX:
            self.navigate(self.BEAD_MASTER_INDEX)
            return

        self.show_placeholder(title or "Module", subtitle or "This module will be connected soon.")
"""

new_navigation_block = """        if index != self.PLACEHOLDER_INDEX:
            self.navigate(index)
            return

        self.show_placeholder(title or "Module", subtitle or "This module will be connected soon.")
"""

replace_once(old_navigation_block, new_navigation_block, "generic module navigation")

file_path.write_text(code, encoding="utf-8")

print("")
print("main_window.py patched successfully.")
print(f"Backup saved: {backup_path}")
print("")
print("Next commands:")
print("python -m py_compile app\\ui\\main_window.py")
print("python run.py")
