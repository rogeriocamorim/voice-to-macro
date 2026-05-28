"""
agent/context_builder.py — Assembles the LLM classification prompt.

Combines the active game profile's action list with any previously
learned command mappings, then wraps the transcript into a tightly
scoped classification prompt for the LLM.
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


def build_prompt(transcript: str, profile: dict[str, Any]) -> str:
    """
    Build a minimal classification prompt for the LLM.

    The prompt instructs the model to return ONLY the action name
    (from the profile) that best matches the transcript, or 'unknown'
    if nothing fits. No explanations, no conversation.

    Parameters
    ----------
    transcript : str
        The raw STT output (lowercased).
    profile : dict
        The loaded game profile dict (from profiles/*.json).

    Returns
    -------
    str
        The fully assembled prompt string.
    """
    actions = profile.get("actions", {})
    game = profile.get("game", "a PC game")

    # Build action list: "action_name — description"
    action_lines = "\n".join(
        f"- {name}: {meta.get('description', name)}"
        for name, meta in actions.items()
    )

    # Inject confirmed learned mappings as examples
    learned = _load_learned_commands()
    learned_lines = ""
    confirmed = {
        phrase: data
        for phrase, data in learned.items()
        if data.get("confirmed") and data.get("intent") in actions
    }
    if confirmed:
        examples = "\n".join(
            f'  "{phrase}" → {data["intent"]}'
            for phrase, data in list(confirmed.items())[:10]  # cap at 10 examples
        )
        learned_lines = f"\nKnown user phrases (use as hints):\n{examples}\n"

    prompt = (
        f"You are a voice command classifier for {game}.\n"
        f"Your ONLY job is to match the user's spoken phrase to one action from the list below.\n"
        f"Reply with ONLY the exact action name from the list, or 'unknown' if nothing fits.\n"
        f"Do NOT explain. Do NOT add punctuation. Do NOT make up action names.\n"
        f"\nAvailable actions:\n{action_lines}\n"
        f"{learned_lines}"
        f"\nUser said: \"{transcript}\"\n"
        f"Action:"
    )
    return prompt
