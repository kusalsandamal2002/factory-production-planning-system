from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text
from app.database import engine
from app.utils.reports_export import export_to_csv


class LogDetailDialog(QDialog):
    def __init__(self, parent=None, log_item: dict | None = None):
        super().__init__(parent)
        self.log_item = log_item or {}

        self.setWindowTitle(f"Audit Log Detail: ID {self.log_item.get('id')}")
        self.setMinimumSize(600, 480)

        # Text edits
        self.old_text = QTextEdit()
        self.old_text.setReadOnly(True)
        self.new_text = QTextEdit()
        self.new_text.setReadOnly(True)

        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("SecondaryButton")
        self.close_btn.clicked.connect(self.accept)

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
            QLabel#LabelHeader {
                color: #0f172a;
                font-size: 11pt;
                font-weight: 850;
            }
            QTextEdit {
                font-family: Consolas, monospace;
                background: #f1f5f9;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
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

        info_layout = QHBoxLayout()
        info_layout.addWidget(QLabel(f"<b>Timestamp:</b> {self.log_item.get('action_timestamp')}"))
        info_layout.addWidget(QLabel(f"<b>User:</b> {self.log_item.get('username')}"))
        info_layout.addWidget(QLabel(f"<b>Action:</b> {self.log_item.get('action_type')}"))
        layout.addLayout(info_layout)

        layout.addWidget(QLabel(f"<b>Table Name:</b> {self.log_item.get('table_name')} | <b>Record ID:</b> {self.log_item.get('record_id')}"))
        layout.addWidget(QLabel(f"<b>Note:</b> {self.log_item.get('note')}"))

        # Diff areas
        diff_layout = QHBoxLayout()
        
        left_box = QVBoxLayout()
        left_title = QLabel("Before Change (Old Values)")
        left_title.setObjectName("LabelHeader")
        left_box.addWidget(left_title)
        left_box.addWidget(self.old_text)
        
        right_box = QVBoxLayout()
        right_title = QLabel("After Change (New Values)")
        right_title.setObjectName("LabelHeader")
        right_box.addWidget(right_title)
        right_box.addWidget(self.new_text)

        diff_layout.addLayout(left_box)
        diff_layout.addLayout(right_box)
        layout.addLayout(diff_layout)

        button_row = QHBoxLayout()
        button_row.addStretch()
        button_row.addWidget(self.close_btn)
        layout.addLayout(button_row)

        root.addWidget(card)

    def _load_data(self) -> None:
        old_val = self.log_item.get("old_values") or "No history data recorded."
        new_val = self.log_item.get("new_values") or "No history data recorded."

        self.old_text.setText(old_val)
        self.new_text.setText(new_val)


class AuditLogPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.selected_log_id: int | None = None

        # Controls
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search username, table, record or note...")
        self.search_input.textChanged.connect(self.refresh_table)

        self.action_combo = QComboBox()
        self.action_combo.addItems([
            "All Action Types", "INSERT", "UPDATE", "DELETE", "LOGIN", "RESTORE", "BACKUP"
        ])
        self.action_combo.currentTextChanged.connect(self.refresh_table)

        self.limit_combo = QComboBox()
        self.limit_combo.addItems(["100 Logs", "500 Logs", "1000 Logs", "5000 Logs"])
        self.limit_combo.currentTextChanged.connect(self.refresh_table)

        self.export_btn = QPushButton("📥 Export Logs (CSV)")
        self.export_btn.setObjectName("SecondaryButton")
        self.export_btn.clicked.connect(self.export_logs)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([
            "ID", "Timestamp", "Username", "Action", "Table Name", "Record ID", "Note / Description"
        ])

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

        # Controls Card
        ctrl_card = QFrame()
        ctrl_card.setObjectName("ControlCard")
        ctrl_layout = QVBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(18, 16, 18, 18)
        ctrl_layout.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("System Transactions Audit Log")
        title.setObjectName("SectionTitle")
        hint = QLabel("Track database operations, user configurations changes and execution histories.")
        hint.setObjectName("SectionHint")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        header.addLayout(title_box, 1)

        header.addWidget(self.export_btn)
        header.addWidget(self.refresh_btn)
        ctrl_layout.addLayout(header)

        filters = QHBoxLayout()
        filters.setSpacing(12)
        filters.addWidget(QLabel("Search"))
        filters.addWidget(self.search_input, 2)
        filters.addWidget(QLabel("Action"))
        filters.addWidget(self.action_combo, 1)
        filters.addWidget(QLabel("Limit"))
        filters.addWidget(self.limit_combo, 1)
        ctrl_layout.addLayout(filters)

        root.addWidget(ctrl_card)

        # Table Card
        table_card = QFrame()
        table_card.setObjectName("TableCard")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.setSpacing(12)

        table_title = QLabel("Audit Ledger Logs")
        table_title.setObjectName("SectionTitle")
        table_layout.addWidget(table_title)
        table_layout.addWidget(self.table, 1)

        root.addWidget(table_card, 1)

    def _setup_table(self) -> None:
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setAlternatingRowColors(True)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 160)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 140)
        self.table.setColumnWidth(5, 120)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemDoubleClicked.connect(self.view_detail)

    def refresh(self) -> None:
        self.refresh_table()

    def refresh_table(self) -> None:
        self.selected_log_id = None
        search_text = self.search_input.text().strip()
        action_filter = self.action_combo.currentText()
        limit_text = self.limit_combo.currentText()

        # Parse limit
        limit = int(limit_text.split(" ")[0])

        conditions = []
        params = {"search": f"%{search_text}%", "limit": limit}

        if search_text:
            conditions.append(
                "(username ILIKE :search OR table_name ILIKE :search OR record_id ILIKE :search OR note ILIKE :search)"
            )
        if action_filter != "All Action Types":
            conditions.append("action_type = :action_type")
            params["action_type"] = action_filter

        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

        sql = f"""
            SELECT id, action_timestamp, username, action_type, table_name, record_id, note
            FROM mpps_audit_logs
            {where_sql}
            ORDER BY action_timestamp DESC, id DESC
            LIMIT :limit;
        """

        try:
            with engine.begin() as connection:
                rows = connection.execute(text(sql), params).mappings().all()

            self.table.setRowCount(0)
            for idx, r in enumerate(rows):
                self.table.insertRow(idx)

                time_str = r["action_timestamp"].strftime("%Y-%m-%d %H:%M:%S") if r["action_timestamp"] else "-"
                items = [
                    str(r["id"]),
                    time_str,
                    r["username"],
                    r["action_type"],
                    r["table_name"],
                    r["record_id"] or "-",
                    r["note"] or ""
                ]

                for col_idx, val in enumerate(items):
                    item = QTableWidgetItem(val)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if col_idx in (0, 1, 2, 3, 4, 5):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if col_idx == 0:
                        item.setData(Qt.ItemDataRole.UserRole, int(r["id"]))
                    self.table.setItem(idx, col_idx, item)

            self.table.resizeRowsToContents()

        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Failed to query audit logs: {exc}")

    def on_selection_changed(self) -> None:
        ranges = self.table.selectedRanges()
        if not ranges:
            self.selected_log_id = None
            return
        row = ranges[0].topRow()
        item = self.table.item(row, 0)
        if item is not None:
            self.selected_log_id = item.data(Qt.ItemDataRole.UserRole)

    def view_detail(self) -> None:
        if not self.selected_log_id:
            return

        try:
            with engine.begin() as connection:
                row = connection.execute(
                    text("SELECT * FROM mpps_audit_logs WHERE id = :id;"),
                    {"id": self.selected_log_id}
                ).mappings().first()

            if not row:
                QMessageBox.warning(self, "View Log", "Record no longer exists.")
                return

            dialog = LogDetailDialog(self, dict(row))
            dialog.exec()
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to load details: {exc}")

    def export_logs(self) -> None:
        headers = ["Log ID", "Timestamp", "Username", "Action Type", "Table Name", "Record ID", "Note", "Old Values", "New Values"]
        
        sql = """
            SELECT id, action_timestamp, username, action_type, table_name, record_id, note, old_values, new_values
            FROM mpps_audit_logs
            ORDER BY action_timestamp DESC, id DESC;
        """

        try:
            with engine.begin() as connection:
                rows = connection.execute(text(sql)).mappings().all()

            csv_rows = []
            for r in rows:
                time_str = r["action_timestamp"].strftime("%Y-%m-%d %H:%M:%S") if r["action_timestamp"] else ""
                csv_rows.append([
                    str(r["id"]),
                    time_str,
                    r["username"],
                    r["action_type"],
                    r["table_name"],
                    r["record_id"] or "",
                    r["note"] or "",
                    r["old_values"] or "",
                    r["new_values"] or ""
                ])

            filepath = export_to_csv(headers, csv_rows, "mpps_audit_logs")
            QMessageBox.information(self, "Export Successful", f"Audit logs exported to:\n{filepath}")

        except Exception as exc:
            QMessageBox.critical(self, "Export Error", f"Failed to export logs: {exc}")
