"""
agent/feedback.py — Clarification loop (Option B).

When the LLM returns 'unknown' or low confidence, this module:
1. Fuzzy-matches the transcript against available action descriptions
2. Picks the top 2 closest candidates
3. Uses TTS to ask "Did you mean X or Y?"
4. Listens for the user's voice reply
5. Returns the confirmed action name, or None if not resolved

The confirmed mapping is then saved to learned_commands.json by the caller.
"""

from __future__ import annotations
from typing import Any, Optional

from thefuzz import fuzz  # type: ignore


def _score_action(transcript: str, action_name: str, description: str) -> int:
    """
    Score how well a transcript matches an action.
    Uses both the action name and its description for matching.
    """
    name_score = fuzz.partial_ratio(transcript, action_name.replace("_", " "))
    desc_score = fuzz.partial_ratio(transcript, description.lower())
    return max(name_score, desc_score)


def find_closest_actions(
    transcript: str,
    profile: dict[str, Any],
    top_n: int = 2,
    min_score: int = 40,
) -> list[tuple[str, int]]:
    """
    Return the top N closest action names to the transcript.

    Returns
    -------
    list of (action_name, score) sorted by score descending.
    Empty list if nothing scores above min_score.
    """
    actions = profile.get("actions", {})
    scored = []
    for name, meta in actions.items():
        description = meta.get("description", name)
        score = _score_action(transcript, name, description)
        scored.append((name, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    filtered = [(name, score) for name, score in scored if score >= min_score]
    return filtered[:top_n]


def clarify(
    transcript: str,
    profile: dict[str, Any],
    speaker: Any,          # tts.speaker.Speaker instance
    recorder: Any,         # vad.silero_vad.PTTRecorder or callable → np.ndarray
    stt: Any,              # stt.whisper_stt.WhisperSTT instance
    ptt_mode: bool = True,
) -> Optional[str]:
    """
    Run the clarification loop.

    Asks the user which of the top 2 matching actions they meant,
    listens for a reply, and returns the confirmed action name.

    Parameters
    ----------
    transcript : str
        The original transcript that was not understood.
    profile : dict
        Active game profile.
    speaker : Speaker
        TTS speaker instance.
    recorder : PTTRecorder or None
        Used to capture the user's clarification reply (PTT mode).
    stt : WhisperSTT
        Used to transcribe the clarification reply.
    ptt_mode : bool
        If True, wait for PTT hold. If False, use a short fixed recording.

    Returns
    -------
    str or None
        Confirmed action name, or None if not resolved.
    """
    candidates = find_closest_actions(transcript, profile)

    if not candidates:
        speaker.say("Command not recognized. Say help for available commands.")
        return None

    # Build question
    action_names = [name.replace("_", " ") for name, _ in candidates]
    if len(action_names) == 1:
        question = f"Didn't catch that. Did you mean {action_names[0]}?"
    else:
        question = f"Didn't catch that. Did you mean {action_names[0]} or {action_names[1]}?"

    speaker.say(question)

    # Listen for reply
    if ptt_mode and recorder is not None:
        import numpy as np
        audio = recorder.record()
    else:
        # Short fixed recording (2 seconds) for always-on fallback
        import sounddevice as sd  # type: ignore
        import numpy as np
        audio = sd.rec(int(2 * 16000), samplerate=16000, channels=1, dtype="float32")
        sd.wait()
        audio = audio[:, 0]

    if audio is None or len(audio) == 0:
        speaker.say("No response heard. Cancelling.")
        return None

    reply = stt.transcribe(audio).strip().lower()
    print(f"[FEEDBACK] User replied: '{reply}'")

    # Match reply to one of the candidates
    actions = profile.get("actions", {})
    for name, _ in candidates:
        display = name.replace("_", " ")
        if display in reply or reply in display:
            speaker.say(f"Got it. Executing {display}.")
            return name

    # Check if reply contains any known action name directly
    for action_name in actions:
        if action_name.replace("_", " ") in reply:
            speaker.say(f"Got it. Executing {action_name.replace('_', ' ')}.")
            return action_name

    # User said "neither", "no", "cancel", etc.
    if any(word in reply for word in ("neither", "no", "cancel", "never mind", "stop")):
        speaker.say("Understood. Command cancelled.")
        return None

    speaker.say("Could not confirm. Command cancelled.")
    return None
