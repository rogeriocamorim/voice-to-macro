"""
handlers/navigate_to.py — Galaxy map route plotting via UI automation.

Opens the galaxy map, types the destination system name into the search
box using the player's real keybindings, and plots the route.
"""

from __future__ import annotations
import time
from typing import Any

import pyautogui  # type: ignore

from gameapi.binds_parser import KeyBinding


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _press_bind(binds: dict[str, KeyBinding], action_name: str, hold_ms: int = 0) -> bool:
    """Press a key using the player's actual keybinding."""
    binding = binds.get(action_name)
    if not binding:
        print(f"[NAV] No keybinding found for '{action_name}'")
        return False

    if binding.modifiers:
        if hold_ms > 0:
            for k in binding.modifiers:
                pyautogui.keyDown(k)
            pyautogui.keyDown(binding.key)
            time.sleep(hold_ms / 1000.0)
            pyautogui.keyUp(binding.key)
            for k in reversed(binding.modifiers):
                pyautogui.keyUp(k)
        else:
            pyautogui.hotkey(*binding.modifiers, binding.key)
    else:
        if hold_ms > 0:
            pyautogui.keyDown(binding.key)
            time.sleep(hold_ms / 1000.0)
            pyautogui.keyUp(binding.key)
        else:
            pyautogui.press(binding.key)

    return True


def _type_text(text: str, delay: float = 0.03):
    """Type text character by character (for galaxy map search box)."""
    for char in text:
        if char == " ":
            pyautogui.press("space")
        elif char.isalnum() or char in "-'.":
            pyautogui.press(char.lower())
        time.sleep(delay)


# ---------------------------------------------------------------------------
# Handler
# ---------------------------------------------------------------------------

def handle(
    params: dict,
    game_state: Any,
    config: dict,
    speaker: Any,
    binds: dict[str, KeyBinding],
    edsm: Any,
    spansh: Any,
) -> bool:
    """
    Plot a route to a system via the galaxy map.

    Steps:
    1. Validate system exists via EDSM
    2. Close any open panel
    3. Open galaxy map
    4. Navigate to search box
    5. Type destination name
    6. Select first result and plot route
    """
    target = params.get("target", "").strip()
    if not target:
        speaker.say("No destination specified, Commander.")
        return False

    # Validate system exists
    system_data = edsm.get_system(target)
    if not system_data or not system_data.get("name"):
        speaker.say(f"System {target} not found in the database.")
        return False

    # Use corrected system name from EDSM
    target = system_data["name"]
    print(f"[NAV] Plotting route to: {target}")
    speaker.say(f"Plotting route to {target}, Commander.")

    # Close any open panel
    gui_focus = game_state.get_gui_focus() if game_state else 0
    if gui_focus != 0:
        # Galaxy map is already open (focus=6), close it first
        if gui_focus == 6:
            _press_bind(binds, "GalaxyMapOpen")
            time.sleep(1.0)
        else:
            _press_bind(binds, "UI_Back")
            time.sleep(0.5)

    # Open galaxy map
    if not _press_bind(binds, "GalaxyMapOpen"):
        speaker.say("Cannot open galaxy map. Keybinding not found.")
        return False
    time.sleep(3.0)  # galaxy map takes ~3s to fully load

    # Navigate to search box
    # Zoom in to reset view state
    _press_bind(binds, "CamZoomIn", hold_ms=500)
    time.sleep(0.3)

    # Navigate UI to focus the search input
    _press_bind(binds, "UI_Left")
    time.sleep(0.2)
    _press_bind(binds, "UI_Right")
    time.sleep(0.2)
    _press_bind(binds, "UI_Select")
    time.sleep(0.5)

    # Type the destination system name
    _type_text(target)
    time.sleep(1.5)  # wait for autocomplete results

    # Select first autocomplete result
    pyautogui.press("down")
    time.sleep(0.2)
    pyautogui.press("enter")
    time.sleep(1.0)

    # Plot route (confirm)
    pyautogui.press("enter")
    time.sleep(0.5)

    # Close galaxy map
    _press_bind(binds, "GalaxyMapOpen")

    speaker.say(f"Route plotted to {target}.")
    return True
