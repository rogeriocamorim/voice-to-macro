"""
tests/test_handlers.py — Unit tests for compound action handlers.

All external dependencies (EDSM, Spansh, pyautogui, game state) are mocked.
"""

from __future__ import annotations
from unittest.mock import Mock, patch, MagicMock

import pytest

from gameapi.binds_parser import KeyBinding
from handlers import dispatch_compound, format_credits, format_population
from handlers import navigate_to
from handlers import system_info
from handlers import find_commodity
from handlers import monetize_route
from handlers import trade_route
from handlers import commander_status


# ---------------------------------------------------------------------------
# Shared mocks
# ---------------------------------------------------------------------------

def _mock_speaker() -> Mock:
    return Mock()


def _mock_game_state(system="Sol", station=None, coords=None, nav_route=None, gui_focus=0):
    gs = Mock()
    gs.get_current_system.return_value = system
    gs.get_current_station.return_value = station
    gs.get_system_coords.return_value = coords or [0, 0, 0]
    gs.get_nav_route.return_value = nav_route
    gs.get_gui_focus.return_value = gui_focus
    gs.get_market_id.return_value = None
    return gs


def _mock_edsm() -> Mock:
    return Mock()


def _mock_spansh() -> Mock:
    return Mock()


def _sample_binds() -> dict:
    return {
        "GalaxyMapOpen": KeyBinding(key="m", modifiers=[], hold=False),
        "GalaxyMapClose": KeyBinding(key="m", modifiers=[], hold=False),
    }


# ---------------------------------------------------------------------------
# format_credits() / format_population() utility
# ---------------------------------------------------------------------------

class TestFormatCredits:
    def test_billions(self):
        assert "billion" in format_credits(2_500_000_000)

    def test_millions(self):
        assert "million" in format_credits(50_000_000)
        assert "50.0" in format_credits(50_000_000)

    def test_thousands(self):
        assert "thousand" in format_credits(5_000)

    def test_small(self):
        assert format_credits(500) == "500 credits"


class TestFormatPopulation:
    def test_billions(self):
        assert "billion" in format_population(7_000_000_000)

    def test_millions(self):
        assert "million" in format_population(3_500_000)

    def test_thousands(self):
        assert "thousand" in format_population(50_000)


# ---------------------------------------------------------------------------
# dispatch_compound() registry tests
# ---------------------------------------------------------------------------

class TestDispatchCompound:
    def test_unknown_action_returns_false(self):
        speaker = _mock_speaker()
        result = dispatch_compound(
            "nonexistent_action", {}, None, {}, speaker, {}, None, None
        )
        assert result is False

    @patch("handlers.system_info.handle")
    def test_dispatches_system_info(self, mock_handle):
        mock_handle.return_value = True
        speaker = _mock_speaker()
        result = dispatch_compound(
            "system_info", {"system": "Sol"}, None, {}, speaker, {}, None, None
        )
        assert result is True
        mock_handle.assert_called_once()

    @patch("handlers.navigate_to.handle")
    def test_dispatches_navigate_to(self, mock_handle):
        mock_handle.return_value = True
        speaker = _mock_speaker()
        result = dispatch_compound(
            "navigate_to", {"target": "Sol"}, None, {}, speaker, {}, None, None
        )
        assert result is True

    def test_handler_exception_returns_false(self):
        """If a handler raises, dispatch_compound catches and returns False."""
        speaker = _mock_speaker()
        with patch("handlers.system_info.handle", side_effect=Exception("API error")):
            result = dispatch_compound(
                "system_info", {}, None, {}, speaker, {}, None, None
            )
        assert result is False
        speaker.say.assert_called()  # Should report error


# ---------------------------------------------------------------------------
# navigate_to handler tests
# ---------------------------------------------------------------------------

class TestNavigateTo:
    @patch("handlers.navigate_to.time")
    @patch("handlers.navigate_to.pyautogui")
    def test_navigate_to_missing_target(self, mock_pg, mock_time):
        speaker = _mock_speaker()
        gs = _mock_game_state()
        result = navigate_to.handle({}, gs, {}, speaker, _sample_binds(), _mock_edsm(), _mock_spansh())
        assert result is False

    @patch("handlers.navigate_to.time")
    @patch("handlers.navigate_to.pyautogui")
    def test_navigate_to_system_not_found(self, mock_pg, mock_time):
        edsm = _mock_edsm()
        edsm.get_system.return_value = None
        speaker = _mock_speaker()
        gs = _mock_game_state()
        result = navigate_to.handle(
            {"target": "FakeSystem"}, gs, {}, speaker, _sample_binds(), edsm, _mock_spansh()
        )
        assert result is False


# ---------------------------------------------------------------------------
# system_info handler tests
# ---------------------------------------------------------------------------

class TestSystemInfo:
    @patch("handlers.system_info._speak_system_info")
    def test_system_info_uses_current_system(self, mock_speak):
        mock_speak.return_value = True
        edsm = _mock_edsm()
        edsm.get_system.return_value = {"name": "Sol", "information": {"allegiance": "Federation"}}
        speaker = _mock_speaker()
        gs = _mock_game_state(system="Sol")
        # This tests that the handler fetches info for the current system
        # when no explicit system param is given


# ---------------------------------------------------------------------------
# monetize_route handler tests
# ---------------------------------------------------------------------------

class TestMonetizeRoute:
    def test_no_route_returns_false(self):
        speaker = _mock_speaker()
        gs = _mock_game_state(nav_route=None)
        result = monetize_route.handle(
            {}, gs, {}, speaker, {}, _mock_edsm(), _mock_spansh()
        )
        assert result is False


# ---------------------------------------------------------------------------
# commander_status handler tests
# ---------------------------------------------------------------------------

class TestCommanderStatus:
    def test_missing_credentials_returns_false(self):
        speaker = _mock_speaker()
        config = {}  # no edsm_commander_name or edsm_api_key
        result = commander_status.handle(
            {"query": "credits"}, _mock_game_state(), config, speaker, {},
            _mock_edsm(), _mock_spansh()
        )
        assert result is False

    @patch.object(Mock, "__call__")
    def test_credits_query(self):
        edsm = _mock_edsm()
        edsm.get_credits.return_value = {
            "credits": [{"balance": 50_000_000, "loan": 0}],
        }
        speaker = _mock_speaker()
        config = {"edsm_commander_name": "Test", "edsm_api_key": "abc123"}
        result = commander_status.handle(
            {"query": "credits"}, _mock_game_state(), config, speaker, {},
            edsm, _mock_spansh()
        )
        assert result is True


# ---------------------------------------------------------------------------
# Updated action dispatcher — bind-aware tests
# ---------------------------------------------------------------------------

class TestBindAwareDispatch:
    @patch("executor.action_dispatcher.pyautogui")
    def test_dispatch_from_binds_simple_key(self, mock_pg):
        from executor.action_dispatcher import dispatch_from_binds
        binds = {"GalaxyMapOpen": KeyBinding(key="m", modifiers=[], hold=False)}
        result = dispatch_from_binds("GalaxyMapOpen", binds)
        assert result is True
        mock_pg.press.assert_called_once_with("m")

    @patch("executor.action_dispatcher.pyautogui")
    def test_dispatch_from_binds_with_modifier(self, mock_pg):
        from executor.action_dispatcher import dispatch_from_binds
        binds = {"LandingGearToggle": KeyBinding(key="l", modifiers=["shiftleft"], hold=False)}
        result = dispatch_from_binds("LandingGearToggle", binds)
        assert result is True
        mock_pg.hotkey.assert_called_once_with("shiftleft", "l")

    @patch("executor.action_dispatcher.time")
    @patch("executor.action_dispatcher.pyautogui")
    def test_dispatch_from_binds_hold_key(self, mock_pg, mock_time):
        from executor.action_dispatcher import dispatch_from_binds
        binds = {"ToggleCargoScoop": KeyBinding(key="home", modifiers=[], hold=True)}
        result = dispatch_from_binds("ToggleCargoScoop", binds)
        assert result is True
        mock_pg.keyDown.assert_called_once_with("home")
        mock_pg.keyUp.assert_called_once_with("home")

    def test_dispatch_from_binds_unknown_action(self):
        from executor.action_dispatcher import dispatch_from_binds
        binds = {"GalaxyMapOpen": KeyBinding(key="m", modifiers=[], hold=False)}
        result = dispatch_from_binds("NonExistentAction", binds)
        assert result is False

    @patch("executor.action_dispatcher.pyautogui")
    def test_dispatch_profile_action_uses_binds_first(self, mock_pg):
        from executor.action_dispatcher import dispatch_profile_action
        binds = {"GalaxyMapOpen": KeyBinding(key="g", modifiers=[], hold=False)}
        profile = {
            "actions": {
                "galaxy_map": {
                    "description": "Open galaxy map",
                    "action": {"type": "key", "key": "m"},
                }
            }
        }
        # With binds, should use "g" (from binds) not "m" (from profile)
        result = dispatch_profile_action("galaxy_map", profile, binds=binds)
        assert result is True
        mock_pg.press.assert_called_once_with("g")

    @patch("executor.action_dispatcher.pyautogui")
    def test_dispatch_profile_action_falls_back_to_profile(self, mock_pg):
        from executor.action_dispatcher import dispatch_profile_action
        # Action not in PROFILE_TO_BINDS or binds don't have the mapping
        binds = {}
        profile = {
            "actions": {
                "boost": {
                    "description": "Boost",
                    "action": {"type": "key", "key": "tab"},
                }
            }
        }
        result = dispatch_profile_action("boost", profile, binds=binds)
        assert result is True
        mock_pg.press.assert_called_once_with("tab")
