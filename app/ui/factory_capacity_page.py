from __future__ import annotations

from collections.abc import Callable
import time
from typing import Any

from PySide6.QtCore import QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.database import get_session
from app.services.factory_resource_intelligence_service import FactoryResourceIntelligenceService


class _CapacityWorker(QThread):
    """Small DB worker used by the four operator-facing resource tabs.

    No historical bootstrap, ML training, Excel parsing, or large table building is
    allowed on the Qt UI thread.  Those activities belong to import/migration jobs.
    """

    completed = Signal(int, str, object)
    failed = Signal(int, str, str)
    progress = Signal(int, str, str)

    def __init__(self, job_id: int, action: str, params: dict[str, Any] | None = None):
        super().__init__()
        self.job_id = int(job_id)
        self.action = action
        self.params = params or {}

    def _report(self, percent: int, stage: str, detail: str = "") -> None:
        self.progress.emit(max(0, min(100, int(percent))), stage, detail)

    def run(self) -> None:
        try:
            self._report(8, "Opening data", "Connecting to PostgreSQL")
            with get_session() as session:
                service = FactoryResourceIntelligenceService()
                if self.action == "header":
                    self._report(55, "Reading LIVE OVEN", "Loading current operational authority")
                    payload = service.header_snapshot(session)
                elif self.action.startswith("tab:"):
                    tab = self.action.split(":", 1)[1]
                    self._report(35, f"Loading {tab}", "Reading cached SQL resource memory")
                    payload = service.tab_snapshot(session, tab)
                elif self.action == "detail":
                    self._report(28, "Loading details", "Reading unique learned SAP relationships")
                    payload = service.resource_detail_snapshot(
                        session,
                        resource_type=str(self.params.get("resource_type") or ""),
                        line=str(self.params.get("line") or ""),
                        cavity=str(self.params.get("cavity") or ""),
                        mold_code=str(self.params.get("mold_code") or ""),
                        casing=str(self.params.get("casing") or ""),
                    )
                else:
                    payload = {}
            self._report(78, "Preparing view", "Rendering in responsive batches")
            self.completed.emit(self.job_id, self.action, payload)
        except Exception as exc:  # The UI must survive DB/ML failures.
            self.failed.emit(self.job_id, self.action, str(exc))


class FactoryCapacityPage(QWidget):
    """V11.3 compact Factory Resource & Capacity workspace.

    The operator sees only Production Lines, Cavities, Molds and Casings.  Capacity
    models, compatibility memory and GPU/CPU ML remain backend services used by the
    planning engine and Intelligent Excel Import.
    """

    CACHE_SECONDS = 90.0
    RENDER_BATCH = 40

    def __init__(
        self,
        on_open_page: Callable[[int], None],
        on_back: Callable[[], None],
        page_indexes: dict[str, int],
    ):
        super().__init__()
        self.on_open_page = on_open_page
        self.on_back = on_back
        self.page_indexes = page_indexes

        self._job_seq = 0
        self._workers: dict[int, _CapacityWorker] = {}
        self._running_actions: set[str] = set()
        self._cache: dict[str, dict[str, Any]] = {}
        self._cache_time: dict[str, float] = {}
        self._render_token: dict[str, int] = {}
        self._load_started: dict[str, float] = {}
        self._detail_dialogs: list[QDialog] = []

        self._apply_styles()
        self._build_ui()
        QTimer.singleShot(0, self.refresh)

    # ------------------------------------------------------------------ styles/UI
    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#HeaderCard, QFrame#ProgressCard, QFrame#DetailCard {
                background:#ffffff; border:1px solid #dbe4f0; border-radius:14px;
            }
            QLabel#Breadcrumb { color:#2563eb; font-size:9pt; font-weight:900; }
            QLabel#PageTitle { color:#0f172a; font-size:22pt; font-weight:950; }
            QLabel#SectionTitle { color:#0f172a; font-size:14pt; font-weight:950; }
            QLabel#Hint { color:#64748b; font-size:8.5pt; font-weight:650; }
            QLabel#GoodBadge {
                background:#ecfdf5; color:#047857; border:1px solid #a7f3d0;
                border-radius:10px; padding:7px 10px; font-weight:900;
            }
            QLabel#CardValue { color:#0f172a; font-size:17pt; font-weight:950; }
            QLabel#CardTitle { color:#475569; font-size:8.5pt; font-weight:850; }
            QFrame#ProgressCard { background:#f8fafc; border-radius:11px; }
            QLabel#ProgressStage { color:#0f172a; font-weight:900; }
            QLabel#ProgressDetail { color:#64748b; font-size:8.5pt; font-weight:650; }
            QProgressBar {
                background:#e2e8f0; color:#0f172a; border:1px solid #cbd5e1;
                border-radius:7px; text-align:center; min-height:18px; font-weight:900;
            }
            QProgressBar::chunk { background:#2563eb; border-radius:6px; }
            QPushButton {
                background:#e2e8f0; color:#0f172a; border:none; border-radius:8px;
                padding:7px 12px; font-weight:850;
            }
            QPushButton:hover { background:#cbd5e1; }
            QPushButton#Details {
                background:#eff6ff; color:#1d4ed8; border:1px solid #bfdbfe;
                padding:5px 9px;
            }
            QPushButton#Details:hover { background:#dbeafe; }
            QLineEdit, QComboBox {
                background:#ffffff; border:1px solid #cbd5e1; border-radius:8px;
                padding:6px 9px; color:#0f172a; font-weight:650;
            }
            QTabWidget::pane { border:none; background:transparent; }
            QTabBar::tab {
                background:#f1f5f9; color:#334155; padding:9px 16px;
                margin-right:2px; font-weight:850;
            }
            QTabBar::tab:selected { background:#2563eb; color:#ffffff; }
            QTableWidget {
                background:#ffffff; alternate-background-color:#f8fafc;
                gridline-color:#dbe4f0; selection-background-color:#dbeafe;
                selection-color:#0f172a; border:1px solid #e2e8f0;
            }
            QHeaderView::section {
                background:#eef2f7; color:#0f172a; border:none;
                border-right:1px solid #dbe4f0; border-bottom:1px solid #dbe4f0;
                padding:7px; font-size:8.5pt; font-weight:900;
            }
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(self._build_header())

        self.progress_panel = self._build_progress_panel()
        root.addWidget(self.progress_panel)
        self.progress_panel.hide()

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.lines_tab = self._build_lines_tab()
        self.cavities_tab = self._build_cavities_tab()
        self.molds_tab = self._build_molds_tab()
        self.casings_tab = self._build_casings_tab()
        for widget, title in (
            (self.lines_tab, "Production Lines"),
            (self.cavities_tab, "Cavities"),
            (self.molds_tab, "Molds"),
            (self.casings_tab, "Casings"),
        ):
            self.tabs.addTab(widget, title)
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

    def _build_header(self) -> QFrame:
        card = QFrame(); card.setObjectName("HeaderCard")
        row = QHBoxLayout(card); row.setContentsMargins(20, 13, 20, 13); row.setSpacing(12)
        left = QVBoxLayout(); left.setSpacing(2)
        crumb = QLabel("Data / Factory Resource & Capacity"); crumb.setObjectName("Breadcrumb")
        title = QLabel("Factory Resource & Capacity"); title.setObjectName("PageTitle")
        left.addWidget(crumb); left.addWidget(title)
        self.live_badge = QLabel("LIVE OVEN\nLOADING"); self.live_badge.setObjectName("GoodBadge")
        back = QPushButton("Back"); back.clicked.connect(self.on_back)
        row.addLayout(left, 1); row.addWidget(self.live_badge); row.addWidget(back)
        return card

    def _build_progress_panel(self) -> QFrame:
        panel = QFrame(); panel.setObjectName("ProgressCard")
        row = QHBoxLayout(panel); row.setContentsMargins(14, 8, 14, 8); row.setSpacing(10)
        text_box = QVBoxLayout(); text_box.setSpacing(1)
        self.progress_stage = QLabel("Loading"); self.progress_stage.setObjectName("ProgressStage")
        self.progress_detail = QLabel("Preparing background task..."); self.progress_detail.setObjectName("ProgressDetail")
        text_box.addWidget(self.progress_stage); text_box.addWidget(self.progress_detail)
        self.progress_bar = QProgressBar(); self.progress_bar.setRange(0, 100); self.progress_bar.setFormat("%p%")
        self.progress_bar.setMinimumWidth(260)
        row.addLayout(text_box, 1); row.addWidget(self.progress_bar)
        return panel

    @staticmethod
    def _table(headers: list[str], *, stretch_col: int | None = None, widths: dict[int, int] | None = None) -> QTableWidget:
        table = QTableWidget(0, len(headers)); table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setAlternatingRowColors(True); table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(34); table.setWordWrap(False)
        table.setSortingEnabled(False)
        header = table.horizontalHeader()
        # Automatic content-based resizing on every inserted cell is expensive with a large
        # history.  Stable interactive widths keep the event loop responsive.
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        if stretch_col is not None and 0 <= stretch_col < len(headers):
            header.setSectionResizeMode(stretch_col, QHeaderView.ResizeMode.Stretch)
        for col, width in (widths or {}).items():
            table.setColumnWidth(col, width)
        return table

    @staticmethod
    def _section_shell(title: str) -> tuple[QWidget, QVBoxLayout, QHBoxLayout]:
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(14, 10, 14, 14); layout.setSpacing(9)
        bar = QHBoxLayout(); label = QLabel(title); label.setObjectName("SectionTitle"); bar.addWidget(label)
        layout.addLayout(bar)
        return page, layout, bar

    def _build_lines_tab(self) -> QWidget:
        # User-facing line page intentionally starts directly with the table.
        page = QWidget(); layout = QVBoxLayout(page); layout.setContentsMargins(14, 10, 14, 14); layout.setSpacing(8)
        self.lines_table = self._table(
            ["No.", "Production Line", "Total Cavities", "Active Cavities", "Breakdown Cavities", "Status", "More Details"],
            stretch_col=1,
            widths={0: 50, 2: 110, 3: 110, 4: 130, 5: 125, 6: 120},
        )
        layout.addWidget(self.lines_table, 1)
        return page

    def _build_cavities_tab(self) -> QWidget:
        page, layout, bar = self._section_shell("Cavities")
        bar.addStretch()
        self.cavity_search = QLineEdit(); self.cavity_search.setPlaceholderText("Search line or cavity...")
        self.cavity_line = QComboBox(); self.cavity_line.addItem("All Lines")
        self.cavity_status = QComboBox(); self.cavity_status.addItems([
            "All Status", "ACTIVE", "BREAKDOWN", "LEARNING", "DORMANT",
            "RETIREMENT CANDIDATE", "RETIRED", "REVIEW",
        ])
        bar.addWidget(self.cavity_search, 2); bar.addWidget(self.cavity_line); bar.addWidget(self.cavity_status)
        self.cavities_table = self._table(
            ["No.", "Line", "Oven No / Cavity", "Status", "More Details"],
            stretch_col=2,
            widths={0: 50, 1: 220, 3: 145, 4: 120},
        )
        layout.addWidget(self.cavities_table, 1)
        self.cavity_search.textChanged.connect(lambda: self._debounce_render("cavities"))
        self.cavity_line.currentTextChanged.connect(lambda: self._debounce_render("cavities"))
        self.cavity_status.currentTextChanged.connect(lambda: self._debounce_render("cavities"))
        return page

    def _build_molds_tab(self) -> QWidget:
        page, layout, bar = self._section_shell("Molds")
        bar.addStretch()
        self.mold_search = QLineEdit(); self.mold_search.setPlaceholderText("Search mold code or related SAP...")
        self.mold_status = QComboBox(); self.mold_status.addItems([
            "All Status", "ACTIVE", "LEARNING", "DORMANT", "RETIREMENT CANDIDATE", "RETIRED", "REVIEW",
        ])
        bar.addWidget(self.mold_search, 1); bar.addWidget(self.mold_status)
        self.molds_table = self._table(
            ["No.", "Mold Code", "Max Mold", "Average Use / Shift", "Normal Production Average", "Status", "More Details"],
            stretch_col=1,
            widths={0: 50, 2: 90, 3: 135, 4: 165, 5: 120, 6: 120},
        )
        layout.addWidget(self.molds_table, 1)
        self.mold_search.textChanged.connect(lambda: self._debounce_render("molds"))
        self.mold_status.currentTextChanged.connect(lambda: self._debounce_render("molds"))
        return page

    def _build_casings_tab(self) -> QWidget:
        page, layout, bar = self._section_shell("Casings")
        bar.addStretch()
        self.casing_search = QLineEdit(); self.casing_search.setPlaceholderText("Search casing...")
        self.casing_status = QComboBox(); self.casing_status.addItems([
            "All Status", "ACTIVE", "LEARNING", "DORMANT", "RETIREMENT CANDIDATE", "RETIRED", "REVIEW",
        ])
        self.casing_sap_filter = QLineEdit(); self.casing_sap_filter.setPlaceholderText("SAP filter...")
        self.casing_mold_filter = QLineEdit(); self.casing_mold_filter.setPlaceholderText("Mold filter...")
        self.casing_sap_filter.setMaximumWidth(150); self.casing_mold_filter.setMaximumWidth(180)
        bar.addWidget(self.casing_search, 1); bar.addWidget(self.casing_status)
        bar.addWidget(self.casing_sap_filter); bar.addWidget(self.casing_mold_filter)
        self.casings_table = self._table(
            ["No.", "Casing", "Status", "More Details"],
            stretch_col=1,
            widths={0: 50, 2: 130, 3: 120},
        )
        layout.addWidget(self.casings_table, 1)
        self.casing_search.textChanged.connect(lambda: self._debounce_render("casings"))
        self.casing_status.currentTextChanged.connect(lambda: self._debounce_render("casings"))
        self.casing_sap_filter.textChanged.connect(lambda: self._debounce_render("casings"))
        self.casing_mold_filter.textChanged.connect(lambda: self._debounce_render("casings"))
        return page

    # ------------------------------------------------------------- background jobs
    def _current_tab_key(self) -> str:
        return ("lines", "cavities", "molds", "casings")[self.tabs.currentIndex()]

    def refresh(self) -> None:
        # These are independent lightweight background reads.  Header completion no
        # longer starts a second redundant tab load.
        self._start_job("header")
        self._request_tab(self._current_tab_key(), force=True)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not hasattr(self, "tabs"):
            return
        key = self._current_tab_key()
        if time.monotonic() - self._cache_time.get(key, 0.0) > self.CACHE_SECONDS:
            self._request_tab(key)

    def _on_tab_changed(self, _index: int) -> None:
        key = self._current_tab_key()
        if key in self._cache:
            self._render_cached_tab(key)
        self._request_tab(key)

    def _request_tab(self, key: str, *, force: bool = False) -> None:
        if not force and key in self._cache and time.monotonic() - self._cache_time.get(key, 0.0) < self.CACHE_SECONDS:
            return
        action = f"tab:{key}"
        if action in self._running_actions:
            return
        self._start_job(action)

    def _start_job(self, action: str, params: dict[str, Any] | None = None) -> None:
        if action in self._running_actions and action != "detail":
            return
        self._job_seq += 1
        job_id = self._job_seq
        if action != "detail":
            self._running_actions.add(action)
        self._load_started[f"{action}:{job_id}"] = time.monotonic()
        worker = _CapacityWorker(job_id, action, params)
        worker.progress.connect(lambda p, s, d, a=action, j=job_id: self._job_progress(a, j, p, s, d))
        worker.completed.connect(self._job_completed)
        worker.failed.connect(self._job_failed)
        worker.finished.connect(lambda j=job_id, a=action: self._job_finished(j, a))
        self._workers[job_id] = worker
        if action == "header" or action == f"tab:{self._current_tab_key()}" or action == "detail":
            self.progress_panel.show(); self.progress_bar.setValue(2)
            self.progress_stage.setText("Loading in background")
            self.progress_detail.setText("You can switch tabs, go Back, or open another page while this continues.")
        worker.start()

    def _job_progress(self, action: str, job_id: int, percent: int, stage: str, detail: str) -> None:
        current_action = f"tab:{self._current_tab_key()}"
        if action not in {"header", "detail", current_action}:
            return
        started = self._load_started.get(f"{action}:{job_id}", time.monotonic())
        elapsed = max(0.0, time.monotonic() - started)
        self.progress_bar.setValue(min(78, int(percent)))
        self.progress_stage.setText(stage)
        self.progress_detail.setText(f"{detail} • {elapsed:.1f}s elapsed • navigation remains available")
        self.progress_panel.show()

    def _job_completed(self, _job_id: int, action: str, payload: object) -> None:
        data = payload if isinstance(payload, dict) else {}
        if action == "header":
            latest = data.get("latest_plan_date")
            self.live_badge.setText(f"LIVE OVEN\n{latest or 'NO DATA'}")
            if not any(a.startswith("tab:") for a in self._running_actions):
                QTimer.singleShot(250, self.progress_panel.hide)
            return
        if action == "detail":
            if self.isVisible():
                self._show_detail_dialog(data)
            self.progress_bar.setValue(100); self.progress_stage.setText("Details ready")
            self.progress_detail.setText("Unique SAP/resource memory loaded")
            QTimer.singleShot(350, self.progress_panel.hide)
            return
        key = action.split(":", 1)[1]
        self._cache[key] = data; self._cache_time[key] = time.monotonic()
        if key == self._current_tab_key() and self.isVisible():
            self._render_cached_tab(key)

    def _job_failed(self, _job_id: int, action: str, message: str) -> None:
        if action == f"tab:{self._current_tab_key()}" or action in {"header", "detail"}:
            self.progress_bar.setValue(100); self.progress_stage.setText("Load failed")
            self.progress_detail.setText(f"{message} • application remains usable")
            self.progress_panel.show()

    def _job_finished(self, job_id: int, action: str) -> None:
        self._workers.pop(job_id, None)
        self._load_started.pop(f"{action}:{job_id}", None)
        if action != "detail":
            self._running_actions.discard(action)

    # -------------------------------------------------------------- rendering
    def _debounce_render(self, key: str) -> None:
        token = self._render_token.get(f"debounce:{key}", 0) + 1
        self._render_token[f"debounce:{key}"] = token
        QTimer.singleShot(180, lambda k=key, t=token: self._debounced_render(k, t))

    def _debounced_render(self, key: str, token: int) -> None:
        if self._render_token.get(f"debounce:{key}") == token and key == self._current_tab_key():
            self._render_cached_tab(key)

    def _render_cached_tab(self, key: str) -> None:
        data = self._cache.get(key)
        if data is None:
            return
        self._render_token[key] = self._render_token.get(key, 0) + 1
        token = self._render_token[key]
        if key == "lines":
            self._render_lines(data, token)
        elif key == "cavities":
            self._render_cavities(data, token)
        elif key == "molds":
            self._render_molds(data, token)
        elif key == "casings":
            self._render_casings(data, token)

    def _render_rows_chunked(
        self,
        key: str,
        token: int,
        table: QTableWidget,
        rows: list[dict[str, Any]],
        row_builder: Callable[[QTableWidget, int, dict[str, Any]], None],
    ) -> None:
        table.setRowCount(0)
        total = len(rows)
        if total == 0:
            self._render_complete(key, token)
            return
        self.progress_panel.show(); self.progress_bar.setValue(80)
        self.progress_stage.setText("Rendering table")
        self.progress_detail.setText(f"0 / {total:,} rows • responsive batch rendering")

        def step(offset: int = 0) -> None:
            if self._render_token.get(key) != token or key != self._current_tab_key() or not self.isVisible():
                return
            end = min(total, offset + self.RENDER_BATCH)
            table.setUpdatesEnabled(False)
            try:
                for idx in range(offset, end):
                    row_index = table.rowCount(); table.insertRow(row_index)
                    row_builder(table, row_index, rows[idx])
            finally:
                table.setUpdatesEnabled(True)
            pct = 80 + int(20 * end / max(1, total))
            self.progress_bar.setValue(min(100, pct))
            self.progress_detail.setText(f"{end:,} / {total:,} rows • navigation remains available")
            if end < total:
                QTimer.singleShot(0, lambda e=end: step(e))
            else:
                self._render_complete(key, token)
        QTimer.singleShot(0, step)

    def _render_complete(self, key: str, token: int) -> None:
        if self._render_token.get(key) != token or key != self._current_tab_key():
            return
        self.progress_bar.setValue(100); self.progress_stage.setText("Ready")
        self.progress_detail.setText("Page loaded without blocking the application")
        QTimer.singleShot(250, self.progress_panel.hide)

    @staticmethod
    def _put(table: QTableWidget, row: int, col: int, value: Any, *, center: bool = False, color: str = "") -> None:
        item = QTableWidgetItem(str(value if value is not None else ""))
        if center:
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if color:
            item.setForeground(QColor(color))
        table.setItem(row, col, item)

    @staticmethod
    def _status_color(status: str) -> str:
        status = str(status or "").upper()
        if status in {"BREAKDOWN", "NEED ATTENTION", "REVIEW"}:
            return "#dc2626"
        if status in {"PARTIAL", "DORMANT", "RETIREMENT CANDIDATE", "LEARNING"}:
            return "#b45309"
        if status == "ACTIVE":
            return "#047857"
        return "#475569"

    def _render_lines(self, data: dict[str, Any], token: int) -> None:
        rows = list(data.get("rows", []))

        def build(t: QTableWidget, i: int, r: dict[str, Any]) -> None:
            vals = [
                i + 1,
                r.get("line"),
                r.get("total_cavities"),
                r.get("active_cavities"),
                r.get("breakdown_cavities"),
            ]
            for c, v in enumerate(vals):
                self._put(t, i, c, v, center=c in {0, 2, 3, 4})
            status = str(r.get("status") or "")
            self._put(t, i, 5, status, center=True, color=self._status_color(status))
            btn = QPushButton("More Details"); btn.setObjectName("Details")
            btn.clicked.connect(lambda _=False, line=str(r.get("line") or ""): self._open_detail("LINE", line=line))
            t.setCellWidget(i, 6, btn)

        self._render_rows_chunked("lines", token, self.lines_table, rows, build)

    def _render_cavities(self, data: dict[str, Any], token: int) -> None:
        current_line = self.cavity_line.currentText()
        lines = ["All Lines"] + list(data.get("lines", []))
        existing = [self.cavity_line.itemText(i) for i in range(self.cavity_line.count())]
        if existing != lines:
            self.cavity_line.blockSignals(True); self.cavity_line.clear(); self.cavity_line.addItems(lines)
            self.cavity_line.setCurrentText(current_line if current_line in lines else "All Lines")
            self.cavity_line.blockSignals(False)

        q = self.cavity_search.text().strip().upper()
        line_filter = self.cavity_line.currentText()
        status_filter = self.cavity_status.currentText()
        rows = []
        for r in data.get("rows", []):
            hay = f"{r.get('line') or ''} {r.get('cavity') or ''}".upper()
            if q and q not in hay:
                continue
            if line_filter != "All Lines" and str(r.get("line")) != line_filter:
                continue
            if status_filter != "All Status" and str(r.get("status")) != status_filter:
                continue
            rows.append(r)

        def build(t: QTableWidget, i: int, r: dict[str, Any]) -> None:
            self._put(t, i, 0, i + 1, center=True)
            self._put(t, i, 1, r.get("line"))
            self._put(t, i, 2, r.get("cavity"))
            status = str(r.get("status") or "")
            self._put(t, i, 3, status, center=True, color=self._status_color(status))
            btn = QPushButton("More Details"); btn.setObjectName("Details")
            btn.clicked.connect(
                lambda _=False, line=str(r.get("line") or ""), cavity=str(r.get("cavity") or ""):
                self._open_detail("CAVITY", line=line, cavity=cavity)
            )
            t.setCellWidget(i, 4, btn)

        self._render_rows_chunked("cavities", token, self.cavities_table, rows, build)

    def _render_molds(self, data: dict[str, Any], token: int) -> None:
        q = self.mold_search.text().strip().upper()
        status_filter = self.mold_status.currentText()
        rows = []
        for r in data.get("rows", []):
            hay = f"{r.get('mold_code') or ''} {r.get('related_saps_display') or ''}".upper()
            if q and q not in hay:
                continue
            if status_filter != "All Status" and str(r.get("status")) != status_filter:
                continue
            rows.append(r)

        def build(t: QTableWidget, i: int, r: dict[str, Any]) -> None:
            vals = [
                i + 1,
                r.get("mold_code"),
                r.get("max_mold"),
                f"{float(r.get('average_use') or 0):.2f}",
                f"{float(r.get('normal_production_average') or 0):.1f}",
            ]
            for c, v in enumerate(vals):
                self._put(t, i, c, v, center=c in {0, 2, 3, 4})
            status = str(r.get("status") or "")
            self._put(t, i, 5, status, center=True, color=self._status_color(status))
            btn = QPushButton("More Details"); btn.setObjectName("Details")
            btn.clicked.connect(lambda _=False, mold=str(r.get("mold_code") or ""): self._open_detail("MOLD", mold_code=mold))
            t.setCellWidget(i, 6, btn)

        self._render_rows_chunked("molds", token, self.molds_table, rows, build)

    def _render_casings(self, data: dict[str, Any], token: int) -> None:
        q = self.casing_search.text().strip().upper()
        status_filter = self.casing_status.currentText()
        sap_filter = self.casing_sap_filter.text().strip().upper()
        mold_filter = self.casing_mold_filter.text().strip().upper()
        rows = []
        for r in data.get("rows", []):
            search_blob = str(r.get("search_blob") or r.get("casing") or "").upper()
            saps = " ".join(r.get("related_saps") or []).upper()
            molds = " ".join(r.get("related_molds") or []).upper()
            if q and q not in search_blob:
                continue
            if status_filter != "All Status" and str(r.get("status")) != status_filter:
                continue
            if sap_filter and sap_filter not in saps:
                continue
            if mold_filter and mold_filter not in molds:
                continue
            rows.append(r)

        def build(t: QTableWidget, i: int, r: dict[str, Any]) -> None:
            self._put(t, i, 0, i + 1, center=True)
            self._put(t, i, 1, r.get("casing"))
            status = str(r.get("status") or "")
            self._put(t, i, 2, status, center=True, color=self._status_color(status))
            btn = QPushButton("More Details"); btn.setObjectName("Details")
            btn.clicked.connect(lambda _=False, casing=str(r.get("casing") or ""): self._open_detail("CASING", casing=casing))
            t.setCellWidget(i, 3, btn)

        self._render_rows_chunked("casings", token, self.casings_table, rows, build)

    # ------------------------------------------------------------ detail views
    def _open_detail(
        self,
        resource_type: str,
        *,
        line: str = "",
        cavity: str = "",
        mold_code: str = "",
        casing: str = "",
    ) -> None:
        self._start_job(
            "detail",
            {"resource_type": resource_type, "line": line, "cavity": cavity, "mold_code": mold_code, "casing": casing},
        )

    def _show_detail_dialog(self, data: dict[str, Any]) -> None:
        dlg = QDialog(self.window())
        dlg.setWindowTitle(f"Resource Details • {data.get('title') or ''}")
        dlg.setModal(False); dlg.resize(1120, 690)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        root = QVBoxLayout(dlg); root.setContentsMargins(16, 16, 16, 16); root.setSpacing(10)
        title = QLabel(str(data.get("title") or "Resource Details")); title.setObjectName("SectionTitle")
        root.addWidget(title)

        card = QFrame(); card.setObjectName("DetailCard")
        row = QHBoxLayout(card); row.setContentsMargins(14, 10, 14, 10); row.setSpacing(22)
        for value, label in (
            (data.get("related_saps", 0), "Related SAPs"),
            (data.get("line_count", 0), "Lines"),
            (data.get("cavity_count", 0), "Cavities"),
            (data.get("observed_days", 0), "Observed Days"),
        ):
            box = QVBoxLayout(); v = QLabel(str(value)); v.setObjectName("CardValue")
            l = QLabel(label); l.setObjectName("CardTitle")
            box.addWidget(v); box.addWidget(l); row.addLayout(box); row.addStretch()
        root.addWidget(card)

        table = self._table(
            ["SAP Code", "Tyre Description", "Mold Code", "Casing", "Lines", "Cavities Used", "Observed Days", "Last Planned", "Historical Planned Qty"],
            stretch_col=1,
            widths={0: 115, 2: 170, 3: 115, 4: 150, 5: 95, 6: 95, 7: 105, 8: 135},
        )
        root.addWidget(table, 1)
        rows = list(data.get("rows", []))[:2500]
        detail_progress = QLabel(f"Loading 0 / {len(rows):,} unique SAP relationships...")
        detail_progress.setObjectName("Hint"); root.addWidget(detail_progress)
        dlg.destroyed.connect(lambda _=None, d=dlg: self._detail_dialogs.remove(d) if d in self._detail_dialogs else None)
        self._detail_dialogs.append(dlg); dlg.show()

        batch = max(16, min(self.RENDER_BATCH, 40))

        def render_detail(offset: int = 0) -> None:
            if not dlg.isVisible():
                return
            end = min(len(rows), offset + batch)
            table.setUpdatesEnabled(False)
            try:
                for idx in range(offset, end):
                    r = rows[idx]
                    i = table.rowCount(); table.insertRow(i)
                    vals = [
                        r.get("sap_code"), r.get("description"), r.get("mold_code"), r.get("casing"),
                        r.get("lines"), r.get("cavity_count"), r.get("observed_days"),
                        r.get("last_seen") or "-", r.get("planned_qty"),
                    ]
                    for c, v in enumerate(vals):
                        self._put(table, i, c, v, center=c in {5, 6, 8})
            finally:
                table.setUpdatesEnabled(True)
            detail_progress.setText(f"Loaded {end:,} / {len(rows):,} unique SAP relationships")
            if end < len(rows):
                QTimer.singleShot(0, lambda e=end: render_detail(e))
            else:
                detail_progress.setText(f"Ready • {len(rows):,} unique SAP records")

        QTimer.singleShot(0, render_detail)


__all__ = ["FactoryCapacityPage"]
