from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.database import engine


class MoldRepository:
    def __init__(self) -> None:
        self.ensure_table()

    def ensure_table(self) -> None:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS mold_master (
                    id BIGSERIAL PRIMARY KEY,
                    mold_key_code VARCHAR(255) NOT NULL UNIQUE,
                    mold_count INTEGER NOT NULL DEFAULT 0,
                    casing_type VARCHAR(255) NOT NULL DEFAULT '',
                    casing_count INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(32) NOT NULL DEFAULT 'Active',
                    remarks TEXT NOT NULL DEFAULT '',
                    source_file VARCHAR(255) NOT NULL DEFAULT '',
                    source_sheet VARCHAR(255) NOT NULL DEFAULT '',
                    source_rows TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

    def stats(self) -> dict:
        with engine.connect() as conn:
            return dict(conn.execute(text("""
                SELECT
                    COUNT(*) AS total_keys,
                    COALESCE(SUM(mold_count), 0) AS total_molds,
                    COALESCE(SUM(casing_count), 0) AS total_casings,
                    COUNT(*) FILTER (WHERE status = 'Active') AS active_keys,
                    COUNT(*) FILTER (WHERE casing_type = 'No Casing') AS no_casing_keys
                FROM mold_master
            """)).mappings().one())

    def list_molds(self, search_text: str = "") -> list[dict]:
        search = (search_text or "").strip().lower()

        sql = """
            SELECT
                id,
                mold_key_code,
                mold_count,
                casing_type,
                casing_count,
                status,
                remarks,
                source_file,
                source_sheet,
                source_rows
            FROM mold_master
        """

        params = {}

        if search:
            sql += """
                WHERE LOWER(mold_key_code) LIKE :search
                   OR LOWER(casing_type) LIKE :search
                   OR LOWER(status) LIKE :search
                   OR LOWER(source_file) LIKE :search
            """
            params["search"] = f"%{search}%"

        sql += """
            ORDER BY
                CASE WHEN status = 'Active' THEN 0 ELSE 1 END,
                casing_type,
                mold_key_code
        """

        with engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), params).mappings().all()]

    def get_mold(self, mold_id: int) -> dict:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT
                    id,
                    mold_key_code,
                    mold_count,
                    casing_type,
                    casing_count,
                    status,
                    remarks,
                    source_file,
                    source_sheet,
                    source_rows
                FROM mold_master
                WHERE id = :id
            """), {"id": mold_id}).mappings().one()
            return dict(row)

    def add_mold(self, data: dict) -> None:
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO mold_master (
                    mold_key_code,
                    mold_count,
                    casing_type,
                    casing_count,
                    status,
                    remarks,
                    source_file,
                    source_sheet,
                    source_rows,
                    updated_at
                )
                VALUES (
                    :mold_key_code,
                    :mold_count,
                    :casing_type,
                    :casing_count,
                    :status,
                    :remarks,
                    'Manual',
                    '',
                    '',
                    CURRENT_TIMESTAMP
                )
            """), data)

    def update_mold(self, mold_id: int, data: dict) -> None:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE mold_master
                SET mold_key_code = :mold_key_code,
                    mold_count = :mold_count,
                    casing_type = :casing_type,
                    casing_count = :casing_count,
                    status = :status,
                    remarks = :remarks,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": mold_id, **data})

    def update_status(self, mold_id: int, status: str) -> None:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE mold_master
                SET status = :status,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": mold_id, "status": status})

    def delete_mold(self, mold_id: int) -> None:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM mold_master WHERE id = :id"), {"id": mold_id})


class MoldDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, mold: dict | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)

        self.mold = mold or {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        self.key_input = QLineEdit(str(self.mold.get("mold_key_code", "")))
        self.key_input.setPlaceholderText("Example: 18X7-8 TR NM")

        self.mold_count_input = QSpinBox()
        self.mold_count_input.setRange(0, 100000)
        self.mold_count_input.setValue(int(self.mold.get("mold_count", 0) or 0))

        self.casing_type_input = QLineEdit(str(self.mold.get("casing_type", "")))
        self.casing_type_input.setPlaceholderText("Example: B2 / B5 / No Casing")


        self.status_input = QComboBox()
        self.status_input.addItems(["Active", "Inactive"])
        self.status_input.setCurrentText(str(self.mold.get("status", "Active") or "Active"))

        self.remarks_input = QTextEdit(str(self.mold.get("remarks", "") or ""))
        self.remarks_input.setFixedHeight(88)

        form.addRow("Mold Key Code", self.key_input)
        form.addRow("Mold Count", self.mold_count_input)
        form.addRow("Casing Type", self.casing_type_input)
        form.addRow("Status", self.status_input)
        form.addRow("Remarks", self.remarks_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

    def data(self) -> dict:
        casing_type = self.casing_type_input.text().strip() or "No Casing"

        return {
            "mold_key_code": self.key_input.text().strip(),
            "mold_count": int(self.mold_count_input.value()),
            "casing_type": casing_type,
            "casing_count": int(self.mold.get("casing_count", 0) or 0),
            "status": self.status_input.currentText(),
            "remarks": self.remarks_input.toPlainText().strip(),
        }


class MoldMasterPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.repo = MoldRepository()

        self.setStyleSheet("""
            QFrame#HeaderCard, QFrame#MetricCard, QFrame#TableCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 18px;
            }

            QLabel#Breadcrumb {
                color: #2563eb;
                font-size: 9pt;
                font-weight: 850;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 22pt;
                font-weight: 950;
            }

            QLabel#PageSubtitle, QLabel#MetricLabel {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLabel#MetricValue {
                color: #0f172a;
                font-size: 18pt;
                font-weight: 950;
            }

            QLineEdit {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 8px 10px;
                color: #0f172a;
                font-weight: 650;
            }

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 10px;
                padding: 9px 14px;
                font-weight: 850;
            }

            QPushButton#SecondaryButton {
                background: #f8fafc;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 8px 12px;
                font-weight: 800;
            }

            QPushButton#DangerButton {
                background: #fee2e2;
                color: #991b1b;
                border: 1px solid #fecaca;
                border-radius: 9px;
                padding: 7px 10px;
                font-weight: 850;
            }

            QTableWidget {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                gridline-color: #e2e8f0;
                color: #0f172a;
                font-size: 9.5pt;
            }

            QHeaderView::section {
                background: #f8fafc;
                color: #334155;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 9px;
                font-weight: 900;
            }

            QComboBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 5px 8px;
                font-weight: 750;
            }
        """)

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 22)
        root.setSpacing(16)

        root.addWidget(self._header())
        root.addLayout(self._metrics())
        root.addWidget(self._table_card(), 1)

    def _header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(7)

        breadcrumb = QLabel("Master Data  /  Factory Capacity  /  Mold Master")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Mold Master")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Maintain mold key codes, mold availability and casing compatibility from the master file."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search mold key, casing type, status...")
        self.search_input.setMinimumWidth(340)
        self.search_input.textChanged.connect(self.refresh)

        add_button = QPushButton("+ Add Mold")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self.add_mold)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("SecondaryButton")
        refresh_button.clicked.connect(self.refresh)

        layout.addLayout(text_area, 1)
        layout.addWidget(self.search_input)
        layout.addWidget(refresh_button)
        layout.addWidget(add_button)

        return card

    def _metrics(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)

        self.total_keys_value = self._metric_card(layout, "Mold Keys")
        self.total_molds_value = self._metric_card(layout, "Total Molds")
        self.active_keys_value = self._metric_card(layout, "Active Keys")

        return layout

    def _metric_card(self, parent_layout: QHBoxLayout, label_text: str) -> QLabel:
        card = QFrame()
        card.setObjectName("MetricCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(5)

        value = QLabel("0")
        value.setObjectName("MetricValue")

        label = QLabel(label_text)
        label.setObjectName("MetricLabel")

        layout.addWidget(value)
        layout.addWidget(label)

        parent_layout.addWidget(card)
        return value

    def _table_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Mold Key Code",
            "Mold Count",
            "Casing Type",
            "Status",
            "Action",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(1, 110)
        self.table.setColumnWidth(2, 170)
        self.table.setColumnWidth(3, 120)
        self.table.setColumnWidth(4, 180)

        layout.addWidget(self.table, 1)
        return card

    def refresh(self) -> None:
        try:
            stats = self.repo.stats()
            rows = self.repo.list_molds(self.search_input.text() if hasattr(self, "search_input") else "")
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not load mold master. " + str(exc))
            return

        self.total_keys_value.setText(str(stats.get("total_keys", 0)))
        self.total_molds_value.setText(str(stats.get("total_molds", 0)))
        self.active_keys_value.setText(str(stats.get("active_keys", 0)))

        self.table.setRowCount(len(rows))

        for row_index, mold in enumerate(rows):
            self.table.setRowHeight(row_index, 54)

            self._set_item(row_index, 0, mold.get("mold_key_code", ""))
            self._set_item(row_index, 1, mold.get("mold_count", 0), center=True)
            self._set_item(row_index, 2, mold.get("casing_type", ""))

            status_combo = QComboBox()
            status_combo.addItems(["Active", "Inactive"])
            status_combo.blockSignals(True)
            status_combo.setCurrentText(str(mold.get("status", "Active") or "Active"))
            status_combo.blockSignals(False)
            status_combo.currentTextChanged.connect(
                lambda status, mold_id=mold["id"]: self.update_status(mold_id, status)
            )
            self.table.setCellWidget(row_index, 3, status_combo)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 4, 4, 4)
            action_layout.setSpacing(6)

            edit_button = QPushButton("Edit")
            edit_button.setObjectName("SecondaryButton")
            edit_button.clicked.connect(lambda checked=False, mold_id=mold["id"]: self.edit_mold(mold_id))

            delete_button = QPushButton("Delete")
            delete_button.setObjectName("DangerButton")
            delete_button.clicked.connect(lambda checked=False, mold_id=mold["id"]: self.delete_mold(mold_id))

            action_layout.addWidget(edit_button)
            action_layout.addWidget(delete_button)

            self.table.setCellWidget(row_index, 4, action_widget)

    def _set_item(self, row: int, col: int, value, center: bool = False) -> None:
        item = QTableWidgetItem(str(value if value is not None else ""))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        if center:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.table.setItem(row, col, item)

    def add_mold(self) -> None:
        dialog = MoldDialog(self, "Add Mold")

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()

        if not data["mold_key_code"]:
            QMessageBox.warning(self, "Validation", "Mold Key Code is required.")
            return

        try:
            self.repo.add_mold(data)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not add mold. " + str(exc))

    def edit_mold(self, mold_id: int) -> None:
        try:
            mold = self.repo.get_mold(mold_id)
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not load selected mold. " + str(exc))
            return

        dialog = MoldDialog(self, "Edit Mold", mold)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()

        if not data["mold_key_code"]:
            QMessageBox.warning(self, "Validation", "Mold Key Code is required.")
            return

        try:
            self.repo.update_mold(mold_id, data)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not update mold. " + str(exc))

    def update_status(self, mold_id: int, status: str) -> None:
        try:
            self.repo.update_status(mold_id, status)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not update status. " + str(exc))

    def delete_mold(self, mold_id: int) -> None:
        answer = QMessageBox.question(
            self,
            "Delete Mold",
            "Delete this mold key from Mold Master?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        try:
            self.repo.delete_mold(mold_id)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not delete mold. " + str(exc))
