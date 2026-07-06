from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QGraphicsDropShadowEffect,
    QTabWidget,
    QTextEdit,
)
from sqlalchemy import text

from app.database import engine
from app.services.auth_service import hash_password


class UserEditDialog(QDialog):
    def __init__(self, parent=None, user_item: dict | None = None, roles: list[dict] | None = None):
        super().__init__(parent)

        self.user_item = user_item or {}
        self.roles = roles or []
        self.is_new = user_item is None

        self.setWindowTitle("Create User Account" if self.is_new else "Edit User Account")
        self.setMinimumWidth(520)

        self.full_name_input = QLineEdit()
        self.full_name_input.setPlaceholderText("Full name")

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")

        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText(
            "Password" if self.is_new else "Leave blank to keep current password"
        )

        self.role_combo = QComboBox()
        for role in self.roles:
            self.role_combo.addItem(role["role_name"], role["id"])

        self.active_checkbox = QCheckBox("Allow this user to login")
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
            QDialog {
                background: #f4f7fb;
                font-family: "Segoe UI";
            }

            QFrame#Card {
                background: #ffffff;
                border: 1px solid #dfe7f3;
                border-radius: 18px;
            }

            QLabel#Title {
                color: #071a34;
                font-size: 18pt;
                font-weight: 950;
            }

            QLabel#Hint {
                color: #64748b;
                font-size: 10pt;
                font-weight: 550;
            }

            QLabel#FieldLabel {
                color: #334155;
                font-size: 9.5pt;
                font-weight: 800;
            }

            QLineEdit, QComboBox {
                min-height: 38px;
                background: #ffffff;
                color: #071a34;
                border: 1px solid #cfd9e8;
                border-radius: 10px;
                padding-left: 12px;
                padding-right: 12px;
                font-size: 10pt;
                font-weight: 600;
            }

            QLineEdit:focus, QComboBox:focus {
                border: 2px solid #1d4ed8;
            }

            QCheckBox {
                color: #475569;
                font-size: 10pt;
                font-weight: 650;
            }

            QPushButton#PrimaryButton {
                min-height: 38px;
                min-width: 120px;
                background: #165ee6;
                color: white;
                border: none;
                border-radius: 10px;
                font-weight: 900;
            }

            QPushButton#PrimaryButton:hover {
                background: #0f50d4;
            }

            QPushButton#SecondaryButton {
                min-height: 38px;
                min-width: 100px;
                background: #f8fafc;
                color: #0f172a;
                border: 1px solid #cfd9e8;
                border-radius: 10px;
                font-weight: 800;
            }

            QPushButton#SecondaryButton:hover {
                background: #eef4ff;
                border: 1px solid #93c5fd;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)

        card = QFrame()
        card.setObjectName("Card")

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(15, 23, 42, 28))
        card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel("User Account Details")
        title.setObjectName("Title")

        hint = QLabel("Create or update login credentials, account status and role access.")
        hint.setObjectName("Hint")

        layout.addWidget(title)
        layout.addWidget(hint)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        labels = [
            ("Full Name", self.full_name_input),
            ("Username", self.username_input),
            ("Password", self.password_input),
            ("Security Role", self.role_combo),
        ]

        for row, (label_text, field) in enumerate(labels):
            label = QLabel(label_text)
            label.setObjectName("FieldLabel")
            form.addWidget(label, row, 0)
            form.addWidget(field, row, 1)

        layout.addLayout(form)
        layout.addWidget(self.active_checkbox)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        root.addWidget(card)

    def _load_data(self) -> None:
        if self.is_new:
            return

        self.full_name_input.setText(str(self.user_item.get("full_name") or ""))
        self.username_input.setText(str(self.user_item.get("username") or ""))
        self.username_input.setReadOnly(True)
        self.active_checkbox.setChecked(bool(self.user_item.get("is_active")))

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
            raise ValueError("Full name is required.")

        if not username:
            raise ValueError("Username is required.")

        if self.is_new and not password:
            raise ValueError("Password is required for new users.")

        if role_id is None:
            raise ValueError("Security role is required.")

        data = {
            "id": self.user_item.get("id"),
            "full_name": full_name,
            "username": username,
            "role_id": role_id,
            "is_active": self.active_checkbox.isChecked(),
        }

        if password:
            data["password_hash"] = hash_password(password)

        return data


class UserDetailsDialog(QDialog):
    def __init__(self, parent=None, user_id: int | None = None):
        super().__init__(parent)

        self.user_id = user_id
        self.user_data: dict = {}
        self.audit_rows: list[dict] = []

        self.setWindowTitle("User Details")
        self.setMinimumSize(760, 620)

        self._apply_styles()
        self._load_data()
        self._build_ui()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #f4f7fb;
                font-family: "Segoe UI";
            }

            QFrame#HeroCard,
            QFrame#InfoCard {
                background: #ffffff;
                border: 1px solid #dfe7f3;
                border-radius: 18px;
            }

            QLabel#Title {
                color: #071a34;
                font-size: 22pt;
                font-weight: 950;
            }

            QLabel#Subtitle {
                color: #64748b;
                font-size: 10.5pt;
                font-weight: 600;
            }

            QLabel#Badge {
                background: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 14px;
                padding: 7px 14px;
                font-weight: 900;
            }

            QLabel#FieldName {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 800;
            }

            QLabel#FieldValue {
                color: #071a34;
                font-size: 11pt;
                font-weight: 800;
            }

            QTabWidget::pane {
                border: 1px solid #dfe7f3;
                border-radius: 14px;
                background: #ffffff;
            }

            QTabBar::tab {
                background: #f8fafc;
                color: #334155;
                padding: 10px 18px;
                border: 1px solid #dfe7f3;
                border-bottom: none;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
                font-weight: 850;
            }

            QTabBar::tab:selected {
                background: #ffffff;
                color: #1d4ed8;
            }

            QTableWidget {
                background: #ffffff;
                alternate-background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                gridline-color: #e5edf6;
                color: #0f172a;
                font-size: 10pt;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }

            QHeaderView::section {
                background: #f1f5f9;
                color: #334155;
                border: none;
                border-right: 1px solid #e2e8f0;
                border-bottom: 1px solid #e2e8f0;
                padding: 9px 8px;
                font-weight: 900;
            }

            QTextEdit {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                padding: 10px;
                font-size: 10pt;
            }

            QPushButton {
                min-height: 38px;
                padding-left: 16px;
                padding-right: 16px;
                background: #165ee6;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 9.5pt;
                font-weight: 900;
            }

            QPushButton:hover {
                background: #0f50d4;
            }
            """
        )

    def _load_data(self) -> None:
        if self.user_id is None:
            return

        try:
            with engine.begin() as connection:
                row = connection.execute(
                    text(
                        """
                        SELECT
                            u.*,
                            r.role_name
                        FROM users u
                        LEFT JOIN roles r ON u.role_id = r.id
                        WHERE u.id = :id;
                        """
                    ),
                    {"id": self.user_id},
                ).mappings().first()

                if row:
                    self.user_data = dict(row)

                try:
                    logs = connection.execute(
                        text(
                            """
                            SELECT
                                id,
                                username,
                                action_type,
                                table_name,
                                record_id,
                                old_values,
                                new_values,
                                note,
                                created_at
                            FROM mpps_audit_logs
                            WHERE record_id = :username
                               OR username = :username
                            ORDER BY created_at DESC
                            LIMIT 20;
                            """
                        ),
                        {"username": self.user_data.get("username", "")},
                    ).mappings().all()

                    self.audit_rows = [dict(item) for item in logs]
                except Exception:
                    self.audit_rows = []

        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Failed to load user details:\n{exc}")

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(16)

        hero = QFrame()
        hero.setObjectName("HeroCard")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(22, 18, 22, 18)

        name = str(self.user_data.get("full_name") or "-")
        username = str(self.user_data.get("username") or "-")
        role = str(self.user_data.get("role_name") or "-")
        status = "Active" if self.user_data.get("is_active") else "Inactive"

        title_box = QVBoxLayout()
        title_box.setSpacing(4)

        title = QLabel(name)
        title.setObjectName("Title")

        subtitle = QLabel(f"Username: {username}   ?   Role: {role}")
        subtitle.setObjectName("Subtitle")

        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        badge = QLabel(status)
        badge.setObjectName("Badge")

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.accept)

        hero_layout.addLayout(title_box, 1)
        hero_layout.addWidget(badge)
        hero_layout.addWidget(close_btn)

        root.addWidget(hero)

        tabs = QTabWidget()

        overview_tab = QWidget()
        overview_layout = QVBoxLayout(overview_tab)
        overview_layout.setContentsMargins(16, 16, 16, 16)
        overview_layout.setSpacing(14)

        overview_grid = QGridLayout()
        overview_grid.setHorizontalSpacing(16)
        overview_grid.setVerticalSpacing(14)

        overview_items = [
            ("User ID", self.user_data.get("id", "-")),
            ("Full Name", self.user_data.get("full_name", "-")),
            ("Username", self.user_data.get("username", "-")),
            ("Security Role", self.user_data.get("role_name", "-")),
            ("Role ID", self.user_data.get("role_id", "-")),
            ("Status", status),
            ("Created At", self._fmt(self.user_data.get("created_at"))),
            ("Password Hash", "Stored securely" if self.user_data.get("password_hash") else "-"),
        ]

        for index, (label, value) in enumerate(overview_items):
            card = self._info_card(str(label), str(value))
            overview_grid.addWidget(card, index // 2, index % 2)

        overview_layout.addLayout(overview_grid)
        overview_layout.addStretch()

        raw_tab = QWidget()
        raw_layout = QVBoxLayout(raw_tab)
        raw_layout.setContentsMargins(16, 16, 16, 16)

        raw_table = QTableWidget(0, 2)
        raw_table.setHorizontalHeaderLabels(["Field", "Value"])
        raw_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        raw_table.verticalHeader().setVisible(False)
        raw_table.setAlternatingRowColors(True)

        for key, value in self.user_data.items():
            row = raw_table.rowCount()
            raw_table.insertRow(row)
            raw_table.setItem(row, 0, QTableWidgetItem(str(key)))
            raw_table.setItem(row, 1, QTableWidgetItem(self._fmt(value)))

        raw_layout.addWidget(raw_table)

        audit_tab = QWidget()
        audit_layout = QVBoxLayout(audit_tab)
        audit_layout.setContentsMargins(16, 16, 16, 16)

        audit_table = QTableWidget(0, 6)
        audit_table.setHorizontalHeaderLabels(["Time", "Actor", "Action", "Table", "Record", "Note"])
        audit_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        audit_table.verticalHeader().setVisible(False)
        audit_table.setAlternatingRowColors(True)

        for item in self.audit_rows:
            row = audit_table.rowCount()
            audit_table.insertRow(row)

            values = [
                self._fmt(item.get("created_at")),
                item.get("username", ""),
                item.get("action_type", ""),
                item.get("table_name", ""),
                item.get("record_id", ""),
                item.get("note", ""),
            ]

            for col, value in enumerate(values):
                audit_table.setItem(row, col, QTableWidgetItem(str(value)))

        audit_layout.addWidget(audit_table)

        tabs.addTab(overview_tab, "Overview")
        tabs.addTab(raw_tab, "Database Fields")
        tabs.addTab(audit_tab, "Audit Logs")

        root.addWidget(tabs, 1)

    def _info_card(self, label: str, value: str) -> QFrame:
        card = QFrame()
        card.setObjectName("InfoCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)

        name = QLabel(label)
        name.setObjectName("FieldName")

        val = QLabel(value)
        val.setObjectName("FieldValue")
        val.setWordWrap(True)

        layout.addWidget(name)
        layout.addWidget(val)

        return card

    def _fmt(self, value) -> str:
        if value is None:
            return "-"

        if hasattr(value, "strftime"):
            return value.strftime("%Y-%m-%d %H:%M:%S")

        return str(value)





class UsersRolesPage(QWidget):
    def __init__(self, current_user=None):
        super().__init__()

        self.current_user = current_user
        self.selected_user_id: int | None = None
        self.roles_list: list[dict] = []
        self.all_users: list[dict] = []

        self.title = QLabel("System Users & Roles")
        self.title.setObjectName("PageTitle")

        self.subtitle = QLabel("Manage user accounts, role assignments and system login access.")
        self.subtitle.setObjectName("PageSubtitle")

        self.admin_badge = QLabel("")
        self.admin_badge.setObjectName("AdminBadge")

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search users by name, username or role...")
        self.search_input.textChanged.connect(self.apply_filter)

        self.add_btn = QPushButton("+ Create User")
        self.add_btn.setObjectName("PrimaryButton")
        self.add_btn.clicked.connect(self.add_user)

        self.edit_btn = QPushButton("Edit Selected")
        self.edit_btn.setObjectName("SecondaryButton")
        self.edit_btn.setEnabled(False)
        self.edit_btn.clicked.connect(self.edit_selected_user)

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setObjectName("SecondaryButton")
        self.refresh_btn.clicked.connect(self.refresh)

        self.total_value = QLabel("0")
        self.active_value = QLabel("0")
        self.inactive_value = QLabel("0")
        self.roles_value = QLabel("0")

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["ID", "Full Name", "Username", "Security Role", "Status", "Created At"]
        )

        self._apply_styles()
        self._setup_table()
        self._build_ui()
        self.refresh()

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                font-family: "Segoe UI";
            }

            QLabel#PageTitle {
                color: #071a34;
                font-size: 22pt;
                font-weight: 950;
            }

            QLabel#PageSubtitle {
                color: #64748b;
                font-size: 10.5pt;
                font-weight: 550;
            }

            QFrame#HeroCard,
            QFrame#StatsCard,
            QFrame#TableCard {
                background: #ffffff;
                border: 1px solid #dfe7f3;
                border-radius: 18px;
            }

            QLabel#AdminBadge {
                background: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 14px;
                padding: 8px 16px;
                font-size: 10pt;
                font-weight: 900;
            }

            QLabel#StatValue {
                color: #071a34;
                font-size: 22pt;
                font-weight: 950;
            }

            QLabel#StatLabel {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 750;
            }

            QLabel#SectionTitle {
                color: #071a34;
                font-size: 16pt;
                font-weight: 950;
            }

            QLineEdit {
                min-height: 38px;
                background: #ffffff;
                color: #071a34;
                border: 1px solid #cfd9e8;
                border-radius: 12px;
                padding-left: 14px;
                padding-right: 14px;
                font-size: 10pt;
                font-weight: 600;
            }

            QLineEdit:focus {
                border: 2px solid #1d4ed8;
            }

            QPushButton#PrimaryButton {
                min-height: 38px;
                padding-left: 16px;
                padding-right: 16px;
                background: #165ee6;
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 9.5pt;
                font-weight: 900;
            }

            QPushButton#PrimaryButton:hover {
                background: #0f50d4;
            }

            QPushButton#PrimaryButton:disabled {
                background: #94a3b8;
                color: #f8fafc;
            }

            QPushButton#SecondaryButton {
                min-height: 38px;
                padding-left: 14px;
                padding-right: 14px;
                background: #f8fafc;
                color: #0f172a;
                border: 1px solid #cfd9e8;
                border-radius: 10px;
                font-size: 9.5pt;
                font-weight: 850;
            }

            QPushButton#SecondaryButton:hover {
                background: #eef4ff;
                border: 1px solid #93c5fd;
            }

            QPushButton#SecondaryButton:disabled {
                color: #94a3b8;
                background: #f1f5f9;
            }

            QTableWidget {
                background: #ffffff;
                alternate-background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                gridline-color: #e5edf6;
                color: #0f172a;
                font-size: 10pt;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }

            QHeaderView::section {
                background: #f1f5f9;
                color: #334155;
                border: none;
                border-right: 1px solid #e2e8f0;
                border-bottom: 1px solid #e2e8f0;
                padding: 9px 8px;
                font-weight: 900;
            }

            QTableWidget::item {
                padding: 7px;
                border-bottom: 1px solid #eef2f7;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        hero_card = QFrame()
        hero_card.setObjectName("HeroCard")
        hero_layout = QHBoxLayout(hero_card)
        hero_layout.setContentsMargins(22, 18, 22, 18)
        hero_layout.setSpacing(16)

        title_box = QVBoxLayout()
        title_box.setSpacing(4)
        title_box.addWidget(self.title)
        title_box.addWidget(self.subtitle)

        hero_layout.addLayout(title_box, 1)
        hero_layout.addWidget(self.admin_badge)
        hero_layout.addWidget(self.add_btn)
        hero_layout.addWidget(self.edit_btn)
        hero_layout.addWidget(self.refresh_btn)

        root.addWidget(hero_card)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(14)

        stats_row.addWidget(self._stat_card("Total Users", self.total_value, "#eff6ff"))
        stats_row.addWidget(self._stat_card("Active Users", self.active_value, "#ecfdf5"))
        stats_row.addWidget(self._stat_card("Inactive Users", self.inactive_value, "#fff7ed"))
        stats_row.addWidget(self._stat_card("Security Roles", self.roles_value, "#f5f3ff"))

        root.addLayout(stats_row)

        table_card = QFrame()
        table_card.setObjectName("TableCard")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(22, 18, 22, 18)
        table_layout.setSpacing(14)

        table_header = QHBoxLayout()
        table_title = QLabel("Registered User Logins")
        table_title.setObjectName("SectionTitle")

        table_header.addWidget(table_title)
        table_header.addStretch()
        table_header.addWidget(self.search_input, 0)

        table_layout.addLayout(table_header)
        table_layout.addWidget(self.table, 1)

        root.addWidget(table_card, 1)

    def _stat_card(self, label_text: str, value_label: QLabel, bg: str) -> QFrame:
        card = QFrame()
        card.setObjectName("StatsCard")
        card.setStyleSheet(
            f"""
            QFrame#StatsCard {{
                background: {bg};
                border: 1px solid #dfe7f3;
                border-radius: 16px;
            }}
            """
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(2)

        value_label.setObjectName("StatValue")

        label = QLabel(label_text)
        label.setObjectName("StatLabel")

        layout.addWidget(value_label)
        layout.addWidget(label)

        return card

    def _setup_table(self) -> None:
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 70)
        self.table.setColumnWidth(2, 150)
        self.table.setColumnWidth(4, 110)
        self.table.setColumnWidth(5, 180)

        self.table.itemSelectionChanged.connect(self.on_selection_changed)
        self.table.itemClicked.connect(self.on_table_item_clicked)
        self.table.itemDoubleClicked.connect(self.edit_selected_user)

    def is_admin(self) -> bool:
        if self.current_user is None:
            return True

        if getattr(self.current_user, "role", None) is None:
            return False

        return self.current_user.role.role_name == "Admin"

    def refresh(self) -> None:
        if self.is_admin():
            self.admin_badge.setText("Authorized: Admin")
            self.admin_badge.setStyleSheet(
                "background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;border-radius:14px;padding:8px 16px;font-weight:900;"
            )
            self.add_btn.setEnabled(True)
        else:
            self.admin_badge.setText("Read Only")
            self.admin_badge.setStyleSheet(
                "background:#fef3c7;color:#d97706;border:1px solid #fde68a;border-radius:14px;padding:8px 16px;font-weight:900;"
            )
            self.add_btn.setEnabled(False)

        self.load_roles()
        self.load_users()
        self.apply_filter()

    def load_roles(self) -> None:
        self.roles_list.clear()

        try:
            with engine.begin() as connection:
                rows = connection.execute(
                    text("SELECT id, role_name FROM roles ORDER BY id ASC;")
                ).mappings().all()

            self.roles_list = [dict(row) for row in rows]

        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Failed to load roles:\n{exc}")

    def load_users(self) -> None:
        sql = """
            SELECT
                u.id,
                u.full_name,
                u.username,
                u.role_id,
                r.role_name,
                u.is_active,
                u.created_at
            FROM users u
            JOIN roles r ON u.role_id = r.id
            ORDER BY u.id ASC;
        """

        try:
            with engine.begin() as connection:
                rows = connection.execute(text(sql)).mappings().all()

            self.all_users = [dict(row) for row in rows]
            self._update_stats()

        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Failed to load users:\n{exc}")

    def _update_stats(self) -> None:
        total = len(self.all_users)
        active = sum(1 for user in self.all_users if user.get("is_active"))
        inactive = total - active

        self.total_value.setText(str(total))
        self.active_value.setText(str(active))
        self.inactive_value.setText(str(inactive))
        self.roles_value.setText(str(len(self.roles_list)))

    def apply_filter(self) -> None:
        keyword = self.search_input.text().strip().lower()

        if not keyword:
            users = self.all_users
        else:
            users = [
                user for user in self.all_users
                if keyword in str(user.get("full_name", "")).lower()
                or keyword in str(user.get("username", "")).lower()
                or keyword in str(user.get("role_name", "")).lower()
            ]

        self._populate_table(users)

    def _populate_table(self, users: list[dict]) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        self.selected_user_id = None
        self.edit_btn.setEnabled(False)

        for row_idx, row in enumerate(users):
            self.table.insertRow(row_idx)

            created_at = row.get("created_at")
            created_str = created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else "-"

            values = [
                str(row.get("id", "")),
                str(row.get("full_name", "")),
                str(row.get("username", "")),
                str(row.get("role_name", "")),
                "Active" if row.get("is_active") else "Inactive",
                created_str,
            ]

            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                if col_idx in (0, 2, 4, 5):
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if col_idx == 0:
                    item.setData(Qt.ItemDataRole.UserRole, int(row["id"]))

                if col_idx == 4:
                    if value == "Active":
                        item.setForeground(QColor("#047857"))
                        item.setFont(self._bold_font())
                    else:
                        item.setForeground(QColor("#b45309"))
                        item.setFont(self._bold_font())

                self.table.setItem(row_idx, col_idx, item)

        self.table.resizeRowsToContents()
        self.table.setSortingEnabled(True)

    def _bold_font(self) -> QFont:
        font = QFont("Segoe UI")
        font.setBold(True)
        return font

    def on_table_item_clicked(self, item) -> None:
        if item is None:
            return

        # Username column click opens the full user details page.
        if item.column() != 2:
            return

        row = item.row()
        id_item = self.table.item(row, 0)

        if id_item is None:
            return

        user_id = id_item.data(Qt.ItemDataRole.UserRole)

        if user_id is None:
            return

        dialog = UserDetailsDialog(self, user_id=int(user_id))
        dialog.exec()


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
            self.edit_btn.setEnabled(self.is_admin())

    def add_user(self) -> None:
        if not self.is_admin():
            QMessageBox.warning(self, "Permission Denied", "Only administrators can create users.")
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
                        INSERT INTO users
                            (full_name, username, password_hash, role_id, is_active, created_at)
                        VALUES
                            (:full_name, :username, :password_hash, :role_id, :is_active, CURRENT_TIMESTAMP);
                        """
                    ),
                    data,
                )

                connection.execute(
                    text(
                        """
                        INSERT INTO mpps_audit_logs
                            (username, action_type, table_name, record_id, new_values, note)
                        VALUES
                            (:username, 'INSERT', 'users', :record, :val, 'Created new user account.');
                        """
                    ),
                    {
                        "username": actor,
                        "record": data["username"],
                        "val": f"Full Name: {data['full_name']}, Role ID: {data['role_id']}",
                    },
                )

            QMessageBox.information(self, "User Created", f"User '{data['username']}' created successfully.")
            self.refresh()

        except Exception as exc:
            QMessageBox.critical(self, "Error Saving User", f"Failed to create user:\n{exc}")

    def edit_selected_user(self) -> None:
        if not self.is_admin():
            QMessageBox.warning(self, "Permission Denied", "Only administrators can edit users.")
            return

        if not self.selected_user_id:
            return

        try:
            with engine.begin() as connection:
                row = connection.execute(
                    text("SELECT * FROM users WHERE id = :id;"),
                    {"id": self.selected_user_id},
                ).mappings().first()

            if not row:
                QMessageBox.warning(self, "Edit User", "Selected user no longer exists.")
                return

            dialog = UserEditDialog(self, user_item=dict(row), roles=self.roles_list)

            if dialog.exec() != QDialog.DialogCode.Accepted:
                return

            data = dialog.get_data()
            actor = self.current_user.username if self.current_user else "anonymous"

            sql_parts = [
                "full_name = :full_name",
                "role_id = :role_id",
                "is_active = :is_active",
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
                        INSERT INTO mpps_audit_logs
                            (username, action_type, table_name, record_id, old_values, new_values, note)
                        VALUES
                            (:username, 'UPDATE', 'users', :record, :old, :new, 'Updated user settings.');
                        """
                    ),
                    {
                        "username": actor,
                        "record": data["username"],
                        "old": f"Full Name: {row['full_name']}, Role ID: {row['role_id']}, Active: {row['is_active']}",
                        "new": f"Full Name: {data['full_name']}, Role ID: {data['role_id']}, Active: {data['is_active']}, PassChanged: {'password_hash' in data}",
                    },
                )

            QMessageBox.information(self, "User Updated", "User details updated successfully.")
            self.refresh()

        except Exception as exc:
            QMessageBox.critical(self, "Error Updating User", f"Failed to update user:\n{exc}")
