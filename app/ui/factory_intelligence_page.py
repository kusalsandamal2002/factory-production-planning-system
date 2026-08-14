from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.database import get_session
from app.services.ai_planning_service import AIPlanningService
from app.services.factory_intelligence_service import FactoryIntelligenceService
from app.services.operational_source_service import OperationalSourceService


class _FactoryIntelligenceWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def run(self) -> None:
        try:
            with get_session() as session:
                ai = AIPlanningService()
                fi = FactoryIntelligenceService()
                ai.ensure_schema(session)
                fi.ensure_schema(session)
                result: dict[str, Any] = {}
                result.update(ai.reconcile_plan_vs_actual(session))
                result.update(ai.train_models(session))
                result.update(fi.train_capacity_models(session))
                result.update(fi.train_planner_policy(session))
                result.update(ai.evaluate_ai_runs(session))
                result.update(fi.refresh_state(session))
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class FactoryIntelligencePage(QWidget):
    """Professional decision-support dashboard for learned factory behavior."""

    def __init__(self, current_user=None, *args, **kwargs):
        super().__init__()
        self.current_user = current_user
        self.service = FactoryIntelligenceService()
        self.worker: _FactoryIntelligenceWorker | None = None
        self.metrics: dict[str, QLabel] = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Factory Intelligence Center")
        title.setStyleSheet("font-size:26px;font-weight:950;color:#0f172a;")
        subtitle = QLabel(
            "Decision-support layer learned from FINAL OVEN plans, verified PROD actuals, "
            "shipment demand, monthly opening stock and historical execution. Newest OVEN "
            "workbook drives live operations; older workbooks train and validate the models."
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet("color:#64748b;font-size:12px;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box, 1)

        self.source_badge = QLabel("Live OVEN: -")
        self.source_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.source_badge.setMinimumWidth(180)
        self.source_badge.setStyleSheet(
            "background:#ecfdf5;color:#166534;border:1px solid #bbf7d0;"
            "border-radius:16px;padding:10px 14px;font-weight:950;"
        )
        self.mode_badge = QLabel("V10 HYBRID ML")
        self.mode_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mode_badge.setMinimumWidth(170)
        self.mode_badge.setStyleSheet(
            "background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;"
            "border-radius:16px;padding:10px 14px;font-weight:950;"
        )
        header.addWidget(self.source_badge)
        header.addWidget(self.mode_badge)
        root.addLayout(header)

        metric_grid = QGridLayout()
        metric_grid.setSpacing(10)
        specs = [
            ("workbooks", "Historical Workbooks"),
            ("actual_days", "Verified Actual Days"),
            ("coverage", "Historical Data Coverage"),
            ("capacity_conf", "Capacity Confidence"),
            ("capacity_models", "Capacity Models"),
            ("aliases", "Learned Identity Aliases"),
            ("unresolved", "Identity Reviews"),
            ("ai_high", "High-Confidence SAP AI"),
        ]
        for i, (key, caption) in enumerate(specs):
            metric_grid.addWidget(self._metric_card(key, caption), i // 4, i % 4)
        root.addLayout(metric_grid)

        controls = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh Intelligence")
        self.refresh_btn.setMinimumHeight(40)
        self.refresh_btn.clicked.connect(self.refresh)
        controls.addWidget(self.refresh_btn)
        self.rebuild_btn = QPushButton("Reconcile + Rebuild ML Models")
        self.rebuild_btn.setMinimumHeight(40)
        self.rebuild_btn.setStyleSheet(
            "background:#2563eb;color:white;border:none;border-radius:8px;"
            "font-weight:950;padding:0 18px;"
        )
        self.rebuild_btn.clicked.connect(self.rebuild_models)
        controls.addWidget(self.rebuild_btn)
        self.notice = QLabel(
            "Auto-control remains disabled until forward validation is strong enough. "
            "Excel is still FINAL; AI is decision support."
        )
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet(
            "background:#fff7ed;color:#9a3412;border:1px solid #fed7aa;"
            "border-radius:8px;padding:8px 12px;font-weight:800;"
        )
        controls.addWidget(self.notice, 1)
        root.addLayout(controls)

        tabs = QTabWidget()
        self.capacity_table = self._table([
            "Level", "Entity", "Samples", "Safe Capacity", "Expected", "Stretch",
            "Recent", "Day Share", "Validation WAPE", "Confidence", "Band", "Trend"
        ])
        self.daily_table = self._table([
            "Date", "Day Actual", "Night Actual", "Total Actual", "Final Plan",
            "Achievement %", "Active SAPs", "Source Workbook"
        ])
        self.identity_table = self._table([
            "Plan Date", "Raw SAP", "Canonical SAP", "Raw Description", "Canonical Description",
            "Confidence", "Method", "Action", "Explanation"
        ])
        identity_panel = QWidget()
        identity_layout = QVBoxLayout(identity_panel)
        identity_layout.setContentsMargins(0, 0, 0, 0)
        identity_layout.setSpacing(8)
        identity_actions = QHBoxLayout()
        approve_suggested = QPushButton("Approve Suggested Mapping")
        approve_suggested.setToolTip(
            "Teach the system that the selected raw description maps to the suggested canonical SAP."
        )
        approve_suggested.clicked.connect(self.approve_selected_identity)
        identity_actions.addWidget(approve_suggested)
        map_to_sap = QPushButton("Map Selected Description to SAP...")
        map_to_sap.setToolTip(
            "Human-supervised correction. The approved mapping is learned for future OVEN imports."
        )
        map_to_sap.clicked.connect(self.map_selected_identity)
        identity_actions.addWidget(map_to_sap)
        identity_hint = QLabel(
            "High-confidence mismatches auto-heal. Ambiguous rows stay in review until a planner approves a mapping."
        )
        identity_hint.setWordWrap(True)
        identity_hint.setStyleSheet("color:#64748b;font-weight:700;")
        identity_actions.addWidget(identity_hint, 1)
        identity_layout.addLayout(identity_actions)
        identity_layout.addWidget(self.identity_table, 1)

        self.opening_table = self._table([
            "Plan Date", "Month", "SAP", "Description", "PROD STOCK Raw",
            "Opening Used", "Mode", "Source Workbook"
        ])
        tabs.addTab(self.capacity_table, "Real Capacity Models")
        tabs.addTab(self.daily_table, "Factory Capacity History")
        tabs.addTab(identity_panel, "Data Identity / Auto-Heal")
        tabs.addTab(self.opening_table, "Opening Stock Evidence")
        root.addWidget(tabs, 1)

    def _metric_card(self, key: str, caption: str) -> QFrame:
        card = QFrame()
        card.setStyleSheet(
            "QFrame{background:#fff;border:1px solid #e2e8f0;border-radius:14px;}"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        value = QLabel("-")
        value.setStyleSheet("font-size:19px;font-weight:950;color:#0f172a;")
        label = QLabel(caption)
        label.setStyleSheet("font-size:10px;font-weight:800;color:#64748b;")
        layout.addWidget(value)
        layout.addWidget(label)
        self.metrics[key] = value
        return card

    @staticmethod
    def _table(headers: list[str]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(36)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        table.horizontalHeader().setStretchLastSection(True)
        return table

    @staticmethod
    def _set_rows(table: QTableWidget, rows: list[list[Any]]) -> None:
        table.setUpdatesEnabled(False)
        try:
            table.setRowCount(len(rows))
            for r, values in enumerate(rows):
                for c, value in enumerate(values):
                    item = QTableWidgetItem("" if value is None else str(value))
                    if c not in {1, 3, 4, len(values)-1}:
                        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    table.setItem(r, c, item)
        finally:
            table.setUpdatesEnabled(True)

    def refresh(self, *args) -> None:
        try:
            with get_session() as session:
                payload = self.service.dashboard(session, limit=500)
                source = OperationalSourceService.latest(session)
            state = payload.get("state", {})
            self.metrics["workbooks"].setText(f"{int(state.get('workbooks') or 0):,}")
            self.metrics["actual_days"].setText(f"{int(state.get('actual_days') or 0):,}")
            self.metrics["coverage"].setText(f"{float(state.get('data_coverage_pct') or 0):.1f}%")
            self.metrics["capacity_conf"].setText(f"{float(state.get('capacity_confidence_pct') or 0):.1f}%")
            self.metrics["capacity_models"].setText(f"{int(state.get('capacity_models') or 0):,}")
            self.metrics["aliases"].setText(f"{int(state.get('aliases') or 0):,}")
            self.metrics["unresolved"].setText(f"{int(state.get('unresolved') or 0):,}")
            self.metrics["ai_high"].setText(f"{int(state.get('ai_high_confidence') or 0):,}")
            if source.plan_date:
                self.source_badge.setText(f"Live OVEN: {source.plan_date.isoformat()}")
                self.source_badge.setToolTip(source.workbook_name or "Newest live workbook")
            else:
                self.source_badge.setText("Live OVEN: not imported")

            capacity_rows = []
            for row in payload.get("capacity_models", []):
                capacity_rows.append([
                    row.get("model_level"), row.get("entity_key"), row.get("sample_days"),
                    self._qty(row.get("safe_capacity_qty")), self._qty(row.get("expected_capacity_qty")),
                    self._qty(row.get("stretch_capacity_qty")), self._qty(row.get("recent_capacity_qty")),
                    f"{float(row.get('day_share') or 0)*100:.1f}%",
                    f"{float(row.get('validation_wape_pct') or 0):.1f}%",
                    f"{float(row.get('confidence_score') or 0)*100:.1f}%",
                    row.get("confidence_band"), f"{float(row.get('trend_score') or 0)*100:+.1f}%",
                ])
            self._set_rows(self.capacity_table, capacity_rows)

            daily_rows = []
            for row in payload.get("daily_capacity", []):
                daily_rows.append([
                    row.get("production_date"), self._qty(row.get("day_actual_qty")),
                    self._qty(row.get("night_actual_qty")), self._qty(row.get("total_actual_qty")),
                    self._qty(row.get("total_plan_qty")), f"{float(row.get('achievement_pct') or 0):.1f}%",
                    row.get("active_sap_count"), row.get("source_workbook"),
                ])
            self._set_rows(self.daily_table, daily_rows)

            identity_rows = []
            for row in payload.get("identity_log", []):
                identity_rows.append([
                    row.get("plan_date"), row.get("raw_sap_code"), row.get("canonical_sap_code"),
                    row.get("raw_description"), row.get("canonical_description"),
                    f"{float(row.get('confidence_score') or 0)*100:.1f}%", row.get("resolution_method"),
                    row.get("action"), row.get("explanation"),
                ])
            self._set_rows(self.identity_table, identity_rows)

            opening_rows = []
            for row in payload.get("opening_stock_evidence", []):
                opening_rows.append([
                    row.get("plan_date"), row.get("month_key"), row.get("sap_code"),
                    row.get("item_description"), self._qty(row.get("raw_stock_qty")),
                    self._qty(row.get("normalized_opening_qty")), row.get("import_mode"), row.get("source_workbook"),
                ])
            self._set_rows(self.opening_table, opening_rows)
        except Exception as exc:
            QMessageBox.critical(self, "Factory Intelligence", str(exc))

    def _selected_identity_values(self) -> tuple[str, str, str] | None:
        row = self.identity_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Identity Review", "Select an identity row first.")
            return None
        raw_desc_item = self.identity_table.item(row, 3)
        canonical_item = self.identity_table.item(row, 2)
        plan_date_item = self.identity_table.item(row, 0)
        raw_desc = raw_desc_item.text().strip() if raw_desc_item else ""
        canonical = canonical_item.text().strip() if canonical_item else ""
        plan_date_text = plan_date_item.text().strip() if plan_date_item else ""
        if not raw_desc:
            QMessageBox.warning(self, "Identity Review", "The selected row has no source description to learn.")
            return None
        return raw_desc, canonical, plan_date_text

    def approve_selected_identity(self) -> None:
        selected = self._selected_identity_values()
        if selected is None:
            return
        raw_desc, canonical, plan_date_text = selected
        if not canonical:
            self.map_selected_identity()
            return
        self._approve_mapping(raw_desc, canonical, plan_date_text)

    def map_selected_identity(self) -> None:
        selected = self._selected_identity_values()
        if selected is None:
            return
        raw_desc, suggested, plan_date_text = selected
        sap, ok = QInputDialog.getText(
            self,
            "Map Description to Canonical SAP",
            f"Source description:\n{raw_desc}\n\nCanonical SAP code:",
            text=suggested,
        )
        if not ok or not sap.strip():
            return
        self._approve_mapping(raw_desc, sap.strip(), plan_date_text)

    def _approve_mapping(self, raw_desc: str, sap: str, plan_date_text: str) -> None:
        try:
            from datetime import date as _date
            plan_date = _date.fromisoformat(plan_date_text) if plan_date_text else None
        except Exception:
            plan_date = None
        try:
            with get_session() as session:
                result = self.service.approve_identity_mapping(
                    session,
                    raw_description=raw_desc,
                    canonical_sap_code=sap,
                    plan_date=plan_date,
                )
                self.service.refresh_state(session)
            QMessageBox.information(
                self,
                "Mapping Learned",
                f"Approved: {raw_desc}\n→ SAP {result['canonical_sap_code']}\n"
                "Future matching OVEN rows can now auto-heal with supervised evidence.",
            )
            self.refresh()
        except Exception as exc:
            QMessageBox.critical(self, "Identity Review", str(exc))

    @staticmethod
    def _qty(value: Any) -> str:
        try:
            return f"{int(round(float(value or 0))):,}"
        except Exception:
            return "0"

    def rebuild_models(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        self.rebuild_btn.setEnabled(False)
        self.rebuild_btn.setText("Rebuilding...")
        worker = _FactoryIntelligenceWorker(self)
        self.worker = worker
        worker.completed.connect(self._rebuild_done)
        worker.failed.connect(self._rebuild_failed)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(self._worker_finished)
        worker.start()

    def _worker_finished(self) -> None:
        self.worker = None
        self.rebuild_btn.setEnabled(True)
        self.rebuild_btn.setText("Reconcile + Rebuild ML Models")

    def _rebuild_done(self, _result: object) -> None:
        self.refresh()

    def _rebuild_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Factory Intelligence", message)


__all__ = ["FactoryIntelligencePage"]
