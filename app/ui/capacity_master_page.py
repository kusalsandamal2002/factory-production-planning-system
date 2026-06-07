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


class CapacityEditDialog(QDialog):
    def __init__(self, parent=None, capacity_item: dict | None = None):
        super().__init__(parent)
        self.capacity_item = capacity_item or {}
        self.is_new = capacity_item is None

        self.setWindowTitle("Add Capacity Record" if self.is_new else "Edit Capacity Record")
        self.setMinimumWidth(550)

        self.item_code_input = QLineEdit()
        self.item_code_input.setPlaceholderText("Material code or size group category...")

        self.running_moulds_input = QDoubleSpinBox()
        self.running_moulds_input.setRange(0, 9999)
        self.running_moulds_input.setDecimals(2)
        self.running_moulds_input.setValue(0.0)
        self.running_moulds_input.valueChanged.connect(self._auto_calc_daily)

        self.per_mould_input = QDoubleSpinBox()
        self.per_mould_input.setRange(0, 999999)
        self.per_mould_input.setDecimals(2)
        self.per_mould_input.setValue(0.0)
        self.per_mould_input.valueChanged.connect(self._auto_calc_daily)

        self.daily_capacity_input = QDoubleSpinBox()
        self.daily_capacity_input.setRange(0, 9999999)
        self.daily_capacity_input.setDecimals(2)
        self.daily_capacity_input.setValue(0.0)

        self.active_checkbox = QCheckBox("Active Capacity Config")
        self.active_checkbox.setChecked(True)

        self.save_btn = QPushButton("Save Capacity Link")
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

        title = QLabel("Capacity Master Specification")
        title.setObjectName("Title")
        hint = QLabel("Set running moulds, mould productivity rate, and daily available capacity in units.")
        hint.setObjectName("Hint")
        layout.addWidget(title)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        form.addWidget(QLabel("Item Code / Size Group"), 0, 0)
        form.addWidget(self.item_code_input, 0, 1)
        form.addWidget(QLabel("Running Moulds"), 1, 0)
        form.addWidget(self.running_moulds_input, 1, 1)
        form.addWidget(QLabel("Per Mould Capacity (daily)"), 2, 0)
        form.addWidget(self.per_mould_input, 2, 1)
        form.addWidget(QLabel("Available Daily Capacity"), 3, 0)
        form.addWidget(self.daily_capacity_input, 3, 1)

        layout.addLayout(form)
        layout.addWidget(self.active_checkbox)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.cancel_btn)
        button_row.addWidget(self.save_btn)
        layout.addLayout(button_row)

        root.addWidget(card)

    def _auto_calc_daily(self) -> None:
        moulds = self.running_moulds_input.value()
        rate = self.per_mould_input.value()
        self.daily_capacity_input.setValue(moulds * rate)

    def _load_data(self) -> None:
        if self.is_new:
            return
        self.item_code_input.setText(str(self.capacity_item.get("item_code") or ""))
        self.item_code_input.setReadOnly(True)
        self.running_moulds_input.setValue(float(self.capacity_item.get("running_moulds") or 0.0))
        self.per_mould_input.setValue(float(self.capacity_item.get("per_mould_capacity") or 0.0))
        self.daily_capacity_input.setValue(float(self.capacity_item.get("available_capacity_per_day") or 0.0))
        self.active_checkbox.setChecked(bool(self.capacity_item.get("is_active")))

    def get_data(self) -> dict:
        item_code = self.item_code_input.text().strip()
        if not item_code:
            raise ValueError("Item Code / Size Group is required.")

        return {
            "id": self.capacity_item.get("id"),
            "item_code": item_code,
            "running_moulds": Decimal(str(self.running_moulds_input.value())),
            "per_mould_capacity": Decimal(str(self.per_mould_input.value())),
            "available_capacity_per_day": Decimal(str(self.daily_capacity_input.value())),
            "is_active": self.active_checkbox.isChecked(),
        }


class CapacityMasterPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.selected_capacity_id: int | None = None

        # Widgets
        self.total_moulds_value = QLabel("0")
        self.total_capacity_value = QLabel("0")
        self.capacity_warnings_value = QLabel("0")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search item code / size group...")
        self.search_input.textChanged.connect(self.refresh_table)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["All Status", "Active Only", "Inactive Only"])
        self.status_combo.currentTextChanged.connect(self.refresh_table)

        self.add_btn = QPushButton("+ Add Capacity Link")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.clicked.connect(self.add_capacity)

        self.edit_btn = QPushButton("Edit Selected")
        self.edit_btn.setObjectName("SecondaryButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.edit_selected_capacity)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Item Code / Size Group", "Running Moulds", "Per Mould Rate", "Daily Capacity", "Status"]
        )

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
        metrics_layout.addWidget(self._metric_card("Total Running Moulds", self.total_moulds_value), 1)
        metrics_layout.addWidget(self._metric_card("Total Daily Capacity (units)", self.total_capacity_value), 1)
        metrics_layout.addWidget(self._metric_card("Mould Capacity Warnings", self.capacity_warnings_value), 1)
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
        title = QLabel("Capacity Master Control")
        title.setObjectName("SectionTitle")
        hint = QLabel("Define daily mould/category production capacities. Active items with zero capacity will raise warnings.")
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

        table_title = QLabel("Capacity Specifications")
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
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 140)
        self.table.setColumnWidth(4, 150)
        self.table.setColumnWidth(5, 100)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemDoubleClicked.connect(self.edit_selected_capacity)

    def refresh(self) -> None:
        try:
            self.refresh_metrics()
            self.refresh_table()
        except Exception as exc:
            QMessageBox.critical(self, "Capacity Master Error", f"Failed to refresh: {exc}")

    def refresh_metrics(self) -> None:
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        COALESCE(SUM(running_moulds), 0) AS total_moulds,
                        COALESCE(SUM(available_capacity_per_day), 0) AS total_capacity,
                        SUM(CASE WHEN is_active = TRUE AND COALESCE(available_capacity_per_day, 0) = 0 THEN 1 ELSE 0 END) AS capacity_warnings
                    FROM mpps_capacity_master;
                    """
                )
            ).mappings().one()

        self.total_moulds_value.setText(f"{row['total_moulds']:.2f}")
        self.total_capacity_value.setText(f"{row['total_capacity']:.2f}")
        self.capacity_warnings_value.setText(str(row["capacity_warnings"] or 0))

    def refresh_table(self) -> None:
        self.selected_capacity_id = None
        self.edit_btn.setEnabled(False)

        search_text = self.search_input.text().strip()
        status_value = self.status_combo.currentText()

        conditions = []
        params = {"search": f"%{search_text}%"}

        if search_text:
            conditions.append("item_code ILIKE :search")

        if status_value == "Active Only":
            conditions.append("is_active = TRUE")
        elif status_value == "Inactive Only":
            conditions.append("is_active = FALSE")

        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

        sql = f"""
            SELECT id, item_code, running_moulds, per_mould_capacity, available_capacity_per_day, is_active
            FROM mpps_capacity_master
            {where_sql}
            ORDER BY item_code ASC;
        """

        with engine.begin() as connection:
            rows = connection.execute(text(sql), params).mappings().all()

        self.table.setRowCount(0)
        for idx, row in enumerate(rows):
            self.table.insertRow(idx)

            items = [
                str(row["id"]),
                row["item_code"],
                f"{row['running_moulds']:.2f}",
                f"{row['per_mould_capacity']:.2f}",
                f"{row['available_capacity_per_day']:.2f}",
                "Active" if row["is_active"] else "Inactive"
            ]

            for col_idx, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx in (0, 2, 3, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col_idx == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                
                # Capacity warning style (active with 0 capacity)
                if col_idx == 4 and row["is_active"] and float(row["available_capacity_per_day"] or 0.0) == 0.0:
                    item.setForeground(Qt.GlobalColor.red)
                    item.setToolTip("Active capacity mapping is set to zero capacity!")

                self.table.setItem(idx, col_idx, item)

        self.table.resizeRowsToContents()

    def on_selection_changed(self) -> None:
        ranges = self.table.selectedRanges()
        if not ranges:
            self.selected_capacity_id = None
            self.edit_btn.setEnabled(False)
            return
        row = ranges[0].topRow()
        item = self.table.item(row, 0)
        if item is not None:
            self.selected_capacity_id = item.data(Qt.ItemDataRole.UserRole)
            self.edit_btn.setEnabled(True)

    def add_capacity(self) -> None:
        dialog = CapacityEditDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            data = dialog.get_data()
            username = self.current_user.username if self.current_user else "anonymous"

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_capacity_master (
                            item_code, running_moulds, per_mould_capacity, available_capacity_per_day, is_active
                        )
                        VALUES (
                            :item_code, :running_moulds, :per_mould_capacity, :available_capacity_per_day, :is_active
                        );
                        """
                    ),
                    data
                )

                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_audit_logs (username, action_type, table_name, record_id, new_values, note)
                        VALUES (:username, 'INSERT', 'mpps_capacity_master', :record, :val, 'Added new mould capacity definition.');
                        """
                    ),
                    {"username": username, "record": data["item_code"], "val": str(data)}
                )

            QMessageBox.information(self, "Success", "Capacity mapping added successfully.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error Saving Capacity", f"Failed to save record: {exc}")

    def edit_selected_capacity(self) -> None:
        if not self.selected_capacity_id:
            return

        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT * FROM mpps_capacity_master WHERE id = :id;"),
                {"id": self.selected_capacity_id}
            ).mappings().first()

        if not row:
            QMessageBox.warning(self, "Edit Capacity", "Record no longer exists.")
            return

        dialog = CapacityEditDialog(self, dict(row))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            data = dialog.get_data()
            username = self.current_user.username if self.current_user else "anonymous"

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE mpps_capacity_master
                        SET running_moulds = :running_moulds,
                            per_mould_capacity = :per_mould_capacity,
                            available_capacity_per_day = :available_capacity_per_day,
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
                        VALUES (:username, 'UPDATE', 'mpps_capacity_master', :record, :old, :new, 'Updated mould capacity definition.');
                        """
                    ),
                    {
                        "username": username,
                        "record": data["item_code"],
                        "old": str(dict(row)),
                        "new": str(data)
                    }
                )

            QMessageBox.information(self, "Success", "Capacity mapping updated successfully.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error Saving Capacity", f"Failed to save record: {exc}")
