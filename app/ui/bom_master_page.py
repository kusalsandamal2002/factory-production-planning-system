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
    QHeaderView,
    QHBoxLayout,
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


class BomEditDialog(QDialog):
    def __init__(self, parent=None, bom_item: dict | None = None):
        super().__init__(parent)

        self.bom_item = bom_item or {}
        self.is_new = bom_item is None

        self.setWindowTitle("Add BOM Item" if self.is_new else "Edit BOM Item")
        self.setMinimumWidth(680)

        self.finished_item_input = QLineEdit()
        self.finished_item_input.setPlaceholderText("Finished item material code...")

        self.raw_material_code_input = QLineEdit()
        self.raw_material_code_input.setPlaceholderText("Raw material code...")

        self.raw_material_name_input = QLineEdit()
        self.raw_material_name_input.setPlaceholderText("Raw material name / description...")

        self.usage_input = QDoubleSpinBox()
        self.usage_input.setRange(0, 999999999)
        self.usage_input.setDecimals(6)
        self.usage_input.setSingleStep(0.001)

        self.unit_input = QLineEdit()
        self.unit_input.setPlaceholderText("KG / PCS / MTR...")

        self.wastage_input = QDoubleSpinBox()
        self.wastage_input.setRange(0, 100)
        self.wastage_input.setDecimals(4)
        self.wastage_input.setSingleStep(0.1)

        self.active_checkbox = QCheckBox("Active BOM item")
        self.active_checkbox.setChecked(True)

        self.save_btn = QPushButton("Save BOM Item")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.accept)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SecondaryButton")
        self.cancel_btn.clicked.connect(self.reject)

        self._apply_styles()
        self._build_ui()
        self._load_bom_item()

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

        title = QLabel("BOM Master")
        title.setObjectName("Title")

        hint = QLabel(
            "Maintain finished-item to raw-material usage. This BOM data is used to calculate material requirements from production demand."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        self._add_field(form, 0, "Finished Item Code", self.finished_item_input)
        self._add_field(form, 1, "Raw Material Code", self.raw_material_code_input)
        self._add_field(form, 2, "Raw Material Name", self.raw_material_name_input)
        self._add_field(form, 3, "Usage Per Unit", self.usage_input)
        self._add_field(form, 4, "Unit", self.unit_input)
        self._add_field(form, 5, "Wastage %", self.wastage_input)

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

    def _load_bom_item(self) -> None:
        if not self.bom_item:
            self.unit_input.setText("KG")
            return

        self.finished_item_input.setText(str(self.bom_item.get("finished_item_code") or ""))
        self.raw_material_code_input.setText(str(self.bom_item.get("raw_material_code") or ""))
        self.raw_material_name_input.setText(str(self.bom_item.get("raw_material_name") or ""))

        self.usage_input.setValue(float(self.bom_item.get("usage_per_unit") or 0))
        self.unit_input.setText(str(self.bom_item.get("unit") or "KG"))
        self.wastage_input.setValue(float(self.bom_item.get("wastage_percentage") or 0))
        self.active_checkbox.setChecked(bool(self.bom_item.get("is_active")))

    def get_data(self) -> dict:
        finished_item = self.finished_item_input.text().strip()
        raw_code = self.raw_material_code_input.text().strip()
        raw_name = self.raw_material_name_input.text().strip()
        unit = self.unit_input.text().strip()

        if not finished_item:
            raise ValueError("Finished Item Code is required.")

        if not raw_code:
            raise ValueError("Raw Material Code is required.")

        if not raw_name:
            raise ValueError("Raw Material Name is required.")

        if self.usage_input.value() <= 0:
            raise ValueError("Usage Per Unit must be greater than 0.")

        if not unit:
            raise ValueError("Unit is required.")

        return {
            "id": self.bom_item.get("id"),
            "finished_item_code": finished_item,
            "raw_material_code": raw_code,
            "raw_material_name": raw_name,
            "usage_per_unit": Decimal(str(self.usage_input.value())),
            "unit": unit,
            "wastage_percentage": Decimal(str(self.wastage_input.value())),
            "is_active": self.active_checkbox.isChecked(),
        }


class BomMasterPage(QWidget):
    def __init__(self):
        super().__init__()

        self.selected_bom_id: int | None = None

        self.total_bom_value = QLabel("0")
        self.active_bom_value = QLabel("0")
        self.finished_items_value = QLabel("0")
        self.raw_materials_value = QLabel("0")
        self.missing_usage_value = QLabel("0")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search finished item, raw material code or raw material name...")
        self.search_input.textChanged.connect(self.refresh_table)

        self.finished_item_input = QLineEdit()
        self.finished_item_input.setPlaceholderText("Filter finished item code...")
        self.finished_item_input.textChanged.connect(self.refresh_table)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["All Status", "Active Only", "Inactive Only"])
        self.status_combo.currentTextChanged.connect(self.refresh_table)

        self.missing_usage_checkbox = QCheckBox("Missing / zero usage only")
        self.missing_usage_checkbox.stateChanged.connect(self.refresh_table)

        self.add_btn = QPushButton("+ Add BOM Item")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.clicked.connect(self.add_bom_item)

        self.edit_btn = QPushButton("Edit Selected")
        self.edit_btn.setObjectName("SecondaryButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.edit_selected_bom_item)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Finished Item",
                "Raw Code",
                "Raw Material Name",
                "Usage",
                "Unit",
                "Wastage %",
                "Status",
                "Source",
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
            self._metric_card("Total BOM Rows", self.total_bom_value),
            self._metric_card("Active BOM Rows", self.active_bom_value),
            self._metric_card("Finished Items", self.finished_items_value),
            self._metric_card("Raw Materials", self.raw_materials_value),
            self._metric_card("Missing Usage", self.missing_usage_value),
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

        title = QLabel("BOM Master Control")
        title.setObjectName("SectionTitle")

        hint = QLabel(
            "Maintain raw material usage per finished item. This page replaces manual BOM sheet checking in Excel."
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

        finished_label = QLabel("Finished Item")
        finished_label.setObjectName("FieldLabel")

        status_label = QLabel("Status")
        status_label.setObjectName("FieldLabel")

        form.addWidget(search_label, 0, 0)
        form.addWidget(self.search_input, 0, 1, 1, 5)

        form.addWidget(finished_label, 1, 0)
        form.addWidget(self.finished_item_input, 1, 1, 1, 2)

        form.addWidget(status_label, 1, 3)
        form.addWidget(self.status_combo, 1, 4, 1, 2)

        form.setColumnStretch(1, 2)
        form.setColumnStretch(2, 1)
        form.setColumnStretch(4, 2)
        form.setColumnStretch(5, 1)

        layout.addLayout(form)
        layout.addWidget(self.missing_usage_checkbox)

        return card

    def _build_table_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel("BOM Master Data")
        title.setObjectName("SectionTitle")

        hint = QLabel(
            "Double-click a row to edit. Changes update clean MPPS BOM data, not the original raw Excel archive."
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
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 130)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(3, 95)
        self.table.setColumnWidth(4, 75)
        self.table.setColumnWidth(5, 95)
        self.table.setColumnWidth(6, 85)
        self.table.setColumnWidth(7, 95)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemDoubleClicked.connect(self.edit_selected_bom_item)

    def refresh(self) -> None:
        try:
            self.refresh_metrics()
            self.refresh_table()
        except Exception as exc:
            QMessageBox.critical(self, "BOM Master Error", str(exc))

    def refresh_metrics(self) -> None:
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS total_bom,
                        SUM(CASE WHEN is_active = TRUE THEN 1 ELSE 0 END) AS active_bom,
                        COUNT(DISTINCT finished_item_code) AS finished_items,
                        COUNT(DISTINCT raw_material_code) AS raw_materials,
                        SUM(CASE WHEN COALESCE(usage_per_unit, 0) <= 0 THEN 1 ELSE 0 END) AS missing_usage
                    FROM mpps_bom_items;
                    """
                )
            ).mappings().one()

        self.total_bom_value.setText(self._format_int(row["total_bom"]))
        self.active_bom_value.setText(self._format_int(row["active_bom"]))
        self.finished_items_value.setText(self._format_int(row["finished_items"]))
        self.raw_materials_value.setText(self._format_int(row["raw_materials"]))
        self.missing_usage_value.setText(self._format_int(row["missing_usage"]))

    def refresh_table(self, *args) -> None:
        self.selected_bom_id = None
        self.edit_btn.setEnabled(False)

        search_text = self.search_input.text().strip()
        finished_text = self.finished_item_input.text().strip()
        status_value = self.status_combo.currentText().strip()

        conditions = []
        params = {
            "search": f"%{search_text}%",
            "finished": f"%{finished_text}%",
        }

        if search_text:
            conditions.append(
                """
                (
                    finished_item_code ILIKE :search
                    OR raw_material_code ILIKE :search
                    OR raw_material_name ILIKE :search
                    OR COALESCE(unit, '') ILIKE :search
                )
                """
            )

        if finished_text:
            conditions.append("finished_item_code ILIKE :finished")

        if status_value == "Active Only":
            conditions.append("is_active = TRUE")
        elif status_value == "Inactive Only":
            conditions.append("is_active = FALSE")

        if self.missing_usage_checkbox.isChecked():
            conditions.append("COALESCE(usage_per_unit, 0) <= 0")

        where_sql = ""
        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT
                id,
                finished_item_code,
                raw_material_code,
                raw_material_name,
                usage_per_unit,
                unit,
                wastage_percentage,
                is_active,
                source_sheet
            FROM mpps_bom_items
            {where_sql}
            ORDER BY
                finished_item_code ASC,
                raw_material_code ASC
            LIMIT 1000;
        """

        with engine.begin() as connection:
            rows = connection.execute(text(sql), params).mappings().all()

        self.table.setRowCount(0)

        for row_index, row in enumerate(rows):
            self.table.insertRow(row_index)

            values = [
                row["finished_item_code"],
                row["raw_material_code"],
                row["raw_material_name"],
                self._format_decimal(row["usage_per_unit"], 6),
                row["unit"] or "-",
                self._format_decimal(row["wastage_percentage"], 4),
                "Active" if row["is_active"] else "Inactive",
                row["source_sheet"] or "App",
            ]

            for column_index, value in enumerate(values):
                item = self._readonly_item(value)

                if column_index in {3, 4, 5, 6, 7}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if column_index == 6:
                    self._apply_status_style(item, bool(row["is_active"]))

                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))

                self.table.setItem(row_index, column_index, item)

        self.table.resizeRowsToContents()

    def add_bom_item(self) -> None:
        dialog = BomEditDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            data = dialog.get_data()
            self.save_bom_item(data, is_new=True)
            self.refresh()
            QMessageBox.information(self, "BOM Added", "BOM item saved successfully.")
        except Exception as exc:
            QMessageBox.critical(self, "Add BOM Failed", str(exc))

    def edit_selected_bom_item(self, *args) -> None:
        if not self.selected_bom_id:
            return

        bom_item = self.get_bom_item(self.selected_bom_id)

        if bom_item is None:
            QMessageBox.warning(self, "BOM Item Missing", "Selected BOM item was not found.")
            return

        dialog = BomEditDialog(self, dict(bom_item))

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            data = dialog.get_data()
            self.save_bom_item(data, is_new=False)
            self.refresh()
            QMessageBox.information(self, "BOM Updated", "BOM item updated successfully.")
        except Exception as exc:
            QMessageBox.critical(self, "Update BOM Failed", str(exc))

    def get_bom_item(self, bom_id: int):
        with engine.begin() as connection:
            return connection.execute(
                text(
                    """
                    SELECT
                        id,
                        finished_item_code,
                        raw_material_code,
                        raw_material_name,
                        usage_per_unit,
                        unit,
                        wastage_percentage,
                        is_active
                    FROM mpps_bom_items
                    WHERE id = :id
                    LIMIT 1;
                    """
                ),
                {"id": bom_id},
            ).mappings().first()

    def save_bom_item(self, data: dict, is_new: bool) -> None:
        with engine.begin() as connection:
            if is_new:
                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_bom_items (
                            finished_item_code,
                            raw_material_code,
                            raw_material_name,
                            usage_per_unit,
                            unit,
                            wastage_percentage,
                            is_active,
                            source_note
                        )
                        VALUES (
                            :finished_item_code,
                            :raw_material_code,
                            :raw_material_name,
                            :usage_per_unit,
                            :unit,
                            :wastage_percentage,
                            :is_active,
                            'Created from BOM Master page.'
                        );
                        """
                    ),
                    data,
                )
            else:
                connection.execute(
                    text(
                        """
                        UPDATE mpps_bom_items
                        SET
                            finished_item_code = :finished_item_code,
                            raw_material_code = :raw_material_code,
                            raw_material_name = :raw_material_name,
                            usage_per_unit = :usage_per_unit,
                            unit = :unit,
                            wastage_percentage = :wastage_percentage,
                            is_active = :is_active,
                            source_note = 'Edited from BOM Master page.',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id;
                        """
                    ),
                    data,
                )

    def on_selection_changed(self) -> None:
        selected_items = self.table.selectedItems()

        if not selected_items:
            self.selected_bom_id = None
            self.edit_btn.setEnabled(False)
            return

        row = selected_items[0].row()
        item = self.table.item(row, 0)

        if item is None:
            self.selected_bom_id = None
            self.edit_btn.setEnabled(False)
            return

        self.selected_bom_id = item.data(Qt.ItemDataRole.UserRole)
        self.edit_btn.setEnabled(bool(self.selected_bom_id))

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