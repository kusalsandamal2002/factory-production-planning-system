from __future__ import annotations

from datetime import date
from importlib import import_module
from typing import Any

from PySide6.QtCore import QDate, QTimer, Qt
from PySide6.QtGui import QColor, QTextCharFormat
from PySide6.QtWidgets import (
    QCalendarWidget,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.task_manager import TaskManager
from app.services.admin_control_service import (
    load_admin_health_snapshot,
    load_calendar_month,
    load_data_sources_snapshot,
    load_planning_rules,
    save_planning_rules,
    set_calendar_day,
)


CARD_DEFINITIONS = (
    (
        "Users & Roles",
        "Manage planner, supervisor, stores, admin and viewer access.",
        "users_roles",
    ),
    (
        "Factory Calendar",
        "Maintain factory holidays and manager-approved special working days.",
        "factory_calendar",
    ),
    (
        "Planning Rules",
        "Control planning horizon, dispatch buffer, safety stock and auto-replan policy.",
        "planning_rules",
    ),
    (
        "Data Sources & Integrations",
        "Review PostgreSQL / Excel authority and future ERP, WMS, MES and machine connections.",
        "data_sources",
    ),
    (
        "Backup & Restore",
        "Create and restore safe PostgreSQL/application recovery points.",
        "backup_restore",
    ),
    (
        "Audit Log",
        "Trace operational and administrative changes by user and time.",
        "audit_log",
    ),
    (
        "System Health",
        "Review database, latest source, backups, background jobs and data warnings.",
        "system_health",
    ),
    (
        "Advanced Database Tools",
        "Admin-only read-only PostgreSQL inspection with lazy loading and export.",
        "advanced_database",
    ),
)


def _date_text(value: Any) -> str:
    if value is None:
        return "—"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    text = str(value).strip()
    return text or "—"


class _AdminBasePage(QWidget):
    def __init__(self, *, back_callback=None):
        super().__init__()
        self.back_callback = back_callback
        self.tasks = TaskManager.instance()

    def _header(
        self,
        title: str,
        subtitle: str,
        *,
        refresh_callback=None,
    ) -> QFrame:
        frame = QFrame()
        frame.setObjectName("AdminHeader")
        row = QHBoxLayout(frame)
        row.setContentsMargins(18, 13, 18, 13)

        back = QPushButton("← Admin")
        back.setObjectName("SecondaryButton")
        back.clicked.connect(
            lambda: self.back_callback()
            if callable(self.back_callback)
            else None
        )
        row.addWidget(back)

        text_layout = QVBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("AdminPageTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("AdminPageSubtitle")
        subtitle_label.setWordWrap(True)
        text_layout.addWidget(title_label)
        text_layout.addWidget(subtitle_label)
        row.addLayout(text_layout, 1)

        if refresh_callback is not None:
            refresh = QPushButton("Refresh")
            refresh.setObjectName("PrimaryButton")
            refresh.clicked.connect(refresh_callback)
            row.addWidget(refresh)

        return frame


class FactoryCalendarAdminPage(_AdminBasePage):
    def __init__(self, *, back_callback=None):
        super().__init__(back_callback=back_callback)
        self._marks: dict[date, dict[str, Any]] = {}
        self._build_ui()
        QTimer.singleShot(0, self.refresh_month)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(
            self._header(
                "Factory Calendar",
                "Factory works normally unless a date is explicitly marked as a holiday. "
                "Special working days can override a holiday.",
                refresh_callback=self.refresh_month,
            )
        )

        body = QFrame()
        body.setObjectName("AdminPanel")
        layout = QHBoxLayout(body)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.currentPageChanged.connect(
            lambda _y, _m: self.refresh_month()
        )
        self.calendar.selectionChanged.connect(self._selection_changed)
        layout.addWidget(self.calendar, 2)

        right = QVBoxLayout()
        selected_title = QLabel("Selected Date")
        selected_title.setObjectName("SectionTitle")
        right.addWidget(selected_title)

        self.selected_date_label = QLabel("—")
        self.selected_date_label.setObjectName("LargeValue")
        right.addWidget(self.selected_date_label)

        self.selected_status = QLabel("Normal Working Day")
        self.selected_status.setObjectName("StatusBadge")
        self.selected_status.setWordWrap(True)
        right.addWidget(self.selected_status)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(
            "Holiday / special working day description"
        )
        right.addWidget(self.name_input)

        holiday = QPushButton("Mark Factory Holiday")
        holiday.setObjectName("DangerButton")
        holiday.clicked.connect(lambda: self._save("HOLIDAY"))
        right.addWidget(holiday)

        working = QPushButton("Mark Special Working Day")
        working.setObjectName("PrimaryButton")
        working.clicked.connect(lambda: self._save("WORKING"))
        right.addWidget(working)

        clear = QPushButton("Clear Manual Mark")
        clear.setObjectName("SecondaryButton")
        clear.clicked.connect(lambda: self._save("CLEAR"))
        right.addWidget(clear)

        self.message = QLabel("")
        self.message.setObjectName("InfoText")
        self.message.setWordWrap(True)
        right.addWidget(self.message)
        right.addStretch()

        layout.addLayout(right, 1)
        root.addWidget(body, 1)
        self._selection_changed()

    def refresh_month(self):
        year = int(self.calendar.yearShown())
        month = int(self.calendar.monthShown())
        self.message.setText("Loading calendar...")
        self.tasks.submit(
            "admin.calendar.month",
            lambda y=year, m=month: load_calendar_month(y, m),
            on_result=self._apply_month,
            on_error=lambda message: self.message.setText(
                "Calendar load failed."
            ),
        )

    def _apply_month(self, rows):
        self._marks = {}
        self.calendar.setDateTextFormat(QDate(), QTextCharFormat())

        holiday_format = QTextCharFormat()
        holiday_format.setBackground(QColor("#fee2e2"))
        holiday_format.setForeground(QColor("#991b1b"))

        working_format = QTextCharFormat()
        working_format.setBackground(QColor("#dcfce7"))
        working_format.setForeground(QColor("#166534"))

        for row in rows or []:
            day = row.get("holiday_date")
            if day is None:
                continue
            self._marks[day] = dict(row)
            qdate = QDate(day.year, day.month, day.day)
            if bool(row.get("is_working_day_override")):
                self.calendar.setDateTextFormat(qdate, working_format)
            else:
                self.calendar.setDateTextFormat(qdate, holiday_format)

        self.message.setText(
            f"{len(self._marks)} manual mark(s) in this month."
        )
        self._selection_changed()

    def _selection_changed(self):
        qdate = self.calendar.selectedDate()
        selected = date(qdate.year(), qdate.month(), qdate.day())
        self.selected_date_label.setText(selected.isoformat())

        row = self._marks.get(selected)
        if not row:
            self.selected_status.setText("Normal Working Day")
            self.name_input.setText("")
            return

        if bool(row.get("is_working_day_override")):
            self.selected_status.setText("Special Working Day")
        else:
            self.selected_status.setText("Factory Holiday")
        self.name_input.setText(str(row.get("holiday_name") or ""))

    def _save(self, mode):
        qdate = self.calendar.selectedDate()
        selected = date(qdate.year(), qdate.month(), qdate.day())
        name = self.name_input.text().strip()
        self.message.setText("Saving calendar mark...")
        self.tasks.submit(
            "admin.calendar.save",
            lambda d=selected, m=mode, n=name: set_calendar_day(d, m, n),
            on_result=lambda _payload: self.refresh_month(),
            on_error=lambda _message: self.message.setText(
                "Calendar update failed."
            ),
        )


class PlanningRulesAdminPage(_AdminBasePage):
    def __init__(self, *, back_callback=None):
        super().__init__(back_callback=back_callback)
        self._build_ui()
        QTimer.singleShot(0, self.refresh)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(
            self._header(
                "Planning Rules",
                "System-wide deterministic planning rules. ML may estimate execution, "
                "but it cannot override these hard business controls.",
                refresh_callback=self.refresh,
            )
        )

        panel = QFrame()
        panel.setObjectName("AdminPanel")
        form = QFormLayout(panel)
        form.setContentsMargins(22, 20, 22, 20)
        form.setSpacing(14)

        self.horizon = QSpinBox()
        self.horizon.setRange(1, 365)
        self.horizon.setSuffix(" days")

        self.dispatch_buffer = QSpinBox()
        self.dispatch_buffer.setRange(0, 30)
        self.dispatch_buffer.setSuffix(" days")

        self.safety_stock = QDoubleSpinBox()
        self.safety_stock.setRange(0.0, 100.0)
        self.safety_stock.setDecimals(1)
        self.safety_stock.setSuffix(" %")

        self.auto_replan = QCheckBox("Automatically replan after operational changes")
        self.allow_overtime = QCheckBox("Allow overtime as a planning option")

        self.replan_debounce = QSpinBox()
        self.replan_debounce.setRange(1, 120)
        self.replan_debounce.setSuffix(" sec")

        self.priority_policy = QComboBox()
        self.priority_policy.addItem(
            "Target Date First",
            "TARGET_DATE_FIRST",
        )
        self.priority_policy.addItem(
            "Delivery Risk First",
            "DELIVERY_RISK_FIRST",
        )

        form.addRow("Planning Horizon", self.horizon)
        form.addRow("Packing / Dispatch Buffer", self.dispatch_buffer)
        form.addRow("Safety Stock", self.safety_stock)
        form.addRow("Auto Replan", self.auto_replan)
        form.addRow("Overtime", self.allow_overtime)
        form.addRow("Replan Debounce", self.replan_debounce)
        form.addRow("Priority Policy", self.priority_policy)

        save = QPushButton("Save Planning Rules")
        save.setObjectName("PrimaryButton")
        save.clicked.connect(self.save)
        form.addRow("", save)

        self.status = QLabel("")
        self.status.setObjectName("InfoText")
        form.addRow("", self.status)

        root.addWidget(panel)
        root.addStretch()

    def refresh(self):
        self.status.setText("Loading planning rules...")
        self.tasks.submit(
            "admin.planning_rules.load",
            load_planning_rules,
            on_result=self._apply,
            on_error=lambda _message: self.status.setText(
                "Planning rules could not be loaded."
            ),
        )

    def _apply(self, rules):
        rules = dict(rules or {})
        self.horizon.setValue(
            int(float(rules.get("planning_horizon_days") or 30))
        )
        self.dispatch_buffer.setValue(
            int(float(rules.get("packing_dispatch_buffer_days") or 1))
        )
        self.safety_stock.setValue(
            float(rules.get("safety_stock_pct") or 0)
        )
        self.auto_replan.setChecked(
            str(rules.get("auto_replan_enabled") or "").lower() == "true"
        )
        self.allow_overtime.setChecked(
            str(rules.get("allow_overtime") or "").lower() == "true"
        )
        self.replan_debounce.setValue(
            int(float(rules.get("replan_debounce_seconds") or 5))
        )

        policy = str(
            rules.get("priority_policy") or "TARGET_DATE_FIRST"
        )
        index = self.priority_policy.findData(policy)
        self.priority_policy.setCurrentIndex(max(0, index))
        self.status.setText("Planning rules loaded.")

    def save(self):
        payload = {
            "planning_horizon_days": self.horizon.value(),
            "packing_dispatch_buffer_days": self.dispatch_buffer.value(),
            "safety_stock_pct": self.safety_stock.value(),
            "auto_replan_enabled": self.auto_replan.isChecked(),
            "allow_overtime": self.allow_overtime.isChecked(),
            "replan_debounce_seconds": self.replan_debounce.value(),
            "priority_policy": self.priority_policy.currentData(),
        }
        self.status.setText("Saving planning rules...")
        self.tasks.submit(
            "admin.planning_rules.save",
            lambda p=payload: save_planning_rules(p),
            on_result=lambda _rules: self.status.setText(
                "Planning rules saved."
            ),
            on_error=lambda _message: self.status.setText(
                "Planning rules could not be saved."
            ),
        )


class DataSourcesAdminPage(_AdminBasePage):
    def __init__(self, *, back_callback=None):
        super().__init__(back_callback=back_callback)
        self.rows = {}
        self._build_ui()
        QTimer.singleShot(0, self.refresh)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(
            self._header(
                "Data Sources & Integrations",
                "Current authority and future integration readiness. "
                "Excel remains a transition source until operational ledgers replace it.",
                refresh_callback=self.refresh,
            )
        )

        grid = QGridLayout()
        grid.setSpacing(10)
        for index, name in enumerate(
            (
                "PostgreSQL",
                "Daily Excel / OVEN",
                "ERP",
                "WMS",
                "MES",
                "Barcode / QR",
                "Machine / PLC",
            )
        ):
            card = QFrame()
            card.setObjectName("MetricCard")
            layout = QVBoxLayout(card)
            layout.setContentsMargins(14, 12, 14, 12)
            title = QLabel(name)
            title.setObjectName("MetricTitle")
            value = QLabel("Loading..." if index < 2 else "Not configured")
            value.setObjectName("MetricValue")
            detail = QLabel("")
            detail.setObjectName("SmallText")
            detail.setWordWrap(True)
            layout.addWidget(title)
            layout.addWidget(value)
            layout.addWidget(detail)
            self.rows[name] = (value, detail)
            grid.addWidget(card, index // 3, index % 3)

        root.addLayout(grid)
        note = QLabel(
            "Future Excel-free operation requires actual production, stock, "
            "material, resource and dispatch data to flow from MPPS-native "
            "transactions or ERP/MES/WMS/scanner/machine integrations."
        )
        note.setObjectName("InfoBanner")
        note.setWordWrap(True)
        root.addWidget(note)
        root.addStretch()

    def refresh(self):
        self.tasks.submit(
            "admin.data_sources",
            load_data_sources_snapshot,
            on_result=self._apply,
            on_error=lambda _message: self.rows["PostgreSQL"][0].setText(
                "Unavailable"
            ),
        )

    def _apply(self, payload):
        payload = dict(payload or {})
        pg_value, pg_detail = self.rows["PostgreSQL"]
        pg_value.setText(str(payload.get("postgresql_status") or "Unavailable"))
        pg_detail.setText(
            str(payload.get("database_name") or "")
        )

        excel_value, excel_detail = self.rows["Daily Excel / OVEN"]
        excel_value.setText(
            _date_text(payload.get("latest_source_date"))
        )
        excel_detail.setText(
            str(
                payload.get("latest_source_name")
                or payload.get("last_excel_name")
                or "No committed source identified"
            )
        )

        for name, status in payload.get("future_integrations") or []:
            if name in self.rows:
                self.rows[name][0].setText(str(status))


class SystemHealthAdminPage(_AdminBasePage):
    def __init__(self, *, back_callback=None):
        super().__init__(back_callback=back_callback)
        self.values = {}
        self.details = {}
        self._build_ui()
        QTimer.singleShot(0, self.refresh)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(
            self._header(
                "System Health",
                "Read-only operational health summary. Heavy checks run in the background.",
                refresh_callback=self.refresh,
            )
        )

        grid = QGridLayout()
        grid.setSpacing(10)
        items = (
            ("database", "Database"),
            ("source", "Latest Data Source"),
            ("backup", "Last Backup"),
            ("jobs", "Background Jobs"),
            ("issues", "Data Issues"),
            ("status", "System Status"),
        )
        for i, (key, title_text) in enumerate(items):
            card = QFrame()
            card.setObjectName("MetricCard")
            layout = QVBoxLayout(card)
            value = QLabel("—")
            value.setObjectName("MetricValue")
            title = QLabel(title_text)
            title.setObjectName("MetricTitle")
            detail = QLabel("")
            detail.setObjectName("SmallText")
            detail.setWordWrap(True)
            layout.addWidget(value)
            layout.addWidget(title)
            layout.addWidget(detail)
            self.values[key] = value
            self.details[key] = detail
            grid.addWidget(card, i // 3, i % 3)

        root.addLayout(grid)
        self.message = QLabel(
            "System Health does not alter business data."
        )
        self.message.setObjectName("InfoBanner")
        self.message.setWordWrap(True)
        root.addWidget(self.message)
        root.addStretch()

    def refresh(self):
        self.message.setText("Refreshing health snapshot...")
        self.tasks.submit(
            "admin.system_health",
            load_admin_health_snapshot,
            on_result=self._apply,
            on_error=lambda _message: self.message.setText(
                "System health refresh failed."
            ),
        )

    def _apply(self, payload):
        payload = dict(payload or {})
        database = str(payload.get("database") or "Unavailable")
        self.values["database"].setText(database)
        self.details["database"].setText(
            str(payload.get("database_name") or "")
        )

        self.values["source"].setText(
            _date_text(payload.get("latest_source_date"))
        )
        self.details["source"].setText(
            str(payload.get("latest_source_name") or "")
        )

        self.values["backup"].setText(
            str(payload.get("last_backup") or "Not available")
        )
        self.details["backup"].setText(
            str(payload.get("last_backup_path") or "")
        )

        try:
            active_jobs = self.tasks.pool.activeThreadCount()
        except Exception:
            active_jobs = 0
        self.values["jobs"].setText(str(active_jobs))
        self.details["jobs"].setText("Active background worker(s)")

        issues = payload.get("quality_issues")
        self.values["issues"].setText(
            "—" if issues is None else str(issues)
        )
        self.details["issues"].setText(
            "No central issue table"
            if issues is None
            else "Recorded data-quality issue rows"
        )

        healthy = database == "Connected"
        self.values["status"].setText(
            "READY" if healthy else "ATTENTION"
        )
        self.details["status"].setText(
            "Core database reachable"
            if healthy
            else "Database requires attention"
        )
        self.message.setText("Health snapshot updated.")


class AdminControlCenterPage(QWidget):
    def __init__(self, open_callback=None):
        super().__init__()
        self.open_callback = open_callback
        self.tasks = TaskManager.instance()
        self.health_values = {}
        self._internal_pages = {}
        self._build_ui()
        QTimer.singleShot(0, self.refresh_health)

    def _build_ui(self):
        self.setStyleSheet(
            """
            QWidget {
                background:#f8fafc;
                color:#0f172a;
                font-family:"Segoe UI";
            }
            QFrame#AdminHeader,
            QFrame#AdminCard,
            QFrame#MetricCard,
            QFrame#AdminPanel {
                background:#ffffff;
                border:1px solid #dbe4ef;
                border-radius:16px;
            }
            QLabel#AdminTitle {
                color:#0f172a;
                font-size:23pt;
                font-weight:950;
            }
            QLabel#AdminSubtitle,
            QLabel#AdminPageSubtitle,
            QLabel#SmallText,
            QLabel#InfoText {
                color:#64748b;
                font-size:9pt;
                font-weight:650;
            }
            QLabel#AdminPageTitle {
                color:#0f172a;
                font-size:18pt;
                font-weight:950;
            }
            QLabel#CardTitle,
            QLabel#SectionTitle {
                color:#0f172a;
                font-size:12.5pt;
                font-weight:950;
            }
            QLabel#CardDescription {
                color:#64748b;
                font-size:9pt;
                font-weight:650;
            }
            QLabel#MetricValue,
            QLabel#LargeValue {
                color:#0f172a;
                font-size:15pt;
                font-weight:950;
            }
            QLabel#MetricTitle {
                color:#64748b;
                font-size:8.5pt;
                font-weight:850;
            }
            QLabel#StatusBadge {
                background:#f1f5f9;
                border:1px solid #cbd5e1;
                border-radius:9px;
                padding:7px 10px;
                color:#334155;
                font-weight:850;
            }
            QLabel#InfoBanner {
                background:#eff6ff;
                border:1px solid #bfdbfe;
                border-radius:10px;
                padding:10px 12px;
                color:#1e40af;
                font-weight:750;
            }
            QPushButton#PrimaryButton {
                background:#2563eb;
                color:white;
                border:none;
                border-radius:9px;
                padding:9px 14px;
                font-weight:900;
            }
            QPushButton#SecondaryButton {
                background:#e2e8f0;
                color:#0f172a;
                border:none;
                border-radius:9px;
                padding:9px 14px;
                font-weight:900;
            }
            QPushButton#DangerButton {
                background:#fee2e2;
                color:#991b1b;
                border:1px solid #fecaca;
                border-radius:9px;
                padding:9px 14px;
                font-weight:900;
            }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
                background:white;
                border:1px solid #cbd5e1;
                border-radius:8px;
                padding:7px 9px;
            }
            QCalendarWidget {
                background:white;
                border:1px solid #dbe4ef;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        self.dashboard = self._build_dashboard()
        self.stack.addWidget(self.dashboard)
        root.addWidget(self.stack)

    def _build_dashboard(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        header = QFrame()
        header.setObjectName("AdminHeader")
        row = QHBoxLayout(header)
        row.setContentsMargins(20, 15, 20, 15)

        left = QVBoxLayout()
        title = QLabel("Admin Control Center")
        title.setObjectName("AdminTitle")
        subtitle = QLabel(
            "System configuration, governance, integrations, backup and health. "
            "Operational AI diagnostics remain in AI / ML."
        )
        subtitle.setObjectName("AdminSubtitle")
        subtitle.setWordWrap(True)
        left.addWidget(title)
        left.addWidget(subtitle)
        row.addLayout(left, 1)

        refresh = QPushButton("Refresh Status")
        refresh.setObjectName("SecondaryButton")
        refresh.clicked.connect(self.refresh_health)
        row.addWidget(refresh)
        root.addWidget(header)

        metrics = QGridLayout()
        metrics.setSpacing(10)
        for index, (key, caption) in enumerate(
            (
                ("database", "Database"),
                ("backup", "Last Backup"),
                ("source", "Last Data Sync"),
                ("jobs", "Background Jobs"),
            )
        ):
            card = QFrame()
            card.setObjectName("MetricCard")
            layout = QVBoxLayout(card)
            value = QLabel("—")
            value.setObjectName("MetricValue")
            label = QLabel(caption)
            label.setObjectName("MetricTitle")
            layout.addWidget(value)
            layout.addWidget(label)
            self.health_values[key] = value
            metrics.addWidget(card, 0, index)
        root.addLayout(metrics)

        grid = QGridLayout()
        grid.setSpacing(12)
        for index, (title_text, description, action_key) in enumerate(
            CARD_DEFINITIONS
        ):
            card = QFrame()
            card.setObjectName("AdminCard")
            card.setMinimumHeight(150)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(16, 14, 16, 14)
            title = QLabel(title_text)
            title.setObjectName("CardTitle")
            description_label = QLabel(description)
            description_label.setObjectName("CardDescription")
            description_label.setWordWrap(True)

            button_row = QHBoxLayout()
            button_row.addStretch()
            button = QPushButton("Open")
            button.setObjectName("PrimaryButton")
            button.clicked.connect(
                lambda _checked=False, key=action_key: self._open(key)
            )
            button_row.addWidget(button)

            layout.addWidget(title)
            layout.addWidget(description_label, 1)
            layout.addLayout(button_row)
            grid.addWidget(card, index // 2, index % 2)

        root.addLayout(grid)
        root.addStretch()
        return page

    def refresh_health(self):
        self.health_values["database"].setText("Checking...")
        self.tasks.submit(
            "admin.dashboard.health",
            load_admin_health_snapshot,
            on_result=self._apply_health,
            on_error=lambda _message: self.health_values["database"].setText(
                "Unavailable"
            ),
        )

    def _apply_health(self, payload):
        payload = dict(payload or {})
        self.health_values["database"].setText(
            str(payload.get("database") or "Unavailable")
        )
        self.health_values["backup"].setText(
            str(payload.get("last_backup") or "Not available")
        )
        self.health_values["source"].setText(
            _date_text(payload.get("latest_source_date"))
        )
        try:
            active = self.tasks.pool.activeThreadCount()
        except Exception:
            active = 0
        self.health_values["jobs"].setText(str(active))

    def _show_dashboard(self):
        self.stack.setCurrentWidget(self.dashboard)
        self.refresh_health()

    def _internal(self, key):
        existing = self._internal_pages.get(key)
        if existing is not None:
            return existing

        if key == "factory_calendar":
            page = FactoryCalendarAdminPage(
                back_callback=self._show_dashboard
            )
        elif key == "planning_rules":
            page = PlanningRulesAdminPage(
                back_callback=self._show_dashboard
            )
        elif key == "data_sources":
            page = DataSourcesAdminPage(
                back_callback=self._show_dashboard
            )
        elif key == "system_health":
            page = SystemHealthAdminPage(
                back_callback=self._show_dashboard
            )
        elif key == "advanced_database":
            module = import_module("app.ui.admin_database_viewer_page")
            inner = module.AdminDatabaseViewerPage(None)
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(0, 0, 0, 0)
            header = _AdminBasePage(
                back_callback=self._show_dashboard
            )._header(
                "Advanced Database Tools",
                "Admin-only read-only PostgreSQL inspection.",
            )
            layout.addWidget(header)
            layout.addWidget(inner, 1)
        else:
            return None

        self._internal_pages[key] = page
        self.stack.addWidget(page)
        return page

    def _open(self, key):
        if key in {
            "users_roles",
            "backup_restore",
            "audit_log",
        }:
            if callable(self.open_callback):
                self.open_callback(key)
            return

        page = self._internal(key)
        if page is not None:
            self.stack.setCurrentWidget(page)


def create_admin_control_page(open_callback=None):
    return AdminControlCenterPage(open_callback=open_callback)
