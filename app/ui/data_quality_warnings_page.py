from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
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
    QInputDialog,
)
from sqlalchemy import text
from app.database import engine
from app.utils.reports_export import export_to_csv


class DataQualityIssuesPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.selected_issue_id: int | None = None

        # Widgets
        self.total_issues_value = QLabel("0")
        self.unresolved_warnings_value = QLabel("0")
        self.unresolved_errors_value = QLabel("0")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search material code, message or area...")
        self.search_input.textChanged.connect(self.refresh_table)

        self.level_combo = QComboBox()
        self.level_combo.addItems(["All Severities", "WARNING", "ERROR"])
        self.level_combo.currentTextChanged.connect(self.refresh_table)

        self.status_combo = QComboBox()
        self.status_combo.addItems(["Unresolved Only", "Resolved Only", "All Issues"])
        self.status_combo.currentTextChanged.connect(self.refresh_table)

        self.resolve_btn = QPushButton("Resolve Selected")
        self.resolve_btn.setObjectName("PrimaryButton")
        self.resolve_btn.setEnabled(False)
        self.resolve_btn.clicked.connect(self.resolve_issue)

        self.reevaluate_btn = QPushButton("Re-evaluate Warnings")
        self.reevaluate_btn.setObjectName("SecondaryButton")
        self.reevaluate_btn.clicked.connect(self.reevaluate_warnings)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(
            [
                "ID",
                "Severity",
                "Area",
                "Material Code",
                "Message",
                "Workbook / Sheet / Row",
                "Status",
                "Resolved Note",
                "Resolved At",
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

        # Metrics layout
        metrics_layout = QHBoxLayout()
        metrics_layout.setSpacing(14)
        metrics_layout.addWidget(self._metric_card("Total Quality Issues", self.total_issues_value), 1)
        metrics_layout.addWidget(self._metric_card("Unresolved Warnings", self.unresolved_warnings_value), 1)
        metrics_layout.addWidget(self._metric_card("Unresolved Errors", self.unresolved_errors_value), 1)
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
        title = QLabel("Data Quality Issues & Warnings")
        title.setObjectName("SectionTitle")
        hint = QLabel("Review inconsistencies such as missing weights, missing BOMs, or negative values. Resolve them or run re-evaluation.")
        hint.setObjectName("SectionHint")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        header.addLayout(title_box, 1)
        header.addWidget(self.resolve_btn)
        header.addWidget(self.reevaluate_btn)
        header.addWidget(self.refresh_btn)
        ctrl_layout.addLayout(header)

        form = QHBoxLayout()
        form.setSpacing(12)
        form.addWidget(QLabel("Search"))
        form.addWidget(self.search_input, 2)
        form.addWidget(QLabel("Severity"))
        form.addWidget(self.level_combo, 1)
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

        table_title = QLabel("Data Quality Log")
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
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(1, 100)
        self.table.setColumnWidth(2, 110)
        self.table.setColumnWidth(3, 110)
        self.table.setColumnWidth(6, 100)
        self.table.setColumnWidth(8, 140)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)

    def refresh(self) -> None:
        try:
            self.refresh_metrics()
            self.refresh_table()
        except Exception as exc:
            QMessageBox.critical(self, "Data Quality Error", f"Failed to refresh: {exc}")

    def refresh_metrics(self) -> None:
        with engine.begin() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS total_issues,
                        SUM(CASE WHEN is_resolved = FALSE AND issue_level = 'WARNING' THEN 1 ELSE 0 END) AS unresolved_warnings,
                        SUM(CASE WHEN is_resolved = FALSE AND issue_level = 'ERROR' THEN 1 ELSE 0 END) AS unresolved_errors
                    FROM mpps_data_quality_issues;
                    """
                )
            ).mappings().one()

        self.total_issues_value.setText(str(row["total_issues"] or 0))
        self.unresolved_warnings_value.setText(str(row["unresolved_warnings"] or 0))
        self.unresolved_errors_value.setText(str(row["unresolved_errors"] or 0))

    def refresh_table(self) -> None:
        self.selected_issue_id = None
        self.resolve_btn.setEnabled(False)

        search_text = self.search_input.text().strip()
        severity = self.level_combo.currentText()
        status = self.status_combo.currentText()

        conditions = []
        params = {"search": f"%{search_text}%"}

        if search_text:
            conditions.append(
                """
                (
                    material_code ILIKE :search
                    OR issue_message ILIKE :search
                    OR issue_area ILIKE :search
                )
                """
            )

        if severity != "All Severities":
            conditions.append("issue_level = :severity")
            params["severity"] = severity

        if status == "Unresolved Only":
            conditions.append("is_resolved = FALSE")
        elif status == "Resolved Only":
            conditions.append("is_resolved = TRUE")

        where_sql = "WHERE " + " AND ".join(conditions) if conditions else ""

        sql = f"""
            SELECT
                id, issue_level, issue_area, material_code, issue_message,
                source_workbook, source_sheet, source_row,
                is_resolved, resolved_note, resolved_at
            FROM mpps_data_quality_issues
            {where_sql}
            ORDER BY is_resolved ASC, id DESC;
        """

        with engine.begin() as connection:
            rows = connection.execute(text(sql), params).mappings().all()

        self.table.setRowCount(0)
        for idx, row in enumerate(rows):
            self.table.insertRow(idx)

            trace_info = f"{row['source_workbook'] or ''} / {row['source_sheet'] or ''} / R{row['source_row'] or ''}"
            if trace_info.strip(" / R") == "":
                trace_info = "Manual Entry"

            status_str = "Resolved" if row["is_resolved"] else "Unresolved"
            resolved_at_str = row["resolved_at"].strftime("%Y-%m-%d %H:%M") if row["resolved_at"] else "-"

            items = [
                str(row["id"]),
                row["issue_level"],
                row["issue_area"],
                row["material_code"] or "-",
                row["issue_message"],
                trace_info,
                status_str,
                row["resolved_note"] or "-",
                resolved_at_str
            ]

            for col_idx, val in enumerate(items):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                if col_idx in (0, 1, 2, 3, 6, 8):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                # Style Severity
                if col_idx == 1:
                    if row["issue_level"] == "ERROR":
                        item.setForeground(Qt.GlobalColor.red)
                    else:
                        item.setForeground(Qt.GlobalColor.darkYellow)

                # Style Status
                if col_idx == 6:
                    if row["is_resolved"]:
                        item.setForeground(Qt.GlobalColor.darkGreen)
                    else:
                        item.setForeground(Qt.GlobalColor.red)

                if col_idx == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))

                self.table.setItem(idx, col_idx, item)

        self.table.resizeRowsToContents()

    def on_selection_changed(self) -> None:
        ranges = self.table.selectedRanges()
        if not ranges:
            self.selected_issue_id = None
            self.resolve_btn.setEnabled(False)
            return

        row = ranges[0].topRow()
        item = self.table.item(row, 0)
        status_item = self.table.item(row, 6)

        if item is not None and status_item is not None:
            self.selected_issue_id = item.data(Qt.ItemDataRole.UserRole)
            # Enable resolution button only if the issue is unresolved
            self.resolve_btn.setEnabled(status_item.text() == "Unresolved")

    def resolve_issue(self) -> None:
        if not self.selected_issue_id:
            return

        note, ok = QInputDialog.getText(
            self,
            "Resolve Data Issue",
            "Enter resolution actions or notes:"
        )
        if not ok or not note.strip():
            return

        username = self.current_user.username if self.current_user else "anonymous"

        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        UPDATE mpps_data_quality_issues
                        SET is_resolved = TRUE,
                            resolved_note = :note,
                            resolved_at = CURRENT_TIMESTAMP
                        WHERE id = :id;
                        """
                    ),
                    {"id": self.selected_issue_id, "note": note.strip()}
                )

                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_audit_logs (username, action_type, table_name, record_id, note)
                        VALUES (:username, 'UPDATE', 'mpps_data_quality_issues', :record, :note);
                        """
                    ),
                    {
                        "username": username,
                        "record": str(self.selected_issue_id),
                        "note": f"Data quality issue resolved. Note: {note.strip()}"
                    }
                )

            QMessageBox.information(self, "Success", "Issue marked as resolved.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Resolution Error", f"Failed to resolve issue: {exc}")

    def reevaluate_warnings(self) -> None:
        # Re-run data quality checks non-destructively
        username = self.current_user.username if self.current_user else "anonymous"

        try:
            from map_raw_excel_to_clean_mpps import create_data_quality_issues
            create_data_quality_issues()
            
            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_audit_logs (username, action_type, table_name, note)
                        VALUES (:username, 'RESTORE', 'mpps_data_quality_issues', 'Re-evaluated all data quality warnings from active master data.');
                        """
                    ),
                    {"username": username}
                )

            QMessageBox.information(self, "Re-evaluation Complete", "All data quality issues and warnings have been re-evaluated against the active database state.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Re-evaluation Failed", f"Failed to re-run data quality checks: {exc}")
