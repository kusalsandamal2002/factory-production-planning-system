from __future__ import annotations

from dataclasses import asdict
from datetime import date
from pathlib import Path
import traceback
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.services.factory_planning_engine import (
    FactoryPlanningEngine,
)
from app.services.intelligent_excel_import_service import (
    IntelligentExcelImportService,
    WorkbookAnalysis,
)


class _TaskWorker(QThread):
    progress = Signal(int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, action: Callable[[Callable[[int, str], None]], Any]):
        super().__init__()
        self.action = action

    def run(self) -> None:
        try:
            result = self.action(
                lambda percent, message: self.progress.emit(percent, message)
            )
            self.completed.emit(result)
        except Exception:
            self.failed.emit(traceback.format_exc())


class RawExcelViewerPage(QWidget):
    """Professional one-workbook MPPS import, audit, update and rollback center."""

    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__()
        self.current_user = current_user
        self.project_root = Path(__file__).resolve().parents[2]
        self.service = IntelligentExcelImportService(self.project_root)
        self.analysis: WorkbookAnalysis | None = None
        self.sync_preview: dict[str, Any] = {}
        self.worker: _TaskWorker | None = None
        self.selected_file = ""
        self._build_ui()
        self.refresh_history()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Intelligent Excel Import Center")
        title.setObjectName("ExcelImportTitle")
        title.setStyleSheet(
            "font-size:26px;font-weight:900;color:#0f172a;"
        )
        subtitle = QLabel(
            "One workbook → stock, shipment demand, production history, "
            "oven/cavity plan, day/night plan, weights, compound/BOM, bead, "
            "band and core. Semantic sheet detection, confidence scoring, "
            "transactional updates, duplicate-safe continuous shipment sync, "
            "historical/live revision protection, local learning observations "
            "and rollback are built in."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#52627a;font-size:12px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

        self.status_badge = QLabel("READY FOR ANALYSIS")
        self.status_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_badge.setMinimumWidth(190)
        self.status_badge.setStyleSheet(
            "background:#e0f2fe;color:#075985;border:1px solid #7dd3fc;"
            "border-radius:16px;padding:8px 14px;font-weight:900;"
        )
        header.addWidget(self.status_badge)
        root.addLayout(header)

        source_card = self._card()
        source_layout = QVBoxLayout(source_card)
        source_layout.setContentsMargins(16, 14, 16, 14)
        source_layout.setSpacing(10)

        source_title = QLabel("1. Select the complete production workbook")
        source_title.setStyleSheet("font-weight:900;font-size:14px;color:#0f172a;")
        source_layout.addWidget(source_title)

        source_row = QHBoxLayout()
        self.file_box = QLineEdit()
        self.file_box.setPlaceholderText(
            "Select OVEN / MPPS production workbook (.xlsx or .xlsm)"
        )
        self.file_box.setMinimumHeight(38)
        source_row.addWidget(self.file_box, 1)

        browse_btn = QPushButton("Browse Workbook")
        browse_btn.setMinimumHeight(38)
        browse_btn.clicked.connect(self.browse_file)
        source_row.addWidget(browse_btn)

        self.analyze_btn = QPushButton("Analyze with Semantic Engine")
        self.analyze_btn.setMinimumHeight(38)
        self.analyze_btn.setStyleSheet(
            "background:#0f766e;color:white;font-weight:900;padding:0 18px;"
        )
        self.analyze_btn.clicked.connect(self.analyze_workbook)
        source_row.addWidget(self.analyze_btn)
        source_layout.addLayout(source_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress_label = QLabel("Select a workbook to begin.")
        self.progress_label.setStyleSheet("color:#64748b;")
        source_layout.addWidget(self.progress)
        source_layout.addWidget(self.progress_label)
        root.addWidget(source_card)

        self.kpi_grid = QGridLayout()
        self.kpi_grid.setSpacing(10)
        self.kpi_labels: dict[str, tuple[QLabel, QLabel]] = {}
        kpi_specs = [
            ("confidence", "Workbook Confidence"),
            ("sheets", "Mapped Sheets"),
            ("stock", "Stock Items"),
            ("shipments", "Shipment Orders"),
            ("demand", "Shipment Qty"),
            ("required", "Production Required"),
            ("today", "Day + Night Plan"),
            ("materials", "Material / BOM Rows"),
            ("errors", "Formula Errors"),
            ("issues", "Review Issues"),
            ("sync_mode", "Resolved Import Mode"),
            ("sync_new", "New Shipments"),
            ("sync_updated", "Updated Shipments"),
            ("sync_missing", "Missing / Removed"),
            ("sync_review", "Sync Review"),
        ]
        for index, (key, caption) in enumerate(kpi_specs):
            card = self._metric_card(key, caption)
            self.kpi_grid.addWidget(card, index // 5, index % 5)
        root.addLayout(self.kpi_grid)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)

        self.preview_tabs = QTabWidget()
        self.sheet_table = self._table(
            [
                "Sheet",
                "Detected Role",
                "Confidence",
                "Rows",
                "Columns",
                "Non-empty Cells",
                "Formulas",
                "Cached Errors",
                "Evidence",
            ]
        )
        self.issue_table = self._table(
            [
                "Severity",
                "Category",
                "Sheet",
                "Cell",
                "Item",
                "Message",
                "Recommendation",
            ]
        )
        self.stock_table = self._table(
            [
                "SAP Code",
                "Description",
                "FG Stock",
                "Scrap",
                "Blocked",
                "Shipment",
                "Production Required",
                "Planned Today",
                "Remaining",
                "Weight Kg",
            ]
        )
        self.sync_table = self._table(
            [
                "Action",
                "Identity",
                "Column",
                "Shipment",
                "Existing ID",
                "Old Qty",
                "New Qty",
                "Changed",
                "New Items",
                "Removed",
                "Conflicts",
                "Manual Preserved",
                "Reason",
            ]
        )
        self.shipment_table = self._table(
            [
                "Column",
                "Shipment",
                "Source Status",
                "Target Date",
                "Date Class",
                "SAP Code",
                "Description",
                "Quantity",
            ]
        )
        self.oven_table = self._table(
            [
                "Date",
                "Line",
                "Oven / Cavity",
                "Shift",
                "SAP Code",
                "Description",
                "Qty",
                "Weight Kg",
            ]
        )
        self.material_table = self._table(
            [
                "Type",
                "Material / Item",
                "Description",
                "Day",
                "Night",
                "Total",
                "Next Day",
                "Source",
            ]
        )
        self.history_table = self._table(
            [
                "Run",
                "Workbook",
                "Plan Date",
                "Confidence",
                "Status",
                "Imported By",
                "Started",
                "Completed",
                "Rollback",
            ]
        )

        self.preview_tabs.addTab(self.sheet_table, "Sheet Intelligence")
        self.preview_tabs.addTab(self.issue_table, "Issues & Decisions")
        self.preview_tabs.addTab(self.stock_table, "Stock & Demand")
        self.preview_tabs.addTab(self.sync_table, "Live Sync Preview")
        self.preview_tabs.addTab(self.shipment_table, "Shipment Snapshot")
        self.preview_tabs.addTab(self.oven_table, "Oven / Shift Plan")
        self.preview_tabs.addTab(self.material_table, "Materials")
        self.preview_tabs.addTab(self.history_table, "Import History")
        splitter.addWidget(self.preview_tabs)

        control_card = self._card()
        control_layout = QVBoxLayout(control_card)
        control_layout.setContentsMargins(16, 14, 16, 14)
        control_layout.setSpacing(10)
        control_title = QLabel("2. Safe update controls")
        control_title.setStyleSheet("font-weight:900;font-size:14px;color:#0f172a;")
        control_layout.addWidget(control_title)

        options = QGridLayout()
        self.option_boxes: dict[str, QCheckBox] = {}
        option_specs = [
            ("archive_source", "Archive exact source workbook", True),
            ("auto_detect_import_mode", "Auto-detect historical vs live revision", True),
            ("update_stock", "Update current stock only for latest live revision", True),
            ("update_daily_stock", "Create dated daily-stock snapshot", True),
            ("sync_live_shipments", "Auto-sync live shipments (new / update / remove safely)", True),
            ("mark_missing_shipments", "Mark shipments missing from latest workbook", True),
            ("sync_deferred_shipments", "Sync deferred / inactive Excel shipments", False),
            ("update_blank_weights", "Fill blank/zero approved weights", True),
            ("overwrite_existing_weights", "Overwrite existing weights", False),
            ("import_oven_plan", "Import oven/cavity day-night plan", True),
            ("import_materials", "Import compound/BOM/bead/band/core", True),
            ("import_shipment_snapshots", "Import all shipment snapshots", True),
            ("import_production_history", "Import dated production history", True),
            ("capture_learning_observations", "Capture ML learning observations", True),
            ("rebuild_learning_models", "Rebuild advisory learning models", True),
        ]
        for index, (key, text, checked) in enumerate(option_specs):
            checkbox = QCheckBox(text)
            checkbox.setChecked(checked)
            if key in {
                "overwrite_existing_weights",
                "sync_deferred_shipments",
            }:
                checkbox.setStyleSheet("color:#b45309;font-weight:800;")
            self.option_boxes[key] = checkbox
            options.addWidget(checkbox, index // 5, index % 5)
        control_layout.addLayout(options)

        warning = QLabel(
            "Continuous-sync protection: the newest workbook updates one stable "
            "live shipment instead of creating duplicates. Older workbooks become "
            "historical snapshots. Manual target dates, holds, produced/completed "
            "quantities and manually locked items are never overwritten. ML models "
            "remain advisory and do not change the live production plan automatically."
        )
        warning.setWordWrap(True)
        warning.setStyleSheet(
            "background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;"
            "border-radius:8px;padding:9px;font-weight:700;"
        )
        control_layout.addWidget(warning)

        action_row = QHBoxLayout()
        self.commit_btn = QPushButton("Commit Safe Full Update")
        self.commit_btn.setMinimumHeight(42)
        self.commit_btn.setEnabled(False)
        self.commit_btn.setStyleSheet(
            "background:#1d4ed8;color:white;font-weight:900;padding:0 20px;"
        )
        self.commit_btn.clicked.connect(self.commit_import)
        action_row.addWidget(self.commit_btn)

        refresh_btn = QPushButton("Refresh History")
        refresh_btn.setMinimumHeight(42)
        refresh_btn.clicked.connect(self.refresh_history)
        action_row.addWidget(refresh_btn)

        self.rollback_btn = QPushButton("Rollback Selected Import")
        self.rollback_btn.setMinimumHeight(42)
        self.rollback_btn.setStyleSheet("font-weight:900;color:#b91c1c;")
        self.rollback_btn.clicked.connect(self.rollback_selected)
        action_row.addWidget(self.rollback_btn)
        action_row.addStretch()
        control_layout.addLayout(action_row)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumHeight(240)
        self.output.setPlaceholderText("Analysis and import result will appear here.")
        control_layout.addWidget(self.output)
        splitter.addWidget(control_card)
        splitter.setSizes([520, 260])
        root.addWidget(splitter, 1)

    def _card(self) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame {background:#ffffff;border:1px solid #dbe4ef;"
            "border-radius:10px;}"
        )
        return card

    def _metric_card(self, key: str, caption: str) -> QFrame:
        card = self._card()
        card.setMinimumHeight(84)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 9, 12, 9)
        value = QLabel("—")
        value.setStyleSheet("font-size:20px;font-weight:950;color:#0f172a;")
        label = QLabel(caption)
        label.setStyleSheet("color:#64748b;font-size:10px;font-weight:800;")
        label.setWordWrap(True)
        layout.addWidget(value)
        layout.addWidget(label)
        self.kpi_labels[key] = (value, label)
        return card

    def _table(self, headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.verticalHeader().setVisible(False)
        header = table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        table.setStyleSheet(
            "QTableWidget {border:0;background:white;gridline-color:#e2e8f0;}"
            "QHeaderView::section {background:#f8fafc;color:#334155;"
            "font-weight:900;border:0;border-bottom:1px solid #cbd5e1;"
            "padding:7px;}"
        )
        return table

    def browse_file(self) -> None:
        start = self.project_root / "data_sources"
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select MPPS / OVEN Excel Workbook",
            str(start if start.exists() else self.project_root),
            "Excel Workbooks (*.xlsx *.xlsm)",
        )
        if path:
            self.selected_file = path
            self.file_box.setText(path)
            self.analysis = None
            self.commit_btn.setEnabled(False)
            self._set_status("FILE SELECTED", "#e0f2fe", "#075985", "#7dd3fc")

    def analyze_workbook(self) -> None:
        path = self.file_box.text().strip()
        if not path or not Path(path).exists():
            QMessageBox.warning(self, "Workbook Required", "Select an existing Excel workbook.")
            return
        self._start_task(
            lambda progress: self.service.analyze(path, progress=progress),
            self._analysis_complete,
            "Analyzing workbook",
        )

    def commit_import(self) -> None:
        if self.analysis is None:
            QMessageBox.warning(self, "Analyze First", "Analyze the workbook before committing.")
            return
        blockers = [i for i in self.analysis.issues if i.severity == "BLOCKER"]
        if blockers:
            QMessageBox.critical(
                self,
                "Safe Import Blocked",
                "The analysis contains blocker issues. Resolve them before live updates.",
            )
            return
        live_sync = self.option_boxes["sync_live_shipments"].isChecked()
        overwrite_weights = self.option_boxes["overwrite_existing_weights"].isChecked()
        sync_deferred = self.option_boxes["sync_deferred_shipments"].isChecked()
        if live_sync or overwrite_weights or sync_deferred:
            reply = QMessageBox.warning(
                self,
                "Controlled Update Confirmation",
                "You enabled live revision synchronization, deferred-shipment sync "
                "or approved-weight overwrite. The preview shows the exact new, "
                "updated, removed and protected rows. The import remains reversible. "
                "Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        options = {key: box.isChecked() for key, box in self.option_boxes.items()}
        user_name = self._user_name()
        self._start_task(
            lambda progress: self._commit_and_auto_replan(
                options=options,
                imported_by=user_name,
                progress=progress,
            ),
            self._commit_complete,
            "Committing safe full update",
        )

    def _commit_and_auto_replan(
        self,
        *,
        options: dict[str, bool],
        imported_by: str,
        progress,
    ) -> dict[str, Any]:
        result = self.service.commit(
            self.analysis,
            options=options,
            imported_by=imported_by,
            progress=(
                lambda percent, message: progress(
                    min(84, int(percent * 0.84)),
                    message,
                )
            ),
        )

        sync_result = result.get("shipment_sync", {})
        live_change_count = int(
            sync_result.get("live_change_count", 0) or 0
        )
        if (
            options.get("sync_live_shipments")
            and result.get("import_mode") == "LIVE"
            and live_change_count > 0
        ):
            progress(
                88,
                "Reallocating stock and replanning the complete shipment queue",
            )
            planning_result = FactoryPlanningEngine(
                start_date=date.today()
            ).replan_all_open_shipments(
                trigger_reason=(
                    f"continuous_excel_sync_run_"
                    f"{result['run_id']}"
                ),
                created_by=imported_by or "excel_sync",
            )
            result["planning_run_id"] = (
                planning_result.planning_run_id
            )
            result["auto_planned_shipments"] = len(
                planning_result.shipments
            )
        else:
            result["auto_planned_shipments"] = 0

        progress(
            95,
            "Reconciling Excel demand/plan against the live application",
        )
        reconciliation = self.service.finalize_post_plan(
            import_run_id=result["run_id"],
            analysis=self.analysis,
        )
        result["reconciliation"] = reconciliation
        result.setdefault("changes", {}).update(reconciliation)

        progress(
            100,
            "Continuous Excel sync, learning capture and reconciliation complete",
        )
        return result

    def rollback_selected(self) -> None:
        row = self.history_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Select Import", "Select a committed import run in Import History.")
            return
        run_item = self.history_table.item(row, 0)
        if run_item is None:
            return
        run_id = int(run_item.text())
        reply = QMessageBox.warning(
            self,
            "Rollback Import",
            f"Restore live data changed by import run #{run_id}? The archived source "
            "and audit history will be kept.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._start_task(
            lambda progress: self._rollback_action(run_id, progress),
            self._rollback_complete,
            f"Rolling back import #{run_id}",
        )

    def _rollback_action(self, run_id: int, progress) -> dict[str, Any]:
        progress(15, "Loading import change ledger")
        result = self.service.rollback(run_id, rolled_back_by=self._user_name())
        progress(100, "Rollback complete")
        return result

    def refresh_history(self) -> None:
        try:
            rows = self.service.list_history(100)
        except Exception as exc:
            self.output.setPlainText(
                "Import history is not available yet. The schema will be created on "
                f"the first successful analysis/commit.\n\n{exc}"
            )
            return
        self.history_table.setRowCount(0)
        for row_data in rows:
            row = self.history_table.rowCount()
            self.history_table.insertRow(row)
            values = [
                row_data.get("id"),
                row_data.get("workbook_name"),
                row_data.get("plan_date"),
                _format_percent(row_data.get("confidence_score")),
                row_data.get("status"),
                row_data.get("imported_by"),
                row_data.get("started_at"),
                row_data.get("completed_at"),
                row_data.get("rollback_at"),
            ]
            for column, value in enumerate(values):
                self.history_table.setItem(row, column, QTableWidgetItem(_display(value)))

    def _start_task(self, action, completed, label: str) -> None:
        if self.worker and self.worker.isRunning():
            QMessageBox.information(self, "Task Running", "Wait for the current task to finish.")
            return
        self._set_busy(True)
        self.progress.setValue(0)
        self.progress_label.setText(label)
        self.output.setPlainText(label + "...")
        self.worker = _TaskWorker(action)
        self.worker.progress.connect(self._on_progress)
        self.worker.completed.connect(completed)
        self.worker.completed.connect(lambda _: self._set_busy(False))
        self.worker.failed.connect(self._task_failed)
        self.worker.failed.connect(lambda _: self._set_busy(False))
        self.worker.start()

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        self.progress_label.setText(message)

    def _analysis_complete(self, analysis: WorkbookAnalysis) -> None:
        self.analysis = analysis
        self._populate_analysis(analysis)
        preview_options = {
            key: box.isChecked()
            for key, box in self.option_boxes.items()
        }
        try:
            self.sync_preview = self.service.preview_shipment_sync(
                analysis,
                options=preview_options,
            )
        except Exception as exc:
            self.sync_preview = {
                "mode": "UNAVAILABLE",
                "reason": str(exc),
                "summary": {},
                "rows": [],
            }
        self._populate_sync_preview(self.sync_preview)
        blockers = analysis.summary.get("blocker_count", 0)
        self.commit_btn.setEnabled(blockers == 0)
        if blockers:
            self._set_status("ANALYSIS BLOCKED", "#fee2e2", "#991b1b", "#fecaca")
        elif analysis.summary.get("warning_count", 0):
            self._set_status("READY WITH WARNINGS", "#fef3c7", "#92400e", "#fde68a")
        else:
            self._set_status("SAFE UPDATE READY", "#dcfce7", "#166534", "#86efac")
        self.output.setPlainText(self._analysis_text(analysis))

    def _commit_complete(self, result: dict[str, Any]) -> None:
        self._set_status("UPDATE COMMITTED", "#dcfce7", "#166534", "#86efac")
        self.output.setPlainText(
            "SAFE FULL UPDATE COMMITTED\n\n"
            f"Import run: #{result['run_id']}\n"
            f"Status: {result['status']}\n"
            f"Plan date: {result['plan_date']}\n"
            f"Archived source: {result.get('archive_path') or '-'}\n"
            f"Warnings retained for review: {result['warnings']}\n"
            f"Import mode: {result.get('import_mode') or '-'}\n"
            f"Sync reason: {result.get('import_mode_reason') or '-'}\n"
            f"New shipments: {result.get('shipment_sync', {}).get('new_shipments', 0):,}\n"
            f"Updated shipments: {result.get('shipment_sync', {}).get('updated_shipments', 0):,}\n"
            f"Missing shipments marked: {result.get('shipment_sync', {}).get('missing_shipments', 0):,}\n"
            f"Review conflicts: {result.get('shipment_sync', {}).get('review_shipments', 0):,}\n"
            f"Manual fields preserved: {result.get('shipment_sync', {}).get('manual_fields_preserved', 0):,}\n"
            f"Auto-planned shipments: {result.get('auto_planned_shipments', 0):,}\n"
            f"Planning run: {result.get('planning_run_id') or '-'}\n"
            f"Learning models: {result.get('learning', {}).get('models_total', 0):,}\n"
            f"Reconciliation review rows: {result.get('reconciliation', {}).get('reconciliation_review', 0):,}\n\n"
            "Changes:\n"
            + "\n".join(
                f"  {key}: {value:,}" if isinstance(value, int) else f"  {key}: {value}"
                for key, value in sorted(result.get("changes", {}).items())
            )
        )
        self.refresh_history()
        self.preview_tabs.setCurrentWidget(self.history_table)
        QMessageBox.information(
            self,
            "Import Committed",
            f"Workbook imported as run #{result['run_id']}. The exact source was "
            "archived, duplicate-safe shipment revision sync was applied, manual "
            "and actual values were protected, the affected queue was replanned, "
            "and advisory learning observations were updated. Rollback remains "
            "available.",
        )

    def _rollback_complete(self, result: dict[str, Any]) -> None:
        self._set_status("IMPORT ROLLED BACK", "#e0f2fe", "#075985", "#7dd3fc")
        self.output.setPlainText(
            f"IMPORT RUN #{result['run_id']} ROLLED BACK\n\n"
            f"Rows restored: {result['restored_rows']}\n"
            f"Inserted rows removed: {result['removed_rows']}\n"
            "The archived workbook and audit history were retained."
        )
        self.refresh_history()

    def _task_failed(self, details: str) -> None:
        self._set_status("TASK FAILED", "#fee2e2", "#991b1b", "#fecaca")
        self.output.setPlainText(details)
        lines = [line.strip() for line in details.splitlines() if line.strip()]
        exact_reason = lines[-1] if lines else "Unknown import error"
        QMessageBox.critical(
            self,
            "Intelligent Excel Import Error",
            "The task was stopped and the database transaction was rolled back.\n\n"
            f"Exact reason:\n{exact_reason}\n\n"
            "The complete traceback remains in Technical Output.",
        )

    def _set_busy(self, busy: bool) -> None:
        self.analyze_btn.setEnabled(not busy)
        self.commit_btn.setEnabled((not busy) and self.analysis is not None)
        self.rollback_btn.setEnabled(not busy)

    def _set_status(self, text: str, background: str, color: str, border: str) -> None:
        self.status_badge.setText(text)
        self.status_badge.setStyleSheet(
            f"background:{background};color:{color};border:1px solid {border};"
            "border-radius:16px;padding:8px 14px;font-weight:900;"
        )

    def _populate_analysis(self, analysis: WorkbookAnalysis) -> None:
        summary = analysis.summary
        self._metric("confidence", f"{analysis.confidence_score * 100:.1f}%")
        self._metric(
            "sheets",
            f"{summary.get('mapped_sheet_count', 0)} / {summary.get('sheet_count', 0)}",
        )
        self._metric("stock", _number_text(summary.get("stock_item_count", 0)))
        self._metric("shipments", _number_text(summary.get("shipment_count", 0)))
        self._metric("demand", _number_text(summary.get("total_shipment_qty", 0)))
        self._metric("required", _number_text(summary.get("production_required_qty", 0)))
        self._metric(
            "today",
            _number_text(summary.get("day_plan_qty", 0) + summary.get("night_plan_qty", 0)),
        )
        self._metric(
            "materials",
            _number_text(
                summary.get("compound_bom_rows", 0)
                + summary.get("bead_master_rows", 0)
                + summary.get("material_plan_rows", 0)
            ),
        )
        self._metric("errors", _number_text(summary.get("cached_error_cell_count", 0)))
        self._metric(
            "issues",
            _number_text(
                summary.get("blocker_count", 0)
                + summary.get("warning_count", 0)
                + summary.get("info_count", 0)
            ),
        )

        self._fill_table(
            self.sheet_table,
            [
                [
                    row.sheet_name,
                    row.role,
                    f"{row.confidence * 100:.1f}%",
                    row.max_row,
                    row.max_column,
                    row.nonempty_cells,
                    row.formula_cells,
                    row.cached_error_cells,
                    row.evidence,
                ]
                for row in analysis.sheet_profiles
            ],
        )
        self._fill_issues(analysis)
        self._fill_table(
            self.stock_table,
            [
                [
                    row["sap_code"],
                    row["description"],
                    row["fg_stock"],
                    row["scrap_stock"],
                    row["blocked_stock"],
                    row["total_shipment"],
                    row["production_required"],
                    row["planned_today"],
                    row["remaining_to_plan"],
                    row.get("weight_kg") or "",
                ]
                for row in analysis.stock_rows[:5000]
            ],
        )
        self._fill_table(
            self.shipment_table,
            [
                [
                    row["shipment_column"],
                    row["shipment_name"],
                    row["source_status"],
                    row.get("source_target_date") or "",
                    row.get("source_date_class") or "",
                    row["sap_code"],
                    row["description"],
                    row["quantity"],
                ]
                for row in analysis.shipment_rows[:10000]
            ],
        )
        self._fill_table(
            self.oven_table,
            [
                [
                    row["plan_date"],
                    row["line_name"],
                    row["oven_code"],
                    row["shift_name"],
                    row["sap_code"],
                    row["description"],
                    row["planned_qty"],
                    row["planned_weight_kg"],
                ]
                for row in analysis.oven_rows
            ],
        )
        material_rows = [
            [
                "COMPOUND",
                row["compound_name"],
                row["sap_code"],
                row["usage_per_unit"],
                "",
                row["usage_per_unit"],
                "",
                f"{row['source_sheet']}:{row['source_row']}",
            ]
            for row in analysis.compound_rows[:5000]
        ]
        material_rows.extend(
            [
                row["material_type"],
                row["material_key"],
                row["material_description"],
                row["day_qty"],
                row["night_qty"],
                row["total_qty"],
                row["next_day_qty"],
                f"{row['source_sheet']}:{row['source_row']}",
            ]
            for row in analysis.material_plan_rows
        )
        self._fill_table(self.material_table, material_rows)

    def _populate_sync_preview(self, preview: dict[str, Any]) -> None:
        summary = preview.get("summary", {})
        self._metric("sync_mode", preview.get("mode") or "-")
        self._metric("sync_new", _number_text(summary.get("new_shipments", 0)))
        self._metric("sync_updated", _number_text(summary.get("updated_shipments", 0)))
        self._metric(
            "sync_missing",
            _number_text(
                int(summary.get("missing_shipments", 0) or 0)
                + int(summary.get("removed_items", 0) or 0)
            ),
        )
        self._metric("sync_review", _number_text(summary.get("review_shipments", 0)))
        rows = []
        for row in preview.get("rows", []):
            rows.append(
                [
                    row.get("action"),
                    row.get("identity_key"),
                    row.get("shipment_column"),
                    row.get("shipment_name"),
                    row.get("existing_shipment_id"),
                    row.get("old_total_qty"),
                    row.get("new_total_qty"),
                    row.get("changed_items"),
                    row.get("new_items"),
                    row.get("removed_items"),
                    row.get("conflicts"),
                    row.get("manual_fields_preserved"),
                    row.get("reason"),
                ]
            )
        self._fill_table(self.sync_table, rows)

    def _fill_issues(self, analysis: WorkbookAnalysis) -> None:
        self.issue_table.setRowCount(0)
        colors = {
            "BLOCKER": QColor("#fee2e2"),
            "WARNING": QColor("#fef3c7"),
            "INFO": QColor("#e0f2fe"),
        }
        for issue in analysis.issues:
            row = self.issue_table.rowCount()
            self.issue_table.insertRow(row)
            values = [
                issue.severity,
                issue.category,
                issue.sheet_name,
                issue.cell_address,
                issue.item_key,
                issue.message,
                issue.recommendation,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(_display(value))
                item.setBackground(colors.get(issue.severity, QColor("#ffffff")))
                self.issue_table.setItem(row, column, item)

    def _fill_table(self, table: QTableWidget, rows: list[list[Any]]) -> None:
        table.setSortingEnabled(False)
        table.setRowCount(0)
        for values in rows:
            row = table.rowCount()
            table.insertRow(row)
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(_display(value)))
        table.setSortingEnabled(True)

    def _metric(self, key: str, value: str) -> None:
        self.kpi_labels[key][0].setText(value)

    def _analysis_text(self, analysis: WorkbookAnalysis) -> str:
        s = analysis.summary
        return (
            "INTELLIGENT WORKBOOK ANALYSIS COMPLETE\n\n"
            f"Workbook: {analysis.workbook_name}\n"
            f"SHA256: {analysis.workbook_hash}\n"
            f"Detected type: {analysis.detected_type}\n"
            f"Plan date: {analysis.plan_date or 'Not resolved'}\n"
            f"Confidence: {analysis.confidence_score * 100:.1f}%\n\n"
            f"Sheets: {s.get('sheet_count', 0):,}; mapped: {s.get('mapped_sheet_count', 0):,}\n"
            f"Non-empty cells: {s.get('nonempty_cell_count', 0):,}\n"
            f"Formulas: {s.get('formula_cell_count', 0):,}; cached errors: {s.get('cached_error_cell_count', 0):,}\n"
            f"Stock items: {s.get('stock_item_count', 0):,}; FG stock: {s.get('total_fg_stock', 0):,}\n"
            f"Negative source-stock rows protected: {s.get('negative_stock_row_count', 0):,}\n"
            f"Shipments: {s.get('shipment_count', 0):,}; shipment qty: {s.get('total_shipment_qty', 0):,}\n"
            f"Production required: {s.get('production_required_qty', 0):,}\n"
            f"Day plan: {s.get('day_plan_qty', 0):,}; night plan: {s.get('night_plan_qty', 0):,}; next day: {s.get('next_day_plan_qty', 0):,}\n"
            f"Compound/BOM: {s.get('compound_bom_rows', 0):,}; material plans: {s.get('material_plan_rows', 0):,}\n\n"
            f"Blockers: {s.get('blocker_count', 0):,}; warnings: {s.get('warning_count', 0):,}; information: {s.get('info_count', 0):,}\n\n"
            f"Resolved import mode: {self.sync_preview.get('mode', 'Calculating')}\n"
            f"Revision decision: {self.sync_preview.get('reason', 'Preview will be calculated after analysis.')}\n\n"
            "The exact workbook will be archived. Older plan dates become historical "
            "snapshots automatically. The newest revision updates stable live shipment "
            "identities without duplicating orders, while manual/actual values remain protected."
        )

    def _user_name(self) -> str:
        user = self.current_user
        for attribute in ("username", "full_name", "name", "email"):
            value = getattr(user, attribute, None) if user is not None else None
            if value:
                return str(value)
        return "Local User"


def _display(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if value.is_integer():
            return f"{int(value):,}"
        return f"{value:,.5f}".rstrip("0").rstrip(".")
    return str(value)


def _number_text(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return _display(value)


def _format_percent(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return ""
