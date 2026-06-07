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


class CompoundEditDialog(QDialog):
    def __init__(self, parent=None, compound_item: dict | None = None):
        super().__init__(parent)

        self.compound_item = compound_item or {}
        self.is_new = compound_item is None

        self.setWindowTitle("Add Compound Item" if self.is_new else "Edit Compound Item")
        self.setMinimumWidth(680)

        self.item_code_input = QLineEdit()
        self.item_code_input.setPlaceholderText("Finished item / material code...")

        self.compound_code_input = QLineEdit()
        self.compound_code_input.setPlaceholderText("Compound code...")

        self.compound_name_input = QLineEdit()
        self.compound_name_input.setPlaceholderText("Compound name / description...")

        self.stage_combo = QComboBox()
        self.stage_combo.addItems(
            [
                "MAIN",
                "1ST_STAGE",
                "2ND_STAGE",
                "REWORK",
                "RECYCLE",
                "OTHER",
            ]
        )

        self.weight_input = QDoubleSpinBox()
        self.weight_input.setRange(0, 999999999)
        self.weight_input.setDecimals(6)
        self.weight_input.setSingleStep(0.001)

        self.active_checkbox = QCheckBox("Active compound item")
        self.active_checkbox.setChecked(True)

        self.save_btn = QPushButton("Save Compound Item")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.accept)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SecondaryButton")
        self.cancel_btn.clicked.connect(self.reject)

        self._apply_styles()
        self._build_ui()
        self._load_compound_item()

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
            QComboBox,
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
            QComboBox:focus,
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

        title = QLabel("Compound Master")
        title.setObjectName("Title")

        hint = QLabel(
            "Maintain compound requirement data per finished item. This data is used to calculate compound requirement from production demand."
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        self._add_field(form, 0, "Item Code", self.item_code_input)
        self._add_field(form, 1, "Compound Code", self.compound_code_input)
        self._add_field(form, 2, "Compound Name", self.compound_name_input)
        self._add_field(form, 3, "Stage", self.stage_combo)
        self._add_field(form, 4, "Weight Per Unit", self.weight_input)

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

    def _load_compound_item(self) -> None:
        if not self.compound_item:
            return

        self.item_code_input.setText(str(self.compound_item.get("item_code") or ""))
        self.compound_code_input.setText(str(self.compound_item.get("compound_code") or ""))
        self.compound_name_input.setText(str(self.compound_item.get("compound_name") or ""))

        stage = str(self.compound_item.get("stage") or "MAIN")
        stage_index = self.stage_combo.findText(stage)

        if stage_index >= 0:
            self.stage_combo.setCurrentIndex(stage_index)
        else:
            self.stage_combo.addItem(stage)
            self.stage_combo.setCurrentText(stage)

        self.weight_input.setValue(float(self.compound_item.get("compound_weight_per_unit") or 0))
        self.active_checkbox.setChecked(bool(self.compound_item.get("is_active")))

    def get_data(self) -> dict:
        item_code = self.item_code_input.text().strip()
        compound_code = self.compound_code_input.text().strip()
        compound_name = self.compound_name_input.text().strip()
        stage = self.stage_combo.currentText().strip()

        if not item_code:
            raise ValueError("Item Code is required.")

        if not compound_code:
            raise ValueError("Compound Code is required.")

        if not compound_name:
            raise ValueError("Compound Name is required.")

        if self.weight_input.value() <= 0:
            raise ValueError("Weight Per Unit must be greater than 0.")

        return {
            "id": self.compound_item.get("id"),
            "item_code": item_code,
            "compound_code": compound_code,
            "compound_name": compound_name,
            "stage": stage,
            "compound_weight_per_unit": Decimal(str(self.weight_input.value())),
            "is_active": self.active_checkbox.isChecked(),
        }


class CompoundMasterPage(QWidget):
    def __init__(self):
        super().__init__()

        self.selected_compound_id: int | None = None

        self.total_rows_value = QLabel("0")
        self.active_rows_value = QLabel("0")
        self.item_codes_value = QLabel("0")
        self.compounds_value = QLabel("0")
        self.missing_weight_value = QLabel("0")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search item code, compound code, compound name or stage...")
        self.search_input.textChanged.connect(self.refresh_table)

        self.item_code_input = QLineEdit()
        self.item_code_input.setPlaceholderText("Filter item code...")
        self.item_code_input.textChanged.connect(self.refresh_table)

        self.stage_combo = QComboBox()
        self.stage_combo.addItem("All Stages")
        self.stage_combo.currentTextChanged.connect(self.refresh_table)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["All Status", "Active Only", "Inactive Only"])
        self.status_combo.currentTextChanged.connect(self.refresh_table)

        self.missing_weight_checkbox = QCheckBox("Missing / zero weight only")
        self.missing_weight_checkbox.stateChanged.connect(self.refresh_table)

        self.add_btn = QPushButton("+ Add Compound")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.clicked.connect(self.add_compound_item)

        self.edit_btn = QPushButton("Edit Selected")
        self.edit_btn.setObjectName("SecondaryButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.edit_selected_compound_item)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "Item Code",
                "Compound Code",
                "Compound Name",
                "Stage",
                "Weight",
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
            self._metric_card("Total Compound Rows", self.total_rows_value),
            self._metric_card("Active Rows", self.active_rows_value),
            self._metric_card("Item Codes", self.item_codes_value),
            self._metric_card("Compound Codes", self.compounds_value),
            self._metric_card("Missing Weight", self.missing_weight_value),
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

        title = QLabel("Compound Master Control")
        title.setObjectName("SectionTitle")

        hint = QLabel(
            "Maintain compound requirement data by item and stage. This page replaces manual compound sheet checking in Excel."
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

        item_label = QLabel("Item Code")
        item_label.setObjectName("FieldLabel")

        stage_label = QLabel("Stage")
        stage_label.setObjectName("FieldLabel")

        status_label = QLabel("Status")
        status_label.setObjectName("FieldLabel")

        form.addWidget(search_label, 0, 0)
        form.addWidget(self.search_input, 0, 1, 1, 5)

        form.addWidget(item_label, 1, 0)
        form.addWidget(self.item_code_input, 1, 1)

        form.addWidget(stage_label, 1, 2)
        form.addWidget(self.stage_combo, 1, 3)

        form.addWidget(status_label, 1, 4)
        form.addWidget(self.status_combo, 1, 5)

        form.setColumnStretch(1, 2)
        form.setColumnStretch(3, 1)
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

        title = QLabel("Compound Master Data")
        title.setObjectName("SectionTitle")

        hint = QLabel(
            "Double-click a row to edit. Changes update clean MPPS compound data, not the original raw Excel archive."
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

        self.table.setColumnWidth(0, 125)
        self.table.setColumnWidth(1, 145)
        self.table.setColumnWidth(3, 105)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 85)
        self.table.setColumnWidth(6, 105)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemDoubleClicked.connect(self.edit_selected_compound_item)

    def refresh(self) -> None:
        try:
            self.load_stages()
            self.refresh_metrics()
            self.refresh_table()
        except Exception as exc:
            QMessageBox.critical(self, "Compound Master Error", str(exc))

    def load_stages(self) -> None:
        current_value = self.stage_combo.currentText()

        with engine.begin() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT DISTINCT stage
                    FROM mpps_compound_master
                    WHERE stage IS NOT NULL
                      AND TRIM(stage) <> ''
                    ORDER BY stage;
                    """
                )
            ).scalars().all()

        self.stage_combo.blockSignals(True)
        self.stage_combo.clear()
        self.stage_combo.addItem("All Stages")

        for value in rows:
            self.stage_combo.addItem(str(value))

        index = self.stage_combo.findText(current_value)

        if index >= 0:
            self.stage_combo.setCurrentIndex(index)

        self.stage_combo.blockSignals(False)

    def refresh_metrics(self) -> None:
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS total_rows,
                        SUM(CASE WHEN is_active = TRUE THEN 1 ELSE 0 END) AS active_rows,
                        COUNT(DISTINCT item_code) AS item_codes,
                        COUNT(DISTINCT compound_code) AS compound_codes,
                        SUM(CASE WHEN COALESCE(compound_weight_per_unit, 0) <= 0 THEN 1 ELSE 0 END) AS missing_weight
                    FROM mpps_compound_master;
                    """
                )
            ).mappings().one()

        self.total_rows_value.setText(self._format_int(row["total_rows"]))
        self.active_rows_value.setText(self._format_int(row["active_rows"]))
        self.item_codes_value.setText(self._format_int(row["item_codes"]))
        self.compounds_value.setText(self._format_int(row["compound_codes"]))
        self.missing_weight_value.setText(self._format_int(row["missing_weight"]))

    def refresh_table(self, *args) -> None:
        self.selected_compound_id = None
        self.edit_btn.setEnabled(False)

        search_text = self.search_input.text().strip()
        item_text = self.item_code_input.text().strip()
        stage_value = self.stage_combo.currentText().strip()
        status_value = self.status_combo.currentText().strip()

        conditions = []
        params = {
            "search": f"%{search_text}%",
            "item_code": f"%{item_text}%",
            "stage": stage_value,
        }

        if search_text:
            conditions.append(
                """
                (
                    item_code ILIKE :search
                    OR compound_code ILIKE :search
                    OR compound_name ILIKE :search
                    OR COALESCE(stage, '') ILIKE :search
                )
                """
            )

        if item_text:
            conditions.append("item_code ILIKE :item_code")

        if stage_value and stage_value != "All Stages":
            conditions.append("stage = :stage")

        if status_value == "Active Only":
            conditions.append("is_active = TRUE")
        elif status_value == "Inactive Only":
            conditions.append("is_active = FALSE")

        if self.missing_weight_checkbox.isChecked():
            conditions.append("COALESCE(compound_weight_per_unit, 0) <= 0")

        where_sql = ""
        if conditions:
            where_sql = "WHERE " + " AND ".join(conditions)

        sql = f"""
            SELECT
                id,
                item_code,
                compound_code,
                compound_name,
                stage,
                compound_weight_per_unit,
                is_active,
                source_sheet
            FROM mpps_compound_master
            {where_sql}
            ORDER BY
                item_code ASC,
                compound_code ASC
            LIMIT 1000;
        """

        with engine.begin() as connection:
            rows = connection.execute(text(sql), params).mappings().all()

        self.table.setRowCount(0)

        for row_index, row in enumerate(rows):
            self.table.insertRow(row_index)

            values = [
                row["item_code"],
                row["compound_code"],
                row["compound_name"],
                row["stage"] or "-",
                self._format_decimal(row["compound_weight_per_unit"], 6),
                "Active" if row["is_active"] else "Inactive",
                row["source_sheet"] or "App",
            ]

            for column_index, value in enumerate(values):
                item = self._readonly_item(value)

                if column_index in {3, 4, 5, 6}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if column_index == 5:
                    self._apply_status_style(item, bool(row["is_active"]))

                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))

                self.table.setItem(row_index, column_index, item)

        self.table.resizeRowsToContents()

    def add_compound_item(self) -> None:
        dialog = CompoundEditDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            data = dialog.get_data()
            self.save_compound_item(data, is_new=True)
            self.refresh()
            QMessageBox.information(self, "Compound Added", "Compound item saved successfully.")
        except Exception as exc:
            QMessageBox.critical(self, "Add Compound Failed", str(exc))

    def edit_selected_compound_item(self, *args) -> None:
        if not self.selected_compound_id:
            return

        compound_item = self.get_compound_item(self.selected_compound_id)

        if compound_item is None:
            QMessageBox.warning(self, "Compound Missing", "Selected compound item was not found.")
            return

        dialog = CompoundEditDialog(self, dict(compound_item))

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            data = dialog.get_data()
            self.save_compound_item(data, is_new=False)
            self.refresh()
            QMessageBox.information(self, "Compound Updated", "Compound item updated successfully.")
        except Exception as exc:
            QMessageBox.critical(self, "Update Compound Failed", str(exc))

    def get_compound_item(self, compound_id: int):
        with engine.begin() as connection:
            return connection.execute(
                text(
                    """
                    SELECT
                        id,
                        item_code,
                        compound_code,
                        compound_name,
                        stage,
                        compound_weight_per_unit,
                        is_active
                    FROM mpps_compound_master
                    WHERE id = :id
                    LIMIT 1;
                    """
                ),
                {"id": compound_id},
            ).mappings().first()

    def save_compound_item(self, data: dict, is_new: bool) -> None:
        with engine.begin() as connection:
            if is_new:
                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_compound_master (
                            item_code,
                            compound_code,
                            compound_name,
                            compound_weight_per_unit,
                            stage,
                            is_active,
                            source_note
                        )
                        VALUES (
                            :item_code,
                            :compound_code,
                            :compound_name,
                            :compound_weight_per_unit,
                            :stage,
                            :is_active,
                            'Created from Compound Master page.'
                        );
                        """
                    ),
                    data,
                )
            else:
                connection.execute(
                    text(
                        """
                        UPDATE mpps_compound_master
                        SET
                            item_code = :item_code,
                            compound_code = :compound_code,
                            compound_name = :compound_name,
                            compound_weight_per_unit = :compound_weight_per_unit,
                            stage = :stage,
                            is_active = :is_active,
                            source_note = 'Edited from Compound Master page.',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id;
                        """
                    ),
                    data,
                )

    def on_selection_changed(self) -> None:
        selected_items = self.table.selectedItems()

        if not selected_items:
            self.selected_compound_id = None
            self.edit_btn.setEnabled(False)
            return

        row = selected_items[0].row()
        item = self.table.item(row, 0)

        if item is None:
            self.selected_compound_id = None
            self.edit_btn.setEnabled(False)
            return

        self.selected_compound_id = item.data(Qt.ItemDataRole.UserRole)
        self.edit_btn.setEnabled(bool(self.selected_compound_id))

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