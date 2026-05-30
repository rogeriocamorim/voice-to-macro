"""
gameapi/status_reader.py — Poll Elite Dangerous Status.json for real-time ship state.

Status.json is rewritten by the game ~4 times per second and contains:
- Flags bitfield (32 ship flags: docked, supercruise, hardpoints, etc.)
- Flags2 bitfield (20 on-foot/Odyssey flags)
- Pips (SYS/ENG/WPN distribution)
- GuiFocus (which panel is open)
- Fuel, Cargo, Destination, etc.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gameapi.game_state import GameState


# ---------------------------------------------------------------------------
# Flags bitfield constants (bit positions)
# ---------------------------------------------------------------------------

class ShipFlags:
    DOCKED = 0
    LANDED = 1
    LANDING_GEAR = 2
    SHIELDS_UP = 3
    SUPERCRUISE = 4
    FA_OFF = 5
    HARDPOINTS = 6
    IN_WING = 7
    LIGHTS = 8
    CARGO_SCOOP = 9
    SILENT_RUNNING = 10
    SCOOPING_FUEL = 11
    SRV_HANDBRAKE = 12
    SRV_TURRET = 13
    SRV_TURRET_RETRACTED = 14
    SRV_DRIVE_ASSIST = 15
    FSD_MASS_LOCKED = 16
    FSD_CHARGING = 17
    FSD_COOLDOWN = 18
    LOW_FUEL = 19
    OVERHEATING = 20
    HAS_LAT_LONG = 21
    IN_DANGER = 22
    BEING_INTERDICTED = 23
    IN_MAIN_SHIP = 24
    IN_FIGHTER = 25
    IN_SRV = 26
    HUD_ANALYSIS = 27
    NIGHT_VISION = 28
    ALT_FROM_AVG_RADIUS = 29
    FSD_JUMP = 30
    SRV_HIGH_BEAM = 31


class OnFootFlags:
    ON_FOOT = 0
    IN_TAXI = 1
    IN_MULTICREW = 2
    ON_FOOT_STATION = 3
    ON_FOOT_PLANET = 4
    AIM_DOWN_SIGHT = 5
    LOW_OXYGEN = 6
    LOW_HEALTH = 7
    COLD = 8
    HOT = 9
    VERY_COLD = 10
    VERY_HOT = 11
    GLIDE_MODE = 12
    ON_FOOT_HANGAR = 13
    ON_FOOT_SOCIAL = 14
    ON_FOOT_EXTERIOR = 15
    BREATHABLE_ATMO = 16
    TELEPRESENCE_MULTICREW = 17
    PHYSICAL_MULTICREW = 18
    FSD_HYPERDRIVE_CHARGING = 19


class GuiFocus:
    NONE = 0
    INTERNAL_PANEL = 1
    EXTERNAL_PANEL = 2
    COMMS_PANEL = 3
    ROLE_PANEL = 4
    STATION_SERVICES = 5
    GALAXY_MAP = 6
    SYSTEM_MAP = 7
    ORRERY = 8
    FSS_MODE = 9
    SAA_MODE = 10
    CODEX = 11


def check_flag(flags: int, bit: int) -> bool:
    """Check if a specific bit is set in the flags value."""
    return bool(flags & (1 << bit))


class StatusReader(threading.Thread):
    """
    Background thread that polls Status.json for real-time ship state.
    Updates GameState with current flags, pips, GUI focus, etc.
    """

    def __init__(self, journal_dir: str | Path, game_state: GameState):
        super().__init__(daemon=True, name="StatusReader")
        self.status_file = Path(journal_dir) / "Status.json"
        self.game_state = game_state
        self._stop_event = threading.Event()
        self._poll_interval = 0.5  # seconds
        self._last_timestamp = ""

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.is_set():
            try:
                if self.status_file.exists():
                    self._read_status()
            except Exception as e:
                # Status.json can be partially written; just retry
                pass
            time.sleep(self._poll_interval)

    def _read_status(self):
        try:
            with open(self.status_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return

        timestamp = data.get("timestamp", "")
        if timestamp == self._last_timestamp:
            return  # no change
        self._last_timestamp = timestamp

        # Update game state with status data
        self.game_state.update_status(
            flags=data.get("Flags", 0),
            flags2=data.get("Flags2", 0),
            pips=data.get("Pips", [0, 0, 0]),
            gui_focus=data.get("GuiFocus", 0),
            fuel=data.get("Fuel"),
            cargo=data.get("Cargo", 0.0),
            destination=data.get("Destination"),
            legal_state=data.get("LegalState", ""),
            balance=data.get("Balance"),
        )
