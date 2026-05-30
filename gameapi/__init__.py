"""
gameapi — Elite Dangerous game state integration.

Provides real-time game state awareness by reading Elite Dangerous output files:
- Journal log tailing (events like FSDJump, Docked, etc.)
- Status.json polling (ship flags, pips, GUI focus)
- .binds XML parsing (player's actual keybindings)
"""

from gameapi.game_state import GameState
from gameapi.binds_parser import parse_binds, find_binds_file

__all__ = ["GameState", "parse_binds", "find_binds_file"]
