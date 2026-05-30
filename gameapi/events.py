"""
gameapi/events.py — Journal event dataclasses.

Each class maps to a specific Elite Dangerous journal event.
Only events we need for game state tracking are defined here;
unknown events are silently ignored by the watcher.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

@dataclass
class JournalEvent:
    timestamp: str
    event: str


# ---------------------------------------------------------------------------
# Position / Navigation
# ---------------------------------------------------------------------------

@dataclass
class FSDJump(JournalEvent):
    StarSystem: str = ""
    SystemAddress: int = 0
    StarPos: list = field(default_factory=list)
    JumpDist: float = 0.0
    FuelUsed: float = 0.0
    FuelLevel: float = 0.0
    SystemAllegiance: str = ""
    SystemEconomy_Localised: str = ""
    SystemGovernment_Localised: str = ""
    SystemSecurity_Localised: str = ""
    Population: int = 0
    Body: str = ""
    BodyType: str = ""


@dataclass
class Location(JournalEvent):
    StarSystem: str = ""
    SystemAddress: int = 0
    StarPos: list = field(default_factory=list)
    Docked: bool = False
    StationName: str = ""
    StationType: str = ""
    MarketID: int = 0
    Body: str = ""
    BodyType: str = ""


@dataclass
class Docked(JournalEvent):
    StationName: str = ""
    StationType: str = ""
    StarSystem: str = ""
    SystemAddress: int = 0
    MarketID: int = 0
    DistFromStarLS: float = 0.0
    StationServices: list = field(default_factory=list)
    LandingPads: dict = field(default_factory=dict)


@dataclass
class Undocked(JournalEvent):
    StationName: str = ""
    StationType: str = ""


@dataclass
class NavRoute(JournalEvent):
    """Triggers reading NavRoute.json for actual route data."""
    pass


@dataclass
class NavRouteClear(JournalEvent):
    """Route was cleared."""
    pass


# ---------------------------------------------------------------------------
# Ship / Commander
# ---------------------------------------------------------------------------

@dataclass
class LoadGame(JournalEvent):
    Commander: str = ""
    Ship: str = ""
    ShipName: str = ""
    ShipIdent: str = ""
    ShipID: int = 0
    FuelLevel: float = 0.0
    FuelCapacity: float = 0.0
    GameMode: str = ""
    Credits: int = 0
    Loan: int = 0


@dataclass
class Loadout(JournalEvent):
    ShipID: int = 0
    Ship: str = ""
    ShipName: str = ""
    ShipIdent: str = ""


@dataclass
class SetUserShipName(JournalEvent):
    ShipID: int = 0
    UserShipName: str = ""
    UserShipId: str = ""


@dataclass
class ShipyardSwap(JournalEvent):
    ShipID: int = 0
    ShipType: str = ""


@dataclass
class ShipyardBuy(JournalEvent):
    ShipType: str = ""
    ShipPrice: int = 0


# ---------------------------------------------------------------------------
# Market / Trade
# ---------------------------------------------------------------------------

@dataclass
class MarketBuy(JournalEvent):
    MarketID: int = 0
    Type: str = ""
    Count: int = 0
    BuyPrice: int = 0
    TotalCost: int = 0


@dataclass
class MarketSell(JournalEvent):
    MarketID: int = 0
    Type: str = ""
    Count: int = 0
    SellPrice: int = 0
    TotalSale: int = 0
    AvgPricePaid: int = 0


# ---------------------------------------------------------------------------
# Exploration
# ---------------------------------------------------------------------------

@dataclass
class Scan(JournalEvent):
    ScanType: str = ""
    BodyName: str = ""
    BodyID: int = 0
    StarSystem: str = ""
    PlanetClass: str = ""
    StarType: str = ""
    TerraformState: str = ""
    Landable: bool = False
    WasDiscovered: bool = False
    WasMapped: bool = False
    DistanceFromArrivalLS: float = 0.0


# ---------------------------------------------------------------------------
# Crew (for state tracking only)
# ---------------------------------------------------------------------------

@dataclass
class JoinACrew(JournalEvent):
    Captain: str = ""


@dataclass
class QuitACrew(JournalEvent):
    Captain: str = ""


# ---------------------------------------------------------------------------
# Event Registry
# ---------------------------------------------------------------------------

EVENT_REGISTRY: dict[str, type] = {
    "FSDJump": FSDJump,
    "Location": Location,
    "Docked": Docked,
    "Undocked": Undocked,
    "NavRoute": NavRoute,
    "NavRouteClear": NavRouteClear,
    "LoadGame": LoadGame,
    "Loadout": Loadout,
    "SetUserShipName": SetUserShipName,
    "ShipyardSwap": ShipyardSwap,
    "ShipyardBuy": ShipyardBuy,
    "MarketBuy": MarketBuy,
    "MarketSell": MarketSell,
    "Scan": Scan,
    "JoinACrew": JoinACrew,
    "QuitACrew": QuitACrew,
}
