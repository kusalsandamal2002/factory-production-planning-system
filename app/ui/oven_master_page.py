from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
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


class OvenEditDialog(QDialog):
    def __init__(self, parent=None, oven_item: dict | None = None):
        super().__init__(parent)
        self.oven_item = oven_item or {}
        self.is_new = oven_item is None

        self.setWindowTitle("Add Oven Machine" if self.is_new else "Edit Oven Machine")
        self.setMinimumWidth(500)

        self.oven_code_input = QLineEdit()
        self.oven_code_input.setPlaceholderText("Oven unique identifier (e.g., OVEN-01)...")
        self.oven_name_input = QLineEdit()
        self.oven_name_input.setPlaceholderText("Human readable description/name...")

        self.active_checkbox = QCheckBox("Active Oven Status")
        self.active_checkbox.setChecked(True)

        self.save_btn = QPushButton("Save Oven")
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

        title = QLabel("Oven Master Record")
        title.setObjectName("Title")
        hint = QLabel("Register and maintain the production ovens available in the curing schedule scheduler.")
        hint.setObjectName("Hint")
        layout.addWidget(title)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        form.addWidget(QLabel("Oven Code"), 0, 0)
        form.addWidget(self.oven_code_input, 0, 1)
        form.addWidget(QLabel("Oven Name"), 1, 0)
        form.addWidget(self.oven_name_input, 1, 1)

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
        self.oven_code_input.setText(str(self.oven_item.get("oven_code") or ""))
        self.oven_code_input.setReadOnly(True)
        self.oven_name_input.setText(str(self.oven_item.get("oven_name") or ""))
        self.active_checkbox.setChecked(bool(self.oven_item.get("is_active")))

    def get_data(self) -> dict:
        oven_code = self.oven_code_input.text().strip()
        oven_name = self.oven_name_input.text().strip()

        if not oven_code:
            raise ValueError("Oven Code is required.")
        if not oven_name:
            raise ValueError("Oven Name is required.")

        return {
            "id": self.oven_item.get("id"),
            "oven_code": oven_code,
            "oven_name": oven_name,
            "is_active": self.active_checkbox.isChecked(),
        }


class OvenMasterPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.selected_oven_id: int | None = None

        # Widgets
        self.total_ovens_value = QLabel("0")
        self.active_ovens_value = QLabel("0")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search oven code or name...")
        self.search_input.textChanged.connect(self.refresh_table)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["All Status", "Active Only", "Inactive Only"])
        self.status_combo.currentTextChanged.connect(self.refresh_table)

        self.add_btn = QPushButton("+ Add Oven Machine")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.clicked.connect(self.add_oven)

        self.edit_btn = QPushButton("Edit Selected")
        self.edit_btn.setObjectName("SecondaryButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.edit_selected_oven)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["ID", "Oven Code", "Oven Name", "Status"])

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
        metrics_layout.addWidget(self._metric_card("Total Ovens", self.total_ovens_value), 1)
        metrics_layout.addWidget(self._metric_card("Active Ovens", self.active_ovens_value), 1)
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
        title = QLabel("Oven Master Control")
        title.setObjectName("SectionTitle")
        hint = QLabel("Register curing ovens. Schedulers use these oven resources for auto oven allocation planning.")
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

        table_title = QLabel("Oven Machines")
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
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 80)
        self.table.setColumnWidth(1, 160)
        self.table.setColumnWidth(3, 120)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemDoubleClicked.connect(self.edit_selected_oven)

    def refresh(self) -> None:
        try:
            self.refresh_metrics()
            self.refresh_table()
        except Exception as exc:
            QMessageBox.critical(self, "Oven Master Error", f"Failed to refresh: {exc}")

    def refresh_metrics(self) -> None:
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS total_ovens,
                        SUM(CASE WHEN is_active = TRUE THEN 1 ELSE 0 END) AS active_ovens
                    FROM ovens;
                    """
                )
            ).mappings().one()

        self.total_ovens_value.setText(str(row["total_ovens"] or 0))
        self.active_ovens_value.setText(str(row["active_ovens"] or 0))

    def refresh_table(self) -> None:
        self.selected_oven_id = None
        self.edit_btn.setEnabled(False)

        search_text = self.search_input.text().strip()
        status_value = self.status_combo.currentText()

        conditions = []
        params = {"search": f"%{search_text}%"}

        if search_text:
            conditions.append("(oven_code ILIKE :search OR oven_name ILIKE :search)")

        if status_value == "Active Only":
            conditions.append("is_active = TRUE")
        elif status_value == "Inactive Only":
            conditions.append("is_active = FALSE")

        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

        sql = f"""
            SELECT id, oven_code, oven_name, is_active
            FROM ovens
            {where_sql}
            ORDER BY oven_code ASC;
        """

        with engine.begin() as connection:
            rows = connection.execute(text(sql), params).mappings().all()

        self.table.setRowCount(0)
        for idx, row in enumerate(rows):
            self.table.insertRow(idx)

            items = [
                str(row["id"]),
                row["oven_code"],
                row["oven_name"],
                "Active" if row["is_active"] else "Inactive"
            ]

            for col_idx, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx in (0, 1, 3):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if col_idx == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                self.table.setItem(idx, col_idx, item)

        self.table.resizeRowsToContents()

    def on_selection_changed(self) -> None:
        ranges = self.table.selectedRanges()
        if not ranges:
            self.selected_oven_id = None
            self.edit_btn.setEnabled(False)
            return
        row = ranges[0].topRow()
        item = self.table.item(row, 0)
        if item is not None:
            self.selected_oven_id = item.data(Qt.ItemDataRole.UserRole)
            self.edit_btn.setEnabled(True)

    def add_oven(self) -> None:
        dialog = OvenEditDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            data = dialog.get_data()
            username = self.current_user.username if self.current_user else "anonymous"

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO ovens (oven_code, oven_name, is_active)
                        VALUES (:oven_code, :oven_name, :is_active);
                        """
                    ),
                    data
                )

                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_audit_logs (username, action_type, table_name, record_id, new_values, note)
                        VALUES (:username, 'INSERT', 'ovens', :record, :val, 'Added new oven machine.');
                        """
                    ),
                    {"username": username, "record": data["oven_code"], "val": str(data)}
                )

            QMessageBox.information(self, "Success", "Oven machine added successfully.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error Saving Oven", f"Failed to save record: {exc}")

    def edit_selected_oven(self) -> None:
        if not self.selected_oven_id:
            return

        with engine.begin() as connection:
            row = connection.execute(
                text("SELECT * FROM ovens WHERE id = :id;"),
                {"id": self.selected_oven_id}
            ).mappings().first()

        if not row:
            QMessageBox.warning(self, "Edit Oven", "Record no longer exists.")
            return

        dialog = OvenEditDialog(self, dict(row))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            data = dialog.get_data()
            username = self.current_user.username if self.current_user else "anonymous"

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE ovens
                        SET oven_name = :oven_name,
                            is_active = :is_active
                        WHERE id = :id;
                        """
                    ),
                    data
                )

                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_audit_logs (username, action_type, table_name, record_id, old_values, new_values, note)
                        VALUES (:username, 'UPDATE', 'ovens', :record, :old, :new, 'Updated oven machine config.');
                        """
                    ),
                    {
                        "username": username,
                        "record": data["oven_code"],
                        "old": str(dict(row)),
                        "new": str(data)
                    }
                )

            QMessageBox.information(self, "Success", "Oven updated successfully.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error Saving Oven", f"Failed to save record: {exc}")
