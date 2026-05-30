"""
handlers/commander_status.py — Commander data from EDSM (authenticated).

Requires edsm_commander_name and edsm_api_key in config.yaml.
"""

from __future__ import annotations
from typing import Any

from handlers import format_credits


def handle(params: dict, game_state: Any, config: dict, speaker: Any,
           binds: dict, edsm: Any, spansh: Any) -> bool:
    """Check commander data: credits, ranks, materials, or position."""
    query = params.get("query", "credits")

    cmdr = config.get("edsm_commander_name", "")
    api_key = config.get("edsm_api_key", "")

    if not cmdr or not api_key:
        speaker.say("EDSM commander name or API key not configured. Check config.yaml.")
        return False

    if query == "credits":
        return _handle_credits(cmdr, api_key, speaker, edsm)
    elif query == "ranks":
        return _handle_ranks(cmdr, api_key, speaker, edsm)
    elif query == "materials":
        return _handle_materials(cmdr, api_key, speaker, edsm)
    elif query == "position":
        return _handle_position(cmdr, api_key, speaker, edsm)
    else:
        speaker.say(f"Unknown commander query: {query}.")
        return False


def _handle_credits(cmdr: str, api_key: str, speaker: Any, edsm: Any) -> bool:
    data = edsm.get_credits(cmdr, api_key)
    if data and data.get("credits"):
        balance = data["credits"][0].get("balance", 0)
        loan = data["credits"][0].get("loan", 0)
        msg = f"Commander, your balance is {format_credits(balance)}."
        if loan > 0:
            msg += f" Outstanding loan: {format_credits(loan)}."
        speaker.say(msg)
        return True
    speaker.say("Could not retrieve credit information from EDSM.")
    return False


def _handle_ranks(cmdr: str, api_key: str, speaker: Any, edsm: Any) -> bool:
    data = edsm.get_ranks(cmdr, api_key)
    if data and data.get("ranksVerbose"):
        ranks = data["ranksVerbose"]
        progress = data.get("progress", {})

        # Report the most interesting ranks
        parts = []
        for rank_name in ("Combat", "Trade", "Explore", "Federation", "Empire"):
            if rank_name in ranks:
                rank_val = ranks[rank_name]
                prog = progress.get(rank_name, 0)
                if rank_val != "None":
                    parts.append(f"{rank_name}: {rank_val}, {prog}% progress")

        if parts:
            speaker.say("Your ranks: " + ". ".join(parts) + ".")
            return True

    speaker.say("Could not retrieve rank information from EDSM.")
    return False


def _handle_materials(cmdr: str, api_key: str, speaker: Any, edsm: Any) -> bool:
    data = edsm.get_materials(cmdr, api_key, mat_type="materials")
    if data and data.get("materials"):
        materials = data["materials"]
        count = len(materials)
        total = sum(m.get("qty", 0) for m in materials)
        speaker.say(f"You have {count} different materials, {total} total units in storage.")
        return True
    speaker.say("Could not retrieve materials information from EDSM.")
    return False


def _handle_position(cmdr: str, api_key: str, speaker: Any, edsm: Any) -> bool:
    data = edsm.get_position(cmdr, api_key)
    if data and data.get("system"):
        msg = f"Your last known position on EDSM: {data['system']}."
        if data.get("date"):
            msg += f" Recorded at {data['date']}."
        speaker.say(msg)
        return True
    speaker.say("Could not retrieve position from EDSM.")
    return False
