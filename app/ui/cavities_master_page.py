from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.database import engine


REFERENCE_LINE_ORDER = {
    "ORING-PRESS": 1,
    "NEW PRESS": 2,
    "NANCY PRESS": 3,
    "400 T PRESS": 4,
    "T 600 -01 PRESS": 5,
    "T 600 -02 PRESS": 6,
    "L-PRESS-1250": 7,
    "L-PRESS-1500": 8,
    "L-PRESS-1800": 9,
    "Press -LINE": 10,
    "Line-400": 11,
    "Line-800": 12,
}

LINE_INFO = {
    "ORING-PRESS": ("Special Press", "O-ring press positions"),
    "NEW PRESS": ("Special Press", "New press position"),
    "NANCY PRESS": ("Special Press", "Nancy upper/lower press positions"),
    "400 T PRESS": ("Press", "400T upper/lower press positions"),
    "T 600 -01 PRESS": ("Press", "600T press 01 upper/lower positions"),
    "T 600 -02 PRESS": ("Press", "600T press 02 upper/lower positions"),
    "L-PRESS-1250": ("Large Press", "1250 press position"),
    "L-PRESS-1500": ("Large Press", "1500 press position"),
    "L-PRESS-1800": ("Large Press", "1800 press position"),
    "Press -LINE": ("200T / Press Line", "L-Press and double press cavity positions"),
    "Line-400": ("400T Line", "400T main oven/cavity positions"),
    "Line-800": ("800T Line", "800T main oven/cavity positions"),
}


class CavityRepository:
    def ensure_tables(self) -> None:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS production_lines (
                    id VARCHAR(64) PRIMARY KEY,
                    line_name VARCHAR(255) NOT NULL UNIQUE,
                    status VARCHAR(32) NOT NULL DEFAULT 'Active',
                    remarks TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS production_line_cavities (
                    id BIGSERIAL PRIMARY KEY,
                    line_name VARCHAR(255) NOT NULL,
                    cavity_no INTEGER NOT NULL,
                    status VARCHAR(32) NOT NULL DEFAULT 'Active',
                    assigned_tyre_item VARCHAR(255) NOT NULL DEFAULT '',
                    remarks TEXT NOT NULL DEFAULT '',
                    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(line_name, cavity_no)
                )
            """))

            conn.execute(text("""
                ALTER TABLE production_line_cavities
                ADD COLUMN IF NOT EXISTS cavity_code VARCHAR(255) NOT NULL DEFAULT ''
            """))

            conn.execute(text("""
                ALTER TABLE production_line_cavities
                ADD COLUMN IF NOT EXISTS display_order INTEGER NOT NULL DEFAULT 0
            """))

    def list_lines_summary(self) -> list[dict]:
        self.ensure_tables()

        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT
                    pl.line_name,
                    pl.status AS line_status,
                    pl.remarks AS line_remarks,
                    COALESCE(COUNT(pc.id), 0) AS total_cavities,
                    COALESCE(SUM(CASE WHEN pc.status = 'Active' THEN 1 ELSE 0 END), 0) AS active_cavities,
                    COALESCE(SUM(CASE WHEN pc.status = 'Breakdown' THEN 1 ELSE 0 END), 0) AS breakdown_cavities,
                    COALESCE(SUM(CASE WHEN pc.assigned_tyre_item <> '' THEN 1 ELSE 0 END), 0) AS used_cavities,
                    COALESCE(SUM(CASE WHEN pc.assigned_tyre_item = '' AND pc.status = 'Active' THEN 1 ELSE 0 END), 0) AS free_cavities,
                    MIN(pl.created_at) AS created_at
                FROM production_lines pl
                LEFT JOIN production_line_cavities pc
                    ON pc.line_name = pl.line_name
                GROUP BY
                    pl.line_name,
                    pl.status,
                    pl.remarks
            """)).mappings().all()

        result = [dict(row) for row in rows]
        result.sort(
            key=lambda row: (
                REFERENCE_LINE_ORDER.get(row["line_name"], 999),
                str(row.get("created_at", "")),
                row["line_name"],
            )
        )
        return result

    def list_cavities(self, line_name: str) -> list[dict]:
        self.ensure_tables()

        with engine.connect() as conn:
            rows = conn.execute(
                text("""
                    SELECT
                        id,
                        line_name,
                        cavity_no,
                        cavity_code,
                        display_order,
                        status,
                        assigned_tyre_item,
                        remarks
                    FROM production_line_cavities
                    WHERE line_name = :line_name
                    ORDER BY
                    CASE
                        WHEN LOWER(status) = 'breakdown' THEN 0
                        ELSE 1
                    END,
                    COALESCE(NULLIF(display_order, 0), cavity_no),
                    cavity_no, cavity_code
                """),
                {"line_name": line_name},
            ).mappings().all()

        return [dict(row) for row in rows]

    def cavity_code_exists(self, line_name: str, cavity_code: str, exclude_id: int | None = None) -> bool:
        self.ensure_tables()

        query = """
            SELECT COUNT(*)
            FROM production_line_cavities
            WHERE line_name = :line_name
              AND LOWER(cavity_code) = LOWER(:cavity_code)
        """

        params = {
            "line_name": line_name,
            "cavity_code": cavity_code,
        }

        if exclude_id is not None:
            query += " AND id <> :exclude_id"
            params["exclude_id"] = exclude_id

        with engine.connect() as conn:
            return int(conn.execute(text(query), params).scalar_one()) > 0

    def add_cavity(self, line_name: str, cavity_code: str, status: str, assigned_tyre_item: str, remarks: str) -> None:
        self.ensure_tables()

        if self.cavity_code_exists(line_name, cavity_code):
            raise ValueError(f"Cavity code already exists for {line_name}: {cavity_code}")

        with engine.begin() as conn:
            next_no = int(
                conn.execute(
                    text("""
                        SELECT COALESCE(MAX(cavity_no), 0) + 1
                        FROM production_line_cavities
                        WHERE line_name = :line_name
                    """),
                    {"line_name": line_name},
                ).scalar_one()
            )

            next_order = int(
                conn.execute(
                    text("""
                        SELECT COALESCE(MAX(display_order), 0) + 1
                        FROM production_line_cavities
                        WHERE line_name = :line_name
                    """),
                    {"line_name": line_name},
                ).scalar_one()
            )

            conn.execute(
                text("""
                    INSERT INTO production_line_cavities
                        (line_name, cavity_no, cavity_code, display_order, status, assigned_tyre_item, remarks)
                    VALUES
                        (:line_name, :cavity_no, :cavity_code, :display_order, :status, :assigned_tyre_item, :remarks)
                """),
                {
                    "line_name": line_name,
                    "cavity_no": next_no,
                    "cavity_code": cavity_code,
                    "display_order": next_order,
                    "status": status,
                    "assigned_tyre_item": assigned_tyre_item,
                    "remarks": remarks,
                },
            )

    def update_cavity(
        self,
        cavity_id: int,
        line_name: str,
        cavity_code: str,
        status: str,
        assigned_tyre_item: str,
        remarks: str,
    ) -> None:
        self.ensure_tables()

        if self.cavity_code_exists(line_name, cavity_code, exclude_id=cavity_id):
            raise ValueError(f"Cavity code already exists for {line_name}: {cavity_code}")

        with engine.begin() as conn:
            conn.execute(
                text("""
                    UPDATE production_line_cavities
                    SET cavity_code = :cavity_code,
                        status = :status,
                        assigned_tyre_item = :assigned_tyre_item,
                        remarks = :remarks,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :id
                """),
                {
                    "id": cavity_id,
                    "cavity_code": cavity_code,
                    "status": status,
                    "assigned_tyre_item": assigned_tyre_item,
                    "remarks": remarks,
                },
            )

    def update_cavity_status(self, cavity_id: int, status: str) -> None:
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

    def delete_cavity(self, cavity_id: int) -> None:
        """Retire a cavity while preserving its historical production evidence."""
        self.ensure_tables()
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE production_line_cavities
                    SET status='Retired',
                        remarks=CASE
                            WHEN TRIM(COALESCE(remarks,''))=''
                            THEN 'Retired from technical register; historical ML evidence retained.'
                            ELSE remarks END,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=:id
                    """
                ),
                {"id": cavity_id},
            )


class CavityDialog(QDialog):
    def __init__(self, parent=None, line_name: str = "", row: dict | None = None):
        super().__init__(parent)
        self.line_name = line_name
        self.row = row or {}
        self.is_edit = row is not None

        self.setWindowTitle("Edit Cavity" if self.is_edit else "Add Cavity")
        self.setMinimumWidth(600)

        self.setStyleSheet("""
            QDialog {
                background: #f8fafc;
            }

            QLabel {
                color: #0f172a;
                font-size: 9.5pt;
                font-weight: 850;
            }

            QLineEdit, QComboBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 10px 12px;
                color: #0f172a;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #2563eb;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        title_text = "Edit Cavity" if self.is_edit else "Add New Cavity"
        title = QLabel(f"{title_text} - {line_name}")
        title.setStyleSheet("color: #0f172a; font-size: 16pt; font-weight: 950;")
        root.addWidget(title)

        form = QGridLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(14)

        self.cavity_code_input = QLineEdit()
        self.cavity_code_input.setPlaceholderText("Example: T400-042 / L-PRESS-015 / CUSTOM-001")
        self.cavity_code_input.setText(self.row.get("cavity_code", ""))

        self.status_input = QComboBox()
        self.status_input.addItems(["Active", "Breakdown"])
        self.status_input.setCurrentText(self.row.get("status", "Active"))

        self.assigned_item_input = QLineEdit()
        self.assigned_item_input.setPlaceholderText("Leave empty if this cavity is free")
        self.assigned_item_input.setText(self.row.get("assigned_tyre_item", ""))

        self.remarks_input = QLineEdit()
        self.remarks_input.setPlaceholderText("Optional remarks")
        self.remarks_input.setText(self.row.get("remarks", ""))

        form.addWidget(QLabel("Cavity Code"), 0, 0)
        form.addWidget(self.cavity_code_input, 0, 1)

        form.addWidget(QLabel("Status"), 1, 0)
        form.addWidget(self.status_input, 1, 1)

        form.addWidget(QLabel("Tyre Item"), 2, 0)
        form.addWidget(self.assigned_item_input, 2, 1)

        form.addWidget(QLabel("Remarks"), 3, 0)
        form.addWidget(self.remarks_input, 3, 1)

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept_if_valid)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _accept_if_valid(self) -> None:
        if not self.cavity_code_input.text().strip():
            QMessageBox.warning(self, "Missing Cavity Code", "Please enter a cavity code.")
            return

        self.accept()

    def data(self) -> dict:
        return {
            "cavity_code": self.cavity_code_input.text().strip(),
            "status": self.status_input.currentText(),
            "assigned_tyre_item": self.assigned_item_input.text().strip(),
            "remarks": self.remarks_input.text().strip(),
        }


class CavitiesMasterPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.repo = CavityRepository()
        self.line_summaries: list[dict] = []
        self.cavities: list[dict] = []
        self.selected_line_name = ""

        self.setStyleSheet("""
            QFrame#HeaderCard, QFrame#MetricCard, QFrame#TableCard {
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
                min-height: 178px;
            }

            QFrame#LineCard:hover {
                border: 2px solid #2563eb;
                background: #f8fbff;
            }

            QFrame#LineCard[attention="true"] {
                border: 2px solid #f97316;
                background: #fff7ed;
            }

            QLabel#Breadcrumb {
                color: #2563eb;
                font-size: 9pt;
                font-weight: 950;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 24pt;
                font-weight: 950;
            }

            QLabel#PageSubtitle, QLabel#HintText {
                color: #64748b;
                font-size: 9.2pt;
                font-weight: 650;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 15pt;
                font-weight: 950;
            }

            QLabel#LineTitle {
                color: #0f172a;
                font-size: 15pt;
                font-weight: 950;
            }

            QLabel#FamilyText {
                color: #64748b;
                font-size: 8.5pt;
                font-weight: 800;
            }

            QLabel#CardValue {
                color: #020617;
                font-size: 21pt;
                font-weight: 950;
            }

            QLabel#CardLabel {
                color: #64748b;
                font-size: 8.2pt;
                font-weight: 850;
            }

            QLabel#SmallValue {
                color: #0f172a;
                font-size: 13pt;
                font-weight: 950;
            }

            QLabel#SmallLabel {
                color: #64748b;
                font-size: 7.8pt;
                font-weight: 850;
            }

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

            QLabel#StatusActive {
                background: #dcfce7;
                color: #166534;
                border: 1px solid #bbf7d0;
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 8pt;
                font-weight: 950;
            }

            QLabel#StatusBreakdown {
                background: #fee2e2;
                color: #991b1b;
                border: 1px solid #fecaca;
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 8pt;
                font-weight: 950;
            }

            QLabel#StatusFree {
                background: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                border-radius: 10px;
                padding: 6px 10px;
                font-size: 8pt;
                font-weight: 950;
            }

            QLabel#StatusUsed {
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

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 11px;
                padding: 9px 15px;
                font-size: 8.8pt;
                font-weight: 950;
            }

            QPushButton#PrimaryButton:hover {
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

            QPushButton#BackButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 8.5pt;
                font-weight: 900;
            }

            QPushButton#EditButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 8.5pt;
                font-weight: 900;
                min-width: 78px;
            }

            QPushButton#BackButton:hover, QPushButton#EditButton:hover {
                background: #cbd5e1;
            }

            QPushButton#DeleteButton {
                background: #fee2e2;
                color: #991b1b;
                border: none;
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 8.5pt;
                font-weight: 900;
                min-width: 88px;
            }

            QPushButton#DeleteButton:hover {
                background: #fecaca;
            }


            QTableWidget {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
                gridline-color: #e2e8f0;
                color: #0f172a;
                font-size: 9.3pt;
                font-weight: 700;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }

            QTableWidget::item {
                padding: 10px;
            }

            QHeaderView::section {
                background: #f8fafc;
                color: #334155;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 12px;
                font-size: 8.8pt;
                font-weight: 950;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_overview_page())
        self.stack.addWidget(self._build_detail_page())

        root.addWidget(self.stack)
        self.refresh()

    def _apply_shadow(self, widget: QWidget, blur: int = 28, y: int = 8) -> None:
        effect = QGraphicsDropShadowEffect(widget)
        effect.setBlurRadius(blur)
        effect.setOffset(0, y)
        effect.setColor(QColor(15, 23, 42, 28))
        widget.setGraphicsEffect(effect)

    def _build_overview_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self._overview_header())
        root.addLayout(self._overview_summary_metrics())
        root.addWidget(self._overview_cards_panel(), 1)

        return page

    def _overview_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        breadcrumb = QLabel("Factory Capacity  /  Cavities")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Cavity Control Center")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Production line cards are loaded from Production Line Master. Open a line card to add, edit, delete and update cavity status."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("PrimaryButton")
        refresh_button.clicked.connect(self.refresh)

        layout.addLayout(text_area, 1)
        layout.addWidget(refresh_button)

        self._apply_shadow(card)
        return card

    def _overview_summary_metrics(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(12)

        self.overview_metric_labels: dict[str, QLabel] = {}

        cards = [
            ("lines", "Operating Lines", "From Production Line Master"),
            ("total", "Total Cavity Positions", "Registered cavities"),
            ("free", "Ready / Free", "Active and unassigned"),
            ("attention", "Need Attention", "Breakdown or assigned"),
        ]

        for col, (key, label, hint) in enumerate(cards):
            grid.addWidget(self._overview_metric_card(key, label, hint), 0, col)
            grid.setColumnStretch(col, 1)

        return grid

    def _overview_metric_card(self, key: str, label: str, hint: str) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(3)

        value = QLabel("0")
        value.setObjectName("CardValue")
        self.overview_metric_labels[key] = value

        label_widget = QLabel(label)
        label_widget.setObjectName("CardLabel")

        hint_widget = QLabel(hint)
        hint_widget.setObjectName("HintText")
        hint_widget.setWordWrap(True)

        layout.addWidget(value)
        layout.addWidget(label_widget)
        layout.addWidget(hint_widget)

        self._apply_shadow(card)
        return card

    def _overview_cards_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("PanelCard")

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 22, 24, 24)
        layout.setSpacing(20)

        top = QHBoxLayout()

        title = QLabel("Production Line Boards")
        title.setObjectName("SectionTitle")

        hint = QLabel("Select a production line card to view or maintain cavities.")
        hint.setObjectName("HintText")

        top.addWidget(title)
        top.addStretch()
        top.addWidget(hint)

        self.line_grid = QGridLayout()
        self.line_grid.setSpacing(22)

        layout.addLayout(top)
        layout.addLayout(self.line_grid)
        layout.addStretch()

        return panel

    def _build_detail_page(self) -> QWidget:
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addWidget(self._detail_header())
        root.addLayout(self._detail_metrics())
        root.addWidget(self._detail_table_card(), 1)

        return page

    def _detail_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("HeaderCard")

        layout = QHBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        breadcrumb = QLabel("Cavities  /  Line Board")
        breadcrumb.setObjectName("Breadcrumb")

        self.detail_title = QLabel("Line Cavity Board")
        self.detail_title.setObjectName("PageTitle")

        self.detail_subtitle = QLabel("Add cavities and maintain active/breakdown/assigned status for this production line.")
        self.detail_subtitle.setObjectName("PageSubtitle")
        self.detail_subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(self.detail_title)
        text_area.addWidget(self.detail_subtitle)

        add_button = QPushButton("+ Add Cavity")
        add_button.setObjectName("PrimaryButton")
        add_button.clicked.connect(self._add_cavity)

        back_button = QPushButton("Back to Boards")
        back_button.setObjectName("BackButton")
        back_button.clicked.connect(self._back_to_overview)

        layout.addLayout(text_area, 1)
        layout.addWidget(add_button)
        layout.addWidget(back_button)

        self._apply_shadow(card)
        return card

    def _detail_metrics(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(12)

        self.detail_metric_labels: dict[str, QLabel] = {}

        cards = [
            ("total", "Total", "All positions"),
            ("active", "Operational", "Working cavities"),
            ("breakdown", "Breakdown", "Not usable"),
            ("used", "Assigned", "Tyre item loaded"),
            ("free", "Free", "Ready now"),
        ]

        for col, (key, label, hint) in enumerate(cards):
            grid.addWidget(self._detail_metric_card(key, label, hint), 0, col)
            grid.setColumnStretch(col, 1)

        return grid

    def _detail_metric_card(self, key: str, label: str, hint: str) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(3)

        value = QLabel("0")
        value.setObjectName("CardValue")
        self.detail_metric_labels[key] = value

        label_widget = QLabel(label)
        label_widget.setObjectName("CardLabel")

        hint_widget = QLabel(hint)
        hint_widget.setObjectName("HintText")
        hint_widget.setWordWrap(True)

        layout.addWidget(value)
        layout.addWidget(label_widget)
        layout.addWidget(hint_widget)

        self._apply_shadow(card)
        return card

    def _detail_table_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("TableCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 16, 18, 18)
        layout.setSpacing(12)

        title = QLabel("Cavity Position Details")
        title.setObjectName("SectionTitle")

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([
            "Cavity Code",
            "Status",
            "Availability",
            "Tyre Item",
            "Remarks",
            "Action",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(5, 140)

        layout.addWidget(title)
        layout.addWidget(self.table, 1)

        self._apply_shadow(card)
        return card

    def refresh(self) -> None:
        try:
            self.line_summaries = self.repo.list_lines_summary()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Could not load cavities.\n\n{exc}")
            self.line_summaries = []

        self._refresh_overview_metrics()
        self._refresh_overview_cards()

        if self.stack.currentIndex() == 1 and self.selected_line_name:
            self._load_detail(self.selected_line_name)

    refresh_page = refresh
    load_data = refresh

    def _refresh_overview_metrics(self) -> None:
        total_lines = len(self.line_summaries)
        total_cavities = sum(int(row["total_cavities"] or 0) for row in self.line_summaries)
        free = sum(int(row["free_cavities"] or 0) for row in self.line_summaries)
        breakdown = sum(int(row["breakdown_cavities"] or 0) for row in self.line_summaries)
        used = sum(int(row["used_cavities"] or 0) for row in self.line_summaries)

        self.overview_metric_labels["lines"].setText(str(total_lines))
        self.overview_metric_labels["total"].setText(str(total_cavities))
        self.overview_metric_labels["free"].setText(str(free))
        self.overview_metric_labels["attention"].setText(str(breakdown + used))

    def _refresh_overview_cards(self) -> None:
        while self.line_grid.count():
            item = self.line_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        for index, summary in enumerate(self.line_summaries):
            card = self._line_overview_card(summary)
            self.line_grid.addWidget(card, index // 3, index % 3)

        for col in range(3):
            self.line_grid.setColumnStretch(col, 1)

    def _line_overview_card(self, summary: dict) -> QFrame:
        line_name = str(summary["line_name"])
        total = int(summary["total_cavities"] or 0)
        active = int(summary["active_cavities"] or 0)
        breakdown = int(summary["breakdown_cavities"] or 0)
        used = int(summary["used_cavities"] or 0)
        free = int(summary["free_cavities"] or 0)
        used_count = used

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
        numbers.addWidget(self._small_stat(str(breakdown), "Breakdown", warning=breakdown > 0))
        numbers.addWidget(self._small_stat(str(free), "Free"))
        numbers.addWidget(self._small_stat(str(used_count), "Used", warning=used_count > 0))

        layout.addLayout(header)
        layout.addWidget(description_label)
        layout.addStretch()
        layout.addLayout(numbers)

        card.mousePressEvent = lambda event, name=line_name: self._open_line_board(name)

        self._apply_shadow(card)
        return card

    def _small_stat(self, value: str, label: str, warning: bool = False) -> QWidget:
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



    def _cavity_status_combo_style(self, status: str) -> str:
        status_text = str(status or "").strip().lower()

        if status_text == "breakdown":
            return """
                QComboBox {
                    background: #fee2e2;
                    color: #991b1b;
                    border: 1px solid #fca5a5;
                    border-radius: 9px;
                    padding: 6px 26px 6px 10px;
                    font-size: 8.5pt;
                    font-weight: 950;
                }

                QComboBox:hover {
                    background: #fecaca;
                    border: 1px solid #ef4444;
                }

                QComboBox::drop-down {
                    border: none;
                    width: 22px;
                }

                QComboBox QAbstractItemView {
                    background: #ffffff;
                    color: #0f172a;
                    border: 1px solid #cbd5e1;
                    selection-background-color: #fee2e2;
                    selection-color: #991b1b;
                }
            """

        return """
            QComboBox {
                background: #dcfce7;
                color: #166534;
                border: 1px solid #86efac;
                border-radius: 9px;
                padding: 6px 26px 6px 10px;
                font-size: 8.5pt;
                font-weight: 950;
            }

            QComboBox:hover {
                background: #bbf7d0;
                border: 1px solid #22c55e;
            }

            QComboBox::drop-down {
                border: none;
                width: 22px;
            }

            QComboBox QAbstractItemView {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                selection-background-color: #dcfce7;
                selection-color: #166534;
            }
        """

    def _style_cavity_status_combos(self) -> None:
        table_candidates = []

        for attr_name in ("table", "cavity_table", "cavities_table", "detail_table"):
            table = getattr(self, attr_name, None)
            if table is not None and hasattr(table, "cellWidget"):
                table_candidates.append(table)

        seen = set()

        for table in table_candidates:
            table_id = id(table)
            if table_id in seen:
                continue
            seen.add(table_id)

            for row_index in range(table.rowCount()):
                combo = table.cellWidget(row_index, 1)

                if combo is None or not hasattr(combo, "currentText"):
                    continue

                combo.setStyleSheet(self._cavity_status_combo_style(combo.currentText()))

                if not combo.property("statusStyleConnected"):
                    combo.currentTextChanged.connect(
                        lambda _text="", c=combo: c.setStyleSheet(
                            self._cavity_status_combo_style(c.currentText())
                        )
                    )
                    combo.setProperty("statusStyleConnected", True)


    def handle_back_navigation(self) -> bool:
        """
        Called by MainWindow before global Backspace navigation.
        If a cavity line detail board is open, Backspace should behave exactly
        like the 'Back to Boards' button.
        """
        try:
            if hasattr(self, "stack") and self.stack.currentIndex() != 0:
                if hasattr(self, "_back_to_overview"):
                    self._back_to_overview()
                else:
                    self.stack.setCurrentIndex(0)
                return True
        except Exception:
            return False

        return False

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Backspace:
            if self.handle_back_navigation():
                event.accept()
                return

        super().keyPressEvent(event)


    def _open_line_board(self, line_name: str) -> None:
        self.selected_line_name = line_name
        self._load_detail(line_name)
        self.stack.setCurrentIndex(1)
        QTimer.singleShot(0, self._style_cavity_status_combos)

    def _back_to_overview(self) -> None:
        self.refresh()
        self.stack.setCurrentIndex(0)

    def _load_detail(self, line_name: str) -> None:
        self.cavities = self.repo.list_cavities(line_name)

        family, _description = LINE_INFO.get(line_name, ("Custom Production Line", ""))

        self.detail_title.setText(f"{line_name} Cavity Board")
        self.detail_subtitle.setText(
            f"{family}. Add/edit/delete cavities. Operational + no assigned tyre item = Available."
        )

        self._refresh_detail_metrics()
        self._refresh_table()
        QTimer.singleShot(0, self._style_cavity_status_combos)

    def _refresh_detail_metrics(self) -> None:
        total = len(self.cavities)
        active = sum(1 for item in self.cavities if item.get("status") == "Active")
        breakdown = sum(1 for item in self.cavities if item.get("status") == "Breakdown")
        used = sum(1 for item in self.cavities if item.get("assigned_tyre_item", "") != "")
        free = sum(
            1
            for item in self.cavities
            if item.get("status") == "Active" and item.get("assigned_tyre_item", "") == ""
        )

        self.detail_metric_labels["total"].setText(str(total))
        self.detail_metric_labels["active"].setText(str(active))
        self.detail_metric_labels["breakdown"].setText(str(breakdown))
        self.detail_metric_labels["used"].setText(str(used))
        self.detail_metric_labels["free"].setText(str(free))

    def _refresh_table(self) -> None:
        self.table.setRowCount(len(self.cavities))

        for row_index, row in enumerate(self.cavities):
            self.table.setRowHeight(row_index, 54)

            cavity_code = row.get("cavity_code") or f"Cavity {row.get('cavity_no', '')}"

            code_item = QTableWidgetItem(str(cavity_code))
            code_item.setFlags(code_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, 0, code_item)

            status = row.get("status", "Active")
            status_dropdown = QComboBox()
            status_dropdown.setObjectName("StatusDropdown")
            status_dropdown.addItems(["Operational", "Breakdown"])
            status_dropdown.setCurrentText("Breakdown" if status == "Breakdown" else "Operational")
            status_dropdown.currentTextChanged.connect(
                lambda value, cavity_id=row["id"]: self._change_cavity_status(cavity_id, value)
            )
            self.table.setCellWidget(row_index, 1, status_dropdown)

            assigned_item = row.get("assigned_tyre_item", "")
            load_label = QLabel("Assigned" if assigned_item else "Available")
            load_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            load_label.setObjectName("StatusUsed" if assigned_item else "StatusFree")
            self.table.setCellWidget(row_index, 2, load_label)

            tyre_item = QTableWidgetItem(assigned_item if assigned_item else "-")
            tyre_item.setFlags(tyre_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, 3, tyre_item)

            remarks_item = QTableWidgetItem(row.get("remarks", ""))
            remarks_item.setFlags(remarks_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row_index, 4, remarks_item)

            action_widget = QWidget()
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



    def _change_cavity_status(self, cavity_id: int, ui_status: str) -> None:
        db_status = "Breakdown" if ui_status == "Breakdown" else "Active"

        try:
            self.repo.update_cavity_status(cavity_id, db_status)
        except Exception as exc:
            QMessageBox.critical(self, "Status Update Failed", f"Could not update cavity status.\n\n{exc}")
            return

        self._load_detail(self.selected_line_name)

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
        box.setText(f"{self.selected_line_name}\n{cavity_code}")
        box.setInformativeText("Choose what you want to do with this cavity.")
        box.setIcon(QMessageBox.Icon.Question)

        edit_button = box.addButton("Edit", QMessageBox.ButtonRole.AcceptRole)
        delete_button = box.addButton("Retire", QMessageBox.ButtonRole.DestructiveRole)
        cancel_button = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)

        box.exec()
        clicked = box.clickedButton()

        if clicked == edit_button:
            self._edit_cavity(cavity_id)
        elif clicked == delete_button:
            self._delete_cavity(cavity_id)
        elif clicked == cancel_button:
            return

    def _add_cavity(self) -> None:
        if not self.selected_line_name:
            return

        dialog = CavityDialog(self, line_name=self.selected_line_name)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()

        try:
            self.repo.add_cavity(
                line_name=self.selected_line_name,
                cavity_code=data["cavity_code"],
                status=data["status"],
                assigned_tyre_item=data["assigned_tyre_item"],
                remarks=data["remarks"],
            )
        except Exception as exc:
            QMessageBox.critical(self, "Add Failed", f"Could not add cavity.\n\n{exc}")
            return

        self._load_detail(self.selected_line_name)

    def _edit_cavity(self, cavity_id: int) -> None:
        row = None

        for item in self.cavities:
            if item["id"] == cavity_id:
                row = item
                break

        if row is None:
            return

        dialog = CavityDialog(self, line_name=self.selected_line_name, row=row)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()

        try:
            self.repo.update_cavity(
                cavity_id=cavity_id,
                line_name=self.selected_line_name,
                cavity_code=data["cavity_code"],
                status=data["status"],
                assigned_tyre_item=data["assigned_tyre_item"],
                remarks=data["remarks"],
            )
        except Exception as exc:
            QMessageBox.critical(self, "Update Failed", f"Could not update cavity.\n\n{exc}")
            return

        self._load_detail(self.selected_line_name)

    def _delete_cavity(self, cavity_id: int) -> None:
        row = None

        for item in self.cavities:
            if item["id"] == cavity_id:
                row = item
                break

        if row is None:
            return

        cavity_code = row.get("cavity_code") or f"Cavity {row.get('cavity_no', '')}"

        confirm = QMessageBox.question(
            self,
            "Retire Cavity",
            f"Retire {cavity_code} from {self.selected_line_name}? Historical evidence will be retained.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if confirm != QMessageBox.StandardButton.Yes:
            return

        try:
            self.repo.delete_cavity(cavity_id)
        except Exception as exc:
            QMessageBox.critical(self, "Retire Failed", f"Could not delete cavity.\n\n{exc}")
            return

        self._load_detail(self.selected_line_name)


CavityMasterPage = CavitiesMasterPage
