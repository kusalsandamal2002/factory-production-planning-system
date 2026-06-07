from __future__ import annotations

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
from app.models import User
from app.ui.dashboard_page import DashboardPage
from app.ui.details.shipment_details_page import ShipmentDetailsPage
from app.ui.details.tire_details_page import TireDetailsPage
from app.ui.module_hub_page import (
    create_admin_control_page,
    create_factory_data_center_page,
    create_manager_output_page,
)
from app.ui.order_entry_page import OrderEntryPage
from app.ui.product_master_page import ProductMasterPage
from app.ui.stock_master_page import StockMasterPage
from app.ui.bom_master_page import BomMasterPage
from app.ui.compound_master_page import CompoundMasterPage
from app.ui.bead_master_page import BeadMasterPage
from app.ui.schedule_page import SchedulePage
from app.ui.stock_planning_page import StockPlanningPage
from app.ui.tire_stock_page import TireStockPage

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
    PLACEHOLDER_INDEX = 27

    def __init__(self, current_user: User):
        super().__init__()

        self.current_user = current_user
        self.nav_buttons: list[QPushButton] = []
        self.placeholder_page: PlaceholderPage | None = None

        self.setWindowTitle(settings.app_name)
        self.resize(1600, 920)
        self.setMinimumSize(1250, 760)

        shell = QFrame()
        shell.setObjectName("AppShell")

        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self.setCentralWidget(shell)

        shell_layout.addWidget(self._build_sidebar())
        shell_layout.addWidget(self._build_content(), 1)

        self.navigate(self.DASHBOARD_INDEX)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(320)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 16, 20, 18)
        layout.setSpacing(10)

        brand = QLabel("Factory Oven\nPlanner")
        brand.setObjectName("BrandTitle")
        brand.setWordWrap(True)
        brand.setMinimumHeight(72)
        brand.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        subtitle = QLabel("Excel Replacement • MPPS • Oven Planning")
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
        self._add_nav_button(layout, "▦   Executive Dashboard", self.DASHBOARD_INDEX)

        layout.addSpacing(8)

        self._add_caption(layout, "Operations")
        self._add_nav_button(layout, "+   Customer / Shipment Demand", self.ORDER_ENTRY_INDEX)
        self._add_nav_button(layout, "▣   Daily Production Entry", self.PRODUCTION_ENTRY_INDEX)
        self._add_nav_button(layout, "▣   Daily Oven Schedule", self.SCHEDULE_INDEX)
        self._add_nav_button(layout, "↳   Shipment Management", self.SHIPMENT_DETAILS_INDEX)

        layout.addSpacing(8)

        self._add_caption(layout, "MPPS Planning")
        self._add_nav_button(layout, "▤   Stock Planning", self.STOCK_PLANNING_INDEX)
        self._add_nav_button(layout, "▥   Manager Output Center", self.MANAGER_OUTPUT_INDEX)

        layout.addSpacing(8)

        self._add_caption(layout, "Factory Data Center")
        self._add_nav_button(layout, "▧   Master Data Center", self.FACTORY_DATA_CENTER_INDEX)
        self._add_nav_button(layout, "↳   Tire Details", self.TIRE_DETAILS_INDEX)
        self._add_nav_button(layout, "↳   Tire Stock", self.TIRE_STOCK_INDEX)

        layout.addSpacing(8)

        self._add_caption(layout, "Admin")
        self._add_nav_button(layout, "⚙   Admin Control Center", self.ADMIN_CONTROL_INDEX)

        layout.addStretch()

        layout.addWidget(self._build_user_box())
        layout.addWidget(self._build_connection_badge())

        return sidebar

    def _build_content(self) -> QFrame:
        content = QFrame()
        content.setObjectName("ContentArea")

        layout = QVBoxLayout(content)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(0)

        self.stack = QStackedWidget()

        self.dashboard_page = self._create_dashboard_page()
        self.order_entry_page = OrderEntryPage(self.current_user)
        self.schedule_page = SchedulePage(self.current_user)
        self.stock_planning_page = StockPlanningPage(
            open_item_detail_callback=self.open_stock_item_detail
        )
        self.shipment_details_page = ShipmentDetailsPage()
        self.tire_details_page = TireDetailsPage()
        self.tire_stock_page = TireStockPage()
        self.factory_data_center_page = create_factory_data_center_page(
            open_callback=self.open_module_action
        )
        self.manager_output_page = create_manager_output_page(
            open_callback=self.open_module_action
        )
        self.admin_control_page = create_admin_control_page(
            open_callback=self.open_module_action
        )
        self.product_master_page = ProductMasterPage()
        self.stock_master_page = StockMasterPage()
        self.bom_master_page = BomMasterPage()
        self.compound_master_page = CompoundMasterPage()
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
            "Module",
            "This module will be connected in the next step.",
        )

        self.stack.addWidget(self._wrap_scroll(self.dashboard_page))
        self.stack.addWidget(self._wrap_scroll(self.order_entry_page))
        self.stack.addWidget(self._wrap_scroll(self.schedule_page))
        self.stack.addWidget(self._wrap_scroll(self.stock_planning_page))
        self.stack.addWidget(self._wrap_scroll(self.shipment_details_page))
        self.stack.addWidget(self._wrap_scroll(self.tire_details_page))
        self.stack.addWidget(self._wrap_scroll(self.tire_stock_page))
        self.stack.addWidget(self._wrap_scroll(self.factory_data_center_page))
        self.stack.addWidget(self._wrap_scroll(self.manager_output_page))
        self.stack.addWidget(self._wrap_scroll(self.admin_control_page))
        self.stack.addWidget(self._wrap_scroll(self.product_master_page))
        self.stack.addWidget(self._wrap_scroll(self.stock_master_page))
        self.stack.addWidget(self._wrap_scroll(self.bom_master_page))
        self.stack.addWidget(self._wrap_scroll(self.compound_master_page))
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

        layout.addWidget(self.stack)

        return content

    def _safe_create_page(self, page_class, *args) -> QWidget:
        try:
            return page_class(*args)
        except TypeError:
            return page_class()

    def _create_dashboard_page(self) -> DashboardPage:
        try:
            return DashboardPage(
                open_total_shipments_callback=self.open_shipment_details_page,
                open_completed_orders_callback=self.open_shipment_details_page,
                open_pending_orders_callback=self.open_shipment_details_page,
                open_overdue_orders_callback=self.open_shipment_details_page,
            )
        except TypeError:
            try:
                return DashboardPage(
                    self.open_shipment_details_page,
                    self.open_shipment_details_page,
                    self.open_shipment_details_page,
                    self.open_shipment_details_page,
                )
            except TypeError:
                return DashboardPage()

    def _wrap_scroll(self, widget: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(widget)
        return scroll

    def _add_caption(self, layout: QVBoxLayout, text: str) -> None:
        caption = QLabel(text.upper())
        caption.setObjectName("SidebarCaption")
        layout.addWidget(caption)

    def _add_nav_button(self, layout: QVBoxLayout, text: str, index: int) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName("NavButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setCheckable(True)
        button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        button.clicked.connect(lambda checked=False, page_index=index: self.navigate(page_index))

        self.nav_buttons.append(button)
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
        badge.setObjectName("ConnectionBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return badge

    def navigate(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

        for button_position, button in enumerate(self.nav_buttons):
            button.setChecked(button_position == self._nav_position_from_index(index))

        self._refresh_page(index)

    def _nav_position_from_index(self, index: int) -> int:
        nav_map = {
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

        return nav_map.get(index, -1)

    def _refresh_page(self, index: int) -> None:
        page_by_index = {
            self.DASHBOARD_INDEX: self.dashboard_page,
            self.SCHEDULE_INDEX: self.schedule_page,
            self.STOCK_PLANNING_INDEX: self.stock_planning_page,
            self.SHIPMENT_DETAILS_INDEX: self.shipment_details_page,
            self.TIRE_DETAILS_INDEX: self.tire_details_page,
            self.TIRE_STOCK_INDEX: self.tire_stock_page,
            self.PRODUCT_MASTER_INDEX: self.product_master_page,
            self.STOCK_MASTER_INDEX: self.stock_master_page,
            self.BOM_MASTER_INDEX: self.bom_master_page,
            self.COMPOUND_MASTER_INDEX: self.compound_master_page,
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

        page = page_by_index.get(index)

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

    def open_shipment_details_page(self) -> None:
        self.navigate(self.SHIPMENT_DETAILS_INDEX)

    def open_stock_planning_page(self) -> None:
        self.navigate(self.STOCK_PLANNING_INDEX)

    def open_stock_item_detail(self, material_code: str) -> None:
        title = f"Stock Item Detail: {material_code}"
        subtitle = (
            "Detailed BOM, compound, bead, band and capacity analysis for this item "
            "will be connected in the next module step. The selected material code is "
            f"{material_code}."
        )
        self.show_placeholder(title, subtitle)

    def open_module_action(self, action_key: str) -> None:
        action_map = {
            "stock_planning": (self.STOCK_PLANNING_INDEX, None, None),
            "product_master": (
                self.PRODUCT_MASTER_INDEX,
                None,
                None,
            ),
            "stock_master": (
                self.STOCK_MASTER_INDEX,
                None,
                None,
            ),
            "bom_master": (
                self.BOM_MASTER_INDEX,
                None,
                None,
            ),
            "compound_master": (
                self.COMPOUND_MASTER_INDEX,
                None,
                None,
            ),
            "bead_master": (
                self.BEAD_MASTER_INDEX,
                None,
                None,
            ),
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

    def show_placeholder(self, title: str, subtitle: str) -> None:
        self.placeholder_page = PlaceholderPage(title, subtitle)

        old_widget = self.stack.widget(self.PLACEHOLDER_INDEX)
        self.stack.removeWidget(old_widget)
        old_widget.deleteLater()

        self.stack.insertWidget(
            self.PLACEHOLDER_INDEX,
            self._wrap_scroll(self.placeholder_page),
        )

        self.navigate(self.PLACEHOLDER_INDEX)