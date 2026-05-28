"""
tests/test_context_builder.py — Unit tests for the LLM prompt builder.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from agent.context_builder import build_prompt


SAMPLE_PROFILE = {
    "game": "Elite Dangerous",
    "actions": {
        "fsd_jump": {"description": "Engage FSD hyperspace jump"},
        "landing_gear": {"description": "Toggle landing gear"},
        "silent_running": {"description": "Toggle silent running"},
    },
}


class TestBuildPrompt:
    def test_prompt_contains_game_name(self):
        prompt = build_prompt("engage jump", SAMPLE_PROFILE)
        assert "Elite Dangerous" in prompt

    def test_prompt_contains_action_names(self):
        prompt = build_prompt("engage jump", SAMPLE_PROFILE)
        assert "fsd_jump" in prompt
        assert "landing_gear" in prompt
        assert "silent_running" in prompt

    def test_prompt_contains_transcript(self):
        prompt = build_prompt("punch it", SAMPLE_PROFILE)
        assert "punch it" in prompt

    def test_prompt_contains_action_descriptions(self):
        prompt = build_prompt("land the ship", SAMPLE_PROFILE)
        assert "Toggle landing gear" in prompt

    def test_prompt_instructs_single_word_reply(self):
        prompt = build_prompt("go dark", SAMPLE_PROFILE)
        assert "ONLY" in prompt

    def test_prompt_includes_learned_commands(self, tmp_path):
        learned = {
            "punch it": {"intent": "fsd_jump", "action": "fsd_jump", "confirmed": True, "uses": 3}
        }
        learned_file = tmp_path / "learned_commands.json"
        learned_file.write_text(json.dumps(learned))

        with patch("agent.context_builder.LEARNED_COMMANDS_PATH", learned_file):
            prompt = build_prompt("punch it", SAMPLE_PROFILE)

        assert "punch it" in prompt
        assert "fsd_jump" in prompt

    def test_prompt_excludes_unconfirmed_learned_commands(self, tmp_path):
        learned = {
            "go dark": {"intent": "silent_running", "action": "silent_running", "confirmed": False, "uses": 1}
        }
        learned_file = tmp_path / "learned_commands.json"
        learned_file.write_text(json.dumps(learned))

        with patch("agent.context_builder.LEARNED_COMMANDS_PATH", learned_file):
            prompt = build_prompt("go dark", SAMPLE_PROFILE)

        # Should NOT include unconfirmed entries as examples
        assert "Known user phrases" not in prompt or "go dark" not in prompt


# ---------------------------------------------------------------------------
# tests/test_feedback.py — Unit tests for the clarification loop.
# ---------------------------------------------------------------------------

class TestFindClosestActions:
    """Tests for agent.feedback.find_closest_actions"""

    def test_returns_top_matches(self):
        from agent.feedback import find_closest_actions
        profile = {
            "actions": {
                "fsd_jump": {"description": "Engage FSD hyperspace jump"},
                "landing_gear": {"description": "Toggle landing gear"},
                "boost": {"description": "Engine boost"},
            }
        }
        results = find_closest_actions("land the ship", profile, top_n=2)
        names = [name for name, _ in results]
        assert "landing_gear" in names

    def test_returns_empty_for_no_matches(self):
        from agent.feedback import find_closest_actions
        profile = {
            "actions": {
                "fsd_jump": {"description": "Engage FSD"},
            }
        }
        results = find_closest_actions("xxxxxxxxxxx", profile, min_score=90)
        assert results == []

    def test_top_n_limits_results(self):
        from agent.feedback import find_closest_actions
        profile = {
            "actions": {
                "boost": {"description": "Boost engines"},
                "landing_gear": {"description": "Landing gear"},
                "fsd_jump": {"description": "FSD jump"},
            }
        }
        results = find_closest_actions("boost", profile, top_n=1)
        assert len(results) == 1
