"""
tests/test_game_state.py — Unit tests for the GameState class.

Tests state transitions from journal events and StatusReader updates.
"""

from __future__ import annotations
from unittest.mock import patch

import pytest

from gameapi.game_state import GameState
from gameapi.events import (
    FSDJump, Location, Docked, Undocked, NavRoute, NavRouteClear,
    LoadGame, Scan,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_game_state() -> GameState:
    """Create a GameState with a fake journal dir."""
    with patch("pathlib.Path.exists", return_value=True):
        return GameState("/fake/journal/path")


def _fsd_jump(system: str = "Sol", coords: list | None = None) -> FSDJump:
    return FSDJump(
        timestamp="2024-01-15T12:30:00Z",
        event="FSDJump",
        StarSystem=system,
        SystemAddress=123,
        StarPos=coords or [0, 0, 0],
        JumpDist=5.5,
        FuelUsed=1.2,
        FuelLevel=30.0,
    )


def _docked(station: str = "Jameson", system: str = "Shinrarta") -> Docked:
    return Docked(
        timestamp="2024-01-15T13:00:00Z",
        event="Docked",
        StationName=station,
        StationType="Coriolis",
        StarSystem=system,
        SystemAddress=456,
        MarketID=128666762,
    )


def _location(system: str = "Sol", docked: bool = False) -> Location:
    return Location(
        timestamp="2024-01-15T10:00:00Z",
        event="Location",
        StarSystem=system,
        SystemAddress=789,
        StarPos=[0, 0, 0],
        Docked=docked,
        StationName="Test Station" if docked else "",
    )


# ---------------------------------------------------------------------------
# FSDJump tests
# ---------------------------------------------------------------------------

class TestFSDJump:
    def test_fsd_jump_updates_system(self):
        gs = _make_game_state()
        gs.handle_event(_fsd_jump("Sol", [0, 0, 0]))
        assert gs.get_current_system() == "Sol"
        assert gs.get_system_coords() == [0, 0, 0]

    def test_fsd_jump_clears_station(self):
        gs = _make_game_state()
        gs.handle_event(_docked("Jameson"))
        gs.handle_event(_fsd_jump("Alpha Centauri", [3, 0, 3]))
        assert gs.get_current_station() is None
        assert gs.get_current_system() == "Alpha Centauri"

    def test_multiple_jumps_update_system(self):
        gs = _make_game_state()
        gs.handle_event(_fsd_jump("Sol"))
        gs.handle_event(_fsd_jump("Alpha Centauri", [3, 0, 3]))
        gs.handle_event(_fsd_jump("Barnard's Star", [5, 0, 5]))
        assert gs.get_current_system() == "Barnard's Star"


# ---------------------------------------------------------------------------
# Docked / Undocked tests
# ---------------------------------------------------------------------------

class TestDocking:
    def test_docked_updates_station(self):
        gs = _make_game_state()
        gs.handle_event(_docked("Jameson Memorial", "Shinrarta Dezhra"))
        assert gs.get_current_station() == "Jameson Memorial"
        assert gs.get_market_id() == 128666762

    def test_undocked_clears_station(self):
        gs = _make_game_state()
        gs.handle_event(_docked("Jameson Memorial"))
        gs.handle_event(Undocked(
            timestamp="2024-01-15T14:00:00Z",
            event="Undocked",
            StationName="Jameson Memorial",
        ))
        assert gs.get_current_station() is None

    def test_docked_updates_system_from_event(self):
        gs = _make_game_state()
        gs.handle_event(_docked("Jameson Memorial", "Shinrarta Dezhra"))
        assert gs.get_current_system() == "Shinrarta Dezhra"


# ---------------------------------------------------------------------------
# Location event tests
# ---------------------------------------------------------------------------

class TestLocation:
    def test_location_sets_system(self):
        gs = _make_game_state()
        gs.handle_event(_location("Sol", docked=False))
        assert gs.get_current_system() == "Sol"

    def test_location_docked_sets_station(self):
        gs = _make_game_state()
        gs.handle_event(_location("Sol", docked=True))
        assert gs.get_current_system() == "Sol"
        assert gs.get_current_station() == "Test Station"


# ---------------------------------------------------------------------------
# LoadGame tests
# ---------------------------------------------------------------------------

class TestLoadGame:
    def test_load_game_sets_commander(self):
        gs = _make_game_state()
        gs.handle_event(LoadGame(
            timestamp="2024-01-15T09:00:00Z",
            event="LoadGame",
            Commander="CMDR Test",
            Ship="anaconda",
            ShipName="USS Enterprise",
            Credits=500000000,
        ))
        assert gs.get_commander() == "CMDR Test"


# ---------------------------------------------------------------------------
# NavRoute tests
# ---------------------------------------------------------------------------

class TestNavRoute:
    @patch("gameapi.journal_watcher.read_nav_route")
    def test_nav_route_event_reads_file(self, mock_read):
        mock_read.return_value = [
            {"StarSystem": "Sol", "StarPos": [0, 0, 0]},
            {"StarSystem": "Alpha Centauri", "StarPos": [3, 0, 3]},
        ]
        gs = _make_game_state()
        gs.handle_event(NavRoute(
            timestamp="2024-01-15T15:00:00Z",
            event="NavRoute",
        ))
        route = gs.get_nav_route()
        assert route is not None
        assert len(route) == 2

    def test_nav_route_clear_clears_route(self):
        gs = _make_game_state()
        gs.handle_event(NavRouteClear(
            timestamp="2024-01-15T15:30:00Z",
            event="NavRouteClear",
        ))
        assert gs.get_nav_route() is None


# ---------------------------------------------------------------------------
# Status update tests
# ---------------------------------------------------------------------------

class TestStatusUpdate:
    def test_update_status_sets_flags(self):
        gs = _make_game_state()
        # Flags: docked (bit 0) + shields up (bit 3) = 1 + 8 = 9
        gs.update_status(flags=9, gui_focus=0)
        assert gs.is_docked() is True
        assert gs.is_shields_up() is True
        assert gs.is_supercruise() is False

    def test_update_status_sets_pips(self):
        gs = _make_game_state()
        gs.update_status(pips=[4, 8, 0])
        assert gs.get_pips() == [4, 8, 0]

    def test_update_status_sets_gui_focus(self):
        gs = _make_game_state()
        gs.update_status(gui_focus=6)  # Galaxy map
        assert gs.get_gui_focus() == 6

    def test_supercruise_flag(self):
        gs = _make_game_state()
        gs.update_status(flags=(1 << 4))  # bit 4 = supercruise
        assert gs.is_supercruise() is True
        assert gs.is_docked() is False

    def test_low_fuel_flag(self):
        gs = _make_game_state()
        gs.update_status(flags=(1 << 19))  # bit 19 = low fuel
        assert gs.is_low_fuel() is True


# ---------------------------------------------------------------------------
# get_status_summary() tests
# ---------------------------------------------------------------------------

class TestStatusSummary:
    def test_summary_includes_system(self):
        gs = _make_game_state()
        gs.handle_event(_fsd_jump("Sol"))
        summary = gs.get_status_summary()
        assert summary["system"] == "Sol"

    def test_summary_includes_docked(self):
        gs = _make_game_state()
        gs.handle_event(_docked("Jameson", "Shinrarta"))
        summary = gs.get_status_summary()
        assert "station" in summary
        assert summary["station"] == "Jameson"
