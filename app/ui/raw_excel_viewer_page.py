
from pathlib import Path
import subprocess
import sys

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QTextEdit, QLineEdit
)
from PySide6.QtCore import Qt


class RawExcelViewerPage(QWidget):
    def __init__(self, *args, **kwargs):
        super().__init__()
        self.project_root = Path(__file__).resolve().parents[2]
        self.default_file = self.project_root / "data_sources" / "SMDS6.xlsx"
        self.selected_file = str(self.default_file)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("SMDS Excel Import")
        title.setStyleSheet("font-size: 28px; font-weight: 800;")
        layout.addWidget(title)

        subtitle = QLabel("Import SMDS6.xlsx into PostgreSQL master tables: SMDS, Mold, Casing and Line Cavities.")
        subtitle.setStyleSheet("color: #52627a; font-size: 13px;")
        layout.addWidget(subtitle)

        row = QHBoxLayout()
        self.file_box = QLineEdit(self.selected_file)
        self.file_box.setMinimumHeight(36)
        row.addWidget(self.file_box, 1)

        browse_btn = QPushButton("Select Excel File")
        browse_btn.setMinimumHeight(36)
        browse_btn.clicked.connect(self.browse_file)
        row.addWidget(browse_btn)

        layout.addLayout(row)

        btn_row = QHBoxLayout()

        import_btn = QPushButton("Import SMDS Data")
        import_btn.setMinimumHeight(42)
        import_btn.setStyleSheet("font-weight: 700;")
        import_btn.clicked.connect(self.run_import)
        btn_row.addWidget(import_btn)

        replace_btn = QPushButton("Replace Existing Master Data + Import")
        replace_btn.setMinimumHeight(42)
        replace_btn.clicked.connect(lambda: self.run_import(replace=True))
        btn_row.addWidget(replace_btn)

        layout.addLayout(btn_row)

        note = QLabel("Use Replace only when you want to clear old SMDS/Mold/Casing/Cavity master data before importing. Stock data is not deleted.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #9a3412;")
        layout.addWidget(note)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Import result will appear here.")
        layout.addWidget(self.output, 1)

    def browse_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select SMDS Excel File",
            str(self.default_file.parent),
            "Excel Files (*.xlsx *.xlsm)"
        )
        if path:
            self.selected_file = path
            self.file_box.setText(path)

    def run_import(self, replace=False):
        excel_path = self.file_box.text().strip()
        script_path = self.project_root / "tools" / "import_smds6_now.py"

        if not Path(excel_path).exists():
            self.output.setPlainText("ERROR: Excel file not found:\n" + excel_path)
            return

        if not script_path.exists():
            self.output.setPlainText("ERROR: Import script not found:\n" + str(script_path))
            return

        cmd = [
            sys.executable,
            str(script_path),
            excel_path,
            "--seed-line-cavities",
        ]

        if replace:
            cmd.append("--replace")

        self.output.setPlainText("Running import...\n\n" + " ".join(cmd))

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self.project_root),
                capture_output=True,
                text=True,
                timeout=300,
            )

            result = []
            result.append("COMMAND:")
            result.append(" ".join(cmd))
            result.append("")
            result.append("STDOUT:")
            result.append(proc.stdout)
            result.append("")
            result.append("STDERR:")
            result.append(proc.stderr)
            result.append("")
            result.append(f"EXIT CODE: {proc.returncode}")

            self.output.setPlainText("\n".join(result))

        except Exception as e:
            self.output.setPlainText("ERROR running import:\n" + str(e))
