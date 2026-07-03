from pathlib import Path
import re

path = Path("app/ui/cavities_master_page.py")
text = path.read_text(encoding="utf-8")

# Remove QProgressBar import if present.
text = text.replace("    QProgressBar,\n", "")

# Remove progress bar stylesheet block.
text = re.sub(
    r"""
\s*QProgressBar\s*\{
.*?
\}

\s*QProgressBar::chunk\s*\{
.*?
\}
""",
    "\n",
    text,
    flags=re.S | re.VERBOSE,
)

# Add professional metric box stylesheet if missing.
if "QFrame#InlineMetricBox" not in text:
    insert_after = """            QLabel#SmallLabel {
                color: #64748b;
                font-size: 7.8pt;
                font-weight: 850;
            }
"""
    extra = """
            QFrame#InlineMetricBox {
                background: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
            }

            QFrame#InlineMetricBox[warning="true"] {
                background: #fff7ed;
                border: 1px solid #fed7aa;
            }

            QLabel#BoardHint {
                color: #2563eb;
                font-size: 8.5pt;
                font-weight: 950;
            }
"""
    if insert_after in text:
        text = text.replace(insert_after, insert_after + extra)

# Make line cards cleaner and consistent.
text = text.replace(
    "min-height: 190px;",
    "min-height: 178px;",
)

text = text.replace(
    "layout.setContentsMargins(24, 22, 24, 22)\n        layout.setSpacing(14)",
    "layout.setContentsMargins(24, 22, 24, 20)\n        layout.setSpacing(12)",
)

# Replace the whole line overview card builder with a cleaner professional version.
pattern = r"    def _line_overview_card\(self, summary: dict\) -> QFrame:\n.*?\n    def _small_stat\(self, value: str, label: str\) -> QWidget:\n"
replacement = '''    def _line_overview_card(self, summary: dict) -> QFrame:
        line_name = str(summary["line_name"])
        total = int(summary["total_cavities"] or 0)
        active = int(summary["active_cavities"] or 0)
        breakdown = int(summary["breakdown_cavities"] or 0)
        used = int(summary["used_cavities"] or 0)
        free = int(summary["free_cavities"] or 0)
        busy_or_issue = used + breakdown

        attention = breakdown > 0 or used > 0

        family, description = LINE_INFO.get(
            line_name,
            ("Custom Production Line", "Manual production line. Open this board to maintain cavities."),
        )

        card = QFrame()
        card.setObjectName("LineCard")
        card.setProperty("attention", "true" if attention else "false")
        card.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(12)

        title_area = QVBoxLayout()
        title_area.setSpacing(4)

        title = QLabel(line_name)
        title.setObjectName("LineTitle")

        family_label = QLabel(family)
        family_label.setObjectName("FamilyText")

        title_area.addWidget(title)
        title_area.addWidget(family_label)

        board_hint = QLabel("VIEW BOARD")
        board_hint.setObjectName("BoardHint")
        board_hint.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        header.addLayout(title_area, 1)
        header.addWidget(board_hint)

        description_label = QLabel(description)
        description_label.setObjectName("HintText")
        description_label.setWordWrap(True)
        description_label.setMinimumHeight(32)

        numbers = QHBoxLayout()
        numbers.setSpacing(10)
        numbers.addWidget(self._small_stat(str(total), "Total"))
        numbers.addWidget(self._small_stat(str(active), "Active"))
        numbers.addWidget(self._small_stat(str(free), "Free"))
        numbers.addWidget(self._small_stat(str(busy_or_issue), "Used / Down", warning=busy_or_issue > 0))

        layout.addLayout(header)
        layout.addWidget(description_label)
        layout.addStretch()
        layout.addLayout(numbers)

        card.mousePressEvent = lambda event, name=line_name: self._open_line_board(name)

        self._apply_shadow(card)
        return card

    def _small_stat(self, value: str, label: str, warning: bool = False) -> QWidget:
'''

text, count = re.subn(pattern, replacement, text, flags=re.S)

if count != 1:
    raise SystemExit(f"Could not replace _line_overview_card cleanly. Replacements: {count}")

# Replace _small_stat body with boxed metrics.
pattern_small = r"    def _small_stat\(self, value: str, label: str, warning: bool = False\) -> QWidget:\n.*?\n    def _open_line_board\(self, line_name: str\) -> None:\n"
replacement_small = '''    def _small_stat(self, value: str, label: str, warning: bool = False) -> QWidget:
        wrapper = QFrame()
        wrapper.setObjectName("InlineMetricBox")
        wrapper.setProperty("warning", "true" if warning else "false")

        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(1)

        value_label = QLabel(value)
        value_label.setObjectName("SmallValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        label_widget = QLabel(label)
        label_widget.setObjectName("SmallLabel")
        label_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(value_label)
        layout.addWidget(label_widget)

        return wrapper

    def _open_line_board(self, line_name: str) -> None:
'''

text, count = re.subn(pattern_small, replacement_small, text, flags=re.S)

if count != 1:
    raise SystemExit(f"Could not replace _small_stat cleanly. Replacements: {count}")

path.write_text(text, encoding="utf-8")
print("Clean professional cavity cards applied.")
