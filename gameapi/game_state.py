"""
gameapi/game_state.py — Aggregated game state manager.

Maintains the current state of the game by processing events from the
journal watcher and status updates from the status reader. Thread-safe
via a lock since background threads write while the main loop reads.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from gameapi.events import (
    Docked,
    FSDJump,
    JoinACrew,
    JournalEvent,
    LoadGame,
    Loadout,
    Location,
    NavRoute,
    NavRouteClear,
    QuitACrew,
    SetUserShipName,
    ShipyardBuy,
    ShipyardSwap,
    Undocked,
)
from gameapi.journal_watcher import read_nav_route
from gameapi.status_reader import ShipFlags, check_flag


class GameState:
    """
    Aggregated game state — the single source of truth for the current
    game context. Updated by JournalWatcher and StatusReader threads.
    """

    def __init__(self, journal_dir: str | Path):
        self.journal_dir = Path(journal_dir)
        self._lock = threading.Lock()

        # Position
        self._system_name: str | None = None
        self._system_address: int | None = None
        self._system_coords: list[float] | None = None
        self._station_name: str | None = None
        self._market_id: int | None = None

        # Ship
        self._ship_id: int | None = None
        self._ship_type: str | None = None
        self._ship_name: str | None = None
        self._commander: str | None = None
        self._credits: int | None = None
        self._fuel_level: float | None = None
        self._fuel_capacity: float | None = None

        # Navigation
        self._nav_route: list[dict] | None = None

        # Status.json derived
        self._flags: int = 0
        self._flags2: int = 0
        self._pips: list[int] = [0, 0, 0]
        self._gui_focus: int = 0
        self._destination: dict | None = None
        self._cargo: float = 0.0
        self._legal_state: str = ""
        self._balance: int | None = None

        # Crew state
        self._in_crew: bool = False
        self._send_events: bool = True

    # ------------------------------------------------------------------
    # Event handling (called by JournalWatcher)
    # ------------------------------------------------------------------

    def handle_event(self, event: JournalEvent) -> None:
        """Process a journal event and update state accordingly."""
        with self._lock:
            self._handle_event_internal(event)

    def _handle_event_internal(self, event: JournalEvent) -> None:
        """
        State transition logic.
        Based on EDSM transient state tracking documentation.
        """
        etype = event.event

        if etype == "LoadGame":
            assert isinstance(event, LoadGame)
            self._system_name = None
            self._system_address = None
            self._system_coords = None
            self._station_name = None
            self._market_id = None
            self._ship_id = None
            self._commander = event.Commander
            self._credits = event.Credits if event.Credits else self._credits
            self._fuel_level = event.FuelLevel if event.FuelLevel else self._fuel_level
            self._fuel_capacity = event.FuelCapacity if event.FuelCapacity else self._fuel_capacity

        elif etype == "SetUserShipName":
            assert isinstance(event, SetUserShipName)
            self._ship_id = event.ShipID

        elif etype == "ShipyardBuy":
            self._ship_id = None

        elif etype == "ShipyardSwap":
            assert isinstance(event, ShipyardSwap)
            self._ship_id = event.ShipID

        elif etype == "Loadout":
            assert isinstance(event, Loadout)
            self._ship_id = event.ShipID
            if event.Ship:
                self._ship_type = event.Ship
            if event.ShipName:
                self._ship_name = event.ShipName

        elif etype == "Undocked":
            self._station_name = None
            self._market_id = None

        elif etype in ("Location", "FSDJump", "Docked"):
            star_system = getattr(event, "StarSystem", None)
            if star_system and star_system != self._system_name:
                self._system_coords = None

            # Skip CQC/ProvingGround
            if star_system and star_system not in ("ProvingGround", "CQC"):
                system_address = getattr(event, "SystemAddress", None)
                if system_address:
                    self._system_address = system_address
                self._system_name = star_system

                star_pos = getattr(event, "StarPos", None)
                if star_pos:
                    self._system_coords = star_pos
            elif star_system in ("ProvingGround", "CQC"):
                self._system_name = None
                self._system_address = None
                self._system_coords = None

            market_id = getattr(event, "MarketID", None)
            if market_id:
                self._market_id = market_id
            station_name = getattr(event, "StationName", None)
            if station_name:
                self._station_name = station_name

            # FSDJump also updates fuel
            if etype == "FSDJump" and isinstance(event, FSDJump):
                if event.FuelLevel:
                    self._fuel_level = event.FuelLevel

        elif etype == "NavRoute":
            self._nav_route = read_nav_route(self.journal_dir)

        elif etype == "NavRouteClear":
            self._nav_route = None

        elif etype == "JoinACrew":
            assert isinstance(event, JoinACrew)
            if event.Captain and event.Captain != self._commander:
                self._send_events = False
            self._in_crew = True
            self._system_name = None
            self._system_address = None
            self._system_coords = None
            self._station_name = None
            self._market_id = None

        elif etype == "QuitACrew":
            self._send_events = True
            self._in_crew = False
            self._system_name = None
            self._system_address = None
            self._system_coords = None
            self._station_name = None
            self._market_id = None

    # ------------------------------------------------------------------
    # Status updates (called by StatusReader)
    # ------------------------------------------------------------------

    def update_status(
        self,
        flags: int = 0,
        flags2: int = 0,
        pips: list[int] | None = None,
        gui_focus: int = 0,
        fuel: dict | None = None,
        cargo: float = 0.0,
        destination: dict | None = None,
        legal_state: str = "",
        balance: int | None = None,
    ) -> None:
        """Update ship status from Status.json polling."""
        with self._lock:
            self._flags = flags
            self._flags2 = flags2
            if pips:
                self._pips = pips
            self._gui_focus = gui_focus
            if fuel:
                self._fuel_level = fuel.get("FuelMain", self._fuel_level)
            self._cargo = cargo
            self._destination = destination
            self._legal_state = legal_state
            if balance is not None:
                self._balance = balance

    # ------------------------------------------------------------------
    # Public read API (called by main loop and handlers)
    # ------------------------------------------------------------------

    def get_current_system(self) -> str | None:
        with self._lock:
            return self._system_name

    def get_current_station(self) -> str | None:
        with self._lock:
            return self._station_name

    def get_system_coords(self) -> list[float] | None:
        with self._lock:
            return self._system_coords

    def get_nav_route(self) -> list[dict] | None:
        with self._lock:
            return self._nav_route

    def get_market_id(self) -> int | None:
        with self._lock:
            return self._market_id

    def get_commander(self) -> str | None:
        with self._lock:
            return self._commander

    def get_fuel(self) -> tuple[float | None, float | None]:
        with self._lock:
            return (self._fuel_level, self._fuel_capacity)

    def get_pips(self) -> list[int]:
        with self._lock:
            return list(self._pips)

    def get_gui_focus(self) -> int:
        with self._lock:
            return self._gui_focus

    def get_destination(self) -> dict | None:
        with self._lock:
            return self._destination

    def get_balance(self) -> int | None:
        with self._lock:
            return self._balance

    def get_ship_type(self) -> str | None:
        with self._lock:
            return self._ship_type

    def get_ship_name(self) -> str | None:
        with self._lock:
            return self._ship_name

    def get_cargo(self) -> float:
        with self._lock:
            return self._cargo

    # Ship flag properties
    def is_docked(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.DOCKED)

    def is_landed(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.LANDED)

    def is_supercruise(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.SUPERCRUISE)

    def is_landing_gear_down(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.LANDING_GEAR)

    def is_hardpoints_deployed(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.HARDPOINTS)

    def is_cargo_scoop_deployed(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.CARGO_SCOOP)

    def is_shields_up(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.SHIELDS_UP)

    def is_lights_on(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.LIGHTS)

    def is_silent_running(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.SILENT_RUNNING)

    def is_fsd_charging(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.FSD_CHARGING)

    def is_low_fuel(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.LOW_FUEL)

    def is_in_danger(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.IN_DANGER)

    def is_being_interdicted(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.BEING_INTERDICTED)

    def is_night_vision(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.NIGHT_VISION)

    def is_in_hyperspace(self) -> bool:
        with self._lock:
            return check_flag(self._flags, ShipFlags.FSD_JUMP)

    # ------------------------------------------------------------------
    # Summary for LLM prompt context
    # ------------------------------------------------------------------

    def get_status_summary(self) -> dict[str, Any]:
        """
        Return a concise summary of current game state for injection
        into the LLM classification prompt.
        """
        with self._lock:
            fuel_str = ""
            if self._fuel_level is not None:
                if self._fuel_capacity:
                    fuel_str = f"{self._fuel_level:.1f}/{self._fuel_capacity:.1f}"
                else:
                    fuel_str = f"{self._fuel_level:.1f}"

            return {
                "system": self._system_name or "Unknown",
                "station": self._station_name or "Not docked",
                "docked": check_flag(self._flags, ShipFlags.DOCKED),
                "supercruise": check_flag(self._flags, ShipFlags.SUPERCRUISE),
                "fuel": fuel_str or "Unknown",
                "destination": self._destination.get("Name") if self._destination else None,
                "in_danger": check_flag(self._flags, ShipFlags.IN_DANGER),
                "gui_focus": self._gui_focus,
            }
