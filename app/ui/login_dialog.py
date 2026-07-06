from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)


class LoginDialog(QDialog):
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "admin123"

    def __init__(self, parent=None):
        super().__init__(parent)

        self.current_user = None

        self.setWindowTitle("Admin Login")
        self.setFixedWidth(430)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self.setStyleSheet(
            """
            QDialog {
                background: #f3f6fb;
                font-family: "Segoe UI";
            }

            QFrame#LoginCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 18px;
            }

            QLabel#Title {
                color: #0f172a;
                font-size: 21pt;
                font-weight: 900;
            }

            QLabel#Subtitle {
                color: #64748b;
                font-size: 10pt;
                font-weight: 650;
            }

            QLabel#FieldLabel {
                color: #334155;
                font-size: 9pt;
                font-weight: 800;
            }

            QLineEdit {
                min-height: 40px;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 6px 11px;
                color: #0f172a;
                background: #ffffff;
                font-size: 10pt;
            }

            QLineEdit:focus {
                border: 1px solid #2563eb;
            }

            QPushButton#LoginButton {
                min-height: 44px;
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 11px;
                font-size: 10pt;
                font-weight: 900;
            }

            QPushButton#LoginButton:hover {
                background: #1d4ed8;
            }

            QLabel#Hint {
                color: #64748b;
                font-size: 8.5pt;
                font-weight: 650;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("LoginCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(30, 28, 30, 28)
        layout.setSpacing(12)

        title = QLabel("Admin Login")
        title.setObjectName("Title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Factory Oven Production Planning System")
        subtitle.setObjectName("Subtitle")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        username_label = QLabel("Username")
        username_label.setObjectName("FieldLabel")

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username")
        self.username_input.setText("admin")

        password_label = QLabel("Password")
        password_label.setObjectName("FieldLabel")

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)

        self.login_button = QPushButton("Login")
        self.login_button.setObjectName("LoginButton")
        self.login_button.setCursor(Qt.CursorShape.PointingHandCursor)

        hint = QLabel("Default admin: admin / admin123")
        hint.setObjectName("Hint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(16)
        layout.addWidget(username_label)
        layout.addWidget(self.username_input)
        layout.addWidget(password_label)
        layout.addWidget(self.password_input)
        layout.addSpacing(10)
        layout.addWidget(self.login_button)
        layout.addWidget(hint)

        root.addWidget(card)

        self.login_button.clicked.connect(self._login)
        self.username_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self._login)

        self.password_input.setFocus()

    def _login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if username == self.ADMIN_USERNAME and password == self.ADMIN_PASSWORD:
            self.current_user = self._build_admin_user()
            self.accept()
            return

        QMessageBox.warning(
            self,
            "Login Failed",
            "Invalid username or password.",
        )
        self.password_input.clear()
        self.password_input.setFocus()

    def _build_admin_user(self):
        admin_role = SimpleNamespace(
            id=1,
            role_id=1,
            role_name="Admin",
        )

        return SimpleNamespace(
            id=1,
            username="admin",
            full_name="Admin User",
            display_name="Admin User",
            email="",
            role=admin_role,
            role_id=1,
            role_name="Admin",
        )
