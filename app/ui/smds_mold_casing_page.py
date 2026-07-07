from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import text

from app.database import engine


def _clean_display(value, *, no_casing: bool = False) -> str:
    text_value = str(value or "").strip()

    if not text_value or text_value.upper() in {"NULL", "NONE", "N/A", "NA"}:
        return "-"

    normalized = text_value.lower().replace("-", " ").replace("_", " ")
    normalized = " ".join(normalized.split())

    if no_casing and normalized in {"no casing", "nocasing", "without casing", "without tyre casing"}:
        return "No Casing"

    return text_value


class SmdsMoldCasingRepository:
    def __init__(self) -> None:
        self._columns_cache: set[str] | None = None
        self.ensure_ready()

    def _columns(self) -> set[str]:
        if self._columns_cache is None:
            with engine.connect() as conn:
                rows = conn.execute(
                    text(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = 'public'
                          AND table_name = 'smds'
                        """
                    )
                ).mappings().all()

            self._columns_cache = {str(row["column_name"]) for row in rows}

        return self._columns_cache

    def _has_column(self, name: str) -> bool:
        return name in self._columns()

    def _description_column(self) -> str:
        if self._has_column("material_description"):
            return "material_description"

        if self._has_column("description"):
            return "description"

        return "''"

    def ensure_ready(self) -> None:
        with engine.begin() as conn:
            exists = conn.execute(text("SELECT to_regclass('public.smds')")).scalar()

            if exists is None:
                raise RuntimeError(
                    "SMDS table does not exist. Import SMDS first, then open Mold & Casing Rules."
                )

            conn.execute(
                text(
                    """
                    ALTER TABLE smds
                    ADD COLUMN IF NOT EXISTS key_code TEXT NOT NULL DEFAULT '-'
                    """
                )
            )
            conn.execute(
                text(
                    """
                    ALTER TABLE smds
                    ADD COLUMN IF NOT EXISTS casing_type TEXT NOT NULL DEFAULT '-'
                    """
                )
            )

            conn.execute(
                text(
                    """
                    UPDATE smds
                    SET key_code = '-'
                    WHERE key_code IS NULL OR BTRIM(CAST(key_code AS TEXT)) = ''
                    """
                )
            )
            conn.execute(
                text(
                    """
                    UPDATE smds
                    SET casing_type =
                        CASE
                            WHEN casing_type IS NULL OR BTRIM(CAST(casing_type AS TEXT)) = '' THEN '-'
                            WHEN LOWER(BTRIM(CAST(casing_type AS TEXT))) IN (
                                'no casing', 'nocasing', 'no-casing', 'without casing'
                            ) THEN 'No Casing'
                            ELSE BTRIM(CAST(casing_type AS TEXT))
                        END
                    """
                )
            )

        self._columns_cache = None

        try:
            self.recreate_view()
        except Exception:
            pass

    def recreate_view(self) -> None:
        description_col = self._description_column()

        with engine.begin() as conn:
            conn.execute(text("DROP VIEW IF EXISTS smds_mold_casing_rules"))
            conn.execute(
                text(
                    f"""
                    CREATE VIEW smds_mold_casing_rules AS
                    SELECT
                        id,
                        sap_code,
                        {description_col} AS material_description,
                        key_code AS mold_key_code,
                        casing_type
                    FROM smds
                    """
                )
            )

    def stats(self) -> dict:
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS total_items,
                        COUNT(DISTINCT NULLIF(BTRIM(key_code), '-')) AS mold_keys,
                        COUNT(*) FILTER (WHERE casing_type = 'No Casing') AS no_casing_items,
                        COUNT(*) FILTER (
                            WHERE casing_type IS NULL OR BTRIM(casing_type) = '' OR BTRIM(casing_type) = '-'
                        ) AS unknown_casing_items
                    FROM smds
                    """
                )
            ).mappings().one()

        return dict(row)

    def casing_options(self) -> list[str]:
        with engine.connect() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT DISTINCT casing_type
                    FROM smds
                    WHERE casing_type IS NOT NULL
                      AND BTRIM(casing_type) <> ''
                    ORDER BY casing_type
                    """
                )
            ).scalars().all()

        options: list[str] = ["-", "No Casing"]

        for value in rows:
            cleaned = _clean_display(value, no_casing=True)

            if cleaned not in options:
                options.append(cleaned)

        return options

    def list_rows(self, search_text: str = "", limit: int = 1200) -> list[dict]:
        search = (search_text or "").strip()
        description_col = self._description_column()

        sql = f"""
            SELECT
                id,
                sap_code,
                {description_col} AS material_description,
                key_code,
                casing_type
            FROM smds
            WHERE 1 = 1
        """
        params: dict[str, object] = {"limit": int(limit)}

        if search:
            sql += f"""
                AND (
                    CAST(sap_code AS TEXT) ILIKE :search
                    OR CAST({description_col} AS TEXT) ILIKE :search
                    OR CAST(key_code AS TEXT) ILIKE :search
                    OR CAST(casing_type AS TEXT) ILIKE :search
                )
            """
            params["search"] = f"%{search}%"

        sql += """
            ORDER BY
                CASE WHEN key_code IS NULL OR BTRIM(CAST(key_code AS TEXT)) = '' OR BTRIM(CAST(key_code AS TEXT)) = '-' THEN 1 ELSE 0 END,
                key_code,
                sap_code
            LIMIT :limit
        """

        with engine.connect() as conn:
            rows = conn.execute(text(sql), params).mappings().all()

        return [dict(row) for row in rows]

    def get_row(self, row_id: int) -> dict:
        description_col = self._description_column()

        with engine.connect() as conn:
            row = conn.execute(
                text(
                    f"""
                    SELECT
                        id,
                        sap_code,
                        {description_col} AS material_description,
                        key_code,
                        casing_type
                    FROM smds
                    WHERE id = :id
                    """
                ),
                {"id": row_id},
            ).mappings().one()

        return dict(row)

    def update_rule(self, row_id: int, mold_key_code: str, casing_type: str) -> None:
        mold_key = _clean_display(mold_key_code)
        casing = _clean_display(casing_type, no_casing=True)

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE smds
                    SET key_code = :key_code,
                        casing_type = :casing_type
                    WHERE id = :id
                    """
                ),
                {
                    "id": row_id,
                    "key_code": mold_key,
                    "casing_type": casing,
                },
            )


class SmdsMoldCasingDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        row: dict,
        casing_options: list[str],
    ) -> None:
        super().__init__(parent)

        self.setWindowTitle("Edit SMDS Mold & Casing Rule")
        self.setMinimumWidth(680)

        self.row = row
        self.casing_options = casing_options

        self.setStyleSheet(
            """
            QDialog {
                background: #f8fafc;
            }

            QLabel#DialogTitle {
                color: #0f172a;
                font-size: 18pt;
                font-weight: 950;
            }

            QLabel#InfoText {
                color: #334155;
                font-size: 9.2pt;
                font-weight: 650;
            }

            QLineEdit, QComboBox {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 9px 11px;
                color: #0f172a;
                font-size: 9.5pt;
                font-weight: 650;
            }

            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #2563eb;
            }
            """
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 20)
        root.setSpacing(16)

        title = QLabel("Edit Mold & Casing Rule")
        title.setObjectName("DialogTitle")
        root.addWidget(title)

        sap_label = QLabel(f"SAP Code: {row.get('sap_code', '-')}")
        sap_label.setObjectName("InfoText")

        desc_label = QLabel(f"Description: {row.get('material_description', '-')}")
        desc_label.setObjectName("InfoText")
        desc_label.setWordWrap(True)

        root.addWidget(sap_label)
        root.addWidget(desc_label)

        hint = QLabel(
            "Mold Key Code saves to SMDS key_code. Casing Type saves to SMDS casing_type. "
            "Use 'No Casing' when the item does not need a casing. Use '-' when the casing is unknown."
        )
        hint.setObjectName("InfoText")
        hint.setWordWrap(True)
        root.addWidget(hint)

        form = QFormLayout()
        form.setHorizontalSpacing(14)
        form.setVerticalSpacing(12)

        self.mold_key_input = QLineEdit(_clean_display(row.get("key_code", "")))
        self.mold_key_input.setPlaceholderText("Mold key code / Key Code")

        self.casing_input = QComboBox()
        self.casing_input.setEditable(True)

        for option in casing_options:
            self.casing_input.addItem(option)

        current_casing = _clean_display(row.get("casing_type", ""), no_casing=True)

        if current_casing not in casing_options:
            self.casing_input.addItem(current_casing)

        self.casing_input.setCurrentText(current_casing)

        form.addRow("Mold Key Code", self.mold_key_input)
        form.addRow("Casing Type", self.casing_input)

        root.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        root.addWidget(buttons)

    def data(self) -> dict:
        return {
            "key_code": _clean_display(self.mold_key_input.text()),
            "casing_type": _clean_display(self.casing_input.currentText(), no_casing=True),
        }


class SmdsMoldCasingPage(QWidget):
    def __init__(self, on_back: Callable[[], None] | None = None) -> None:
        super().__init__()

        self.on_back = on_back
        self.repo = SmdsMoldCasingRepository()
        self.rows: list[dict] = []

        self.setStyleSheet(
            """
            QFrame#PageCard,
            QFrame#MetricCard,
            QFrame#DataSection {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 20px;
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

            QLabel#PageSubtitle,
            QLabel#SectionSubtitle {
                color: #64748b;
                font-size: 9.2pt;
                font-weight: 650;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 16pt;
                font-weight: 950;
            }

            QLabel#CountBadge {
                background: #eef2ff;
                color: #1d4ed8;
                border: 1px solid #c7d2fe;
                border-radius: 11px;
                padding: 7px 12px;
                font-size: 8.5pt;
                font-weight: 950;
            }

            QLabel#MetricTitle {
                color: #0f172a;
                font-size: 18pt;
                font-weight: 950;
            }

            QLabel#MetricHint {
                color: #64748b;
                font-size: 8.8pt;
                font-weight: 800;
            }

            QPushButton#SecondaryButton {
                background: #e2e8f0;
                color: #0f172a;
                border: none;
                border-radius: 11px;
                padding: 10px 16px;
                font-size: 9pt;
                font-weight: 950;
            }

            QPushButton#SecondaryButton:hover {
                background: #cbd5e1;
            }

            QPushButton#ManageButton {
                background: #eef2ff;
                color: #1d4ed8;
                border: 1px solid #c7d2fe;
                border-radius: 10px;
                padding: 7px 12px;
                font-size: 8.3pt;
                font-weight: 950;
                min-width: 86px;
            }

            QPushButton#ManageButton:hover {
                background: #dbeafe;
            }

            QLineEdit {
                background: #ffffff;
                border: 1px solid #cbd5e1;
                border-radius: 10px;
                padding: 9px 12px;
                color: #0f172a;
                font-size: 9pt;
                font-weight: 650;
            }

            QLineEdit:focus {
                border: 1px solid #2563eb;
            }

            QTableWidget {
                background: #ffffff;
                border: 1px solid #e2e8f0;
                border-radius: 14px;
                gridline-color: #e2e8f0;
                color: #0f172a;
                font-size: 9pt;
                font-weight: 700;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }

            QTableWidget::item {
                padding: 9px;
            }

            QHeaderView::section {
                background: #f8fafc;
                color: #334155;
                border: none;
                border-bottom: 1px solid #e2e8f0;
                padding: 12px;
                font-size: 8.5pt;
                font-weight: 950;
            }
            """
        )

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        card = QFrame()
        card.setObjectName("PageCard")

        layout = QVBoxLayout(card)
        layout.setContentsMargins(22, 18, 22, 22)
        layout.setSpacing(18)

        layout.addLayout(self._header())
        layout.addLayout(self._metrics())
        layout.addWidget(self._table_section(), 1)

        root.addWidget(card, 1)

    def _header(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(14)

        text_area = QVBoxLayout()
        text_area.setSpacing(8)

        breadcrumb = QLabel("Master Data  /  Tyre Item Master  /  Mold & Casing Rules")
        breadcrumb.setObjectName("Breadcrumb")

        title = QLabel("Mold & Casing Rules")
        title.setObjectName("PageTitle")

        subtitle = QLabel(
            "Maintain SAP-code wise mold key code and casing type directly in the central SMDS table."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)

        text_area.addWidget(breadcrumb)
        text_area.addWidget(title)
        text_area.addWidget(subtitle)

        back_button = QPushButton("Back to Tyre Master")
        back_button.setObjectName("SecondaryButton")
        back_button.clicked.connect(self._back)

        layout.addLayout(text_area, 1)
        layout.addWidget(back_button)

        return layout

    def _metrics(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setSpacing(12)

        self.total_items_metric = self._metric_card(layout, "0", "SMDS Items")
        self.mold_keys_metric = self._metric_card(layout, "0", "Mold Keys")
        self.no_casing_metric = self._metric_card(layout, "0", "No Casing Items")
        self.unknown_casing_metric = self._metric_card(layout, "0", "Unknown Casing")

        return layout

    def _metric_card(self, parent_layout: QHBoxLayout, value_text: str, hint_text: str) -> QLabel:
        card = QFrame()
        card.setObjectName("MetricCard")
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(5)

        value = QLabel(value_text)
        value.setObjectName("MetricTitle")

        hint = QLabel(hint_text)
        hint.setObjectName("MetricHint")

        layout.addWidget(value)
        layout.addWidget(hint)

        parent_layout.addWidget(card)
        return value

    def _table_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("DataSection")

        layout = QVBoxLayout(section)
        layout.setContentsMargins(20, 18, 20, 20)
        layout.setSpacing(14)

        top = QHBoxLayout()
        top.setSpacing(12)

        title_area = QVBoxLayout()
        title_area.setSpacing(5)

        title = QLabel("SAP Code / Mold Key / Casing Type")
        title.setObjectName("SectionTitle")

        subtitle = QLabel(
            "Key Code is treated as the mold code. Unknown values are shown as '-'. "
            "Double-click a row or use Edit to update SMDS."
        )
        subtitle.setObjectName("SectionSubtitle")
        subtitle.setWordWrap(True)

        title_area.addWidget(title)
        title_area.addWidget(subtitle)

        self.count_badge = QLabel("0 Items")
        self.count_badge.setObjectName("CountBadge")
        self.count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search SAP, description, mold key or casing type...")
        self.search_input.setMinimumWidth(420)
        self.search_input.textChanged.connect(self.refresh)

        refresh_button = QPushButton("Refresh")
        refresh_button.setObjectName("SecondaryButton")
        refresh_button.clicked.connect(self.refresh)

        top.addLayout(title_area, 1)
        top.addWidget(self.count_badge)
        top.addWidget(self.search_input)
        top.addWidget(refresh_button)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "SAP Code",
            "Description",
            "Mold Key Code",
            "Casing Type",
            "Action",
        ])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.cellDoubleClicked.connect(self._edit_from_row)

        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)

        self.table.setColumnWidth(0, 155)
        self.table.setColumnWidth(2, 230)
        self.table.setColumnWidth(3, 160)
        self.table.setColumnWidth(4, 130)

        layout.addLayout(top)
        layout.addWidget(self.table, 1)

        return section

    def _back(self) -> None:
        if callable(self.on_back):
            self.on_back()

    def refresh(self) -> None:
        stats = {}

        try:
            stats = self.repo.stats()
            search_text = self.search_input.text().strip() if hasattr(self, "search_input") else ""
            self.rows = self.repo.list_rows(search_text)
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Could not load SMDS mold/casing rules.\n\n{exc}")
            self.rows = []

        if hasattr(self, "total_items_metric"):
            self.total_items_metric.setText(str(stats.get("total_items", 0)))
            self.mold_keys_metric.setText(str(stats.get("mold_keys", 0)))
            self.no_casing_metric.setText(str(stats.get("no_casing_items", 0)))
            self.unknown_casing_metric.setText(str(stats.get("unknown_casing_items", 0)))

        self.count_badge.setText(f"{len(self.rows)} Items / showing first 1200")
        self.table.setRowCount(len(self.rows))

        for row_index, row in enumerate(self.rows):
            self.table.setRowHeight(row_index, 58)

            self._set_item(row_index, 0, row.get("sap_code", ""), center=True)
            self._set_item(row_index, 1, row.get("material_description", ""))
            self._set_item(row_index, 2, _clean_display(row.get("key_code", "")))
            self._set_item(row_index, 3, _clean_display(row.get("casing_type", ""), no_casing=True), center=True)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(6, 5, 6, 5)

            edit_button = QPushButton("Edit")
            edit_button.setObjectName("ManageButton")
            edit_button.clicked.connect(lambda checked=False, row_id=row["id"]: self._edit_rule(row_id))

            action_layout.addStretch()
            action_layout.addWidget(edit_button)
            action_layout.addStretch()

            self.table.setCellWidget(row_index, 4, action_widget)

    def _set_item(self, row_index: int, col_index: int, value, center: bool = False) -> None:
        item = QTableWidgetItem(str(value if value is not None else "-"))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

        if center:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        self.table.setItem(row_index, col_index, item)

    def _edit_from_row(self, row_index: int, column_index: int) -> None:
        if row_index < 0 or row_index >= len(self.rows):
            return

        row_id = self.rows[row_index].get("id")

        if row_id is not None:
            self._edit_rule(int(row_id))

    def _edit_rule(self, row_id: int) -> None:
        try:
            row = self.repo.get_row(row_id)
            options = self.repo.casing_options()
        except Exception as exc:
            QMessageBox.critical(self, "Database Error", f"Could not load selected SMDS row.\n\n{exc}")
            return

        dialog = SmdsMoldCasingDialog(self, row, options)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        data = dialog.data()

        try:
            self.repo.update_rule(row_id, data["key_code"], data["casing_type"])
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", f"Could not update SMDS mold/casing rule.\n\n{exc}")
            return

        self.refresh()
