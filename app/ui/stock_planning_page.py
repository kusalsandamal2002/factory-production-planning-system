from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy import text

from app.database import engine


class StockPlanningPage(QWidget):
    def __init__(self, open_item_detail_callback=None):
        super().__init__()

        self.open_item_detail_callback = open_item_detail_callback
        self.selected_material_code: str | None = None

        self.total_items_value = QLabel("0")
        self.ready_items_value = QLabel("0")
        self.required_items_value = QLabel("0")
        self.shortage_qty_value = QLabel("0")
        self.production_required_qty_value = QLabel("0")
        self.planned_tons_value = QLabel("0.00")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search material code, description or product group..."
        )
        self.search_input.textChanged.connect(self.refresh_table)

        self.status_combo = QComboBox()
        self.status_combo.addItems(
            [
                "ALL",
                "PRODUCTION_REQUIRED",
                "PARTIAL_READY",
                "NO_STOCK_PRODUCTION_REQUIRED",
                "READY",
                "NO_DEMAND",
            ]
        )
        self.status_combo.currentTextChanged.connect(self.refresh_table)

        self.product_group_combo = QComboBox()
        self.product_group_combo.addItem("All Product Groups")
        self.product_group_combo.currentTextChanged.connect(self.refresh_table)

        self.shortage_only_checkbox = QCheckBox("Shortage only")
        self.shortage_only_checkbox.stateChanged.connect(self.refresh_table)

        self.ready_only_checkbox = QCheckBox("Ready only")
        self.ready_only_checkbox.stateChanged.connect(self.refresh_table)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("PrimaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.open_detail_btn = QPushButton("Open Item Detail")
        self.open_detail_btn.setObjectName("SecondaryButton")
        self.open_detail_btn.setEnabled(False)
        self.open_detail_btn.clicked.connect(self.open_selected_item)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Material Code",
                "Description",
                "Available",
                "Demand",
                "Required",
                "Tons",
                "Status",
                "Product Group",
            ]
        )

        self._setup_table()
        self._apply_styles()
        self._build_ui()

        self.refresh()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#MetricCard,
            QFrame#ControlCard,
            QFrame#TableCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }

            QLabel#MetricTitle {
                color: #64748b;
                font-size: 8.5pt;
                font-weight: 850;
            }

            QLabel#MetricValue {
                color: #0f172a;
                font-size: 19pt;
                font-weight: 950;
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

            QLabel#FieldLabel {
                color: #334155;
                font-size: 9pt;
                font-weight: 850;
            }

            QLineEdit,
            QComboBox {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 9px 12px;
                font-size: 10pt;
                font-weight: 650;
                min-height: 24px;
            }

            QLineEdit:focus,
            QComboBox:focus {
                border: 1px solid #2563eb;
            }

            QCheckBox {
                color: #334155;
                font-size: 9.5pt;
                font-weight: 850;
                spacing: 8px;
            }

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 10px 18px;
                font-weight: 950;
                min-height: 26px;
            }

            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }

            QPushButton#SecondaryButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 10px 18px;
                font-weight: 950;
                min-height: 26px;
            }

            QPushButton#SecondaryButton:hover {
                background: #cbd5e1;
            }

            QPushButton#SecondaryButton:disabled {
                background: #f1f5f9;
                color: #94a3b8;
            }

            QTableWidget {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                gridline-color: #e2e8f0;
                alternate-background-color: #f8fafc;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }

            QTableWidget::item {
                padding: 8px 10px;
                border: none;
            }

            QTableWidget::item:selected {
                background: #dbeafe;
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

        root.addLayout(self._build_metrics_grid())
        root.addWidget(self._build_control_card())
        root.addWidget(self._build_table_card(), 1)

    def _build_metrics_grid(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        cards = [
            self._metric_card("Total Items", self.total_items_value),
            self._metric_card("Ready for Shipment Items", self.ready_items_value),
            self._metric_card("Production Required Items", self.required_items_value),
            self._metric_card("Total Shortage Qty", self.shortage_qty_value),
            self._metric_card("Total Production Required Qty", self.production_required_qty_value),
            self._metric_card("Total Planned Tons", self.planned_tons_value),
        ]

        for index, card in enumerate(cards):
            grid.addWidget(card, index // 3, index % 3)

        return grid

    def _metric_card(self, title_text: str, value_label: QLabel) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(5)

        title = QLabel(title_text)
        title.setObjectName("MetricTitle")

        value_label.setObjectName("MetricValue")

        layout.addWidget(title)
        layout.addWidget(value_label)

        return card

    def _build_control_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("ControlCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel("MPPS Stock Planning Control")
        title.setObjectName("SectionTitle")

        hint = QLabel(
            "Stock → Demand → Shortage → Production Required → Weight/Tonnage. "
            "This page uses the clean PostgreSQL MPPS tables mapped from the original Excel source."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(hint)

        header.addLayout(title_box, 1)
        header.addWidget(self.refresh_btn)

        layout.addLayout(header)

        form_grid = QGridLayout()
        form_grid.setHorizontalSpacing(12)
        form_grid.setVerticalSpacing(10)

        search_label = QLabel("Search")
        search_label.setObjectName("FieldLabel")

        status_label = QLabel("Status")
        status_label.setObjectName("FieldLabel")

        group_label = QLabel("Product Group")
        group_label.setObjectName("FieldLabel")

        form_grid.addWidget(search_label, 0, 0)
        form_grid.addWidget(self.search_input, 0, 1, 1, 5)

        form_grid.addWidget(status_label, 1, 0)
        form_grid.addWidget(self.status_combo, 1, 1, 1, 2)

        form_grid.addWidget(group_label, 1, 3)
        form_grid.addWidget(self.product_group_combo, 1, 4, 1, 2)

        form_grid.setColumnStretch(1, 2)
        form_grid.setColumnStretch(2, 1)
        form_grid.setColumnStretch(4, 2)
        form_grid.setColumnStretch(5, 1)

        layout.addLayout(form_grid)

        actions = QHBoxLayout()
        actions.setSpacing(14)

        actions.addWidget(self.shortage_only_checkbox)
        actions.addWidget(self.ready_only_checkbox)
        actions.addStretch()
        actions.addWidget(self.open_detail_btn)

        layout.addLayout(actions)

        return card

    def _build_table_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Stock Planning Summary")
        title.setObjectName("SectionTitle")

        hint = QLabel(
            "Decision view: high shortage and production-required items appear first. "
            "Double-click a row to review BOM, compound, bead, band and capacity details."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self.table, 1)

        return card

    def _setup_table(self) -> None:
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(48)
        self.table.setAlternatingRowColors(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 135)
        self.table.setColumnWidth(2, 105)
        self.table.setColumnWidth(3, 105)
        self.table.setColumnWidth(4, 105)
        self.table.setColumnWidth(5, 95)
        self.table.setColumnWidth(6, 190)
        self.table.setColumnWidth(7, 150)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemDoubleClicked.connect(self.on_row_double_clicked)

    def refresh(self) -> None:
        try:
            self.load_product_groups()
            self.refresh_metrics()
            self.refresh_table()
        except Exception as exc:
            QMessageBox.critical(self, "MPPS Stock Planning Error", str(exc))

    def load_product_groups(self) -> None:
        current_value = self.product_group_combo.currentText()

        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT DISTINCT product_group
                    FROM mpps_stock_planning_view
                    WHERE product_group IS NOT NULL
                      AND TRIM(product_group) <> ''
                    ORDER BY product_group;
                    """
                )
            ).scalars().all()

        self.product_group_combo.blockSignals(True)
        self.product_group_combo.clear()
        self.product_group_combo.addItem("All Product Groups")

        for value in rows:
            self.product_group_combo.addItem(str(value))

        index = self.product_group_combo.findText(current_value)

        if index >= 0:
            self.product_group_combo.setCurrentIndex(index)

        self.product_group_combo.blockSignals(False)

    def refresh_metrics(self) -> None:
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS total_items,
                        SUM(CASE WHEN status = 'READY' THEN 1 ELSE 0 END) AS ready_items,
                        SUM(CASE WHEN production_required_qty > 0 THEN 1 ELSE 0 END) AS required_items,
                        COALESCE(SUM(shortage_qty), 0) AS total_shortage_qty,
                        COALESCE(SUM(production_required_qty), 0) AS total_production_required_qty,
                        COALESCE(SUM(total_required_weight_tons), 0) AS total_planned_tons
                    FROM mpps_stock_planning_view;
                    """
                )
            ).mappings().one()

        self.total_items_value.setText(self._format_int(row["total_items"]))
        self.ready_items_value.setText(self._format_int(row["ready_items"]))
        self.required_items_value.setText(self._format_int(row["required_items"]))
        self.shortage_qty_value.setText(self._format_int(row["total_shortage_qty"]))
        self.production_required_qty_value.setText(
            self._format_int(row["total_production_required_qty"])
        )
        self.planned_tons_value.setText(self._format_decimal(row["total_planned_tons"], 2))

    def refresh_table(self, *args) -> None:
        self.selected_material_code = None
        self.open_detail_btn.setEnabled(False)

        search_text = self.search_input.text().strip()
        status_value = self.status_combo.currentText().strip()
        product_group_value = self.product_group_combo.currentText().strip()

        conditions = []
        params = {
            "search": f"%{search_text}%",
            "status": status_value,
            "product_group": product_group_value,
        }

        if search_text:
            conditions.append(
                """
                (
                    material_code ILIKE :search
                    OR item_description ILIKE :search
                    OR COALESCE(product_group, '') ILIKE :search
                )
                """
            )

        if status_value and status_value != "ALL":
            conditions.append("status = :status")

        if product_group_value and product_group_value != "All Product Groups":
            conditions.append("product_group = :product_group")

        if self.shortage_only_checkbox.isChecked():
            conditions.append("production_required_qty > 0")

        if self.ready_only_checkbox.isChecked():
            conditions.append("status = 'READY'")

        where_sql = ""

        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT
                material_code,
                item_description,
                available_stock,
                shipment_demand,
                production_required_qty,
                total_required_weight_tons,
                status,
                product_group
            FROM mpps_stock_planning_view
            {where_sql}
            ORDER BY
                production_required_qty DESC,
                shipment_demand DESC,
                material_code ASC
            LIMIT 1000;
        """

        with engine.begin() as connection:
            rows = connection.execute(text(sql), params).mappings().all()

        self.table.setRowCount(0)

        for row_index, row in enumerate(rows):
            self.table.insertRow(row_index)

            values = [
                row["material_code"],
                row["item_description"],
                self._format_int(row["available_stock"]),
                self._format_int(row["shipment_demand"]),
                self._format_int(row["production_required_qty"]),
                self._format_decimal(row["total_required_weight_tons"], 2),
                self._format_status(row["status"]),
                row["product_group"] or "-",
            ]

            for column_index, value in enumerate(values):
                item = self._readonly_item(value)

                if column_index in {2, 3, 4, 5}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if column_index == 6:
                    self._apply_status_style(item, str(row["status"]))

                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row["material_code"])

                self.table.setItem(row_index, column_index, item)

        self.table.resizeRowsToContents()

    def on_selection_changed(self) -> None:
        selected_items = self.table.selectedItems()

        if not selected_items:
            self.selected_material_code = None
            self.open_detail_btn.setEnabled(False)
            return

        row = selected_items[0].row()
        material_item = self.table.item(row, 0)

        if material_item is None:
            self.selected_material_code = None
            self.open_detail_btn.setEnabled(False)
            return

        self.selected_material_code = material_item.data(Qt.ItemDataRole.UserRole)
        self.open_detail_btn.setEnabled(bool(self.selected_material_code))

    def on_row_double_clicked(self, *args) -> None:
        self.open_selected_item()

    def open_selected_item(self) -> None:
        if not self.selected_material_code:
            return

        if self.open_item_detail_callback is None:
            QMessageBox.information(
                self,
                "Item Detail",
                "Item detail page is not connected.",
            )
            return

        self.open_item_detail_callback(self.selected_material_code)

    def _readonly_item(self, text_value: str) -> QTableWidgetItem:
        item = QTableWidgetItem(str(text_value))
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

    def _apply_status_style(self, item: QTableWidgetItem, status: str) -> None:
        status_value = status.upper()

        if status_value == "READY":
            item.setForeground(QColor("#166534"))
            item.setBackground(QColor("#dcfce7"))
        elif status_value == "PARTIAL_READY":
            item.setForeground(QColor("#92400e"))
            item.setBackground(QColor("#fef3c7"))
        elif status_value == "NO_STOCK_PRODUCTION_REQUIRED":
            item.setForeground(QColor("#991b1b"))
            item.setBackground(QColor("#fee2e2"))
        elif status_value == "PRODUCTION_REQUIRED":
            item.setForeground(QColor("#1d4ed8"))
            item.setBackground(QColor("#dbeafe"))
        else:
            item.setForeground(QColor("#475569"))
            item.setBackground(QColor("#f1f5f9"))

        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

    def _format_status(self, value: str | None) -> str:
        if not value:
            return "-"

        return str(value).replace("_", " ")

    def _format_int(self, value) -> str:
        try:
            return f"{int(value or 0):,}"
        except (TypeError, ValueError):
            return "0"

    def _format_decimal(self, value, decimals: int = 2) -> str:
        try:
            decimal_value = Decimal(str(value or 0))
            return f"{decimal_value:,.{decimals}f}"
        except Exception:
            return "0.00"