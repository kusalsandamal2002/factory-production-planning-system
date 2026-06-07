from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from app.database import get_session, init_database
from app.seed_data import seed_database
from app.ui.login_window import LoginWindow
from app.ui.main_window import MainWindow
from app.ui.styles import APP_STYLESHEET


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)

    try:
        init_database()
        with get_session() as session:
            seed_database(session)
    except Exception as exc:
        QMessageBox.critical(
            None,
            "Database Connection Error",
            "Could not connect to PostgreSQL database.\n\n"
            "Please check that PostgreSQL is running and that .env DATABASE_URL has the correct port, username, password and database name.\n\n"
            f"Error: {exc}",
        )
        return 1

    login = LoginWindow()
    if login.exec() != LoginWindow.DialogCode.Accepted or login.current_user is None:
        return 0

    window = MainWindow(login.current_user)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())