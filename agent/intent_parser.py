"""
agent/intent_parser.py — LLM-based intent classification via Ollama.

Supports two response modes:
- Simple actions: returns a plain action name (existing behavior)
- Compound actions: returns JSON {"action": "name", "params": {...}}

The model is kept minimal — just classification, no reasoning.
"""

from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from typing import Any

import ollama  # type: ignore
from thefuzz import fuzz  # type: ignore

from agent.context_builder import build_prompt


# Normalize LLM output: strip whitespace/punctuation, lowercase
_CLEAN_RE = re.compile(r"[^a-z0-9_ ]")

# Minimum fuzzy score (0-100) to accept a description match without LLM
_DESCRIPTION_MATCH_THRESHOLD = 72


@dataclass
class ParsedIntent:
    """Result of intent classification."""
    action: str
    confidence: float
    params: dict = field(default_factory=dict)
    is_compound: bool = False


def _clean(text: str) -> str:
    return _CLEAN_RE.sub("", text.strip().lower()).strip()


def parse_intent(
    transcript: str,
    profile: dict[str, Any],
    model: str = "phi3:mini",
    game_state: Any = None,
) -> ParsedIntent:
    """
    Classify a voice transcript into an action using a local LLM.

    Parameters
    ----------
    transcript : str
        Raw STT output (lowercased).
    profile : dict
        Active game profile dict.
    model : str
        Ollama model name.
    game_state : GameState, optional
        Current game state for context.

    Returns
    -------
    ParsedIntent
        Classified action with confidence and optional params.
    """
    if not transcript.strip():
        return ParsedIntent("unknown", 0.0)

    actions = profile.get("actions", {})
    compound_actions = profile.get("compound_actions", {})
    all_action_keys = set(actions.keys()) | set(compound_actions.keys())

    # --- Fast-path: fuzzy match against action descriptions ---
    t_lower = transcript.lower().strip()
    best_action, best_score = None, 0
    is_best_compound = False

    for action_name, action_data in actions.items():
        description = action_data.get("description", "").lower()
        score = max(
            fuzz.token_set_ratio(t_lower, description),
            fuzz.partial_ratio(t_lower, description),
        )
        if score > best_score:
            best_score = score
            best_action = action_name
            is_best_compound = False

    for action_name, action_data in compound_actions.items():
        description = action_data.get("description", "").lower()
        score = max(
            fuzz.token_set_ratio(t_lower, description),
            fuzz.partial_ratio(t_lower, description),
        )
        if score > best_score:
            best_score = score
            best_action = action_name
            is_best_compound = True

    # Only use fuzzy match for simple actions (compound need params from LLM)
    if best_score >= _DESCRIPTION_MATCH_THRESHOLD and best_action and not is_best_compound:
        confidence = round(best_score / 100, 2)
        print(f"[AGENT] Description match: '{best_action}' (score={best_score})")
        return ParsedIntent(best_action, confidence)

    # --- LLM classification (Ollama) ---
    prompt = build_prompt(transcript, profile, game_state)

    try:
        response = ollama.generate(
            model=model,
            prompt=prompt,
            options={
                "temperature": 0.0,   # deterministic — classification only
                "num_predict": 60,    # slightly more tokens for JSON responses
                "stop": ["\n\n"],
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
        return ParsedIntent("unknown", 0.0)

    # --- Try JSON parse first (compound action) ---
    json_result = _try_parse_json(raw, compound_actions)
    if json_result:
        return json_result

    # --- Plain text matching (simple action) ---
    cleaned = _clean(raw)

    # Exact match
    if cleaned in all_action_keys:
        is_compound = cleaned in compound_actions
        return ParsedIntent(cleaned, 1.0, is_compound=is_compound)

    # Partial match (LLM returned "fsd jump" for "fsd_jump")
    normalized_actions = {a.replace("_", " "): a for a in all_action_keys}
    if cleaned in normalized_actions:
        action = normalized_actions[cleaned]
        is_compound = action in compound_actions
        return ParsedIntent(action, 0.9, is_compound=is_compound)

    # Fuzzy fallback — check if LLM response contains a known action
    for display, original in normalized_actions.items():
        if display in cleaned or cleaned in display:
            is_compound = original in compound_actions
            return ParsedIntent(original, 0.7, is_compound=is_compound)

    return ParsedIntent("unknown", 0.0)


def _try_parse_json(raw: str, compound_actions: dict) -> ParsedIntent | None:
    """
    Attempt to parse LLM output as JSON for compound actions.
    Returns ParsedIntent if valid, None otherwise.
    """
    # Try to find JSON in the response (LLM may add text around it)
    raw = raw.strip()

    # Direct JSON parse
    try:
        data = json.loads(raw)
        if isinstance(data, dict) and "action" in data:
            action = data["action"]
            params = data.get("params", {})
            if action in compound_actions:
                return ParsedIntent(action, 1.0, params=params, is_compound=True)
    except json.JSONDecodeError:
        pass

    # Try extracting JSON from surrounding text
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start:end])
            if isinstance(data, dict) and "action" in data:
                action = data["action"]
                params = data.get("params", {})
                if action in compound_actions:
                    return ParsedIntent(action, 0.9, params=params, is_compound=True)
        except json.JSONDecodeError:
            pass

    return None
