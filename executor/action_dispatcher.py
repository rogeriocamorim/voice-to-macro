"""
executor/action_dispatcher.py — Executes game actions via keyboard/mouse.

Supports four action types defined in profile JSON:
  - key:      single keypress
  - combo:    simultaneous key combination
  - hold:     key held for a duration
  - sequence: ordered list of steps (key/combo/hold/delay)

All input is delivered via pyautogui (keyboard) and pynput (fallback).
"""

from __future__ import annotations
import time
from typing import Any

import pyautogui  # type: ignore

# Disable the pyautogui fail-safe (moving mouse to corner stops it)
# since users may move the mouse during gameplay.
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.0  # no inter-call sleep; we handle delays ourselves


# ---------------------------------------------------------------------------
# Internal step executors
# ---------------------------------------------------------------------------

def _press_key(key: str) -> None:
    """Single keypress (down + up)."""
    pyautogui.press(key)


def _press_combo(keys: list[str]) -> None:
    """Simultaneous key combination (hotkey)."""
    pyautogui.hotkey(*keys)


def _hold_key(key: str, duration_ms: int) -> None:
    """Hold a key down for a given duration, then release."""
    pyautogui.keyDown(key)
    time.sleep(duration_ms / 1000.0)
    pyautogui.keyUp(key)


def _execute_step(step: dict[str, Any]) -> None:
    """
    Execute a single step inside a sequence.

    Step formats:
      { "key": "j" }
      { "key": "j", "hold_ms": 500 }
      { "combo": ["ctrl", "shift", "g"] }
      { "delay_ms": 200 }
    """
    if "delay_ms" in step:
        time.sleep(step["delay_ms"] / 1000.0)
        return

    if "combo" in step:
        _press_combo(step["combo"])
        return

    if "key" in step:
        hold_ms = step.get("hold_ms", 0)
        if hold_ms > 0:
            _hold_key(step["key"], hold_ms)
        else:
            _press_key(step["key"])
        return

    print(f"[EXECUTOR] Unknown step format: {step}")


# ---------------------------------------------------------------------------
# Public dispatcher
# ---------------------------------------------------------------------------

def dispatch(action_def: dict[str, Any]) -> None:
    """
    Execute an action from a game profile.

    Parameters
    ----------
    action_def : dict
        The 'action' field from a profile action entry. Examples:

        { "type": "key", "key": "j" }
        { "type": "combo", "keys": ["shift", "s"] }
        { "type": "hold", "key": "w", "duration_ms": 1000 }
        { "type": "sequence", "steps": [
            { "key": "j" },
            { "delay_ms": 300 },
            { "combo": ["ctrl", "alt", "f"] }
        ]}

    Raises
    ------
    ValueError
        If the action type is not recognised.
    """
    action_type = action_def.get("type", "key")

    if action_type == "key":
        _press_key(action_def["key"])

    elif action_type == "combo":
        _press_combo(action_def["keys"])

    elif action_type == "hold":
        _hold_key(action_def["key"], action_def.get("duration_ms", 500))

    elif action_type == "sequence":
        for step in action_def.get("steps", []):
            _execute_step(step)

    else:
        raise ValueError(f"[EXECUTOR] Unknown action type: '{action_type}'")


def dispatch_profile_action(action_name: str, profile: dict[str, Any]) -> bool:
    """
    Look up action_name in profile and dispatch it.

    Parameters
    ----------
    action_name : str
        Key in profile["actions"].
    profile : dict
        Active game profile dict.

    Returns
    -------
    bool
        True if dispatched successfully, False if action not found.
    """
    actions = profile.get("actions", {})
    if action_name not in actions:
        print(f"[EXECUTOR] Action '{action_name}' not found in profile.")
        return False

    action_def = actions[action_name].get("action")
    if action_def is None:
        print(f"[EXECUTOR] Action '{action_name}' has no 'action' definition.")
        return False

    try:
        dispatch(action_def)
        return True
    except Exception as e:
        print(f"[EXECUTOR] Error executing '{action_name}': {e}")
        return False
