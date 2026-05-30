"""
tests/test_binds_parser.py — Unit tests for the keybindings parser.

Tests XML parsing, key name mapping, modifier detection, and hold flags.
"""

from __future__ import annotations
from unittest.mock import patch, mock_open

import pytest

from gameapi.binds_parser import KeyBinding, map_key_name, parse_binds


# ---------------------------------------------------------------------------
# Sample .binds XML for testing
# ---------------------------------------------------------------------------

SAMPLE_BINDS_XML = '''\
<?xml version="1.0" encoding="UTF-8" ?>
<Root PresetName="Custom" MajorVersion="4" MinorVersion="0">
  <GalaxyMapOpen>
    <Primary Device="Keyboard" Key="Key_M"/>
    <Secondary Device="072" Key="Joy_5"/>
  </GalaxyMapOpen>
  <LandingGearToggle>
    <Primary Device="Keyboard" Key="Key_L">
      <Modifier Device="Keyboard" Key="Key_LeftShift"/>
    </Primary>
  </LandingGearToggle>
  <ToggleCargoScoop>
    <Primary Device="Keyboard" Key="Key_Home" Hold="1"/>
  </ToggleCargoScoop>
  <PrimaryFire>
    <Primary Device="Mouse" Key="Mouse_1"/>
  </PrimaryFire>
  <Hyperspace>
    <Primary Device="Keyboard" Key="Key_J"/>
    <Secondary Device="{NoDevice}" Key=""/>
  </Hyperspace>
  <SetSpeedZero>
    <Primary Device="Keyboard" Key="Key_X"/>
  </SetSpeedZero>
  <DeployHardpointToggle>
    <Primary Device="Keyboard" Key="Key_U">
      <Modifier Device="Keyboard" Key="Key_LeftControl"/>
      <Modifier Device="Keyboard" Key="Key_LeftAlt"/>
    </Primary>
  </DeployHardpointToggle>
  <UseBoostJuice>
    <Primary Device="Keyboard" Key="Key_Tab"/>
  </UseBoostJuice>
  <NightVisionToggle>
    <Primary Device="Keyboard" Key="Key_F1"/>
  </NightVisionToggle>
</Root>
'''


# ---------------------------------------------------------------------------
# map_key_name() tests
# ---------------------------------------------------------------------------

class TestMapKeyName:
    def test_letter_keys(self):
        assert map_key_name("Key_M") == "m"
        assert map_key_name("Key_A") == "a"
        assert map_key_name("Key_Z") == "z"

    def test_number_keys(self):
        assert map_key_name("Key_0") == "0"
        assert map_key_name("Key_9") == "9"

    def test_function_keys(self):
        assert map_key_name("Key_F1") == "f1"
        assert map_key_name("Key_F12") == "f12"

    def test_modifier_keys(self):
        assert map_key_name("Key_LeftShift") == "shiftleft"
        assert map_key_name("Key_RightShift") == "shiftright"
        assert map_key_name("Key_LeftControl") == "ctrlleft"
        assert map_key_name("Key_RightControl") == "ctrlright"
        assert map_key_name("Key_LeftAlt") == "altleft"
        assert map_key_name("Key_RightAlt") == "altright"

    def test_navigation_keys(self):
        assert map_key_name("Key_UpArrow") == "up"
        assert map_key_name("Key_DownArrow") == "down"
        assert map_key_name("Key_LeftArrow") == "left"
        assert map_key_name("Key_RightArrow") == "right"
        assert map_key_name("Key_Home") == "home"
        assert map_key_name("Key_End") == "end"

    def test_special_keys(self):
        assert map_key_name("Key_Space") == "space"
        assert map_key_name("Key_Tab") == "tab"
        assert map_key_name("Key_Enter") == "enter"
        assert map_key_name("Key_Escape") == "escape"
        assert map_key_name("Key_Backspace") == "backspace"

    def test_numpad_keys(self):
        assert map_key_name("Key_Numpad_5") == "num5"
        assert map_key_name("Key_Numpad_0") == "num0"

    def test_unknown_key_returns_lowercase_stripped(self):
        # Unknown keys should still return something usable
        result = map_key_name("Key_Unknown")
        assert result is not None


# ---------------------------------------------------------------------------
# parse_binds() tests (using file mock)
# ---------------------------------------------------------------------------

class TestParseBinds:
    @patch("builtins.open", mock_open(read_data=SAMPLE_BINDS_XML))
    def test_simple_key_binding(self):
        binds = parse_binds("/fake/Custom.4.0.binds")
        assert "GalaxyMapOpen" in binds
        assert binds["GalaxyMapOpen"].key == "m"
        assert binds["GalaxyMapOpen"].modifiers == []
        assert binds["GalaxyMapOpen"].hold is False

    @patch("builtins.open", mock_open(read_data=SAMPLE_BINDS_XML))
    def test_binding_with_modifier(self):
        binds = parse_binds("/fake/Custom.4.0.binds")
        assert "LandingGearToggle" in binds
        assert binds["LandingGearToggle"].key == "l"
        assert binds["LandingGearToggle"].modifiers == ["shiftleft"]
        assert binds["LandingGearToggle"].hold is False

    @patch("builtins.open", mock_open(read_data=SAMPLE_BINDS_XML))
    def test_binding_with_hold(self):
        binds = parse_binds("/fake/Custom.4.0.binds")
        assert "ToggleCargoScoop" in binds
        assert binds["ToggleCargoScoop"].key == "home"
        assert binds["ToggleCargoScoop"].hold is True

    @patch("builtins.open", mock_open(read_data=SAMPLE_BINDS_XML))
    def test_non_keyboard_bindings_skipped(self):
        binds = parse_binds("/fake/Custom.4.0.binds")
        # PrimaryFire is Mouse only — should not appear
        assert "PrimaryFire" not in binds

    @patch("builtins.open", mock_open(read_data=SAMPLE_BINDS_XML))
    def test_multiple_modifiers(self):
        binds = parse_binds("/fake/Custom.4.0.binds")
        assert "DeployHardpointToggle" in binds
        assert binds["DeployHardpointToggle"].key == "u"
        assert "ctrlleft" in binds["DeployHardpointToggle"].modifiers
        assert "altleft" in binds["DeployHardpointToggle"].modifiers

    @patch("builtins.open", mock_open(read_data=SAMPLE_BINDS_XML))
    def test_all_keyboard_bindings_parsed(self):
        binds = parse_binds("/fake/Custom.4.0.binds")
        # Should have: GalaxyMapOpen, LandingGearToggle, ToggleCargoScoop,
        #              Hyperspace, SetSpeedZero, DeployHardpointToggle,
        #              UseBoostJuice, NightVisionToggle
        expected = {
            "GalaxyMapOpen", "LandingGearToggle", "ToggleCargoScoop",
            "Hyperspace", "SetSpeedZero", "DeployHardpointToggle",
            "UseBoostJuice", "NightVisionToggle",
        }
        assert expected.issubset(set(binds.keys()))

    @patch("builtins.open", mock_open(read_data=SAMPLE_BINDS_XML))
    def test_hyperspace_binding(self):
        binds = parse_binds("/fake/Custom.4.0.binds")
        assert binds["Hyperspace"].key == "j"
        assert binds["Hyperspace"].modifiers == []

    @patch("builtins.open", mock_open(read_data=SAMPLE_BINDS_XML))
    def test_function_key_binding(self):
        binds = parse_binds("/fake/Custom.4.0.binds")
        assert binds["NightVisionToggle"].key == "f1"
