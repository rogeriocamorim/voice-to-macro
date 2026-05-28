"""
tts/speaker.py — Text-to-speech with natural neural voices via edge-tts.

Primary engine : edge-tts (Microsoft neural voices — free, internet required)
Fallback engine: pyttsx3 (offline SAPI — used if edge-tts fails or no internet)

Voice is selected automatically based on the active game profile:
  - Elite Dangerous / Star Citizen → en-GB-RyanNeural (calm male co-pilot)
  - Generic                        → en-US-AriaNeural (clear female assistant)

Can be overridden in config.yaml:  tts_voice: "en-US-GuyNeural"

Available neural voices (a selection):
  Female: en-US-AriaNeural, en-US-JennyNeural, en-GB-SoniaNeural
  Male  : en-US-GuyNeural,  en-GB-RyanNeural,  en-AU-WilliamNeural
"""

from __future__ import annotations
import asyncio
import io
import random
import tempfile
import threading
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Voice mapping — profile game name → neural voice
# ---------------------------------------------------------------------------

_GAME_VOICE_MAP: dict[str, str] = {
    "Elite Dangerous": "en-GB-RyanNeural",
    "Star Citizen":    "en-GB-RyanNeural",
    "Generic":         "en-US-AriaNeural",
}

_DEFAULT_VOICE = "en-US-AriaNeural"

# Confirmation phrases per personality
_GENERIC_CONFIRMATIONS = [
    "Executing.",
    "Done.",
    "Command received.",
    "Confirmed.",
    "On it.",
]

_GAME_CONFIRMATIONS = [
    "{display}, aye.",
    "Executing {display}.",
    "{display} confirmed.",
    "Copy that. {display}.",
    "Roger. {display}.",
]

_GENERIC_UNKNOWN = [
    "Command not recognized.",
    "Unknown command.",
    "Say help for available commands.",
]


# ---------------------------------------------------------------------------
# edge-tts async helper
# ---------------------------------------------------------------------------

def _speak_edge(text: str, voice: str) -> bool:
    """
    Speak text using edge-tts. Returns True on success, False on failure.
    Plays audio via sounddevice so it works without a system media player.
    """
    try:
        import edge_tts        # type: ignore
        import sounddevice as sd  # type: ignore
        import soundfile as sf  # type: ignore
        import numpy as np

        async def _generate() -> bytes:
            communicate = edge_tts.Communicate(text, voice)
            audio_chunks = []
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_chunks.append(chunk["data"])
            return b"".join(audio_chunks)

        mp3_bytes = asyncio.run(_generate())
        if not mp3_bytes:
            return False

        # Write to temp file and read back as numpy array for playback
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            tmp.write(mp3_bytes)
            tmp_path = tmp.name

        try:
            data, samplerate = sf.read(tmp_path, dtype="float32")
            sd.play(data, samplerate)
            sd.wait()
        finally:
            Path(tmp_path).unlink(missing_ok=True)

        return True

    except Exception as e:
        # Common causes: no internet, edge-tts not installed, soundfile missing
        print(f"[TTS] edge-tts failed ({type(e).__name__}: {e}) — falling back to pyttsx3")
        return False


def _speak_pyttsx3(text: str) -> None:
    """Offline fallback using pyttsx3 / Windows SAPI."""
    try:
        import pyttsx3  # type: ignore
        engine = pyttsx3.init()
        engine.setProperty("rate", 175)
        engine.setProperty("volume", 0.9)
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print(f"[TTS] pyttsx3 also failed: {e}")


# ---------------------------------------------------------------------------
# Speaker class
# ---------------------------------------------------------------------------

class Speaker:
    """
    Text-to-speech speaker with neural voice support.

    Parameters
    ----------
    personality : str
        'generic' or 'game_themed'
    profile : dict
        Active game profile. Used to select the appropriate voice.
    voice_override : str, optional
        Force a specific edge-tts voice name (e.g. 'en-US-GuyNeural').
        Overrides the automatic game-based voice selection.
    """

    def __init__(
        self,
        personality: str = "generic",
        profile: Optional[dict[str, Any]] = None,
        voice_override: Optional[str] = None,
    ):
        self.personality = personality
        self.profile = profile or {}
        self._voice_override = voice_override
        self._edge_available: Optional[bool] = None  # lazy check

    @property
    def _voice(self) -> str:
        if self._voice_override:
            return self._voice_override
        game = self.profile.get("game", "Generic")
        return _GAME_VOICE_MAP.get(game, _DEFAULT_VOICE)

    def _check_edge(self) -> bool:
        """Lazy check — try edge-tts once, cache the result."""
        if self._edge_available is None:
            try:
                import edge_tts  # type: ignore
                import soundfile  # type: ignore
                self._edge_available = True
            except ImportError:
                self._edge_available = False
                print("[TTS] edge-tts or soundfile not installed — using pyttsx3.")
                print("      For better voices: pip install edge-tts soundfile")
        return self._edge_available

    def say(self, text: str) -> None:
        """Speak text immediately (blocking). Tries edge-tts first, falls back to pyttsx3."""
        print(f"[TTS] {text}")
        if self._check_edge():
            success = _speak_edge(text, self._voice)
            if success:
                return
            # Mark edge as unavailable for this session so we stop retrying
            self._edge_available = False
        _speak_pyttsx3(text)

    def confirm(self, action_name: str) -> None:
        """Speak a confirmation for a successfully executed action."""
        display = action_name.replace("_", " ")
        if self.personality == "game_themed":
            template = random.choice(_GAME_CONFIRMATIONS)
            self.say(template.format(display=display))
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
        """Update the active profile — resets voice selection."""
        self.profile = profile
        self._edge_available = None  # re-check on next say()
