"""
executor/action_dispatcher.py — Executes game actions via keyboard/mouse.

Supports four action types defined in profile JSON:
  - key:      single keypress
  - combo:    simultaneous key combination
  - hold:     key held for a duration
  - sequence: ordered list of steps (key/combo/hold/delay)

Also supports bind-aware dispatch for Elite Dangerous: uses the player's
real keybindings from their .binds file, falling back to profile definitions.

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
# Profile action name -> .binds action name mapping (Elite Dangerous)
# ---------------------------------------------------------------------------

PROFILE_TO_BINDS: dict[str, str] = {
    "fsd_jump": "Hyperspace",
    "supercruise": "Supercruise",
    "boost": "UseBoostJuice",
    "landing_gear": "LandingGearToggle",
    "silent_running": "ToggleButtonUpInput",
    "hardpoints": "DeployHardpointToggle",
    "throttle_zero": "SetSpeedZero",
    "throttle_full": "SetSpeed100",
    "cargo_scoop": "ToggleCargoScoop",
    "galaxy_map": "GalaxyMapOpen",
    "system_map": "SystemMapOpen",
    "next_target": "SelectTarget",
    "night_vision": "NightVisionToggle",
    "lights": "ShipSpotLightToggle",
    "request_docking": "FocusCommsPanel",
    "power_weapons": "IncreaseWeaponsPower",
    "power_engines": "IncreaseEnginesPower",
    "shields": "IncreaseSystemsPower",
    "fire_weapons": "PrimaryFire",
}


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
# Bind-aware dispatch (Elite Dangerous)
# ---------------------------------------------------------------------------

def dispatch_from_binds(binds_action_name: str, binds: dict) -> bool:
    """
    Dispatch using the player's real keybindings from .binds file.

    Parameters
    ----------
    binds_action_name : str
        The Elite Dangerous action name (e.g. "Hyperspace", "GalaxyMapOpen").
    binds : dict
        Parsed keybindings dict: {action_name: KeyBinding}.

    Returns
    -------
    bool
        True if binding found and executed, False otherwise.
    """
    binding = binds.get(binds_action_name)
    if not binding:
        return False

    if binding.modifiers:
        keys = binding.modifiers + [binding.key]
        if binding.hold:
            for k in binding.modifiers:
                pyautogui.keyDown(k)
            pyautogui.keyDown(binding.key)
            time.sleep(0.5)
            pyautogui.keyUp(binding.key)
            for k in reversed(binding.modifiers):
                pyautogui.keyUp(k)
        else:
            pyautogui.hotkey(*keys)
    else:
        if binding.hold:
            _hold_key(binding.key, 500)
        else:
            _press_key(binding.key)

    return True


# ---------------------------------------------------------------------------
# Public dispatchers
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


def dispatch_profile_action(
    action_name: str, profile: dict[str, Any], binds: dict | None = None
) -> bool:
    """
    Look up action_name in profile and dispatch it.

    If binds are provided and the action has a known .binds mapping,
    uses the player's real keybinding. Falls back to profile definition.

    Parameters
    ----------
    action_name : str
        Key in profile["actions"].
    profile : dict
        Active game profile dict.
    binds : dict, optional
        Parsed keybindings from .binds file.

    Returns
    -------
    bool
        True if dispatched successfully, False if action not found.
    """
    # Try real keybinding first (bind-aware path)
    if binds:
        binds_action = PROFILE_TO_BINDS.get(action_name)
        if binds_action and dispatch_from_binds(binds_action, binds):
            return True

    # Fall back to profile definition
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
