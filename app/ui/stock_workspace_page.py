from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from typing import Any

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.core.task_manager import TaskManager


class StockWorkspacePage(QWidget):
    """Unified stock shell with truly lazy child-module loading.

    R5 intentionally avoids importing Monthly/Current/Daily stock modules while the
    Stock Master route is being constructed.  Module import runs in the worker pool;
    only QWidget construction returns to the GUI thread after the shell has painted.
    """

    TAB_MONTHLY = 0
    TAB_CURRENT = 1
    TAB_DAILY = 2

    TAB_SPECS = {
        TAB_MONTHLY: (
            "Monthly Stock",
            "app.ui.monthly_stock_page",
            "MonthlyStockPage",
            {"on_back": None},
        ),
        TAB_CURRENT: (
            "Current Stock",
            "app.ui.current_stock_page",
            "CurrentStockPage",
            {"on_back": None},
        ),
        TAB_DAILY: (
            "Daily Stock",
            "app.ui.daily_stock_page",
            "DailyStockPage",
            {},
        ),
    }

    TASK_PREFIX = "stock-workspace-r5:"

    def __init__(self, on_back: Callable[[], None] | None = None):
        super().__init__()
        self.on_back = on_back
        self.task_manager = TaskManager.instance()
        self._pages: dict[int, QWidget] = {}
        self._loading_tabs: set[int] = set()
        self._generation: dict[int, int] = {}
        self._apply_styles()
        self._build_ui()
        QTimer.singleShot(24, lambda: self._ensure_tab_loaded(self.tabs.currentIndex()))

    def _apply_styles(self) -> None:
        self.setStyleSheet(
            """
            QFrame#StockWorkspaceHeader,QFrame#StockLoadingCard {
                background:#ffffff;border:1px solid #dbe4f0;border-radius:14px;
            }
            QLabel#StockBreadcrumb{color:#2563eb;font-size:9pt;font-weight:900;}
            QLabel#StockTitle{color:#0f172a;font-size:22pt;font-weight:950;}
            QLabel#StockLoadingTitle{color:#0f172a;font-size:14pt;font-weight:950;}
            QLabel#StockLoadingHint{color:#64748b;font-weight:700;}
            QPushButton#StockSecondary{
                background:#e2e8f0;color:#0f172a;border:none;border-radius:8px;
                padding:8px 13px;font-weight:900;
            }
            QTabWidget#StockWorkspaceTabs::pane{border:none;background:transparent;top:-1px;}
            QTabWidget#StockWorkspaceTabs QTabBar::tab{
                background:#f1f5f9;color:#334155;border:none;padding:10px 18px;
                margin-right:2px;font-size:9pt;font-weight:900;min-width:150px;
            }
            QTabWidget#StockWorkspaceTabs QTabBar::tab:selected{background:#2563eb;color:#fff;}
            """
        )

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)
        root.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.setObjectName("StockWorkspaceTabs")
        self.tabs.setDocumentMode(True)
        for index in (self.TAB_MONTHLY, self.TAB_CURRENT, self.TAB_DAILY):
            title = self.TAB_SPECS[index][0]
            self.tabs.addTab(
                self._loading_page(title, f"Preparing {title.lower()} in background..."),
                title,
            )
        self.tabs.currentChanged.connect(self._on_tab_changed)
        root.addWidget(self.tabs, 1)

    def _build_header(self) -> QFrame:
        card = QFrame()
        card.setObjectName("StockWorkspaceHeader")
        row = QHBoxLayout(card)
        row.setContentsMargins(20, 13, 20, 13)
        left = QVBoxLayout()
        crumb = QLabel("Data / Stock Master")
        crumb.setObjectName("StockBreadcrumb")
        title = QLabel("Stock Master")
        title.setObjectName("StockTitle")
        left.addWidget(crumb)
        left.addWidget(title)
        row.addLayout(left, 1)
        back = QPushButton("Back")
        back.setObjectName("StockSecondary")
        if self.on_back is not None:
            back.clicked.connect(self.on_back)
        else:
            back.setEnabled(False)
        row.addWidget(back)
        return card

    @staticmethod
    def _loading_page(title: str, hint: str) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        card = QFrame()
        card.setObjectName("StockLoadingCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(22, 20, 22, 20)
        title_label = QLabel(title)
        title_label.setObjectName("StockLoadingTitle")
        hint_label = QLabel(hint)
        hint_label.setObjectName("StockLoadingHint")
        hint_label.setWordWrap(True)
        card_layout.addWidget(title_label)
        card_layout.addWidget(hint_label)
        card_layout.addStretch()
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _on_tab_changed(self, index: int) -> None:
        QTimer.singleShot(0, lambda idx=index: self._ensure_tab_loaded(idx))

    def _ensure_tab_loaded(self, index: int) -> None:
        if index in self._pages or index in self._loading_tabs:
            return
        spec = self.TAB_SPECS.get(index)
        if spec is None:
            return

        self._loading_tabs.add(index)
        generation = self._generation.get(index, 0) + 1
        self._generation[index] = generation
        _title, module_name, _class_name, _kwargs = spec

        self.task_manager.submit(
            self.TASK_PREFIX + f"import:{index}",
            lambda module=module_name: bool(import_module(module)),
            on_result=lambda _ok, idx=index, gen=generation: self._construct_tab(idx, gen),
            on_error=lambda message, idx=index, gen=generation: self._tab_error(idx, gen, message),
            priority=-1,
            replace=True,
        )

    def _construct_tab(self, index: int, generation: int) -> None:
        if self._generation.get(index) != generation or index in self._pages:
            self._loading_tabs.discard(index)
            return
        spec = self.TAB_SPECS[index]
        title, module_name, class_name, kwargs = spec
        try:
            cls = getattr(import_module(module_name), class_name)
            page = cls(**dict(kwargs))
            self._prepare_embedded_page(page)
            old = self.tabs.widget(index)
            self.tabs.removeTab(index)
            self.tabs.insertTab(index, page, title)
            if old is not None:
                old.deleteLater()
            self._pages[index] = page
            if self.tabs.currentIndex() != index:
                self.tabs.setCurrentIndex(index)
        except Exception as exc:
            self._tab_error(index, generation, str(exc))
            return
        finally:
            self._loading_tabs.discard(index)

        # Warm only Python imports for the other tabs at low priority. No widget or
        # database work is started until the user opens that tab.
        for other, other_spec in self.TAB_SPECS.items():
            if other == index or other in self._pages:
                continue
            module = other_spec[1]
            self.task_manager.submit(
                self.TASK_PREFIX + f"warm:{other}",
                lambda name=module: bool(import_module(name)),
                priority=-2,
                replace=True,
            )

    def _tab_error(self, index: int, generation: int, message: str) -> None:
        if self._generation.get(index) != generation:
            return
        self._loading_tabs.discard(index)
        title = self.TAB_SPECS.get(index, ("Stock",))[0]
        old = self.tabs.widget(index)
        error = self._loading_page(title, "Workspace load failed: " + (message.splitlines()[-1] if message else "unknown error"))
        self.tabs.removeTab(index)
        self.tabs.insertTab(index, error, title)
        if old is not None:
            old.deleteLater()

    @staticmethod
    def _prepare_embedded_page(page: QWidget) -> None:
        for frame in page.findChildren(QFrame):
            if frame.objectName() == "HeaderCard":
                frame.hide()
                break
        page.setContentsMargins(0, 0, 0, 0)

    def refresh_current_tab(self) -> None:
        index = self.tabs.currentIndex()
        self._ensure_tab_loaded(index)
        page = self._pages.get(index)
        if page is None:
            return
        refresh = getattr(page, "refresh", None)
        if callable(refresh):
            QTimer.singleShot(0, refresh)
            return
        refresh_table = getattr(page, "refresh_table", None)
        if callable(refresh_table):
            QTimer.singleShot(0, refresh_table)

    def handle_domain_event(self, event: Any) -> None:
        for page in list(self._pages.values()):
            handler = getattr(page, "handle_domain_event", None)
            if callable(handler):
                handler(event)
