"""
tts/speaker.py — Text-to-speech with personality support.

Uses pyttsx3 for fully offline, zero-latency speech output.
Supports two personality modes:
  - generic:    plain, concise confirmations
  - game_themed: uses the profile's personality string as a character voice prefix
"""

from __future__ import annotations
import random
from typing import Any, Optional

import pyttsx3  # type: ignore


# Generic confirmation phrases — used when personality == 'generic'
_GENERIC_CONFIRMATIONS = [
    "Executing.",
    "Done.",
    "Command received.",
    "Confirmed.",
    "On it.",
]

# Generic unknown phrases
_GENERIC_UNKNOWN = [
    "Command not recognized.",
    "Say help for available commands.",
    "Unknown command.",
]


class Speaker:
    """
    Text-to-speech speaker with personality awareness.

    Parameters
    ----------
    personality : str
        'generic' or 'game_themed'
    profile : dict
        Active game profile. Used to extract personality description.
    rate : int
        Speech rate (words per minute). Default 175.
    volume : float
        Volume level (0.0–1.0). Default 0.9.
    """

    def __init__(
        self,
        personality: str = "generic",
        profile: Optional[dict[str, Any]] = None,
        rate: int = 175,
        volume: float = 0.9,
    ):
        self.personality = personality
        self.profile = profile or {}
        self._engine = pyttsx3.init()
        self._engine.setProperty("rate", rate)
        self._engine.setProperty("volume", volume)

    def say(self, text: str) -> None:
        """Speak text immediately (blocking)."""
        print(f"[TTS] {text}")
        self._engine.say(text)
        self._engine.runAndWait()

    def confirm(self, action_name: str) -> None:
        """
        Speak a confirmation for a successfully executed action.

        In game_themed mode, uses the profile personality for context.
        In generic mode, uses a random short confirmation.
        """
        display = action_name.replace("_", " ")

        if self.personality == "game_themed":
            # Use personality prefix from profile if available
            persona = self.profile.get("personality", "")
            phrases = [
                f"{display}, aye.",
                f"Executing {display}.",
                f"{display} confirmed.",
                f"Copy that. {display}.",
            ]
            self.say(random.choice(phrases))
        else:
            self.say(random.choice(_GENERIC_CONFIRMATIONS))

    def unknown(self) -> None:
        """Speak a generic 'unknown command' message."""
        self.say(random.choice(_GENERIC_UNKNOWN))

    def help(self, profile: dict[str, Any]) -> None:
        """Read out available commands from the profile."""
        actions = profile.get("actions", {})
        if not actions:
            self.say("No actions available in the current profile.")
            return
        names = ", ".join(a.replace("_", " ") for a in actions.keys())
        self.say(f"Available commands: {names}")

    def update_profile(self, profile: dict[str, Any]) -> None:
        """Update the active profile reference (e.g. on profile switch)."""
        self.profile = profile
