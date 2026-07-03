from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCalendarWidget,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.database import engine


class DashboardPage(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.setObjectName("DashboardPage")

        self.setStyleSheet("""
            QWidget#DashboardPage {
                background: #f3f6fb;
            }

            QFrame#HeaderCard, QFrame#MetricCard, QFrame#PanelCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 20px;
            }

            QLabel#Breadcrumb {
                color: #2563eb;
                font-size: 9pt;
                font-weight: 950;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 22pt;
                font-weight: 950;
            }

            QLabel#PageSubtitle {
                color: #64748b;
                font-size: 9.2pt;
                font-weight: 650;
            }

            QLabel#MetricValue {
                color: #020617;
                font-size: 22pt;
                font-weight: 950;
            }

            QLabel#MetricTitle {
                color: #0f172a;
                font-size: 10pt;
                font-weight: 950;
            }

            QLabel#MetricHint {
                color: #64748b;
                font-size: 8.6pt;
                font-weight: 650;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 15pt;
                font-weight: 950;
            }

            QLabel#SectionText {
                color: #334155;
                font-size: 9.2pt;
                font-weight: 650;
            }

            QLabel#StatusBadge {
                background: #eef2ff;
                color: #1d4ed8;
                border: 1px solid #c7d2fe;
                border-radius: 11px;
                padding: 6px 12px;
                font-size: 8.5pt;
                font-weight: 950;
            }

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 11px;
                padding: 9px 14px;
                font-size: 9pt;
                font-weight: 950;
            }

            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }

            QPushButton#SecondaryButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 11px;
                padding: 9px 14px;
                font-size: 9pt;
                font-weight: 950;
            }

            QPushButton#SecondaryButton:hover {
                background: #cbd5e1;
            }

            QProgressBar {
                background: #e2e8f0;
                border: none;
                border-radius: 8px;
                height: 16px;
                text-align: center;
                color: #0f172a;
                font-size: 8pt;
                font-weight: 900;
            }

            QProgressBar::chunk {
                background: #2563eb;
                border-radius: 8px;
            }

            QCalendarWidget {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
            }

            QCalendarWidget QWidget {
                background: #ffffff;
                color: #0f172a;
            }

            QCalendarWidget QToolButton {
                background: #eef2ff;
                color: #1d4ed8;
                border: 1px solid #c7d2fe;
                border-radius: 9px;
                padding: 6px 10px;
                font-weight: 900;
            }

            QCalendarWidget QAbstractItemView {
                background: #ffffff;
                color: #0f172a;
                selection-background-color: #2563eb;
                selection-color: #ffffff;
                gridline-color: #e2e8f0;
                outline: none;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        root.addWidget(self._build_header())
        root.addLayout(self._build_metrics())

        body = QHBoxLayout()
        body.setSpacing(16)
        body.addWidget(self._build_calendar_panel(), 1)
        body.addWidget(self._build_daily_plan_panel(), 1)
        root.addLayout(body, 1)

        root.addWidget(self._build_capacity_panel(), 0)

        self.refresh()

    def _build_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        breadcrumb = QLabel("Dashboard  /  Production Planning")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Production Planning Dashboard")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Summary view for shipment orders, production demand, capacity usage and daily planning status."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        self.today_badge = QLabel(date.today().strftime("%A, %Y-%m-%d"))
        self.today_badge.setObjectName("StatusBadge")
        self.today_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(text_area, 1)
        layout.addWidget(self.today_badge)

        return card

    def _build_metrics(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(14)

        self.metric_labels: dict[str, QLabel] = {}

        cards = [
            ("orders", "Customer Orders", "Orders currently included in production planning"),
            ("production_orders", "Production Orders", "Items requiring production after stock verification"),
            ("required_qty", "Required Production Qty", "Total quantity to be produced after stock check"),
            ("alerts", "Planning Alerts", "Orders or items needing planning attention"),
        ]

        for col, (key, title, hint) in enumerate(cards):
            grid.addWidget(self._metric_card(key, title, hint), 0, col)
            grid.setColumnStretch(col, 1)

        return grid

    def _metric_card(self, key: str, title: str, hint: str) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        value = QLabel("0")
        value.setObjectName("MetricValue")
        self.metric_labels[key] = value

        title_label = QLabel(title)
        title_label.setObjectName("MetricTitle")

        hint_label = QLabel(hint)
        hint_label.setObjectName("MetricHint")
        hint_label.setWordWrap(True)

        button = QPushButton("View details")
        button.setObjectName("SecondaryButton")

        layout.addWidget(value)
        layout.addWidget(title_label)
        layout.addWidget(hint_label)
        layout.addStretch()
        layout.addWidget(button)

        return card

    def _build_calendar_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("PanelCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(14)

        title = QLabel("Factory Working Calendar")
        title.setObjectName("SectionTitle")

        self.day_status = QLabel("Factory is operating 24/7. Production planning is allowed for this date.")
        self.day_status.setObjectName("SectionText")
        self.day_status.setWordWrap(True)

        self.calendar = QCalendarWidget()
        self.calendar.setMaximumHeight(270)
        self.calendar.setGridVisible(False)
        self.calendar.setSelectedDate(self.calendar.selectedDate().currentDate())

        note = QLabel("Click a date to review factory holiday, special working day or production availability.")
        note.setObjectName("SectionText")
        note.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(self.day_status)
        layout.addWidget(self.calendar, 1)
        layout.addWidget(note)

        return card

    def _build_daily_plan_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("PanelCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 16)
        layout.setSpacing(14)

        title = QLabel("Daily Production Plan")
        title.setObjectName("SectionTitle")

        subtitle = QLabel("Order-based daily production plan using line, mold, casing, cavity and capacity data.")
        subtitle.setObjectName("SectionText")
        subtitle.setWordWrap(True)

        self.plan_date = QLabel(f"Date: {date.today().strftime('%A, %Y-%m-%d')}")
        self.plan_date.setObjectName("SectionText")

        self.plan_status = QLabel("NO PRODUCTION REQUIRED")
        self.plan_status.setObjectName("StatusBadge")
        self.plan_status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.plan_date)
        layout.addWidget(self.plan_status, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(12)

        self.plan_fields: dict[str, QLabel] = {}

        fields = [
            ("planned_qty", "Planned Qty"),
            ("capacity", "Available Production Capacity"),
            ("usage", "Capacity Usage"),
            ("cavities", "Active Press / Cavities"),
        ]

        for key, label in fields:
            row = QHBoxLayout()
            name = QLabel(label)
            name.setObjectName("SectionText")

            value = QLabel("0")
            value.setObjectName("SectionText")
            value.setAlignment(Qt.AlignmentFlag.AlignRight)
            self.plan_fields[key] = value

            row.addWidget(name, 1)
            row.addWidget(value)
            layout.addLayout(row)

        layout.addStretch()

        summary = QLabel("This dashboard summarizes the current production planning position for the selected date.")
        summary.setObjectName("SectionText")
        summary.setWordWrap(True)
        layout.addWidget(summary)

        return card

    def _build_capacity_panel(self) -> QFrame:
        card = QFrame()
        card.setObjectName("PanelCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 12, 18, 14)
        layout.setSpacing(10)

        title = QLabel("Production Capacity Usage")
        title.setObjectName("SectionTitle")

        subtitle = QLabel("Planned production quantity compared with available line, mold and cavity capacity.")
        subtitle.setObjectName("SectionText")
        subtitle.setWordWrap(True)

        self.capacity_bar = QProgressBar()
        self.capacity_bar.setRange(0, 100)
        self.capacity_bar.setValue(0)
        self.capacity_bar.setFormat("0 planned / 0 quantity capacity")

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self.capacity_bar)

        return card

    def refresh(self) -> None:
        values = self._load_dashboard_values()

        self.metric_labels["orders"].setText(str(values["orders"]))
        self.metric_labels["production_orders"].setText(str(values["production_orders"]))
        self.metric_labels["required_qty"].setText(str(values["required_qty"]))
        self.metric_labels["alerts"].setText(str(values["alerts"]))

        self.plan_fields["planned_qty"].setText(str(values["required_qty"]))
        self.plan_fields["capacity"].setText(str(values["capacity"]))
        self.plan_fields["usage"].setText(f"{values['usage_percent']}%")
        self.plan_fields["cavities"].setText(str(values["active_cavities"]))

        self.capacity_bar.setValue(int(values["usage_percent"]))
        self.capacity_bar.setFormat(f"{values['required_qty']} planned / {values['capacity']} quantity capacity")

    refresh_page = refresh
    load_data = refresh

    def _load_dashboard_values(self) -> dict:
        values = {
            "orders": 0,
            "production_orders": 0,
            "required_qty": 0,
            "alerts": 0,
            "capacity": 0,
            "usage_percent": 0,
            "active_cavities": 0,
        }

        try:
            with engine.connect() as conn:
                values["orders"] = self._safe_count(conn, "orders")
                values["production_orders"] = self._safe_count(conn, "order_items")
                values["required_qty"] = self._safe_sum(conn, "order_items", "quantity")
                values["active_cavities"] = self._safe_count_where(
                    conn,
                    "production_line_cavities",
                    "LOWER(status) = 'active'",
                )
                values["capacity"] = values["active_cavities"]

                if values["capacity"] > 0:
                    values["usage_percent"] = min(100, round((values["required_qty"] / values["capacity"]) * 100))

        except Exception:
            pass

        return values

    def _table_exists(self, conn, table_name: str) -> bool:
        return bool(conn.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                )
            """),
            {"table_name": table_name},
        ).scalar_one())

    def _column_exists(self, conn, table_name: str, column_name: str) -> bool:
        return bool(conn.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name = :table_name
                      AND column_name = :column_name
                )
            """),
            {"table_name": table_name, "column_name": column_name},
        ).scalar_one())

    def _safe_count(self, conn, table_name: str) -> int:
        if not self._table_exists(conn, table_name):
            return 0
        return int(conn.execute(text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one() or 0)

    def _safe_count_where(self, conn, table_name: str, where_clause: str) -> int:
        if not self._table_exists(conn, table_name):
            return 0
        return int(conn.execute(text(f"SELECT COUNT(*) FROM {table_name} WHERE {where_clause}")).scalar_one() or 0)

    def _safe_sum(self, conn, table_name: str, column_name: str) -> int:
        if not self._table_exists(conn, table_name):
            return 0
        if not self._column_exists(conn, table_name, column_name):
            return 0
        return int(conn.execute(text(f"SELECT COALESCE(SUM({column_name}), 0) FROM {table_name}")).scalar_one() or 0)


ProductionDashboardPage = DashboardPage
PlanningDashboardPage = DashboardPage
MainDashboardPage = DashboardPage
