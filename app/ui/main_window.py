from __future__ import annotations

from importlib import import_module
import sys
from time import perf_counter
from typing import Any, Callable

from PySide6.QtCore import QEvent, QTimer, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.config import settings
from app.core.events import DomainEvent, EventBus
from app.core.source_versions import SourceVersions
from app.core.task_manager import TaskManager
from app.core.thread_lifecycle import quiesce_qthreads
from app.core.ui_watchdog import UIWatchdog


class _LoadingPage(QWidget):
    def __init__(self, title: str):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 26, 26, 26)
        card = QFrame()
        card.setStyleSheet(
            "QFrame{background:#fff;border:1px solid #dbe4ef;border-radius:18px;}"
        )
        layout = QVBoxLayout(card)
        label = QLabel(title)
        label.setStyleSheet("font-size:22pt;font-weight:950;color:#0f172a;")
        hint = QLabel(
            "Opening workspace shell. Database, planning and model work runs in background."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#64748b;font-weight:700;")
        badge = QLabel("LOADING WORKSPACE")
        badge.setStyleSheet(
            "background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;"
            "border-radius:10px;padding:8px 12px;font-weight:950;"
        )
        layout.addWidget(label)
        layout.addWidget(hint)
        layout.addSpacing(8)
        layout.addWidget(badge)
        layout.addStretch()
        root.addWidget(card)
        root.addStretch()


class _ErrorPage(QWidget):
    def __init__(self, title: str, message: str, retry: Callable[[], None]):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 26, 26, 26)
        card = QFrame()
        card.setStyleSheet(
            "QFrame{background:#fff;border:1px solid #fecaca;border-radius:18px;}"
        )
        layout = QVBoxLayout(card)
        head = QLabel(title)
        head.setStyleSheet("font-size:20pt;font-weight:950;color:#991b1b;")
        body = QLabel(message)
        body.setWordWrap(True)
        body.setStyleSheet("color:#7f1d1d;font-weight:700;")
        button = QPushButton("Retry")
        button.clicked.connect(retry)
        layout.addWidget(head)
        layout.addWidget(body)
        layout.addWidget(button)
        layout.addStretch()
        root.addWidget(card)
        root.addStretch()


class MainWindow(QMainWindow):
    """Foundation R1 clean navigation shell.

    No historical Vxx monkey-patch chain, no periodic full tyre scan, and no eager
    import of retired pages. Active workspaces are imported only when requested.
    """

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
    WORKBOOK_LEARNING_INDEX = 39
    FACTORY_INTELLIGENCE_INDEX = 40
    MONTHLY_STOCK_OVEN_INDEX = 41

    MONTHLY_STOCK_MANAGER_ROLE = "Monthly Stock Manager"
    MONTHLY_STOCK_VIEWER_ROLE = "Monthly Stock Viewer"

    def __init__(self, current_user):
        super().__init__()
        self.current_user = current_user
        self.task_manager = TaskManager.instance()
        self.event_bus = EventBus.instance()
        self.source_versions = SourceVersions.instance()
        self.event_bus.event.connect(self._on_domain_event)
        self.ui_watchdog = UIWatchdog(interval_ms=80, warn_ms=200, parent=self)
        self.ui_watchdog.start()

        self.monthly_stock_viewer_mode = self._role_name().lower() == self.MONTHLY_STOCK_VIEWER_ROLE.lower()
        self.monthly_stock_only_mode = self._role_name().lower() in {
            self.MONTHLY_STOCK_MANAGER_ROLE.lower(),
            self.MONTHLY_STOCK_VIEWER_ROLE.lower(),
        }

        self._route_factories: dict[int, Callable[[], QWidget]] = {}
        self._route_titles: dict[int, str] = {}
        self._route_widgets: dict[int, QWidget] = {}
        self._route_pages: dict[int, QWidget] = {}
        self._route_creating: set[int] = set()
        self._history: list[int] = []
        self._current_route: int | None = None
        self.nav_buttons_by_index: dict[int, list[QPushButton]] = {}
        self._route_load_times: dict[int, float] = {}
        self._route_module_hints: dict[int, str] = {}

        self.setWindowTitle(settings.app_name)
        self.resize(1600, 920)
        self.setMinimumSize(1250, 760)
        self._apply_styles()
        self._register_routes()
        self._build_shell()

        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

        start_route = self.STOCK_MASTER_INDEX if self.monthly_stock_only_mode else self.DASHBOARD_INDEX
        QTimer.singleShot(0, lambda: self.navigate(start_route, record_history=False))
        QTimer.singleShot(400, self._refresh_live_source_async)

    # ------------------------------------------------------------------ shell
    def _apply_styles(self) -> None:
        self.setStyleSheet(
            self.styleSheet()
            + """
            QFrame#Sidebar{background:#0f172a;border:none;}
            QLabel#BrandTitle{color:#fff;font-size:13pt;font-weight:950;}
            QLabel#BrandSubtitle{color:#9fb0c7;font-size:7.5pt;font-weight:750;}
            QLabel#SidebarCaption{color:#93b4e8;font-size:7.5pt;font-weight:950;letter-spacing:1px;margin-top:7px;}
            QPushButton#NavButton{background:transparent;color:#f8fafc;border:none;border-radius:10px;padding:9px 11px;text-align:left;font-size:9pt;font-weight:850;}
            QPushButton#NavButton:hover{background:#1e293b;}
            QPushButton#NavButton:checked{background:#2563eb;color:#fff;}
            QLabel#SourceBadge{background:#063f3a;color:#ecfdf5;border:1px solid #0f766e;border-radius:9px;padding:7px;font-size:7.5pt;font-weight:950;}
            QLabel#DbBadge{color:#dbeafe;font-size:8pt;padding:5px;}
            """
        )

    def _build_shell(self) -> None:
        shell = QFrame()
        layout = QHBoxLayout(shell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())

        content = QFrame()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(22, 22, 22, 22)
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)
        layout.addWidget(content, 1)
        self.setCentralWidget(shell)

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 14, 12, 10)
        layout.setSpacing(4)

        brand = QLabel("Factory Production\nPlanner")
        brand.setObjectName("BrandTitle")
        subtitle = QLabel("Industrial Tyre Production Planning")
        subtitle.setObjectName("BrandSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(brand)
        layout.addWidget(subtitle)
        layout.addSpacing(8)

        if self.monthly_stock_only_mode:
            self._caption(layout, "Stock")
            self._nav(layout, "Stock Master", self.STOCK_MASTER_INDEX)
        else:
            self._caption(layout, "Dashboard")
            self._nav(layout, "Dashboard", self.DASHBOARD_INDEX)
            self._caption(layout, "Orders")
            self._nav(layout, "Shipment Orders", self.ORDER_ENTRY_INDEX)
            self._nav(layout, "Shipment Details", self.SHIPMENT_DETAILS_INDEX)
            self._caption(layout, "Data")
            self._nav(layout, "Factory Capacity", self.FACTORY_CAPACITY_INDEX)
            self._nav(layout, "Tyre Item Master", self.PRODUCT_MASTER_INDEX)
            self._nav(layout, "Stock Master", self.STOCK_MASTER_INDEX)
            self._caption(layout, "Planning")
            self._nav(layout, "Production Planning", self.SCHEDULE_INDEX)
            self._nav(layout, "Daily Plan", self.DAILY_PLAN_INDEX)
            self._nav(layout, "Shift Plan", self.SHIFT_PLAN_INDEX)
            self._nav(layout, "Material Requirement", self.MATERIAL_REQUIREMENT_INDEX)
            self._caption(layout, "Admin / Intelligence")
            self._nav(layout, "Admin Settings", self.ADMIN_CONTROL_INDEX)
            self._nav(layout, "AI / ML", self.RAW_EXCEL_VIEWER_INDEX)

        layout.addStretch()
        self.live_source_badge = QLabel("LIVE OVEN\nloading...")
        self.live_source_badge.setObjectName("SourceBadge")
        self.live_source_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.live_source_badge)
        if not self.monthly_stock_viewer_mode:
            db = QLabel("PostgreSQL Connected")
            db.setObjectName("DbBadge")
            db.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(db)
        return sidebar

    def _caption(self, layout: QVBoxLayout, text: str) -> None:
        label = QLabel(text.upper())
        label.setObjectName("SidebarCaption")
        layout.addWidget(label)

    def _nav(self, layout: QVBoxLayout, text: str, route: int) -> None:
        button = QPushButton(text)
        button.setObjectName("NavButton")
        button.setCheckable(True)
        button.clicked.connect(lambda _checked=False, r=route: self.navigate(r))
        layout.addWidget(button)
        self.nav_buttons_by_index.setdefault(route, []).append(button)

    # ------------------------------------------------------------------ routes
    def _register(self, route: int, title: str, factory: Callable[[], QWidget]) -> None:
        self._route_titles[route] = title
        self._route_factories[route] = factory

    @staticmethod
    def _class(module: str, name: str):
        return getattr(import_module(module), name)

    def _register_routes(self) -> None:
        self._register(
            self.DASHBOARD_INDEX,
            "Dashboard",
            lambda: self._class("app.ui.dashboard_pro_page", "DashboardProPage")(),
        )
        self._register(
            self.ORDER_ENTRY_INDEX,
            "Shipment Orders",
            lambda: self._class("app.ui.order_entry_async_page", "ShipmentOrderAsyncPage")(
                self.current_user,
                on_shipment_saved=self.open_saved_shipment_details,
            ),
        )
        self._register(
            self.SHIPMENT_DETAILS_INDEX,
            "Shipment Details",
            lambda: self._class("app.ui.shipment_details_pro_page", "ShipmentDetailsProPage")(
                self.current_user,
                on_new_shipment=self.open_new_shipment_entry,
            ),
        )
        self._register(
            self.FACTORY_CAPACITY_INDEX,
            "Factory Capacity",
            lambda: self._class("app.ui.factory_capacity_page", "FactoryCapacityPage")(
                on_open_page=lambda index: self.navigate(index),
                on_back=lambda: self.navigate(self.DASHBOARD_INDEX),
                page_indexes={
                    "Production Lines": self.OVEN_MASTER_INDEX,
                    "Cavities": self.CAVITIES_MASTER_INDEX,
                    "Mold Master": self.MOLD_MASTER_V2_INDEX,
                    "Casing Master": self.CASING_MASTER_V2_INDEX,
                    "Capacity / Time Master": self.CAPACITY_MASTER_INDEX,
                },
            ),
        )
        self._register(
            self.PRODUCT_MASTER_INDEX,
            "Tyre Item Master",
            lambda: self._class("app.ui.tyre_item_master_pro_page", "TyreItemMasterProPage")(),
        )
        self._register(
            self.STOCK_MASTER_INDEX,
            "Stock Master",
            lambda: self._class("app.ui.stock_workspace_page", "StockWorkspacePage")(
                on_back=lambda: self.navigate(self.DASHBOARD_INDEX)
            ),
        )
        self._register(
            self.SCHEDULE_INDEX,
            "Production Planning",
            lambda: self._class("app.ui.schedule_page", "SchedulePage")(self.current_user),
        )
        self._register(
            self.DAILY_PLAN_INDEX,
            "Daily Plan",
            lambda: self._class("app.ui.daily_plan_async_page", "DailyPlanAsyncPage")(self.current_user),
        )
        self._register(
            self.SHIFT_PLAN_INDEX,
            "Shift Plan",
            lambda: self._class("app.ui.intelligent_operations_pages", "ShiftPlanPage")(self.current_user),
        )
        self._register(
            self.MATERIAL_REQUIREMENT_INDEX,
            "Material Requirement",
            lambda: self._class("app.ui.material_requirement_pro_page", "MaterialRequirementProPage")(self.current_user),
        )
        self._register(
            self.ADMIN_CONTROL_INDEX,
            "Admin Settings",
            lambda: import_module("app.ui.module_hub_page").create_admin_control_page(
                open_callback=self.open_module_action
            ),
        )
        self._register(
            self.RAW_EXCEL_VIEWER_INDEX,
            "AI / ML",
            lambda: self._class("app.ui.ai_ml_control_center_page", "AIMLControlCenterPage")(self.current_user),
        )

        # Hidden routes used only by Factory Capacity / Admin workflows.
        self._register(self.OVEN_MASTER_INDEX, "Production Lines", lambda: self._class("app.ui.production_line_master_page", "ProductionLineMasterPage")())
        self._register(self.CAVITIES_MASTER_INDEX, "Cavities", lambda: self._class("app.ui.cavities_master_page", "CavitiesMasterPage")())
        self._register(self.MOLD_MASTER_V2_INDEX, "Mold Master", lambda: self._class("app.ui.mold_master_page", "MoldMasterPage")())
        self._register(self.CASING_MASTER_V2_INDEX, "Casing Master", lambda: self._class("app.ui.casing_master_page", "CasingMasterPage")())
        self._register(self.CAPACITY_MASTER_INDEX, "Capacity / Time Master", lambda: self._safe_construct("app.ui.capacity_master_page", ("CapacityMasterPage", "CapacityPage")))
        self._register(self.USERS_ROLES_INDEX, "Users & Roles", lambda: self._safe_construct("app.ui.users_roles_page", ("UsersRolesPage", "UserRolesPage", "UsersAndRolesPage")))
        self._register(self.BACKUP_RESTORE_INDEX, "Backup & Restore", lambda: self._safe_construct("app.ui.backup_restore_page", ("BackupRestorePage", "BackupAndRestorePage")))
        self._register(self.AUDIT_LOG_INDEX, "Audit Log", lambda: self._safe_construct("app.ui.audit_log_page", ("AuditLogPage", "AuditLogsPage")))

        self._route_module_hints.update(
            {
                self.DASHBOARD_INDEX: "app.ui.dashboard_pro_page",
                self.ORDER_ENTRY_INDEX: "app.ui.order_entry_async_page",
                self.SHIPMENT_DETAILS_INDEX: "app.ui.shipment_details_pro_page",
                self.FACTORY_CAPACITY_INDEX: "app.ui.factory_capacity_page",
                self.PRODUCT_MASTER_INDEX: "app.ui.tyre_item_master_pro_page",
                self.STOCK_MASTER_INDEX: "app.ui.stock_workspace_page",
                self.SCHEDULE_INDEX: "app.ui.schedule_page",
                self.DAILY_PLAN_INDEX: "app.ui.daily_plan_async_page",
                self.SHIFT_PLAN_INDEX: "app.ui.intelligent_operations_pages",
                self.MATERIAL_REQUIREMENT_INDEX: "app.ui.material_requirement_pro_page",
                self.ADMIN_CONTROL_INDEX: "app.ui.module_hub_page",
                self.RAW_EXCEL_VIEWER_INDEX: "app.ui.ai_ml_control_center_page",
            }
        )

    def _safe_construct(self, module_name: str, names: tuple[str, ...]) -> QWidget:
        module = import_module(module_name)
        for name in names:
            cls = getattr(module, name, None)
            if cls is not None:
                try:
                    return cls(self.current_user)
                except TypeError:
                    return cls()
        raise ImportError(f"No supported page class found in {module_name}")

    def _wrap(self, page: QWidget) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(page)
        return scroll

    def navigate(self, route: int, *, record_history: bool = True) -> None:
        redirects = {
            self.REPORTS_INDEX: self.DASHBOARD_INDEX,
            self.WORKBOOK_LEARNING_INDEX: self.RAW_EXCEL_VIEWER_INDEX,
            self.FACTORY_INTELLIGENCE_INDEX: self.RAW_EXCEL_VIEWER_INDEX,
            self.TYRE_PRODUCT_TREE_INDEX: self.FACTORY_CAPACITY_INDEX,
            self.DELIVERY_DATE_INDEX: self.SHIPMENT_DETAILS_INDEX,
            self.MONTHLY_STOCK_COUNT_INDEX: self.STOCK_MASTER_INDEX,
        }
        route = redirects.get(int(route), int(route))
        if self.monthly_stock_only_mode and route != self.STOCK_MASTER_INDEX:
            route = self.STOCK_MASTER_INDEX

        if record_history and self._current_route is not None and self._current_route != route:
            self._history.append(self._current_route)
            if len(self._history) > 60:
                self._history = self._history[-60:]
        self._current_route = route
        self._select_nav(route)

        existing = self._route_widgets.get(route)
        if existing is not None:
            self.stack.setCurrentWidget(existing)
            return

        if route not in self._route_factories:
            QMessageBox.warning(self, "Workspace", "This legacy route is not part of the active MPPS workflow.")
            return

        loader = _LoadingPage(self._route_titles.get(route, "Workspace"))
        self._route_widgets[route] = loader
        self.stack.addWidget(loader)
        self.stack.setCurrentWidget(loader)
        if route in self._route_creating:
            return
        self._route_creating.add(route)
        QTimer.singleShot(16, lambda r=route: self._preload_route_module(r))

    def _preload_route_module(self, route: int) -> None:
        module_name = self._route_module_hints.get(route)
        if not module_name or module_name in sys.modules:
            QTimer.singleShot(0, lambda r=route: self._materialize_route(r))
            return

        self.task_manager.submit(
            f"route-import:{route}",
            lambda module=module_name: bool(import_module(module)),
            on_result=lambda _ok, r=route: QTimer.singleShot(0, lambda: self._materialize_route(r)),
            on_error=lambda message, r=route: self._route_import_failed(r, message),
            priority=-1,
            replace=True,
        )

    def _route_import_failed(self, route: int, message: str) -> None:
        loader = self._route_widgets.get(route)
        if loader is None:
            self._route_creating.discard(route)
            return
        error = _ErrorPage(
            self._route_titles.get(route, "Workspace") + " failed to import",
            message.splitlines()[-1] if message else "Unknown import error",
            retry=lambda r=route: self._retry_route(r),
        )
        self.stack.addWidget(error)
        self.stack.removeWidget(loader)
        loader.deleteLater()
        self._route_widgets[route] = error
        self._route_creating.discard(route)
        if self._current_route == route:
            self.stack.setCurrentWidget(error)

    def _materialize_route(self, route: int) -> None:
        factory = self._route_factories.get(route)
        loader = self._route_widgets.get(route)
        if factory is None or loader is None:
            self._route_creating.discard(route)
            return
        started = perf_counter()
        try:
            page = factory()
            wrapper = self._wrap(page)
            self.stack.addWidget(wrapper)
            if loader in [self.stack.widget(i) for i in range(self.stack.count())]:
                self.stack.removeWidget(loader)
                loader.deleteLater()
            self._route_widgets[route] = wrapper
            self._route_pages[route] = page
            elapsed = perf_counter() - started
            self._route_load_times[route] = elapsed
            print(f"[MPPS FOUNDATION] Created {self._route_titles.get(route, route)} shell in {elapsed:.3f}s", flush=True)
            if elapsed > 0.25:
                print(f"[MPPS PERFORMANCE WARNING] Constructor exceeded 0.25s: route={route} elapsed={elapsed:.3f}s", flush=True)
            if self._current_route == route:
                self.stack.setCurrentWidget(wrapper)
        except Exception as exc:
            message = str(exc)
            error = _ErrorPage(
                self._route_titles.get(route, "Workspace") + " failed to load",
                message,
                retry=lambda r=route: self._retry_route(r),
            )
            self.stack.addWidget(error)
            self.stack.removeWidget(loader)
            loader.deleteLater()
            self._route_widgets[route] = error
            if self._current_route == route:
                self.stack.setCurrentWidget(error)
        finally:
            self._route_creating.discard(route)

    def _retry_route(self, route: int) -> None:
        widget = self._route_widgets.pop(route, None)
        page = self._route_pages.pop(route, None)
        if widget is not None:
            self.stack.removeWidget(widget)
            widget.deleteLater()
        if page is not None:
            report = quiesce_qthreads(page, wait_ms=1500, force_wait_ms=400)
            if report.get("forced") or report.get("still_running"):
                print(f"[MPPS THREAD RETRY] route={route} {report}", flush=True)
            page.deleteLater()
        self.navigate(route, record_history=False)

    def _select_nav(self, route: int) -> None:
        for index, buttons in self.nav_buttons_by_index.items():
            for button in buttons:
                button.blockSignals(True)
                button.setChecked(index == route)
                button.blockSignals(False)

    # ------------------------------------------------------------------ callbacks/events
    def _role_name(self) -> str:
        try:
            role = getattr(self.current_user, "role", None)
            return str(getattr(role, "role_name", "") or "").strip()
        except Exception:
            return ""

    def _refresh_live_source_async(self) -> None:
        def load_source():
            from app.database import get_session
            from app.services.operational_source_service import OperationalSourceService
            with get_session() as session:
                source = OperationalSourceService.latest(session)
                return source.plan_date, source.workbook_name or source.label or ""

        self.task_manager.submit(
            "main-window:live-source",
            load_source,
            on_result=self._apply_live_source,
            on_error=lambda _msg: self.live_source_badge.setText("LIVE OVEN\nunavailable"),
            replace=True,
        )

    def _apply_live_source(self, payload) -> None:
        plan_date, workbook = payload
        text = plan_date.isoformat() if hasattr(plan_date, "isoformat") else "—"
        self.live_source_badge.setText(f"LIVE OVEN\n{text}")
        self.live_source_badge.setToolTip(str(workbook or ""))

    def _on_domain_event(self, event: DomainEvent) -> None:
        mapping = {
            "SourceCommitted": ("source", "stock", "shipment", "planning", "material", "master"),
            "ShipmentCreated": ("shipment", "planning"),
            "ShipmentUpdated": ("shipment", "planning"),
            "ShipmentCancelled": ("shipment", "planning", "stock", "material"),
            "ShipmentShipped": ("shipment", "planning", "stock"),
            "StockChanged": ("stock", "planning"),
            "MasterDataChanged": ("master", "planning"),
            "PlanGenerated": ("planning", "material"),
        }
        keys = mapping.get(event.name, ())
        if keys:
            self.source_versions.bump(*keys)
        for page in list(self._route_pages.values()):
            handler = getattr(page, "handle_domain_event", None)
            if callable(handler):
                try:
                    handler(event)
                except Exception as exc:
                    print(f"[MPPS EVENT WARNING] {event.name}: {exc}", flush=True)
            elif event.name == "SourceCommitted":
                notify = getattr(page, "notify_source_changed", None)
                if callable(notify):
                    try:
                        notify()
                    except Exception:
                        pass
        if event.name == "SourceCommitted":
            self._refresh_live_source_async()

    def _when_route_ready(self, route: int, callback: Callable[[QWidget], None], attempts: int = 40) -> None:
        page = self._route_pages.get(route)
        if page is not None:
            callback(page)
            return
        if attempts <= 0:
            return
        QTimer.singleShot(80, lambda: self._when_route_ready(route, callback, attempts - 1))

    def open_new_shipment_entry(self) -> None:
        self.navigate(self.ORDER_ENTRY_INDEX)
        def ready(page):
            clear = getattr(page, "clear_form", None)
            if callable(clear):
                clear()
            field = getattr(page, "shipment_name_input", None)
            if field is not None:
                field.setFocus()
        self._when_route_ready(self.ORDER_ENTRY_INDEX, ready)

    def open_saved_shipment_details(self, shipment_id: int) -> None:
        self.event_bus.publish("ShipmentCreated", shipment_id=int(shipment_id))
        self.navigate(self.SHIPMENT_DETAILS_INDEX)
        self._when_route_ready(
            self.SHIPMENT_DETAILS_INDEX,
            lambda page: getattr(page, "open_shipment_detail", lambda _id: None)(int(shipment_id)),
        )

    def open_shipment_details_page(self) -> None:
        self.navigate(self.SHIPMENT_DETAILS_INDEX)

    def open_stock_planning_page(self) -> None:
        self.navigate(self.STOCK_MASTER_INDEX)

    def open_module_action(self, action_key: str) -> None:
        action_map = {
            "stock_planning": self.STOCK_MASTER_INDEX,
            "monthly_stock_count": self.STOCK_MASTER_INDEX,
            "stock_master": self.STOCK_MASTER_INDEX,
            "product_master": self.PRODUCT_MASTER_INDEX,
            "material_requirement": self.MATERIAL_REQUIREMENT_INDEX,
            "raw_excel_viewer": self.RAW_EXCEL_VIEWER_INDEX,
            "workbook_learning": self.RAW_EXCEL_VIEWER_INDEX,
            "ai_learning": self.RAW_EXCEL_VIEWER_INDEX,
            "users_roles": self.USERS_ROLES_INDEX,
            "backup_restore": self.BACKUP_RESTORE_INDEX,
            "audit_log": self.AUDIT_LOG_INDEX,
            "capacity_master": self.CAPACITY_MASTER_INDEX,
            "oven_master": self.OVEN_MASTER_INDEX,
        }
        route = action_map.get(str(action_key))
        if route is None:
            QMessageBox.information(self, "Admin", "This legacy action is not part of the active workflow.")
            return
        self.navigate(route)

    # ------------------------------------------------------------------ back/close
    def go_back(self) -> bool:
        while self._history:
            route = self._history.pop()
            if route != self._current_route:
                self.navigate(route, record_history=False)
                return True
        return False

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            modifiers = event.modifiers()
            if key == Qt.Key.Key_Left and bool(modifiers & Qt.KeyboardModifier.AltModifier):
                if self.go_back():
                    return True
            if key == Qt.Key.Key_Backspace:
                focus = QApplication.focusWidget()
                if not isinstance(focus, (QLineEdit, QTextEdit)) and self.go_back():
                    return True
        return super().eventFilter(obj, event)

    def closeEvent(self, event) -> None:
        try:
            self.event_bus.event.disconnect(self._on_domain_event)
        except Exception:
            pass

        app = QApplication.instance()
        if app is not None:
            try:
                app.removeEventFilter(self)
            except Exception:
                pass

        try:
            self.ui_watchdog.stop()
        except Exception:
            pass

        self.task_manager.cancel_all()

        totals = {"found": 0, "graceful": 0, "forced": 0, "still_running": 0}
        for route, page in list(self._route_pages.items()):
            try:
                report = quiesce_qthreads(page, wait_ms=3500, force_wait_ms=750)
                for key in totals:
                    totals[key] += int(report.get(key, 0))
                if report.get("found"):
                    print(f"[MPPS THREAD SHUTDOWN] route={route} {report}", flush=True)
            except Exception as exc:
                print(f"[MPPS THREAD SHUTDOWN WARNING] route={route}: {exc}", flush=True)

        pool_done = self.task_manager.shutdown(wait_ms=5000)
        print(
            f"[MPPS SHUTDOWN] page_threads={totals} task_pool_done={pool_done}",
            flush=True,
        )
        super().closeEvent(event)
