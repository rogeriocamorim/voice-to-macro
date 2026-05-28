"""
agent/intent_parser.py — LLM-based intent classification via Ollama.

Sends a minimal classification prompt to a local Ollama model and
returns the matched action name plus a confidence score.

The model only needs to return a single action name — it is not asked
to reason, explain, or generate text. This keeps latency very low.
"""

from __future__ import annotations
import re
from typing import Any

import ollama  # type: ignore

from agent.context_builder import build_prompt


# Normalize LLM output: strip whitespace/punctuation, lowercase
_CLEAN_RE = re.compile(r"[^a-z0-9_ ]")


def _clean(text: str) -> str:
    return _CLEAN_RE.sub("", text.strip().lower()).strip()


def parse_intent(
    transcript: str,
    profile: dict[str, Any],
    model: str = "phi3:mini",
) -> tuple[str, float]:
    """
    Classify a voice transcript into an action name using a local LLM.

    Parameters
    ----------
    transcript : str
        Raw STT output (lowercased).
    profile : dict
        Active game profile dict.
    model : str
        Ollama model name.

    Returns
    -------
    tuple[str, float]
        (action_name, confidence)
        - action_name: key from profile["actions"], or "unknown"
        - confidence: 1.0 if exact match, 0.5 if partial, 0.0 if unknown
    """
    if not transcript.strip():
        return "unknown", 0.0

    actions = set(profile.get("actions", {}).keys())
    prompt = build_prompt(transcript, profile)

    try:
        response = ollama.generate(
            model=model,
            prompt=prompt,
            options={
                "temperature": 0.0,   # deterministic — classification only
                "num_predict": 20,    # we only need a few tokens
                "stop": ["\n", ".", ","],
            },
        )
        raw = response.get("response", "").strip()
    except Exception as e:
        err = str(e)
        if "connection" in err.lower() or "refused" in err.lower() or "timeout" in err.lower():
            print("[AGENT] Cannot reach Ollama server. Is it running?")
            print("        Fix: launch the Ollama app or run: ollama serve")
        elif "not found" in err.lower() or "no such" in err.lower():
            print(f"[AGENT] Model not found. Pull it with: ollama pull {model}")
        else:
            print(f"[AGENT] Ollama error: {e}")
        return "unknown", 0.0

    cleaned = _clean(raw)

    # Exact match
    if cleaned in actions:
        return cleaned, 1.0

    # Partial match (LLM returned something like "fsd jump" for "fsd_jump")
    normalized_actions = {a.replace("_", " "): a for a in actions}
    if cleaned in normalized_actions:
        return normalized_actions[cleaned], 0.9

    # Fuzzy fallback — check if LLM response starts with or contains a known action
    for display, original in normalized_actions.items():
        if display in cleaned or cleaned in display:
            return original, 0.7

    return "unknown", 0.0
