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
from app.services.auth_service import hash_password


class UserEditDialog(QDialog):
    def __init__(self, parent=None, user_item: dict | None = None, roles: list[dict] = None):
        super().__init__(parent)
        self.user_item = user_item or {}
        self.roles = roles or []
        self.is_new = user_item is None

        self.setWindowTitle("Add User" if self.is_new else "Edit User")
        self.setMinimumWidth(450)

        self.full_name_input = QLineEdit()
        self.full_name_input.setPlaceholderText("Enter full name...")

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username...")

        self.password_input = QLineEdit()
        if self.is_new:
            self.password_input.setPlaceholderText("Enter password...")
        else:
            self.password_input.setPlaceholderText("(Leave blank to keep existing password)")
            self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.role_combo = QComboBox()
        for r in self.roles:
            self.role_combo.addItem(r["role_name"], r["id"])

        self.active_checkbox = QCheckBox("User Active / Allowed Login")
        self.active_checkbox.setChecked(True)

        self.save_btn = QPushButton("Save User")
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

        title = QLabel("User Account Details")
        title.setObjectName("Title")
        hint = QLabel("Set account names, credentials and security roles.")
        hint.setObjectName("Hint")
        layout.addWidget(title)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        form.addWidget(QLabel("Full Name"), 0, 0)
        form.addWidget(self.full_name_input, 0, 1)
        form.addWidget(QLabel("Username"), 1, 0)
        form.addWidget(self.username_input, 1, 1)
        form.addWidget(QLabel("Password"), 2, 0)
        form.addWidget(self.password_input, 2, 1)
        form.addWidget(QLabel("Security Role"), 3, 0)
        form.addWidget(self.role_combo, 3, 1)

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

        self.full_name_input.setText(str(self.user_item.get("full_name") or ""))
        self.username_input.setText(str(self.user_item.get("username") or ""))
        self.username_input.setReadOnly(True)  # Username cannot be changed
        self.active_checkbox.setChecked(bool(self.user_item.get("is_active")))

        # Set role index
        role_id = self.user_item.get("role_id")
        for idx in range(self.role_combo.count()):
            if self.role_combo.itemData(idx) == role_id:
                self.role_combo.setCurrentIndex(idx)
                break

    def get_data(self) -> dict:
        full_name = self.full_name_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        role_id = self.role_combo.currentData()

        if not full_name:
            raise ValueError("Full Name is required.")
        if not username:
            raise ValueError("Username is required.")
        if self.is_new and not password:
            raise ValueError("Password is required for new users.")

        res = {
            "id": self.user_item.get("id"),
            "full_name": full_name,
            "username": username,
            "role_id": role_id,
            "is_active": self.active_checkbox.isChecked(),
        }

        if password:
            res["password_hash"] = hash_password(password)

        return res


class UsersRolesPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.selected_user_id: int | None = None
        self.roles_list: list[dict] = []

        # UI elements
        self.admin_badge = QLabel("")
        self.admin_badge.setObjectName("AdminBadge")

        self.add_btn = QPushButton("+ Create User Account")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.clicked.connect(self.add_user)

        self.edit_btn = QPushButton("Edit User Settings")
        self.edit_btn.setObjectName("SecondaryButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.edit_selected_user)

        self.refresh_btn = QPushButton("Refresh List")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "ID", "Full Name", "Username", "Security Role", "Status", "Created At"
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
            QLabel#AdminBadge {
                border-radius: 12px;
                padding: 6px 14px;
                font-size: 9.5pt;
                font-weight: 900;
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
        title = QLabel("System Users & Roles")
        title.setObjectName("SectionTitle")
        hint = QLabel("Manage users, security permissions and system access control level.")
        hint.setObjectName("SectionHint")
        title_box.addWidget(title)
        title_box.addWidget(hint)
        header.addLayout(title_box, 1)

        header.addWidget(self.admin_badge)
        header.addWidget(self.add_btn)
        header.addWidget(self.edit_btn)
        header.addWidget(self.refresh_btn)

        ctrl_layout.addLayout(header)
        root.addWidget(ctrl_card)

        # Table Card
        table_card = QFrame()
        table_card.setObjectName("TableCard")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(18, 16, 18, 18)
        table_layout.setSpacing(12)

        table_title = QLabel("Registered User Logins")
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
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(2, 130)
        self.table.setColumnWidth(4, 100)
        self.table.setColumnWidth(5, 180)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemDoubleClicked.connect(self.edit_selected_user)

    def is_admin(self) -> bool:
        if self.current_user is None:
            return True  # Fallback for debugging
        if self.current_user.role is None:
            return False
        return self.current_user.role.role_name == "Admin"

    def refresh(self) -> None:
        # Check permissions
        if self.is_admin():
            self.admin_badge.setText("Authorized: Admin")
            self.admin_badge.setStyleSheet("background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe;")
            self.add_btn.setEnabled(True)
        else:
            self.admin_badge.setText("Read Only: Manager/Viewer")
            self.admin_badge.setStyleSheet("background: #fef3c7; color: #d97706; border: 1px solid #fde68a;")
            self.add_btn.setEnabled(False)

        self.load_roles()
        self.refresh_table()

    def load_roles(self) -> None:
        self.roles_list.clear()
        try:
            with engine.begin() as connection:
                rows = connection.execute(
                    text("SELECT id, role_name FROM roles ORDER BY id ASC;")
                ).mappings().all()
                for r in rows:
                    self.roles_list.append(dict(r))
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Failed to load roles: {exc}")

    def refresh_table(self) -> None:
        self.selected_user_id = None
        self.edit_btn.setEnabled(False)

        sql = """
            SELECT u.id, u.full_name, u.username, u.role_id, r.role_name, u.is_active, u.created_at
            FROM users u
            JOIN roles r ON u.role_id = r.id
            ORDER BY u.id ASC;
        """

        try:
            with engine.begin() as connection:
                rows = connection.execute(text(sql)).mappings().all()

            self.table.setRowCount(0)
            for idx, row in enumerate(rows):
                self.table.insertRow(idx)

                created_str = row["created_at"].strftime("%Y-%m-%d %H:%M:%S") if row["created_at"] else "-"
                items = [
                    str(row["id"]),
                    row["full_name"],
                    row["username"],
                    row["role_name"],
                    "Active" if row["is_active"] else "Inactive",
                    created_str
                ]

                for col_idx, val in enumerate(items):
                    item = QTableWidgetItem(val)
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if col_idx in (0, 2, 4, 5):
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    if col_idx == 0:
                        item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))
                    self.table.setItem(idx, col_idx, item)

            self.table.resizeRowsToContents()

        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Failed to load users: {exc}")

    def on_selection_changed(self) -> None:
        ranges = self.table.selectedRanges()
        if not ranges:
            self.selected_user_id = None
            self.edit_btn.setEnabled(False)
            return
        row = ranges[0].topRow()
        item = self.table.item(row, 0)
        if item is not None:
            self.selected_user_id = item.data(Qt.ItemDataRole.UserRole)
            # Enable Edit only if current user is admin
            self.edit_btn.setEnabled(self.is_admin())

    def add_user(self) -> None:
        if not self.is_admin():
            QMessageBox.warning(self, "Permission Denied", "Only Administrators can create users.")
            return

        dialog = UserEditDialog(self, roles=self.roles_list)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            data = dialog.get_data()
            actor = self.current_user.username if self.current_user else "anonymous"

            with engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO users (full_name, username, password_hash, role_id, is_active, created_at)
                        VALUES (:full_name, :username, :password_hash, :role_id, :is_active, CURRENT_TIMESTAMP);
                        """
                    ),
                    data
                )

                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_audit_logs (username, action_type, table_name, record_id, new_values, note)
                        VALUES (:username, 'INSERT', 'users', :record, :val, 'Created new user account.');
                        """
                    ),
                    {"username": actor, "record": data["username"], "val": f"Full Name: {data['full_name']}, Role ID: {data['role_id']}"}
                )

            QMessageBox.information(self, "Success", f"User account '{data['username']}' created successfully.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error Saving User", f"Failed to create user: {exc}")

    def edit_selected_user(self) -> None:
        if not self.is_admin():
            QMessageBox.warning(self, "Permission Denied", "Only Administrators can edit users.")
            return

        if not self.selected_user_id:
            return

        try:
            with engine.begin() as connection:
                row = connection.execute(
                    text("SELECT * FROM users WHERE id = :id;"),
                    {"id": self.selected_user_id}
                ).mappings().first()

            if not row:
                QMessageBox.warning(self, "Edit User", "User no longer exists.")
                return

            dialog = UserEditDialog(self, user_item=dict(row), roles=self.roles_list)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            data = dialog.get_data()
            actor = self.current_user.username if self.current_user else "anonymous"

            sql_parts = [
                "full_name = :full_name",
                "role_id = :role_id",
                "is_active = :is_active"
            ]

            if "password_hash" in data:
                sql_parts.append("password_hash = :password_hash")

            sql = f"""
                UPDATE users
                SET {", ".join(sql_parts)}
                WHERE id = :id;
            """

            with engine.begin() as connection:
                connection.execute(text(sql), data)

                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_audit_logs (username, action_type, table_name, record_id, old_values, new_values, note)
                        VALUES (:username, 'UPDATE', 'users', :record, :old, :new, 'Updated user settings.');
                        """
                    ),
                    {
                        "username": actor,
                        "record": data["username"],
                        "old": f"Full Name: {row['full_name']}, Role ID: {row['role_id']}, Active: {row['is_active']}",
                        "new": f"Full Name: {data['full_name']}, Role ID: {data['role_id']}, Active: {data['is_active']}, PassChanged: {'password_hash' in data}"
                    }
                )

            QMessageBox.information(self, "Success", "User details updated successfully.")
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Error Updating User", f"Failed to update user: {exc}")
