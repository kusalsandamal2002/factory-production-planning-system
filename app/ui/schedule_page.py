from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCore import QDate, QObject, QThread, Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.database import get_session
from app.services.operational_source_service import OperationalSourceService
from app.services.cavity_daily_plan_service import (
    BlockedDemand,
    CavityPlanRow,
    CavityPlanSettings,
    CavityPlanSummary,
    generate_cavity_plan,
    load_latest_saved_plan,
    save_cavity_plan,
)
from app.utils.reports_export import export_to_csv


OVEN_STATUS_OPTIONS = [
    "ALL",
    "ASSIGNED",
    "AVAILABLE / FREE",
    "CURRENTLY ASSIGNED",
    "BREAKDOWN",
]

TABLE_HEADERS = [
    "Line Name",
    "Oven No",
    "Oven Status",
    "Tyre Code",
    "Description",
    "HEEL",
    "SOFT",
    "Tred",
    "Remark",
    "Total To be produced",
    "TODAY",
    "Day Plan Pcs",
    "Night Plan Pcs",
    "CORE",
    "NEXT DAY PLAN",
    "Total",
    "Weight per Tyre (Kg)",
    "Day Plan Weight",
    "Night Plan Weight",
    "Total Plan",
    "Balance",
    "CASING TYPE",
    "Mold Type",
]

COLUMN_WIDTHS = [
    130,
    170,
    150,
    110,
    300,
    110,
    110,
    140,
    280,
    145,
    90,
    110,
    115,
    90,
    125,
    95,
    135,
    125,
    130,
    105,
    100,
    125,
    150,
]


# PRODUCTION PLANNING FAST ASYNC LOAD V7.1
# MPPS ULTRA PERFORMANCE + GLOBAL PROGRESS V7.2


class _PlanGenerationWorker(QObject):
    result_ready = Signal(object, object, object)
    progress = Signal(int, str)
    failed = Signal(str)

    def __init__(self, settings: CavityPlanSettings):
        super().__init__()
        self.settings = settings

    @Slot()
    def run(self) -> None:
        try:
            with get_session() as session:
                rows, summary, blocked = generate_cavity_plan(
                    session,
                    settings=self.settings,
                    progress_callback=(
                        lambda percent, message:
                        self.progress.emit(percent, message)
                    ),
                )
            self.result_ready.emit(rows, summary, blocked)
        except Exception as exc:
            self.failed.emit(str(exc))



class SchedulePage(QWidget):
    """Cavity-level daily production scheduling page."""

    def __init__(self, current_user=None):
        super().__init__()
        self.current_user = current_user
        self.plan_rows: list[CavityPlanRow] = []
        self.visible_rows: list[CavityPlanRow] = []
        self.blocked_rows: list[BlockedDemand] = []
        self.summary: CavityPlanSummary | None = None
        self.current_run_id: int | None = None
        self.preview_is_saved = False
        self._auto_refresh_pending = False
        self._plan_thread: QThread | None = None
        self._plan_worker: _PlanGenerationWorker | None = None

        self.plan_date = QDateEdit()
        self.plan_date.setCalendarPopup(True)
        self.plan_date.setDisplayFormat("yyyy-MM-dd")
        initial_date = date.today()
        try:
            with get_session() as session:
                initial_date = OperationalSourceService.next_plan_date(session, fallback=date.today())
        except Exception:
            initial_date = date.today()
        self.plan_date.setDate(QDate(initial_date.year, initial_date.month, initial_date.day))
        self.plan_date.setToolTip(
            "Defaults to the day after the newest LIVE OVEN workbook. Older workbooks remain history/ML only."
        )
        self.plan_date.dateChanged.connect(
            self._load_saved_or_preview
        )

        self.shift_selector = QComboBox()
        self.shift_selector.addItem(
            "ALL SHIFTS (07:00 - 07:00)",
            "ALL",
        )
        self.shift_selector.addItem(
            "DAY SHIFT (07:00 - 19:00)",
            "DAY",
        )
        self.shift_selector.addItem(
            "NIGHT SHIFT (19:00 - 07:00)",
            "NIGHT",
        )
        self.shift_selector.setMinimumWidth(230)
        self.shift_selector.setToolTip(
            "Select the fixed factory shift to generate."
        )
        self.shift_selector.currentIndexChanged.connect(
            self._on_shift_changed
        )

        self.changeover_minutes = QSpinBox()
        self.changeover_minutes.setRange(0, 240)
        self.changeover_minutes.setValue(0)
        self.changeover_minutes.setSuffix(" min")

        self.line_combo = QComboBox()
        self.line_combo.addItem("ALL LINES")
        self.line_combo.currentTextChanged.connect(
            self.filter_table
        )

        self.status_combo = QComboBox()
        self.status_combo.addItems(
            OVEN_STATUS_OPTIONS
        )
        self.status_combo.currentTextChanged.connect(
            self.filter_table
        )

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Search line, oven, tyre code, description, "
            "mold, casing or remark..."
        )
        self.search_input.textChanged.connect(
            self.filter_table
        )

        self.refresh_button = QPushButton(
            "Refresh Saved"
        )
        self.refresh_button.setObjectName(
            "SecondaryButton"
        )
        self.refresh_button.clicked.connect(
            self._load_saved_or_preview
        )

        self.recalculate_button = QPushButton(
            "Recalculate Plan"
        )
        self.recalculate_button.setObjectName(
            "PrimaryButton"
        )
        self.recalculate_button.clicked.connect(
            self.recalculate_plan
        )

        self.save_button = QPushButton("Save Plan")
        self.save_button.setObjectName("SuccessButton")
        self.save_button.clicked.connect(
            self.save_plan
        )

        self.export_button = QPushButton("Export CSV")
        self.export_button.setObjectName(
            "SecondaryButton"
        )
        self.export_button.clicked.connect(
            self.export_csv
        )

        self.status_badge = QLabel("NO DATA")
        self.status_badge.setObjectName("StatusBadge")
        self.saved_badge = QLabel("PREVIEW")
        self.saved_badge.setObjectName("PreviewBadge")

        self.plan_progress = QProgressBar()
        self.plan_progress.setRange(0, 100)
        self.plan_progress.setValue(0)
        self.plan_progress.setFormat("%p%")
        self.plan_progress.setTextVisible(True)
        self.plan_progress.setMinimumHeight(22)
        self.plan_progress_label = QLabel(
            "Planner ready"
        )
        self.plan_progress_label.setWordWrap(True)
        self.plan_progress_label.setStyleSheet(
            "color:#475569; font-weight:800;"
        )

        self.metric_labels = {
            "total_cavities": QLabel("0"),
            "breakdown": QLabel("0"),
            "currently_assigned": QLabel("0"),
            "planned_cavities": QLabel("0"),
            "free": QLabel("0"),
            "required": QLabel("0"),
            "today": QLabel("0"),
            "next_day": QLabel("0"),
            "balance": QLabel("0"),
            "tons": QLabel("0.000"),
        }

        self.table = QTableWidget(
            0,
            len(TABLE_HEADERS),
        )
        self.table.setHorizontalHeaderLabels(
            TABLE_HEADERS
        )

        self.blocked_table = QTableWidget(0, 6)
        self.blocked_table.setHorizontalHeaderLabels(
            [
                "SAP Code",
                "Description",
                "Required Qty",
                "Approval",
                "Due Date",
                "Reason",
            ]
        )

        self._setup_tables()
        self._apply_styles()
        self._build_ui()
        self._load_saved_or_preview()

    def showEvent(self, event) -> None:
        # V7.1: heavy production planning is never launched from showEvent.
        # Recalculate Plan runs it in a background QThread.
        super().showEvent(event)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        header_card = QFrame()
        header_card.setObjectName("Card")
        header_layout = QVBoxLayout(header_card)
        header_layout.setContentsMargins(
            20,
            18,
            20,
            18,
        )
        header_layout.setSpacing(12)

        heading_row = QHBoxLayout()
        title_area = QVBoxLayout()
        title = QLabel(
            "Cavity-Level Daily Production Plan"
        )
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Displays every factory cavity. Automatic "
            "allocation uses approved SMDS data, shipment "
            "shortage, SAP stock, line compatibility, mold "
            "and casing concurrency, curing time, handling "
            "time and cavity operating status. Fixed shifts: "
            "DAY 07:00-19:00 and NIGHT 19:00-07:00."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("PageSubtitle")
        title_area.addWidget(title)
        title_area.addWidget(subtitle)

        heading_row.addLayout(title_area, 1)
        heading_row.addWidget(self.saved_badge)
        heading_row.addWidget(self.status_badge)
        heading_row.addWidget(self.refresh_button)
        heading_row.addWidget(
            self.recalculate_button
        )
        heading_row.addWidget(self.save_button)
        heading_row.addWidget(self.export_button)
        header_layout.addLayout(heading_row)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(10)
        progress_caption = QLabel(
            "Planning Progress"
        )
        progress_caption.setStyleSheet(
            "color:#334155; font-weight:900;"
        )
        progress_row.addWidget(progress_caption)
        progress_row.addWidget(self.plan_progress, 1)
        progress_row.addWidget(
            self.plan_progress_label,
            2,
        )
        header_layout.addLayout(progress_row)

        planning_controls = QHBoxLayout()
        planning_controls.setSpacing(9)
        planning_controls.addWidget(
            QLabel("Planning Date")
        )
        planning_controls.addWidget(self.plan_date)
        planning_controls.addWidget(
            QLabel("Shift")
        )
        planning_controls.addWidget(
            self.shift_selector
        )
        planning_controls.addWidget(
            QLabel("Tyre Changeover")
        )
        planning_controls.addWidget(
            self.changeover_minutes
        )
        planning_controls.addStretch()
        header_layout.addLayout(planning_controls)

        filters = QHBoxLayout()
        filters.setSpacing(9)
        filters.addWidget(QLabel("Line"))
        filters.addWidget(self.line_combo)
        filters.addWidget(QLabel("Oven Status"))
        filters.addWidget(self.status_combo)
        filters.addWidget(QLabel("Search"))
        filters.addWidget(self.search_input, 1)
        header_layout.addLayout(filters)

        note = QLabel(
            "Oven Status: BREAKDOWN = unavailable; "
            "CURRENTLY ASSIGNED = operational assignment "
            "already exists; ASSIGNED = generated plan; "
            "AVAILABLE / FREE = active cavity with no generated allocation. "
            "The same oven appears on multiple rows when its "
            "remaining daily time can produce another tyre type."
        )
        note.setWordWrap(True)
        note.setObjectName("AssumptionNote")
        header_layout.addWidget(note)
        root.addWidget(header_card)

        metric_layout = QGridLayout()
        metric_layout.setHorizontalSpacing(10)
        metric_layout.setVerticalSpacing(10)
        metrics = [
            ("Total Cavities", "total_cavities"),
            ("Breakdown", "breakdown"),
            (
                "Currently Assigned",
                "currently_assigned",
            ),
            ("Planned Cavities", "planned_cavities"),
            ("Free Cavities", "free"),
            ("Production Required", "required"),
            ("TODAY Planned", "today"),
            ("NEXT DAY Planned", "next_day"),
            ("Remaining Balance", "balance"),
            ("TODAY Planned Tons", "tons"),
        ]
        for index, (label, key) in enumerate(
            metrics
        ):
            metric_layout.addWidget(
                self._metric_card(
                    label,
                    self.metric_labels[key],
                ),
                index // 5,
                index % 5,
            )
        root.addLayout(metric_layout)

        table_card = QFrame()
        table_card.setObjectName("Card")
        table_layout = QVBoxLayout(table_card)
        table_layout.setContentsMargins(
            16,
            14,
            16,
            16,
        )
        table_layout.setSpacing(8)

        table_header = QHBoxLayout()
        table_title = QLabel(
            "Factory Cavity / Oven Allocation"
        )
        table_title.setObjectName("SectionTitle")
        self.row_count_label = QLabel("0 rows")
        self.row_count_label.setObjectName(
            "SectionBadge"
        )
        table_header.addWidget(table_title)
        table_header.addStretch()
        table_header.addWidget(
            self.row_count_label
        )

        table_hint = QLabel(
            "The grid always contains every cavity. "
            "Multiple sequential allocations for one oven "
            "are shown as additional rows using the same "
            "Line Name and Oven No."
        )
        table_hint.setObjectName("SectionHint")
        table_hint.setWordWrap(True)

        table_layout.addLayout(table_header)
        table_layout.addWidget(table_hint)
        table_layout.addWidget(self.table, 1)
        root.addWidget(table_card, 1)

        blocked_card = QFrame()
        blocked_card.setObjectName("Card")
        blocked_layout = QVBoxLayout(blocked_card)
        blocked_layout.setContentsMargins(
            16,
            14,
            16,
            16,
        )
        blocked_layout.setSpacing(8)

        blocked_header = QHBoxLayout()
        blocked_title = QLabel(
            "Unallocated / Blocked Production Demand"
        )
        blocked_title.setObjectName("SectionTitle")
        self.blocked_count_label = QLabel(
            "0 items"
        )
        self.blocked_count_label.setObjectName(
            "WarningBadge"
        )
        blocked_header.addWidget(blocked_title)
        blocked_header.addStretch()
        blocked_header.addWidget(
            self.blocked_count_label
        )
        blocked_layout.addLayout(blocked_header)
        blocked_layout.addWidget(
            self.blocked_table
        )
        root.addWidget(blocked_card)

    def _metric_card(
        self,
        title_text: str,
        value_label: QLabel,
    ) -> QFrame:
        card = QFrame()
        card.setObjectName("MetricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(
            14,
            10,
            14,
            10,
        )
        title = QLabel(title_text)
        title.setObjectName("MetricTitle")
        value_label.setObjectName("MetricValue")
        layout.addWidget(title)
        layout.addWidget(value_label)
        return card

    def _setup_tables(self) -> None:
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )
        self.table.setSelectionBehavior(
            QAbstractItemView
            .SelectionBehavior
            .SelectRows
        )
        self.table.setSelectionMode(
            QAbstractItemView
            .SelectionMode
            .SingleSelection
        )
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(
            44
        )
        self.table.setMinimumHeight(500)
        self.table.setSortingEnabled(False)

        header = self.table.horizontalHeader()
        header.setDefaultAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        for column, width in enumerate(
            COLUMN_WIDTHS
        ):
            header.setSectionResizeMode(
                column,
                QHeaderView.ResizeMode.Fixed,
            )
            self.table.setColumnWidth(
                column,
                width,
            )

        self.blocked_table.setEditTriggers(
            QAbstractItemView
            .EditTrigger
            .NoEditTriggers
        )
        self.blocked_table.setSelectionBehavior(
            QAbstractItemView
            .SelectionBehavior
            .SelectRows
        )
        self.blocked_table.verticalHeader().setVisible(
            False
        )
        self.blocked_table.setAlternatingRowColors(
            True
        )
        self.blocked_table.setMaximumHeight(190)
        blocked_header = (
            self.blocked_table.horizontalHeader()
        )
        blocked_header.setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.blocked_table.setColumnWidth(0, 110)
        self.blocked_table.setColumnWidth(1, 300)
        self.blocked_table.setColumnWidth(2, 110)
        self.blocked_table.setColumnWidth(3, 110)
        self.blocked_table.setColumnWidth(4, 110)
        blocked_header.setSectionResizeMode(
            5,
            QHeaderView.ResizeMode.Stretch,
        )

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#Card,
            QFrame#MetricCard {
                background: #ffffff;
                border: 1px solid #dbe4f0;
                border-radius: 15px;
            }

            QLabel#PageTitle {
                color: #0f172a;
                font-size: 20pt;
                font-weight: 950;
            }

            QLabel#PageSubtitle,
            QLabel#SectionHint,
            QLabel#AssumptionNote {
                color: #64748b;
                font-size: 9pt;
                font-weight: 650;
            }

            QLabel#SectionTitle {
                color: #0f172a;
                font-size: 14pt;
                font-weight: 950;
            }

            QLabel#MetricTitle {
                color: #64748b;
                font-size: 8pt;
                font-weight: 850;
            }

            QLabel#MetricValue {
                color: #0f172a;
                font-size: 17pt;
                font-weight: 950;
            }

            QLabel#StatusBadge,
            QLabel#PreviewBadge,
            QLabel#SectionBadge,
            QLabel#WarningBadge {
                border-radius: 9px;
                padding: 8px 11px;
                font-weight: 950;
            }

            QLabel#StatusBadge {
                background: #e2e8f0;
                color: #0f172a;
            }

            QLabel#PreviewBadge {
                background: #fef3c7;
                color: #92400e;
            }

            QLabel#SectionBadge {
                background: #dbeafe;
                color: #1d4ed8;
            }

            QLabel#WarningBadge {
                background: #fee2e2;
                color: #991b1b;
            }

            QPushButton#PrimaryButton,
            QPushButton#SuccessButton,
            QPushButton#SecondaryButton {
                border: none;
                border-radius: 9px;
                padding: 10px 14px;
                font-weight: 900;
            }

            QPushButton#PrimaryButton {
                background: #2563eb;
                color: white;
            }

            QPushButton#PrimaryButton:hover {
                background: #1d4ed8;
            }

            QPushButton#SuccessButton {
                background: #16a34a;
                color: white;
            }

            QPushButton#SuccessButton:hover {
                background: #15803d;
            }

            QPushButton#SecondaryButton {
                background: #e2e8f0;
                color: #0f172a;
            }

            QPushButton#SecondaryButton:hover {
                background: #cbd5e1;
            }

            QLineEdit,
            QComboBox,
            QDateEdit,
            QDoubleSpinBox,
            QSpinBox {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #cbd5e1;
                border-radius: 8px;
                padding: 7px 9px;
                min-height: 25px;
            }

            QTableWidget {
                background: #ffffff;
                color: #0f172a;
                border: 1px solid #dbe4f0;
                border-radius: 9px;
                gridline-color: #dbe4f0;
                alternate-background-color: #f8fafc;
                selection-background-color: #dbeafe;
                selection-color: #0f172a;
            }

            QHeaderView::section {
                background: #eef3f9;
                color: #172033;
                border: none;
                border-right: 1px solid #dbe4f0;
                border-bottom: 1px solid #dbe4f0;
                padding: 9px 6px;
                font-weight: 950;
            }
            """
        )

    def _on_shift_changed(self, *args) -> None:
        QTimer.singleShot(
            0,
            self._refresh_selected_shift_preview,
        )

    def _refresh_selected_shift_preview(self) -> None:
        if not self.isVisible():
            return

        try:
            settings = self._settings()
            with get_session() as session:
                rows, summary, blocked = generate_cavity_plan(
                    session,
                    settings=settings,
                )

            self.current_run_id = None
            self.preview_is_saved = False
            self._apply_result(rows, summary, blocked)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Shift Plan Refresh",
                str(exc),
            )

    def _settings(self) -> CavityPlanSettings:
        planning_date = self.plan_date.date().toPython()
        if not isinstance(planning_date, date):
            planning_date = date(
                planning_date.year,
                planning_date.month,
                planning_date.day,
            )

        shift_mode = str(
            self.shift_selector.currentData() or "ALL"
        ).upper()
        if shift_mode not in {"ALL", "DAY", "NIGHT"}:
            shift_mode = "ALL"

        day_minutes = 720 if shift_mode in {"ALL", "DAY"} else 0
        night_minutes = 720 if shift_mode in {"ALL", "NIGHT"} else 0

        return CavityPlanSettings(
            planning_date=planning_date,
            day_shift_minutes=day_minutes,
            night_shift_minutes=night_minutes,
            changeover_minutes=max(
                0,
                int(self.changeover_minutes.value()),
            ),
        )

    def _load_saved_or_preview(
        self,
        *args,
    ) -> None:
        """Fast page load: read a saved plan only.

        A missing saved plan no longer triggers the full cavity planner
        inside the UI page constructor. The user can recalculate in the
        background with the existing Recalculate Plan button.
        """
        try:
            settings = self._settings()
            with get_session() as session:
                saved = load_latest_saved_plan(
                    session,
                    planning_date=settings.planning_date,
                )

            if saved:
                (
                    rows,
                    summary,
                    blocked,
                    saved_settings,
                    run_id,
                ) = saved
                self._set_shift_controls(saved_settings)
                self.current_run_id = run_id
                self.preview_is_saved = True
                self._apply_result(rows, summary, blocked)
                self.plan_progress.setValue(100)
                self.plan_progress_label.setText(
                    "Saved plan loaded — 100%"
                )
                self.save_button.setEnabled(True)
                return

            self.current_run_id = None
            self.preview_is_saved = False
            self._show_no_saved_plan_state()

        except Exception as exc:
            QMessageBox.critical(
                self,
                "Production Planning",
                "Could not load the saved cavity-level "
                f"production plan.\n\n{exc}",
            )

    def _show_no_saved_plan_state(self) -> None:
        self.plan_rows = []
        self.visible_rows = []
        self.blocked_rows = []
        self.summary = None

        for key, label in self.metric_labels.items():
            label.setText("0.000" if key == "tons" else "0")

        self.status_badge.setText("READY — CLICK RECALCULATE")
        self.status_badge.setStyleSheet(
            "background:#dbeafe;"
            "color:#1d4ed8;"
            "border-radius:9px;"
            "padding:8px 11px;"
            "font-weight:950;"
        )
        self.saved_badge.setText("NO SAVED PLAN")
        self.saved_badge.setStyleSheet(
            "background:#e2e8f0;"
            "color:#334155;"
            "border-radius:9px;"
            "padding:8px 11px;"
            "font-weight:950;"
        )

        self.plan_progress.setValue(0)
        self.plan_progress_label.setText(
            "Ready — click Recalculate Plan"
        )
        self.table.setRowCount(0)
        self.blocked_table.setRowCount(0)
        self._refresh_line_filter()
        self.save_button.setEnabled(False)

    def _set_generation_running(self, running: bool) -> None:
        self.recalculate_button.setEnabled(not running)
        self.refresh_button.setEnabled(not running)
        self.save_button.setEnabled(
            (not running) and bool(self.plan_rows)
        )
        self.plan_date.setEnabled(not running)
        self.shift_selector.setEnabled(not running)
        self.changeover_minutes.setEnabled(not running)

        if running:
            self.plan_progress.setValue(0)
            self.plan_progress_label.setText(
                "Starting high-priority planner..."
            )
            self.status_badge.setText(
                "CALCULATING 0%"
            )
            self.status_badge.setStyleSheet(
                "background:#dbeafe;"
                "color:#1d4ed8;"
                "border-radius:9px;"
                "padding:8px 11px;"
                "font-weight:950;"
            )

    def recalculate_plan(self, *args) -> None:
        if (
            self._plan_thread is not None
            and self._plan_thread.isRunning()
        ):
            return

        try:
            settings = self._settings()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Invalid Shift Settings",
                str(exc),
            )
            return

        self._set_generation_running(True)
        self.current_run_id = None
        self.preview_is_saved = False

        thread = QThread(self)
        worker = _PlanGenerationWorker(settings)
        worker.moveToThread(thread)

        self._plan_thread = thread
        self._plan_worker = worker

        thread.started.connect(worker.run)
        worker.result_ready.connect(
            self._on_background_plan_ready
        )
        worker.progress.connect(
            self._on_background_plan_progress
        )
        worker.failed.connect(
            self._on_background_plan_failed
        )
        worker.result_ready.connect(
            lambda *_: thread.quit()
        )
        worker.failed.connect(
            lambda *_: thread.quit()
        )
        worker.result_ready.connect(
            lambda *_: worker.deleteLater()
        )
        worker.failed.connect(
            lambda *_: worker.deleteLater()
        )
        thread.finished.connect(
            self._on_background_thread_finished
        )
        thread.finished.connect(thread.deleteLater)
        thread.start(QThread.Priority.HighPriority)

    @Slot(int, str)
    def _on_background_plan_progress(
        self,
        percent: int,
        message: str,
    ) -> None:
        value = max(0, min(100, int(percent)))
        self.plan_progress.setValue(value)
        self.plan_progress_label.setText(
            message or "Calculating production plan..."
        )
        self.status_badge.setText(
            f"CALCULATING {value}%"
            if value < 100
            else "PLAN READY 100%"
        )

    @Slot(object, object, object)
    def _on_background_plan_ready(
        self,
        rows,
        summary,
        blocked,
    ) -> None:
        self.current_run_id = None
        self.preview_is_saved = False
        self._apply_result(rows, summary, blocked)
        self._set_generation_running(False)
        self.plan_progress.setValue(100)
        self.plan_progress_label.setText(
            "Production plan ready — 100%"
        )

        QMessageBox.information(
            self,
            "Plan Recalculated",
            (
                f"Generated {len(rows):,} display rows "
                f"for {summary.total_cavities:,} "
                "factory cavities.\n\n"
                "No plan was saved yet. Click Save Plan "
                "after reviewing the allocation."
            ),
        )

    @Slot(str)
    def _on_background_plan_failed(self, message: str) -> None:
        self._set_generation_running(False)
        self.plan_progress_label.setText(
            "Planner stopped — see error"
        )
        QMessageBox.critical(
            self,
            "Recalculate Plan",
            message,
        )

    @Slot()
    def _on_background_thread_finished(self) -> None:
        self._plan_thread = None
        self._plan_worker = None

    def save_plan(self, *args) -> None:
        if not self.plan_rows or self.summary is None:
            QMessageBox.warning(
                self,
                "Save Plan",
                "There is no generated plan to save.",
            )
            return

        try:
            settings = self._settings()
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Invalid Shift Settings",
                str(exc),
            )
            return

        confirmation = QMessageBox.question(
            self,
            "Save Cavity Plan",
            (
                "Save this cavity-level plan as the latest "
                f"plan for {settings.planning_date}"
                "?\n\nA new version will be created; older "
                "saved versions are retained."
            ),
            (
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
            ),
            QMessageBox.StandardButton.No,
        )
        if (
            confirmation
            != QMessageBox.StandardButton.Yes
        ):
            return

        try:
            with get_session() as session:
                run_id = save_cavity_plan(
                    session,
                    settings=settings,
                    rows=self.plan_rows,
                    summary=self.summary,
                    blocked=self.blocked_rows,
                    created_by=self._current_user_name(),
                )
            self.current_run_id = run_id
            self.preview_is_saved = True
            self._update_saved_badge()
            QMessageBox.information(
                self,
                "Plan Saved",
                (
                    "Cavity-level production plan saved "
                    f"successfully.\n\nRun ID: {run_id}"
                ),
            )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Save Plan Failed",
                str(exc),
            )

    def _apply_result(
        self,
        rows: list[CavityPlanRow],
        summary: CavityPlanSummary,
        blocked: list[BlockedDemand],
    ) -> None:
        self.plan_rows = rows
        self.summary = summary
        self.blocked_rows = blocked
        self._update_metrics(summary)
        self._update_saved_badge()
        self._refresh_line_filter()
        self.filter_table()
        self._populate_blocked_table()

    def _update_metrics(
        self,
        summary: CavityPlanSummary,
    ) -> None:
        values = {
            "total_cavities": (
                summary.total_cavities
            ),
            "breakdown": (
                summary.breakdown_cavities
            ),
            "currently_assigned": (
                summary.currently_assigned_cavities
            ),
            "planned_cavities": (
                summary.planned_cavities
            ),
            "free": summary.free_cavities,
            "required": (
                summary.production_required_qty
            ),
            "today": summary.today_planned_qty,
            "next_day": (
                summary.next_day_planned_qty
            ),
            "balance": (
                summary.remaining_balance_qty
            ),
        }
        for key, value in values.items():
            self.metric_labels[key].setText(
                f"{value:,}"
            )
        self.metric_labels["tons"].setText(
            f"{summary.planned_tons:,.3f}"
        )
        self.status_badge.setText(
            summary.status_text
        )

        status_styles = {
            "TWO-DAY PLAN COMPLETE": (
                "#dcfce7",
                "#166534",
            ),
            "PARTIALLY PLANNED": (
                "#fef3c7",
                "#92400e",
            ),
            "PARTIALLY BLOCKED": (
                "#ffedd5",
                "#9a3412",
            ),
            "UNPLANNED": (
                "#fee2e2",
                "#991b1b",
            ),
        }
        background, foreground = (
            status_styles.get(
                summary.status_text,
                ("#e2e8f0", "#0f172a"),
            )
        )
        self.status_badge.setStyleSheet(
            f"background:{background};"
            f"color:{foreground};"
            "border-radius:9px;"
            "padding:8px 11px;"
            "font-weight:950;"
        )

    def _update_saved_badge(self) -> None:
        if self.preview_is_saved:
            text = (
                f"SAVED RUN #{self.current_run_id}"
                if self.current_run_id
                else "SAVED"
            )
            self.saved_badge.setText(text)
            self.saved_badge.setStyleSheet(
                "background:#dcfce7;"
                "color:#166534;"
                "border-radius:9px;"
                "padding:8px 11px;"
                "font-weight:950;"
            )
        else:
            self.saved_badge.setText(
                "UNSAVED PREVIEW"
            )
            self.saved_badge.setStyleSheet(
                "background:#fef3c7;"
                "color:#92400e;"
                "border-radius:9px;"
                "padding:8px 11px;"
                "font-weight:950;"
            )

    def _set_shift_controls(
        self,
        settings: CavityPlanSettings,
    ) -> None:
        day_enabled = settings.day_shift_minutes > 0
        night_enabled = settings.night_shift_minutes > 0

        if day_enabled and night_enabled:
            shift_mode = "ALL"
        elif day_enabled:
            shift_mode = "DAY"
        elif night_enabled:
            shift_mode = "NIGHT"
        else:
            shift_mode = "ALL"

        index = self.shift_selector.findData(shift_mode)
        self.shift_selector.blockSignals(True)
        self.shift_selector.setCurrentIndex(max(0, index))
        self.shift_selector.blockSignals(False)
        self.changeover_minutes.setValue(
            settings.changeover_minutes
        )

    def _refresh_line_filter(self) -> None:
        current = self.line_combo.currentText()
        lines = sorted(
            {
                row.line_name
                for row in self.plan_rows
                if row.line_name
            }
        )
        self.line_combo.blockSignals(True)
        self.line_combo.clear()
        self.line_combo.addItem("ALL LINES")
        self.line_combo.addItems(lines)
        index = self.line_combo.findText(current)
        self.line_combo.setCurrentIndex(
            index if index >= 0 else 0
        )
        self.line_combo.blockSignals(False)

    def filter_table(self, *args) -> None:
        search = (
            self.search_input.text()
            .strip()
            .lower()
        )
        selected_line = (
            self.line_combo.currentText()
        )
        selected_status = (
            self.status_combo.currentText()
        )

        visible: list[CavityPlanRow] = []
        for row in self.plan_rows:
            if (
                selected_line != "ALL LINES"
                and row.line_name != selected_line
            ):
                continue
            if (
                selected_status != "ALL"
                and row.oven_status
                != selected_status
            ):
                continue

            searchable = " ".join(
                [
                    row.line_name,
                    row.oven_no,
                    row.oven_status,
                    row.tyre_code,
                    row.description,
                    row.heel,
                    row.soft,
                    row.tred,
                    row.remark,
                    row.core,
                    row.casing_type,
                    row.mold_type,
                    row.risk_reason,
                ]
            ).lower()
            if search and search not in searchable:
                continue
            visible.append(row)

        self.visible_rows = visible
        self._populate_table()
        self.row_count_label.setText(
            f"{len(visible):,} rows / "
            f"{len(self.plan_rows):,} total"
        )

    def _populate_table(self) -> None:
        self.table.setRowCount(0)

        for row_index, row in enumerate(
            self.visible_rows
        ):
            self.table.insertRow(row_index)
            values = [
                row.line_name,
                row.oven_no,
                row.oven_status,
                row.tyre_code or "-",
                row.description or "-",
                row.heel,
                row.soft,
                row.tred,
                row.remark,
                f"{row.total_to_be_produced:,}",
                f"{row.today_qty:,}",
                f"{row.day_plan_pcs:,}",
                f"{row.night_plan_pcs:,}",
                row.core,
                f"{row.next_day_plan:,}",
                f"{row.total:,}",
                f"{row.weight_per_tyre_kg:,.3f}",
                f"{row.day_plan_weight:,.3f}",
                f"{row.night_plan_weight:,.3f}",
                f"{row.total_plan:,}",
                f"{row.balance:,}",
                row.casing_type,
                row.mold_type,
            ]

            tooltip = self._row_tooltip(row)
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(
                    Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsEnabled
                )
                item.setToolTip(tooltip)

                if column not in {
                    0,
                    1,
                    3,
                    4,
                    5,
                    6,
                    7,
                    8,
                    13,
                    21,
                    22,
                }:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )

                if column == 2:
                    self._style_oven_status(
                        item,
                        row.oven_status,
                    )

                self.table.setItem(
                    row_index,
                    column,
                    item,
                )

    def _populate_blocked_table(self) -> None:
        self.blocked_table.setRowCount(
            len(self.blocked_rows)
        )
        self.blocked_count_label.setText(
            f"{len(self.blocked_rows):,} items"
        )

        for row_index, row in enumerate(
            self.blocked_rows
        ):
            values = [
                row.sap_code,
                row.description,
                f"{row.required_qty:,}",
                row.approval_status,
                (
                    row.due_date.isoformat()
                    if row.due_date
                    else "-"
                ),
                row.reason,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setFlags(
                    Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsEnabled
                )
                if column in {0, 2, 3, 4}:
                    item.setTextAlignment(
                        Qt.AlignmentFlag.AlignCenter
                    )
                if column == 3:
                    status = (
                        row.approval_status
                        .strip()
                        .lower()
                    )
                    if status == "approved":
                        item.setBackground(
                            QColor("#dcfce7")
                        )
                        item.setForeground(
                            QColor("#166534")
                        )
                    else:
                        item.setBackground(
                            QColor("#fef3c7")
                        )
                        item.setForeground(
                            QColor("#92400e")
                        )
                self.blocked_table.setItem(
                    row_index,
                    column,
                    item,
                )

    def _style_oven_status(
        self,
        item: QTableWidgetItem,
        status: str,
    ) -> None:
        colors = {
            "ASSIGNED": (
                "#1d4ed8",
                "#dbeafe",
            ),
            "AVAILABLE / FREE": (
                "#166534",
                "#dcfce7",
            ),
            "CURRENTLY ASSIGNED": (
                "#7c2d12",
                "#ffedd5",
            ),
            "BREAKDOWN": (
                "#991b1b",
                "#fee2e2",
            ),
        }
        foreground, background = colors.get(
            status,
            ("#475569", "#f1f5f9"),
        )
        item.setForeground(QColor(foreground))
        item.setBackground(QColor(background))
        item.setTextAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

    def _row_tooltip(
        self,
        row: CavityPlanRow,
    ) -> str:
        schedule = "-"
        if row.end_minute > row.start_minute:
            schedule = (
                f"{self._format_minute(row.start_minute)}"
                f" - "
                f"{self._format_minute(row.end_minute)}"
            )
        return (
            f"Line: {row.line_name}\n"
            f"Oven: {row.oven_no}\n"
            f"Status: {row.oven_status}\n"
            f"Sequence: {row.sequence_no}\n"
            f"Schedule: {schedule}\n"
            f"Shift: {row.shift_name or '-'}\n"
            f"Reason: {row.risk_reason or '-'}"
        )

    def export_csv(self) -> None:
        if not self.visible_rows:
            QMessageBox.warning(
                self,
                "Export CSV",
                "There are no visible cavity plan rows.",
            )
            return

        data = []
        for row in range(self.table.rowCount()):
            data.append(
                [
                    (
                        self.table
                        .item(row, column)
                        .text()
                        if self.table.item(
                            row,
                            column,
                        )
                        is not None
                        else ""
                    )
                    for column in range(
                        self.table.columnCount()
                    )
                ]
            )

        path = export_to_csv(
            TABLE_HEADERS,
            data,
            (
                "cavity_level_production_plan_"
                + self._settings()
                .planning_date
                .isoformat()
            ),
        )
        QMessageBox.information(
            self,
            "Export Complete",
            f"CSV exported to:\n\n{path}",
        )

    def _current_user_name(self) -> str:
        user = self.current_user
        if user is None:
            return ""
        if isinstance(user, dict):
            for key in (
                "username",
                "name",
                "email",
                "full_name",
            ):
                value = user.get(key)
                if value:
                    return str(value)
            return ""
        for attribute in (
            "username",
            "name",
            "email",
            "full_name",
        ):
            value: Any = getattr(
                user,
                attribute,
                None,
            )
            if value:
                return str(value)
        return str(user)

    @staticmethod
    def _format_minute(value: int) -> str:
        minute = (420 + max(0, int(value))) % 1440
        return (
            f"{minute // 60:02d}:"
            f"{minute % 60:02d}"
        )
