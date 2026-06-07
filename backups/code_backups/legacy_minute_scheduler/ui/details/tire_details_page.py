from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.ui.details.machine_details_page import MachineDetailsPage
from app.ui.details.tire_master_data_page import TireMasterDataPage
from app.ui.details.tire_production_time_page import TireProductionTimePage


class TireDetailsPage(QWidget):
    MASTER_INDEX = 0
    PRODUCTION_TIME_INDEX = 1
    MACHINE_INDEX = 2

    def __init__(self):
        super().__init__()

        self.nav_buttons: list[QPushButton] = []

        self.master_page = TireMasterDataPage()
        self.production_time_page = TireProductionTimePage()
        self.machine_page = MachineDetailsPage()

        self.stack = QStackedWidget()
        self.stack.addWidget(self.master_page)
        self.stack.addWidget(self.production_time_page)
        self.stack.addWidget(self.machine_page)

        self._apply_module_styles()
        self._build_ui()
        self.navigate_sub_page(self.MASTER_INDEX)

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
                padding: 9px 16px;
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
        tab_layout.setSpacing(10)

        self._add_sub_nav_button(tab_layout, "Tire Master Data", self.MASTER_INDEX)
        self._add_sub_nav_button(tab_layout, "Tire Production Time", self.PRODUCTION_TIME_INDEX)
        self._add_sub_nav_button(tab_layout, "Machine Details", self.MACHINE_INDEX)
        tab_layout.addStretch()

        root.addWidget(tab_bar)
        root.addWidget(self.stack, 1)

    def _add_sub_nav_button(self, layout: QHBoxLayout, text: str, index: int) -> None:
        button = QPushButton(text)
        button.setObjectName("SubNavButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda checked=False, idx=index: self.navigate_sub_page(idx))

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

    def refresh(self) -> None:
        current_widget = self.stack.currentWidget()

        if hasattr(current_widget, "refresh"):
            current_widget.refresh()

