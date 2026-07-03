from pathlib import Path
import re

path = Path("app/ui/cavities_master_page.py")
text = path.read_text(encoding="utf-8")

# Add Manage button stylesheet.
if "QPushButton#ManageButton" not in text:
    marker = """            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }
"""
    insert = """            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }

            QPushButton#ManageButton {
                background: #eef2ff;
                color: #1d4ed8;
                border: 1px solid #c7d2fe;
                border-radius: 10px;
                padding: 6px 12px;
                font-size: 8.2pt;
                font-weight: 950;
                min-width: 86px;
                max-width: 96px;
            }

            QPushButton#ManageButton:hover {
                background: #dbeafe;
                border: 1px solid #93c5fd;
            }
"""
    if marker not in text:
        raise SystemExit("Could not find PrimaryButton style block.")
    text = text.replace(marker, insert)

# Make action column compact because only one Manage button is shown.
text = re.sub(
    r"self\.table\.setColumnWidth\(5,\s*\d+\)",
    "self.table.setColumnWidth(5, 140)",
    text,
)

# Replace row action buttons block with one Manage button.
pattern = r'''            action_widget = QWidget\(\)
            action_layout = QHBoxLayout\(action_widget\)
.*?
            self\.table\.setCellWidget\(row_index, 5, action_widget\)
'''

replacement = '''            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(6, 5, 6, 5)
            action_layout.setSpacing(0)

            manage_button = QPushButton("Manage")
            manage_button.setObjectName("ManageButton")
            manage_button.clicked.connect(lambda checked=False, cavity_id=row["id"]: self._manage_cavity(cavity_id))

            action_layout.addStretch()
            action_layout.addWidget(manage_button)
            action_layout.addStretch()
            self.table.setCellWidget(row_index, 5, action_widget)
'''

text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)

if count != 1:
    raise SystemExit(f"Could not replace action button block. Replacements: {count}")

# Add manage popup method before _add_cavity.
if "def _manage_cavity(self, cavity_id: int)" not in text:
    marker = "\n    def _add_cavity(self) -> None:\n"

    method = '''
    def _manage_cavity(self, cavity_id: int) -> None:
        row = None

        for item in self.cavities:
            if item["id"] == cavity_id:
                row = item
                break

        if row is None:
            return

        cavity_code = row.get("cavity_code") or f"Cavity {row.get('cavity_no', '')}"

        box = QMessageBox(self)
        box.setWindowTitle("Manage Cavity")
        box.setText(f"{self.selected_line_name}\\n{cavity_code}")
        box.setInformativeText("Choose what you want to do with this cavity.")
        box.setIcon(QMessageBox.Icon.Question)

        edit_button = box.addButton("Edit", QMessageBox.ButtonRole.AcceptRole)
        delete_button = box.addButton("Delete", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

        box.exec()
        clicked = box.clickedButton()

        if clicked == edit_button:
            self._edit_cavity(cavity_id)
        elif clicked == delete_button:
            self._delete_cavity(cavity_id)
        elif clicked == cancel_button:
            return

'''

    if marker not in text:
        raise SystemExit("Could not find _add_cavity method marker.")

    text = text.replace(marker, "\n" + method + "    def _add_cavity(self) -> None:\n")

path.write_text(text, encoding="utf-8")
print("Action column fixed with single Manage button.")
