APP_STYLESHEET = """
/* Factory Oven Production Planning System - Professional UI Theme */

* {
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 10.5pt;
}

QMainWindow {
    background: #f3f6fb;
}

QWidget {
    background: transparent;
    color: #111827;
}

QLabel {
    background: transparent;
    color: #111827;
}

QFrame#AppShell {
    background: #f3f6fb;
}

/* ------------------------------------------------------------------
   Sidebar
------------------------------------------------------------------ */
QFrame#Sidebar {
    background: #0b1220;
    border: none;
}

QLabel#BrandTitle {
    color: #ffffff;
    background: transparent;
    font-size: 18pt;
    font-weight: 900;
}

QLabel#BrandSubtitle {
    color: #94a3b8;
    background: transparent;
    font-size: 9.5pt;
}

QLabel#SidebarCaption {
    color: #94a3b8;
    background: transparent;
    font-size: 8.5pt;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 1.3px;
}

QPushButton#NavButton {
    background: transparent;
    color: #cbd5e1;
    border: none;
    border-radius: 10px;
    padding: 12px 14px;
    text-align: left;
    font-size: 10.5pt;
    font-weight: 700;
}

QPushButton#NavButton:hover {
    background: #1e293b;
    color: #ffffff;
}

QPushButton#NavButton[active="true"] {
    background: #2563eb;
    color: #ffffff;
}

/* ------------------------------------------------------------------
   Top Bar
------------------------------------------------------------------ */
QFrame#TopBar {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
}

QLabel#PageTitle {
    color: #0f172a;
    background: transparent;
    font-size: 20pt;
    font-weight: 900;
}

QLabel#PageSubtitle {
    color: #64748b;
    background: transparent;
    font-size: 9.8pt;
}

QLabel#UserBadge {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 14px;
    color: #1d4ed8;
    padding: 8px 14px;
    font-weight: 800;
}

/* ------------------------------------------------------------------
   Normal Cards / Dashboard Cards
------------------------------------------------------------------ */
QFrame#PanelCard,
QFrame#MetricCard,
QFrame#Card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 16px;
}

QFrame#MetricCard:hover {
    background: #f8fafc;
    border: 1px solid #bfdbfe;
}

QLabel#CardTitle {
    color: #334155;
    background: transparent;
    font-size: 11pt;
    font-weight: 900;
}

QLabel#SectionHint {
    color: #64748b;
    background: transparent;
    font-size: 9.5pt;
}

QLabel#MetricLabel {
    color: #475569;
    background: transparent;
    font-size: 9.4pt;
    font-weight: 900;
}

QLabel#MetricValue {
    color: #0f172a;
    background: transparent;
    font-size: 24pt;
    font-weight: 900;
}

QLabel#MetricHint {
    color: #64748b;
    background: transparent;
    font-size: 9pt;
}

/* ------------------------------------------------------------------
   Summary Rows
------------------------------------------------------------------ */
QFrame#SummaryRow {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
}

QLabel#SummaryLabel {
    color: #475569;
    background: transparent;
    font-size: 9.5pt;
    font-weight: 900;
}

QLabel#SummaryValue {
    color: #0f172a;
    background: transparent;
    font-size: 10.5pt;
    font-weight: 900;
}

/* ------------------------------------------------------------------
   Pills
------------------------------------------------------------------ */
QLabel#InfoPill {
    background: #dbeafe;
    color: #1e40af;
    border-radius: 10px;
    padding: 7px 12px;
    font-weight: 900;
}

QLabel#SuccessPill {
    background: #dcfce7;
    color: #166534;
    border-radius: 10px;
    padding: 7px 12px;
    font-weight: 900;
}

QLabel#WarningPill {
    background: #fef3c7;
    color: #92400e;
    border-radius: 10px;
    padding: 7px 12px;
    font-weight: 900;
}

QLabel#SundayPill {
    background: #fee2e2;
    color: #991b1b;
    border-radius: 10px;
    padding: 7px 12px;
    font-weight: 900;
}

QLabel#HolidayPill {
    background: #fecaca;
    color: #7f1d1d;
    border-radius: 10px;
    padding: 7px 12px;
    font-weight: 900;
}

/* ------------------------------------------------------------------
   Buttons
------------------------------------------------------------------ */
QPushButton {
    background: #1f2937;
    color: #ffffff;
    border: none;
    padding: 9px 15px;
    border-radius: 10px;
    font-weight: 800;
}

QPushButton:hover {
    background: #374151;
}

QPushButton#PrimaryButton {
    background: #2563eb;
    color: #ffffff;
}

QPushButton#PrimaryButton:hover {
    background: #1d4ed8;
}

QPushButton#SecondaryButton {
    background: #e2e8f0;
    color: #0f172a;
}

QPushButton#SecondaryButton:hover {
    background: #cbd5e1;
}

QPushButton#DangerButton {
    background: #dc2626;
    color: #ffffff;
}

QPushButton#DangerButton:hover {
    background: #b91c1c;
}

QPushButton#SoftButton {
    background: #dbeafe;
    color: #1e40af;
    border: none;
    border-radius: 10px;
    padding: 8px 12px;
    font-weight: 900;
}

QPushButton#SoftButton:hover {
    background: #bfdbfe;
    color: #1d4ed8;
}

/* ------------------------------------------------------------------
   Inputs
------------------------------------------------------------------ */
QLineEdit,
QComboBox,
QSpinBox,
QDateEdit,
QDateTimeEdit,
QTextEdit {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 10px;
    padding: 8px 10px;
    selection-background-color: #bfdbfe;
}

QLineEdit:focus,
QComboBox:focus,
QSpinBox:focus,
QDateEdit:focus,
QDateTimeEdit:focus,
QTextEdit:focus {
    border: 1px solid #2563eb;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

/* ------------------------------------------------------------------
   Modern Custom Production Calendar
------------------------------------------------------------------ */
QFrame#ModernCalendarPanel {
    background: #10131a;
    border: 1px solid #1f2937;
    border-radius: 26px;
}

QFrame#CalendarLeftPanel {
    background: transparent;
    border: none;
}

QFrame#CalendarRightPanel {
    background: transparent;
    border: none;
}

QLabel#CalendarSelectedDayName {
    color: #e5e7eb;
    background: transparent;
    font-size: 14pt;
    font-weight: 900;
    letter-spacing: 2px;
}

QLabel#CalendarSelectedDayNumber {
    color: #ffffff;
    background: transparent;
    font-size: 46pt;
    font-weight: 300;
}

QLabel#CalendarSelectedStatus {
    color: #cbd5e1;
    background: transparent;
    font-size: 15pt;
    font-weight: 700;
}

QLabel#CalendarSelectedHint {
    color: #94a3b8;
    background: transparent;
    font-size: 10pt;
}

QLabel#CalendarStatusWorking {
    color: #bbf7d0;
    background: transparent;
    font-size: 15pt;
    font-weight: 800;
}

QLabel#CalendarStatusHoliday {
    color: #fecaca;
    background: transparent;
    font-size: 15pt;
    font-weight: 800;
}

QLabel#CalendarStatusSpecial {
    color: #bfdbfe;
    background: transparent;
    font-size: 15pt;
    font-weight: 800;
}

QLabel#CalendarMonthTitle {
    color: #f8fafc;
    background: transparent;
    font-size: 14pt;
    font-weight: 900;
    letter-spacing: 2px;
}

QPushButton#CalendarNavButton {
    background: rgba(255, 255, 255, 0.08);
    color: #e5e7eb;
    border: none;
    border-radius: 14px;
    min-width: 36px;
    min-height: 34px;
    font-size: 18pt;
    font-weight: 900;
    padding: 0px;
}

QPushButton#CalendarNavButton:hover {
    background: rgba(255, 255, 255, 0.16);
    color: #ffffff;
}

QLabel#CalendarWeekDay {
    color: #e5e7eb;
    background: transparent;
    font-size: 11pt;
    font-weight: 900;
    letter-spacing: 1px;
}

QLabel#CalendarDayCell {
    color: #f8fafc;
    background: transparent;
    border-radius: 18px;
    font-size: 12pt;
    font-weight: 700;
}

QLabel#CalendarDayCell:hover {
    background: rgba(255, 255, 255, 0.10);
}

QLabel#CalendarEmptyCell {
    color: transparent;
    background: transparent;
    border: none;
}

QLabel#CalendarTodayCell {
    color: #ffffff;
    background: rgba(37, 99, 235, 0.35);
    border: 1px solid rgba(96, 165, 250, 0.85);
    border-radius: 18px;
    font-size: 12pt;
    font-weight: 900;
}

QLabel#CalendarSelectedCell {
    color: #111827;
    background: #f9a8d4;
    border-radius: 18px;
    font-size: 12pt;
    font-weight: 900;
}

QLabel#CalendarSundayCell {
    color: #fecaca;
    background: rgba(239, 68, 68, 0.13);
    border-radius: 18px;
    font-size: 12pt;
    font-weight: 900;
}

QLabel#CalendarHolidayCell {
    color: #ffffff;
    background: #dc2626;
    border-radius: 18px;
    font-size: 12pt;
    font-weight: 900;
}

QLabel#CalendarSpecialDayCell {
    color: #052e16;
    background: #86efac;
    border-radius: 18px;
    font-size: 12pt;
    font-weight: 900;
}

QLabel#CalendarLegendSunday {
    color: #fecaca;
    background: rgba(239, 68, 68, 0.12);
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 8.5pt;
    font-weight: 900;
}

QLabel#CalendarLegendHoliday {
    color: #ffffff;
    background: rgba(220, 38, 38, 0.70);
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 8.5pt;
    font-weight: 900;
}

QLabel#CalendarLegendSpecial {
    color: #052e16;
    background: #86efac;
    border-radius: 10px;
    padding: 6px 10px;
    font-size: 8.5pt;
    font-weight: 900;
}

/* ------------------------------------------------------------------
   Calendar Popup Menu
------------------------------------------------------------------ */
QMenu#DateActionMenu {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    padding: 8px;
}

QMenu#DateActionMenu::item {
    padding: 10px 30px;
    border-radius: 8px;
}

QMenu#DateActionMenu::item:selected {
    background: #dbeafe;
    color: #1e40af;
}

QMenu#DateActionMenu::separator {
    height: 1px;
    background: #e2e8f0;
    margin: 6px 4px;
}

/* ------------------------------------------------------------------
   Tables
------------------------------------------------------------------ */
QTableWidget {
    background: #ffffff;
    color: #0f172a;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    gridline-color: #e5e7eb;
    alternate-background-color: #f8fafc;
    selection-background-color: #dbeafe;
    selection-color: #0f172a;
}

QTableWidget::item {
    padding: 8px;
    border: none;
}

QHeaderView::section {
    background: #f1f5f9;
    color: #334155;
    padding: 9px;
    border: none;
    border-right: 1px solid #e2e8f0;
    font-weight: 900;
}

/* ------------------------------------------------------------------
   Progress Bar
------------------------------------------------------------------ */
QProgressBar {
    background: #e2e8f0;
    border: none;
    border-radius: 8px;
    height: 20px;
    text-align: center;
    color: #0f172a;
    font-size: 8.5pt;
    font-weight: 900;
}

QProgressBar::chunk {
    background: #2563eb;
    border-radius: 8px;
}

/* ------------------------------------------------------------------
   Scroll Area / Scroll Bars
------------------------------------------------------------------ */
QScrollArea {
    border: none;
    background: transparent;
}

QScrollArea > QWidget > QWidget {
    background: transparent;
}

QScrollBar:vertical {
    background: #f1f5f9;
    width: 10px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #cbd5e1;
    border-radius: 5px;
}

QScrollBar::handle:vertical:hover {
    background: #94a3b8;
}

QScrollBar:horizontal {
    background: #f1f5f9;
    height: 10px;
    margin: 0px;
}

QScrollBar::handle:horizontal {
    background: #cbd5e1;
    border-radius: 5px;
}

QScrollBar::handle:horizontal:hover {
    background: #94a3b8;
}

/* ------------------------------------------------------------------
   Message Boxes / Dialogs
------------------------------------------------------------------ */
QDialog,
QMessageBox {
    background: #ffffff;
}

QMessageBox QLabel,
QDialog QLabel {
    color: #111827;
    background: transparent;
}
"""