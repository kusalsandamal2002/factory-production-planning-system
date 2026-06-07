from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.database import get_session
from app.services.stock_planning_service import ItemDetailSummary, build_item_detail_summary


class StockItemDetailPage(QWidget):
    STOCK_INDEX = 0
    DEMAND_INDEX = 1
    BOM_INDEX = 2
    COMPOUND_INDEX = 3
    BEAD_BAND_INDEX = 4
    CAPACITY_INDEX = 5
    WARNING_INDEX = 6

    def __init__(self, on_back_callback=None):
        super().__init__()

        self.on_back_callback = on_back_callback
        self.material_code: str | None = None
        self.detail: ItemDetailSummary | None = None
        self.nav_buttons: list[QPushButton] = []

        self.item_title = QLabel("Select Stock Item")
        self.item_title.setObjectName("ItemTitle")

        self.item_subtitle = QLabel("Open an item from MPPS Stock Planning to view detailed requirement breakdown.")
        self.item_subtitle.setObjectName("ItemSubtitle")
        self.item_subtitle.setWordWrap(True)

        self.back_btn = QPushButton("Back to Stock Planning")
        self.back_btn.setObjectName("SecondaryButton")
        self.back_btn.setMinimumHeight(42)
        self.back_btn.clicked.connect(self.back_to_stock_planning)

        self.refresh_btn = QPushButton("Refresh Detail")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.setMinimumHeight(42)
        self.refresh_btn.clicked.connect(self.refresh)

        self.stock_labels = {
            "fg_stock": QLabel("0"),
            "qc_stock": QLabel("0"),
            "scrap_stock": QLabel("0"),
            "blocked_stock": QLabel("0"),
            "available_stock": QLabel("0"),
            "shipment_demand": QLabel("0"),
            "shortage_qty": QLabel("0"),
            "production_required_qty": QLabel("0"),
            "status": QLabel("-"),
            "planned_tons": QLabel("0.0000"),
        }

        self.demand_table = QTableWidget(0, 7)
        self.demand_table.setHorizontalHeaderLabels(
            [
                "Source",
                "Order No",
                "Customer",
                "Demand Qty",
                "Shipment Date",
                "Status",
                "Note",
            ]
        )

        self.bom_table = QTableWidget(0, 8)
        self.bom_table.setHorizontalHeaderLabels(
            [
                "Finished Item",
                "Raw Material Code",
                "Raw Material Name",
                "Usage / Unit",
                "Production Qty",
                "Total Required",
                "Wastage %",
                "Final Required",
            ]
        )

        self.compound_table = QTableWidget(0, 7)
        self.compound_table.setHorizontalHeaderLabels(
            [
                "Item Code",
                "Compound Code",
                "Compound Name",
                "Stage",
                "Weight / Unit",
                "Production Qty",
                "Required KG",
            ]
        )

        self.bead_table = QTableWidget(0, 6)
        self.bead_table.setHorizontalHeaderLabels(
            [
                "Item Code",
                "Tire Size",
                "Bead Type",
                "Bead / Tyre",
                "Production Qty",
                "Total Bead Required",
            ]
        )

        self.band_table = QTableWidget(0, 7)
        self.band_table.setHorizontalHeaderLabels(
            [
                "Item Code",
                "Tire Size",
                "Band Code",
                "Band Type",
                "Band / Tyre",
                "Production Qty",
                "Total Band Required",
            ]
        )

        self.capacity_table = QTableWidget(0, 8)
        self.capacity_table.setHorizontalHeaderLabels(
            [
                "Item Code",
                "Description",
                "Production Qty",
                "Running Moulds",
                "Per Mould Capacity",
                "Daily Capacity",
                "Production Days",
                "Capacity Status",
            ]
        )

        self.tonnage_table = QTableWidget(0, 6)
        self.tonnage_table.setHorizontalHeaderLabels(
            [
                "Item Code",
                "Description",
                "Production Qty",
                "Average Weight",
                "Total KG",
                "Total Tons",
            ]
        )

        self.warning_table = QTableWidget(0, 2)
        self.warning_table.setHorizontalHeaderLabels(["No", "Warning"])

        self.stack = QStackedWidget()

        self._setup_tables()
        self._apply_styles()
        self._build_ui()
        self.navigate_sub_page(self.STOCK_INDEX)

    def _setup_tables(self) -> None:
        tables = [
            self.demand_table,
            self.bom_table,
            self.compound_table,
            self.bead_table,
            self.band_table,
            self.capacity_table,
            self.tonnage_table,
            self.warning_table,
        ]

        for table in tables:
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.verticalHeader().setVisible(False)
            table.verticalHeader().setDefaultSectionSize(48)
            table.setAlternatingRowColors(True)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#HeaderCard,
            QFrame#SubNavCard,
            QFrame#ContentCard,
            QFrame#MetricCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }

            QLabel#ItemTitle {
                color: #0f172a;
                font-size: 17pt;
                font-weight: 950;
            }

            QLabel#ItemSubtitle {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 15pt;
                font-weight: 950;
            }

            QLabel#SectionHint {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLabel#MetricTitle {
                color: #64748b;
                font-size: 8.5pt;
                font-weight: 850;
            }

            QLabel#MetricValue {
                color: #0f172a;
                font-size: 18pt;
                font-weight: 950;
            }

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 8px 16px;
                font-weight: 950;
            }

            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }

            QPushButton#SecondaryButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 8px 16px;
                font-weight: 950;
            }

            QPushButton#SecondaryButton:hover {
                background: #cbd5e1;
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

            QTableWidget {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                gridline-color: #e2e8f0;
                selection-background-color: #eff6ff;
                selection-color: #0f172a;
                alternate-background-color: #f8fafc;
            }

            QTableWidget::item {
                padding: 8px 10px;
                border: none;
            }

            QTableWidget::item:selected {
                background: #eff6ff;
                color: #0f172a;
            }

            QHeaderView::section {
                background: #f1f5f9;
                color: #1e293b;
                border: none;
                border-right: 1px solid #e2e8f0;
                border-bottom: 1px solid #e2e8f0;
                padding: 10px;
                font-weight: 950;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self._build_header_card())
        root.addWidget(self._build_sub_nav_card())

        self.stack.addWidget(self._build_stock_summary_page())
        self.stack.addWidget(self._build_table_page(
            "Demand Breakdown",
            "Customer/order-wise active demand used for MPPS shipment demand calculation.",
            self.demand_table,
        ))
        self.stack.addWidget(self._build_table_page(
            "BOM Requirement",
            "Raw material requirement calculated from production required quantity and BOM usage.",
            self.bom_table,
        ))
        self.stack.addWidget(self._build_table_page(
            "Compound Requirement",
            "Rubber compound requirement grouped by compound code and production stage.",
            self.compound_table,
        ))
        self.stack.addWidget(self._build_bead_band_page())
        self.stack.addWidget(self._build_capacity_page())
        self.stack.addWidget(self._build_table_page(
            "Warnings",
            "Missing master data, stock issues and capacity risks for the selected item.",
            self.warning_table,
        ))

        root.addWidget(self.stack, 1)

    def _build_header_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_box.addWidget(self.item_title)
        title_box.addWidget(self.item_subtitle)

        layout.addLayout(title_box, 1)
        layout.addWidget(self.back_btn)
        layout.addWidget(self.refresh_btn)

        return card

    def _build_sub_nav_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("SubNavCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        self._add_sub_nav_button(layout, "Stock Summary", self.STOCK_INDEX)
        self._add_sub_nav_button(layout, "Demand", self.DEMAND_INDEX)
        self._add_sub_nav_button(layout, "BOM", self.BOM_INDEX)
        self._add_sub_nav_button(layout, "Compound", self.COMPOUND_INDEX)
        self._add_sub_nav_button(layout, "Bead / Band", self.BEAD_BAND_INDEX)
        self._add_sub_nav_button(layout, "Capacity", self.CAPACITY_INDEX)
        self._add_sub_nav_button(layout, "Warnings", self.WARNING_INDEX)

        layout.addStretch()

        return card

    def _add_sub_nav_button(self, layout: QHBoxLayout, text_value: str, index: int) -> None:
        button = QPushButton(text_value)
        button.setObjectName("SubNavButton")
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda checked=False, idx=index: self.navigate_sub_page(idx))

        self.nav_buttons.append(button)
        layout.addWidget(button)

    def _build_stock_summary_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        summary_card = QFrame()
        summary_card.setObjectName("ContentCard")

        summary_layout = QVBoxLayout(summary_card)
        summary_layout.setContentsMargins(18, 16, 18, 18)
        summary_layout.setSpacing(14)

        title = QLabel("Stock Summary")
        title.setObjectName("SectionTitle")

        hint = QLabel("FG + QC - Scrap - Blocked = Available Stock. Shortage becomes production required quantity.")
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        summary_layout.addWidget(title)
        summary_layout.addWidget(hint)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        cards = [
            self._metric_card("FG Stock", self.stock_labels["fg_stock"]),
            self._metric_card("QC Stock", self.stock_labels["qc_stock"]),
            self._metric_card("Scrap", self.stock_labels["scrap_stock"]),
            self._metric_card("Blocked", self.stock_labels["blocked_stock"]),
            self._metric_card("Available", self.stock_labels["available_stock"]),
            self._metric_card("Shipment Demand", self.stock_labels["shipment_demand"]),
            self._metric_card("Shortage", self.stock_labels["shortage_qty"]),
            self._metric_card("Production Required", self.stock_labels["production_required_qty"]),
            self._metric_card("Status", self.stock_labels["status"]),
            self._metric_card("Planned Tons", self.stock_labels["planned_tons"]),
        ]

        for index, card in enumerate(cards):
            grid.addWidget(card, index // 5, index % 5)

        summary_layout.addLayout(grid)
        summary_layout.addStretch()

        layout.addWidget(summary_card, 1)

        return page

    def _metric_card(self, title_text: str, value_label: QLabel) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(5)

        title = QLabel(title_text)
        title.setObjectName("MetricTitle")

        value_label.setObjectName("MetricValue")
        value_label.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(value_label)

        return card

    def _build_table_page(self, title_text: str, hint_text: str, table: QTableWidget) -> QWidget:
        page = QWidget()
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        card = QFrame()
        card.setObjectName("ContentCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel(title_text)
        title.setObjectName("SectionTitle")

        hint = QLabel(hint_text)
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(table, 1)

        page_layout.addWidget(card, 1)

        return page

    def _build_bead_band_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        bead_card = self._table_card(
            title_text="Bead Requirement",
            hint_text="Total bead requirement = Production Required Qty × Bead Per Tyre.",
            table=self.bead_table,
        )

        band_card = self._table_card(
            title_text="Band Requirement",
            hint_text="Total band requirement = Production Required Qty × Band Usage Per Tyre.",
            table=self.band_table,
        )

        layout.addWidget(bead_card, 1)
        layout.addWidget(band_card, 1)

        return page

    def _build_capacity_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        tonnage_card = self._table_card(
            title_text="Weight / Tonnage",
            hint_text="Total production weight = Production Required Qty × Average Weight. Tons = KG / 1000.",
            table=self.tonnage_table,
        )

        capacity_card = self._table_card(
            title_text="Capacity Preview",
            hint_text="Capacity preview uses MPPS capacity master. Existing oven planning logic remains protected.",
            table=self.capacity_table,
        )

        layout.addWidget(tonnage_card, 1)
        layout.addWidget(capacity_card, 1)

        return page

    def _table_card(self, title_text: str, hint_text: str, table: QTableWidget) -> QFrame:
        card = QFrame()
        card.setObjectName("ContentCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel(title_text)
        title.setObjectName("SectionTitle")

        hint = QLabel(hint_text)
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(table, 1)

        return card

    def navigate_sub_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)

        for button_index, button in enumerate(self.nav_buttons):
            button.setProperty("active", "true" if button_index == index else "false")
            button.style().unpolish(button)
            button.style().polish(button)

    def set_material_code(self, material_code: str) -> None:
        self.material_code = material_code
        self.refresh()

    def refresh(self) -> None:
        if not self.material_code:
            return

        try:
            with get_session() as session:
                self.detail = build_item_detail_summary(
                    session,
                    material_code=self.material_code,
                )
        except Exception as exc:
            QMessageBox.critical(self, "Item Detail Error", str(exc))
            return

        self.populate_detail()

    def populate_detail(self) -> None:
        if self.detail is None:
            return

        stock = self.detail.stock

        self.item_title.setText(f"{stock.material_code} - {stock.item_description}")
        self.item_subtitle.setText(
            f"Status: {stock.status.replace('_', ' ')} | "
            f"Demand: {stock.shipment_demand} | "
            f"Shortage: {stock.shortage_qty} | "
            f"Production Required: {stock.production_required_qty}"
        )

        self.stock_labels["fg_stock"].setText(str(stock.fg_stock))
        self.stock_labels["qc_stock"].setText(str(stock.qc_stock))
        self.stock_labels["scrap_stock"].setText(str(stock.scrap_stock))
        self.stock_labels["blocked_stock"].setText(str(stock.blocked_stock))
        self.stock_labels["available_stock"].setText(str(stock.available_stock))
        self.stock_labels["shipment_demand"].setText(str(stock.shipment_demand))
        self.stock_labels["shortage_qty"].setText(str(stock.shortage_qty))
        self.stock_labels["production_required_qty"].setText(str(stock.production_required_qty))
        self.stock_labels["status"].setText(stock.status.replace("_", " "))
        self.stock_labels["planned_tons"].setText(f"{stock.total_required_weight_tons:,.4f}")

        self.populate_demand_table()
        self.populate_bom_table()
        self.populate_compound_table()
        self.populate_bead_table()
        self.populate_band_table()
        self.populate_tonnage_table()
        self.populate_capacity_table()
        self.populate_warning_table()

    def populate_demand_table(self) -> None:
        self.demand_table.setRowCount(0)

        for row_index, row in enumerate(self.detail.demand_breakdown if self.detail else []):
            self.demand_table.insertRow(row_index)

            values = [
                row.source,
                row.order_no,
                row.customer_name,
                str(row.demand_qty),
                self._format_date(row.shipment_date),
                row.status,
                row.note,
            ]

            self._set_table_row(self.demand_table, row_index, values, center_columns={0, 1, 3, 4, 5})

        self._finish_table(self.demand_table, stretch_columns=[2, 6])

    def populate_bom_table(self) -> None:
        self.bom_table.setRowCount(0)

        for row_index, row in enumerate(self.detail.bom_requirements if self.detail else []):
            self.bom_table.insertRow(row_index)

            values = [
                row.finished_item_code,
                row.raw_material_code,
                row.raw_material_name,
                self._format_number(row.usage_per_unit),
                str(row.production_required_qty),
                self._format_number(row.total_required_qty),
                self._format_number(row.wastage_percentage),
                f"{self._format_number(row.final_required_qty)} {row.unit}",
            ]

            self._set_table_row(self.bom_table, row_index, values, center_columns={0, 1, 3, 4, 5, 6, 7})

        self._finish_table(self.bom_table, stretch_columns=[2])

    def populate_compound_table(self) -> None:
        self.compound_table.setRowCount(0)

        for row_index, row in enumerate(self.detail.compound_requirements if self.detail else []):
            self.compound_table.insertRow(row_index)

            values = [
                row.item_code,
                row.compound_code,
                row.compound_name,
                row.stage,
                self._format_number(row.compound_weight_per_unit),
                str(row.production_required_qty),
                self._format_number(row.total_required_kg),
            ]

            self._set_table_row(self.compound_table, row_index, values, center_columns={0, 1, 3, 4, 5, 6})

        self._finish_table(self.compound_table, stretch_columns=[2])

    def populate_bead_table(self) -> None:
        self.bead_table.setRowCount(0)

        for row_index, row in enumerate(self.detail.bead_requirements if self.detail else []):
            self.bead_table.insertRow(row_index)

            values = [
                row.item_code,
                row.tire_size,
                row.bead_type,
                self._format_number(row.bead_per_tyre),
                str(row.production_required_qty),
                self._format_number(row.total_bead_required),
            ]

            self._set_table_row(self.bead_table, row_index, values, center_columns={0, 1, 3, 4, 5})

        self._finish_table(self.bead_table, stretch_columns=[2])

    def populate_band_table(self) -> None:
        self.band_table.setRowCount(0)

        for row_index, row in enumerate(self.detail.band_requirements if self.detail else []):
            self.band_table.insertRow(row_index)

            values = [
                row.item_code,
                row.tire_size,
                row.band_code,
                row.band_type,
                self._format_number(row.band_usage_per_tyre),
                str(row.production_required_qty),
                self._format_number(row.total_band_required),
            ]

            self._set_table_row(self.band_table, row_index, values, center_columns={0, 1, 2, 4, 5, 6})

        self._finish_table(self.band_table, stretch_columns=[3])

    def populate_tonnage_table(self) -> None:
        self.tonnage_table.setRowCount(0)

        if self.detail is None:
            return

        row = self.detail.tonnage
        self.tonnage_table.insertRow(0)

        values = [
            row.item_code,
            row.item_description,
            str(row.production_required_qty),
            self._format_number(row.average_weight),
            self._format_number(row.total_weight_kg),
            self._format_number(row.total_weight_tons),
        ]

        self._set_table_row(self.tonnage_table, 0, values, center_columns={0, 2, 3, 4, 5})
        self._finish_table(self.tonnage_table, stretch_columns=[1])

    def populate_capacity_table(self) -> None:
        self.capacity_table.setRowCount(0)

        if self.detail is None:
            return

        row = self.detail.capacity_preview
        self.capacity_table.insertRow(0)

        values = [
            row.item_code,
            row.item_description,
            str(row.production_required_qty),
            self._format_number(row.running_moulds),
            self._format_number(row.per_mould_capacity),
            self._format_number(row.daily_capacity),
            str(row.production_days),
            row.capacity_status.replace("_", " "),
        ]

        self._set_table_row(self.capacity_table, 0, values, center_columns={0, 2, 3, 4, 5, 6, 7})

        status_item = self.capacity_table.item(0, 7)

        if status_item is not None:
            self._apply_capacity_status_style(status_item, row.capacity_status)

        self._finish_table(self.capacity_table, stretch_columns=[1])

    def populate_warning_table(self) -> None:
        self.warning_table.setRowCount(0)

        warnings = self.detail.warnings if self.detail else []

        if not warnings:
            warnings = ["No warnings for this item."]

        for row_index, warning in enumerate(warnings):
            self.warning_table.insertRow(row_index)
            self._set_table_row(
                self.warning_table,
                row_index,
                [str(row_index + 1), warning],
                center_columns={0},
            )

            warning_item = self.warning_table.item(row_index, 1)

            if warning_item is not None and warning != "No warnings for this item.":
                warning_item.setForeground(QColor("#92400e"))
                warning_item.setBackground(QColor("#fef3c7"))

        self._finish_table(self.warning_table, stretch_columns=[1])

    def _set_table_row(
        self,
        table: QTableWidget,
        row_index: int,
        values: list[str],
        *,
        center_columns: set[int] | None = None,
    ) -> None:
        center_columns = center_columns or set()

        for column, value in enumerate(values):
            item = self._readonly_item(value)

            if column in center_columns:
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            table.setItem(row_index, column, item)

    def _finish_table(self, table: QTableWidget, stretch_columns: list[int]) -> None:
        table.resizeColumnsToContents()

        for column in stretch_columns:
            table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.Stretch)

    def _readonly_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

    def _apply_capacity_status_style(self, item: QTableWidgetItem, status: str) -> None:
        status_value = status.upper()

        if status_value in ("CAPACITY_OK", "NO_PRODUCTION_REQUIRED"):
            item.setForeground(QColor("#166534"))
            item.setBackground(QColor("#dcfce7"))
        elif status_value == "CANNOT_COMPLETE_BY_TARGET":
            item.setForeground(QColor("#991b1b"))
            item.setBackground(QColor("#fee2e2"))
        else:
            item.setForeground(QColor("#92400e"))
            item.setBackground(QColor("#fef3c7"))

    def _format_date(self, value) -> str:
        if value is None:
            return "-"

        try:
            return value.strftime("%d %b %Y")
        except AttributeError:
            return str(value)

    def _format_number(self, value) -> str:
        try:
            return f"{float(value):,.4f}"
        except (TypeError, ValueError):
            return "0.0000"

    def back_to_stock_planning(self) -> None:
        if self.on_back_callback is not None:
            self.on_back_callback()
