from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy import text

from app.database import engine


class StockEditDialog(QDialog):
    def __init__(self, parent=None, stock_item: dict | None = None):
        super().__init__(parent)

        self.stock_item = stock_item or {}

        self.setWindowTitle("Edit Stock Balance")
        self.setMinimumWidth(620)

        self.material_code_label = QLabel("-")
        self.description_label = QLabel("-")

        self.fg_stock_input = QSpinBox()
        self.fg_stock_input.setRange(0, 999999999)

        self.qc_stock_input = QSpinBox()
        self.qc_stock_input.setRange(0, 999999999)

        self.scrap_stock_input = QSpinBox()
        self.scrap_stock_input.setRange(0, 999999999)

        self.blocked_stock_input = QSpinBox()
        self.blocked_stock_input.setRange(0, 999999999)

        self.reason_input = QLineEdit()
        self.reason_input.setPlaceholderText("Required: reason for stock correction...")

        self.save_btn = QPushButton("Save Stock Balance")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.accept)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SecondaryButton")
        self.cancel_btn.clicked.connect(self.reject)

        self._apply_styles()
        self._build_ui()
        self._load_stock_item()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #f8fafc;
            }

            QFrame#Card {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }

            QLabel#Title {
                color: #0f172a;
                font-size: 16pt;
                font-weight: 950;
            }

            QLabel#Hint {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLabel#FieldLabel {
                color: #334155;
                font-size: 9pt;
                font-weight: 850;
            }

            QLabel#ReadonlyValue {
                background: #f1f5f9;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 10px 12px;
                font-size: 10pt;
                font-weight: 800;
            }

            QLineEdit,
            QSpinBox {
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
            QSpinBox:focus {
                border: 1px solid #2563eb;
            }

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 10px 20px;
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
                padding: 10px 20px;
                font-weight: 950;
                min-height: 26px;
            }

            QPushButton#SecondaryButton:hover {
                background: #cbd5e1;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(14)

        card = QFrame()
        card.setObjectName("Card")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        title = QLabel("Stock Master")
        title.setObjectName("Title")

        hint = QLabel(
            "Update stock balances carefully. This changes the clean MPPS database stock values used for planning decisions."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        self._add_readonly_field(form, 0, "Material Code", self.material_code_label)
        self._add_readonly_field(form, 1, "Description", self.description_label)
        self._add_field(form, 2, "FG Stock", self.fg_stock_input)
        self._add_field(form, 3, "QC Stock", self.qc_stock_input)
        self._add_field(form, 4, "Scrap Stock", self.scrap_stock_input)
        self._add_field(form, 5, "Blocked Stock", self.blocked_stock_input)
        self._add_field(form, 6, "Correction Reason", self.reason_input)

        layout.addLayout(form)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.cancel_btn)
        button_row.addWidget(self.save_btn)

        layout.addLayout(button_row)

        root.addWidget(card)

    def _add_field(self, grid: QGridLayout, row: int, label_text: str, widget: QWidget) -> None:
        label = QLabel(label_text)
        label.setObjectName("FieldLabel")

        grid.addWidget(label, row, 0)
        grid.addWidget(widget, row, 1)

        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)

    def _add_readonly_field(self, grid: QGridLayout, row: int, label_text: str, widget: QLabel) -> None:
        label = QLabel(label_text)
        label.setObjectName("FieldLabel")

        widget.setObjectName("ReadonlyValue")
        widget.setWordWrap(True)

        grid.addWidget(label, row, 0)
        grid.addWidget(widget, row, 1)

    def _load_stock_item(self) -> None:
        self.material_code_label.setText(str(self.stock_item.get("material_code") or "-"))
        self.description_label.setText(str(self.stock_item.get("item_description") or "-"))

        self.fg_stock_input.setValue(int(self.stock_item.get("fg_stock") or 0))
        self.qc_stock_input.setValue(int(self.stock_item.get("qc_stock") or 0))
        self.scrap_stock_input.setValue(int(self.stock_item.get("scrap_stock") or 0))
        self.blocked_stock_input.setValue(int(self.stock_item.get("blocked_stock") or 0))

    def get_data(self) -> dict:
        reason = self.reason_input.text().strip()

        if not reason:
            raise ValueError("Correction reason is required.")

        return {
            "material_code": self.stock_item.get("material_code"),
            "fg_stock": self.fg_stock_input.value(),
            "qc_stock": self.qc_stock_input.value(),
            "scrap_stock": self.scrap_stock_input.value(),
            "blocked_stock": self.blocked_stock_input.value(),
            "reason": reason,
        }


class StockMasterPage(QWidget):
    def __init__(self):
        super().__init__()

        self.selected_material_code: str | None = None

        self.total_items_value = QLabel("0")
        self.total_fg_value = QLabel("0")
        self.total_qc_value = QLabel("0")
        self.total_available_value = QLabel("0")
        self.total_blocked_value = QLabel("0")
        self.out_of_stock_value = QLabel("0")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search material code, description or group...")
        self.search_input.textChanged.connect(self.refresh_table)

        self.product_group_combo = QComboBox()
        self.product_group_combo.addItem("All Product Groups")
        self.product_group_combo.currentTextChanged.connect(self.refresh_table)

        self.stock_status_combo = QComboBox()
        self.stock_status_combo.addItems(
            [
                "All Stock Status",
                "Available Stock",
                "Out of Stock",
                "Blocked Stock",
                "Scrap Stock",
            ]
        )
        self.stock_status_combo.currentTextChanged.connect(self.refresh_table)

        self.edit_btn = QPushButton("Edit Selected Stock")
        self.edit_btn.setObjectName("PrimaryButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.edit_selected_stock)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Material",
                "Description",
                "Group",
                "FG",
                "QC",
                "Scrap",
                "Blocked",
                "Available",
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

            QPushButton#PrimaryButton:disabled {
                background: #bfdbfe;
                color: #eff6ff;
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
            self._metric_card("FG Stock", self.total_fg_value),
            self._metric_card("QC Stock", self.total_qc_value),
            self._metric_card("Available Stock", self.total_available_value),
            self._metric_card("Blocked Stock", self.total_blocked_value),
            self._metric_card("Out of Stock Items", self.out_of_stock_value),
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

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel("Stock Master Control")
        title.setObjectName("SectionTitle")

        hint = QLabel(
            "Maintain FG, QC, scrap and blocked stock balances. These values directly affect shortage and production planning."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(hint)

        header.addLayout(title_box, 1)
        header.addWidget(self.edit_btn)
        header.addWidget(self.refresh_btn)

        layout.addLayout(header)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        search_label = QLabel("Search")
        search_label.setObjectName("FieldLabel")

        group_label = QLabel("Product Group")
        group_label.setObjectName("FieldLabel")

        status_label = QLabel("Stock Status")
        status_label.setObjectName("FieldLabel")

        form.addWidget(search_label, 0, 0)
        form.addWidget(self.search_input, 0, 1, 1, 5)

        form.addWidget(group_label, 1, 0)
        form.addWidget(self.product_group_combo, 1, 1, 1, 2)

        form.addWidget(status_label, 1, 3)
        form.addWidget(self.stock_status_combo, 1, 4, 1, 2)

        form.setColumnStretch(1, 2)
        form.setColumnStretch(2, 1)
        form.setColumnStretch(4, 2)
        form.setColumnStretch(5, 1)

        layout.addLayout(form)

        return card

    def _build_table_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Stock Master Data")
        title.setObjectName("SectionTitle")

        hint = QLabel(
            "Double-click a row to edit stock. Available stock is calculated as FG + QC - Scrap - Blocked."
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
        header.setStretchLastSection(False)

        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 115)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 90)
        self.table.setColumnWidth(5, 90)
        self.table.setColumnWidth(6, 95)
        self.table.setColumnWidth(7, 105)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemDoubleClicked.connect(self.edit_selected_stock)

    def refresh(self) -> None:
        try:
            self.load_product_groups()
            self.refresh_metrics()
            self.refresh_table()
        except Exception as exc:
            QMessageBox.critical(self, "Stock Master Error", str(exc))

    def load_product_groups(self) -> None:
        current_value = self.product_group_combo.currentText()

        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT DISTINCT product_group
                    FROM mpps_stock_items
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
                        COALESCE(SUM(fg_stock), 0) AS total_fg,
                        COALESCE(SUM(qc_stock), 0) AS total_qc,
                        COALESCE(SUM(scrap_stock), 0) AS total_scrap,
                        COALESCE(SUM(blocked_stock), 0) AS total_blocked,
                        COALESCE(SUM(fg_stock + qc_stock - scrap_stock - blocked_stock), 0) AS total_available,
                        SUM(
                            CASE
                                WHEN (fg_stock + qc_stock - scrap_stock - blocked_stock) <= 0 THEN 1
                                ELSE 0
                            END
                        ) AS out_of_stock_items
                    FROM mpps_stock_items
                    WHERE is_active = TRUE;
                    """
                )
            ).mappings().one()

        self.total_items_value.setText(self._format_int(row["total_items"]))
        self.total_fg_value.setText(self._format_int(row["total_fg"]))
        self.total_qc_value.setText(self._format_int(row["total_qc"]))
        self.total_available_value.setText(self._format_int(row["total_available"]))
        self.total_blocked_value.setText(self._format_int(row["total_blocked"]))
        self.out_of_stock_value.setText(self._format_int(row["out_of_stock_items"]))

    def refresh_table(self, *args) -> None:
        self.selected_material_code = None
        self.edit_btn.setEnabled(False)

        search_text = self.search_input.text().strip()
        group_value = self.product_group_combo.currentText().strip()
        status_value = self.stock_status_combo.currentText().strip()

        conditions = ["is_active = TRUE"]
        params = {
            "search": f"%{search_text}%",
            "product_group": group_value,
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

        if group_value and group_value != "All Product Groups":
            conditions.append("product_group = :product_group")

        if status_value == "Available Stock":
            conditions.append("(fg_stock + qc_stock - scrap_stock - blocked_stock) > 0")
        elif status_value == "Out of Stock":
            conditions.append("(fg_stock + qc_stock - scrap_stock - blocked_stock) <= 0")
        elif status_value == "Blocked Stock":
            conditions.append("blocked_stock > 0")
        elif status_value == "Scrap Stock":
            conditions.append("scrap_stock > 0")

        where_sql = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT
                material_code,
                item_description,
                product_group,
                fg_stock,
                qc_stock,
                scrap_stock,
                blocked_stock,
                (fg_stock + qc_stock - scrap_stock - blocked_stock) AS available_stock
            FROM mpps_stock_items
            {where_sql}
            ORDER BY
                available_stock ASC,
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
                row["product_group"] or "-",
                self._format_int(row["fg_stock"]),
                self._format_int(row["qc_stock"]),
                self._format_int(row["scrap_stock"]),
                self._format_int(row["blocked_stock"]),
                self._format_int(row["available_stock"]),
            ]

            for column_index, value in enumerate(values):
                item = self._readonly_item(value)

                if column_index in {3, 4, 5, 6, 7}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if column_index == 7:
                    self._apply_available_stock_style(item, int(row["available_stock"] or 0))

                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row["material_code"])

                self.table.setItem(row_index, column_index, item)

        self.table.resizeRowsToContents()

    def edit_selected_stock(self, *args) -> None:
        if not self.selected_material_code:
            return

        stock_item = self.get_stock_item(self.selected_material_code)

        if stock_item is None:
            QMessageBox.warning(self, "Stock Item Missing", "Selected stock item was not found.")
            return

        dialog = StockEditDialog(self, dict(stock_item))

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            data = dialog.get_data()
            self.save_stock_balance(data)
            self.refresh()
            QMessageBox.information(self, "Stock Updated", "Stock balance updated successfully.")
        except Exception as exc:
            QMessageBox.critical(self, "Stock Update Failed", str(exc))

    def get_stock_item(self, material_code: str):
        with engine.begin() as connection:
            return connection.execute(
                text(
                    """
                    SELECT
                        material_code,
                        item_description,
                        product_group,
                        fg_stock,
                        qc_stock,
                        scrap_stock,
                        blocked_stock
                    FROM mpps_stock_items
                    WHERE material_code = :material_code
                    LIMIT 1;
                    """
                ),
                {"material_code": material_code},
            ).mappings().first()

    def save_stock_balance(self, data: dict) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE mpps_stock_items
                    SET
                        fg_stock = :fg_stock,
                        qc_stock = :qc_stock,
                        scrap_stock = :scrap_stock,
                        blocked_stock = :blocked_stock,
                        last_updated_date = CURRENT_DATE,
                        source_note = :reason,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE material_code = :material_code;
                    """
                ),
                data,
            )

    def on_selection_changed(self) -> None:
        selected_items = self.table.selectedItems()

        if not selected_items:
            self.selected_material_code = None
            self.edit_btn.setEnabled(False)
            return

        row = selected_items[0].row()
        material_item = self.table.item(row, 0)

        if material_item is None:
            self.selected_material_code = None
            self.edit_btn.setEnabled(False)
            return

        self.selected_material_code = material_item.data(Qt.ItemDataRole.UserRole)
        self.edit_btn.setEnabled(bool(self.selected_material_code))

    def _readonly_item(self, text_value: str) -> QTableWidgetItem:
        item = QTableWidgetItem(str(text_value))
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

    def _apply_available_stock_style(self, item: QTableWidgetItem, available_stock: int) -> None:
        if available_stock > 0:
            item.setForeground(QColor("#166534"))
            item.setBackground(QColor("#dcfce7"))
        elif available_stock == 0:
            item.setForeground(QColor("#92400e"))
            item.setBackground(QColor("#fef3c7"))
        else:
            item.setForeground(QColor("#991b1b"))
            item.setBackground(QColor("#fee2e2"))

    def _format_int(self, value) -> str:
        try:
            return f"{int(value or 0):,}"
        except Exception:
            return "0"