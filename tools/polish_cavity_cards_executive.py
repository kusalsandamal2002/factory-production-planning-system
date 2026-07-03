from pathlib import Path
import re

path = Path("app/ui/cavities_master_page.py")
text = path.read_text(encoding="utf-8")

# Add QColor import.
if "from PySide6.QtGui import QColor" not in text:
    text = text.replace(
        "from PySide6.QtCore import Qt\n",
        "from PySide6.QtCore import Qt\nfrom PySide6.QtGui import QColor\n",
    )

# Add QGraphicsDropShadowEffect import.
if "QGraphicsDropShadowEffect" not in text:
    text = text.replace(
        "    QFrame,\n",
        "    QFrame,\n    QGraphicsDropShadowEffect,\n",
        1,
    )

# Upgrade main card stylesheet.
old_style = """            QFrame#HeaderCard, QFrame#PanelCard, QFrame#LineCard, QFrame#MetricCard, QFrame#TableCard {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 18px;
            }

            QFrame#LineCard {
                min-height: 150px;
            }

            QFrame#LineCard:hover {
                border: 1px solid #2563eb;
                background: #f8fbff;
            }

            QFrame#LineCard[attention="true"] {
                border: 1px solid #f97316;
                background: #fff7ed;
            }
"""

new_style = """            QFrame#HeaderCard, QFrame#MetricCard, QFrame#TableCard {
                background: #ffffff;
                border: 1px solid #dbe4f0;
                border-radius: 22px;
            }

            QFrame#PanelCard {
                background: #f8fafc;
                border: 1px solid #dbe4f0;
                border-radius: 24px;
            }

            QFrame#LineCard {
                background: #ffffff;
                border: 1px solid #d8e3f0;
                border-radius: 24px;
                min-height: 190px;
            }

            QFrame#LineCard:hover {
                border: 2px solid #2563eb;
                background: #f8fbff;
            }

            QFrame#LineCard[attention="true"] {
                border: 2px solid #f97316;
                background: #fff7ed;
            }
"""

if old_style in text:
    text = text.replace(old_style, new_style)
else:
    print("Main style block not matched exactly; continuing with targeted replacements.")
    text = text.replace("border-radius: 18px;", "border-radius: 22px;")
    text = text.replace("min-height: 150px;", "min-height: 190px;")

# More premium typography.
text = text.replace(
    """            QLabel#LineTitle {
                color: #0f172a;
                font-size: 13.5pt;
                font-weight: 950;
            }
""",
    """            QLabel#LineTitle {
                color: #0f172a;
                font-size: 15pt;
                font-weight: 950;
            }
""",
)

text = text.replace(
    """            QLabel#SmallValue {
                color: #0f172a;
                font-size: 12pt;
                font-weight: 950;
            }
""",
    """            QLabel#SmallValue {
                color: #0f172a;
                font-size: 13pt;
                font-weight: 950;
            }
""",
)

# Stronger progress bar.
text = text.replace(
    """            QProgressBar {
                background: #e2e8f0;
                border: none;
                border-radius: 4px;
                height: 8px;
            }

            QProgressBar::chunk {
                background: #2563eb;
                border-radius: 4px;
            }
""",
    """            QProgressBar {
                background: #e5edf7;
                border: none;
                border-radius: 5px;
                height: 10px;
            }

            QProgressBar::chunk {
                background: #2563eb;
                border-radius: 5px;
            }
""",
)

# Increase panel spacing/margins.
text = text.replace(
    "layout.setContentsMargins(18, 16, 18, 18)\n        layout.setSpacing(14)",
    "layout.setContentsMargins(24, 22, 24, 24)\n        layout.setSpacing(20)",
)

text = text.replace(
    "self.line_grid.setSpacing(14)",
    "self.line_grid.setSpacing(22)",
)

# 3 columns to 2 columns for clearer separation.
text = text.replace(
    "self.line_grid.addWidget(card, index // 3, index % 3)",
    "self.line_grid.addWidget(card, index // 2, index % 2)",
)

text = text.replace(
    "for col in range(3):\n            self.line_grid.setColumnStretch(col, 1)",
    "for col in range(2):\n            self.line_grid.setColumnStretch(col, 1)",
)

# Bigger line card padding.
text = text.replace(
    "layout.setContentsMargins(16, 14, 16, 14)\n        layout.setSpacing(10)",
    "layout.setContentsMargins(24, 22, 24, 22)\n        layout.setSpacing(14)",
)

# Cleaner footer wording.
text = text.replace(
    'footer_text = f"{free_percent}% free capacity - click card to open board"',
    'footer_text = f"{free} of {total} cavities free - click to open board"',
)

text = text.replace(
    'footer_text = "No cavities registered - click card to add cavities"',
    'footer_text = "No cavities registered - click to add cavities"',
)

# Insert shadow helper method into CavitiesMasterPage.
if "def _apply_shadow" not in text:
    marker = "        self.refresh()\n\n    def _build_overview_page(self) -> QWidget:"
    replacement = """        self.refresh()

    def _apply_shadow(self, widget: QWidget, blur: int = 28, y: int = 8) -> None:
        effect = QGraphicsDropShadowEffect(widget)
        effect.setBlurRadius(blur)
        effect.setOffset(0, y)
        effect.setColor(QColor(15, 23, 42, 28))
        widget.setGraphicsEffect(effect)

    def _build_overview_page(self) -> QWidget:"""

    if marker not in text:
        raise SystemExit("Could not insert shadow helper method.")

    text = text.replace(marker, replacement)

# Apply shadow before returning card widgets.
if "self._apply_shadow(card)" not in text:
    text = text.replace(
        "        return card\n",
        "        self._apply_shadow(card)\n        return card\n",
    )

# Add a little more card height consistency through layout hint.
text = text.replace(
    "description_label.setWordWrap(True)\n\n        numbers = QHBoxLayout()",
    "description_label.setWordWrap(True)\n        description_label.setMinimumHeight(34)\n\n        numbers = QHBoxLayout()",
)

path.write_text(text, encoding="utf-8")
print("Executive-level cavity card polish applied.")
