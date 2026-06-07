from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from app.database import get_session
from app.models import User
from app.services.auth_service import authenticate_user


class LoginWindow(QDialog):
    def __init__(self):
        super().__init__()
        self.current_user: User | None = None
        self.setWindowTitle("Factory Oven Planner Login")
        self.setFixedSize(760, 460)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        hero = QFrame()
        hero.setObjectName("Sidebar")
        hero.setFixedWidth(310)

        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(28, 34, 28, 34)
        hero_layout.setSpacing(14)

        brand = QLabel("Factory Oven\nPlanning System")
        brand.setObjectName("BrandTitle")
        brand.setWordWrap(True)
        hero_layout.addWidget(brand)

        subtitle = QLabel(
            "Professional MPPS and OVEN Excel-derived production planning, "
            "stock, material, capacity, and shipment-risk control."
        )
        subtitle.setObjectName("BrandSubtitle")
        subtitle.setWordWrap(True)
        hero_layout.addWidget(subtitle)

        hero_layout.addStretch()

        pill = QLabel("MPPS Stock | Quantity Capacity | Excel Traceability")
        pill.setObjectName("InfoPill")
        hero_layout.addWidget(pill)

        root.addWidget(hero)

        form_area = QFrame()
        form_area.setObjectName("AppShell")

        form_layout = QVBoxLayout(form_area)
        form_layout.setContentsMargins(38, 38, 38, 38)
        form_layout.setSpacing(18)
        form_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Sign in")
        title.setObjectName("PageTitle")

        subtitle2 = QLabel("Development/demo access for the MPPS production planner.")
        subtitle2.setObjectName("PageSubtitle")

        form_layout.addWidget(title)
        form_layout.addWidget(subtitle2)

        card = QFrame()
        card.setObjectName("PanelCard")

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 22, 22, 22)
        card_layout.setSpacing(14)

        form = QGridLayout()
        form.setVerticalSpacing(12)

        self.username = QLineEdit()
        self.username.setPlaceholderText("manager")
        self.username.setMinimumHeight(38)

        self.password = QLineEdit()
        self.password.setPlaceholderText("manager123")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        self.password.setMinimumHeight(38)

        form.addWidget(QLabel("Username"), 0, 0)
        form.addWidget(self.username, 0, 1)
        form.addWidget(QLabel("Password"), 1, 0)
        form.addWidget(self.password, 1, 1)

        card_layout.addLayout(form)

        hint = QLabel(
            "Demo users: admin/admin123   •   manager/manager123   •   owner/owner123"
        )
        hint.setObjectName("SectionHint")
        hint.setWordWrap(True)
        card_layout.addWidget(hint)

        login_btn = QPushButton("Login to Production Planner")
        login_btn.setObjectName("PrimaryButton")
        login_btn.setMinimumHeight(42)
        login_btn.clicked.connect(self.try_login)
        card_layout.addWidget(login_btn)

        form_layout.addWidget(card)

        root.addWidget(form_area, 1)

        self.username.setText("manager")
        self.password.setText("manager123")

    def try_login(self) -> None:
        username = self.username.text().strip()
        password = self.password.text().strip()

        if not username or not password:
            QMessageBox.warning(self, "Missing Login", "Please enter username and password.")
            return

        user = None

        with get_session() as session:
            user = authenticate_user(session, username, password)

            if user:
                _ = user.role.role_name if user.role else None
                session.expunge(user)

        if user is None:
            QMessageBox.critical(self, "Login Failed", "Invalid username or password.")
            return

        self.current_user = user
        self.accept()
