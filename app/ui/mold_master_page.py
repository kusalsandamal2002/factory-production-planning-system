from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
                    production_mold_count INTEGER NOT NULL DEFAULT 0,
                    breakdown_mold_count INTEGER NOT NULL DEFAULT 0,
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

            for sql in [
                "ALTER TABLE mold_master ADD COLUMN IF NOT EXISTS production_mold_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mold_master ADD COLUMN IF NOT EXISTS breakdown_mold_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mold_master ADD COLUMN IF NOT EXISTS casing_type VARCHAR(255) NOT NULL DEFAULT ''",
                "ALTER TABLE mold_master ADD COLUMN IF NOT EXISTS casing_count INTEGER NOT NULL DEFAULT 0",
                "ALTER TABLE mold_master ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'Active'",
                "ALTER TABLE mold_master ADD COLUMN IF NOT EXISTS remarks TEXT NOT NULL DEFAULT ''",
                "ALTER TABLE mold_master ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP",
            ]:
                conn.execute(text(sql))

            conn.execute(text("""
                UPDATE mold_master
                SET production_mold_count = COALESCE(production_mold_count, 0),
                    breakdown_mold_count = COALESCE(breakdown_mold_count, 0),
                    mold_count = COALESCE(mold_count, 0),
                    status = COALESCE(NULLIF(status, ''), 'Active')
            """))

    def stats(self) -> dict:
        with engine.connect() as conn:
            return dict(conn.execute(text("""
                SELECT
                    COUNT(*) AS total_keys,
                    COALESCE(SUM(mold_count), 0) AS total_molds,
                    COALESCE(SUM(production_mold_count), 0) AS production_molds,
                    COALESCE(SUM(breakdown_mold_count), 0) AS breakdown_molds,
                    COALESCE(SUM(GREATEST(
                        COALESCE(mold_count, 0)
                        - COALESCE(production_mold_count, 0)
                        - COALESCE(breakdown_mold_count, 0),
                        0
                    )), 0) AS available_molds
                FROM mold_master
            """)).mappings().one())

    def list_molds(self, search_text: str = "") -> list[dict]:
        search = (search_text or "").strip().lower()

        sql = """
            SELECT
                id,
                mold_key_code,
                mold_count,
                production_mold_count,
                breakdown_mold_count,
                GREATEST(
                    COALESCE(mold_count, 0)
                    - COALESCE(production_mold_count, 0)
                    - COALESCE(breakdown_mold_count, 0),
                    0
                ) AS available_mold_count,
                remarks,
                status
            FROM mold_master
        """

        params = {}
        if search:
            sql += " WHERE LOWER(mold_key_code) LIKE :search "
            params["search"] = f"%{search}%"

        sql += " ORDER BY mold_key_code ASC "

        with engine.connect() as conn:
            return [dict(row) for row in conn.execute(text(sql), params).mappings().all()]

    def get_mold(self, mold_id: int) -> dict:
        with engine.connect() as conn:
            row = conn.execute(text("""
                SELECT
                    id,
                    mold_key_code,
                    mold_count,
                    production_mold_count,
                    breakdown_mold_count,
                    GREATEST(
                        COALESCE(mold_count, 0)
                        - COALESCE(production_mold_count, 0)
                        - COALESCE(breakdown_mold_count, 0),
                        0
                    ) AS available_mold_count,
                    remarks,
                    status
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
                    production_mold_count,
                    breakdown_mold_count,
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
                    :production_mold_count,
                    :breakdown_mold_count,
                    'Active',
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
                    production_mold_count = :production_mold_count,
                    breakdown_mold_count = :breakdown_mold_count,
                    status = 'Active',
                    remarks = :remarks,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :id
            """), {"id": mold_id, **data})


class MoldDialog(QDialog):
    def __init__(self, parent: QWidget, title: str, mold: dict | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)

        self.mold = mold or {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(12)

        self.key_input = QLineEdit(str(self.mold.get("mold_key_code", "")))
        self.key_input.setPlaceholderText("Example: 140/55-9 TR")

        self.total_input = QSpinBox()
        self.total_input.setRange(0, 100000)
        self.total_input.setValue(int(self.mold.get("mold_count", 0) or 0))

        self.add_qty_input = QSpinBox()
        self.add_qty_input.setRange(0, 100000)
        self.add_qty_input.setValue(0)

        self.production_input = QSpinBox()
        self.production_input.setRange(0, 100000)
        self.production_input.setValue(int(self.mold.get("production_mold_count", 0) or 0))

        self.breakdown_input = QSpinBox()
        self.breakdown_input.setRange(0, 100000)
        self.breakdown_input.setValue(int(self.mold.get("breakdown_mold_count", 0) or 0))

        self.available_label = QLabel()
        self.available_label.setStyleSheet("font-weight:900; color:#047857;")

        self.remarks_input = QTextEdit(str(self.mold.get("remarks", "") or ""))
        self.remarks_input.setFixedHeight(88)

        for widget in [
            self.total_input,
            self.add_qty_input,
            self.production_input,
            self.breakdown_input,
        ]:
            widget.valueChanged.connect(self.update_available_preview)

        form.addRow("Mold Key Code", self.key_input)
        form.addRow("Current / Total Mold Count", self.total_input)
        form.addRow("Add New Mold Quantity", self.add_qty_input)
        form.addRow("Production Mold Count", self.production_input)
        form.addRow("Breakdown Mold Count", self.breakdown_input)
        form.addRow("Available Mold Count", self.available_label)
        form.addRow("Remarks", self.remarks_input)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout.addLayout(form)
        layout.addWidget(buttons)

        self.update_available_preview()

    def update_available_preview(self) -> None:
        total = self.total_input.value() + self.add_qty_input.value()
        production = self.production_input.value()
        breakdown = self.breakdown_input.value()
        available = max(0, total - production - breakdown)
        self.available_label.setText(str(available))

    def data(self) -> dict:
        total = int(self.total_input.value()) + int(self.add_qty_input.value())
        return {
            "mold_key_code": self.key_input.text().strip(),
            "mold_count": total,
            "production_mold_count": int(self.production_input.value()),
            "breakdown_mold_count": int(self.breakdown_input.value()),
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
            "Maintain total, production, breakdown and available mold counts."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search mold key code...")
        self.search_input.setMinimumWidth(340)
        self.search_input.textChanged.connect(self.refresh)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("SecondaryButton")
        refresh_button.clicked.connect(self.refresh)

        add_button = QPushButton("+ Add Mold")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self.add_mold)

        layout.addLayout(text_area, 1)
        layout.addWidget(self.search_input)
        layout.addWidget(refresh_button)
        layout.addWidget(add_button)

        return card

    def _metrics(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)

        self.total_keys_value = self._metric_card(layout, "Mold Key Codes")
        self.total_molds_value = self._metric_card(layout, "Total Molds")
        self.production_molds_value = self._metric_card(layout, "Production Molds")
        self.breakdown_molds_value = self._metric_card(layout, "Breakdown Molds")
        self.available_molds_value = self._metric_card(layout, "Available Molds")

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

        self.loaded_rows_label = QLabel("Loaded Mold Key Codes: 0")
        self.loaded_rows_label.setObjectName("PageSubtitle")
        layout.addWidget(self.loaded_rows_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Mold Key Code",
            "Total Mold",
            "Production Mold",
            "Breakdown Mold",
            "Available Mold",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(lambda row, col: self.edit_mold_for_row(row))

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, 5):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 145)
        self.table.setColumnWidth(3, 145)
        self.table.setColumnWidth(4, 145)

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
        self.production_molds_value.setText(str(stats.get("production_molds", 0)))
        self.breakdown_molds_value.setText(str(stats.get("breakdown_molds", 0)))
        self.available_molds_value.setText(str(stats.get("available_molds", 0)))

        self.table.setRowCount(len(rows))
        if hasattr(self, "loaded_rows_label"):
            self.loaded_rows_label.setText(
                f"Loaded Mold Key Codes: {len(rows)} / {stats.get('total_keys', 0)}"
            )

        for row_index, mold in enumerate(rows):
            self.table.setRowHeight(row_index, 38)

            self._set_item(row_index, 0, mold.get("mold_key_code", ""), mold_id=mold.get("id"))
            self._set_item(row_index, 1, mold.get("mold_count", 0), center=True)
            self._set_item(row_index, 2, mold.get("production_mold_count", 0), center=True)
            self._set_item(row_index, 3, mold.get("breakdown_mold_count", 0), center=True)
            self._set_item(row_index, 4, mold.get("available_mold_count", 0), center=True)

    def _set_item(self, row: int, col: int, value, center: bool = False, mold_id: int | None = None) -> None:
        item = QTableWidgetItem(str(value if value is not None else ""))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        if center:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        if mold_id is not None:
            item.setData(Qt.ItemDataRole.UserRole, int(mold_id))

        self.table.setItem(row, col, item)

    def _validate_counts(self, data: dict) -> bool:
        if not data["mold_key_code"]:
            QMessageBox.warning(self, "Validation", "Mold Key Code is required.")
            return False

        total = int(data["mold_count"])
        used = int(data["production_mold_count"]) + int(data["breakdown_mold_count"])

        if used > total:
            QMessageBox.warning(
                self,
                "Validation",
                "Production Mold Count + Breakdown Mold Count cannot be greater than Total Mold Count.",
            )
            return False

        return True

    def add_mold(self) -> None:
        dialog = MoldDialog(self, "Add Mold")

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()

        if not self._validate_counts(data):
            return

        try:
            self.repo.add_mold(data)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not add mold. " + str(exc))

    def edit_mold_for_row(self, row: int) -> None:
        if row < 0:
            return

        item = self.table.item(row, 0)
        if item is None:
            return

        mold_id = item.data(Qt.ItemDataRole.UserRole)
        if mold_id is None:
            return

        self.edit_mold(int(mold_id))

    def edit_mold(self, mold_id: int) -> None:
        try:
            mold = self.repo.get_mold(mold_id)
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not load selected mold. " + str(exc))
            return

        dialog = MoldDialog(self, "Edit Mold / Add Mold Quantity", mold)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()

        if not self._validate_counts(data):
            return

        try:
            self.repo.update_mold(mold_id, data)
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", "Could not update mold. " + str(exc))
