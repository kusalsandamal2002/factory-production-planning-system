from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class FactoryCapacityPage(QWidget):
    def __init__(
        self,
        on_open_page: Callable[[int], None],
        on_back: Callable[[], None],
        page_indexes: dict[str, int],
    ):
        super().__init__()
        self.on_open_page = on_open_page
        self.on_back = on_back
        self.page_indexes = page_indexes

        self.setStyleSheet("""
            QFrame#HeaderCard, QFrame#MetricCard, QFrame#ModuleCard, QFrame#InfoCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 18px;
            }

            QLabel#Breadcrumb {
                color: #2563eb;
                font-size: 9pt;
                font-weight: 900;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 24pt;
                font-weight: 950;
            }

            QLabel#PageSubtitle, QLabel#CardHint {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 15pt;
                font-weight: 950;
            }

            QLabel#CardTitle {
                color: #0f172a;
                font-size: 14pt;
                font-weight: 950;
            }

            QLabel#MetricValue {
                color: #020617;
                font-size: 22pt;
                font-weight: 950;
            }

            QLabel#MetricLabel {
                color: #64748b;
                font-size: 9pt;
                font-weight: 800;
            }

            QLabel#Badge {
                background: #eef2ff;
                color: #4338ca;
                border: 1px solid #c7d2fe;
                border-radius: 10px;
                padding: 5px 10px;
                font-size: 8pt;
                font-weight: 900;
            }

            QPushButton#OpenButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 11px;
                padding: 10px 16px;
                font-size: 9pt;
                font-weight: 950;
            }

            QPushButton#OpenButton:hover {
                background: #1d4ed8;
            }

            QPushButton#BackButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 11px;
                padding: 10px 16px;
                font-size: 9pt;
                font-weight: 950;
            }

            QPushButton#BackButton:hover {
                background: #cbd5e1;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self._build_header())
        root.addLayout(self._build_metrics())
        root.addWidget(self._build_modules(), 1)

    def _build_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(7)

        breadcrumb = QLabel("Master Data  /  Factory Capacity")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Factory Capacity")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Manage operational capacity master data used for shipment receive date calculation, production scheduling and line loading."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        back_button = QPushButton("Back to Master Data")
        back_button.setObjectName("BackButton")
        back_button.clicked.connect(self.on_back)

        layout.addLayout(text_area, 1)
        layout.addWidget(back_button)

        return card

    def _build_metrics(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(12)

        metrics = [
            ("4", "Capacity Modules", "Line, mold, casing and time masters"),
            ("86", "Active Cavities", "200T, 400T, 800T and SuperSolid"),
            ("243", "Mold Capacity", "200T, 400T and 800T mold count"),
            ("Ready", "Planning Base", "Capacity data prepared for scheduling"),
        ]

        for col, (value, label, hint) in enumerate(metrics):
            grid.addWidget(self._metric_card(value, label, hint), 0, col)

        return grid

    def _metric_card(self, value: str, label: str, hint: str) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)

        value_label = QLabel(value)
        value_label.setObjectName("MetricValue")

        label_widget = QLabel(label)
        label_widget.setObjectName("MetricLabel")

        hint_widget = QLabel(hint)
        hint_widget.setObjectName("CardHint")
        hint_widget.setWordWrap(True)

        layout.addWidget(value_label)
        layout.addWidget(label_widget)
        layout.addWidget(hint_widget)

        return card

    def _build_modules(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("HeaderCard")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Factory Capacity Modules")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(14)

        cards = [
            (
                "Production Lines",
                "LINE MASTER",
                "Maintain 200T, 400T, 800T and SuperSolid production line capacity.",
            ),
            (
                "Mold Master",
                "MOLD DATA",
                "Maintain mold availability, mold count and item compatibility.",
            ),
            (
                "Casing Master",
                "CASING DATA",
                "Maintain casing type availability for 400T and 800T production lines.",
            ),
            (
                "Capacity / Time Master",
                "TIME DATA",
                "Maintain cavity capacity, production time, curing time and shift parameters.",
            ),
        ]

        for index, (name, badge, hint) in enumerate(cards):
            grid.addWidget(self._module_card(name, badge, hint), index // 2, index % 2)

        layout.addLayout(grid)
        layout.addStretch()

        return panel

    def _module_card(self, name: str, badge_text: str, hint_text: str) -> QFrame:
        card = QFrame()
        card.setObjectName("ModuleCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.mousePressEvent = lambda event, module_key=name: self._open_module(module_key)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        top = QHBoxLayout()
        badge = QLabel(badge_text)
        badge.setObjectName("Badge")
        top.addWidget(badge)
        top.addStretch()

        title = QLabel(name)
        title.setObjectName("CardTitle")

        hint = QLabel(hint_text)
        hint.setObjectName("CardHint")
        hint.setWordWrap(True)

        button = QPushButton("Open Module")
        button.setObjectName("OpenButton")
        button.clicked.connect(lambda checked=False, module_key=name: self._open_module(module_key))

        layout.addLayout(top)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addStretch()
        layout.addWidget(button)

        return card

    def _open_module(self, key: str) -> None:
        index = self.page_indexes.get(key)
        if index is not None:
            self.on_open_page(index)
