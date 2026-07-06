from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "login"


def asset_path(name: str) -> str:
    return str(ASSET_DIR / name)


class BackgroundWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.bg = QPixmap(asset_path("login_bg.png"))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(), QColor("#071a34"))

        if self.bg.isNull():
            return

        target = self.rect()
        scaled = self.bg.scaled(
            target.size(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )

        sx = max(0, (scaled.width() - target.width()) // 2)
        sy = max(0, (scaled.height() - target.height()) // 2)

        painter.drawPixmap(
            target,
            scaled,
            QRect(sx, sy, target.width(), target.height()),
        )


class LoginDialog(QDialog):
    DEFAULT_ROLE = "User"
    DEFAULT_PASSWORD_NOTE = "Temporary open login"

    def __init__(self, parent=None):
        super().__init__(parent)

        self.current_user = None

        self.setWindowTitle("LAUGFS Industrial Tyres Planning UI")
        self.setFixedSize(1366, 768)

        icon_file = asset_path("app_icon.ico")
        if Path(icon_file).exists():
            self.setWindowIcon(QIcon(icon_file))

        self.background = BackgroundWidget(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.background)

        self._build_login_card()

    def _build_login_card(self):
        self.card = QFrame(self.background)
        self.card.setGeometry(840, 118, 420, 520)
        self.card.setObjectName("PremiumLoginCard")
        self.card.setStyleSheet(
            """
            QFrame#PremiumLoginCard {
                background: rgba(255, 255, 255, 248);
                border: 1px solid rgba(217, 226, 240, 230);
                border-radius: 28px;
            }
            """
        )

        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(52)
        shadow.setOffset(0, 20)
        shadow.setColor(QColor(2, 20, 48, 72))
        self.card.setGraphicsEffect(shadow)

        top_line = QFrame(self.card)
        top_line.setGeometry(54, 28, 312, 4)
        top_line.setStyleSheet(
            """
            QFrame {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f5a623,
                    stop:0.45 #2563eb,
                    stop:1 #0b1b3a
                );
                border-radius: 2px;
            }
            """
        )

        badge = QLabel("A", self.card)
        badge.setGeometry(174, 58, 72, 72)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            """
            QLabel {
                background: #eef4ff;
                color: #1458e5;
                border: 1px solid #dbe8ff;
                border-radius: 36px;
                font-family: "Segoe UI";
                font-size: 30px;
                font-weight: 950;
            }
            """
        )

        title = QLabel("Welcome Back!", self.card)
        title.setGeometry(40, 148, 340, 42)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            """
            QLabel {
                color: #071a34;
                font-family: "Segoe UI";
                font-size: 30px;
                font-weight: 950;
                background: transparent;
                letter-spacing: -0.5px;
            }
            """
        )

        subtitle = QLabel("Sign in to access the planning system", self.card)
        subtitle.setGeometry(40, 190, 340, 24)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(
            """
            QLabel {
                color: #64748b;
                font-family: "Segoe UI";
                font-size: 13.5px;
                font-weight: 560;
                background: transparent;
            }
            """
        )

        admin_pill = QLabel("PLANNING SYSTEM ACCESS", self.card)
        admin_pill.setGeometry(112, 226, 196, 30)
        admin_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        admin_pill.setStyleSheet(
            """
            QLabel {
                background: #f1f6ff;
                color: #1458e5;
                border: 1px solid #dbe8ff;
                border-radius: 15px;
                font-family: "Segoe UI";
                font-size: 11px;
                font-weight: 900;
                letter-spacing: 1px;
            }
            """
        )

        self.username_input = QLineEdit(self.card)
        self.username_input.setGeometry(42, 286, 336, 52)
        self.username_input.setPlaceholderText("Username")
        # username intentionally left blank
        self.username_input.setStyleSheet(self._input_css())

        self.password_input = QLineEdit(self.card)
        self.password_input.setGeometry(42, 352, 336, 52)
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setStyleSheet(self._input_css())

        self.remember_check = QCheckBox("Remember me", self.card)
        self.remember_check.setGeometry(42, 418, 150, 28)
        self.remember_check.setStyleSheet(
            """
            QCheckBox {
                color: #52627a;
                font-family: "Segoe UI";
                font-size: 13px;
                font-weight: 600;
                background: transparent;
            }

            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #c6d2e3;
                border-radius: 4px;
                background: white;
            }

            QCheckBox::indicator:checked {
                background: #1458e5;
                border: 1px solid #1458e5;
            }
            """
        )

        forgot = QPushButton("Forgot password?", self.card)
        forgot.setGeometry(244, 416, 138, 30)
        forgot.setCursor(Qt.CursorShape.PointingHandCursor)
        forgot.setFlat(True)
        forgot.setStyleSheet(
            """
            QPushButton {
                color: #1458e5;
                border: none;
                background: transparent;
                font-family: "Segoe UI";
                font-size: 13px;
                font-weight: 800;
                text-align: right;
            }

            QPushButton:hover {
                color: #0b43b5;
                text-decoration: underline;
            }
            """
        )

        self.login_button = QPushButton("Sign In", self.card)
        self.login_button.setGeometry(42, 462, 336, 52)
        self.login_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.login_button.setStyleSheet(
            """
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #1458e5,
                    stop:1 #2563eb
                );
                color: white;
                border: none;
                border-radius: 14px;
                font-family: "Segoe UI";
                font-size: 15px;
                font-weight: 950;
            }

            QPushButton:hover {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0f45bd,
                    stop:1 #1d4ed8
                );
            }

            QPushButton:pressed {
                background: #0b43b5;
            }
            """
        )

        self.login_button.clicked.connect(self._login)
        self.username_input.returnPressed.connect(self.password_input.setFocus)
        self.password_input.returnPressed.connect(self._login)

        self.password_input.setFocus()

    def _input_css(self) -> str:
        return """
            QLineEdit {
                background: #ffffff;
                color: #071a34;
                border: 1px solid #d5deeb;
                border-radius: 14px;
                padding-left: 18px;
                padding-right: 18px;
                font-family: "Segoe UI";
                font-size: 14px;
                font-weight: 650;
            }

            QLineEdit:focus {
                border: 2px solid #1458e5;
                background: #ffffff;
            }

            QLineEdit::placeholder {
                color: #94a3b8;
            }
        """

    def _login(self):
        username = self.username_input.text().strip()
        password = self.password_input.text()

        if not username:
            QMessageBox.warning(self, "Login Failed", "Please enter your username.")
            self.username_input.setFocus()
            return

        if not password:
            QMessageBox.warning(self, "Login Failed", "Please enter your password.")
            self.password_input.setFocus()
            return

        self.current_user = self._build_user(username)
        self.accept()

    def _build_user(self, username: str):
        # Temporary login mode:
        # Any non-empty username/password can enter.
        # Real users and roles can be connected later from the Admin page.
        default_role = SimpleNamespace(
            id=1,
            role_id=1,
            role_name="Admin",
        )

        display_name = username.strip().title()

        return SimpleNamespace(
            id=1,
            username=username,
            full_name=display_name,
            display_name=display_name,
            email="",
            role=default_role,
            role_id=1,
            role_name="Admin",
        )

