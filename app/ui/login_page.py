from __future__ import annotations

import hashlib
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)
from sqlalchemy import text

from app.database import engine


class LoginDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.current_user: dict[str, Any] | None = None

        self.setWindowTitle("Factory Production Planner - Login")
        self.setMinimumSize(900, 560)
        self.setModal(True)

        self.setStyleSheet("""
            QDialog {
                background: #eef2f7;
            }

            QFrame#ShellCard {
                background: #ffffff;
                border: 1px solid #dbe5f0;
                border-radius: 26px;
            }

            QFrame#BrandPanel {
                background: #0f172a;
                border-top-left-radius: 24px;
                border-bottom-left-radius: 24px;
            }

            QLabel#BrandTitle {
                color: #ffffff;
                font-size: 25pt;
                font-weight: 950;
            }

            QLabel#BrandSubtitle {
                color: #cbd5e1;
                font-size: 10pt;
                font-weight: 650;
            }

            QLabel#BrandBadge {
                background: rgba(37, 99, 235, 0.22);
                color: #bfdbfe;
                border: 1px solid rgba(147, 197, 253, 0.35);
                border-radius: 13px;
                padding: 8px 12px;
                font-size: 9pt;
                font-weight: 900;
            }

            QLabel#FormTitle {
                color: #0f172a;
                font-size: 22pt;
                font-weight: 950;
            }

            QLabel#FormSubtitle {
                color: #64748b;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLabel#FieldLabel {
                color: #0f172a;
                font-size: 9.5pt;
                font-weight: 850;
            }

            QLabel#FooterText {
                color: #94a3b8;
                font-size: 8.5pt;
                font-weight: 650;
            }

            QLineEdit {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 12px;
                padding: 12px 14px;
                color: #0f172a;
                font-size: 10pt;
                font-weight: 650;
            }

            QLineEdit:focus {
                border: 1px solid #2563eb;
            }

            QPushButton#LoginButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 12px;
                padding: 13px 18px;
                font-size: 10pt;
                font-weight: 950;
            }

            QPushButton#LoginButton:hover {
                background: #1d4ed8;
            }

            QPushButton#CancelButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 12px;
                padding: 13px 18px;
                font-size: 10pt;
                font-weight: 950;
            }

            QPushButton#CancelButton:hover {
                background: #cbd5e1;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(36, 34, 36, 34)
        root.setSpacing(0)

        shell = QFrame()
        shell.setObjectName("ShellCard")

        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        shell_layout.addWidget(self._build_brand_panel(), 1)
        shell_layout.addWidget(self._build_form_panel(), 1)

        root.addWidget(shell)

    def _build_brand_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("BrandPanel")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(38, 42, 38, 42)
        layout.setSpacing(22)

        badge = QLabel("DATABASE SECURED ACCESS")
        badge.setObjectName("BrandBadge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedWidth(230)

        title = QLabel("Factory\nProduction\nPlanner")
        title.setObjectName("BrandTitle")

        subtitle = QLabel(
            "Industrial tyre production planning system for shipment planning, "
            "factory capacity, curing time and daily scheduling."
        )
        subtitle.setObjectName("BrandSubtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignLeft)
        layout.addSpacing(28)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addStretch()

        footer = QLabel("PostgreSQL authentication enabled")
        footer.setObjectName("BrandSubtitle")
        layout.addWidget(footer)

        return panel

    def _build_form_panel(self) -> QFrame:
        panel = QFrame()

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(46, 48, 46, 42)
        layout.setSpacing(18)

        title = QLabel("Sign in")
        title.setObjectName("FormTitle")

        subtitle = QLabel("Use your database user account to continue.")
        subtitle.setObjectName("FormSubtitle")

        username_label = QLabel("Username or Email")
        username_label.setObjectName("FieldLabel")

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username or email")

        password_label = QLabel("Password")
        password_label.setObjectName("FieldLabel")

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.returnPressed.connect(self._login)

        button_row = QHBoxLayout()
        button_row.setSpacing(12)

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("CancelButton")
        cancel_button.clicked.connect(self.reject)

        login_button = QPushButton("Login")
        login_button.setObjectName("LoginButton")
        login_button.clicked.connect(self._login)

        button_row.addWidget(cancel_button)
        button_row.addWidget(login_button)

        footer = QLabel("Authenticated against app_auth_users table in PostgreSQL.")
        footer.setObjectName("FooterText")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(12)
        layout.addWidget(username_label)
        layout.addWidget(self.username_input)
        layout.addWidget(password_label)
        layout.addWidget(self.password_input)
        layout.addSpacing(8)
        layout.addLayout(button_row)
        layout.addStretch()
        layout.addWidget(footer)

        return panel

    def _login(self) -> None:
        identity = self.username_input.text().strip()
        password = self.password_input.text()

        if not identity or not password:
            QMessageBox.warning(self, "Missing Login Details", "Please enter username and password.")
            return

        try:
            user = self._authenticate(identity, password)
        except Exception as exc:
            QMessageBox.critical(self, "Login Error", f"Could not validate login.\n\n{exc}")
            return

        if not user:
            QMessageBox.warning(self, "Login Failed", "Invalid username or password.")
            self.password_input.clear()
            self.password_input.setFocus()
            return

        self.current_user = user
        self.accept()

    def _authenticate(self, identity: str, password: str) -> dict[str, Any] | None:
        self._ensure_auth_table()

        with engine.connect() as conn:
            row = conn.execute(
                text("""
                    SELECT
                        id,
                        username,
                        email,
                        display_name,
                        password_hash,
                        role_name,
                        is_active
                    FROM app_auth_users
                    WHERE LOWER(username) = LOWER(:identity)
                       OR LOWER(email) = LOWER(:identity)
                    LIMIT 1
                """),
                {"identity": identity},
            ).mappings().first()

        if not row:
            return None

        data = dict(row)

        if not data.get("is_active", False):
            return None

        stored_hash = str(data.get("password_hash") or "")

        if not self._verify_password(password, stored_hash):
            return None

        return {
            "id": data.get("id"),
            "username": data.get("username"),
            "email": data.get("email"),
            "display_name": data.get("display_name"),
            "role_name": data.get("role_name"),
        }

    def _ensure_auth_table(self) -> None:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS app_auth_users (
                    id BIGSERIAL PRIMARY KEY,
                    username VARCHAR(128) NOT NULL UNIQUE,
                    email VARCHAR(255) NOT NULL DEFAULT '',
                    display_name VARCHAR(255) NOT NULL DEFAULT '',
                    password_hash TEXT NOT NULL,
                    role_name VARCHAR(80) NOT NULL DEFAULT 'Operation Manager',
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

    def _verify_password(self, plain_password: str, stored_hash: str) -> bool:
        if not stored_hash:
            return False

        if stored_hash.startswith("pbkdf2_sha256$"):
            try:
                _, iterations_text, salt, expected = stored_hash.split("$", 3)
                iterations = int(iterations_text)
                actual = hashlib.pbkdf2_hmac(
                    "sha256",
                    plain_password.encode("utf-8"),
                    salt.encode("utf-8"),
                    iterations,
                ).hex()
                return actual == expected
            except Exception:
                return False

        if hashlib.sha256(plain_password.encode("utf-8")).hexdigest() == stored_hash:
            return True

        return plain_password == stored_hash
