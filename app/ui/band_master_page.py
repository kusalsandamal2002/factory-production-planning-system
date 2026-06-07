from __future__ import annotations

from decimal import Decimal
from PySide6.QtCore import Qt
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


class BandEditDialog(QDialog):
    def __init__(self, parent=None, band_item: dict | None = None):
        super().__init__(parent)
        self.band_item = band_item or {}
        self.is_new = band_item is None

        self.setWindowTitle("Add Band Record" if self.is_new else "Edit Band Record")
        self.setMinimumWidth(550)

        self.item_code_input = QLineEdit()
        self.item_code_input.setPlaceholderText("Material code or tyre size group...")
        self.band_code_input = QLineEdit()
        self.band_code_input.setPlaceholderText("Band code (e.g., BND-01)...")
        self.band_type_input = QLineEdit()
        self.band_type_input.setPlaceholderText("Band type description...")

        self.usage_input = QDoubleSpinBox()
        self.usage_input.setRange(0, 999999)
        self.usage_input.setDecimals(4)
        self.usage_input.setValue(1.0)

        self.active_checkbox = QCheckBox("Active Band Link")
        self.active_checkbox.setChecked(True)

        self.save_btn = QPushButton("Save Band Record")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.accept)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setObjectName("SecondaryButton")
        self.cancel_btn.clicked.connect(self.reject)

        self._apply_styles()
        self._build_ui()
        self._load_data()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background: #f8fafc; }
            QFrame#Card {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }
            QLabel#Title {
                color: #0f172a;
                font-size: 14pt;
                font-weight: 950;
            }
            QLabel#Hint {
                color: #64748b;
                font-size: 9.5pt;
            }
            QLabel#FieldLabel {
                color: #334155;
                font-size: 9pt;
                font-weight: 850;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        
        card = QFrame()
        card.setObjectName("Card")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        title = QLabel("Band Master Record")
        title.setObjectName("Title")
        hint = QLabel("Link finished items/sizes to their band codes and usage requirements.")
        hint.setObjectName("Hint")
        layout.addWidget(title)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        form.addWidget(QLabel("Item Code / Size"), 0, 0)
        form.addWidget(self.item_code_input, 0, 1)
        form.addWidget(QLabel("Band Code"), 1, 0)
        form.addWidget(self.band_code_input, 1, 1)
        form.addWidget(QLabel("Band Type"), 2, 0)
        form.addWidget(self.band_type_input, 2, 1)
        form.addWidget(QLabel("Usage per Tyre"), 3, 0)
        form.addWidget(self.usage_input, 3, 1)

        layout.addLayout(form)
        layout.addWidget(self.active_checkbox)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.cancel_btn)
        button_row.addWidget(self.save_btn)
        layout.addLayout(button_row)

        root.addWidget(card)

    def _load_data(self) -> None:
        if self.is_new:
            return
        self.item_code_input.setText(str(self.band_item.get("item_code") or ""))
        self.item_code_input.setReadOnly(True)
        self.band_code_input.setText(str(self.band_item.get("band_code") or ""))
        self.band_type_input.setText(str(self.band_item.get("band_type") or ""))
        self.usage_input.setValue(float(self.band_item.get("band_usage_per_tyre") or 1.0))
        self.active_checkbox.setChecked(bool(self.band_item.get("is_active")))

    def get_data(self) -> dict:
        item_code = self.item_code_input.text().strip()
        band_code = self.band_code_input.text().strip()
        band_type = self.band_type_input.text().strip()

        if not item_code:
            raise ValueError("Item Code is required.")
        if not band_type:
            raise ValueError("Band Type description is required.")

        return {
            "id": self.band_item.get("id"),
            "item_code": item_code,
            "band_code": band_code or None,
            "band_type": band_type,
            "band_usage_per_tyre": Decimal(str(self.usage_input.value())),
            "is_active": self.active_checkbox.isChecked(),
        }


class BandMasterPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.selected_band_id: int | None = None

        # Widgets
        self.total_bands_value = QLabel("0")
        self.active_bands_value = QLabel("0")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search item code, band code, or band type...")
        self.search_input.textChanged.connect(self.refresh_table)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["All Status", "Active Only", "Inactive Only"])
        self.status_combo.currentTextChanged.connect(self.refresh_table)

        self.add_btn = QPushButton("+ Add Band link")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.clicked.connect(self.add_band)

        self.edit_btn = QPushButton("Edit Selected")
        self.edit_btn.setObjectName("SecondaryButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.edit_selected_band)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["ID", "Item Code / Size", "Band Code", "Band Type", "Usage per Tyre", "Status"])

        self._setup_table()
        self._apply_styles()
        self._build_ui()
        self.refresh()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#ControlCard,
            QFrame#TableCard,
            QFrame#MetricCard {
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
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # Metrics grid
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(14)
        metrics_layout.addWidget(self._metric_card("Total Band links", self.total_bands_value), 1)
        metrics_layout.addWidget(self._metric_card("Active Band links", self.active_bands_value), 1)
        root.addLayout(metrics_layout)

        # Controls card
        ctrl_card = QFrame()
        ctrl_card.setObjectName("ControlCard")
        ctrl_layout = QVBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(18, 16, 18, 18)
        ctrl_layout.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("Band Master Control")
        title.setObjectName("SectionTitle")
        hint = QLabel("Link finished items and size profiles to band components used in production planning.")
        hint.setObjectName("SectionHint")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        header.addLayout(title_box, 1)
        header.addWidget(self.add_btn)
        header.addWidget(self.edit_btn)
        header.addWidget(self.refresh_btn)
        ctrl_layout.addLayout(header)

        form = QHBoxLayout()
        form.setSpacing(12)
        form.addWidget(QLabel("Search"))
        form.addWidget(self.search_input, 2)
        form.addWidget(QLabel("Status"))
        form.addWidget(self.status_combo, 1)
        ctrl_layout.addLayout(form)

        root.addWidget(ctrl_card)

        # Table card
        table_card = QFrame()
        table_card.setObjectName("TableCard")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.setSpacing(12)

        table_title = QLabel("Band Master Specifications")
        table_title.setObjectName("SectionTitle")
        table_layout.addWidget(table_title)
        table_layout.addWidget(self.table, 1)

        root.addWidget(table_card, 1)

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

    def _setup_table(self) -> None:
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setAlternatingRowColors(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(2, 120)
        self.table.setColumnWidth(4, 130)
        self.table.setColumnWidth(5, 100)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemDoubleClicked.connect(self.edit_selected_band)

    def refresh(self) -> None:
        try:
            self.refresh_metrics()
            self.refresh_table()
        except Exception as exc:
            QMessageBox.critical(self, "Band Master Error", f"Failed to refresh: {exc}")

    def refresh_metrics(self) -> None:
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS total_bands,
                        SUM(CASE WHEN is_active = TRUE THEN 1 ELSE 0 END) AS active_bands
                    FROM mpps_band_master;
                    """
                )
            ).mappings().one()

        self.total_bands_value.setText(str(row["total_bands"] or 0))
        self.active_bands_value.setText(str(row["active_bands"] or 0))

    def refresh_table(self) -> None:
        self.selected_band_id = None
        self.edit_btn.setEnabled(False)

        search_text = self.search_input.text().strip()
        status_value = self.status_combo.currentText()

        conditions = []
        params = {"search": f"%{search_text}%"}

        if search_text:
            conditions.append("(item_code ILIKE :search OR band_code ILIKE :search OR band_type ILIKE :search)")

        if status_value == "Active Only":
            conditions.append("is_active = TRUE")
        elif status_value == "Inactive Only":
            conditions.append("is_active = FALSE")

        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

        sql = f"""
            SELECT id, item_code, band_code, band_type, band_usage_per_tyre, is_active
            FROM mpps_band_master
            {where_sql}
            ORDER BY item_code ASC, band_code ASC;
        """

        with engine.begin() as connection:
            rows = connection.execute(text(sql), params).mappings().all()

        self.table.setRowCount(0)
        for idx, row in enumerate(rows):
            self.table.insertRow(idx)

            items = [
                str(row["id"]),
                row["item_code"],
                row["band_code"] or "-",
                row["band_type"],
                f"{row['band_usage_per_tyre']:.4f}",
                "Active" if row["is_active"] else "Inactive"
            ]

            for col_idx, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx in (0, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col_idx == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.table.setItem(idx, col_idx, item)

        self.table.resizeRowsToContents()

    def on_selection_changed(self) -> None:
        ranges = self.table.selectedRanges()
        if not ranges:
            self.selected_band_id = None
            self.edit_btn.setEnabled(False)
            return
        row = ranges[0].topRow()
        item = self.table.item(row, 0)
        if item is not None:
            self.selected_band_id = item.data(Qt.ItemDataRole.UserRole)
            self.edit_btn.setEnabled(True)

    def add_band(self) -> None:
        dialog = BandEditDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            data = dialog.get_data()
            username = self.current_user.username if self.current_user else "anonymous"

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_band_master (
                            item_code, band_code, band_type, band_usage_per_tyre, is_active
                        )
                        VALUES (
                            :item_code, :band_code, :band_type, :band_usage_per_tyre, :is_active
                        );
                        """
                    ),
                    data
                )

                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_audit_logs (username, action_type, table_name, record_id, new_values, note)
                        VALUES (:username, 'INSERT', 'mpps_band_master', :record, :val, 'Added new band specification.');
                        """
                    ),
                    {"username": username, "record": data["item_code"], "val": str(data)}
                )

            QMessageBox.information(self, "Success", "Band specification added successfully.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error Saving Band", f"Failed to save record: {exc}")

    def edit_selected_band(self) -> None:
        if not self.selected_band_id:
            return

        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT * FROM mpps_band_master WHERE id = :id;"),
                {"id": self.selected_band_id}
            ).mappings().first()

        if not row:
            QMessageBox.warning(self, "Edit Band", "Record no longer exists.")
            return

        dialog = BandEditDialog(self, dict(row))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            data = dialog.get_data()
            username = self.current_user.username if self.current_user else "anonymous"

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE mpps_band_master
                        SET band_code = :band_code,
                            band_type = :band_type,
                            band_usage_per_tyre = :band_usage_per_tyre,
                            is_active = :is_active,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = :id;
                        """
                    ),
                    data
                )

                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_audit_logs (username, action_type, table_name, record_id, old_values, new_values, note)
                        VALUES (:username, 'UPDATE', 'mpps_band_master', :record, :old, :new, 'Updated band specification.');
                        """
                    ),
                    {
                        "username": username,
                        "record": data["item_code"],
                        "old": str(dict(row)),
                        "new": str(data)
                    }
                )

            QMessageBox.information(self, "Success", "Band specification updated successfully.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error Saving Band", f"Failed to save record: {exc}")
