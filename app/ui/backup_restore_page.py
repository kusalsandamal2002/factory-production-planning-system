from __future__ import annotations

import json
from datetime import date, datetime, time
from decimal import Decimal
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text
from app.database import engine

# Correct dependency order for deletion (top to bottom) and insertion (bottom to top)
TABLES_DEPENDENCY_ORDER = [
    "oven_schedule",
    "schedule_change_log",
    "order_status_history",
    "tire_stock_movements",
    "mpps_audit_logs",
    "order_items",
    "orders",
    "mpps_stock_items",
    "mpps_band_master",
    "mpps_capacity_master",
    "production_rules",
    "shifts",
    "ovens",
    "tire_types",
    "customers",
    "users",
    "roles",
]


class BackupRestorePage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user

        # Widgets
        self.backup_btn = QPushButton("💾 Export JSON Database Backup")
        self.backup_btn.setObjectName("PrimaryButton")
        self.backup_btn.clicked.connect(self.export_backup)

        self.restore_btn = QPushButton("📂 Import / Restore Database Backup")
        self.restore_btn.setObjectName("DangerButton")
        self.restore_btn.clicked.connect(self.import_backup)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setPlaceholderText("Operations logs will be displayed here...")

        self._apply_styles()
        self._build_ui()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#ControlCard,
            QFrame#LogCard {
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
            QPushButton#DangerButton {
                background: #ef4444;
                color: #ffffff;
                font-weight: bold;
                border-radius: 8px;
                padding: 10px 18px;
            }
            QPushButton#DangerButton:hover {
                background: #dc2626;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        # Control Card
        ctrl_card = QFrame()
        ctrl_card.setObjectName("ControlCard")
        ctrl_layout = QVBoxLayout(ctrl_card)
        ctrl_layout.setContentsMargins(18, 16, 18, 18)
        ctrl_layout.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title = QLabel("System Backup & Restore Utility")
        title.setObjectName("SectionTitle")
        hint = QLabel("Export clean master configuration and transactional schedule logs. Reverts to safe checkpoints.")
        hint.setObjectName("SectionHint")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        header.addLayout(title_box, 1)

        header.addWidget(self.backup_btn)
        header.addWidget(self.restore_btn)

        ctrl_layout.addLayout(header)
        root.addWidget(ctrl_card)

        # Log Card
        log_card = QFrame()
        log_card.setObjectName("LogCard")
        log_layout = QVBoxLayout(log_card)
        log_layout.setContentsMargins(18, 16, 18, 18)
        log_layout.setSpacing(8)

        log_title = QLabel("Operation Console Output")
        log_title.setObjectName("SectionTitle")
        log_layout.addWidget(log_title)
        log_layout.addWidget(self.log_area, 1)

        root.addWidget(log_card, 1)

    def log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_area.append(f"[{timestamp}] {message}")

    def serialize_value(self, val) -> any:
        if isinstance(val, (datetime, date)):
            return val.isoformat()
        if isinstance(val, time):
            return val.strftime("%H:%M:%S")
        if isinstance(val, Decimal):
            return float(val)
        return val

    def export_backup(self) -> None:
        default_name = f"mpps_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Database Backup", default_name, "JSON Files (*.json)"
        )
        if not file_path:
            return

        self.log(f"Starting database export to: {file_path}")
        backup_data = {}

        try:
            with engine.connect() as connection:
                # We select from tables in dependency order
                for table in TABLES_DEPENDENCY_ORDER:
                    self.log(f"Exporting table: {table}...")
                    rows = connection.execute(text(f"SELECT * FROM {table};")).mappings().all()
                    
                    serialized_rows = []
                    for row in rows:
                        s_row = {k: self.serialize_value(v) for k, v in row.items()}
                        serialized_rows.append(s_row)
                    
                    backup_data[table] = serialized_rows
                    self.log(f"  Exported {len(serialized_rows)} rows from {table}")

            # Write JSON file
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(backup_data, f, indent=2)

            # Log audit
            username = self.current_user.username if self.current_user else "anonymous"
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO mpps_audit_logs (username, action_type, table_name, note)
                        VALUES (:username, 'BACKUP', 'all', :note);
                        """
                    ),
                    {"username": username, "note": f"Exported JSON backup file: {default_name}"}
                )

            self.log("Backup completed successfully!")
            QMessageBox.information(self, "Success", "Database exported successfully.")

        except Exception as exc:
            self.log(f"CRITICAL ERROR: Failed to export: {exc}")
            QMessageBox.critical(self, "Backup Error", f"Failed to export backup: {exc}")

    def import_backup(self) -> None:
        # Check privileges
        if self.current_user and self.current_user.role and self.current_user.role.role_name != "Admin":
            QMessageBox.warning(self, "Permission Denied", "Only administrators can restore backups.")
            return

        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Database Backup", "", "JSON Files (*.json)"
        )
        if not file_path:
            return

        confirm_msg = (
            "WARNING: Restoring will overwrite all current schedule plans, users, and clean factory data.\n"
            "Raw Excel preserved tables are NOT affected.\n\n"
            "This operation cannot be undone. Are you sure you want to proceed?"
        )
        reply = QMessageBox.question(
            self,
            "Confirm Restore",
            confirm_msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.log("Restore cancelled by user.")
            return

        self.log(f"Reading backup file: {file_path}")
        try:
            with open(file_path, encoding="utf-8") as f:
                backup_data = json.load(f)
        except Exception as exc:
            self.log(f"ERROR: Invalid JSON file: {exc}")
            QMessageBox.critical(self, "Error", f"Failed to parse backup JSON file: {exc}")
            return

        self.log("Starting transactional database restore...")
        
        try:
            with engine.begin() as connection:
                # 1. Delete in forward dependency order (top to bottom)
                for table in TABLES_DEPENDENCY_ORDER:
                    self.log(f"Deleting rows from {table}...")
                    connection.execute(text(f"DELETE FROM {table};"))

                # 2. Insert in reverse dependency order (bottom to top)
                for table in reversed(TABLES_DEPENDENCY_ORDER):
                    rows = backup_data.get(table, [])
                    if not rows:
                        self.log(f"No records to insert for {table}")
                        continue
                    
                    self.log(f"Restoring {len(rows)} rows to {table}...")
                    
                    # Columns to insert
                    cols = list(rows[0].keys())
                    placeholders = ", ".join(f":{c}" for c in cols)
                    sql = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({placeholders});"
                    
                    connection.execute(text(sql), rows)

                    # 3. Reset primary key SERIAL sequence if it has 'id' column
                    # Postgres table sequence reset
                    has_id = "id" in cols
                    if has_id:
                        seq_sql = f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1)) FROM {table};"
                        try:
                            connection.execute(text(seq_sql))
                        except Exception:
                            # Table might not have standard sequence name or serial type
                            pass

                # Log audit record inside the transaction
                username = self.current_user.username if self.current_user else "anonymous"
                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_audit_logs (username, action_type, table_name, note)
                        VALUES (:username, 'RESTORE', 'all', :note);
                        """
                    ),
                    {"username": username, "note": f"Restored JSON backup file from: {file_path}"}
                )

            self.log("Restore completed successfully! All changes committed.")
            QMessageBox.information(self, "Success", "Database restored successfully.")

        except Exception as exc:
            self.log(f"CRITICAL ERROR: Restore failed. Transaction rolled back! Detail: {exc}")
            QMessageBox.critical(self, "Restore Failed", f"Restore operation failed and was rolled back: {exc}")

    def refresh(self) -> None:
        pass
