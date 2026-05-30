"""
handlers/find_commodity.py — Find best station to buy/sell a commodity.

Uses Spansh for cross-galaxy station search, then EDSM for price details.
"""

from __future__ import annotations
from typing import Any

from handlers import format_credits


def handle(params: dict, game_state: Any, config: dict, speaker: Any,
           binds: dict, edsm: Any, spansh: Any) -> bool:
    """Find stations selling or buying a commodity."""
    commodity = params.get("commodity", "").strip()
    intent = params.get("intent", "buy")  # "buy" or "sell"

    if not commodity:
        speaker.say("What commodity are you looking for, Commander?")
        return False

    system = game_state.get_current_system() if game_state else None
    if not system:
        speaker.say("Current system unknown. Cannot search for commodities.")
        return False

    speaker.say(f"Searching for {commodity} near {system}...")

    # Search via Spansh
    filters = {
        "distance": {"min": 0, "max": 100},
        "market": [{"name": commodity}],
    }

    # Prefer large pad stations
    if config.get("trade_requires_large_pad", True):
        filters["has_large_pad"] = {"value": True}

    results = spansh.search_stations(reference_system=system, filters=filters)

    if not results:
        # Fallback: try without large pad requirement
        if "has_large_pad" in filters:
            del filters["has_large_pad"]
            results = spansh.search_stations(reference_system=system, filters=filters)

    if not results:
        speaker.say(f"No stations found with {commodity} within 100 light years.")
        return False

    # Report top 3
    top = results[:3]
    if intent == "buy":
        msg = f"Best places to buy {commodity}: "
    else:
        msg = f"Best places to sell {commodity}: "

    for r in top:
        station = r.get("name", "Unknown station")
        system_name = r.get("system_name", "Unknown system")
        distance = r.get("distance", 0)

        # Try to get price from market data in result
        price_info = ""
        market = r.get("market", [])
        for m in market:
            if m.get("commodity", "").lower() == commodity.lower():
                if intent == "buy" and m.get("buy_price"):
                    price_info = f" at {format_credits(m['buy_price'])} per ton"
                elif intent == "sell" and m.get("sell_price"):
                    price_info = f" at {format_credits(m['sell_price'])} per ton"
                break

        msg += f"{station} in {system_name}, {distance:.1f} light years{price_info}. "

    speaker.say(msg)
    return True
