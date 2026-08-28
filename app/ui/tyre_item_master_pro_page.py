from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, QSize, QThread, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QProgressBar, QPushButton, QStackedWidget, QTableView, QVBoxLayout, QWidget,
)

from app.services.tyre_master_matrix_service import TyreMasterMatrixService


def _d(value: Any) -> str:
    if value is None: return "-"
    s = str(value).strip()
    return s or "-"


class MatrixModel(QAbstractTableModel):
    def __init__(self,parent=None):
        super().__init__(parent); self.columns=[]; self.rows=[]

    def set_payload(self,columns,rows):
        self.beginResetModel(); self.columns=list(columns or []); self.rows=list(rows or []); self.endResetModel()

    def rowCount(self,parent=QModelIndex()): return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=QModelIndex()): return 0 if parent.isValid() else len(self.columns)

    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole and orientation==Qt.Orientation.Horizontal and 0<=section<len(self.columns):
            return self.columns[section].get("label","")
        return None

    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return None
        col=self.columns[index.column()]; row=self.rows[index.row()]
        key=col.get("key",""); kind=col.get("kind","TEXT"); value=row.get(key)
        if role==Qt.ItemDataRole.DisplayRole: return _d(value)
        if role==Qt.ItemDataRole.TextAlignmentRole and key!="description":
            return int(Qt.AlignmentFlag.AlignCenter|Qt.AlignmentFlag.AlignVCenter)
        if role==Qt.ItemDataRole.ForegroundRole:
            if kind=="COMPAT":
                if value=="✓": return QColor("#047857")
                if value=="✕": return QColor("#b91c1c")
                return QColor("#64748b")
            if kind=="MATERIAL":
                return QColor("#0f766e" if str(value or "").strip() else "#94a3b8")
        if role==Qt.ItemDataRole.ToolTipRole and kind in {"COMPAT","MATERIAL"}: return _d(value)
        return None


class SimpleModel(QAbstractTableModel):
    def __init__(self,columns,parent=None):
        super().__init__(parent); self.columns=list(columns); self.rows=[]

    def set_rows(self,rows):
        self.beginResetModel(); self.rows=list(rows or []); self.endResetModel()

    def rowCount(self,parent=QModelIndex()): return 0 if parent.isValid() else len(self.rows)
    def columnCount(self,parent=QModelIndex()): return len(self.columns)

    def headerData(self,section,orientation,role=Qt.ItemDataRole.DisplayRole):
        if role==Qt.ItemDataRole.DisplayRole and orientation==Qt.Orientation.Horizontal:
            return self.columns[section][0]
        return None

    def data(self,index,role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid(): return None
        key=self.columns[index.column()][1]; value=self.rows[index.row()].get(key)
        if role==Qt.ItemDataRole.DisplayRole: return _d(value)
        if role==Qt.ItemDataRole.ForegroundRole and key=="issue_count":
            return QColor("#047857" if int(value or 0)==0 else "#b91c1c")
        if role==Qt.ItemDataRole.ForegroundRole and key=="status":
            return QColor("#047857" if str(value).upper()=="TRAINED" else "#b45309")
        return None


class GroupedHeaderView(QHeaderView):
    TOP=24; BOTTOM=32

    def __init__(self,parent=None):
        super().__init__(Qt.Orientation.Horizontal,parent)
        self.setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSectionSize(55)
        self.setSectionsClickable(False)

    def sizeHint(self):
        size=super().sizeHint()
        return QSize(size.width(),self.TOP+self.BOTTOM)

    def _bounds(self,section):
        model=self.model()
        if model is None or not hasattr(model,"columns") or section>=len(model.columns): return section,section
        group=model.columns[section].get("group",""); start=end=section
        while start>0 and model.columns[start-1].get("group","")==group: start-=1
        while end+1<len(model.columns) and model.columns[end+1].get("group","")==group: end+=1
        return start,end

    def paintSection(self,painter:QPainter,rect:QRect,logical_index:int):
        model=self.model()
        if not rect.isValid() or model is None or not hasattr(model,"columns") or logical_index>=len(model.columns):
            return super().paintSection(painter,rect,logical_index)
        col=model.columns[logical_index]; group=str(col.get("group","")); label=str(col.get("label",""))
        start,end=self._bounds(logical_index)
        gx=self.sectionViewportPosition(start)
        gw=sum(self.sectionSize(i) for i in range(start,end+1))
        top=QRect(gx,rect.y(),gw,self.TOP)
        bottom=QRect(rect.x(),rect.y()+self.TOP,rect.width(),self.BOTTOM)
        painter.save(); painter.setClipping(False)
        painter.fillRect(top,QColor("#dbeafe")); painter.setPen(QPen(QColor("#bfdbfe"))); painter.drawRect(top.adjusted(0,0,-1,-1))
        painter.setPen(QColor("#1e3a8a")); painter.drawText(top.adjusted(5,0,-5,0),int(Qt.AlignmentFlag.AlignCenter),group)
        painter.fillRect(bottom,QColor("#edf3f9")); painter.setPen(QPen(QColor("#dbe4ef"))); painter.drawRect(bottom.adjusted(0,0,-1,-1))
        painter.setPen(QColor("#1e293b")); painter.drawText(bottom.adjusted(4,0,-4,0),int(Qt.AlignmentFlag.AlignCenter),label)
        painter.restore()


class ListWorker(QThread):
    completed=Signal(str,object); failed=Signal(str,str)
    def __init__(self,key,search,page,page_size):
        super().__init__(); self.key=key; self.search=search; self.page=page; self.page_size=page_size
    def run(self):
        try:
            fn=TyreMasterMatrixService.matrix_page if self.key=="MATRIX" else TyreMasterMatrixService.quality_page
            self.completed.emit(self.key,fn(self.search,self.page,self.page_size))
        except Exception as exc: self.failed.emit(self.key,str(exc))


class DashboardWorker(QThread):
    completed=Signal(object); failed=Signal(str)
    def run(self):
        try: self.completed.emit(TyreMasterMatrixService.dashboard())
        except Exception as exc: self.failed.emit(str(exc))


class TyreItemMasterProPage(QWidget):
    PAGE_SIZE=100
    TABS=(("Tyre Master","MATRIX"),)

    def __init__(self,*args,**kwargs):
        super().__init__()
        self.active_key="MATRIX"; self.buttons={}; self.pages={}; self.tables={}; self.searches={}; self.status={}; self.progress={}
        self.page_labels={}; self.page_number={"MATRIX":1,"QUALITY":1}; self.page_count={"MATRIX":1,"QUALITY":1}
        self.cache={}; self.workers={}; self.dashboard_worker=None
        self.models={
            "MATRIX":MatrixModel(self),
            "QUALITY":SimpleModel((("SAP Code","sap_code"),("Description","description"),("Issues","issues"),("Issue Count","issue_count"),("Last Seen","last_seen"),("Latest Source","latest_source")),self),
            "AI":SimpleModel((("Module","module_name"),("Purpose","purpose"),("Status","status"),("Training Rows","training_rows"),("History Days","history_days"),("Readiness %","readiness_score"),("Version","model_version"),("Last Trained","last_trained_at")),self),
        }
        self.search_timer=QTimer(self); self.search_timer.setSingleShot(True); self.search_timer.setInterval(350); self.search_timer.timeout.connect(self.search_active)
        self.build_ui()
        QTimer.singleShot(0,lambda:self.activate("MATRIX"))

    def build_ui(self):
        self.setStyleSheet("""
            QWidget{font-family:"Segoe UI";}
            QFrame#Header,QFrame#Panel{background:#fff;border:1px solid #dbe4ef;border-radius:16px;}
            QLabel#Crumb{color:#2563eb;font-weight:950;}
            QLabel#Title{color:#0f172a;font-size:24pt;font-weight:950;}
            QLabel#Sub{color:#64748b;font-size:9pt;font-weight:650;}
            QLabel#Badge{background:#ecfdf5;color:#047857;border:1px solid #a7f3d0;border-radius:12px;padding:8px 12px;font-weight:950;}
            QLabel#Sec{color:#0f172a;font-size:14pt;font-weight:950;}
            QLabel#Status{background:#f8fafc;color:#475569;border:1px solid #e2e8f0;border-radius:9px;padding:7px 10px;font-weight:750;}
            QPushButton#Tab{background:transparent;color:#334155;border:none;padding:10px 18px;font-weight:900;}
            QPushButton#Tab:checked{background:#2563eb;color:white;}
            QPushButton#Secondary{background:#e2e8f0;color:#0f172a;border:none;border-radius:9px;padding:9px 15px;font-weight:900;}
            QLineEdit{background:#fff;border:1px solid #cbd5e1;border-radius:9px;padding:8px 11px;}
            QTableView{background:#fff;alternate-background-color:#f8fafc;border:1px solid #dbe4ef;gridline-color:#e2e8f0;selection-background-color:#dbeafe;selection-color:#0f172a;}
            QTableView::item{padding:5px 7px;}
            QHeaderView::section{background:#edf3f9;color:#1e293b;border:none;border-right:1px solid #dbe4ef;border-bottom:1px solid #dbe4ef;padding:8px;font-weight:950;}
        """)
        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(9)
        header=QFrame(); header.setObjectName("Header"); hr=QHBoxLayout(header); hr.setContentsMargins(22,14,20,14)
        left=QVBoxLayout()
        crumb=QLabel("Data / Tyre Item Master"); crumb.setObjectName("Crumb")
        title=QLabel("Tyre Item Master"); title.setObjectName("Title")
        sub=QLabel("One tyre • one row • all line, cavity, process, material, plan and stock data."); sub.setObjectName("Sub")
        left.addWidget(crumb); left.addWidget(title); left.addWidget(sub); hr.addLayout(left,1)
        self.badge=QLabel("DATABASE AUTHORITY\nAUTO MAPPING"); self.badge.setObjectName("Badge"); self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter); self.badge.setMinimumWidth(180)
        hr.addWidget(self.badge); root.addWidget(header)

        tabs=QHBoxLayout(); tabs.setSpacing(0)
        for label,key in self.TABS:
            b=QPushButton(label); b.setObjectName("Tab"); b.setCheckable(True)
            b.clicked.connect(lambda checked=False,k=key:self.activate(k)); self.buttons[key]=b; tabs.addWidget(b)
        tabs.addStretch(); root.addLayout(tabs)

        self.stack=QStackedWidget()
        self.pages["MATRIX"]=self.build_list("MATRIX","Tyre Master Matrix")
        self.pages["QUALITY"]=self.build_list("QUALITY","Data Quality")
        self.pages["AI"]=self.build_ai()
        for _,key in self.TABS: self.stack.addWidget(self.pages[key])
        root.addWidget(self.stack,1)

    def make_table(self,key):
        t=QTableView(); t.setModel(self.models[key]); t.setAlternatingRowColors(True)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows); t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        t.verticalHeader().setVisible(False); t.verticalHeader().setDefaultSectionSize(36)
        if key=="MATRIX":
            t.setHorizontalHeader(GroupedHeaderView(t)); t.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel); t.setWordWrap(False)
        else:
            t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
            if key in {"QUALITY","AI"}: t.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
            if key=="QUALITY": t.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.tables[key]=t; return t

    def build_list(self,key,title_text):
        p=QFrame(); p.setObjectName("Panel"); l=QVBoxLayout(p); l.setContentsMargins(14,12,14,14)
        bar=QHBoxLayout(); title=QLabel(title_text); title.setObjectName("Sec"); bar.addWidget(title)
        st=QLabel("Not loaded"); st.setObjectName("Status"); self.status[key]=st; bar.addWidget(st); bar.addStretch()
        search=QLineEdit(); search.setPlaceholderText("Search SAP or tyre description..."); search.setMinimumWidth(390)
        search.textChanged.connect(lambda _v,k=key:self.queue_search(k)); self.searches[key]=search; bar.addWidget(search)
        refresh=QPushButton("Refresh"); refresh.setObjectName("Secondary"); refresh.clicked.connect(lambda _=False,k=key:self.reload_list(k)); bar.addWidget(refresh)
        l.addLayout(bar)
        prog=QProgressBar(); prog.setRange(0,0); prog.setTextVisible(False); prog.setMaximumHeight(7); prog.hide(); self.progress[key]=prog; l.addWidget(prog)
        l.addWidget(self.make_table(key),1)
        foot=QHBoxLayout()
        prev=QPushButton("← Previous"); prev.setObjectName("Secondary"); prev.clicked.connect(lambda _=False,k=key:self.change_page(k,-1)); foot.addWidget(prev)
        lab=QLabel("Page 1 / 1"); lab.setObjectName("Status"); self.page_labels[key]=lab; foot.addWidget(lab)
        nxt=QPushButton("Next →"); nxt.setObjectName("Secondary"); nxt.clicked.connect(lambda _=False,k=key:self.change_page(k,1)); foot.addWidget(nxt); foot.addStretch()
        rows=QLabel(f"{self.PAGE_SIZE} rows / page"); rows.setObjectName("Status"); foot.addWidget(rows)
        if key=="MATRIX":
            hint=QLabel("Horizontal scroll → Lines • Cavities • Process • Materials • Plan/Stock"); hint.setObjectName("Status"); foot.addWidget(hint)
        l.addLayout(foot); return p

    def build_ai(self):
        p=QFrame(); p.setObjectName("Panel"); l=QVBoxLayout(p); l.setContentsMargins(14,12,14,14)
        bar=QHBoxLayout(); title=QLabel("AI / ML Intelligence"); title.setObjectName("Sec"); bar.addWidget(title); bar.addStretch()
        refresh=QPushButton("Refresh Intelligence"); refresh.setObjectName("Secondary"); refresh.clicked.connect(self.load_dashboard); bar.addWidget(refresh); l.addLayout(bar)
        self.ai_status=QLabel("AI / ML uses the same database-authority Tyre Master."); self.ai_status.setObjectName("Status"); self.ai_status.setWordWrap(True); l.addWidget(self.ai_status)
        self.ai_progress=QProgressBar(); self.ai_progress.setRange(0,0); self.ai_progress.setTextVisible(False); self.ai_progress.hide(); l.addWidget(self.ai_progress)
        l.addWidget(self.make_table("AI"),1); return p

    def activate(self,key):
        self.active_key=key
        for k,b in self.buttons.items(): b.blockSignals(True); b.setChecked(k==key); b.blockSignals(False)
        keys=[k for _,k in self.TABS]; self.stack.setCurrentIndex(keys.index(key))
        if key in {"MATRIX","QUALITY"}: self.load_list(key)
        else: self.load_dashboard()

    def queue_search(self,key):
        if key==self.active_key: self.search_timer.start()

    def search_active(self):
        if self.active_key in {"MATRIX","QUALITY"}:
            self.page_number[self.active_key]=1; self.load_list(self.active_key,True)

    def cache_key(self,key): return (key,self.searches[key].text().strip(),self.page_number[key])

    def load_list(self,key,force=False):
        ck=self.cache_key(key)
        if not force and ck in self.cache: self.apply_result(key,self.cache[ck],True); return
        w=self.workers.get(key)
        if w is not None and w.isRunning(): return
        self.progress[key].show(); self.status[key].setText("Loading in background...")
        w=ListWorker(key,self.searches[key].text().strip(),self.page_number[key],self.PAGE_SIZE); w.setParent(self)
        w.completed.connect(self.list_loaded); w.failed.connect(self.list_failed)
        w.finished.connect(lambda k=key:self.workers.pop(k,None)); w.finished.connect(w.deleteLater)
        self.workers[key]=w; w.start()

    def list_loaded(self,key,result):
        result=dict(result or {}); ck=(key,self.searches[key].text().strip(),int(result.get("page") or 1)); self.cache[ck]=result; self.apply_result(key,result,False)

    def apply_result(self,key,result,cached=False):
        self.progress[key].hide()
        if key=="MATRIX":
            self.models[key].set_payload(result.get("columns") or [],result.get("rows") or []); self.configure_widths()
        else: self.models[key].set_rows(result.get("rows") or [])
        p=int(result.get("page") or 1); pc=int(result.get("page_count") or 1); self.page_number[key]=p; self.page_count[key]=pc
        self.page_labels[key].setText(f"Page {p} / {pc}")
        self.status[key].setText(f"{int(result.get('total') or 0):,} records"+(" • cached" if cached else ""))

    def configure_widths(self):
        t=self.tables["MATRIX"]
        for i,col in enumerate(self.models["MATRIX"].columns):
            key=col.get("key",""); kind=col.get("kind","TEXT")
            width=360 if key=="description" else 95 if key=="sap_code" else 100 if key=="tyre_size" else 95 if kind=="COMPAT" else 160 if kind=="MATERIAL" else 180 if key=="latest_source" else 105
            t.setColumnWidth(i,width)

    def list_failed(self,key,message):
        self.progress[key].hide(); self.status[key].setText("Load failed"); self.status[key].setToolTip(str(message))

    def change_page(self,key,delta):
        target=max(1,min(self.page_count[key],self.page_number[key]+int(delta)))
        if target!=self.page_number[key]: self.page_number[key]=target; self.load_list(key)

    def reload_list(self,key):
        for ck in list(self.cache):
            if ck[0]==key: self.cache.pop(ck,None)
        self.load_list(key,True)

    def load_dashboard(self):
        if self.dashboard_worker is not None and self.dashboard_worker.isRunning(): return
        self.ai_progress.show(); w=DashboardWorker(); w.setParent(self); w.completed.connect(self.dashboard_loaded); w.failed.connect(self.dashboard_failed)
        w.finished.connect(lambda:setattr(self,"dashboard_worker",None)); w.finished.connect(w.deleteLater); self.dashboard_worker=w; w.start()

    def dashboard_loaded(self,dashboard):
        self.ai_progress.hide(); d=dict(dashboard or {}); self.models["AI"].set_rows(d.get("modules") or [])
        state=dict(d.get("sync_state") or {})
        self.badge.setText("DATABASE AUTHORITY\n"+f"{int(state.get('line_links') or 0):,} LINE • {int(state.get('cavity_links') or 0):,} CAVITY\nAUTO MAPPING")
        self.badge.setToolTip(str(state.get("message") or ""))
        self.ai_status.setText(f"{int(d.get('item_count') or 0):,} tyre items • {int(state.get('line_links') or 0):,} confirmed line links • {int(state.get('cavity_links') or 0):,} cavity links • {int(state.get('material_links') or 0):,} material links.")

    def dashboard_failed(self,message):
        self.ai_progress.hide(); self.ai_status.setText(f"AI / ML dashboard failed: {message}")

    def notify_master_synced(self,result=None):
        self.cache.clear()
        if self.active_key in {"MATRIX","QUALITY"}:
            self.page_number[self.active_key]=1; self.load_list(self.active_key,True)
        self.load_dashboard()

    def refresh_async(self):
        if self.active_key in {"MATRIX","QUALITY"}: self.reload_list(self.active_key)
        else: self.load_dashboard()

    refresh=refresh_async
    refresh_page=refresh_async
    load_data=refresh_async
