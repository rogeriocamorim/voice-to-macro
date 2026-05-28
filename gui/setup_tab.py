"""
gui/setup_tab.py — Setup / Configuration tab.

Lets the user configure: profile, Ollama model, PTT key, listening mode,
Whisper model, device (CPU/CUDA), and personality. Reads/writes config.yaml.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import yaml
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.yaml"
PROFILES_DIR = BASE_DIR / "profiles"

OLLAMA_MODELS = [
    ("qwen2.5:3b", "3B, ~2GB VRAM — RECOMMENDED for classification"),
    ("qwen3:4b", "4B, ~3GB VRAM — newest Qwen"),
    ("llama3.2:3b", "3B, ~2GB VRAM — Meta"),
    ("llama3.2:1b", "1B, ~1.3GB VRAM — ultra-fast"),
    ("mistral", "7B, ~4.4GB VRAM — overkill but accurate"),
    ("phi3:mini", "3.8B, ~2.3GB VRAM — no tools"),
]

WHISPER_MODELS = [
    ("tiny", "~1GB VRAM — fastest, least accurate"),
    ("base", "~1GB VRAM — fast, decent"),
    ("small", "~2GB VRAM — balanced"),
    ("medium", "~5GB VRAM — recommended GPU"),
    ("large-v3", "~10GB VRAM — best accuracy"),
]

MODES = [("ptt", "Push-to-Talk"), ("always_on", "Always On (VAD)")]
PERSONALITIES = [("game_themed", "Game Themed"), ("generic", "Generic")]


# ---------------------------------------------------------------------------
# Background thread for pulling Ollama models
# ---------------------------------------------------------------------------

class _PullModelThread(QThread):
    finished = pyqtSignal(bool, str)  # (success, message)

    def __init__(self, model: str, parent=None):
        super().__init__(parent)
        self._model = model

    def run(self):
        try:
            result = subprocess.run(
                ["ollama", "pull", self._model],
                capture_output=True,
                text=True,
                timeout=600,
            )
            if result.returncode == 0:
                self.finished.emit(True, f"Model '{self._model}' pulled successfully.")
            else:
                self.finished.emit(False, f"Pull failed: {result.stderr.strip()}")
        except FileNotFoundError:
            self.finished.emit(False, "Ollama binary not found. Install from https://ollama.com/download")
        except subprocess.TimeoutExpired:
            self.finished.emit(False, "Pull timed out after 10 minutes.")
        except Exception as e:
            self.finished.emit(False, str(e))


class SetupTab(QWidget):
    """Configuration tab — reads/writes config.yaml."""

    config_saved = pyqtSignal(dict)  # emitted after save so other tabs can reload

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pull_thread: _PullModelThread | None = None
        self._build_ui()
        self._load_config()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # --- Profile & Mode ---
        grp_general = QGroupBox("General")
        form1 = QFormLayout()

        self.profile_combo = QComboBox()
        self._populate_profiles()
        form1.addRow("Game Profile:", self.profile_combo)

        self.mode_combo = QComboBox()
        for value, label in MODES:
            self.mode_combo.addItem(label, value)
        form1.addRow("Listening Mode:", self.mode_combo)

        self.ptt_key_edit = QLineEdit()
        self.ptt_key_edit.setPlaceholderText("e.g. t, caps_lock, f13")
        form1.addRow("PTT Key:", self.ptt_key_edit)

        self.personality_combo = QComboBox()
        for value, label in PERSONALITIES:
            self.personality_combo.addItem(label, value)
        form1.addRow("Personality:", self.personality_combo)

        grp_general.setLayout(form1)
        layout.addWidget(grp_general)

        # --- Models ---
        grp_models = QGroupBox("Models")
        form2 = QFormLayout()

        self.ollama_combo = QComboBox()
        for value, desc in OLLAMA_MODELS:
            self.ollama_combo.addItem(f"{value}  —  {desc}", value)
        form2.addRow("Ollama Model:", self.ollama_combo)

        pull_row = QHBoxLayout()
        self.pull_btn = QPushButton("Pull Model")
        self.pull_btn.clicked.connect(self._pull_model)
        self.pull_status = QLabel("")
        pull_row.addWidget(self.pull_btn)
        pull_row.addWidget(self.pull_status, 1)
        form2.addRow("", pull_row)

        self.whisper_combo = QComboBox()
        for value, desc in WHISPER_MODELS:
            self.whisper_combo.addItem(f"{value}  —  {desc}", value)
        form2.addRow("Whisper Model:", self.whisper_combo)

        self.device_combo = QComboBox()
        self.device_combo.addItem("cuda (GPU)", "cuda")
        self.device_combo.addItem("cpu", "cpu")
        form2.addRow("Device:", self.device_combo)

        grp_models.setLayout(form2)
        layout.addWidget(grp_models)

        # --- Ollama Status ---
        grp_status = QGroupBox("Ollama Status")
        status_layout = QHBoxLayout()
        self.ollama_status_label = QLabel("Not checked")
        self.check_ollama_btn = QPushButton("Check Now")
        self.check_ollama_btn.clicked.connect(self._check_ollama)
        status_layout.addWidget(self.ollama_status_label, 1)
        status_layout.addWidget(self.check_ollama_btn)
        grp_status.setLayout(status_layout)
        layout.addWidget(grp_status)

        # --- Save ---
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.save_btn = QPushButton("Save Configuration")
        self.save_btn.setMinimumWidth(180)
        self.save_btn.clicked.connect(self._save_config)
        btn_row.addWidget(self.save_btn)
        layout.addLayout(btn_row)

        layout.addStretch()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _populate_profiles(self) -> None:
        self.profile_combo.clear()
        if PROFILES_DIR.exists():
            for p in sorted(PROFILES_DIR.glob("*.json")):
                name = p.stem
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    display = data.get("game", name)
                except Exception:
                    display = name
                self.profile_combo.addItem(display, name)

    def _load_config(self) -> None:
        if not CONFIG_PATH.exists():
            return
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            return

        # Profile
        idx = self.profile_combo.findData(cfg.get("active_profile", "generic"))
        if idx >= 0:
            self.profile_combo.setCurrentIndex(idx)

        # Mode
        idx = self.mode_combo.findData(cfg.get("mode", "ptt"))
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)

        # PTT key
        self.ptt_key_edit.setText(cfg.get("ptt_key", "caps_lock"))

        # Personality
        idx = self.personality_combo.findData(cfg.get("personality", "generic"))
        if idx >= 0:
            self.personality_combo.setCurrentIndex(idx)

        # Ollama model
        model = cfg.get("model", "qwen2.5:3b")
        idx = self.ollama_combo.findData(model)
        if idx >= 0:
            self.ollama_combo.setCurrentIndex(idx)

        # Whisper
        idx = self.whisper_combo.findData(cfg.get("whisper_model", "small"))
        if idx >= 0:
            self.whisper_combo.setCurrentIndex(idx)

        # Device
        idx = self.device_combo.findData(cfg.get("device", "cpu"))
        if idx >= 0:
            self.device_combo.setCurrentIndex(idx)

    def _get_selected_ollama_model(self) -> str:
        """Return the model tag from the dropdown selection."""
        return self.ollama_combo.currentData() or "qwen2.5:3b"

    def _save_config(self) -> None:
        ptt_key = self.ptt_key_edit.text().strip()
        if not ptt_key:
            QMessageBox.warning(self, "Validation", "PTT key cannot be empty.")
            return

        cfg = {
            "active_profile": self.profile_combo.currentData() or "generic",
            "mode": self.mode_combo.currentData() or "ptt",
            "ptt_key": ptt_key,
            "personality": self.personality_combo.currentData() or "generic",
            "model": self._get_selected_ollama_model(),
            "whisper_model": self.whisper_combo.currentData() or "small",
            "device": self.device_combo.currentData() or "cpu",
            "sample_rate": 16000,
            "vad_threshold": 0.5,
            "confidence_threshold": 0.6,
        }

        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                yaml.dump(cfg, f, default_flow_style=False, sort_keys=False)
            self.config_saved.emit(cfg)
            QMessageBox.information(self, "Saved", "Configuration saved to config.yaml")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save config:\n{e}")

    def _check_ollama(self) -> None:
        binary = bool(shutil.which("ollama"))
        server = False
        if binary:
            try:
                urllib.request.urlopen("http://localhost:11434", timeout=3)
                server = True
            except Exception:
                pass

        if not binary:
            self.ollama_status_label.setText("Not installed — download from ollama.com")
            self.ollama_status_label.setStyleSheet("color: #f38ba8;")
        elif not server:
            self.ollama_status_label.setText("Installed but server not running — launch Ollama app")
            self.ollama_status_label.setStyleSheet("color: #fab387;")
        else:
            self.ollama_status_label.setText("Running")
            self.ollama_status_label.setStyleSheet("color: #a6e3a1;")

    def _pull_model(self) -> None:
        model = self._get_selected_ollama_model()
        if not model:
            return

        self.pull_btn.setEnabled(False)
        self.pull_status.setText(f"Pulling '{model}'...")
        self.pull_status.setStyleSheet("color: #89b4fa;")

        self._pull_thread = _PullModelThread(model, self)
        self._pull_thread.finished.connect(self._on_pull_finished)
        self._pull_thread.start()

    def _on_pull_finished(self, success: bool, message: str) -> None:
        self.pull_btn.setEnabled(True)
        if success:
            self.pull_status.setText(message)
            self.pull_status.setStyleSheet("color: #a6e3a1;")
        else:
            self.pull_status.setText(message)
            self.pull_status.setStyleSheet("color: #f38ba8;")
        self._pull_thread = None

    def get_config(self) -> dict:
        """Return current config values as a dict (without saving to disk)."""
        return {
            "active_profile": self.profile_combo.currentData() or "generic",
            "mode": self.mode_combo.currentData() or "ptt",
            "ptt_key": self.ptt_key_edit.text().strip() or "caps_lock",
            "personality": self.personality_combo.currentData() or "generic",
            "model": self._get_selected_ollama_model(),
            "whisper_model": self.whisper_combo.currentData() or "small",
            "device": self.device_combo.currentData() or "cpu",
            "sample_rate": 16000,
            "vad_threshold": 0.5,
            "confidence_threshold": 0.6,
        }
