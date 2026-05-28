"""
tests/test_action_dispatcher.py — Unit tests for the action dispatcher.

These tests mock pyautogui to verify that the correct key calls are made
for each action type, without actually sending keypresses to the OS.
"""

import time
from unittest.mock import MagicMock, call, patch

import pytest

from executor.action_dispatcher import dispatch, dispatch_profile_action


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_PROFILE = {
    "game": "Test Game",
    "actions": {
        "boost": {
            "description": "Boost engines",
            "action": {"type": "key", "key": "tab"},
        },
        "shields": {
            "description": "Boost shields",
            "action": {"type": "combo", "keys": ["shift", "1"]},
        },
        "hold_thrust": {
            "description": "Hold forward thrust",
            "action": {"type": "hold", "key": "w", "duration_ms": 500},
        },
        "fsd_jump": {
            "description": "Engage FSD jump",
            "action": {
                "type": "sequence",
                "steps": [
                    {"key": "j"},
                    {"delay_ms": 100},
                    {"key": "j"},
                ],
            },
        },
        "combo_in_seq": {
            "description": "Combo inside sequence",
            "action": {
                "type": "sequence",
                "steps": [
                    {"combo": ["ctrl", "alt", "f"]},
                    {"delay_ms": 50},
                ],
            },
        },
    },
}


# ---------------------------------------------------------------------------
# dispatch() — action type: key
# ---------------------------------------------------------------------------

class TestDispatchKey:
    @patch("executor.action_dispatcher.pyautogui")
    def test_single_key_calls_press(self, mock_pg):
        dispatch({"type": "key", "key": "j"})
        mock_pg.press.assert_called_once_with("j")

    @patch("executor.action_dispatcher.pyautogui")
    def test_key_with_hold_calls_key_down_up(self, mock_pg):
        dispatch({"type": "hold", "key": "w", "duration_ms": 100})
        mock_pg.keyDown.assert_called_once_with("w")
        mock_pg.keyUp.assert_called_once_with("w")


# ---------------------------------------------------------------------------
# dispatch() — action type: combo
# ---------------------------------------------------------------------------

class TestDispatchCombo:
    @patch("executor.action_dispatcher.pyautogui")
    def test_combo_calls_hotkey(self, mock_pg):
        dispatch({"type": "combo", "keys": ["shift", "s"]})
        mock_pg.hotkey.assert_called_once_with("shift", "s")

    @patch("executor.action_dispatcher.pyautogui")
    def test_three_key_combo(self, mock_pg):
        dispatch({"type": "combo", "keys": ["ctrl", "shift", "g"]})
        mock_pg.hotkey.assert_called_once_with("ctrl", "shift", "g")


# ---------------------------------------------------------------------------
# dispatch() — action type: sequence
# ---------------------------------------------------------------------------

class TestDispatchSequence:
    @patch("executor.action_dispatcher.time")
    @patch("executor.action_dispatcher.pyautogui")
    def test_sequence_calls_steps_in_order(self, mock_pg, mock_time):
        dispatch({
            "type": "sequence",
            "steps": [
                {"key": "j"},
                {"delay_ms": 200},
                {"key": "l"},
            ]
        })
        assert mock_pg.press.call_count == 2
        mock_pg.press.assert_any_call("j")
        mock_pg.press.assert_any_call("l")
        mock_time.sleep.assert_called_once_with(0.2)

    @patch("executor.action_dispatcher.time")
    @patch("executor.action_dispatcher.pyautogui")
    def test_sequence_with_combo_step(self, mock_pg, mock_time):
        dispatch({
            "type": "sequence",
            "steps": [
                {"combo": ["ctrl", "alt", "f"]},
                {"delay_ms": 50},
            ]
        })
        mock_pg.hotkey.assert_called_once_with("ctrl", "alt", "f")
        mock_time.sleep.assert_called_once_with(0.05)

    @patch("executor.action_dispatcher.time")
    @patch("executor.action_dispatcher.pyautogui")
    def test_sequence_with_hold_step(self, mock_pg, mock_time):
        dispatch({
            "type": "sequence",
            "steps": [
                {"key": "w", "hold_ms": 300},
            ]
        })
        mock_pg.keyDown.assert_called_once_with("w")
        mock_pg.keyUp.assert_called_once_with("w")


# ---------------------------------------------------------------------------
# dispatch() — unknown type
# ---------------------------------------------------------------------------

class TestDispatchUnknownType:
    def test_unknown_type_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown action type"):
            dispatch({"type": "teleport", "destination": "moon"})


# ---------------------------------------------------------------------------
# dispatch_profile_action()
# ---------------------------------------------------------------------------

class TestDispatchProfileAction:
    @patch("executor.action_dispatcher.pyautogui")
    def test_dispatches_known_action(self, mock_pg):
        result = dispatch_profile_action("boost", SAMPLE_PROFILE)
        assert result is True
        mock_pg.press.assert_called_once_with("tab")

    def test_returns_false_for_unknown_action(self):
        result = dispatch_profile_action("nonexistent_action", SAMPLE_PROFILE)
        assert result is False

    @patch("executor.action_dispatcher.pyautogui")
    def test_dispatches_combo_action(self, mock_pg):
        result = dispatch_profile_action("shields", SAMPLE_PROFILE)
        assert result is True
        mock_pg.hotkey.assert_called_once_with("shift", "1")

    @patch("executor.action_dispatcher.time")
    @patch("executor.action_dispatcher.pyautogui")
    def test_dispatches_sequence_action(self, mock_pg, mock_time):
        result = dispatch_profile_action("fsd_jump", SAMPLE_PROFILE)
        assert result is True
        assert mock_pg.press.call_count == 2
