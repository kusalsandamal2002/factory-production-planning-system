from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
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
from sqlalchemy.sql.elements import quoted_name

from app.database import engine


class AdminDatabaseViewerPage(QWidget):
    """
    Admin-only read-only database inspector.

    Performance rules:
    - No table data is loaded in __init__.
    - Table list loads only when load_tables_once() is called.
    - Rows load only when an admin selects a table or changes page.
    - Row queries use LIMIT/OFFSET.
    """

    DEFAULT_PAGE_SIZE = 100
    MAX_PAGE_SIZE = 1000

    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self._tables_loaded = False
        self._allowed_tables: list[str] = []
        self._current_table: str | None = None
        self._current_offset = 0
        self._current_total = 0
        self._current_columns: list[str] = []
        self._last_rows: list[dict[str, Any]] = []

        self.setStyleSheet(
            """
            QWidget {
                background: #f8fafc;
                color: #0f172a;
                font-family: Segoe UI;
            }

            QFrame#Card {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 16px;
            }

            QLabel#Title {
                color: #0f172a;
                font-size: 21pt;
                font-weight: 950;
            }

            QLabel#Subtitle {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLabel#Badge {
                background: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 8.5pt;
                font-weight: 900;
            }

            QPushButton {
                background: #2563eb;
                color: white;
                border: none;
                border-radius: 9px;
                padding: 8px 12px;
                font-weight: 850;
            }

            QPushButton:hover {
                background: #1d4ed8;
            }

            QPushButton:disabled {
                background: #cbd5e1;
                color: #64748b;
            }

            QPushButton#SecondaryButton {
                background: #e2e8f0;
                color: #0f172a;
            }

            QPushButton#SecondaryButton:hover {
                background: #cbd5e1;
            }

            QComboBox,
            QLineEdit,
            QSpinBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 6px 8px;
                min-height: 26px;
            }

            QTableWidget {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                gridline-color: #e2e8f0;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }

            QHeaderView::section {
                background: #f1f5f9;
                color: #0f172a;
                border: none;
                border-right: 1px solid #e2e8f0;
                border-bottom: 1px solid #e2e8f0;
                padding: 8px;
                font-weight: 900;
            }
            """
        )

        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        header = QFrame()
        header.setObjectName("Card")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(20, 18, 20, 18)
        header_layout.setSpacing(8)

        title_row = QHBoxLayout()
        title = QLabel("Admin Database Viewer")
        title.setObjectName("Title")

        badge = QLabel("READ ONLY")
        badge.setObjectName("Badge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_row.addWidget(title)
        title_row.addStretch()
        title_row.addWidget(badge)

        subtitle = QLabel(
            "View PostgreSQL tables safely. Data loads only when this page is opened and a table is selected."
        )
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)

        header_layout.addLayout(title_row)
        header_layout.addWidget(subtitle)
        root.addWidget(header)

        controls = QFrame()
        controls.setObjectName("Card")
        controls_layout = QVBoxLayout(controls)
        controls_layout.setContentsMargins(16, 14, 16, 14)
        controls_layout.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.table_combo = QComboBox()
        self.table_combo.setMinimumWidth(280)
        self.table_combo.currentTextChanged.connect(self._on_table_changed)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter text across visible text/date columns")
        self.search_input.returnPressed.connect(self.apply_filter)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)

        self.export_btn = QPushButton("Export CSV")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.clicked.connect(self.export_current_page_csv)

        row1.addWidget(QLabel("Table:"))
        row1.addWidget(self.table_combo)
        row1.addWidget(QLabel("Search:"))
        row1.addWidget(self.search_input, 1)
        row1.addWidget(self.refresh_btn)
        row1.addWidget(self.export_btn)

        row2 = QHBoxLayout()
        row2.setSpacing(8)

        self.prev_btn = QPushButton("Previous")
        self.prev_btn.setObjectName("SecondaryButton")
        self.prev_btn.clicked.connect(self.previous_page)

        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("SecondaryButton")
        self.next_btn.clicked.connect(self.next_page)

        self.page_size_spin = QSpinBox()
        self.page_size_spin.setRange(10, self.MAX_PAGE_SIZE)
        self.page_size_spin.setSingleStep(50)
        self.page_size_spin.setValue(self.DEFAULT_PAGE_SIZE)
        self.page_size_spin.valueChanged.connect(self._on_page_size_changed)

        self.status_label = QLabel("Open this page to load table list.")
        self.status_label.setObjectName("Subtitle")

        row2.addWidget(self.prev_btn)
        row2.addWidget(self.next_btn)
        row2.addSpacing(12)
        row2.addWidget(QLabel("Rows per page:"))
        row2.addWidget(self.page_size_spin)
        row2.addStretch()
        row2.addWidget(self.status_label)

        controls_layout.addLayout(row1)
        controls_layout.addLayout(row2)
        root.addWidget(controls)

        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(12, 12, 12, 12)
        table_layout.setSpacing(8)

        self.data_table = QTableWidget()
        self.data_table.setAlternatingRowColors(True)
        self.data_table.setSortingEnabled(False)
        self.data_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.data_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.data_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        table_layout.addWidget(self.data_table)
        root.addWidget(table_card, 1)

        self._update_paging_buttons()

    def load_tables_once(self) -> None:
        if self._tables_loaded:
            return
        self.load_tables()

    def refresh(self) -> None:
        self.load_tables(keep_selection=True)

    def load_tables(self, keep_selection: bool = False) -> None:
        selected_before = self.table_combo.currentText().strip() if keep_selection else ""

        try:
            inspector = inspect(engine)
            table_names = sorted(inspector.get_table_names(schema="public"))
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Could not load table list:\n{exc}")
            return

        self._allowed_tables = table_names
        self._tables_loaded = True

        self.table_combo.blockSignals(True)
        self.table_combo.clear()
        self.table_combo.addItems(table_names)

        if selected_before and selected_before in table_names:
            self.table_combo.setCurrentText(selected_before)

        self.table_combo.blockSignals(False)

        if table_names:
            self.status_label.setText(f"{len(table_names)} tables found.")
            self._on_table_changed(self.table_combo.currentText())
        else:
            self.status_label.setText("No tables found in public schema.")
            self.data_table.clear()
            self.data_table.setRowCount(0)
            self.data_table.setColumnCount(0)

    def _on_table_changed(self, table_name: str) -> None:
        table_name = (table_name or "").strip()

        if not table_name:
            return

        if table_name not in self._allowed_tables:
            QMessageBox.warning(self, "Invalid Table", "Selected table is not allowed.")
            return

        self._current_table = table_name
        self._current_offset = 0
        self.load_current_page()

    def _on_page_size_changed(self) -> None:
        self._current_offset = 0
        if self._current_table:
            self.load_current_page()

    def apply_filter(self) -> None:
        self._current_offset = 0
        if self._current_table:
            self.load_current_page()

    def previous_page(self) -> None:
        page_size = int(self.page_size_spin.value())
        self._current_offset = max(0, self._current_offset - page_size)
        self.load_current_page()

    def next_page(self) -> None:
        page_size = int(self.page_size_spin.value())
        next_offset = self._current_offset + page_size

        if next_offset >= self._current_total:
            return

        self._current_offset = next_offset
        self.load_current_page()

    def load_current_page(self) -> None:
        if not self._current_table:
            return

        if self._current_table not in self._allowed_tables:
            QMessageBox.warning(self, "Invalid Table", "Selected table is not allowed.")
            return

        page_size = int(self.page_size_spin.value())
        search_text = self.search_input.text().strip()

        try:
            columns = self._get_columns(self._current_table)
            rows, total = self._fetch_rows(
                table_name=self._current_table,
                columns=columns,
                limit=page_size,
                offset=self._current_offset,
                search_text=search_text,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Load Failed", str(exc))
            return

        self._current_columns = columns
        self._last_rows = rows
        self._current_total = total

        self._render_rows(columns, rows)
        self._update_status()
        self._update_paging_buttons()

    def _get_columns(self, table_name: str) -> list[str]:
        inspector = inspect(engine)
        column_info = inspector.get_columns(table_name, schema="public")
        return [str(col["name"]) for col in column_info]

    def _quote_identifier(self, name: str) -> str:
        prepared = engine.dialect.identifier_preparer
        return prepared.quote_identifier(name)

    def _table_sql_name(self, table_name: str) -> str:
        prepared = engine.dialect.identifier_preparer
        return f"{prepared.quote_schema('public')}.{prepared.quote_identifier(table_name)}"

    def _fetch_rows(
        self,
        table_name: str,
        columns: list[str],
        limit: int,
        offset: int,
        search_text: str,
    ) -> tuple[list[dict[str, Any]], int]:
        table_sql = self._table_sql_name(table_name)

        where_sql = ""
        params: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
        }

        if search_text and columns:
            searchable_parts = []
            for index, column in enumerate(columns):
                param_name = f"search_{index}"
                searchable_parts.append(
                    f"CAST({self._quote_identifier(column)} AS TEXT) ILIKE :{param_name}"
                )
                params[param_name] = f"%{search_text}%"

            where_sql = "WHERE " + " OR ".join(searchable_parts)

        count_sql = text(f"SELECT COUNT(*) FROM {table_sql} {where_sql};")
        data_sql = text(
            f"""
            SELECT *
            FROM {table_sql}
            {where_sql}
            LIMIT :limit OFFSET :offset;
            """
        )

        with engine.begin() as connection:
            total = int(connection.execute(count_sql, params).scalar() or 0)
            result = connection.execute(data_sql, params)
            rows = [dict(row) for row in result.mappings().all()]

        return rows, total

    def _render_rows(self, columns: list[str], rows: list[dict[str, Any]]) -> None:
        self.data_table.clear()
        self.data_table.setColumnCount(len(columns))
        self.data_table.setRowCount(len(rows))
        self.data_table.setHorizontalHeaderLabels(columns)

        header_font = QFont("Segoe UI")
        header_font.setBold(True)

        for row_index, row in enumerate(rows):
            for col_index, column in enumerate(columns):
                value = row.get(column)
                item = QTableWidgetItem(self._format_value(value))
                item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)

                if value is None:
                    item.setForeground(QColor("#94a3b8"))

                self.data_table.setItem(row_index, col_index, item)

        self.data_table.resizeColumnsToContents()

    def _format_value(self, value: Any) -> str:
        if value is None:
            return "NULL"

        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")

        if isinstance(value, date):
            return value.strftime("%Y-%m-%d")

        if isinstance(value, Decimal):
            return str(value)

        text_value = str(value)
        if len(text_value) > 500:
            return text_value[:500] + "..."

        return text_value

    def _update_status(self) -> None:
        if not self._current_table:
            self.status_label.setText("No table selected.")
            return

        page_size = int(self.page_size_spin.value())
        start = self._current_offset + 1 if self._current_total else 0
        end = min(self._current_offset + page_size, self._current_total)

        self.status_label.setText(
            f"{self._current_table}: showing {start:,}-{end:,} of {self._current_total:,} rows"
        )

    def _update_paging_buttons(self) -> None:
        page_size = int(self.page_size_spin.value())
        self.prev_btn.setEnabled(self._current_offset > 0)
        self.next_btn.setEnabled((self._current_offset + page_size) < self._current_total)

    def export_current_page_csv(self) -> None:
        if not self._current_columns or not self._last_rows:
            QMessageBox.information(self, "Export CSV", "No rows to export.")
            return

        default_name = f"{self._current_table or 'table'}_page.csv"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Current Page",
            default_name,
            "CSV Files (*.csv)",
        )

        if not path:
            return

        try:
            output_path = Path(path)
            with output_path.open("w", newline="", encoding="utf-8-sig") as file:
                writer = csv.DictWriter(file, fieldnames=self._current_columns)
                writer.writeheader()
                for row in self._last_rows:
                    writer.writerow(
                        {
                            column: self._format_value(row.get(column))
                            for column in self._current_columns
                        }
                    )

            QMessageBox.information(self, "Export CSV", f"Exported:\n{output_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Failed", str(exc))

    def refresh_page(self) -> None:
        self.load_tables_once()
