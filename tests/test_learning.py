"""
tests/test_learning.py — Unit tests for the command store (learning module).
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

import learning.command_store as store


# ---------------------------------------------------------------------------
# Helpers — redirect store path to a temp file for each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def temp_store(tmp_path):
    """Redirect STORE_PATH to a temp file so tests don't touch the real file."""
    temp_file = tmp_path / "learned_commands.json"
    with patch.object(store, "STORE_PATH", temp_file):
        yield temp_file


# ---------------------------------------------------------------------------
# save_mapping + lookup
# ---------------------------------------------------------------------------

class TestSaveAndLookup:
    def test_save_confirmed_mapping(self):
        store.save_mapping("punch it", "fsd_jump", "fsd_jump", confirmed=True)
        result = store.lookup("punch it")
        assert result is not None
        assert result["intent"] == "fsd_jump"
        assert result["confirmed"] is True

    def test_lookup_returns_none_for_unconfirmed(self):
        store.save_mapping("go dark", "silent_running", "silent_running", confirmed=False)
        result = store.lookup("go dark")
        assert result is None

    def test_lookup_returns_none_for_missing(self):
        result = store.lookup("totally unknown phrase")
        assert result is None

    def test_save_normalises_transcript_to_lowercase(self):
        store.save_mapping("BOOST NOW", "boost", "boost", confirmed=True)
        result = store.lookup("boost now")
        assert result is not None

    def test_save_strips_whitespace(self):
        store.save_mapping("  boost  ", "boost", "boost", confirmed=True)
        result = store.lookup("boost")
        assert result is not None


# ---------------------------------------------------------------------------
# increment_uses + auto-confirm
# ---------------------------------------------------------------------------

class TestIncrementUses:
    def test_increment_increases_use_count(self):
        store.save_mapping("engage", "fsd_jump", "fsd_jump", confirmed=False)
        store.increment_uses("engage")
        data = store.get_all()
        assert data["engage"]["uses"] == 2  # 1 from save + 1 from increment

    def test_auto_confirm_after_three_uses(self):
        store.save_mapping("engage", "fsd_jump", "fsd_jump", confirmed=False)
        store.increment_uses("engage")
        store.increment_uses("engage")
        # 3rd increment should trigger auto-confirm
        store.increment_uses("engage")
        data = store.get_all()
        assert data["engage"]["confirmed"] is True


# ---------------------------------------------------------------------------
# confirm + reject
# ---------------------------------------------------------------------------

class TestConfirmReject:
    def test_confirm_marks_mapping_confirmed(self):
        store.save_mapping("go dark", "silent_running", "silent_running", confirmed=False)
        result = store.confirm("go dark")
        assert result is True
        assert store.lookup("go dark") is not None

    def test_confirm_returns_false_for_missing(self):
        result = store.confirm("does not exist")
        assert result is False

    def test_reject_removes_mapping(self):
        store.save_mapping("mystery phrase", "boost", "boost", confirmed=False)
        result = store.reject("mystery phrase")
        assert result is True
        assert store.lookup("mystery phrase") is None

    def test_reject_returns_false_for_missing(self):
        result = store.reject("ghost command")
        assert result is False


# ---------------------------------------------------------------------------
# get_pending
# ---------------------------------------------------------------------------

class TestGetPending:
    def test_returns_only_unconfirmed(self):
        store.save_mapping("phrase a", "boost", "boost", confirmed=True)
        store.save_mapping("phrase b", "shields", "shields", confirmed=False)
        pending = store.get_pending()
        assert "phrase b" in pending
        assert "phrase a" not in pending

    def test_empty_when_all_confirmed(self):
        store.save_mapping("phrase a", "boost", "boost", confirmed=True)
        pending = store.get_pending()
        assert len(pending) == 0
