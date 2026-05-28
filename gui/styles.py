"""
gui/styles.py — Shared dark theme stylesheet for the Voice-to-Macro GUI.
"""

DARK_THEME = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Consolas", monospace;
    font-size: 13px;
}

QTabWidget::pane {
    border: 1px solid #45475a;
    background-color: #1e1e2e;
}

QTabBar::tab {
    background-color: #313244;
    color: #cdd6f4;
    padding: 8px 20px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
}

QTabBar::tab:selected {
    background-color: #45475a;
    color: #89b4fa;
    font-weight: bold;
}

QTabBar::tab:hover {
    background-color: #585b70;
}

QPushButton {
    background-color: #45475a;
    color: #cdd6f4;
    border: 1px solid #585b70;
    border-radius: 6px;
    padding: 6px 16px;
    min-height: 28px;
}

QPushButton:hover {
    background-color: #585b70;
}

QPushButton:pressed {
    background-color: #89b4fa;
    color: #1e1e2e;
}

QPushButton#startBtn {
    background-color: #a6e3a1;
    color: #1e1e2e;
    font-weight: bold;
    font-size: 14px;
}

QPushButton#startBtn:hover {
    background-color: #94e2d5;
}

QPushButton#stopBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
    font-weight: bold;
    font-size: 14px;
}

QPushButton#stopBtn:hover {
    background-color: #eba0ac;
}

QPushButton#deleteBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
}

QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #585b70;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 26px;
}

QComboBox::drop-down {
    border: none;
}

QComboBox QAbstractItemView {
    background-color: #313244;
    color: #cdd6f4;
    selection-background-color: #45475a;
}

QLineEdit, QSpinBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #585b70;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 26px;
}

QTextEdit {
    background-color: #11111b;
    color: #a6e3a1;
    border: 1px solid #45475a;
    border-radius: 4px;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
}

QTableWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    gridline-color: #45475a;
    border: 1px solid #45475a;
    border-radius: 4px;
}

QTableWidget::item {
    padding: 4px;
}

QTableWidget::item:selected {
    background-color: #45475a;
    color: #89b4fa;
}

QHeaderView::section {
    background-color: #313244;
    color: #89b4fa;
    border: 1px solid #45475a;
    padding: 6px;
    font-weight: bold;
}

QLabel#sectionLabel {
    color: #89b4fa;
    font-size: 14px;
    font-weight: bold;
    padding-top: 8px;
}

QLabel#statusLabel {
    color: #a6e3a1;
    font-size: 13px;
    padding: 4px;
}

QLabel#statusLabelStopped {
    color: #f38ba8;
    font-size: 13px;
    padding: 4px;
}

QGroupBox {
    border: 1px solid #45475a;
    border-radius: 6px;
    margin-top: 12px;
    padding-top: 18px;
    font-weight: bold;
    color: #89b4fa;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}

QScrollBar:vertical {
    background-color: #1e1e2e;
    width: 10px;
}

QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 5px;
    min-height: 20px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""
