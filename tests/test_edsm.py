"""
tests/test_edsm.py — Unit tests for the EDSM API client.

All HTTP calls are mocked — no live API requests.
"""

from __future__ import annotations
import time
from unittest.mock import Mock, patch, MagicMock

import pytest

from search.edsm import EDSMClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _mock_response(status_code: int = 200, json_data=None):
    """Create a mock httpx Response."""
    resp = Mock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.raise_for_status = Mock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    return resp


# ---------------------------------------------------------------------------
# get_system() tests
# ---------------------------------------------------------------------------

class TestGetSystem:
    @patch.object(EDSMClient, "_get")
    def test_get_system_found(self, mock_get):
        mock_get.return_value = {
            "name": "Sol",
            "coords": {"x": 0, "y": 0, "z": 0},
            "information": {"allegiance": "Federation"},
            "primaryStar": {"type": "G (White-Yellow) Star", "isScoopable": True},
        }
        client = EDSMClient()
        result = client.get_system("Sol")
        assert result is not None
        assert result["name"] == "Sol"
        assert result["primaryStar"]["isScoopable"] is True

    @patch.object(EDSMClient, "_get")
    def test_get_system_not_found(self, mock_get):
        mock_get.return_value = None
        client = EDSMClient()
        result = client.get_system("NonExistent12345System")
        assert result is None


# ---------------------------------------------------------------------------
# get_estimated_value() tests
# ---------------------------------------------------------------------------

class TestGetEstimatedValue:
    @patch.object(EDSMClient, "_get")
    def test_estimated_value_valid(self, mock_get):
        mock_get.return_value = {
            "name": "Sol",
            "estimatedValue": 416050,
            "valuableBodies": [
                {"bodyName": "Earth", "valueMax": 607028},
            ],
        }
        client = EDSMClient()
        result = client.get_estimated_value("Sol")
        assert result is not None
        assert result["estimatedValue"] == 416050
        assert result["valuableBodies"][0]["bodyName"] == "Earth"


# ---------------------------------------------------------------------------
# get_market() tests
# ---------------------------------------------------------------------------

class TestGetMarket:
    @patch.object(EDSMClient, "_get")
    def test_get_market_valid(self, mock_get):
        mock_get.return_value = {
            "id": 128666762,
            "commodities": [
                {"name": "Gold", "buyPrice": 45000, "sellPrice": 46000, "stock": 100},
            ],
        }
        client = EDSMClient()
        result = client.get_market(market_id=128666762)
        assert result is not None
        assert result["commodities"][0]["name"] == "Gold"
        assert result["commodities"][0]["buyPrice"] == 45000


# ---------------------------------------------------------------------------
# get_traffic() tests
# ---------------------------------------------------------------------------

class TestGetTraffic:
    @patch.object(EDSMClient, "_get")
    def test_get_traffic(self, mock_get):
        mock_get.return_value = {
            "name": "Sol",
            "traffic": {"total": 50000, "week": 2000, "day": 300},
        }
        client = EDSMClient()
        result = client.get_traffic("Sol")
        assert result is not None
        assert result["traffic"]["total"] == 50000


# ---------------------------------------------------------------------------
# get_deaths() tests
# ---------------------------------------------------------------------------

class TestGetDeaths:
    @patch.object(EDSMClient, "_get")
    def test_get_deaths(self, mock_get):
        mock_get.return_value = {
            "name": "Deciat",
            "deaths": {"total": 1500, "week": 100, "day": 15},
        }
        client = EDSMClient()
        result = client.get_deaths("Deciat")
        assert result is not None
        assert result["deaths"]["total"] == 1500


# ---------------------------------------------------------------------------
# Authenticated endpoints
# ---------------------------------------------------------------------------

class TestAuthenticatedEndpoints:
    @patch.object(EDSMClient, "_get")
    def test_get_ranks(self, mock_get):
        mock_get.return_value = {
            "ranksVerbose": {
                "Combat": "Elite",
                "Trade": "Tycoon",
                "Explore": "Elite",
            },
        }
        client = EDSMClient()
        result = client.get_ranks("CMDR Test", "api123")
        assert result is not None
        assert result["ranksVerbose"]["Combat"] == "Elite"

    @patch.object(EDSMClient, "_get")
    def test_get_credits(self, mock_get):
        mock_get.return_value = {
            "credits": [{"balance": 500000000, "loan": 0}],
        }
        client = EDSMClient()
        result = client.get_credits("CMDR Test", "api123")
        assert result is not None
        assert result["credits"][0]["balance"] == 500000000

    @patch.object(EDSMClient, "_get")
    def test_get_materials(self, mock_get):
        mock_get.return_value = {
            "materials": [
                {"name": "Iron", "qty": 200},
                {"name": "Sulphur", "qty": 150},
            ],
        }
        client = EDSMClient()
        result = client.get_materials("CMDR Test", "api123")
        assert result is not None
        assert len(result["materials"]) == 2


# ---------------------------------------------------------------------------
# Rate limiting tests
# ---------------------------------------------------------------------------

class TestRateLimiting:
    @patch("time.sleep")
    def test_rate_limit_delays_when_called_quickly(self, mock_sleep):
        client = EDSMClient()
        client._last_request_time = time.time()
        client._rate_limit()
        # Should have called sleep since we just set _last_request_time to now
        mock_sleep.assert_called()

    @patch("time.sleep")
    def test_rate_limit_no_delay_when_enough_time_passed(self, mock_sleep):
        client = EDSMClient()
        client._last_request_time = time.time() - 5.0  # 5 seconds ago
        client._rate_limit()
        # Should NOT sleep since enough time passed
        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# get_nearby_systems() tests
# ---------------------------------------------------------------------------

class TestGetNearbySystems:
    @patch.object(EDSMClient, "_get")
    def test_get_sphere_systems(self, mock_get):
        mock_get.return_value = [
            {"name": "Alpha Centauri", "distance": 4.38},
            {"name": "Barnard's Star", "distance": 5.95},
        ]
        client = EDSMClient()
        result = client.get_sphere_systems("Sol", radius=10)
        assert result is not None
        assert len(result) == 2
        assert result[0]["name"] == "Alpha Centauri"
