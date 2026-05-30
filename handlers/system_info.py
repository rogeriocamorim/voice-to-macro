"""
handlers/system_info.py — System information, scan values, danger, nearby systems.

Queries EDSM for system data and speaks results via TTS.
"""

from __future__ import annotations
from typing import Any

from handlers import format_credits, format_population


def handle(params: dict, game_state: Any, config: dict, speaker: Any,
           binds: dict, edsm: Any, spansh: Any) -> bool:
    """Get general system information."""
    system = params.get("system") or (game_state.get_current_system() if game_state else None)
    if not system:
        speaker.say("No system specified and current system unknown.")
        return False

    data = edsm.get_system(system)
    if not data or not data.get("name"):
        speaker.say(f"No data found for {system}.")
        return False

    info = data.get("information", {})
    star = data.get("primaryStar", {})
    name = data["name"]

    parts = [f"{name}."]
    if info.get("allegiance"):
        parts.append(f"Allegiance: {info['allegiance']}.")
    if info.get("economy"):
        parts.append(f"Economy: {info['economy']}.")
    if info.get("population"):
        parts.append(f"Population: {format_population(info['population'])}.")
    if info.get("security"):
        parts.append(f"Security: {info['security']}.")
    if star:
        scoopable = "scoopable" if star.get("isScoopable") else "not scoopable"
        parts.append(f"Primary star: {star.get('type', 'Unknown')}, {scoopable}.")

    speaker.say(" ".join(parts))
    return True


def handle_scan_value(params: dict, game_state: Any, config: dict, speaker: Any,
                      binds: dict, edsm: Any, spansh: Any) -> bool:
    """Check exploration scan values for a system."""
    system = params.get("system") or (game_state.get_current_system() if game_state else None)
    if not system:
        speaker.say("No system specified and current system unknown.")
        return False

    data = edsm.get_estimated_value(system)
    if not data or not data.get("estimatedValue"):
        speaker.say(f"No scan data available for {system}.")
        return False

    value = data["estimatedValue"]
    mapped = data.get("estimatedValueMapped", 0)
    bodies = data.get("valuableBodies", [])

    msg = f"{system} estimated scan value: {format_credits(value)}."
    if mapped and mapped > value:
        msg += f" If fully mapped: {format_credits(mapped)}."

    if bodies:
        top = bodies[0]
        msg += f" Most valuable: {top['bodyName']} worth up to {format_credits(top['valueMax'])}."

    speaker.say(msg)
    return True


def handle_danger(params: dict, game_state: Any, config: dict, speaker: Any,
                  binds: dict, edsm: Any, spansh: Any) -> bool:
    """Assess how dangerous a system is based on death/traffic stats."""
    system = params.get("system") or (game_state.get_current_system() if game_state else None)
    if not system:
        speaker.say("No system specified and current system unknown.")
        return False

    deaths_data = edsm.get_deaths(system)
    traffic_data = edsm.get_traffic(system)

    deaths = deaths_data.get("deaths", {}) if deaths_data else {}
    traffic = traffic_data.get("traffic", {}) if traffic_data else {}

    day_deaths = deaths.get("day", 0)
    day_traffic = traffic.get("day", 0)
    week_deaths = deaths.get("week", 0)

    if day_traffic > 0:
        ratio = day_deaths / day_traffic
        if ratio > 0.1:
            level = "very dangerous"
        elif ratio > 0.03:
            level = "moderately dangerous"
        elif day_deaths > 0:
            level = "slightly risky"
        else:
            level = "safe"
    elif week_deaths > 5:
        level = "potentially dangerous"
    else:
        level = "low traffic, risk unknown"

    msg = f"{system} is {level}. {day_deaths} deaths today, {day_traffic} pilots passing through."
    if week_deaths > 0:
        msg += f" {week_deaths} deaths this week."

    speaker.say(msg)
    return True


def handle_nearby(params: dict, game_state: Any, config: dict, speaker: Any,
                  binds: dict, edsm: Any, spansh: Any) -> bool:
    """Find systems within a given radius."""
    system = game_state.get_current_system() if game_state else None
    if not system:
        speaker.say("Current system unknown. Cannot search nearby.")
        return False

    radius = params.get("radius", 50)
    if isinstance(radius, str):
        try:
            radius = int(radius)
        except ValueError:
            radius = 50

    radius = min(radius, 100)  # EDSM max is 100

    systems = edsm.get_sphere_systems(system, radius=radius)
    if not systems:
        speaker.say(f"No systems found within {radius} light years of {system}.")
        return False

    count = len(systems)
    top = systems[:5]

    msg = f"{count} systems within {radius} light years. Closest: "
    msg += ", ".join(
        f"{s['name']} at {s['distance']:.1f} light years"
        for s in top
    )
    msg += "."

    speaker.say(msg)
    return True


def handle_server_status(params: dict, game_state: Any, config: dict, speaker: Any,
                         binds: dict, edsm: Any, spansh: Any) -> bool:
    """Check Elite Dangerous server status."""
    status = edsm.get_server_status()
    if not status:
        speaker.say("Cannot check server status. EDSM unreachable.")
        return False

    status_type = status.get("type", "unknown")
    message = status.get("message", "Unknown")

    if status_type == "success":
        speaker.say(f"Elite Dangerous servers are online. Status: {message}.")
    elif status_type == "warning":
        speaker.say(f"Elite Dangerous servers have a warning: {message}.")
    else:
        speaker.say(f"Elite Dangerous servers may be down. Status: {message}.")

    return True
