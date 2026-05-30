"""
agent/context_builder.py — Assembles the LLM classification prompt.

Combines the active game profile's action list with any previously
learned command mappings, then wraps the transcript into a tightly
scoped classification prompt for the LLM.

Supports two response modes:
- Simple actions: LLM returns just an action name
- Compound actions: LLM returns JSON {"action": "name", "params": {...}}
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any


LEARNED_COMMANDS_PATH = Path(__file__).parent.parent / "learned_commands.json"


def _load_learned_commands() -> dict[str, Any]:
    if LEARNED_COMMANDS_PATH.exists():
        try:
            with open(LEARNED_COMMANDS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def build_prompt(
    transcript: str,
    profile: dict[str, Any],
    game_state: Any = None,
) -> str:
    """
    Build a classification prompt for the LLM.

    When compound_actions are defined in the profile, the prompt instructs
    the LLM to return JSON for parameterized commands. Otherwise falls back
    to the simple action-name-only format.

    Parameters
    ----------
    transcript : str
        The raw STT output (lowercased).
    profile : dict
        The loaded game profile dict (from profiles/*.json).
    game_state : GameState, optional
        Current game state for context injection.

    Returns
    -------
    str
        The fully assembled prompt string.
    """
    actions = profile.get("actions", {})
    compound_actions = profile.get("compound_actions", {})
    game = profile.get("game", "a PC game")

    # --- Game state context ---
    state_block = ""
    if game_state:
        try:
            summary = game_state.get_status_summary()
            state_block = (
                f"\nCurrent game state:\n"
                f"  System: {summary.get('system', 'Unknown')}\n"
                f"  Station: {summary.get('station', 'Not docked')}\n"
                f"  Docked: {'Yes' if summary.get('docked') else 'No'}\n"
                f"  Supercruise: {'Yes' if summary.get('supercruise') else 'No'}\n"
                f"  Fuel: {summary.get('fuel', 'Unknown')} tons\n"
            )
            if summary.get("destination"):
                state_block += f"  Destination: {summary['destination']}\n"
            if summary.get("in_danger"):
                state_block += "  WARNING: In danger!\n"
        except Exception:
            pass

    # --- Simple actions list ---
    action_lines = "\n".join(
        f"- {name}: {meta.get('description', name)}"
        for name, meta in actions.items()
    )

    # --- Compound actions list ---
    compound_lines = ""
    if compound_actions:
        compound_lines = "\n\nAvailable compound actions (reply with JSON):\n"
        compound_lines += "\n".join(
            f"- {name}: {meta.get('description', name)}. Params: {meta.get('params_hint', 'none')}"
            for name, meta in compound_actions.items()
        )

    # --- Learned commands ---
    learned = _load_learned_commands()
    learned_lines = ""
    all_known_actions = set(actions.keys()) | set(compound_actions.keys())
    confirmed = {
        phrase: data
        for phrase, data in learned.items()
        if data.get("confirmed") and data.get("intent") in all_known_actions
    }
    if confirmed:
        examples = "\n".join(
            f'  "{phrase}" -> {data["intent"]}'
            for phrase, data in list(confirmed.items())[:10]
        )
        learned_lines = f"\nKnown user phrases (use as hints):\n{examples}\n"

    # --- Build prompt ---
    if compound_actions:
        # Full prompt with compound action support
        prompt = (
            f"You are a voice command classifier for {game}.\n"
            f"Match the user's spoken phrase to one action from the lists below.\n"
            f"{state_block}"
            f"\nAvailable simple actions (reply with ONLY the action name):\n{action_lines}\n"
            f"{compound_lines}\n"
            f"\nRules:\n"
            f"- For simple actions: reply with ONLY the exact action name.\n"
            f"- For compound actions: reply with JSON: {{\"action\": \"name\", \"params\": {{...}}}}\n"
            f"- If nothing fits: reply with unknown\n"
            f"- Do NOT explain. Do NOT add extra text.\n"
            f"{learned_lines}"
            f"\nUser said: \"{transcript}\"\n"
            f"Action:"
        )
    else:
        # Legacy simple-only prompt (no compound actions in profile)
        prompt = (
            f"You are a voice command classifier for {game}.\n"
            f"Your ONLY job is to match the user's spoken phrase to one action from the list below.\n"
            f"Reply with ONLY the exact action name from the list, or 'unknown' if nothing fits.\n"
            f"Do NOT explain. Do NOT add punctuation. Do NOT make up action names.\n"
            f"{state_block}"
            f"\nAvailable actions:\n{action_lines}\n"
            f"{learned_lines}"
            f"\nUser said: \"{transcript}\"\n"
            f"Action:"
        )

    return prompt
