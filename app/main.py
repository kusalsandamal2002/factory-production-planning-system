import sys

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QDialog

from app.ui.login_dialog import LoginDialog


def apply_app_palette(app: QApplication) -> None:
    app.setStyle("Fusion")

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#f3f6fb"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#0f172a"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#f8fafc"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#0f172a"))
    palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor("#0f172a"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#2563eb"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))

    app.setPalette(palette)

    app.setStyleSheet(
        """
        QMainWindow {
            background: #f3f6fb;
        }

        QScrollArea {
            background: #f3f6fb;
            border: none;
        }

        QWidget {
            font-family: "Segoe UI";
        }

        QMessageBox {
            background: #ffffff;
            color: #0f172a;
        }

        QToolTip {
            background: #ffffff;
            color: #0f172a;
            border: 1px solid #cbd5e1;
            padding: 6px;
        }
        """
    )


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Factory Oven Production Planning System")
    apply_app_palette(app)

    login_dialog = LoginDialog()

    if login_dialog.exec() != QDialog.DialogCode.Accepted:
        return 0

    if login_dialog.current_user is None:
        return 0

    # Important: MainWindow is imported only after successful login.
    # This makes the login screen open much faster.
    from app.ui.main_window import MainWindow

    window = MainWindow(login_dialog.current_user)
    window.showMaximized()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
