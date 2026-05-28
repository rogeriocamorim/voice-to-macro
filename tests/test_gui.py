"""
tests/test_gui.py — Tests for the Voice-to-Macro GUI.

Covers: layout structure, tab interactions, macro editor CRUD, log tab,
setup tab config round-trip, engine signals, and edge cases.

Uses PyQt6 QApplication + widget testing (no display needed on CI if
QT_QPA_PLATFORM=offscreen is set).
"""

import copy
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# Force offscreen rendering for headless CI
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox, QDialogButtonBox

# Must create QApplication before importing any widget modules
_app = QApplication.instance() or QApplication(sys.argv)

from gui.log_tab import LogTab, _escape
from gui.macro_tab import MacroDialog, MacroTab
from gui.setup_tab import SetupTab
from gui.main_window import MainWindow


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with profiles and config."""
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()

    profile_data = {
        "game": "Test Game",
        "personality": "test",
        "actions": {
            "jump": {
                "description": "Jump up",
                "action": {"type": "key", "key": "space"},
            },
            "crouch": {
                "description": "Crouch down",
                "action": {"type": "combo", "keys": ["ctrl", "c"]},
            },
        },
    }
    (profiles_dir / "test_game.json").write_text(json.dumps(profile_data), encoding="utf-8")
    (profiles_dir / "empty_profile.json").write_text(
        json.dumps({"game": "Empty", "personality": "none", "actions": {}}),
        encoding="utf-8",
    )

    config = {
        "active_profile": "test_game",
        "mode": "ptt",
        "ptt_key": "t",
        "personality": "game_themed",
        "model": "qwen2.5:3b",
        "whisper_model": "small",
        "device": "cpu",
        "sample_rate": 16000,
        "vad_threshold": 0.5,
        "confidence_threshold": 0.6,
    }
    (tmp_path / "config.yaml").write_text(yaml.dump(config), encoding="utf-8")

    return tmp_path, profiles_dir, config, profile_data


# ---------------------------------------------------------------------------
# LogTab tests
# ---------------------------------------------------------------------------

class TestLogTab:
    def test_initial_state(self):
        tab = LogTab()
        assert tab.log_view.toPlainText() == ""
        assert tab.status_label.text() == "STOPPED"

    def test_append_log(self):
        tab = LogTab()
        tab.append_log("[01/01/2026 12:00:00 AM] Hello world")
        assert "Hello world" in tab.log_view.toPlainText()

    def test_append_multiple_lines(self):
        tab = LogTab()
        for i in range(50):
            tab.append_log(f"Line {i}")
        text = tab.log_view.toPlainText()
        assert "Line 0" in text
        assert "Line 49" in text

    def test_clear(self):
        tab = LogTab()
        tab.append_log("something")
        tab._clear()
        assert tab.log_view.toPlainText() == ""

    def test_set_status_idle(self):
        tab = LogTab()
        tab.set_status("IDLE")
        assert tab.status_label.text() == "IDLE"

    def test_set_status_recording(self):
        tab = LogTab()
        tab.set_status("RECORDING")
        assert tab.status_label.text() == "RECORDING"

    def test_set_status_exec(self):
        tab = LogTab()
        tab.set_status("EXEC: boost")
        assert tab.status_label.text() == "EXEC: boost"

    def test_set_recording_indicator(self):
        tab = LogTab()
        tab.set_recording(True)
        # Just verify it doesn't crash; style check is visual

    def test_copy_all(self):
        tab = LogTab()
        tab.append_log("copy me")
        tab._copy_all()
        clipboard = QApplication.clipboard()
        assert "copy me" in clipboard.text()


class TestEscapeHtml:
    def test_escapes_angle_brackets(self):
        assert "&lt;" in _escape("<script>")
        assert "&gt;" in _escape("</script>")

    def test_escapes_ampersand(self):
        assert "&amp;" in _escape("a & b")

    def test_escapes_quotes(self):
        assert "&#39;" in _escape("it's")

    def test_plain_text_unchanged(self):
        assert _escape("hello") == "hello"


# ---------------------------------------------------------------------------
# MacroDialog tests
# ---------------------------------------------------------------------------

class TestMacroDialog:
    def test_empty_dialog_defaults(self):
        dlg = MacroDialog()
        assert dlg.name_edit.text() == ""
        assert dlg.desc_edit.text() == ""
        assert dlg.type_combo.currentText() == "key"

    def test_prefilled_key_action(self):
        data = {
            "description": "Jump up",
            "action": {"type": "key", "key": "space"},
        }
        dlg = MacroDialog(action_name="jump", action_data=data)
        assert dlg.name_edit.text() == "jump"
        assert dlg.desc_edit.text() == "Jump up"
        assert dlg.key_edit.text() == "space"

    def test_prefilled_combo_action(self):
        data = {
            "description": "Combo move",
            "action": {"type": "combo", "keys": ["ctrl", "shift", "s"]},
        }
        dlg = MacroDialog(action_name="save", action_data=data)
        assert dlg.type_combo.currentText() == "combo"
        assert "ctrl" in dlg.keys_edit.text()

    def test_prefilled_hold_action(self):
        data = {
            "description": "Hold fire",
            "action": {"type": "hold", "key": "space", "duration_ms": 1000},
        }
        dlg = MacroDialog(action_name="fire", action_data=data)
        assert dlg.type_combo.currentText() == "hold"
        assert dlg.duration_spin.value() == 1000

    def test_prefilled_sequence_action(self):
        steps = [{"key": "tab"}, {"delay_ms": 100}, {"key": "x"}]
        data = {
            "description": "Evasive",
            "action": {"type": "sequence", "steps": steps},
        }
        dlg = MacroDialog(action_name="evade", action_data=data)
        assert dlg.type_combo.currentText() == "sequence"
        assert "tab" in dlg.sequence_edit.text()

    def test_type_change_toggles_fields(self):
        dlg = MacroDialog()
        dlg._on_type_changed("key")
        assert not dlg.key_edit.isHidden()
        assert dlg.keys_edit.isHidden()

        dlg._on_type_changed("combo")
        assert dlg.key_edit.isHidden()
        assert not dlg.keys_edit.isHidden()

        dlg._on_type_changed("hold")
        assert not dlg.key_edit.isHidden()
        assert not dlg.duration_spin.isHidden()

        dlg._on_type_changed("sequence")
        assert not dlg.sequence_edit.isHidden()
        assert dlg.key_edit.isHidden()

    def test_get_result_key(self):
        dlg = MacroDialog()
        dlg.name_edit.setText("test_action")
        dlg.desc_edit.setText("Test description")
        dlg.type_combo.setCurrentText("key")
        dlg.key_edit.setText("f")
        name, data = dlg.get_result()
        assert name == "test_action"
        assert data["description"] == "Test description"
        assert data["action"]["type"] == "key"
        assert data["action"]["key"] == "f"

    def test_get_result_combo(self):
        dlg = MacroDialog()
        dlg.name_edit.setText("combo_test")
        dlg.desc_edit.setText("A combo")
        dlg.type_combo.setCurrentText("combo")
        dlg.keys_edit.setText("ctrl, shift, s")
        name, data = dlg.get_result()
        assert data["action"]["keys"] == ["ctrl", "shift", "s"]

    def test_get_result_hold(self):
        dlg = MacroDialog()
        dlg.name_edit.setText("hold_test")
        dlg.desc_edit.setText("A hold")
        dlg.type_combo.setCurrentText("hold")
        dlg.key_edit.setText("w")
        dlg.duration_spin.setValue(2000)
        name, data = dlg.get_result()
        assert data["action"]["duration_ms"] == 2000

    def test_get_result_sequence(self):
        dlg = MacroDialog()
        dlg.name_edit.setText("seq_test")
        dlg.desc_edit.setText("A seq")
        dlg.type_combo.setCurrentText("sequence")
        dlg.sequence_edit.setText('[{"key":"a"},{"delay_ms":50}]')
        name, data = dlg.get_result()
        assert len(data["action"]["steps"]) == 2

    def test_name_sanitization(self):
        """Names with spaces/dashes should be lowercased + underscored."""
        dlg = MacroDialog()
        dlg.name_edit.setText("My Cool-Action")
        dlg.desc_edit.setText("test")
        dlg.type_combo.setCurrentText("key")
        dlg.key_edit.setText("x")
        dlg._validate_and_accept()
        assert dlg.name_edit.text() == "my_cool_action"


# ---------------------------------------------------------------------------
# MacroTab tests (with tmp profile files)
# ---------------------------------------------------------------------------

class TestMacroTab:
    def test_loads_profiles(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.macro_tab.PROFILES_DIR", profiles_dir):
            tab = MacroTab()
            assert tab.profile_combo.count() >= 2  # test_game + empty_profile

    def test_table_populated(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.macro_tab.PROFILES_DIR", profiles_dir):
            tab = MacroTab()
            # Find and select test_game
            idx = tab.profile_combo.findData("test_game")
            tab.profile_combo.setCurrentIndex(idx)
            assert tab.table.rowCount() == 2  # jump + crouch

    def test_table_columns(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.macro_tab.PROFILES_DIR", profiles_dir):
            tab = MacroTab()
            assert tab.table.columnCount() == 4
            headers = [tab.table.horizontalHeaderItem(i).text() for i in range(4)]
            assert "Action Name" in headers
            assert "Description" in headers

    def test_empty_profile_shows_no_rows(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.macro_tab.PROFILES_DIR", profiles_dir):
            tab = MacroTab()
            idx = tab.profile_combo.findData("empty_profile")
            tab.profile_combo.setCurrentIndex(idx)
            assert tab.table.rowCount() == 0

    def test_delete_action(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.macro_tab.PROFILES_DIR", profiles_dir):
            tab = MacroTab()
            idx = tab.profile_combo.findData("test_game")
            tab.profile_combo.setCurrentIndex(idx)
            initial_count = tab.table.rowCount()

            # Select first row
            tab.table.selectRow(0)
            # Mock the confirmation dialog
            with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
                tab._delete_selected()

            assert tab.table.rowCount() == initial_count - 1

            # Verify file was updated
            data = json.loads((profiles_dir / "test_game.json").read_text())
            assert len(data["actions"]) == initial_count - 1

    def test_duplicate_action(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.macro_tab.PROFILES_DIR", profiles_dir):
            tab = MacroTab()
            idx = tab.profile_combo.findData("test_game")
            tab.profile_combo.setCurrentIndex(idx)

            tab.table.selectRow(0)
            tab._duplicate_selected()

            assert tab.table.rowCount() == 3  # original 2 + 1 copy

    def test_duplicate_name_collision(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.macro_tab.PROFILES_DIR", profiles_dir):
            tab = MacroTab()
            idx = tab.profile_combo.findData("test_game")
            tab.profile_combo.setCurrentIndex(idx)

            # Duplicate twice — should get _copy and _copy2
            tab.table.selectRow(0)
            tab._duplicate_selected()
            tab.table.selectRow(0)
            tab._duplicate_selected()
            assert tab.table.rowCount() == 4

    def test_no_selection_shows_message(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.macro_tab.PROFILES_DIR", profiles_dir):
            tab = MacroTab()
            idx = tab.profile_combo.findData("test_game")
            tab.profile_combo.setCurrentIndex(idx)
            tab.table.clearSelection()
            with patch.object(QMessageBox, "information") as mock_msg:
                result = tab._get_selected_action_name()
                assert result is None
                mock_msg.assert_called_once()

    def test_set_profile_programmatic(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.macro_tab.PROFILES_DIR", profiles_dir):
            tab = MacroTab()
            tab.set_profile("empty_profile")
            assert tab.profile_combo.currentData() == "empty_profile"
            assert tab.table.rowCount() == 0


# ---------------------------------------------------------------------------
# SetupTab tests
# ---------------------------------------------------------------------------

class TestSetupTab:
    def test_initial_widgets_exist(self):
        with patch("gui.setup_tab.CONFIG_PATH", Path("/nonexistent/config.yaml")):
            with patch("gui.setup_tab.PROFILES_DIR", Path("/nonexistent/profiles")):
                tab = SetupTab()
                assert tab.profile_combo is not None
                assert tab.mode_combo is not None
                assert tab.ptt_key_edit is not None
                assert tab.ollama_combo is not None
                assert tab.whisper_combo is not None
                assert tab.device_combo is not None

    def test_loads_config(self, tmp_project):
        tmp_path, profiles_dir, config, _ = tmp_project
        with patch("gui.setup_tab.CONFIG_PATH", tmp_path / "config.yaml"):
            with patch("gui.setup_tab.PROFILES_DIR", profiles_dir):
                tab = SetupTab()
                assert tab.ptt_key_edit.text() == "t"
                assert tab.mode_combo.currentData() == "ptt"

    def test_save_config(self, tmp_project):
        tmp_path, profiles_dir, config, _ = tmp_project
        config_path = tmp_path / "config.yaml"
        with patch("gui.setup_tab.CONFIG_PATH", config_path):
            with patch("gui.setup_tab.PROFILES_DIR", profiles_dir):
                tab = SetupTab()
                tab.ptt_key_edit.setText("f5")
                with patch.object(QMessageBox, "information"):
                    tab._save_config()

                saved = yaml.safe_load(config_path.read_text())
                assert saved["ptt_key"] == "f5"

    def test_save_empty_ptt_key_rejected(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.setup_tab.CONFIG_PATH", tmp_path / "config.yaml"):
            with patch("gui.setup_tab.PROFILES_DIR", profiles_dir):
                tab = SetupTab()
                tab.ptt_key_edit.setText("")
                with patch.object(QMessageBox, "warning") as mock_warn:
                    tab._save_config()
                    mock_warn.assert_called_once()

    def test_get_config_dict(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.setup_tab.CONFIG_PATH", tmp_path / "config.yaml"):
            with patch("gui.setup_tab.PROFILES_DIR", profiles_dir):
                tab = SetupTab()
                cfg = tab.get_config()
                assert isinstance(cfg, dict)
                assert "model" in cfg
                assert "device" in cfg
                assert "ptt_key" in cfg

    def test_ollama_model_selection(self, tmp_project):
        """Selecting a model from dropdown returns the correct tag."""
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.setup_tab.CONFIG_PATH", tmp_path / "config.yaml"):
            with patch("gui.setup_tab.PROFILES_DIR", profiles_dir):
                tab = SetupTab()
                idx = tab.ollama_combo.findData("mistral")
                tab.ollama_combo.setCurrentIndex(idx)
                model = tab._get_selected_ollama_model()
                assert model == "mistral"

    def test_check_ollama_no_binary(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.setup_tab.CONFIG_PATH", tmp_path / "config.yaml"):
            with patch("gui.setup_tab.PROFILES_DIR", profiles_dir):
                tab = SetupTab()
                with patch("gui.setup_tab.shutil.which", return_value=None):
                    tab._check_ollama()
                    assert "not installed" in tab.ollama_status_label.text().lower() or \
                           "Not installed" in tab.ollama_status_label.text()

    def test_check_ollama_not_running(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.setup_tab.CONFIG_PATH", tmp_path / "config.yaml"):
            with patch("gui.setup_tab.PROFILES_DIR", profiles_dir):
                tab = SetupTab()
                with patch("gui.setup_tab.shutil.which", return_value="/usr/bin/ollama"):
                    with patch("gui.setup_tab.urllib.request.urlopen", side_effect=Exception("refused")):
                        tab._check_ollama()
                        assert "not running" in tab.ollama_status_label.text().lower()

    def test_ollama_model_list_has_known_entries(self):
        """Verify the model dropdown has the recommended models."""
        with patch("gui.setup_tab.CONFIG_PATH", Path("/nonexistent")):
            with patch("gui.setup_tab.PROFILES_DIR", Path("/nonexistent")):
                tab = SetupTab()
                all_data = [tab.ollama_combo.itemData(i) for i in range(tab.ollama_combo.count())]
                assert "qwen2.5:3b" in all_data
                assert "mistral" in all_data
                assert "phi3:mini" in all_data


# ---------------------------------------------------------------------------
# MainWindow tests
# ---------------------------------------------------------------------------

class TestMainWindow:
    def test_window_creates(self):
        with patch("gui.main_window.CONFIG_PATH", Path("/nonexistent")):
            with patch("gui.main_window.PROFILES_DIR", Path("/nonexistent")):
                window = MainWindow()
                assert window.windowTitle() == "Voice-to-Macro"
                assert window.tabs.count() == 3

    def test_tabs_labels(self):
        with patch("gui.main_window.CONFIG_PATH", Path("/nonexistent")):
            with patch("gui.main_window.PROFILES_DIR", Path("/nonexistent")):
                window = MainWindow()
                labels = [window.tabs.tabText(i) for i in range(window.tabs.count())]
                assert "Setup" in labels
                assert "Macros" in labels
                assert "Live Log" in labels

    def test_start_stop_buttons_initial_state(self):
        with patch("gui.main_window.CONFIG_PATH", Path("/nonexistent")):
            with patch("gui.main_window.PROFILES_DIR", Path("/nonexistent")):
                window = MainWindow()
                assert window.start_btn.isEnabled()
                assert not window.stop_btn.isEnabled()

    def test_start_no_config_shows_warning(self, tmp_path):
        config_path = tmp_path / "config.yaml"  # does not exist
        with patch("gui.main_window.CONFIG_PATH", config_path):
            with patch("gui.main_window.PROFILES_DIR", tmp_path / "profiles"):
                window = MainWindow()
                with patch.object(QMessageBox, "warning") as mock_warn:
                    window._start_engine()
                    mock_warn.assert_called_once()
                # Buttons unchanged
                assert window.start_btn.isEnabled()
                assert not window.stop_btn.isEnabled()

    def test_start_missing_profile_shows_warning(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        # Config references "test_game" but delete the profile
        (profiles_dir / "test_game.json").unlink()
        with patch("gui.main_window.CONFIG_PATH", tmp_path / "config.yaml"):
            with patch("gui.main_window.PROFILES_DIR", profiles_dir):
                window = MainWindow()
                with patch.object(QMessageBox, "warning") as mock_warn:
                    window._start_engine()
                    mock_warn.assert_called_once()

    def test_engine_finished_resets_buttons(self):
        with patch("gui.main_window.CONFIG_PATH", Path("/nonexistent")):
            with patch("gui.main_window.PROFILES_DIR", Path("/nonexistent")):
                window = MainWindow()
                # Simulate engine started
                window.start_btn.setEnabled(False)
                window.stop_btn.setEnabled(True)
                # Simulate engine finished
                window._on_engine_finished()
                assert window.start_btn.isEnabled()
                assert not window.stop_btn.isEnabled()
                assert window.engine_status.text() == "STOPPED"

    def test_status_updates_propagate(self):
        with patch("gui.main_window.CONFIG_PATH", Path("/nonexistent")):
            with patch("gui.main_window.PROFILES_DIR", Path("/nonexistent")):
                window = MainWindow()
                window._on_status("TRANSCRIBING")
                assert window.engine_status.text() == "TRANSCRIBING"
                assert window.log_tab.status_label.text() == "TRANSCRIBING"

    def test_close_event_stops_engine(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.main_window.CONFIG_PATH", tmp_path / "config.yaml"):
            with patch("gui.main_window.PROFILES_DIR", profiles_dir):
                window = MainWindow()
                mock_engine = MagicMock()
                mock_engine.isRunning.return_value = True
                window._engine = mock_engine

                from PyQt6.QtGui import QCloseEvent
                event = QCloseEvent()
                window.closeEvent(event)
                mock_engine.stop.assert_called_once()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_log_tab_massive_log(self):
        """Log tab should handle thousands of lines without crashing."""
        tab = LogTab()
        for i in range(5000):
            tab.append_log(f"[01/01/2026 12:00:00 AM] Log entry {i}")
        assert "Log entry 4999" in tab.log_view.toPlainText()

    def test_log_tab_special_characters(self):
        """HTML special chars in log messages should not break rendering."""
        tab = LogTab()
        tab.append_log("<script>alert('xss')</script>")
        text = tab.log_view.toPlainText()
        assert "<script>" not in tab.log_view.toHtml().replace("&lt;", "").replace("&gt;", "")

    def test_macro_dialog_empty_sequence_json(self):
        """Empty sequence JSON should not crash get_result."""
        dlg = MacroDialog()
        dlg.name_edit.setText("test")
        dlg.desc_edit.setText("test")
        dlg.type_combo.setCurrentText("sequence")
        dlg.sequence_edit.setText("")
        # _validate_and_accept should reject this
        with patch.object(QMessageBox, "warning"):
            dlg._validate_and_accept()
            # Dialog should NOT have accepted
            assert dlg.result() != MacroDialog.DialogCode.Accepted

    def test_macro_dialog_invalid_json(self):
        dlg = MacroDialog()
        dlg.name_edit.setText("test")
        dlg.desc_edit.setText("test")
        dlg.type_combo.setCurrentText("sequence")
        dlg.sequence_edit.setText("not json")
        with patch.object(QMessageBox, "warning"):
            dlg._validate_and_accept()
            assert dlg.result() != MacroDialog.DialogCode.Accepted

    def test_macro_dialog_combo_single_key_rejected(self):
        """Combo with only 1 key should be rejected."""
        dlg = MacroDialog()
        dlg.name_edit.setText("test")
        dlg.desc_edit.setText("test")
        dlg.type_combo.setCurrentText("combo")
        dlg.keys_edit.setText("ctrl")
        with patch.object(QMessageBox, "warning"):
            dlg._validate_and_accept()
            assert dlg.result() != MacroDialog.DialogCode.Accepted

    def test_corrupt_profile_json(self, tmp_path):
        """MacroTab should handle corrupt JSON gracefully."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "corrupt.json").write_text("{{{{not json", encoding="utf-8")
        with patch("gui.macro_tab.PROFILES_DIR", profiles_dir):
            tab = MacroTab()
            # Should still create the tab without crashing
            assert tab.profile_combo.count() >= 0

    def test_missing_config_file(self):
        """SetupTab should not crash when config.yaml doesn't exist."""
        with patch("gui.setup_tab.CONFIG_PATH", Path("/nonexistent/config.yaml")):
            with patch("gui.setup_tab.PROFILES_DIR", Path("/nonexistent")):
                tab = SetupTab()
                # Should use defaults
                assert tab.ptt_key_edit.text() == "" or tab.ptt_key_edit.text() == "caps_lock"

    def test_config_saved_signal_emitted(self, tmp_project):
        tmp_path, profiles_dir, _, _ = tmp_project
        with patch("gui.setup_tab.CONFIG_PATH", tmp_path / "config.yaml"):
            with patch("gui.setup_tab.PROFILES_DIR", profiles_dir):
                tab = SetupTab()
                signal_received = []
                tab.config_saved.connect(lambda cfg: signal_received.append(cfg))
                with patch.object(QMessageBox, "information"):
                    tab._save_config()
                assert len(signal_received) == 1
                assert isinstance(signal_received[0], dict)

    def test_profile_with_no_actions_key(self, tmp_path):
        """Profile JSON missing 'actions' key entirely."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        (profiles_dir / "minimal.json").write_text(
            json.dumps({"game": "Minimal", "personality": "test"}),
            encoding="utf-8",
        )
        with patch("gui.macro_tab.PROFILES_DIR", profiles_dir):
            tab = MacroTab()
            idx = tab.profile_combo.findData("minimal")
            if idx >= 0:
                tab.profile_combo.setCurrentIndex(idx)
                assert tab.table.rowCount() == 0
