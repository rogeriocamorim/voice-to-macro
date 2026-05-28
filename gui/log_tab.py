"""
gui/log_tab.py — Live execution log tab.

Displays timestamped, color-coded log entries from the voice engine.
Supports auto-scroll, clear, and copy-to-clipboard.
"""

from __future__ import annotations

from datetime import datetime

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# Color map for log line prefixes
_COLORS = {
    "[STT]": "#89b4fa",       # blue
    "Heard:": "#94e2d5",      # teal
    "Intent:": "#cba6f7",     # mauve
    "Executed": "#a6e3a1",    # green
    "Learned": "#a6e3a1",     # green
    "Clarified": "#f9e2af",   # yellow
    "[ERROR]": "#f38ba8",     # red
    "ignored": "#6c7086",     # grey
    "silence": "#6c7086",     # grey
    "nothing": "#6c7086",     # grey
    "IDLE": "#6c7086",
    "RECORDING": "#f38ba8",
    "TRANSCRIBING": "#89b4fa",
    "CLASSIFYING": "#cba6f7",
    "EXEC:": "#a6e3a1",
}


class LogTab(QWidget):
    """Read-only scrolling log viewer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._auto_scroll = True
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Status bar
        status_row = QHBoxLayout()
        self.status_indicator = QLabel("\u25cf")  # ●
        self.status_indicator.setStyleSheet("color: #6c7086; font-size: 18px;")
        self.status_label = QLabel("STOPPED")
        self.status_label.setStyleSheet("color: #6c7086; font-size: 14px; font-weight: bold;")
        status_row.addWidget(self.status_indicator)
        status_row.addWidget(self.status_label)
        status_row.addStretch()

        self.clear_btn = QPushButton("Clear Log")
        self.clear_btn.clicked.connect(self._clear)
        self.copy_btn = QPushButton("Copy All")
        self.copy_btn.clicked.connect(self._copy_all)
        status_row.addWidget(self.clear_btn)
        status_row.addWidget(self.copy_btn)
        layout.addLayout(status_row)

        # Log view
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.log_view)

    def append_log(self, message: str) -> None:
        """Append a timestamped, color-coded line."""
        color = "#cdd6f4"  # default
        for keyword, c in _COLORS.items():
            if keyword in message:
                color = c
                break

        html = f'<span style="color:{color}">{_escape(message)}</span>'
        self.log_view.append(html)

        if self._auto_scroll:
            cursor = self.log_view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            self.log_view.setTextCursor(cursor)

    def set_status(self, status: str) -> None:
        """Update the status indicator and label."""
        self.status_label.setText(status)

        color_map = {
            "IDLE": "#6c7086",
            "STOPPED": "#f38ba8",
            "LOADING STT": "#f9e2af",
            "RECORDING": "#f38ba8",
            "TRANSCRIBING": "#89b4fa",
            "LISTENING": "#a6e3a1",
            "CLASSIFYING": "#cba6f7",
            "CLARIFYING": "#f9e2af",
        }

        # EXEC: <action> uses green
        if status.startswith("EXEC:"):
            color = "#a6e3a1"
        else:
            color = color_map.get(status, "#cdd6f4")

        self.status_indicator.setStyleSheet(f"color: {color}; font-size: 18px;")
        self.status_label.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")

    def set_recording(self, active: bool) -> None:
        """Flash the recording indicator."""
        if active:
            self.status_indicator.setStyleSheet("color: #f38ba8; font-size: 18px;")
        # Don't override if engine sets a more specific status

    def _clear(self) -> None:
        self.log_view.clear()

    def _copy_all(self) -> None:
        from PyQt6.QtWidgets import QApplication
        text = self.log_view.toPlainText()
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(text)


def _escape(text: str) -> str:
    """HTML-escape for safe embedding in QTextEdit."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace("'", "&#39;")
    )
