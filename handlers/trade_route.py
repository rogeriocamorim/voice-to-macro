"""
handlers/trade_route.py — Full trade route calculation via Spansh.

Calculates an optimal multi-hop trade route from the current location
using Spansh's trade route API.
"""

from __future__ import annotations
from typing import Any

from handlers import format_credits


def handle(params: dict, game_state: Any, config: dict, speaker: Any,
           binds: dict, edsm: Any, spansh: Any) -> bool:
    """Calculate an optimal trade route from current location."""
    system = game_state.get_current_system() if game_state else None
    station = game_state.get_current_station() if game_state else None

    if not system:
        speaker.say("Current system unknown.")
        return False

    if not station:
        speaker.say("You need to be docked at a station to calculate a trade route.")
        return False

    # Get trade parameters from config
    max_cargo = config.get("trade_max_cargo", 200)
    max_hops = config.get("trade_max_hops", 5)
    max_hop_distance = config.get("trade_max_hop_distance", 30)
    requires_large_pad = config.get("trade_requires_large_pad", True)
    starting_capital = config.get("trade_starting_capital", 10_000_000)

    # Use actual balance if available
    balance = game_state.get_balance() if game_state else None
    if balance and balance > 0:
        starting_capital = balance

    speaker.say("Calculating trade route. This may take a moment...")

    result = spansh.trade_route(
        system=system,
        station=station,
        max_hops=max_hops,
        max_hop_distance=max_hop_distance,
        starting_capital=starting_capital,
        max_cargo=max_cargo,
        requires_large_pad=requires_large_pad,
    )

    if not result:
        speaker.say("Could not calculate a trade route. Spansh may be busy or parameters too restrictive.")
        return False

    legs = result
    if not legs:
        speaker.say("No profitable trade route found from this location.")
        return False

    # Calculate total profit
    total_profit = 0
    if isinstance(legs[-1], dict):
        total_profit = legs[-1].get("cumulative_profit", 0)

    msg = f"Found trade route with {len(legs)} legs. "
    if total_profit:
        msg += f"Total estimated profit: {format_credits(total_profit)}. "

    # Announce first leg details
    if legs and isinstance(legs[0], dict):
        first = legs[0]
        src = first.get("source", {})
        dst = first.get("destination", {})
        commodities = first.get("commodities", [])
        leg_profit = first.get("total_profit", 0)

        if commodities:
            commodity_name = commodities[0].get("name", "unknown commodity")
            msg += (
                f"First: Buy {commodity_name} here, "
                f"sell at {dst.get('station', 'Unknown')} in {dst.get('system', 'Unknown')}. "
            )
            if leg_profit:
                msg += f"Leg profit: {format_credits(leg_profit)}."

    speaker.say(msg)
    return True
