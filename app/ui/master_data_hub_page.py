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


class MasterDataHubPage(QWidget):
    def __init__(self, on_open_page: Callable[[int], None], page_indexes: dict[str, int]):
        super().__init__()
        self.on_open_page = on_open_page
        self.page_indexes = page_indexes

        self.setStyleSheet("""
            QFrame#HeaderCard, QFrame#MetricCard, QFrame#ModuleCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 18px;
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
                background: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 10px;
                padding: 5px 10px;
                font-size: 8pt;
                font-weight: 900;
            }

            QLabel#CapacityBadge {
                background: #eef2ff;
                color: #4338ca;
                border: 1px solid #c7d2fe;
                border-radius: 10px;
                padding: 5px 10px;
                font-size: 8pt;
                font-weight: 900;
            }

            QLabel#LegacyBadge {
                background: #fff7ed;
                color: #c2410c;
                border: 1px solid #fed7aa;
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

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(8)

        title = QLabel("Master Data Center")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Manage master data used for shipment planning, production capacity, material requirements and scheduling."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        return card

    def _build_metrics(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(12)

        metrics = [
            ("1", "Factory Capacity", "Line, mold, casing and time data"),
            ("1", "Tyre Item Master", "Item codes, descriptions and weights"),
            ("1", "Legacy Import", "Excel import kept only for transition"),
            ("Ready", "Planning Data", "Master data organized for planning logic"),
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

        title = QLabel("Master Data Modules")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(14)

        cards = [
            (
                "Factory Capacity",
                "CAPACITY DATA",
                "Open factory capacity page for production lines, molds, casings and capacity/time data.",
                "Factory Capacity",
                "capacity",
            ),
            (
                "Tyre Item Master",
                "ITEM MASTER",
                "Maintain tyre item codes, descriptions, weights, product group and active status.",
                "Tyre Item Master",
                "normal",
            ),
            (
                "Legacy Excel Import",
                "ADMIN / LEGACY",
                "Import old Excel files only during transition to database-driven planning.",
                "Legacy Excel Import",
                "legacy",
            ),
        ]

        for index, (name, badge, hint, key, card_type) in enumerate(cards):
            grid.addWidget(
                self._module_card(name, badge, hint, key, card_type),
                0,
                index,
            )

        layout.addLayout(grid)
        layout.addStretch()
        return panel

    def _module_card(self, name: str, badge_text: str, hint_text: str, key: str, card_type: str) -> QFrame:
        card = QFrame()
        card.setObjectName("ModuleCard")
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.mousePressEvent = lambda event, module_key=key: self._open_module(module_key)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        top = QHBoxLayout()
        badge = QLabel(badge_text)

        if card_type == "legacy":
            badge.setObjectName("LegacyBadge")
        elif card_type == "capacity":
            badge.setObjectName("CapacityBadge")
        else:
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
        button.clicked.connect(lambda checked=False, module_key=key: self._open_module(module_key))

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
