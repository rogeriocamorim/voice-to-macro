"""
search/edsm.py — EDSM API client.

Provides access to Elite Dangerous Star Map data:
- System info, coordinates, primary star
- Celestial bodies, scan values
- Stations, markets, commodities
- Traffic, deaths (danger assessment)
- Commander ranks, credits, materials (authenticated)

All public endpoints use GET. Authenticated endpoints require
commanderName + apiKey from config.yaml.

Rate limiting: 1 second between requests.
"""

from __future__ import annotations

import time
from typing import Any

import httpx


class EDSMClient:
    """Client for the EDSM (Elite Dangerous Star Map) REST API."""

    BASE_URL = "https://www.edsm.net"
    TIMEOUT = 15.0
    RATE_LIMIT_DELAY = 1.0  # seconds between requests
    USER_AGENT = "voice-to-macro/1.0 (Elite Dangerous voice assistant)"

    def __init__(self):
        self._last_request_time: float = 0.0
        self._client = httpx.Client(
            timeout=self.TIMEOUT,
            headers={"User-Agent": self.USER_AGENT},
            follow_redirects=True,
        )

    def close(self):
        self._client.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _rate_limit(self):
        """Enforce minimum delay between API requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.RATE_LIMIT_DELAY:
            time.sleep(self.RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict | list | None:
        """Make a rate-limited GET request. Returns parsed JSON or None on error."""
        self._rate_limit()
        url = f"{self.BASE_URL}{path}"

        try:
            response = self._client.get(url, params=params)

            # Handle rate limiting
            if response.status_code == 429:
                reset = response.headers.get("x-rate-limit-reset")
                wait = float(reset) if reset else 10.0
                print(f"[EDSM] Rate limited. Waiting {wait}s...")
                time.sleep(wait)
                response = self._client.get(url, params=params)

            if response.status_code != 200:
                print(f"[EDSM] HTTP {response.status_code} for {path}")
                return None

            data = response.json()

            # Empty responses
            if data == {} or data == []:
                return None

            return data

        except httpx.TimeoutException:
            print(f"[EDSM] Timeout: {path}")
            return None
        except httpx.RequestError as e:
            print(f"[EDSM] Request error: {e}")
            return None
        except Exception as e:
            print(f"[EDSM] Unexpected error: {e}")
            return None

    # ------------------------------------------------------------------
    # Tier 1: Public endpoints (no auth)
    # ------------------------------------------------------------------

    def get_system(self, system_name: str) -> dict | None:
        """
        Get system info: coordinates, allegiance, economy, primary star.

        GET /api-v1/system?systemName=X&showCoordinates=1&showInformation=1&showPrimaryStar=1
        """
        return self._get("/api-v1/system", params={
            "systemName": system_name,
            "showCoordinates": 1,
            "showInformation": 1,
            "showPrimaryStar": 1,
        })

    def get_systems(self, system_name: str | list[str]) -> list | None:
        """
        Get multiple systems. Pass a list for exact matches,
        or a single string for prefix matching.

        GET /api-v1/systems?systemName=X&showCoordinates=1&showInformation=1
        """
        params: dict[str, Any] = {
            "showCoordinates": 1,
            "showInformation": 1,
        }
        if isinstance(system_name, list):
            params["systemName[]"] = system_name
        else:
            params["systemName"] = system_name

        return self._get("/api-v1/systems", params=params)

    def get_sphere_systems(
        self, system_name: str, radius: int = 50, min_radius: int = 0
    ) -> list | None:
        """
        Get systems within a sphere radius (max 100 ly).

        GET /api-v1/sphere-systems?systemName=X&radius=50&showCoordinates=1&showInformation=1
        """
        return self._get("/api-v1/sphere-systems", params={
            "systemName": system_name,
            "radius": min(radius, 100),
            "minRadius": min_radius,
            "showCoordinates": 1,
            "showInformation": 1,
        })

    def get_bodies(self, system_name: str) -> dict | None:
        """
        Get celestial bodies in a system (stars, planets, rings).

        GET /api-system-v1/bodies?systemName=X
        """
        return self._get("/api-system-v1/bodies", params={
            "systemName": system_name,
        })

    def get_estimated_value(self, system_name: str) -> dict | None:
        """
        Get exploration scan value estimates for a system.

        GET /api-system-v1/estimated-value?systemName=X

        Returns: {estimatedValue, estimatedValueMapped, valuableBodies[]}
        """
        return self._get("/api-system-v1/estimated-value", params={
            "systemName": system_name,
        })

    def get_stations(self, system_name: str) -> dict | None:
        """
        Get stations in a system.

        GET /api-system-v1/stations?systemName=X

        Returns: {stations: [{name, type, distanceToArrival, haveMarket, marketId, ...}]}
        """
        return self._get("/api-system-v1/stations", params={
            "systemName": system_name,
        })

    def get_market(
        self,
        market_id: int | None = None,
        system_name: str | None = None,
        station_name: str | None = None,
    ) -> dict | None:
        """
        Get market commodity data for a station.

        Prefer market_id (faster). Falls back to systemName + stationName.

        GET /api-system-v1/stations/market?marketId=X
        """
        params: dict[str, Any] = {}
        if market_id:
            params["marketId"] = market_id
        elif system_name and station_name:
            params["systemName"] = system_name
            params["stationName"] = station_name
        else:
            return None

        return self._get("/api-system-v1/stations/market", params=params)

    def get_factions(self, system_name: str, show_history: bool = False) -> dict | None:
        """
        Get faction info for a system.

        GET /api-system-v1/factions?systemName=X&showHistory=0
        """
        return self._get("/api-system-v1/factions", params={
            "systemName": system_name,
            "showHistory": 1 if show_history else 0,
        })

    def get_traffic(self, system_name: str) -> dict | None:
        """
        Get traffic stats for a system.

        GET /api-system-v1/traffic?systemName=X

        Returns: {traffic: {total, week, day}, breakdown: {ship: count}}
        """
        return self._get("/api-system-v1/traffic", params={
            "systemName": system_name,
        })

    def get_deaths(self, system_name: str) -> dict | None:
        """
        Get death stats for a system.

        GET /api-system-v1/deaths?systemName=X

        Returns: {deaths: {total, week, day}}
        """
        return self._get("/api-system-v1/deaths", params={
            "systemName": system_name,
        })

    def get_server_status(self) -> dict | None:
        """
        Get Elite Dangerous server status.

        GET /api-status-v1/elite-server

        Returns: {lastUpdate, type: "success"|"warning"|"danger", message, status}
        """
        return self._get("/api-status-v1/elite-server")

    # ------------------------------------------------------------------
    # Tier 2: Authenticated endpoints (require commanderName + apiKey)
    # ------------------------------------------------------------------

    def get_position(self, commander_name: str, api_key: str) -> dict | None:
        """
        Get commander's last known position.

        GET /api-logs-v1/get-position?commanderName=X&apiKey=Y&showCoordinates=1
        """
        data = self._get("/api-logs-v1/get-position", params={
            "commanderName": commander_name,
            "apiKey": api_key,
            "showCoordinates": 1,
        })
        if data and data.get("msgnum") == 100:
            return data
        return None

    def get_ranks(self, commander_name: str, api_key: str) -> dict | None:
        """
        Get commander ranks and progress.

        GET /api-commander-v1/get-ranks?commanderName=X&apiKey=Y

        Returns: {ranks: {Combat, Trade, Explore, ...}, progress, ranksVerbose}
        """
        data = self._get("/api-commander-v1/get-ranks", params={
            "commanderName": commander_name,
            "apiKey": api_key,
        })
        if data and data.get("msgnum") == 100:
            return data
        return None

    def get_credits(
        self, commander_name: str, api_key: str, period: str | None = None
    ) -> dict | None:
        """
        Get commander credits.

        GET /api-commander-v1/get-credits?commanderName=X&apiKey=Y&period=7DAY

        period: None (latest), "7DAY", "1MONTH", "3MONTH", "6MONTH"
        Returns: {credits: [{balance, loan, date}]}
        """
        params: dict[str, Any] = {
            "commanderName": commander_name,
            "apiKey": api_key,
        }
        if period:
            params["period"] = period

        data = self._get("/api-commander-v1/get-credits", params=params)
        if data and data.get("msgnum") == 100:
            return data
        return None

    def get_materials(
        self, commander_name: str, api_key: str, mat_type: str = "materials"
    ) -> dict | None:
        """
        Get commander materials, encoded data, or cargo.

        GET /api-commander-v1/get-materials?commanderName=X&apiKey=Y&type=materials

        mat_type: "materials" | "data" | "cargo"
        Returns: {materials: [{type, name, qty}]}
        """
        data = self._get("/api-commander-v1/get-materials", params={
            "commanderName": commander_name,
            "apiKey": api_key,
            "type": mat_type,
        })
        if data and data.get("msgnum") == 100:
            return data
        return None

    def get_flight_logs(
        self,
        commander_name: str,
        api_key: str,
        start_datetime: str | None = None,
        end_datetime: str | None = None,
    ) -> dict | None:
        """
        Get commander flight logs.

        GET /api-logs-v1/get-logs?commanderName=X&apiKey=Y

        Max interval: 1 week. Rate limit: 360/hour.
        Date format: "YYYY-MM-DD HH:MM:SS" (UTC)
        Returns: {logs: [{shipId, system, firstDiscover, date}]}
        """
        params: dict[str, Any] = {
            "commanderName": commander_name,
            "apiKey": api_key,
        }
        if start_datetime:
            params["startDateTime"] = start_datetime
        if end_datetime:
            params["endDateTime"] = end_datetime

        data = self._get("/api-logs-v1/get-logs", params=params)
        if data and data.get("msgnum") == 100:
            return data
        return None
