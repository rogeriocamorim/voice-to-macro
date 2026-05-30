"""
handlers — Compound action handlers for Elite Dangerous.

Each handler implements a complex multi-step action that may involve:
- API calls (EDSM, Spansh)
- Game state queries
- Multi-step keystroke sequences
- TTS responses
"""

from __future__ import annotations
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from gameapi.game_state import GameState
    from gameapi.binds_parser import KeyBinding
    from search.edsm import EDSMClient
    from search.spansh import SpanshClient
    from tts.speaker import Speaker

from handlers import navigate_to
from handlers import system_info
from handlers import find_commodity
from handlers import monetize_route
from handlers import trade_route
from handlers import commander_status


# Handler registry: compound action name -> handler function
HANDLERS: dict[str, Any] = {
    "navigate_to": navigate_to.handle,
    "system_info": system_info.handle,
    "scan_value": system_info.handle_scan_value,
    "danger_check": system_info.handle_danger,
    "nearby_systems": system_info.handle_nearby,
    "find_commodity": find_commodity.handle,
    "monetize_route": monetize_route.handle,
    "trade_route": trade_route.handle,
    "commander_status": commander_status.handle,
    "server_status": system_info.handle_server_status,
}


def dispatch_compound(
    action: str,
    params: dict,
    game_state: Any,
    config: dict,
    speaker: Any,
    binds: dict,
    edsm: Any,
    spansh: Any,
) -> bool:
    """
    Dispatch a compound action to its handler.

    Returns True if handled successfully, False otherwise.
    """
    handler = HANDLERS.get(action)
    if not handler:
        print(f"[HANDLERS] No handler found for compound action: {action}")
        return False

    try:
        return handler(params, game_state, config, speaker, binds, edsm, spansh)
    except Exception as e:
        print(f"[HANDLERS] Error in handler '{action}': {e}")
        speaker.say(f"Error executing {action.replace('_', ' ')}. Check the log.")
        return False


# ---------------------------------------------------------------------------
# Shared utility functions used across handlers
# ---------------------------------------------------------------------------

def format_credits(amount: int) -> str:
    """Format credits for TTS: 1234567 -> '1.2 million credits'"""
    if amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f} billion credits"
    elif amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f} million credits"
    elif amount >= 1_000:
        return f"{amount / 1_000:.0f} thousand credits"
    return f"{amount} credits"


def format_population(pop: int) -> str:
    """Format population for TTS."""
    if pop >= 1_000_000_000:
        return f"{pop / 1_000_000_000:.1f} billion"
    elif pop >= 1_000_000:
        return f"{pop / 1_000_000:.1f} million"
    elif pop >= 1_000:
        return f"{pop / 1_000:.0f} thousand"
    return str(pop)
