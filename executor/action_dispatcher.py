"""
executor/action_dispatcher.py — Executes game actions via keyboard/mouse.

Supports four action types defined in profile JSON:
  - key:      single keypress
  - combo:    simultaneous key combination
  - hold:     key held for a duration
  - sequence: ordered list of steps (key/combo/hold/delay)

Also supports bind-aware dispatch for Elite Dangerous: uses the player's
real keybindings from their .binds file, falling back to profile definitions.

Input is delivered via ctypes SendInput with hardware scan codes so that
fullscreen/DirectInput games like Elite Dangerous receive the keystrokes.
The game window is focused before sending input.
"""

from __future__ import annotations
import ctypes
import platform
import time
from typing import Any

# ---------------------------------------------------------------------------
# Low-level input via ctypes (Windows only, fallback for non-Windows)
# ---------------------------------------------------------------------------

_IS_WINDOWS = platform.system() == "Windows"

if _IS_WINDOWS:
    import ctypes.wintypes as wintypes

    # Windows constants
    INPUT_KEYBOARD = 1
    KEYEVENTF_SCANCODE = 0x0008
    KEYEVENTF_KEYUP = 0x0002

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _fields_ = [
            ("type", wintypes.DWORD),
            ("_input", _INPUT),
        ]

    # Scan code map (US keyboard layout - DirectInput scan codes)
    SCAN_CODES: dict[str, int] = {
        "escape": 0x01, "esc": 0x01,
        "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
        "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
        "-": 0x0C, "=": 0x0D, "backspace": 0x0E,
        "tab": 0x0F,
        "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14,
        "y": 0x15, "u": 0x16, "i": 0x17, "o": 0x18, "p": 0x19,
        "[": 0x1A, "]": 0x1B, "enter": 0x1C, "return": 0x1C,
        "ctrl": 0x1D, "lctrl": 0x1D,
        "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21, "g": 0x22,
        "h": 0x23, "j": 0x24, "k": 0x25, "l": 0x26,
        ";": 0x27, "'": 0x28, "`": 0x29,
        "shift": 0x2A, "lshift": 0x2A, "\\": 0x2B,
        "z": 0x2C, "x": 0x2D, "c": 0x2E, "v": 0x2F, "b": 0x30,
        "n": 0x31, "m": 0x32, ",": 0x33, ".": 0x34, "/": 0x35,
        "rshift": 0x36, "alt": 0x38, "lalt": 0x38,
        "space": 0x39, "capslock": 0x3A, "caps_lock": 0x3A,
        "f1": 0x3B, "f2": 0x3C, "f3": 0x3D, "f4": 0x3E, "f5": 0x3F,
        "f6": 0x40, "f7": 0x41, "f8": 0x42, "f9": 0x43, "f10": 0x44,
        "numlock": 0x45, "scrolllock": 0x46,
        "num7": 0x47, "num8": 0x48, "num9": 0x49, "num-": 0x4A,
        "num4": 0x4B, "num5": 0x4C, "num6": 0x4D, "num+": 0x4E,
        "num1": 0x4F, "num2": 0x50, "num3": 0x51, "num0": 0x52, "num.": 0x53,
        "f11": 0x57, "f12": 0x58,
        "rctrl": 0x9D, "ralt": 0xB8,
        "up": 0xC8, "down": 0xD0, "left": 0xCB, "right": 0xCD,
        "home": 0xC7, "end": 0xCF, "pageup": 0xC9, "pagedown": 0xD1,
        "insert": 0xD2, "delete": 0xD3, "del": 0xD3,
    }

    def _send_scan(scan_code: int, key_up: bool = False) -> None:
        """Send a single scan code via SendInput."""
        flags = KEYEVENTF_SCANCODE
        if key_up:
            flags |= KEYEVENTF_KEYUP

        ki = KEYBDINPUT(
            wVk=0,
            wScan=scan_code,
            dwFlags=flags,
            time=0,
            dwExtraInfo=ctypes.pointer(ctypes.c_ulong(0)),
        )
        inp = INPUT(type=INPUT_KEYBOARD)
        inp._input.ki = ki
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))

    def _get_scan_code(key: str) -> int:
        """Look up a scan code for a key name. Falls back to MapVirtualKeyW."""
        key_lower = key.lower().strip()
        code = SCAN_CODES.get(key_lower)
        if code:
            return code
        # Try mapping via Windows API (virtual key -> scan code)
        vk = ctypes.windll.user32.VkKeyScanW(ord(key_lower[0])) & 0xFF
        if vk:
            scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
            if scan:
                return scan
        print(f"[EXECUTOR] Warning: no scan code for key '{key}'")
        return 0

    def _focus_game_window() -> None:
        """Bring the Elite Dangerous window to the foreground."""
        user32 = ctypes.windll.user32

        # Try known Elite Dangerous window titles
        titles = [
            "Elite - Dangerous (CLIENT)",
            "Elite - Dangerous",
        ]
        hwnd = 0
        for title in titles:
            hwnd = user32.FindWindowW(None, title)
            if hwnd:
                break

        if hwnd:
            # Use the AllowSetForegroundWindow trick via AttachThreadInput
            foreground_tid = user32.GetWindowThreadProcessId(
                user32.GetForegroundWindow(), None
            )
            current_tid = ctypes.windll.kernel32.GetCurrentThreadId()
            if foreground_tid != current_tid:
                user32.AttachThreadInput(current_tid, foreground_tid, True)
                user32.SetForegroundWindow(hwnd)
                user32.AttachThreadInput(current_tid, foreground_tid, False)
            else:
                user32.SetForegroundWindow(hwnd)
            time.sleep(0.05)  # brief pause for focus to take effect

    print("[EXECUTOR] Using ctypes SendInput with DirectInput scan codes (Windows)")

else:
    # Non-Windows fallback (macOS/Linux dev) — use pyautogui
    try:
        import pyautogui  # type: ignore
        pyautogui.FAILSAFE = False
        pyautogui.PAUSE = 0.0
    except ImportError:
        pass

    def _send_scan(scan_code: int, key_up: bool = False) -> None:
        pass

    def _get_scan_code(key: str) -> int:
        return 0

    def _focus_game_window() -> None:
        pass

    print("[EXECUTOR] Non-Windows platform — using pyautogui fallback")


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
    """Single keypress (down + up) via scan code."""
    if _IS_WINDOWS:
        _focus_game_window()
        code = _get_scan_code(key)
        if code:
            _send_scan(code)
            time.sleep(0.03)
            _send_scan(code, key_up=True)
            time.sleep(0.02)
    else:
        try:
            pyautogui.press(key)  # type: ignore
        except Exception:
            pass


def _press_combo(keys: list[str]) -> None:
    """Simultaneous key combination via scan codes."""
    if _IS_WINDOWS:
        _focus_game_window()
        codes = [_get_scan_code(k) for k in keys]
        # Press all keys down
        for code in codes:
            if code:
                _send_scan(code)
                time.sleep(0.02)
        time.sleep(0.03)
        # Release in reverse order
        for code in reversed(codes):
            if code:
                _send_scan(code, key_up=True)
                time.sleep(0.02)
    else:
        try:
            pyautogui.hotkey(*keys)  # type: ignore
        except Exception:
            pass


def _hold_key(key: str, duration_ms: int) -> None:
    """Hold a key down for a given duration, then release."""
    if _IS_WINDOWS:
        _focus_game_window()
        code = _get_scan_code(key)
        if code:
            _send_scan(code)
            time.sleep(duration_ms / 1000.0)
            _send_scan(code, key_up=True)
    else:
        try:
            pyautogui.keyDown(key)  # type: ignore
            time.sleep(duration_ms / 1000.0)
            pyautogui.keyUp(key)  # type: ignore
        except Exception:
            pass


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
            # Hold combo: press modifiers, hold main key, then release all
            _focus_game_window()
            if _IS_WINDOWS:
                for k in binding.modifiers:
                    code = _get_scan_code(k)
                    if code:
                        _send_scan(code)
                        time.sleep(0.02)
                code = _get_scan_code(binding.key)
                if code:
                    _send_scan(code)
                    time.sleep(0.5)
                    _send_scan(code, key_up=True)
                for k in reversed(binding.modifiers):
                    code = _get_scan_code(k)
                    if code:
                        _send_scan(code, key_up=True)
            else:
                _press_combo(keys)
        else:
            _press_combo(keys)
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
