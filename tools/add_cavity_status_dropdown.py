from pathlib import Path
import re

path = Path("app/ui/cavities_master_page.py")
text = path.read_text(encoding="utf-8")

# Add dropdown stylesheet.
if "QComboBox#StatusDropdown" not in text:
    marker = """            QLabel#StatusUsed {
                background: #fef3c7;
                color: #92400e;
                border: 1px solid #fde68a;
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 8pt;
                font-weight: 950;
            }
"""
    insert = """            QLabel#StatusUsed {
                background: #fef3c7;
                color: #92400e;
                border: 1px solid #fde68a;
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 8pt;
                font-weight: 950;
            }

            QComboBox#StatusDropdown {
                background: #f8fafc;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 8.5pt;
                font-weight: 900;
                min-width: 120px;
            }

            QComboBox#StatusDropdown:hover {
                border: 1px solid #2563eb;
                background: #ffffff;
            }
"""
    if marker not in text:
        raise SystemExit("Could not find status label stylesheet block.")
    text = text.replace(marker, insert)

# Add repository method for status-only update.
if "def update_cavity_status(self, cavity_id: int, status: str)" not in text:
    marker = "    def delete_cavity(self, cavity_id: int) -> None:\n"
    method = '''    def update_cavity_status(self, cavity_id: int, status: str) -> None:
        self.ensure_tables()

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE production_line_cavities
                    SET status = :status,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {
                    "id": cavity_id,
                    "status": status,
                },
            )

'''
    if marker not in text:
        raise SystemExit("Could not find delete_cavity repository marker.")
    text = text.replace(marker, method + marker)

# Replace status QLabel block inside _refresh_table with dropdown.
old_block = '''            status = row.get("status", "Active")
            status_label = QLabel(status)
            status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            status_label.setObjectName("StatusBreakdown" if status == "Breakdown" else "StatusActive")
            self.table.setCellWidget(row_index, 1, status_label)
'''

new_block = '''            status = row.get("status", "Active")
            status_dropdown = QComboBox()
            status_dropdown.setObjectName("StatusDropdown")
            status_dropdown.addItems(["Operational", "Breakdown"])
            status_dropdown.setCurrentText("Breakdown" if status == "Breakdown" else "Operational")
            status_dropdown.currentTextChanged.connect(
                lambda value, cavity_id=row["id"]: self._change_cavity_status(cavity_id, value)
            )
            self.table.setCellWidget(row_index, 1, status_dropdown)
'''

if old_block not in text:
    raise SystemExit("Could not find table status label block.")

text = text.replace(old_block, new_block)

# Add page method to handle dropdown status update.
if "def _change_cavity_status(self, cavity_id: int, ui_status: str)" not in text:
    marker = "\n    def _manage_cavity(self, cavity_id: int) -> None:\n"

    method = '''
    def _change_cavity_status(self, cavity_id: int, ui_status: str) -> None:
        db_status = "Breakdown" if ui_status == "Breakdown" else "Active"

        try:
            self.repo.update_cavity_status(cavity_id, db_status)
        except Exception as exc:
            QMessageBox.critical(self, "Status Update Failed", f"Could not update cavity status.\\n\\n{exc}")
            return

        self._load_detail(self.selected_line_name)

'''

    if marker not in text:
        raise SystemExit("Could not find _manage_cavity marker.")

    text = text.replace(marker, "\n" + method + "    def _manage_cavity(self, cavity_id: int) -> None:\n")

# Make table header clearer.
text = text.replace('"Status"', '"Status"')

# Update subtitle wording.
text = text.replace(
    "Active + no assigned tyre item = Available.",
    "Operational + no assigned tyre item = Available.",
)

path.write_text(text, encoding="utf-8")
print("Cavity status column changed to Operational/Breakdown dropdown.")
