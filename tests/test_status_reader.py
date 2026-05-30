"""
tests/test_status_reader.py — Unit tests for status flag decoding.

Tests the check_flag utility and StatusReader flag parsing.
"""

from __future__ import annotations

import pytest

from gameapi.status_reader import check_flag, ShipFlags, OnFootFlags, GuiFocus


# ---------------------------------------------------------------------------
# check_flag() — bitfield utility
# ---------------------------------------------------------------------------

class TestCheckFlag:
    def test_single_bit_set(self):
        assert check_flag(1, ShipFlags.DOCKED) is True  # bit 0

    def test_single_bit_not_set(self):
        assert check_flag(0, ShipFlags.DOCKED) is False

    def test_supercruise_flag(self):
        flags = 1 << ShipFlags.SUPERCRUISE  # bit 4 = 16
        assert check_flag(flags, ShipFlags.SUPERCRUISE) is True
        assert check_flag(flags, ShipFlags.DOCKED) is False

    def test_multiple_flags_set(self):
        # docked (0) + landing gear (2) + supercruise (4)
        flags = (1 << ShipFlags.DOCKED) | (1 << ShipFlags.LANDING_GEAR) | (1 << ShipFlags.SUPERCRUISE)
        assert check_flag(flags, ShipFlags.DOCKED) is True
        assert check_flag(flags, ShipFlags.LANDING_GEAR) is True
        assert check_flag(flags, ShipFlags.SUPERCRUISE) is True
        assert check_flag(flags, ShipFlags.HARDPOINTS) is False
        assert check_flag(flags, ShipFlags.SHIELDS_UP) is False

    def test_all_bits_zero(self):
        for bit in range(32):
            assert check_flag(0, bit) is False

    def test_all_bits_set(self):
        flags = (1 << 32) - 1  # all 32 bits
        for bit in range(32):
            assert check_flag(flags, bit) is True

    def test_fsd_charging_flag(self):
        flags = 1 << ShipFlags.FSD_CHARGING  # bit 17
        assert check_flag(flags, ShipFlags.FSD_CHARGING) is True
        assert check_flag(flags, ShipFlags.FSD_COOLDOWN) is False

    def test_in_danger_flag(self):
        flags = 1 << ShipFlags.IN_DANGER  # bit 22
        assert check_flag(flags, ShipFlags.IN_DANGER) is True

    def test_being_interdicted_flag(self):
        flags = 1 << ShipFlags.BEING_INTERDICTED  # bit 23
        assert check_flag(flags, ShipFlags.BEING_INTERDICTED) is True

    def test_low_fuel_flag(self):
        flags = 1 << ShipFlags.LOW_FUEL  # bit 19
        assert check_flag(flags, ShipFlags.LOW_FUEL) is True

    def test_overheating_flag(self):
        flags = 1 << ShipFlags.OVERHEATING  # bit 20
        assert check_flag(flags, ShipFlags.OVERHEATING) is True


# ---------------------------------------------------------------------------
# ShipFlags constants
# ---------------------------------------------------------------------------

class TestShipFlagsConstants:
    def test_flag_values_unique(self):
        """Each flag should be a unique bit position."""
        values = [
            ShipFlags.DOCKED, ShipFlags.LANDED, ShipFlags.LANDING_GEAR,
            ShipFlags.SHIELDS_UP, ShipFlags.SUPERCRUISE, ShipFlags.FA_OFF,
            ShipFlags.HARDPOINTS, ShipFlags.IN_WING, ShipFlags.LIGHTS,
            ShipFlags.CARGO_SCOOP, ShipFlags.SILENT_RUNNING,
            ShipFlags.SCOOPING_FUEL, ShipFlags.FSD_MASS_LOCKED,
            ShipFlags.FSD_CHARGING, ShipFlags.FSD_COOLDOWN,
            ShipFlags.LOW_FUEL, ShipFlags.OVERHEATING,
            ShipFlags.IN_DANGER, ShipFlags.BEING_INTERDICTED,
            ShipFlags.IN_MAIN_SHIP, ShipFlags.IN_FIGHTER, ShipFlags.IN_SRV,
            ShipFlags.NIGHT_VISION, ShipFlags.FSD_JUMP,
        ]
        assert len(values) == len(set(values))

    def test_flags_are_valid_bit_positions(self):
        assert ShipFlags.DOCKED == 0
        assert ShipFlags.FSD_JUMP == 30
        assert ShipFlags.SRV_HIGH_BEAM == 31


# ---------------------------------------------------------------------------
# GuiFocus constants
# ---------------------------------------------------------------------------

class TestGuiFocusConstants:
    def test_galaxy_map_value(self):
        assert GuiFocus.GALAXY_MAP == 6

    def test_system_map_value(self):
        assert GuiFocus.SYSTEM_MAP == 7

    def test_none_value(self):
        assert GuiFocus.NONE == 0

    def test_station_services_value(self):
        assert GuiFocus.STATION_SERVICES == 5


# ---------------------------------------------------------------------------
# OnFootFlags constants
# ---------------------------------------------------------------------------

class TestOnFootFlagsConstants:
    def test_on_foot_bit(self):
        assert OnFootFlags.ON_FOOT == 0

    def test_in_taxi_bit(self):
        assert OnFootFlags.IN_TAXI == 1

    def test_flags2_decoding(self):
        """Flags2 uses the same bitfield mechanism."""
        flags2 = 1 << OnFootFlags.ON_FOOT  # bit 0
        assert check_flag(flags2, OnFootFlags.ON_FOOT) is True
        assert check_flag(flags2, OnFootFlags.IN_TAXI) is False
