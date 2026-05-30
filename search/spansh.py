"""
search/spansh.py — Spansh API client.

Provides trade route calculation, station/system search, and commodity finding.
Spansh uses an async pattern: POST criteria -> get job ID -> poll GET until 200.

All search endpoints use this pattern:
1. POST search criteria to a /save or /route endpoint
2. Receive a job/search_reference ID
3. Poll GET /results/{id} or /recall/{id} until HTTP 200
"""

from __future__ import annotations

import time
from typing import Any

import httpx


class SpanshClient:
    """Client for the Spansh API (trade routes, station search)."""

    BASE_URL = "https://spansh.co.uk"
    TIMEOUT = 15.0
    POLL_INTERVAL = 2.0  # seconds between poll attempts
    MAX_POLL_TIME = 60.0  # max seconds to wait for results
    USER_AGENT = "voice-to-macro/1.0 (Elite Dangerous voice assistant)"

    def __init__(self):
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

    def _poll_results(self, job_id: str, endpoint: str = "results") -> dict | None:
        """
        Poll for results until HTTP 200 or timeout.

        Parameters
        ----------
        job_id : the job/search reference ID
        endpoint : "results" for trade routes, or "recall" path for searches
        """
        if "/" in endpoint:
            url = f"{self.BASE_URL}/api/{endpoint}/{job_id}"
        else:
            url = f"{self.BASE_URL}/api/{endpoint}/{job_id}"

        start = time.time()
        while time.time() - start < self.MAX_POLL_TIME:
            try:
                response = self._client.get(url)
                if response.status_code == 200:
                    return response.json()
                # Not ready yet — keep polling
            except (httpx.TimeoutException, httpx.RequestError):
                pass
            time.sleep(self.POLL_INTERVAL)

        print(f"[SPANSH] Poll timeout after {self.MAX_POLL_TIME}s for job {job_id}")
        return None

    def _post_form(self, path: str, data: dict[str, Any]) -> str | None:
        """POST form-urlencoded data, return job ID."""
        url = f"{self.BASE_URL}{path}"
        try:
            response = self._client.post(url, data=data)
            if response.status_code in (200, 202):
                result = response.json()
                return result.get("job") or result.get("search_reference")
        except (httpx.TimeoutException, httpx.RequestError) as e:
            print(f"[SPANSH] POST error: {e}")
        return None

    def _post_json(self, path: str, body: dict[str, Any]) -> str | None:
        """POST JSON data, return search reference ID."""
        url = f"{self.BASE_URL}{path}"
        try:
            response = self._client.post(url, json=body)
            if response.status_code in (200, 202):
                result = response.json()
                return result.get("search_reference") or result.get("job")
        except (httpx.TimeoutException, httpx.RequestError) as e:
            print(f"[SPANSH] POST error: {e}")
        return None

    # ------------------------------------------------------------------
    # Trade Route
    # ------------------------------------------------------------------

    def trade_route(
        self,
        system: str,
        station: str,
        max_hops: int = 5,
        max_hop_distance: float = 30.0,
        starting_capital: int = 10_000_000,
        max_cargo: int = 200,
        max_system_distance: int = 1500,
        requires_large_pad: bool = True,
        allow_prohibited: bool = False,
        allow_planetary: bool = True,
        allow_fleet_carriers: bool = False,
        max_price_age: int = 7200,
    ) -> list[dict] | None:
        """
        Calculate an optimal trade route from a starting station.

        POST /api/trade/route (form-urlencoded)
        Poll: GET /api/results/{job}

        Returns list of trade legs, each with source, destination,
        commodities, profit, and distance.
        """
        data: dict[str, Any] = {
            "system": system,
            "station": station,
            "max_hops": max_hops,
            "max_hop_distance": max_hop_distance,
            "starting_capital": starting_capital,
            "max_cargo": max_cargo,
            "max_system_distance": max_system_distance,
            "max_price_age": max_price_age,
        }

        if requires_large_pad:
            data["requires_large_pad"] = 1
        if allow_prohibited:
            data["allow_prohibited"] = 1
        if allow_planetary:
            data["allow_planetary"] = 1
        if allow_fleet_carriers:
            data["allow_player_owned"] = 1

        job_id = self._post_form("/api/trade/route", data)
        if not job_id:
            return None

        result = self._poll_results(job_id, "results")
        if result:
            return result.get("result", [])
        return None

    # ------------------------------------------------------------------
    # Station Search
    # ------------------------------------------------------------------

    def search_stations(
        self,
        reference_system: str,
        filters: dict[str, Any] | None = None,
        size: int = 20,
    ) -> list[dict] | None:
        """
        Search for stations matching criteria.

        POST /api/stations/search/save (JSON)
        Poll: GET /api/stations/search/recall/{id}

        Filters can include:
        - "distance": {"min": 0, "max": 100}
        - "market": [{"name": "Gold"}]
        - "has_large_pad": {"value": true}
        - "is_planetary": {"value": false}
        - "type": {"value": ["Coriolis Starport", "Orbis Starport"]}
        """
        body: dict[str, Any] = {
            "filters": filters or {},
            "sort": [],
            "page": 0,
            "size": size,
            "reference_system": reference_system,
        }

        ref_id = self._post_json("/api/stations/search/save", body)
        if not ref_id:
            return None

        result = self._poll_results(ref_id, "stations/search/recall")
        if result:
            return result.get("results", [])
        return None

    # ------------------------------------------------------------------
    # System Search
    # ------------------------------------------------------------------

    def search_systems(
        self,
        reference_system: str,
        filters: dict[str, Any] | None = None,
    ) -> list[dict] | None:
        """
        Search for star systems matching criteria.

        POST /api/systems/search/save (JSON)
        Poll: GET /api/systems/search/recall/{id}
        """
        body: dict[str, Any] = {
            "filters": filters or {},
            "reference_system": reference_system,
        }

        ref_id = self._post_json("/api/systems/search/save", body)
        if not ref_id:
            return None

        result = self._poll_results(ref_id, "systems/search/recall")
        if result:
            return result.get("results", [])
        return None

    # ------------------------------------------------------------------
    # Fleet Carrier Route
    # ------------------------------------------------------------------

    def carrier_route(
        self,
        source: str,
        destination: str,
        capacity: int = 25000,
        capacity_used: int = 0,
        starting_fuel: int = 500,
    ) -> list[dict] | None:
        """
        Calculate a fleet carrier route.

        POST /api/fleetcarrier/route (form-urlencoded)
        Poll: GET /api/results/{job}

        Returns list of jumps: {name, distance, fuel_used, has_icy_ring, ...}
        """
        data = {
            "source": source,
            "destinations": destination,
            "capacity": capacity,
            "capacity_used": capacity_used,
            "calculate_starting_fuel": 0,
            "starting_fuel": starting_fuel,
        }

        job_id = self._post_form("/api/fleetcarrier/route", data)
        if not job_id:
            return None

        result = self._poll_results(job_id, "results")
        if result and result.get("result"):
            return result["result"].get("jumps", [])
        return None

    # ------------------------------------------------------------------
    # Nearest System
    # ------------------------------------------------------------------

    def nearest_system(self, x: float, y: float, z: float) -> dict | None:
        """
        Find the nearest known system to given coordinates.

        GET /api/nearest?x=X&y=Y&z=Z

        Returns: {"name": str, "x": float, "y": float, "z": float, "distance": float}
        """
        url = f"{self.BASE_URL}/api/nearest"
        try:
            response = self._client.get(url, params={"x": x, "y": y, "z": z})
            if response.status_code == 200:
                data = response.json()
                return data.get("system")
        except (httpx.TimeoutException, httpx.RequestError) as e:
            print(f"[SPANSH] nearest_system error: {e}")
        return None
