from __future__ import annotations
from time import perf_counter
from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import QApplication


from importlib import import_module

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import settings
from app.database import get_session
from app.models import Role, User
from app.ui.bead_master_page import BeadMasterPage
from app.ui.bom_master_page import BomMasterPage
from app.ui.compound_master_page import CompoundMasterPage
from app.ui.dashboard_page import DashboardPage
from app.ui.module_hub_page import (
    create_admin_control_page,
    create_factory_data_center_page,
    create_manager_output_page,
)
from app.ui.monthly_stock_count_page import MonthlyStockCountPage
from app.ui.order_entry_page import OrderEntryPage
from app.ui.shipment_orders_page import ShipmentDetailsPage
from app.ui.product_master_page import ProductMasterPage
from app.ui.production_line_master_page import ProductionLineMasterPage
from app.ui.schedule_page import SchedulePage
from app.ui.stock_master_page import StockMasterPage
from app.ui.daily_stock_page import DailyStockPage
from app.ui.stock_planning_page import StockPlanningPage
from app.ui.tire_stock_page import TireStockPage
from app.ui.tyre_product_tree_page import TyreProductTreePage
from app.ui.master_data_hub_page import MasterDataHubPage
from app.ui.factory_capacity_page import FactoryCapacityPage
from app.ui.cavities_master_page import CavitiesMasterPage
from app.ui.mold_master_page import MoldMasterPage
from app.ui.casing_master_page import CasingMasterPage
from app.ui.tyre_item_master_page import TyreItemMasterPage
from app.ui.admin_database_viewer_page import AdminDatabaseViewerPage
from app.ui.factory_out_date_logic_page import FactoryOutDateLogicPage


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


class PlaceholderPage(QWidget):
    def __init__(self, title: str, subtitle: str):
        super().__init__()

        self.setStyleSheet(
            """
            QFrame#Card {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 18px;
            }

            QLabel#Title {
                color: #0f172a;
                font-size: 22pt;
                font-weight: 950;
            }

            QLabel#Subtitle {
                color: #64748b;
                font-size: 10pt;
                font-weight: 650;
            }

            QLabel#Badge {
                background: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 12px;
                padding: 8px 14px;
                font-size: 9.5pt;
                font-weight: 900;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(18)

        card = QFrame()
        card.setObjectName("Card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("Title")
        title_label.setWordWrap(True)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("Subtitle")
        subtitle_label.setWordWrap(True)

        badge = QLabel("This module will be connected in the next development step.")
        badge.setObjectName("Badge")
        badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addSpacing(8)
        layout.addWidget(badge)
        layout.addStretch()

        root.addWidget(card)
        root.addStretch()


class MainWindow(QMainWindow):
    DASHBOARD_INDEX = 0
    ORDER_ENTRY_INDEX = 1
    SCHEDULE_INDEX = 2
    STOCK_PLANNING_INDEX = 3
    SHIPMENT_DETAILS_INDEX = 4
    TIRE_DETAILS_INDEX = 5
    TIRE_STOCK_INDEX = 6
    FACTORY_DATA_CENTER_INDEX = 7
    MANAGER_OUTPUT_INDEX = 8
    ADMIN_CONTROL_INDEX = 9
    PRODUCT_MASTER_INDEX = 10
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
    MONTHLY_STOCK_COUNT_INDEX = 27
    PLACEHOLDER_INDEX = 28

    TYRE_PRODUCT_TREE_INDEX = 29
    MOLD_MASTER_V2_INDEX = 30
    CASING_MASTER_V2_INDEX = 31
    DELIVERY_DATE_INDEX = 32
    DAILY_PLAN_INDEX = 33
    SHIFT_PLAN_INDEX = 34
    REPORTS_INDEX = 35

    FACTORY_CAPACITY_INDEX = 36

    CAVITIES_MASTER_INDEX = 37
    DAILY_STOCK_INDEX = 38
    MONTHLY_STOCK_MANAGER_ROLE = "Monthly Stock Manager"
    MONTHLY_STOCK_VIEWER_ROLE = "Monthly Stock Viewer"

    def __init__(self, current_user: User):
        super().__init__()
        self._navigation_history: list[int] = []
        self._navigation_back_in_progress = False
        self._last_stack_index = -1

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)


        self.current_user = current_user
        self.monthly_stock_only_mode = self._is_monthly_stock_only_role()
        self.monthly_stock_viewer_mode = self._is_monthly_stock_viewer_role()
        self.nav_buttons: list[QPushButton] = []
        self.placeholder_page: PlaceholderPage | None = None

        self.setWindowTitle(settings.app_name)
        self.resize(1600, 920)
        self.setMinimumSize(1250, 760)
        self.setStyleSheet(self.styleSheet() + """
            QLabel#BrandTitle {
                color: #ffffff;
                font-size: 13pt;
                font-weight: 950;
            }

            QLabel#BrandSubtitle {
                color: #9fb0c7;
                font-size: 7.4pt;
                font-weight: 750;
            }

            QPushButton#NavButton {
                min-height: 34px;
                padding: 7px 12px;
                text-align: left;
                font-size: 9pt;
            }

            QLabel#SidebarCaption {
                margin-top: 8px;
                margin-bottom: 4px;
                font-size: 7.5pt;
                letter-spacing: 1px;
            }
        
            QLabel#SidebarUserRole {
                color: #e5eefb;
                font-size: 8.2pt;
                font-weight: 900;
                padding: 4px 8px 0px 8px;
            }

            QLabel#SidebarDbStatus {
                color: #38bdf8;
                background: #082f49;
                border: 1px solid #075985;
                border-radius: 9px;
                padding: 6px 8px;
                font-size: 7.8pt;
                font-weight: 900;
            }
""")


        shell = QFrame()
        shell.setObjectName("AppShell")

        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.setCentralWidget(shell)

        shell_layout.addWidget(self._build_sidebar())
        shell_layout.addWidget(self._build_content(), 1)

        self._startup_target_index = (
            self.MONTHLY_STOCK_COUNT_INDEX
            if self.monthly_stock_only_mode
            else self.DASHBOARD_INDEX
        )

        if self.monthly_stock_only_mode:
            self.stack.setCurrentIndex(0)
        else:
            self.stack.setCurrentIndex(
                self.DASHBOARD_INDEX
            )
            self._sync_sidebar_selection(
                self.DASHBOARD_INDEX
            )

        QTimer.singleShot(
            50,
            lambda: self.navigate(
                self._startup_target_index
            ),
        )

    def _current_role_name(self) -> str:
        try:
            role = getattr(self.current_user, "role", None)

            if role is not None:
                role_name = str(getattr(role, "role_name", "") or "").strip()
                if role_name:
                    return role_name
        except Exception:
            pass

        role_id = getattr(self.current_user, "role_id", None)
        if role_id is None:
            return ""

        try:
            with get_session() as session:
                role = session.get(Role, role_id)
                if role is None:
                    return ""
                return str(role.role_name or "").strip()
        except Exception:
            return ""

    def _is_monthly_stock_manager_role(self) -> bool:
        return self._current_role_name().lower() == self.MONTHLY_STOCK_MANAGER_ROLE.lower()

    def _is_monthly_stock_viewer_role(self) -> bool:
        return self._current_role_name().lower() == self.MONTHLY_STOCK_VIEWER_ROLE.lower()

    def _is_monthly_stock_only_role(self) -> bool:
        return self._is_monthly_stock_manager_role() or self._is_monthly_stock_viewer_role()

    def _build_sidebar(self) -> QFrame:
        if self.monthly_stock_only_mode:
            return self._build_monthly_stock_only_sidebar()

        sidebar = QFrame()

        sidebar.setObjectName("Sidebar")
        sidebar.setStyleSheet("""
            QFrame#Sidebar {
                background: #0f172a;
                border: none;
            }

            QFrame#Sidebar QLabel {
                color: #e5edf8;
                background: transparent;
            }

            QFrame#Sidebar QPushButton {
                background: transparent;
                color: #f8fafc;
                border: none;
                border-radius: 10px;
                padding: 10px 12px;
                text-align: left;
                font-size: 9pt;
                font-weight: 800;
            }

            QFrame#Sidebar QPushButton:hover {
                background: #1e293b;
                color: #ffffff;
            }

            QFrame#Sidebar QPushButton:checked {
                background: #2563eb;
                color: #ffffff;
            }

            QFrame#Sidebar QPushButton:disabled {
                background: transparent;
                color: #64748b;
            }
        """)
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 10)
        layout.setSpacing(4)

        brand = QLabel("Factory Production\nPlanner")
        brand.setObjectName("BrandTitle")
        brand.setWordWrap(False)
        brand.setMinimumHeight(42)
        brand.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        subtitle = QLabel("Industrial Tyre Production Planning")
        subtitle.setObjectName("BrandSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setMinimumHeight(34)

        layout.addWidget(brand)
        layout.addWidget(subtitle)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background:#1e293b; max-height:1px;")

        layout.addSpacing(10)
        layout.addWidget(divider)
        layout.addSpacing(8)

        self._add_caption(layout, "Dashboard")
        self._add_nav_button(layout, "Dashboard", self.DASHBOARD_INDEX)

        layout.addSpacing(8)

        self._add_caption(layout, "Orders")
        self._add_nav_button(layout, "Shipment Orders", self.ORDER_ENTRY_INDEX)
        self._add_nav_button(layout, "Shipment Details", self.SHIPMENT_DETAILS_INDEX)

        layout.addSpacing(8)

        self._add_caption(layout, "Data")
        self._add_nav_button(layout, "Master Data", self.TYRE_PRODUCT_TREE_INDEX)

        self._add_caption(layout, "Planning")
        self._add_nav_button(layout, "Production Planning", self.SCHEDULE_INDEX)
        self._add_nav_button(layout, "Delivery Date Calculation", self.DELIVERY_DATE_INDEX)
        self._add_nav_button(layout, "Daily Plan", self.DAILY_PLAN_INDEX)
        self._add_nav_button(layout, "Shift Plan", self.SHIFT_PLAN_INDEX)
        self._add_nav_button(layout, "Material Requirement", self.MATERIAL_REQUIREMENT_INDEX)

        layout.addSpacing(8)

        self._add_caption(layout, "Reports & Admin")
        self._add_nav_button(layout, "Reports", self.REPORTS_INDEX)
        self._add_nav_button(layout, "Admin Settings", self.ADMIN_CONTROL_INDEX)
        self._add_nav_button(layout, "Legacy Excel Import", self.RAW_EXCEL_VIEWER_INDEX)

        layout.addStretch()
        layout.addWidget(self._build_connection_badge())

        return sidebar

    def _build_monthly_stock_only_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(10)

        brand = QLabel("Factory Production\nPlanner")
        brand.setObjectName("BrandTitle")
        brand.setWordWrap(False)
        brand.setMinimumHeight(42)
        brand.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        subtitle = QLabel("Monthly Stock Count")
        subtitle.setObjectName("BrandSubtitle")
        subtitle.setWordWrap(True)
        subtitle.setMinimumHeight(34)

        layout.addWidget(brand)
        layout.addWidget(subtitle)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background:#1e293b; max-height:1px;")

        layout.addSpacing(10)
        layout.addWidget(divider)
        layout.addSpacing(8)

        self._add_nav_button(layout, "Monthly Stock Count", self.MONTHLY_STOCK_COUNT_INDEX)

        layout.addStretch()

        if not self.monthly_stock_viewer_mode:
            layout.addWidget(self._build_connection_badge())

        return sidebar

    def _build_content(self) -> QFrame:
        content = QFrame()
        content.setObjectName("ContentArea")

        layout = QVBoxLayout(content)
        layout.setContentsMargins(
            22,
            22,
            22,
            22,
        )
        layout.setSpacing(0)

        self.stack = QStackedWidget()
        self._last_stack_index = (
            self.stack.currentIndex()
        )
        self.stack.currentChanged.connect(
            self._on_stack_changed
        )

        self._page_instances = {}
        self._page_factories = {}
        self._page_attributes = {}
        self._page_titles = {}
        self._loaded_page_indexes = set()
        self._page_load_times = {}

        if self.monthly_stock_only_mode:
            self.monthly_stock_count_page = None
            self._page_factories[0] = (
                lambda: MonthlyStockCountPage(
                    self.current_user
                )
            )
            self._page_attributes[0] = (
                "monthly_stock_count_page"
            )
            self._page_titles[0] = (
                "Monthly Stock Count"
            )
            self.stack.addWidget(
                self._loading_page(
                    "Monthly Stock Count"
                )
            )
            layout.addWidget(self.stack)
            return content

        definitions = [
            (
                self.DASHBOARD_INDEX,
                "dashboard_page",
                "Dashboard",
                self._create_dashboard_page,
            ),
            (
                self.ORDER_ENTRY_INDEX,
                "order_entry_page",
                "Shipment Orders",
                lambda: OrderEntryPage(
                    self.current_user,
                    on_shipment_saved=(
                        self.open_saved_shipment_details
                    ),
                ),
            ),
            (
                self.SCHEDULE_INDEX,
                "schedule_page",
                "Production Planning",
                lambda: SchedulePage(
                    self.current_user
                ),
            ),
            (
                self.STOCK_PLANNING_INDEX,
                "stock_planning_page",
                "Stock Planning",
                lambda: StockPlanningPage(
                    open_item_detail_callback=(
                        self.open_stock_item_detail
                    )
                ),
            ),
            (
                self.SHIPMENT_DETAILS_INDEX,
                "shipment_details_page",
                "Shipment Details",
                lambda: ShipmentDetailsPage(
                    self.current_user,
                    on_new_shipment=(
                        self.open_new_shipment_entry
                    ),
                ),
            ),
            (
                self.TIRE_DETAILS_INDEX,
                "tire_details_page",
                "Archived Legacy Module",
                lambda: PlaceholderPage(
                    "Archived Legacy Module",
                    (
                        "This archived module is not part "
                        "of the current MPPS workflow."
                    ),
                ),
            ),
            (
                self.TIRE_STOCK_INDEX,
                "tire_stock_page",
                "Final Tyre Stock",
                TireStockPage,
            ),
            (
                self.FACTORY_DATA_CENTER_INDEX,
                "factory_data_center_page",
                "Factory Data Center",
                lambda: create_factory_data_center_page(
                    open_callback=(
                        self.open_module_action
                    )
                ),
            ),
            (
                self.MANAGER_OUTPUT_INDEX,
                "manager_output_page",
                "Manager Output",
                lambda: create_manager_output_page(
                    open_callback=(
                        self.open_module_action
                    )
                ),
            ),
            (
                self.ADMIN_CONTROL_INDEX,
                "admin_control_page",
                "Admin Control",
                lambda: create_admin_control_page(
                    open_callback=(
                        self.open_module_action
                    )
                ),
            ),
            (
                self.PRODUCT_MASTER_INDEX,
                "product_master_page",
                "Tyre Item Master",
                TyreItemMasterPage,
            ),
            (
                self.STOCK_MASTER_INDEX,
                "stock_master_page",
                "Stock Master",
                StockMasterPage,
            ),
            (
                self.BOM_MASTER_INDEX,
                "bom_master_page",
                "BOM Master",
                BomMasterPage,
            ),
            (
                self.COMPOUND_MASTER_INDEX,
                "compound_master_page",
                "Compound Master",
                CompoundMasterPage,
            ),
            (
                self.BEAD_MASTER_INDEX,
                "bead_master_page",
                "Bead Master",
                BeadMasterPage,
            ),
            (
                self.PRODUCTION_ENTRY_INDEX,
                "production_entry_page",
                "Archived Legacy Module",
                lambda: PlaceholderPage(
                    "Archived Legacy Module",
                    (
                        "This archived module is not part "
                        "of the current MPPS workflow."
                    ),
                ),
            ),
            (
                self.BAND_MASTER_INDEX,
                "band_master_page",
                "Band Master",
                lambda: self._safe_create_page(
                    BandMasterPage
                ),
            ),
            (
                self.CAPACITY_MASTER_INDEX,
                "capacity_master_page",
                "Capacity / Time Master",
                lambda: self._safe_create_page(
                    CapacityMasterPage
                ),
            ),
            (
                self.OVEN_MASTER_INDEX,
                "oven_master_page",
                "Production Lines",
                ProductionLineMasterPage,
            ),
            (
                self.MATERIAL_REQUIREMENT_INDEX,
                "material_requirement_page",
                "Material Requirement",
                lambda: self._safe_create_page(
                    MaterialRequirementPage
                ),
            ),
            (
                self.CAPACITY_ANALYSIS_INDEX,
                "capacity_analysis_page",
                "Capacity Analysis",
                lambda: self._safe_create_page(
                    CapacityAnalysisPage
                ),
            ),
            (
                self.SHIPMENT_RISK_INDEX,
                "shipment_risk_page",
                "Shipment Risk",
                lambda: self._safe_create_page(
                    ShipmentRiskPage
                ),
            ),
            (
                self.DATA_QUALITY_INDEX,
                "data_quality_page",
                "Data Quality",
                lambda: self._safe_create_page(
                    DataQualityWarningsPage
                ),
            ),
            (
                self.RAW_EXCEL_VIEWER_INDEX,
                "raw_excel_viewer_page",
                "Legacy Excel Import",
                lambda: self._safe_create_page(
                    RawExcelViewerPage
                ),
            ),
            (
                self.USERS_ROLES_INDEX,
                "users_roles_page",
                "Users & Roles",
                lambda: self._safe_create_page(
                    UsersRolesPage
                ),
            ),
            (
                self.BACKUP_RESTORE_INDEX,
                "backup_restore_page",
                "Backup & Restore",
                lambda: self._safe_create_page(
                    BackupRestorePage
                ),
            ),
            (
                self.AUDIT_LOG_INDEX,
                "audit_log_page",
                "Audit Log",
                lambda: self._safe_create_page(
                    AuditLogPage
                ),
            ),
            (
                self.MONTHLY_STOCK_COUNT_INDEX,
                "monthly_stock_count_page",
                "Monthly Stock Count",
                lambda: MonthlyStockCountPage(
                    self.current_user
                ),
            ),
            (
                self.PLACEHOLDER_INDEX,
                "placeholder_page",
                "Module",
                lambda: PlaceholderPage(
                    "Module",
                    (
                        "This module will be connected "
                        "in the next step."
                    ),
                ),
            ),
            (
                self.TYRE_PRODUCT_TREE_INDEX,
                "tyre_product_tree_page",
                "Master Data",
                lambda: MasterDataHubPage(
                    on_open_page=(
                        lambda index: self.navigate(index)
                    ),
                    page_indexes={
                        "Factory Capacity": (
                            self.FACTORY_CAPACITY_INDEX
                        ),
                        "Tyre Item Master": (
                            self.PRODUCT_MASTER_INDEX
                        ),
                        "Final Tyre Stock": (
                            self.STOCK_MASTER_INDEX
                        ),
                        "Daily Stock": (
                            self.DAILY_STOCK_INDEX
                        ),
                        "Legacy Excel Import": (
                            self.RAW_EXCEL_VIEWER_INDEX
                        ),
                    },
                ),
            ),
            (
                self.MOLD_MASTER_V2_INDEX,
                "mold_master_v2_page",
                "Mold Master",
                MoldMasterPage,
            ),
            (
                self.CASING_MASTER_V2_INDEX,
                "casing_master_v2_page",
                "Casing Master",
                CasingMasterPage,
            ),
            (
                self.DELIVERY_DATE_INDEX,
                "delivery_date_page",
                "Delivery Date Calculation",
                lambda: PlaceholderPage(
                    "Delivery Date Calculation",
                    (
                        "Calculate realistic customer "
                        "delivery dates using stock and "
                        "production capacity."
                    ),
                ),
            ),
            (
                self.DAILY_PLAN_INDEX,
                "daily_plan_page",
                "Daily Production Plan",
                lambda: PlaceholderPage(
                    "Daily Production Plan",
                    (
                        "Generate and manage day-wise "
                        "production plans."
                    ),
                ),
            ),
            (
                self.SHIFT_PLAN_INDEX,
                "shift_plan_page",
                "Day / Night Shift Plan",
                lambda: PlaceholderPage(
                    "Day / Night Shift Plan",
                    (
                        "Split production into day and "
                        "night shift targets."
                    ),
                ),
            ),
            (
                self.REPORTS_INDEX,
                "reports_page",
                "Reports",
                lambda: PlaceholderPage(
                    "Reports",
                    (
                        "View production, delivery and "
                        "capacity reports."
                    ),
                ),
            ),
            (
                self.FACTORY_CAPACITY_INDEX,
                "factory_capacity_page",
                "Factory Capacity",
                lambda: FactoryCapacityPage(
                    on_open_page=(
                        lambda index: self.navigate(index)
                    ),
                    on_back=(
                        lambda: self.navigate(
                            self.TYRE_PRODUCT_TREE_INDEX
                        )
                    ),
                    page_indexes={
                        "Production Lines": (
                            self.OVEN_MASTER_INDEX
                        ),
                        "Cavities": (
                            self.CAVITIES_MASTER_INDEX
                        ),
                        "Mold Master": (
                            self.MOLD_MASTER_V2_INDEX
                        ),
                        "Casing Master": (
                            self.CASING_MASTER_V2_INDEX
                        ),
                        "Capacity / Time Master": (
                            self.CAPACITY_MASTER_INDEX
                        ),
                    },
                ),
            ),
            (
                self.CAVITIES_MASTER_INDEX,
                "cavities_master_page",
                "Cavities Master",
                CavitiesMasterPage,
            ),
            (
                self.DAILY_STOCK_INDEX,
                "daily_stock_page",
                "Daily Stock",
                DailyStockPage,
            ),
        ]

        for (
            index,
            attribute,
            title,
            factory,
        ) in definitions:
            self._page_factories[index] = factory
            self._page_attributes[index] = attribute
            self._page_titles[index] = title
            setattr(
                self,
                attribute,
                None,
            )
            self.stack.addWidget(
                self._loading_page(title)
            )

        layout.addWidget(self.stack)
        return content

    def _loading_page(
        self,
        title: str,
    ) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(
            24,
            24,
            24,
            24,
        )

        card = QFrame()
        card.setStyleSheet(
            """
            QFrame {
                background: #ffffff;
                border: 1px solid #dbe4f0;
                border-radius: 18px;
            }
            """
        )
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(
            28,
            26,
            28,
            26,
        )
        card_layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            "color:#0f172a; font-size:20pt; "
            "font-weight:950;"
        )

        message = QLabel(
            "Loading this workspace only when it is "
            "needed. This keeps login and startup fast."
        )
        message.setWordWrap(True)
        message.setStyleSheet(
            "color:#64748b; font-weight:700;"
        )

        badge = QLabel(
            "LOADING WORKSPACE..."
        )
        badge.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        badge.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        badge.setStyleSheet(
            "background:#dbeafe; color:#1d4ed8; "
            "border:1px solid #bfdbfe; "
            "border-radius:10px; padding:8px 12px; "
            "font-weight:950;"
        )

        card_layout.addWidget(title_label)
        card_layout.addWidget(message)
        card_layout.addSpacing(6)
        card_layout.addWidget(badge)
        card_layout.addStretch()

        layout.addWidget(card)
        layout.addStretch()
        return page

    def _ensure_page_loaded(
        self,
        index: int,
    ) -> tuple[QWidget | None, bool]:
        stack_index = (
            0
            if self.monthly_stock_only_mode
            else index
        )

        if stack_index in self._loaded_page_indexes:
            return (
                self._page_instances.get(
                    stack_index
                ),
                False,
            )

        factory = self._page_factories.get(
            stack_index
        )
        if factory is None:
            return None, False

        title = self._page_titles.get(
            stack_index,
            "Workspace",
        )
        placeholder = self.stack.widget(
            stack_index
        )

        self.stack.setCurrentIndex(
            stack_index
        )
        QApplication.setOverrideCursor(
            Qt.CursorShape.WaitCursor
        )
        QApplication.processEvents()

        started = perf_counter()

        try:
            page = factory()
            container = self._wrap_scroll(
                page
            )

            self.stack.removeWidget(
                placeholder
            )
            self.stack.insertWidget(
                stack_index,
                container,
            )
            placeholder.deleteLater()

            attribute = self._page_attributes.get(
                stack_index
            )
            if attribute:
                setattr(
                    self,
                    attribute,
                    page,
                )

            self._page_instances[
                stack_index
            ] = page
            self._loaded_page_indexes.add(
                stack_index
            )

            elapsed = (
                perf_counter()
                - started
            )
            self._page_load_times[
                stack_index
            ] = elapsed

            print(
                "[MPPS STARTUP] Loaded "
                f"{title} in {elapsed:.2f}s",
                flush=True,
            )

            self.stack.setCurrentIndex(
                stack_index
            )
            return page, True

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Workspace Load Failed",
                (
                    f"{title} could not be loaded."
                    f"\n\nReason: {exc}"
                ),
            )
            return None, False

        finally:
            QApplication.restoreOverrideCursor()

    def _safe_create_page(self, page_class, *args) -> QWidget:
        try:
            return page_class(*args)
        except TypeError:
            return page_class()

    def _create_dashboard_page(self) -> DashboardPage:
        return DashboardPage(
            self.open_shipment_details_page,
            self.open_shipment_details_page,
            self.open_stock_planning_page,
            self.open_stock_planning_page,
        )

    def _wrap_scroll(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(widget)
        return scroll

    def _add_caption(self, layout, text):
        caption = QLabel(text.upper())
        caption.setObjectName("SidebarCaption")
        caption.setFixedHeight(24)
        caption.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        caption.setStyleSheet("""
            QLabel#SidebarCaption {
                color: #8ea0ba;
                background: transparent;
                font-size: 7.5pt;
                font-weight: 900;
                padding-left: 8px;
                padding-top: 2px;
                padding-bottom: 2px;
            }
        """)
        layout.addWidget(caption)
        return caption


    def _add_nav_button(self, layout, text, index):
        button = QPushButton(text)
        button.setObjectName("SidebarNavButton")
        button.setCheckable(True)
        button.setFixedHeight(34)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet("""
            QPushButton#SidebarNavButton {
                background: transparent;
                color: #e5eefb;
                border: none;
                border-radius: 9px;
                padding: 7px 10px;
                text-align: left;
                font-size: 8.5pt;
                font-weight: 800;
            }

            QPushButton#SidebarNavButton:hover {
                background: #172235;
                color: #ffffff;
            }

            QPushButton#SidebarNavButton:checked {
                background: #2563eb;
                color: #ffffff;
                font-weight: 950;
            }
        """)

        if not hasattr(self, "nav_buttons_by_index"):
            self.nav_buttons_by_index = {}

        self.nav_buttons_by_index.setdefault(index, []).append(button)
        button.clicked.connect(lambda checked=False, page_index=index: self.navigate(page_index))
        layout.addWidget(button)
        return button


    def _build_user_box(self) -> QFrame:
        box = QFrame()
        box.setObjectName("UserBox")

        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        role_name = "-"
        if self.current_user.role is not None:
            role_name = self.current_user.role.role_name

        full_name = QLabel(self.current_user.full_name)
        full_name.setObjectName("UserName")
        full_name.setWordWrap(True)

        role = QLabel(role_name)
        role.setObjectName("UserRole")
        role.setWordWrap(True)

        layout.addWidget(full_name)
        layout.addWidget(role)

        return box

    def _build_connection_badge(self) -> QLabel:
        badge = QLabel("PostgreSQL Connected")
        badge.setObjectName("SidebarDbStatus")
        badge.setObjectName("ConnectionBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return badge



    def _on_stack_changed(self, index: int) -> None:
        if not hasattr(self, "_navigation_history"):
            self._navigation_history = []

        previous_index = getattr(self, "_last_stack_index", -1)

        if getattr(self, "_navigation_back_in_progress", False):
            self._last_stack_index = index
            return

        if previous_index >= 0 and previous_index != index:
            if not self._navigation_history or self._navigation_history[-1] != previous_index:
                self._navigation_history.append(previous_index)
                self._navigation_history = self._navigation_history[-50:]

        self._last_stack_index = index

    def go_back(self) -> bool:
        if not hasattr(self, "stack"):
            return False

        if not getattr(self, "_navigation_history", []):
            return False

        current_index = self.stack.currentIndex()

        while self._navigation_history:
            target_index = self._navigation_history.pop()

            if target_index != current_index:
                self._navigation_back_in_progress = True
                try:
                    self.navigate(target_index)
                finally:
                    self._navigation_back_in_progress = False

                return True

        return False

    def _is_editing_text_input(self) -> bool:
        app = QApplication.instance()
        if app is None:
            return False

        widget = app.focusWidget()

        editable_widget_names = {
            "QLineEdit",
            "QTextEdit",
            "QPlainTextEdit",
            "QSpinBox",
            "QDoubleSpinBox",
            "QDateEdit",
            "QDateTimeEdit",
            "QTimeEdit",
            "QComboBox",
            "QCalendarWidget",
        }

        while widget is not None:
            class_name = widget.metaObject().className()

            if class_name in editable_widget_names:
                return True

            widget = widget.parentWidget()

        return False


    def _handle_current_page_internal_back(self) -> bool:
        """
        Give the active page a chance to handle Backspace before MainWindow
        global history navigation runs.
        """
        try:
            current = self.stack.currentWidget()
        except Exception:
            return False

        candidates = []

        if current is not None:
            candidates.append(current)

            # Scroll wrapper case.
            try:
                wrapped = current.widget()
                if wrapped is not None:
                    candidates.append(wrapped)
            except Exception:
                pass

            # Child page case.
            try:
                candidates.extend(current.findChildren(object))
            except Exception:
                pass

        for candidate in candidates:
            if hasattr(candidate, "handle_back_navigation"):
                try:
                    if candidate.handle_back_navigation():
                        return True
                except Exception:
                    pass

        return False


    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Backspace:
            if self._handle_current_page_internal_back():
                return True

        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            modifiers = event.modifiers()

            is_backspace = key == Qt.Key.Key_Backspace
            is_alt_left = key == Qt.Key.Key_Left and bool(modifiers & Qt.KeyboardModifier.AltModifier)

            if is_backspace or is_alt_left:
                if not self._is_editing_text_input():
                    if self.go_back():
                        return True

        return super().eventFilter(obj, event)


    def _sync_sidebar_selection(self, index):
        effective_index = index

        data_parent_index = getattr(self, "TYRE_PRODUCT_TREE_INDEX", None)
        data_child_indexes = {
            getattr(self, "TYRE_PRODUCT_TREE_INDEX", None),
            getattr(self, "FACTORY_CAPACITY_INDEX", None),
            getattr(self, "PRODUCT_MASTER_INDEX", None),
            getattr(self, "OVEN_MASTER_INDEX", None),
            getattr(self, "MOLD_MASTER_V2_INDEX", None),
            getattr(self, "CASING_MASTER_V2_INDEX", None),
            getattr(self, "CAPACITY_MASTER_INDEX", None),
            getattr(self, "RAW_EXCEL_VIEWER_INDEX", None),
        }
        data_child_indexes.discard(None)

        if data_parent_index is not None and index in data_child_indexes:
            effective_index = data_parent_index

        for page_index, buttons in getattr(self, "nav_buttons_by_index", {}).items():
            for button in buttons:
                button.blockSignals(True)
                button.setChecked(page_index == effective_index)
                button.blockSignals(False)


    def navigate(
        self,
        index: int,
    ) -> None:
        self._sync_sidebar_selection(index)

        if self.monthly_stock_only_mode:
            page, loaded_now = (
                self._ensure_page_loaded(0)
            )
            self.stack.setCurrentIndex(0)

            for button in self.nav_buttons:
                button.setChecked(True)

            if (
                page is not None
                and not loaded_now
            ):
                self._refresh_monthly_stock_only_page()
            return

        page, loaded_now = (
            self._ensure_page_loaded(index)
        )

        if page is None:
            return

        self.stack.setCurrentIndex(index)

        for (
            button_position,
            button,
        ) in enumerate(self.nav_buttons):
            button.setChecked(
                button_position
                == self._nav_position_from_index(index)
            )

        if not loaded_now:
            self._refresh_page(index)

    def _refresh_monthly_stock_only_page(self) -> None:
        page = getattr(self, "monthly_stock_count_page", None)

        if page is None:
            return

        for method_name in ("refresh", "refresh_page", "load_data"):
            method = getattr(page, method_name, None)
            if callable(method):
                try:
                    method()
                except TypeError:
                    pass
                except Exception as exc:
                    QMessageBox.warning(self, "Refresh Warning", str(exc))
                break

    def _nav_position_from_index(self, index: int) -> int:
        nav_map = {
            self.DASHBOARD_INDEX: 0,
            self.ORDER_ENTRY_INDEX: 1,
            self.SCHEDULE_INDEX: 2,
            self.SHIPMENT_DETAILS_INDEX: 3,
            self.STOCK_PLANNING_INDEX: 4,
            self.TIRE_STOCK_INDEX: 5,
            self.MONTHLY_STOCK_COUNT_INDEX: 6,
            self.MANAGER_OUTPUT_INDEX: 7,
            self.FACTORY_DATA_CENTER_INDEX: 8,
            self.ADMIN_CONTROL_INDEX: 9,
        }

        return nav_map.get(index, -1)

    def _refresh_page(
        self,
        index: int,
    ) -> None:
        page = self._page_instances.get(
            index
        )

        if page is None:
            return

        for method_name in (
            "refresh",
            "refresh_page",
            "load_data",
        ):
            method = getattr(
                page,
                method_name,
                None,
            )

            if callable(method):
                try:
                    method()
                except TypeError:
                    pass
                except Exception as exc:
                    QMessageBox.warning(
                        self,
                        "Refresh Warning",
                        str(exc),
                    )
                break

    def open_new_shipment_entry(
        self,
    ) -> None:
        self.navigate(
            self.ORDER_ENTRY_INDEX
        )

        page = getattr(
            self,
            "order_entry_page",
            None,
        )

        if page is None:
            QMessageBox.warning(
                self,
                "Shipment Orders Unavailable",
                (
                    "The Shipment Orders page "
                    "could not be loaded."
                ),
            )
            return

        clear_form = getattr(
            page,
            "clear_form",
            None,
        )
        if callable(clear_form):
            clear_form()

        refresh_master_items = getattr(
            page,
            "refresh_master_items",
            None,
        )
        if callable(refresh_master_items):
            try:
                refresh_master_items(
                    show_warning=False
                )
            except TypeError:
                refresh_master_items()

        shipment_name_input = getattr(
            page,
            "shipment_name_input",
            None,
        )
        if shipment_name_input is not None:
            shipment_name_input.setFocus()

    def open_shipment_details_page(self) -> None:
        self.navigate(self.SHIPMENT_DETAILS_INDEX)

    def open_saved_shipment_details(self, shipment_id: int) -> None:
        self.navigate(self.SHIPMENT_DETAILS_INDEX)
        page = getattr(self, "shipment_details_page", None)
        if page is None:
            return
        try:
            page.open_shipment_detail(int(shipment_id))
        except Exception as exc:
            QMessageBox.warning(self, "Shipment Open Failed", str(exc))

    def open_stock_planning_page(self) -> None:
        self.navigate(self.STOCK_PLANNING_INDEX)

    def open_monthly_stock_count_page(self) -> None:
        self.navigate(self.MONTHLY_STOCK_COUNT_INDEX)

    def open_stock_item_detail(self, material_code: str) -> None:
        if self.monthly_stock_only_mode:
            self.navigate(self.MONTHLY_STOCK_COUNT_INDEX)
            return

        title = f"Stock Item Detail: {material_code}"
        subtitle = (
            "Detailed BOM, compound, bead, band and capacity analysis for this item "
            "will be connected in the next module step. The selected material code is "
            f"{material_code}."
        )
        self.show_placeholder(title, subtitle)


    def _show_factory_out_date_logic_page(self) -> None:
        if not hasattr(self, "factory_out_date_logic_page"):
            self.factory_out_date_logic_page = None

        if not hasattr(self, "factory_out_date_logic_container"):
            self.factory_out_date_logic_container = None

        if self.factory_out_date_logic_page is None:
            self.factory_out_date_logic_page = FactoryOutDateLogicPage()
            self.factory_out_date_logic_container = self._wrap_scroll(
                self.factory_out_date_logic_page
            )
            self.stack.addWidget(self.factory_out_date_logic_container)

        self.stack.setCurrentWidget(self.factory_out_date_logic_container)


    def _show_admin_database_viewer_page(self) -> None:
        if not hasattr(self, "admin_database_viewer_page"):
            self.admin_database_viewer_page = None

        if not hasattr(self, "admin_database_viewer_container"):
            self.admin_database_viewer_container = None

        if self.admin_database_viewer_page is None:
            self.admin_database_viewer_page = AdminDatabaseViewerPage(self.current_user)
            self.admin_database_viewer_container = self._wrap_scroll(
                self.admin_database_viewer_page
            )
            self.stack.addWidget(self.admin_database_viewer_container)

        self.stack.setCurrentWidget(self.admin_database_viewer_container)

        if hasattr(self.admin_database_viewer_page, "load_tables_once"):
            self.admin_database_viewer_page.load_tables_once()


    def open_module_action(self, action_key: str) -> None:
        if action_key == "factory_out_date_logic":
            self._show_factory_out_date_logic_page()
            return
        if action_key == "database_viewer":
            self._show_admin_database_viewer_page()
            return

        if self.monthly_stock_only_mode:
            self.navigate(self.MONTHLY_STOCK_COUNT_INDEX)
            return

        action_map = {
            "stock_planning": (self.STOCK_PLANNING_INDEX, None, None),
            "monthly_stock_count": (self.MONTHLY_STOCK_COUNT_INDEX, None, None),
            "product_master": (self.PRODUCT_MASTER_INDEX, None, None),
            "stock_master": (self.STOCK_MASTER_INDEX, None, None),
            "bom_master": (self.BOM_MASTER_INDEX, None, None),
            "compound_master": (self.COMPOUND_MASTER_INDEX, None, None),
            "bead_master": (self.BEAD_MASTER_INDEX, None, None),
            "band_master": (self.BAND_MASTER_INDEX, None, None),
            "capacity_master": (self.CAPACITY_MASTER_INDEX, None, None),
            "oven_master": (self.OVEN_MASTER_INDEX, None, None),
            "material_requirement": (self.MATERIAL_REQUIREMENT_INDEX, None, None),
            "capacity_analysis": (self.CAPACITY_ANALYSIS_INDEX, None, None),
            "shipment_risk": (self.SHIPMENT_RISK_INDEX, None, None),
            "data_quality": (self.DATA_QUALITY_INDEX, None, None),
            "raw_excel_viewer": (self.RAW_EXCEL_VIEWER_INDEX, None, None),
            "users_roles": (self.USERS_ROLES_INDEX, None, None),
            "backup_restore": (self.BACKUP_RESTORE_INDEX, None, None),
            "audit_log": (self.AUDIT_LOG_INDEX, None, None),
        }

        target = action_map.get(action_key)

        if target is None:
            self.show_placeholder(
                "Module",
                f"Action '{action_key}' will be connected in the next step.",
            )
            return

        index, title, subtitle = target

        if index != self.PLACEHOLDER_INDEX:
            self.navigate(index)
            return

        self.show_placeholder(title or "Module", subtitle or "This module will be connected soon.")

    def show_placeholder(
        self,
        title: str,
        subtitle: str,
    ) -> None:
        if self.monthly_stock_only_mode:
            self.navigate(
                self.MONTHLY_STOCK_COUNT_INDEX
            )
            return

        index = self.PLACEHOLDER_INDEX
        placeholder = PlaceholderPage(
            title,
            subtitle,
        )

        old_widget = self.stack.widget(index)
        self.stack.removeWidget(old_widget)
        old_widget.deleteLater()

        container = self._wrap_scroll(
            placeholder
        )
        self.stack.insertWidget(
            index,
            container,
        )

        self.placeholder_page = placeholder
        self._page_instances[
            index
        ] = placeholder
        self._loaded_page_indexes.add(
            index
        )

        self.navigate(index)
