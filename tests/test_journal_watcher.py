"""
tests/test_journal_watcher.py — Unit tests for journal parsing.

Tests parse_journal_line() and read_nav_route() with mocked file I/O.
"""

from __future__ import annotations
from unittest.mock import patch, mock_open

import pytest

from gameapi.journal_watcher import parse_journal_line, read_nav_route
from gameapi.events import (
    FSDJump, Docked, Undocked, Location, NavRoute, NavRouteClear,
    LoadGame, Scan, MarketBuy, MarketSell,
)


# ---------------------------------------------------------------------------
# parse_journal_line() — valid events
# ---------------------------------------------------------------------------

class TestParseJournalLine:
    def test_parse_fsd_jump_event(self):
        line = '{"timestamp":"2024-01-15T12:30:00Z","event":"FSDJump","StarSystem":"Sol","SystemAddress":10477373803,"StarPos":[0,0,0],"JumpDist":5.5,"FuelUsed":1.2,"FuelLevel":30.0}'
        event = parse_journal_line(line)
        assert isinstance(event, FSDJump)
        assert event.StarSystem == "Sol"
        assert event.JumpDist == 5.5
        assert event.FuelUsed == 1.2
        assert event.FuelLevel == 30.0
        assert event.SystemAddress == 10477373803
        assert event.StarPos == [0, 0, 0]

    def test_parse_docked_event(self):
        line = '{"timestamp":"2024-01-15T13:00:00Z","event":"Docked","StationName":"Jameson Memorial","StationType":"Coriolis","StarSystem":"Shinrarta Dezhra","SystemAddress":3932277478106,"MarketID":128666762}'
        event = parse_journal_line(line)
        assert isinstance(event, Docked)
        assert event.StationName == "Jameson Memorial"
        assert event.StationType == "Coriolis"
        assert event.StarSystem == "Shinrarta Dezhra"
        assert event.MarketID == 128666762

    def test_parse_undocked_event(self):
        line = '{"timestamp":"2024-01-15T14:00:00Z","event":"Undocked","StationName":"Jameson Memorial","StationType":"Coriolis"}'
        event = parse_journal_line(line)
        assert isinstance(event, Undocked)
        assert event.StationName == "Jameson Memorial"

    def test_parse_location_event(self):
        line = '{"timestamp":"2024-01-15T10:00:00Z","event":"Location","StarSystem":"Sol","SystemAddress":10477373803,"StarPos":[0,0,0],"Docked":true,"StationName":"Abraham Lincoln","StationType":"Orbis","MarketID":128016896,"Body":"Earth","BodyType":"Planet"}'
        event = parse_journal_line(line)
        assert isinstance(event, Location)
        assert event.StarSystem == "Sol"
        assert event.Docked is True
        assert event.StationName == "Abraham Lincoln"

    def test_parse_nav_route_event(self):
        line = '{"timestamp":"2024-01-15T15:00:00Z","event":"NavRoute"}'
        event = parse_journal_line(line)
        assert isinstance(event, NavRoute)

    def test_parse_nav_route_clear_event(self):
        line = '{"timestamp":"2024-01-15T15:30:00Z","event":"NavRouteClear"}'
        event = parse_journal_line(line)
        assert isinstance(event, NavRouteClear)

    def test_parse_load_game_event(self):
        line = '{"timestamp":"2024-01-15T09:00:00Z","event":"LoadGame","Commander":"CMDR Test","Ship":"anaconda","ShipName":"USS Enterprise","FuelLevel":32.0,"FuelCapacity":32.0,"GameMode":"Open","Credits":500000000}'
        event = parse_journal_line(line)
        assert isinstance(event, LoadGame)
        assert event.Commander == "CMDR Test"
        assert event.Ship == "anaconda"
        assert event.Credits == 500000000

    def test_parse_scan_event(self):
        line = '{"timestamp":"2024-01-15T16:00:00Z","event":"Scan","ScanType":"Detailed","BodyName":"Earth","BodyID":3,"StarSystem":"Sol","PlanetClass":"Earth-like world","TerraformState":"","Landable":false,"WasDiscovered":true,"WasMapped":true}'
        event = parse_journal_line(line)
        assert isinstance(event, Scan)
        assert event.BodyName == "Earth"
        assert event.PlanetClass == "Earth-like world"
        assert event.Landable is False

    # --- Edge cases ---

    def test_parse_unknown_event_returns_none(self):
        line = '{"timestamp":"2024-01-15T12:30:00Z","event":"Music","MusicTrack":"NoTrack"}'
        assert parse_journal_line(line) is None

    def test_parse_invalid_json_returns_none(self):
        assert parse_journal_line("not json at all") is None

    def test_parse_empty_line_returns_none(self):
        assert parse_journal_line("") is None

    def test_parse_json_without_event_field_returns_none(self):
        assert parse_journal_line('{"timestamp":"2024-01-15T12:30:00Z"}') is None

    def test_parse_fsd_jump_with_extra_fields(self):
        """Extra fields not in the dataclass are silently ignored."""
        line = '{"timestamp":"2024-01-15T12:30:00Z","event":"FSDJump","StarSystem":"Sol","SystemAddress":123,"StarPos":[0,0,0],"JumpDist":5.5,"FuelUsed":1.2,"FuelLevel":30.0,"Taxi":false,"Multicrew":false}'
        event = parse_journal_line(line)
        assert isinstance(event, FSDJump)
        assert event.StarSystem == "Sol"


# ---------------------------------------------------------------------------
# read_nav_route() — NavRoute.json parsing
# ---------------------------------------------------------------------------

class TestReadNavRoute:
    def test_read_valid_nav_route(self):
        nav_json = '{"Route":[{"StarSystem":"Sol","SystemAddress":123,"StarPos":[0,0,0],"StarClass":"G"},{"StarSystem":"Alpha Centauri","SystemAddress":456,"StarPos":[3.03125,0.09375,3.15625],"StarClass":"K"}]}'
        with patch("builtins.open", mock_open(read_data=nav_json)):
            with patch("pathlib.Path.exists", return_value=True):
                route = read_nav_route("/fake/journal/path")
        assert route is not None
        assert len(route) == 2
        assert route[0]["StarSystem"] == "Sol"
        assert route[1]["StarSystem"] == "Alpha Centauri"
        assert route[1]["StarClass"] == "K"

    def test_read_nav_route_file_not_found(self):
        with patch("pathlib.Path.exists", return_value=False):
            route = read_nav_route("/fake/path")
        assert route is None

    def test_read_nav_route_empty_route(self):
        nav_json = '{"Route":[]}'
        with patch("builtins.open", mock_open(read_data=nav_json)):
            with patch("pathlib.Path.exists", return_value=True):
                route = read_nav_route("/fake/path")
        assert route is not None
        assert len(route) == 0
