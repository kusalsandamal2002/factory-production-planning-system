from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QTableWidgetItem, QWidget


class TablePageBase(QWidget):
    def _readonly_item(self, text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        return item

    def _apply_status_style(self, item: QTableWidgetItem, is_active: bool) -> None:
        if is_active:
            item.setForeground(QColor("#047857"))
        else:
            item.setForeground(QColor("#b91c1c"))

    def _apply_common_styles(self) -> None:
        self.setStyleSheet(
            """
            QLineEdit {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 6px 12px;
                font-weight: 650;
            }

            QLineEdit:focus {
                border: 1px solid #2563eb;
            }

            QTableWidget {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 12px;
                gridline-color: #e2e8f0;
                selection-background-color: #eff6ff;
                selection-color: #0f172a;
                alternate-background-color: #f8fafc;
            }

            QTableWidget::item {
                padding: 9px 10px;
                border: none;
            }

            QTableWidget::item:selected {
                background: #eff6ff;
                color: #0f172a;
            }

            QHeaderView::section {
                background: #f1f5f9;
                color: #1e293b;
                border: none;
                border-right: 1px solid #e2e8f0;
                border-bottom: 1px solid #e2e8f0;
                padding: 11px;
                font-weight: 950;
            }

            QPushButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-weight: 900;
            }

            QPushButton:hover {
                background: #cbd5e1;
            }

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: #ffffff;
            }

            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }
            """
        )