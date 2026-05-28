"""
learning/command_store.py — Self-learning command persistence.

Stores transcript → intent → action mappings in learned_commands.json.
Supports:
  - Saving new mappings (confirmed or unconfirmed)
  - Looking up known mappings for fast-path matching
  - CLI --review mode to approve/reject pending entries
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any, Optional


STORE_PATH = Path(__file__).parent.parent / "learned_commands.json"


# ---------------------------------------------------------------------------
# Core read/write
# ---------------------------------------------------------------------------

def _load() -> dict[str, Any]:
    if STORE_PATH.exists():
        try:
            with open(STORE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save(data: dict[str, Any]) -> None:
    with open(STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def save_mapping(
    transcript: str,
    intent: str,
    action_key: str,
    confirmed: bool = False,
) -> None:
    """
    Save a transcript → intent → action mapping.

    Parameters
    ----------
    transcript : str
        The raw STT phrase (lowercased).
    intent : str
        The action name from the profile.
    action_key : str
        Same as intent (kept separate for future extensibility).
    confirmed : bool
        True if user explicitly confirmed the mapping.
        False if the LLM guessed it (pending confirmation).
    """
    data = _load()
    data[transcript.strip().lower()] = {
        "intent": intent,
        "action": action_key,
        "confirmed": confirmed,
        "uses": data.get(transcript, {}).get("uses", 0) + 1,
    }
    _save(data)


def lookup(transcript: str) -> Optional[dict[str, Any]]:
    """
    Look up a transcript in the learned store.

    Returns the mapping dict if found and confirmed, else None.
    """
    data = _load()
    entry = data.get(transcript.strip().lower())
    if entry and entry.get("confirmed"):
        return entry
    return None


def increment_uses(transcript: str) -> None:
    """Increment the use counter for a learned mapping."""
    data = _load()
    key = transcript.strip().lower()
    if key in data:
        data[key]["uses"] = data[key].get("uses", 0) + 1
        # Auto-confirm after 3 successful uses
        if data[key]["uses"] >= 3 and not data[key].get("confirmed"):
            data[key]["confirmed"] = True
            print(f"[LEARN] Auto-confirmed mapping: '{key}' → {data[key]['intent']}")
        _save(data)


def get_all() -> dict[str, Any]:
    """Return all stored mappings."""
    return _load()


def get_pending() -> dict[str, Any]:
    """Return only unconfirmed mappings."""
    data = _load()
    return {k: v for k, v in data.items() if not v.get("confirmed")}


def confirm(transcript: str) -> bool:
    """Mark a mapping as confirmed. Returns True if it existed."""
    data = _load()
    key = transcript.strip().lower()
    if key in data:
        data[key]["confirmed"] = True
        _save(data)
        return True
    return False


def reject(transcript: str) -> bool:
    """Remove a mapping from the store. Returns True if it existed."""
    data = _load()
    key = transcript.strip().lower()
    if key in data:
        del data[key]
        _save(data)
        return True
    return False


# ---------------------------------------------------------------------------
# CLI review mode
# ---------------------------------------------------------------------------

def review_interactive() -> None:
    """
    Interactive CLI to approve or reject pending (unconfirmed) mappings.
    Called when user runs: python main.py --review
    """
    pending = get_pending()

    if not pending:
        print("No pending learned commands to review.")
        return

    print(f"\n{'='*55}")
    print(f"  Learned Command Review ({len(pending)} pending)")
    print(f"{'='*55}")
    print("  For each entry: [y] confirm  [n] reject  [s] skip\n")

    for phrase, data in pending.items():
        print(f"  Phrase : \"{phrase}\"")
        print(f"  Maps to: {data['intent']}  (used {data.get('uses', 0)} time(s))")
        choice = input("  Action [y/n/s]: ").strip().lower()

        if choice == "y":
            confirm(phrase)
            print(f"  Confirmed.\n")
        elif choice == "n":
            reject(phrase)
            print(f"  Rejected and removed.\n")
        else:
            print(f"  Skipped.\n")

    print("Review complete.")
