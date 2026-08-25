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
        self.current_view = "main"

        self.setStyleSheet(
            """
            QFrame#HeaderCard,
            QFrame#MetricCard,
            QFrame#ModuleCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 18px;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 24pt;
                font-weight: 950;
            }

            QLabel#PageSubtitle,
            QLabel#CardHint {
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

            QLabel#StockBadge {
                background: #ecfdf5;
                color: #047857;
                border: 1px solid #a7f3d0;
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
            """
        )

        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(0, 0, 0, 0)
        self.root.setSpacing(16)

        self.render_main_view()

    def _clear_root(self) -> None:
        while self.root.count():
            item = self.root.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

    def render_main_view(self) -> None:
        self.current_view = "main"
        self._clear_root()

        self.root.addWidget(
            self._build_header(
                "Master Data Center",
                "Manage master data used for shipment planning, production capacity, stock control, material requirements and scheduling.",
            )
        )

        # V11: remove decorative summary cards. The Master Data Center is now
        # module-first so the working area starts immediately below the header.
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
                "Open factory resource page for production lines, cavities, molds and casings.",
                "Factory Capacity",
                "capacity",
            ),
            (
                "Tyre Item Master",
                "ITEM MASTER",
                "Maintain tyre SAP codes, descriptions, weights, product group and active status.",
                "Tyre Item Master",
                "normal",
            ),
            (
                "Stock Master",
                "STOCK CONTROL",
                "Open the same Stock Master workspace used by the Data sidebar for monthly stock, current stock, final tyre stock and daily stock.",
                "Stock Master",
                "stock",
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
                index // 2,
                index % 2,
            )

        layout.addLayout(grid)
        layout.addStretch()

        self.root.addWidget(panel, 1)

    def render_stock_view(self) -> None:
        # Canonical Stock Master redirect: never show a second stock UI.
        index = self.page_indexes.get("Stock Master")
        if index is not None:
            self.on_open_page(index)
            return

        self.current_view = "stock"
        self._clear_root()

        header = self._build_header(
            "Stock Master",
            "Select the stock module you want to manage. Stock balances are used for planning and delivery decisions.",
            show_back=True,
        )

        self.root.addWidget(header)

        panel = QFrame()
        panel.setObjectName("HeaderCard")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Stock Modules")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(14)

        grid.addWidget(
            self._module_card(
                "Monthly Stock",
                "MONTHLY OVEN STOCK + ML",
                "View one selected month at a time. FINAL stock comes from next-month PROD D/E/F; the current LIVE month comes from PROD HS/E/F with ML trend, forecast and risk.",
                "Monthly Stock",
                "stock",
            ),
            0,
            0,
        )

        grid.addWidget(
            self._module_card(
                "Final Tyre Stock",
                "SAP STOCK",
                "Manage final tyre stock balances by SAP Code. Includes FG, QC, Scrap, Blocked and Available stock.",
                "Final Tyre Stock",
                "stock",
            ),
            0,
            1,
        )

        grid.addWidget(
            self._module_card(
                "Daily Stock",
                "DAILY PRODUCTION",
                "Select a date, import daily production Excel, maintain daily stock quantities and export professional Excel reports.",
                "Daily Stock",
                "stock",
            ),
            1,
            0,
        )

        layout.addLayout(grid)
        layout.addStretch()

        self.root.addWidget(panel, 1)

    def _build_header(self, title_text: str, subtitle_text: str, show_back: bool = False) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        title_box = QVBoxLayout()
        title_box.setSpacing(8)

        title = QLabel(title_text)
        title.setObjectName("PageTitle")

        subtitle = QLabel(subtitle_text)
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        layout.addLayout(title_box, 1)

        if show_back:
            back_btn = QPushButton("← Back to Master Data")
            back_btn.setObjectName("BackButton")
            back_btn.clicked.connect(self.render_main_view)
            layout.addWidget(back_btn)

        return card

    def _build_metrics(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(12)

        metrics = [
            ("1", "Factory Capacity", "Line, mold, casing and time data"),
            ("1", "Tyre Item Master", "SAP codes, descriptions and weights"),
            ("1", "Stock Master", "SAP-code based final tyre stock"),
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

    def _module_card(
        self,
        name: str,
        badge_text: str,
        hint_text: str,
        key: str,
        card_type: str,
    ) -> QFrame:
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
        elif card_type == "stock":
            badge.setObjectName("StockBadge")
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
        if key == "Final Tyre Stock":
            key = "Stock Master"

        if key == "Stock Master Hub":
            key = "Stock Master"

        index = self.page_indexes.get(key)

        if index is not None:
            self.on_open_page(index)
