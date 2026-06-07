from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SimpleFieldEditDialog(QDialog):
    def __init__(
        self,
        *,
        dialog_title: str,
        field_label: str,
        current_value: str,
        field_type: str = "text",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self.field_type = field_type
        self.setWindowTitle(dialog_title)
        self.setModal(True)
        self.setMinimumWidth(480)

        self.value_input = QLineEdit()
        self.value_input.setMinimumHeight(42)
        self.value_input.setText(current_value)
        self.value_input.selectAll()

        self.status_combo = QComboBox()
        self.status_combo.setMinimumHeight(42)
        self.status_combo.addItem("Active", True)
        self.status_combo.addItem("Inactive", False)

        if current_value.strip().lower() == "inactive":
            self.status_combo.setCurrentIndex(1)
        else:
            self.status_combo.setCurrentIndex(0)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(40)
        self.cancel_btn.clicked.connect(self.reject)

        self.continue_btn = QPushButton("Continue")
        self.continue_btn.setObjectName("PrimaryButton")
        self.continue_btn.setMinimumHeight(40)
        self.continue_btn.clicked.connect(self.accept)

        self._build_ui(field_label)
        self._apply_styles()

    def _build_ui(self, field_label: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        title = QLabel("Edit Details")
        title.setStyleSheet("font-size: 15pt; font-weight: 950; color: #0f172a;")

        hint = QLabel(
            "Review the value carefully. The change will be saved only after confirmation."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-weight: 650;")

        root.addWidget(title)
        root.addWidget(hint)

        form_card = QFrame()
        form_card.setObjectName("DialogCard")

        form = QGridLayout(form_card)
        form.setContentsMargins(16, 14, 16, 14)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 3)

        label = QLabel(field_label)
        label.setStyleSheet("font-weight: 900; color: #334155;")

        form.addWidget(label, 0, 0)

        if self.field_type == "status":
            form.addWidget(self.status_combo, 0, 1)
        else:
            form.addWidget(self.value_input, 0, 1)

        root.addWidget(form_card)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.continue_btn)

        root.addLayout(btn_row)

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #f8fafc;
            }

            QFrame#DialogCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
            }

            QLineEdit {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 7px 11px;
                font-weight: 850;
            }

            QLineEdit:focus {
                border: 1px solid #2563eb;
            }

            QComboBox {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 7px 11px;
                font-weight: 850;
            }

            QComboBox::drop-down {
                border: none;
                width: 28px;
            }

            QPushButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 8px 18px;
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

    def value(self):
        if self.field_type == "status":
            return self.status_combo.currentData()

        return self.value_input.text().strip()


class NewTireDialog(QDialog):
    def __init__(self, *, suggested_code: str, parent: QWidget | None = None):
        super().__init__(parent)

        self.setWindowTitle("Add New Tire Type")
        self.setModal(True)
        self.setMinimumWidth(520)

        self.code_input = QLineEdit()
        self.code_input.setText(suggested_code)
        self.code_input.setMinimumHeight(42)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter tire type name")
        self.name_input.setText("New Tire Type")
        self.name_input.setMinimumHeight(42)
        self.name_input.selectAll()

        self.status_combo = QComboBox()
        self.status_combo.addItem("Active", True)
        self.status_combo.addItem("Inactive", False)
        self.status_combo.setMinimumHeight(42)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(40)
        self.cancel_btn.clicked.connect(self.reject)

        self.save_btn = QPushButton("Create Tire Type")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.setMinimumHeight(40)
        self.save_btn.clicked.connect(self.accept)

        self._build_ui()
        self._apply_styles()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        title = QLabel("Add New Tire Type")
        title.setStyleSheet("font-size: 15pt; font-weight: 950; color: #0f172a;")

        hint = QLabel(
            "Create a new tire master record. Production time can be changed from the Tire Production Time tab."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-weight: 650;")

        root.addWidget(title)
        root.addWidget(hint)

        form_card = QFrame()
        form_card.setObjectName("DialogCard")

        form = QGridLayout(form_card)
        form.setContentsMargins(16, 14, 16, 14)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 3)

        form.addWidget(self._label("Tire Code"), 0, 0)
        form.addWidget(self.code_input, 0, 1)

        form.addWidget(self._label("Tire Type"), 1, 0)
        form.addWidget(self.name_input, 1, 1)

        form.addWidget(self._label("Status"), 2, 0)
        form.addWidget(self.status_combo, 2, 1)

        root.addWidget(form_card)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.save_btn)

        root.addLayout(btn_row)

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight: 900; color: #334155;")
        return label

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #f8fafc;
            }

            QFrame#DialogCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
            }

            QLineEdit {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 7px 11px;
                font-weight: 850;
            }

            QLineEdit:focus {
                border: 1px solid #2563eb;
            }

            QComboBox {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 7px 11px;
                font-weight: 850;
            }

            QComboBox::drop-down {
                border: none;
                width: 28px;
            }

            QPushButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 8px 18px;
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

    def values(self) -> tuple[str, str, bool]:
        return (
            self.code_input.text().strip().upper(),
            self.name_input.text().strip(),
            bool(self.status_combo.currentData()),
        )


class ProductionTimeEditDialog(QDialog):
    def __init__(
        self,
        *,
        tire_code: str,
        tire_name: str,
        current_minutes: int,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)

        self.setWindowTitle("Edit Tire Production Time")
        self.setModal(True)
        self.setMinimumWidth(540)

        self.minutes_input = QLineEdit()
        self.minutes_input.setMinimumHeight(42)
        self.minutes_input.setText(str(current_minutes))
        self.minutes_input.selectAll()
        self.minutes_input.setPlaceholderText("Enter production minutes")

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(40)
        self.cancel_btn.clicked.connect(self.reject)

        self.continue_btn = QPushButton("Continue")
        self.continue_btn.setObjectName("PrimaryButton")
        self.continue_btn.setMinimumHeight(40)
        self.continue_btn.clicked.connect(self.accept)

        self._build_ui(tire_code, tire_name, current_minutes)
        self._apply_styles()

    def _build_ui(self, tire_code: str, tire_name: str, current_minutes: int) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(14)

        title = QLabel("Edit Tire Production Time")
        title.setStyleSheet("font-size: 15pt; font-weight: 950; color: #0f172a;")

        hint = QLabel(
            "This production time is used for order enquiry date and oven planning calculation."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #64748b; font-weight: 650;")

        root.addWidget(title)
        root.addWidget(hint)

        form_card = QFrame()
        form_card.setObjectName("DialogCard")

        form = QGridLayout(form_card)
        form.setContentsMargins(16, 14, 16, 14)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(12)
        form.setColumnStretch(0, 1)
        form.setColumnStretch(1, 3)

        form.addWidget(self._label("Tire Code"), 0, 0)
        form.addWidget(self._value_label(tire_code), 0, 1)

        form.addWidget(self._label("Tire Type"), 1, 0)
        form.addWidget(self._value_label(tire_name), 1, 1)

        form.addWidget(self._label("Current Time"), 2, 0)
        form.addWidget(self._value_label(f"{current_minutes} min"), 2, 1)

        form.addWidget(self._label("New Time"), 3, 0)
        form.addWidget(self.minutes_input, 3, 1)

        root.addWidget(form_card)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        btn_row.addWidget(self.cancel_btn)
        btn_row.addWidget(self.continue_btn)

        root.addLayout(btn_row)

    def _label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet("font-weight: 900; color: #334155;")
        return label

    def _value_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setMinimumHeight(38)
        label.setStyleSheet(
            """
            QLabel {
                background: #f1f5f9;
                color: #0f172a;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 8px 11px;
                font-weight: 850;
            }
            """
        )
        return label

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QDialog {
                background: #f8fafc;
            }

            QFrame#DialogCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
            }

            QLineEdit {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 7px 11px;
                font-weight: 850;
            }

            QLineEdit:focus {
                border: 1px solid #2563eb;
            }

            QPushButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 8px 18px;
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

    def minutes(self) -> int:
        text_value = self.minutes_input.text().strip().replace(",", "")

        try:
            value = int(text_value)
        except ValueError as exc:
            raise ValueError("Production time must be a whole number.") from exc

        if value <= 0:
            raise ValueError("Production time must be greater than zero.")

        if value > 10000:
            raise ValueError("Production time cannot be greater than 10000 minutes.")

        return value