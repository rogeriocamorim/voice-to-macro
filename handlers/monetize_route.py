"""
handlers/monetize_route.py — Find profitable trades along current nav route.

Reads the player's plotted route from NavRoute.json, queries EDSM for
market data at each stop, and finds the best commodity to trade.
"""

from __future__ import annotations
from typing import Any

from handlers import format_credits


def handle(params: dict, game_state: Any, config: dict, speaker: Any,
           binds: dict, edsm: Any, spansh: Any) -> bool:
    """Find the most profitable trade along the current route."""
    route = game_state.get_nav_route() if game_state else None
    if not route:
        speaker.say("No route plotted. Plot a route first, Commander.")
        return False

    if len(route) < 2:
        speaker.say("Route too short for trade analysis.")
        return False

    speaker.say(f"Analyzing {len(route)} systems for trade opportunities...")

    # Collect market data for each stop
    stop_markets: dict[tuple[str, str], list[dict]] = {}

    for stop in route[:10]:  # Limit to first 10 stops to avoid API overload
        system_name = stop.get("StarSystem", "")
        if not system_name:
            continue

        stations_data = edsm.get_stations(system_name)
        if not stations_data:
            continue

        stations = stations_data.get("stations", [])
        for station in stations:
            if not station.get("haveMarket"):
                continue

            # Skip fleet carriers and distant stations
            dist = station.get("distanceToArrival", 0)
            if dist > 1500:
                continue

            market_id = station.get("marketId")
            if not market_id:
                continue

            market_data = edsm.get_market(market_id=market_id)
            if market_data and market_data.get("commodities"):
                stop_markets[(system_name, station["name"])] = market_data["commodities"]

    if not stop_markets:
        speaker.say("No market data available along your route.")
        return False

    # Find best trade opportunity
    best_profit = 0
    best_trade = None

    stops = list(stop_markets.keys())
    for i, (src_sys, src_stn) in enumerate(stops):
        src_commodities = {
            c["name"]: c for c in stop_markets[(src_sys, src_stn)]
            if c.get("buyPrice", 0) > 0 and c.get("stock", 0) > 0
        }

        for dst_sys, dst_stn in stops[i + 1:]:
            dst_commodities = {
                c["name"]: c for c in stop_markets[(dst_sys, dst_stn)]
                if c.get("sellPrice", 0) > 0 and c.get("demand", 0) > 0
            }

            for name, src_c in src_commodities.items():
                if name in dst_commodities:
                    profit = dst_commodities[name]["sellPrice"] - src_c["buyPrice"]
                    if profit > best_profit:
                        best_profit = profit
                        best_trade = {
                            "commodity": name,
                            "buy_at": f"{src_stn} in {src_sys}",
                            "buy_price": src_c["buyPrice"],
                            "sell_at": f"{dst_stn} in {dst_sys}",
                            "sell_price": dst_commodities[name]["sellPrice"],
                            "profit": profit,
                        }

    if not best_trade:
        speaker.say("No profitable trades found along your route.")
        return False

    msg = (
        f"Best trade along your route: "
        f"Buy {best_trade['commodity']} at {best_trade['buy_at']} "
        f"for {format_credits(best_trade['buy_price'])} per ton. "
        f"Sell at {best_trade['sell_at']} for {format_credits(best_trade['sell_price'])} per ton. "
        f"Profit: {format_credits(best_trade['profit'])} per ton."
    )
    speaker.say(msg)
    return True
