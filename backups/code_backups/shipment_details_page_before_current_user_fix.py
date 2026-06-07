from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import func, select

from app.database import get_session
from app.models import Order
from app.ui.details.completed_orders_page import CompletedOrdersPage
from app.ui.details.history_shipments_page import HistoryShipmentsPage
from app.ui.details.overdue_orders_page import OverdueOrdersPage
from app.ui.details.pending_orders_page import PendingOrdersPage
from app.ui.details.total_shipments_page import TotalShipmentsPage


class ShipmentDetailsPage(QWidget):
    TOTAL_INDEX = 0
    COMPLETED_INDEX = 1
    PENDING_INDEX = 2
    OVERDUE_INDEX = 3
    HISTORY_INDEX = 4

    COMPLETED_STATUSES = ("COMPLETED", "PRODUCTION_COMPLETED", "CLOSED")
    CANCELLED_STATUSES = ("CANCELLED", "CANCELED")
    SHIPPED_STATUSES = (
        "SHIPPED",
        "DISPATCHED",
        "DELIVERED",
        "RECEIVED",
        "COMPLETED",
        "PRODUCTION_COMPLETED",
        "CLOSED",
    )
    HISTORY_STATUSES = SHIPPED_STATUSES + CANCELLED_STATUSES
    CLOSED_STATUSES = COMPLETED_STATUSES + CANCELLED_STATUSES

    def __init__(self, current_user=None):
        super().__init__()

        self.current_user = current_user
        self.nav_buttons: list[QPushButton] = []

        self.stack = QStackedWidget()

        self.total_shipments_page = TotalShipmentsPage(
            on_back=self.back_to_total_shipments,
            current_user=self.current_user
        )
        self.completed_orders_page = self._create_detail_page(CompletedOrdersPage)
        self.pending_orders_page = self._create_detail_page(PendingOrdersPage)
        self.overdue_orders_page = self._create_detail_page(OverdueOrdersPage)
        self.history_shipments_page = self._create_detail_page(HistoryShipmentsPage)

        self.stack.addWidget(self.total_shipments_page)
        self.stack.addWidget(self.completed_orders_page)
        self.stack.addWidget(self.pending_orders_page)
        self.stack.addWidget(self.overdue_orders_page)
        self.stack.addWidget(self.history_shipments_page)

        self._apply_module_styles()
        self._build_ui()
        self.navigate_sub_page(self.TOTAL_INDEX)

    def _create_detail_page(self, page_class):
        try:
            return page_class(on_back=self.back_to_total_shipments)
        except TypeError:
            return page_class()

    def _apply_module_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#CompactTabBar {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }

            QPushButton#SubNavButton {
                background: #e2e8f0;
                color: #334155;
                border: none;
                border-radius: 10px;
                padding: 9px 14px;
                font-weight: 950;
            }

            QPushButton#SubNavButton:hover {
                background: #cbd5e1;
                color: #0f172a;
            }

            QPushButton#SubNavButton[active="true"] {
                background: #2563eb;
                color: #ffffff;
            }

            QPushButton#RefreshButton {
                background: #f1f5f9;
                color: #0f172a;
                border: 1px solid #dbeafe;
                border-radius: 10px;
                padding: 9px 16px;
                font-weight: 950;
            }

            QPushButton#RefreshButton:hover {
                background: #e0f2fe;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        tab_bar = QFrame()
        tab_bar.setObjectName("CompactTabBar")

        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(18, 14, 18, 14)
        tab_layout.setSpacing(8)

        self._add_sub_nav_button(tab_layout, "Total Shipments", self.TOTAL_INDEX)
        self._add_sub_nav_button(tab_layout, "Production Completed", self.COMPLETED_INDEX)
        self._add_sub_nav_button(tab_layout, "To Be Completed", self.PENDING_INDEX)
        self._add_sub_nav_button(tab_layout, "Overdue Orders", self.OVERDUE_INDEX)
        self._add_sub_nav_button(tab_layout, "Shipment History", self.HISTORY_INDEX)

        tab_layout.addStretch()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("RefreshButton")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh)
        tab_layout.addWidget(self.refresh_btn)

        root.addWidget(tab_bar)
        root.addWidget(self.stack, 1)

    def _add_sub_nav_button(self, layout: QHBoxLayout, text: str, index: int) -> None:
        button = QPushButton(text)
        button.setObjectName("SubNavButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setProperty("base_text", text)
        button.clicked.connect(
            lambda checked=False, idx=index: self.navigate_sub_page(idx)
        )

        self.nav_buttons.append(button)
        layout.addWidget(button)

    def navigate_sub_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

        for button_index, button in enumerate(self.nav_buttons):
            button.setProperty("active", "true" if button_index == index else "false")
            button.style().unpolish(button)
            button.style().polish(button)

        widget = self.stack.widget(index)

        if hasattr(widget, "refresh"):
            widget.refresh()

        self.refresh_tab_counts_only()

    def back_to_total_shipments(self) -> None:
        self.navigate_sub_page(self.TOTAL_INDEX)

    def refresh(self) -> None:
        current_widget = self.stack.currentWidget()

        if hasattr(current_widget, "refresh"):
            current_widget.refresh()

        self.refresh_tab_counts_only()

    def refresh_tab_counts_only(self) -> None:
        try:
            metrics = self._load_metrics()
        except Exception as exc:
            QMessageBox.warning(self, "Shipment Summary Error", str(exc))
            return

        self._update_tab_counts(metrics)

    def _load_metrics(self) -> dict[str, int]:
        today = date.today()

        with get_session() as session:
            total = session.scalar(select(func.count(Order.id))) or 0

            completed = session.scalar(
                select(func.count(Order.id)).where(
                    func.upper(Order.status).in_(self.COMPLETED_STATUSES)
                )
            ) or 0

            overdue = session.scalar(
                select(func.count(Order.id)).where(
                    Order.manager_confirmed_receive_date < today,
                    ~func.upper(Order.status).in_(self.CLOSED_STATUSES),
                )
            ) or 0

            pending = session.scalar(
                select(func.count(Order.id)).where(
                    Order.manager_confirmed_receive_date >= today,
                    ~func.upper(Order.status).in_(self.CLOSED_STATUSES),
                )
            ) or 0

            history = session.scalar(
                select(func.count(Order.id)).where(
                    func.upper(Order.status).in_(self.HISTORY_STATUSES)
                )
            ) or 0

        return {
            "total": int(total),
            "completed": int(completed),
            "pending": int(pending),
            "overdue": int(overdue),
            "history": int(history),
        }

    def _update_tab_counts(self, metrics: dict[str, int]) -> None:
        count_map = {
            self.TOTAL_INDEX: metrics.get("total", 0),
            self.COMPLETED_INDEX: metrics.get("completed", 0),
            self.PENDING_INDEX: metrics.get("pending", 0),
            self.OVERDUE_INDEX: metrics.get("overdue", 0),
            self.HISTORY_INDEX: metrics.get("history", 0),
        }

        for index, button in enumerate(self.nav_buttons):
            base_text = button.property("base_text") or button.text()
            button.setText(f"{base_text} ({count_map.get(index, 0)})")

