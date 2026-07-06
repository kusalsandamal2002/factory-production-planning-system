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
from sqlalchemy import inspect, text

from app.database import engine


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class StockEditDialog(QDialog):
    def __init__(self, parent=None, stock_item: dict | None = None):
        super().__init__(parent)

        self.stock_item = stock_item or {}

        self.setWindowTitle("Edit SAP Stock Balance")
        self.setMinimumWidth(620)

        self.sap_code_label = QLabel("-")
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
                font-family: "Segoe UI";
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

            QLineEdit, QSpinBox {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 9px 12px;
                font-size: 10pt;
                font-weight: 650;
                min-height: 24px;
            }

            QLineEdit:focus, QSpinBox:focus {
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

        title = QLabel("SAP Stock Balance")
        title.setObjectName("Title")

        hint = QLabel("Update stock balances carefully. These values are used for planning decisions.")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        self._add_readonly_field(form, 0, "SAP Code", self.sap_code_label)
        self._add_readonly_field(form, 1, "Tyre Description", self.description_label)
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
        self.sap_code_label.setText(str(self.stock_item.get("sap_code") or "-"))
        self.description_label.setText(str(self.stock_item.get("tyre_description") or "-"))

        self.fg_stock_input.setValue(int(self.stock_item.get("fg_stock") or 0))
        self.qc_stock_input.setValue(int(self.stock_item.get("qc_stock") or 0))
        self.scrap_stock_input.setValue(int(self.stock_item.get("scrap_stock") or 0))
        self.blocked_stock_input.setValue(int(self.stock_item.get("blocked_stock") or 0))

    def get_data(self) -> dict:
        reason = self.reason_input.text().strip()

        if not reason:
            raise ValueError("Correction reason is required.")

        return {
            "sap_code": self.stock_item.get("sap_code"),
            "fg_stock": self.fg_stock_input.value(),
            "qc_stock": self.qc_stock_input.value(),
            "scrap_stock": self.scrap_stock_input.value(),
            "blocked_stock": self.blocked_stock_input.value(),
            "reason": reason,
        }


class StockMasterPage(QWidget):
    def __init__(self):
        super().__init__()

        self.selected_sap_code: str | None = None

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search SAP code or tyre description...")
        self.search_input.textChanged.connect(self.refresh_table)

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

        self.sync_btn = QPushButton("Sync Tyres From Master")
        self.sync_btn.setObjectName("PrimaryButton")
        self.sync_btn.clicked.connect(lambda: self.sync_tyres_from_master(show_message=True))

        self.edit_btn = QPushButton("Edit Selected Stock")
        self.edit_btn.setObjectName("PrimaryButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.edit_selected_stock)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "SAP Code",
                "Tyre Description",
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
            QFrame#ControlCard,
            QFrame#TableCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 19pt;
                font-weight: 950;
            }

            QLabel#PageHint {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLabel#FieldLabel {
                color: #334155;
                font-size: 9pt;
                font-weight: 850;
            }

            QLineEdit, QComboBox {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 9px 12px;
                font-size: 10pt;
                font-weight: 650;
                min-height: 24px;
            }

            QLineEdit:focus, QComboBox:focus {
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

        root.addWidget(self._build_control_card())
        root.addWidget(self._build_table_card(), 1)

    def _build_control_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("ControlCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        header = QHBoxLayout()

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel("SAP Stock Master")
        title.setObjectName("PageTitle")

        hint = QLabel(
            "Stock table uses SAP Code as the item key. Missing tyres can be synced from the tyre master with zero opening stock."
        )
        hint.setObjectName("PageHint")
        hint.setWordWrap(True)

        title_box.addWidget(title)
        title_box.addWidget(hint)

        header.addLayout(title_box, 1)
        header.addWidget(self.sync_btn)
        header.addWidget(self.edit_btn)
        header.addWidget(self.refresh_btn)

        layout.addLayout(header)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        search_label = QLabel("Search")
        search_label.setObjectName("FieldLabel")

        status_label = QLabel("Stock Status")
        status_label.setObjectName("FieldLabel")

        form.addWidget(search_label, 0, 0)
        form.addWidget(self.search_input, 0, 1, 1, 5)

        form.addWidget(status_label, 1, 0)
        form.addWidget(self.stock_status_combo, 1, 1, 1, 5)

        form.setColumnStretch(1, 2)
        form.setColumnStretch(2, 1)
        form.setColumnStretch(3, 1)
        form.setColumnStretch(4, 1)
        form.setColumnStretch(5, 1)

        layout.addLayout(form)

        return card

    def _build_table_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(14)

        title = QLabel("SAP Stock Data")
        title.setObjectName("PageTitle")

        hint = QLabel("Double-click a row to edit stock. Available stock = FG + QC - Scrap - Blocked.")
        hint.setObjectName("PageHint")
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

        self.table.setColumnWidth(0, 155)
        self.table.setColumnWidth(2, 95)
        self.table.setColumnWidth(3, 95)
        self.table.setColumnWidth(4, 95)
        self.table.setColumnWidth(5, 105)
        self.table.setColumnWidth(6, 115)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemDoubleClicked.connect(self.edit_selected_stock)

    def refresh(self) -> None:
        try:
            self.ensure_sap_stock_table()

            if self.get_stock_count() == 0:
                self.sync_tyres_from_master(show_message=False)

            self.refresh_table()

        except Exception as exc:
            QMessageBox.critical(self, "SAP Stock Error", str(exc))

    def ensure_sap_stock_table(self) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS mpps_sap_stock_items (
                        id SERIAL PRIMARY KEY,
                        sap_code VARCHAR(100) NOT NULL UNIQUE,
                        tyre_description TEXT NOT NULL,
                        tyre_type VARCHAR(150),
                        fg_stock INTEGER NOT NULL DEFAULT 0,
                        qc_stock INTEGER NOT NULL DEFAULT 0,
                        scrap_stock INTEGER NOT NULL DEFAULT 0,
                        blocked_stock INTEGER NOT NULL DEFAULT 0,
                        is_active BOOLEAN NOT NULL DEFAULT TRUE,
                        source_table VARCHAR(150),
                        source_note TEXT,
                        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
            )

    def get_stock_count(self) -> int:
        with engine.begin() as connection:
            return int(
                connection.execute(
                    text("SELECT COUNT(*) FROM mpps_sap_stock_items WHERE is_active = TRUE;")
                ).scalar()
                or 0
            )

    def sync_tyres_from_master(self, show_message: bool = True) -> None:
        self.ensure_sap_stock_table()

        source_rows, source_table = self.find_tyre_master_rows()

        if not source_rows:
            if show_message:
                QMessageBox.warning(
                    self,
                    "No SAP Tyres Found",
                    "Tyre master table with SAP Code was not found.\n\n"
                    "Please confirm where your SAP tyre list is stored, or import the SAP tyre Excel list first.",
                )
            self.refresh_table()
            return

        insert_sql = text(
            """
            INSERT INTO mpps_sap_stock_items
                (
                    sap_code,
                    tyre_description,
                    tyre_type,
                    fg_stock,
                    qc_stock,
                    scrap_stock,
                    blocked_stock,
                    is_active,
                    source_table,
                    source_note,
                    updated_at
                )
            SELECT
                CAST(:sap_code AS varchar),
                CAST(:tyre_description AS text),
                CAST(:tyre_type AS varchar),
                0,
                0,
                0,
                0,
                TRUE,
                CAST(:source_table AS varchar),
                'Auto-created from tyre master with zero opening stock.',
                CURRENT_TIMESTAMP
            WHERE NOT EXISTS (
                SELECT 1
                FROM mpps_sap_stock_items
                WHERE sap_code = CAST(:sap_code AS varchar)
            );
            """
        )

        inserted = 0

        with engine.begin() as connection:
            for row in source_rows:
                result = connection.execute(
                    insert_sql,
                    {
                        "sap_code": row["sap_code"],
                        "tyre_description": row["tyre_description"],
                        "tyre_type": row["tyre_type"],
                        "source_table": source_table,
                    },
                )

                inserted += int(result.rowcount or 0)

        self.refresh_table()

        if show_message:
            QMessageBox.information(
                self,
                "SAP Stock Sync Complete",
                f"Source table: {source_table}\nNew SAP stock items added: {inserted}",
            )

    def find_tyre_master_rows(self) -> tuple[list[dict], str]:
        inspector = inspect(engine)

        excluded_keywords = [
            "stock",
            "audit",
            "user",
            "role",
            "alembic",
        ]

        sap_candidates = [
            "sap_code",
            "sapcode",
            "sap_material_code",
            "sap_material",
            "material_code",
            "item_code",
            "code",
        ]

        desc_candidates = [
            "tyre_description",
            "item_description",
            "description",
            "product_description",
            "product_name",
            "name",
        ]

        type_candidates = [
            "tyre_type",
            "product_group",
            "product_type",
            "category",
            "group_name",
            "type",
        ]

        for table_name in inspector.get_table_names():
            lower_table = table_name.lower()

            if any(keyword in lower_table for keyword in excluded_keywords):
                continue

            columns = [column["name"] for column in inspector.get_columns(table_name)]
            lower_map = {column.lower(): column for column in columns}

            sap_col = self._first_existing_column(lower_map, sap_candidates)
            desc_col = self._first_existing_column(lower_map, desc_candidates)
            type_col = self._first_existing_column(lower_map, type_candidates)

            if not sap_col or not desc_col:
                continue

            type_expr = (
                f"CAST({_quote_ident(type_col)} AS varchar)"
                if type_col
                else "'Tyre'"
            )

            sql = f"""
                SELECT DISTINCT
                    CAST({_quote_ident(sap_col)} AS varchar) AS sap_code,
                    CAST({_quote_ident(desc_col)} AS text) AS tyre_description,
                    COALESCE(NULLIF(TRIM({type_expr}), ''), 'Tyre') AS tyre_type
                FROM {_quote_ident(table_name)}
                WHERE {_quote_ident(sap_col)} IS NOT NULL
                  AND TRIM(CAST({_quote_ident(sap_col)} AS varchar)) <> ''
                  AND {_quote_ident(desc_col)} IS NOT NULL
                  AND TRIM(CAST({_quote_ident(desc_col)} AS varchar)) <> ''
                ORDER BY sap_code ASC;
            """

            with engine.begin() as connection:
                rows = connection.execute(text(sql)).mappings().all()

            result_rows = [dict(row) for row in rows]

            if result_rows:
                return result_rows, table_name

        return [], "-"

    def _first_existing_column(self, lower_map: dict[str, str], candidates: list[str]) -> str | None:
        for candidate in candidates:
            if candidate.lower() in lower_map:
                return lower_map[candidate.lower()]

        return None

    def refresh_table(self, *args) -> None:
        self.selected_sap_code = None
        self.edit_btn.setEnabled(False)

        search_text = self.search_input.text().strip()
        status_value = self.stock_status_combo.currentText().strip()

        conditions = ["is_active = TRUE"]
        params = {
            "search": f"%{search_text}%",
        }

        if search_text:
            conditions.append(
                """
                (
                    sap_code ILIKE :search
                    OR tyre_description ILIKE :search
                )
                """
            )

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
                sap_code,
                tyre_description,
                fg_stock,
                qc_stock,
                scrap_stock,
                blocked_stock,
                (fg_stock + qc_stock - scrap_stock - blocked_stock) AS available_stock
            FROM mpps_sap_stock_items
            {where_sql}
            ORDER BY available_stock DESC, sap_code ASC
            LIMIT 2000;
        """

        with engine.begin() as connection:
            rows = connection.execute(text(sql), params).mappings().all()

        self.table.setRowCount(0)

        for row_index, row in enumerate(rows):
            self.table.insertRow(row_index)

            values = [
                row["sap_code"],
                row["tyre_description"],
                self._format_int(row["fg_stock"]),
                self._format_int(row["qc_stock"]),
                self._format_int(row["scrap_stock"]),
                self._format_int(row["blocked_stock"]),
                self._format_int(row["available_stock"]),
            ]

            for column_index, value in enumerate(values):
                item = self._readonly_item(value)

                if column_index in {0, 2, 3, 4, 5, 6}:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if column_index == 6:
                    self._apply_available_stock_style(item, int(row["available_stock"] or 0))

                if column_index == 0:
                    item.setData(Qt.ItemDataRole.UserRole, row["sap_code"])

                self.table.setItem(row_index, column_index, item)

        self.table.resizeRowsToContents()

    def edit_selected_stock(self, *args) -> None:
        if not self.selected_sap_code:
            return

        stock_item = self.get_stock_item(self.selected_sap_code)

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

    def get_stock_item(self, sap_code: str):
        with engine.begin() as connection:
            return connection.execute(
                text(
                    """
                    SELECT
                        sap_code,
                        tyre_description,
                        tyre_type,
                        fg_stock,
                        qc_stock,
                        scrap_stock,
                        blocked_stock
                    FROM mpps_sap_stock_items
                    WHERE sap_code = :sap_code
                    LIMIT 1;
                    """
                ),
                {"sap_code": sap_code},
            ).mappings().first()

    def save_stock_balance(self, data: dict) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE mpps_sap_stock_items
                    SET
                        fg_stock = :fg_stock,
                        qc_stock = :qc_stock,
                        scrap_stock = :scrap_stock,
                        blocked_stock = :blocked_stock,
                        source_note = :reason,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE sap_code = :sap_code;
                    """
                ),
                data,
            )

    def on_selection_changed(self) -> None:
        selected_items = self.table.selectedItems()

        if not selected_items:
            self.selected_sap_code = None
            self.edit_btn.setEnabled(False)
            return

        row = selected_items[0].row()
        sap_item = self.table.item(row, 0)

        if sap_item is None:
            self.selected_sap_code = None
            self.edit_btn.setEnabled(False)
            return

        self.selected_sap_code = sap_item.data(Qt.ItemDataRole.UserRole)
        self.edit_btn.setEnabled(bool(self.selected_sap_code))

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
