"""
gui/main_window.py — Main application window.

Three tabs: Setup, Macro Editor, Live Log.
Start/Stop controls the background voice engine thread.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from gui.engine import VoiceEngine
from gui.log_tab import LogTab
from gui.macro_tab import MacroTab
from gui.setup_tab import SetupTab
from gui.styles import DARK_THEME

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"
PROFILES_DIR = BASE_DIR / "profiles"


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Voice-to-Macro")
        self.setMinimumSize(900, 600)
        self.resize(1000, 700)

        self._engine: VoiceEngine | None = None

        self._build_ui()
        self.setStyleSheet(DARK_THEME)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(8, 8, 8, 8)

        # Top bar: Start / Stop
        top = QHBoxLayout()
        self.start_btn = QPushButton("Start")
        self.start_btn.setObjectName("startBtn")
        self.start_btn.setMinimumWidth(120)
        self.start_btn.clicked.connect(self._start_engine)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("stopBtn")
        self.stop_btn.setMinimumWidth(120)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_engine)

        self.engine_status = QLabel("STOPPED")
        self.engine_status.setObjectName("statusLabelStopped")

        top.addWidget(self.start_btn)
        top.addWidget(self.stop_btn)
        top.addStretch()
        top.addWidget(self.engine_status)
        root.addLayout(top)

        # Tabs
        self.tabs = QTabWidget()

        self.setup_tab = SetupTab()
        self.setup_tab.config_saved.connect(self._on_config_saved)
        self.tabs.addTab(self.setup_tab, "Setup")

        self.macro_tab = MacroTab()
        self.tabs.addTab(self.macro_tab, "Macros")

        self.log_tab = LogTab()
        self.tabs.addTab(self.log_tab, "Live Log")

        root.addWidget(self.tabs)

    # ------------------------------------------------------------------
    # Engine lifecycle
    # ------------------------------------------------------------------

    def _load_config(self) -> dict | None:
        if not CONFIG_PATH.exists():
            QMessageBox.warning(
                self, "No Config",
                "config.yaml not found.\nGo to the Setup tab and save a configuration first.",
            )
            return None
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _load_profile(self, name: str) -> dict | None:
        path = PROFILES_DIR / f"{name}.json"
        if not path.exists():
            QMessageBox.warning(self, "Profile Missing", f"Profile '{name}' not found at {path}")
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _start_engine(self) -> None:
        if self._engine and self._engine.isRunning():
            return

        config = self._load_config()
        if not config:
            return

        profile_name = config.get("active_profile", "generic")
        profile = self._load_profile(profile_name)
        if not profile:
            return

        self._engine = VoiceEngine(config=config, profile=profile, parent=self)
        self._engine.log.connect(self.log_tab.append_log)
        self._engine.status.connect(self._on_status)
        self._engine.recording.connect(self.log_tab.set_recording)
        self._engine.finished.connect(self._on_engine_finished)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.engine_status.setText("STARTING...")
        self.engine_status.setObjectName("statusLabel")
        self.engine_status.setStyleSheet("")  # reset to pick up new objectName style

        self.log_tab.set_status("STARTING")
        self.tabs.setCurrentWidget(self.log_tab)

        self._engine.start()

    def _stop_engine(self) -> None:
        if self._engine:
            self._engine.stop()
            self.stop_btn.setEnabled(False)
            self.engine_status.setText("STOPPING...")

    def _on_engine_finished(self) -> None:
        self._engine = None
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.engine_status.setText("STOPPED")
        self.engine_status.setObjectName("statusLabelStopped")
        self.engine_status.setStyleSheet("")
        self.log_tab.set_status("STOPPED")

    def _on_status(self, status: str) -> None:
        self.engine_status.setText(status)
        self.log_tab.set_status(status)

    def _on_config_saved(self, cfg: dict) -> None:
        """When config is saved, sync the macro tab to the new profile."""
        profile_name = cfg.get("active_profile", "generic")
        self.macro_tab.set_profile(profile_name)

    # ------------------------------------------------------------------
    # Close event
    # ------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        if self._engine and self._engine.isRunning():
            self._engine.stop()
            self._engine.wait(3000)
        event.accept()
