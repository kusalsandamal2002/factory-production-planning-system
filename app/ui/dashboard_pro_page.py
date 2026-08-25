from __future__ import annotations

import time
from typing import Any

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.core.task_manager import TaskManager


def _fmt(value, suffix="", decimals=0):
    if value is None:
        return "—"
    try:
        if decimals:
            return f"{float(value):,.{decimals}f}{suffix}"
        return f"{int(round(float(value))):,}{suffix}"
    except Exception:
        return str(value)


class DashboardProPage(QWidget):
    CACHE_SECONDS = 30.0

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.tasks = TaskManager.instance()
        self._refresh_running = False
        self._transient_retry_count = 0
        self._cache = None
        self._cache_time = 0.0
        self._build_ui()

        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(45000)
        self._refresh_timer.timeout.connect(self._background_if_visible)
        self._refresh_timer.start()

        QTimer.singleShot(0, self.refresh_async)

    def _build_ui(self):
        self.setStyleSheet("""
            QWidget { font-family:"Segoe UI"; }
            QFrame#Header, QFrame#Metric, QFrame#Panel {
                background:#ffffff;
                border:1px solid #dbe4ef;
                border-radius:16px;
            }
            QLabel#Crumb { color:#2563eb; font-weight:950; }
            QLabel#Title { color:#0f172a; font-size:24pt; font-weight:950; }
            QLabel#Sub { color:#64748b; font-size:9pt; font-weight:650; }
            QLabel#Badge {
                background:#ecfdf5; color:#047857; border:1px solid #a7f3d0;
                border-radius:12px; padding:8px 12px; font-weight:950;
            }
            QLabel#MetricValue { color:#0f172a; font-size:20pt; font-weight:950; }
            QLabel#MetricTitle { color:#475569; font-size:8.5pt; font-weight:850; }
            QLabel#Section { color:#0f172a; font-size:14pt; font-weight:950; }
            QLabel#Body { color:#334155; font-size:9pt; font-weight:700; }
            QLabel#Warning { color:#b45309; font-size:9pt; font-weight:850; }
            QPushButton {
                background:#e2e8f0; color:#0f172a; border:none; border-radius:9px;
                padding:8px 13px; font-weight:900;
            }
            QProgressBar {
                border:none; border-radius:7px; background:#e2e8f0;
                min-height:14px; text-align:center; color:#0f172a; font-weight:850;
            }
            QProgressBar::chunk { background:#2563eb; border-radius:7px; }
            QTableWidget {
                background:#fff; alternate-background-color:#f8fafc;
                border:1px solid #dbe4ef; gridline-color:#e2e8f0;
            }
            QHeaderView::section {
                background:#edf3f9; color:#1e293b; border:none;
                border-right:1px solid #dbe4ef; border-bottom:1px solid #dbe4ef;
                padding:8px; font-weight:950;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        header = QFrame()
        header.setObjectName("Header")
        hr = QHBoxLayout(header)
        hr.setContentsMargins(22, 14, 20, 14)

        left = QVBoxLayout()
        crumb = QLabel("Dashboard / Operations")
        crumb.setObjectName("Crumb")
        title = QLabel("Production Planning Dashboard")
        title.setObjectName("Title")
        sub = QLabel(
            "Live summary of shipments, production, stock, factory capacity, "
            "materials and operational AI signals."
        )
        sub.setObjectName("Sub")
        sub.setWordWrap(True)
        left.addWidget(crumb)
        left.addWidget(title)
        left.addWidget(sub)
        hr.addLayout(left, 1)

        self.source_badge = QLabel("LIVE OVEN\n—")
        self.source_badge.setObjectName("Badge")
        self.source_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.source_badge.setMinimumWidth(170)
        hr.addWidget(self.source_badge)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(lambda: self.refresh_async(force=True))
        hr.addWidget(self.refresh_btn)

        root.addWidget(header)

        self.metric_labels = {}
        metric_grid = QGridLayout()
        metric_grid.setSpacing(10)
        metrics = (
            ("shipments", "Active Shipments"),
            ("shipment_qty", "Shipment Qty"),
            ("production_gap", "Production Gap"),
            ("fg_stock", "Usable FG Stock"),
            ("planned", "Today Planned"),
            ("capacity", "Daily Capacity"),
            ("critical", "Critical / Late"),
            ("materials", "Material Shortages"),
        )
        for i, (key, caption) in enumerate(metrics):
            metric_grid.addWidget(self._metric_card(key, caption), i // 4, i % 4)
        root.addLayout(metric_grid)

        middle = QHBoxLayout()
        middle.setSpacing(10)
        middle.addWidget(self._production_panel(), 1)
        middle.addWidget(self._shipment_panel(), 1)
        root.addLayout(middle)

        lower = QHBoxLayout()
        lower.setSpacing(10)
        lower.addWidget(self._capacity_panel(), 1)
        lower.addWidget(self._stock_panel(), 1)
        lower.addWidget(self._insight_panel(), 1)
        root.addLayout(lower, 1)

        self.load_progress = QProgressBar()
        self.load_progress.setRange(0, 0)
        self.load_progress.setTextVisible(False)
        self.load_progress.setMaximumHeight(6)
        self.load_progress.hide()
        root.addWidget(self.load_progress)

    def _metric_card(self, key, caption):
        card = QFrame()
        card.setObjectName("Metric")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 11, 14, 11)
        value = QLabel("—")
        value.setObjectName("MetricValue")
        title = QLabel(caption)
        title.setObjectName("MetricTitle")
        self.metric_labels[key] = value
        layout.addWidget(value)
        layout.addWidget(title)
        return card

    def _panel(self, title_text):
        card = QFrame()
        card.setObjectName("Panel")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 13, 16, 14)
        title = QLabel(title_text)
        title.setObjectName("Section")
        layout.addWidget(title)
        return card, layout

    def _production_panel(self):
        card, layout = self._panel("Today's Production")
        self.production_status = QLabel("Awaiting latest plan")
        self.production_status.setObjectName("Body")
        layout.addWidget(self.production_status)

        self.production_rows = {}
        for key, label in (
            ("planned", "Planned Qty"),
            ("actual", "Completed Qty"),
            ("remaining", "Remaining Qty"),
            ("achievement", "Achievement"),
        ):
            row = QHBoxLayout()
            name = QLabel(label)
            name.setObjectName("Body")
            value = QLabel("—")
            value.setObjectName("Body")
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.production_rows[key] = value
            row.addWidget(name, 1)
            row.addWidget(value)
            layout.addLayout(row)

        self.production_bar = QProgressBar()
        self.production_bar.setRange(0, 100)
        self.production_bar.setValue(0)
        layout.addWidget(self.production_bar)
        layout.addStretch()
        return card

    def _shipment_panel(self):
        card, layout = self._panel("Shipment Delivery Risk")
        self.shipment_table = QTableWidget(0, 4)
        self.shipment_table.setHorizontalHeaderLabels(
            ["Shipment", "Target", "Can Out", "Gap"]
        )
        self.shipment_table.verticalHeader().setVisible(False)
        self.shipment_table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.shipment_table.setSelectionMode(
            QAbstractItemView.SelectionMode.NoSelection
        )
        self.shipment_table.setAlternatingRowColors(True)
        self.shipment_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        for c in (1, 2, 3):
            self.shipment_table.horizontalHeader().setSectionResizeMode(
                c, QHeaderView.ResizeMode.ResizeToContents
            )
        layout.addWidget(self.shipment_table, 1)
        return card

    def _capacity_panel(self):
        card, layout = self._panel("Factory Capacity")
        self.capacity_text = QLabel("Awaiting capacity snapshot")
        self.capacity_text.setObjectName("Body")
        self.capacity_text.setWordWrap(True)
        self.capacity_bar = QProgressBar()
        self.capacity_bar.setRange(0, 100)
        self.capacity_bar.setValue(0)
        layout.addWidget(self.capacity_text)
        layout.addWidget(self.capacity_bar)
        layout.addStretch()
        return card

    def _stock_panel(self):
        card, layout = self._panel("Stock & Material Readiness")
        self.stock_text = QLabel("Awaiting stock and material snapshot")
        self.stock_text.setObjectName("Body")
        self.stock_text.setWordWrap(True)
        layout.addWidget(self.stock_text)
        layout.addStretch()
        return card

    def _insight_panel(self):
        card, layout = self._panel("Needs Attention")
        self.insight_label = QLabel("Loading operational insights...")
        self.insight_label.setObjectName("Warning")
        self.insight_label.setWordWrap(True)
        self.insight_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.insight_label, 1)
        return card

    def _background_if_visible(self):
        if self.isVisible():
            self.refresh_async(force=False)

    def refresh_async(self, force=False):
        if (
            not force
            and self._cache is not None
            and time.monotonic() - self._cache_time < self.CACHE_SECONDS
        ):
            self._apply(self._cache)
            return

        if self._refresh_running:
            return

        self._refresh_running = True
        self.load_progress.show()
        self.refresh_btn.setEnabled(False)

        def dashboard_job():
            from app.services.dashboard_snapshot_service import DashboardSnapshotService

            return DashboardSnapshotService.load()

        self.tasks.submit(
            "dashboard.snapshot",
            dashboard_job,
            on_result=self._loaded,
            on_error=self._failed,
            replace=True,
        )

    def _loaded(self, payload):
        self._refresh_running = False
        self._transient_retry_count = 0
        self.load_progress.hide()
        self.refresh_btn.setEnabled(True)
        self._cache = dict(payload or {})
        self._cache_time = time.monotonic()
        self._apply(self._cache)

    def _failed(self, message):
        self._refresh_running = False
        lower = str(message or "").lower()
        transient = any(
            token in lower
            for token in (
                "system is in recovery",
                "database system is starting up",
                "the database system is starting up",
                "cannot connect now",
                "connection refused",
                "server closed the connection unexpectedly",
            )
        )

        if transient and self._transient_retry_count < 8:
            self._transient_retry_count += 1
            self.insight_label.setText(
                "Database is finishing startup. Dashboard will retry automatically."
            )
            QTimer.singleShot(
                min(2500, 400 + self._transient_retry_count * 250),
                lambda: self.refresh_async(force=True),
            )
            return

        self.load_progress.hide()
        self.refresh_btn.setEnabled(True)
        self.insight_label.setText(
            "Dashboard background refresh failed. Use Refresh after the database is ready."
        )

    def _apply(self, data):
        source_date = data.get("source_date")
        self.source_badge.setText(
            "LIVE OVEN\n" + (source_date.isoformat() if hasattr(source_date, "isoformat") else _display_date(source_date))
        )
        self.source_badge.setToolTip(str(data.get("source_workbook") or ""))

        values = {
            "shipments": _fmt(data.get("shipment_count")),
            "shipment_qty": _fmt(data.get("shipment_qty")),
            "production_gap": _fmt(data.get("production_gap")),
            "fg_stock": _fmt(data.get("fg_stock")),
            "planned": _fmt(data.get("planned_qty")),
            "capacity": _fmt(data.get("capacity_qty")),
            "critical": _fmt(data.get("critical_shipments")),
            "materials": _fmt(data.get("material_exceptions")),
        }
        for key, value in values.items():
            self.metric_labels[key].setText(value)

        planned = data.get("planned_qty")
        actual = data.get("actual_qty")
        remaining = data.get("remaining_qty")
        achievement = data.get("achievement_pct")
        self.production_rows["planned"].setText(_fmt(planned))
        self.production_rows["actual"].setText(_fmt(actual))
        self.production_rows["remaining"].setText(_fmt(remaining))
        self.production_rows["achievement"].setText(
            _fmt(achievement, "%", 1)
        )
        if planned is None:
            self.production_status.setText("Awaiting latest committed production plan")
        elif planned == 0:
            self.production_status.setText("No production required for the latest plan")
        else:
            self.production_status.setText("Latest committed plan loaded")
        self.production_bar.setValue(
            int(max(0, min(100, achievement or 0)))
        )

        usage = data.get("capacity_usage_pct")
        self.capacity_bar.setValue(int(max(0, min(100, usage or 0))))
        self.capacity_text.setText(
            "Active lines: "
            + _fmt(data.get("active_lines"))
            + "\nActive cavities: "
            + _fmt(data.get("active_cavities"))
            + "\nEstimated daily output: "
            + _fmt(data.get("estimated_daily_capacity_qty"))
            + " tyres/day\nBreakdown / unavailable: "
            + _fmt(data.get("breakdown_cavities"))
            + "\nToday capacity utilisation: "
            + _fmt(usage, "%", 1)
        )

        self.stock_text.setText(
            "Usable FG Stock: "
            + _fmt(data.get("fg_stock"))
            + "\nStock allocated to active shipments: "
            + _fmt(data.get("stock_covered_qty"))
            + "\nScrap: "
            + _fmt(data.get("scrap"))
            + "\nBlocked: "
            + _fmt(data.get("blocked"))
            + "\nMaterial shortages: "
            + _fmt(data.get("material_exceptions"))
        )

        insights = list(data.get("insights") or [])
        self.insight_label.setText(
            "\n".join(f"• {item}" for item in insights)
            if insights
            else "No high-priority exception detected."
        )

        urgent = list(data.get("urgent_shipments") or [])
        self.shipment_table.setRowCount(len(urgent))
        for r, row in enumerate(urgent):
            values = (
                row.get("shipment_name") or row.get("shipment_no") or "-",
                _display_date(row.get("target_date")),
                _display_date(row.get("factory_can_receive_date")),
                _fmt(row.get("production_gap")),
            )
            for c, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if c == 3 and int(row.get("production_gap") or 0) > 0:
                    item.setForeground(QColor("#b45309"))
                self.shipment_table.setItem(r, c, item)

    def notify_source_changed(self, *args, **kwargs):
        self._cache = None
        self.refresh_async(force=True)

    def refresh(self):
        self.refresh_async(force=True)

    refresh_page = refresh
    load_data = refresh


def _display_date(value):
    if value is None:
        return "—"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    value = str(value).strip()
    return value or "—"


DashboardPage = DashboardProPage
ProductionDashboardPage = DashboardProPage
PlanningDashboardPage = DashboardProPage
MainDashboardPage = DashboardProPage
