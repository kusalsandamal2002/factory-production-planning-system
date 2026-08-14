from __future__ import annotations

from uuid import uuid4

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
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


class ProductionLineRepository:
    def ensure_table(self) -> None:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS production_lines (
                    id VARCHAR(64) PRIMARY KEY,
                    line_name VARCHAR(255) NOT NULL UNIQUE,
                    status VARCHAR(32) NOT NULL DEFAULT 'Active',
                    remarks TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

    def list_rows(self) -> list[dict]:
        self.ensure_table()

        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT id, line_name, status, remarks
                FROM production_lines
                ORDER BY line_name
            """)).mappings().all()

        return [dict(row) for row in rows]

    def create(self, data: dict) -> None:
        self.ensure_table()

        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO production_lines (id, line_name, status, remarks)
                    VALUES (:id, :line_name, :status, :remarks)
                """),
                {
                    "id": str(uuid4()),
                    "line_name": data["line_name"],
                    "status": data["status"],
                    "remarks": data["remarks"],
                },
            )

    def update(self, item_id: str, data: dict) -> None:
        self.ensure_table()

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE production_lines
                    SET line_name = :line_name,
                        status = :status,
                        remarks = :remarks,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {
                    "id": item_id,
                    "line_name": data["line_name"],
                    "status": data["status"],
                    "remarks": data["remarks"],
                },
            )

    def update_status(self, item_id: str, status: str) -> None:
        self.ensure_table()

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE production_lines
                    SET status = :status,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {"id": item_id, "status": status},
            )

    def delete(self, item_id: str) -> None:
        """Non-destructive V11 lifecycle action: retire instead of delete."""
        self.ensure_table()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE production_lines
                    SET status='Retired',
                        remarks=CASE
                            WHEN TRIM(COALESCE(remarks,''))=''
                            THEN 'Retired from technical register; historical ML evidence retained.'
                            ELSE remarks END,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=:id
                    """
                ),
                {"id": item_id},
            )


class ProductionLineDialog(QDialog):
    def __init__(self, parent=None, data: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Production Line")
        self.setMinimumWidth(560)

        self.setStyleSheet("""
            QDialog {
                background: #f8fafc;
            }

            QLabel {
                color: #0f172a;
                font-size: 9.5pt;
                font-weight: 850;
            }

            QLineEdit, QComboBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 10px 12px;
                color: #0f172a;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #2563eb;
            }

            QPushButton {
                border-radius: 10px;
                padding: 8px 14px;
                font-weight: 900;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(14)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(14)

        self.line_name_input = QLineEdit()
        self.line_name_input.setPlaceholderText("Example: 200T Line")

        self.status_input = QComboBox()
        self.status_input.addItems(["Active", "Inactive"])

        self.remarks_input = QLineEdit()
        self.remarks_input.setPlaceholderText("Optional remarks")

        form.addWidget(QLabel("Line Name"), 0, 0)
        form.addWidget(self.line_name_input, 0, 1)

        form.addWidget(QLabel("Current Status"), 1, 0)
        form.addWidget(self.status_input, 1, 1)

        form.addWidget(QLabel("Remarks"), 2, 0)
        form.addWidget(self.remarks_input, 2, 1)

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        if data:
            self.line_name_input.setText(data.get("line_name", ""))
            self.status_input.setCurrentText(data.get("status", "Active"))
            self.remarks_input.setText(data.get("remarks", ""))

    def _validate_and_accept(self) -> None:
        if not self.line_name_input.text().strip():
            QMessageBox.warning(self, "Required", "Production line name is required.")
            return

        self.accept()

    def data(self) -> dict:
        return {
            "line_name": self.line_name_input.text().strip(),
            "status": self.status_input.currentText(),
            "remarks": self.remarks_input.text().strip(),
        }


class ProductionLineMasterPage(QWidget):
    def __init__(self):
        super().__init__()
        self.repo = ProductionLineRepository()
        self.rows: list[dict] = []
        self.metric_labels: dict[str, QLabel] = {}

        self.setStyleSheet("""
            QFrame#HeaderCard, QFrame#TableCard, QFrame#MetricCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 18px;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 24pt;
                font-weight: 950;
            }

            QLabel#PageSubtitle, QLabel#HintText {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 15pt;
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

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 11px;
                padding: 11px 18px;
                font-size: 9pt;
                font-weight: 950;
            }

            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }

            QPushButton#EditButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 8.5pt;
                font-weight: 900;
                min-width: 76px;
            }

            QPushButton#EditButton:hover {
                background: #cbd5e1;
            }

            QPushButton#DeleteButton {
                background: #fee2e2;
                color: #991b1b;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 8.5pt;
                font-weight: 900;
                min-width: 76px;
            }

            QPushButton#DeleteButton:hover {
                background: #fecaca;
            }

            QComboBox#StatusCombo {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 7px 10px;
                font-size: 8.5pt;
                font-weight: 900;
                min-width: 135px;
            }

            QComboBox#StatusCombo:focus {
                border: 1px solid #2563eb;
            }

            QTableWidget {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
                gridline-color: #e2e8f0;
                color: #0f172a;
                font-size: 9.5pt;
                font-weight: 700;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }

            QTableWidget::item {
                padding: 12px;
            }

            QHeaderView::section {
                background: #f8fafc;
                color: #334155;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 13px;
                font-size: 9pt;
                font-weight: 950;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self._build_header())
        root.addLayout(self._build_metrics())
        root.addWidget(self._build_table_card(), 1)

        self.refresh()

    def _build_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        title = QLabel("Production Line Master")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Maintain production line names and current operating status. Capacity, mold, casing and time settings are handled in separate Factory Capacity modules."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        add_button = QPushButton("+ Add Production Line")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self._add_line)

        layout.addLayout(text_area, 1)
        layout.addWidget(add_button)

        return card

    def _build_metrics(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(12)

        for col, key in enumerate(["total", "active", "inactive"]):
            grid.addWidget(self._metric_card(key), 0, col)
            grid.setColumnStretch(col, 1)

        return grid

    def _metric_card(self, key: str) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(4)

        value_label = QLabel("0")
        value_label.setObjectName("MetricValue")
        self.metric_labels[key] = value_label

        if key == "total":
            label, hint = "Total Lines", "Production lines registered"
        elif key == "active":
            label, hint = "Active Lines", "Available for planning"
        elif key == "inactive":
            label, hint = "Inactive Lines", "Not used for new planning"
        else:
            label, hint = "Module Scope", "Line identity and operating status only"
            value_label.setText("Clean")

        label_widget = QLabel(label)
        label_widget.setObjectName("MetricLabel")

        hint_widget = QLabel(hint)
        hint_widget.setObjectName("HintText")
        hint_widget.setWordWrap(True)

        layout.addWidget(value_label)
        layout.addWidget(label_widget)
        layout.addWidget(hint_widget)

        return card

    def _build_table_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title_row = QHBoxLayout()

        title_area = QVBoxLayout()
        title_area.setSpacing(5)

        title = QLabel("Production Lines")
        title.setObjectName("SectionTitle")

        hint = QLabel(
            "Change current status directly from the table. Capacity, mold, casing and time details are managed in their own modules."
        )
        hint.setObjectName("HintText")
        hint.setWordWrap(True)

        title_area.addWidget(title)
        title_area.addWidget(hint)

        title_row.addLayout(title_area, 1)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([
            "Line Name",
            "Current Status",
            "Remarks",
            "Actions",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setColumnWidth(3, 190)

        layout.addLayout(title_row)
        layout.addWidget(self.table, 1)

        return card

    def refresh(self) -> None:
        try:
            self.rows = self.repo.list_rows()
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Database Error",
                f"Could not load production lines from PostgreSQL.\n\n{exc}",
            )
            self.rows = []

        self._refresh_metrics()
        self._refresh_table()

    refresh_page = refresh
    load_data = refresh

    def _refresh_metrics(self) -> None:
        active_count = sum(1 for row in self.rows if row.get("status") == "Active")
        inactive_count = sum(1 for row in self.rows if row.get("status") == "Inactive")

        self.metric_labels["total"].setText(str(len(self.rows)))
        self.metric_labels["active"].setText(str(active_count))
        self.metric_labels["inactive"].setText(str(inactive_count))

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.rows))

        for row_index, row in enumerate(self.rows):
            self.table.setRowHeight(row_index, 58)

            name_item = QTableWidgetItem(row.get("line_name", ""))
            name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, 0, name_item)

            status_combo = QComboBox()
            status_combo.setObjectName("StatusCombo")
            status_combo.addItems(["Active", "Inactive"])
            status_combo.setCurrentText(row.get("status", "Active"))
            status_combo.currentTextChanged.connect(
                lambda status, item_id=row["id"]: self._change_status(item_id, status)
            )
            self.table.setCellWidget(row_index, 1, status_combo)

            remarks_item = QTableWidgetItem(row.get("remarks", ""))
            remarks_item.setFlags(remarks_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, 2, remarks_item)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 4, 4, 4)
            action_layout.setSpacing(8)

            edit_button = QPushButton("Edit")
            edit_button.setObjectName("EditButton")
            edit_button.clicked.connect(lambda checked=False, item_id=row["id"]: self._edit_line(item_id))

            delete_button = QPushButton("Retire")
            delete_button.setObjectName("DeleteButton")
            delete_button.clicked.connect(lambda checked=False, item_id=row["id"]: self._delete_line(item_id))

            action_layout.addWidget(edit_button)
            action_layout.addWidget(delete_button)

            self.table.setCellWidget(row_index, 3, action_widget)

    def _add_line(self) -> None:
        dialog = ProductionLineDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self.repo.create(dialog.data())
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Failed",
                f"Could not save production line.\n\nPossible duplicate line name or database issue.\n\n{exc}",
            )
            return

        self.refresh()

    def _edit_line(self, item_id: str) -> None:
        row = self._find_row(item_id)
        if row is None:
            return

        dialog = ProductionLineDialog(self, row)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            self.repo.update(item_id, dialog.data())
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Update Failed",
                f"Could not update production line.\n\nPossible duplicate line name or database issue.\n\n{exc}",
            )
            return

        self.refresh()

    def _change_status(self, item_id: str, status: str) -> None:
        row = self._find_row(item_id)

        if row is not None and row.get("status") == status:
            return

        try:
            self.repo.update_status(item_id, status)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Status Update Failed",
                f"Could not change production line status.\n\n{exc}",
            )
            return

        self.refresh()

    def _delete_line(self, item_id: str) -> None:
        row = self._find_row(item_id)
        if row is None:
            return

        answer = QMessageBox.question(
            self,
            "Retire Production Line",
            f"Retire production line '{row.get('line_name', '')}'? Historical evidence will be retained.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.repo.delete(item_id)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Retire Failed",
                f"Could not delete production line.\n\n{exc}",
            )
            return

        self.refresh()

    def _find_row(self, item_id: str) -> dict | None:
        for row in self.rows:
            if row.get("id") == item_id:
                return row
        return None


OvenMasterPage = ProductionLineMasterPage
ProductionLinesPage = ProductionLineMasterPage
