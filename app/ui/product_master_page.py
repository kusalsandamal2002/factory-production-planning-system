from __future__ import annotations

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QVBoxLayout,
    QWidget,
)

from sqlalchemy import text

from app.database import engine


class ProductEditDialog(QDialog):
    def __init__(self, parent=None, product: dict | None = None):
        super().__init__(parent)

        self.product = product or {}
        self.is_new = product is None

        self.setWindowTitle("Add Product" if self.is_new else "Edit Product")
        self.setMinimumWidth(620)

        self.material_code_input = QLineEdit()
        self.description_input = QLineEdit()
        self.product_group_input = QLineEdit()
        self.bead_type_input = QLineEdit()
        self.band_type_input = QLineEdit()

        self.average_weight_input = QDoubleSpinBox()
        self.average_weight_input.setRange(0, 999999)
        self.average_weight_input.setDecimals(4)
        self.average_weight_input.setSingleStep(0.1)

        self.compound_weight_input = QDoubleSpinBox()
        self.compound_weight_input.setRange(0, 999999)
        self.compound_weight_input.setDecimals(4)
        self.compound_weight_input.setSingleStep(0.1)

        self.active_checkbox = QCheckBox("Active product")
        self.active_checkbox.setChecked(True)

        self.save_btn = QPushButton("Save Product")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.accept)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SecondaryButton")
        self.cancel_btn.clicked.connect(self.reject)

        self._apply_styles()
        self._build_ui()
        self._load_product()

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

            QLineEdit,
            QDoubleSpinBox {
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
            QDoubleSpinBox:focus {
                border: 1px solid #2563eb;
            }

            QCheckBox {
                color: #334155;
                font-size: 10pt;
                font-weight: 850;
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

        title = QLabel("Product Master")
        title.setObjectName("Title")

        hint = QLabel(
            "Maintain product/material master data used by stock planning, demand, BOM, compound and capacity calculations."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        self._add_field(form, 0, "Material Code", self.material_code_input)
        self._add_field(form, 1, "Description", self.description_input)
        self._add_field(form, 2, "Product Group", self.product_group_input)
        self._add_field(form, 3, "Average Weight / Tyre", self.average_weight_input)
        self._add_field(form, 4, "Compound Weight", self.compound_weight_input)
        self._add_field(form, 5, "Bead Type", self.bead_type_input)
        self._add_field(form, 6, "Band Type", self.band_type_input)

        layout.addLayout(form)
        layout.addWidget(self.active_checkbox)

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

    def _load_product(self) -> None:
        if not self.product:
            return

        self.material_code_input.setText(str(self.product.get("material_code") or ""))
        self.material_code_input.setReadOnly(True)

        self.description_input.setText(str(self.product.get("item_description") or ""))
        self.product_group_input.setText(str(self.product.get("product_group") or ""))
        self.bead_type_input.setText(str(self.product.get("bead_type") or ""))
        self.band_type_input.setText(str(self.product.get("band_type") or ""))

        self.average_weight_input.setValue(float(self.product.get("average_weight") or 0))
        self.compound_weight_input.setValue(float(self.product.get("compound_weight") or 0))

        self.active_checkbox.setChecked(bool(self.product.get("is_active")))

    def get_data(self) -> dict:
        material_code = self.material_code_input.text().strip()
        description = self.description_input.text().strip()

        if not material_code:
            raise ValueError("Material Code is required.")

        if not description:
            raise ValueError("Description is required.")

        return {
            "material_code": material_code,
            "item_description": description,
            "product_group": self.product_group_input.text().strip() or None,
            "average_weight": Decimal(str(self.average_weight_input.value())),
            "compound_weight": Decimal(str(self.compound_weight_input.value())),
            "bead_type": self.bead_type_input.text().strip() or None,
            "band_type": self.band_type_input.text().strip() or None,
            "is_active": self.active_checkbox.isChecked(),
        }


class ProductMasterPage(QWidget):
    def __init__(self):
        super().__init__()

        self.selected_material_code: str | None = None

        self.total_products_value = QLabel("0")
        self.active_products_value = QLabel("0")
        self.missing_weight_value = QLabel("0")
        self.production_required_value = QLabel("0")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search material code, description, group, bead or band...")
        self.search_input.textChanged.connect(self.refresh_table)

        self.product_group_combo = QComboBox()
        self.product_group_combo.addItem("All Product Groups")
        self.product_group_combo.currentTextChanged.connect(self.refresh_table)

        self.active_combo = QComboBox()
        self.active_combo.addItems(["All Status", "Active Only", "Inactive Only"])
        self.active_combo.currentTextChanged.connect(self.refresh_table)

        self.missing_weight_checkbox = QCheckBox("Missing weight only")
        self.missing_weight_checkbox.stateChanged.connect(self.refresh_table)

        self.add_btn = QPushButton("+ Add Product")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.clicked.connect(self.add_product)

        self.edit_btn = QPushButton("Edit Selected")
        self.edit_btn.setObjectName("SecondaryButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.edit_selected_product)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Material",
                "Description",
                "Group",
                "Avg Wgt",
                "Comp Wgt",
                "Bead",
                "Band",
                "Status",
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
            self._metric_card("Total Products", self.total_products_value),
            self._metric_card("Active Products", self.active_products_value),
            self._metric_card("Missing Weight", self.missing_weight_value),
            self._metric_card("Production Required Items", self.production_required_value),
        ]

        for index, card in enumerate(cards):
            grid.addWidget(card, 0, index)

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

        title = QLabel("Product Master Control")
        title.setObjectName("SectionTitle")

        hint = QLabel(
            "Maintain product/material master data used by MPPS stock planning, tonnage, BOM, compound and capacity calculations."
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(hint)

        header.addLayout(title_box, 1)
        header.addWidget(self.add_btn)
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

        status_label = QLabel("Status")
        status_label.setObjectName("FieldLabel")

        form.addWidget(search_label, 0, 0)
        form.addWidget(self.search_input, 0, 1, 1, 5)

        form.addWidget(group_label, 1, 0)
        form.addWidget(self.product_group_combo, 1, 1, 1, 2)

        form.addWidget(status_label, 1, 3)
        form.addWidget(self.active_combo, 1, 4, 1, 2)

        form.setColumnStretch(1, 2)
        form.setColumnStretch(2, 1)
        form.setColumnStretch(4, 2)
        form.setColumnStretch(5, 1)

        layout.addLayout(form)
        layout.addWidget(self.missing_weight_checkbox)

        return card

    def _build_table_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel("Product Master Data")
        title.setObjectName("SectionTitle")

        hint = QLabel(
            "Double-click a row to edit. Changes update the clean MPPS database, not the original raw Excel archive."
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
        self.table.setColumnWidth(2, 115)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 95)
        self.table.setColumnWidth(5, 100)
        self.table.setColumnWidth(6, 85)
        self.table.setColumnWidth(7, 80)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemDoubleClicked.connect(self.edit_selected_product)

    def refresh(self) -> None:
        try:
            self.load_product_groups()
            self.refresh_metrics()
            self.refresh_table()
        except Exception as exc:
            QMessageBox.critical(self, "Product Master Error", str(exc))

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
                        COUNT(*) AS total_products,
                        SUM(CASE WHEN is_active = TRUE THEN 1 ELSE 0 END) AS active_products,
                        SUM(CASE WHEN COALESCE(average_weight, 0) <= 0 THEN 1 ELSE 0 END) AS missing_weight,
                        (
                            SELECT COUNT(*)
                            FROM mpps_stock_planning_view
                            WHERE production_required_qty > 0
                        ) AS production_required_items
                    FROM mpps_stock_items;
                    """
                )
            ).mappings().one()

        self.total_products_value.setText(self._format_int(row["total_products"]))
        self.active_products_value.setText(self._format_int(row["active_products"]))
        self.missing_weight_value.setText(self._format_int(row["missing_weight"]))
        self.production_required_value.setText(self._format_int(row["production_required_items"]))

    def refresh_table(self, *args) -> None:
        self.selected_material_code = None
        self.edit_btn.setEnabled(False)

        search_text = self.search_input.text().strip()
        group_value = self.product_group_combo.currentText().strip()
        active_value = self.active_combo.currentText().strip()

        conditions = []
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
                    OR COALESCE(bead_type, '') ILIKE :search
                    OR COALESCE(band_type, '') ILIKE :search
                )
                """
            )

        if group_value and group_value != "All Product Groups":
            conditions.append("product_group = :product_group")

        if active_value == "Active Only":
            conditions.append("is_active = TRUE")
        elif active_value == "Inactive Only":
            conditions.append("is_active = FALSE")

        if self.missing_weight_checkbox.isChecked():
            conditions.append("COALESCE(average_weight, 0) <= 0")

        where_sql = ""

        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT
                material_code,
                item_description,
                product_group,
                average_weight,
                compound_weight,
                bead_type,
                band_type,
                is_active
            FROM mpps_stock_items
            {where_sql}
            ORDER BY
                is_active DESC,
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
                self._format_decimal(row["average_weight"], 4),
                self._format_decimal(row["compound_weight"], 4),
                row["bead_type"] or "-",
                row["band_type"] or "-",
                "Active" if row["is_active"] else "Inactive",
            ]

            for column_index, value in enumerate(values):
                item = self._readonly_item(value)

                if column_index in {3, 4, 7}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if column_index == 7:
                    self._apply_status_style(item, bool(row["is_active"]))

                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row["material_code"])

                self.table.setItem(row_index, column_index, item)

        self.table.resizeRowsToContents()

    def add_product(self) -> None:
        dialog = ProductEditDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            data = dialog.get_data()
            self.save_product(data, is_new=True)
            self.refresh()
            QMessageBox.information(self, "Product Added", "Product saved successfully.")
        except Exception as exc:
            QMessageBox.critical(self, "Add Product Failed", str(exc))

    def edit_selected_product(self, *args) -> None:
        if not self.selected_material_code:
            return

        product = self.get_product(self.selected_material_code)

        if product is None:
            QMessageBox.warning(self, "Product Missing", "Selected product was not found.")
            return

        dialog = ProductEditDialog(self, product=dict(product))

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            data = dialog.get_data()
            self.save_product(data, is_new=False)
            self.refresh()
            QMessageBox.information(self, "Product Updated", "Product updated successfully.")
        except Exception as exc:
            QMessageBox.critical(self, "Update Product Failed", str(exc))

    def get_product(self, material_code: str):
        with engine.begin() as connection:
            return connection.execute(
                text(
                    """
                    SELECT
                        material_code,
                        item_description,
                        product_group,
                        average_weight,
                        compound_weight,
                        bead_type,
                        band_type,
                        is_active
                    FROM mpps_stock_items
                    WHERE material_code = :material_code
                    LIMIT 1;
                    """
                ),
                {"material_code": material_code},
            ).mappings().first()

    def save_product(self, data: dict, is_new: bool) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO tire_types (
                        tire_code,
                        tire_name,
                        curing_minutes,
                        is_active
                    )
                    VALUES (
                        :material_code,
                        :item_description,
                        30,
                        :is_active
                    )
                    ON CONFLICT (tire_code)
                    DO UPDATE SET
                        tire_name = EXCLUDED.tire_name,
                        is_active = EXCLUDED.is_active;
                    """
                ),
                data,
            )

            tire_type_id = connection.execute(
                text(
                    """
                    SELECT id
                    FROM tire_types
                    WHERE tire_code = :material_code
                    LIMIT 1;
                    """
                ),
                data,
            ).scalar()

            save_data = dict(data)
            save_data["tire_type_id"] = tire_type_id

            connection.execute(
                text(
                    """
                    INSERT INTO mpps_stock_items (
                        material_code,
                        item_description,
                        tire_type_id,
                        product_type,
                        product_group,
                        fg_stock,
                        qc_stock,
                        scrap_stock,
                        blocked_stock,
                        average_weight,
                        compound_weight,
                        bead_type,
                        band_type,
                        is_active,
                        last_updated_date,
                        source_note
                    )
                    VALUES (
                        :material_code,
                        :item_description,
                        :tire_type_id,
                        'TYRE',
                        :product_group,
                        0,
                        0,
                        0,
                        0,
                        :average_weight,
                        :compound_weight,
                        :bead_type,
                        :band_type,
                        :is_active,
                        CURRENT_DATE,
                        'Created or edited from Product Master page.'
                    )
                    ON CONFLICT (material_code)
                    DO UPDATE SET
                        item_description = EXCLUDED.item_description,
                        tire_type_id = EXCLUDED.tire_type_id,
                        product_group = EXCLUDED.product_group,
                        average_weight = EXCLUDED.average_weight,
                        compound_weight = EXCLUDED.compound_weight,
                        bead_type = EXCLUDED.bead_type,
                        band_type = EXCLUDED.band_type,
                        is_active = EXCLUDED.is_active,
                        last_updated_date = CURRENT_DATE,
                        source_note = EXCLUDED.source_note,
                        updated_at = CURRENT_TIMESTAMP;
                    """
                ),
                save_data,
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

    def _apply_status_style(self, item: QTableWidgetItem, is_active: bool) -> None:
        if is_active:
            item.setForeground(QColor("#166534"))
            item.setBackground(QColor("#dcfce7"))
        else:
            item.setForeground(QColor("#991b1b"))
            item.setBackground(QColor("#fee2e2"))

    def _format_int(self, value) -> str:
        try:
            return f"{int(value or 0):,}"
        except Exception:
            return "0"

    def _format_decimal(self, value, decimals: int = 4) -> str:
        try:
            decimal_value = Decimal(str(value or 0))
            return f"{decimal_value:,.{decimals}f}"
        except Exception:
            return "0.0000"