"""
tests/test_profiles.py — Validate that all profile JSON files are well-formed
and contain the required structure.
"""

import json
from pathlib import Path

import pytest

PROFILES_DIR = Path(__file__).parent.parent / "profiles"
PROFILE_FILES = list(PROFILES_DIR.glob("*.json"))


@pytest.mark.parametrize("profile_path", PROFILE_FILES, ids=lambda p: p.stem)
class TestProfileStructure:
    def test_is_valid_json(self, profile_path):
        content = profile_path.read_text(encoding="utf-8")
        data = json.loads(content)  # raises if invalid
        assert isinstance(data, dict)

    def test_has_game_field(self, profile_path):
        data = json.loads(profile_path.read_text())
        assert "game" in data, f"Profile '{profile_path.stem}' missing 'game' field"

    def test_has_personality_field(self, profile_path):
        data = json.loads(profile_path.read_text())
        assert "personality" in data

    def test_has_actions(self, profile_path):
        data = json.loads(profile_path.read_text())
        assert "actions" in data
        assert len(data["actions"]) > 0

    def test_each_action_has_description(self, profile_path):
        data = json.loads(profile_path.read_text())
        for name, meta in data["actions"].items():
            assert "description" in meta, (
                f"Action '{name}' in '{profile_path.stem}' missing 'description'"
            )

    def test_each_action_has_action_def(self, profile_path):
        data = json.loads(profile_path.read_text())
        for name, meta in data["actions"].items():
            assert "action" in meta, (
                f"Action '{name}' in '{profile_path.stem}' missing 'action' definition"
            )

    def test_each_action_has_valid_type(self, profile_path):
        valid_types = {"key", "combo", "sequence", "hold"}
        data = json.loads(profile_path.read_text())
        for name, meta in data["actions"].items():
            action = meta.get("action", {})
            assert action.get("type") in valid_types, (
                f"Action '{name}' in '{profile_path.stem}' has invalid type: {action.get('type')}"
            )

    def test_key_actions_have_key_field(self, profile_path):
        data = json.loads(profile_path.read_text())
        for name, meta in data["actions"].items():
            action = meta.get("action", {})
            if action.get("type") == "key":
                assert "key" in action, f"Key action '{name}' missing 'key' field"

    def test_combo_actions_have_keys_field(self, profile_path):
        data = json.loads(profile_path.read_text())
        for name, meta in data["actions"].items():
            action = meta.get("action", {})
            if action.get("type") == "combo":
                assert "keys" in action, f"Combo action '{name}' missing 'keys' field"
                assert len(action["keys"]) >= 2, (
                    f"Combo action '{name}' should have at least 2 keys"
                )

    def test_sequence_actions_have_steps(self, profile_path):
        data = json.loads(profile_path.read_text())
        for name, meta in data["actions"].items():
            action = meta.get("action", {})
            if action.get("type") == "sequence":
                assert "steps" in action, f"Sequence action '{name}' missing 'steps'"
                assert len(action["steps"]) > 0
