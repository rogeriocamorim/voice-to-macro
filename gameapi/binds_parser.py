"""
gameapi/binds_parser.py — Parse Elite Dangerous .binds XML for keybindings.

Reads the player's actual keybinding configuration and maps action names
to pyautogui-compatible key names. This ensures we press the correct keys
regardless of the player's custom bindings.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path


# ---------------------------------------------------------------------------
# KeyBinding dataclass
# ---------------------------------------------------------------------------

@dataclass
class KeyBinding:
    """A parsed keybinding from the .binds file."""
    key: str                        # pyautogui key name (e.g. "m", "shiftleft")
    modifiers: list[str] = field(default_factory=list)  # modifier keys
    hold: bool = False              # whether this is a hold-key action


# ---------------------------------------------------------------------------
# Key name mapping: Elite .binds format -> pyautogui format
# ---------------------------------------------------------------------------

_KEY_MAP: dict[str, str] = {
    # Letters
    **{f"Key_{chr(c)}": chr(c).lower() for c in range(ord("A"), ord("Z") + 1)},
    # Numbers
    **{f"Key_{i}": str(i) for i in range(10)},
    # Function keys
    **{f"Key_F{i}": f"f{i}" for i in range(1, 13)},
    # Numpad
    **{f"Key_Numpad_{i}": f"num{i}" for i in range(10)},
    "Key_Numpad_Enter": "enter",
    "Key_Numpad_Add": "add",
    "Key_Numpad_Subtract": "subtract",
    "Key_Numpad_Multiply": "multiply",
    "Key_Numpad_Divide": "divide",
    "Key_Numpad_Decimal": "decimal",
    # Modifiers
    "Key_LeftShift": "shiftleft",
    "Key_RightShift": "shiftright",
    "Key_LeftControl": "ctrlleft",
    "Key_RightControl": "ctrlright",
    "Key_LeftAlt": "altleft",
    "Key_RightAlt": "altright",
    # Navigation
    "Key_UpArrow": "up",
    "Key_DownArrow": "down",
    "Key_LeftArrow": "left",
    "Key_RightArrow": "right",
    "Key_Home": "home",
    "Key_End": "end",
    "Key_PageUp": "pageup",
    "Key_PageDown": "pagedown",
    # Special
    "Key_Space": "space",
    "Key_Enter": "enter",
    "Key_Return": "enter",
    "Key_Escape": "escape",
    "Key_Tab": "tab",
    "Key_Backspace": "backspace",
    "Key_Delete": "delete",
    "Key_Insert": "insert",
    "Key_CapsLock": "capslock",
    "Key_NumLock": "numlock",
    "Key_ScrollLock": "scrolllock",
    "Key_Pause": "pause",
    "Key_PrintScreen": "printscreen",
    # Punctuation
    "Key_Semicolon": ";",
    "Key_Comma": ",",
    "Key_Period": ".",
    "Key_Slash": "/",
    "Key_Grave": "`",
    "Key_LeftBracket": "[",
    "Key_RightBracket": "]",
    "Key_BackSlash": "\\",
    "Key_Apostrophe": "'",
    "Key_Minus": "-",
    "Key_Equals": "=",
    "Key_Apps": "menu",
}


def map_key_name(elite_key: str) -> str | None:
    """
    Convert an Elite Dangerous key name (e.g. 'Key_M') to a
    pyautogui-compatible key name (e.g. 'm').

    Returns None if the key cannot be mapped.
    """
    if not elite_key:
        return None
    return _KEY_MAP.get(elite_key)


# ---------------------------------------------------------------------------
# .binds file discovery
# ---------------------------------------------------------------------------

def find_binds_file(journal_dir: str | Path) -> Path | None:
    """
    Find the player's .binds file.

    Discovery order:
    1. Read StartPreset.*.start to get preset name
    2. Find matching {preset}.*.binds
    3. Fallback: most recently modified .binds file
    """
    journal_path = Path(journal_dir)
    bindings_dir = journal_path / "Options" / "Bindings"

    if not bindings_dir.exists():
        # Try alternative path structure
        bindings_dir = journal_path.parent / "Options" / "Bindings"
        if not bindings_dir.exists():
            return None

    # Try to read preset name from .start file
    preset_name = _read_preset_name(bindings_dir)

    if preset_name:
        # Find matching .binds file
        matches = sorted(
            bindings_dir.glob(f"{preset_name}.*.binds"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if matches:
            return matches[0]

        # Try exact match without version suffix
        exact = bindings_dir / f"{preset_name}.binds"
        if exact.exists():
            return exact

    # Fallback: newest .binds file
    all_binds = sorted(
        bindings_dir.glob("*.binds"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return all_binds[0] if all_binds else None


def _read_preset_name(bindings_dir: Path) -> str | None:
    """Read the preset name from StartPreset.*.start file."""
    start_files = list(bindings_dir.glob("StartPreset.*.start"))
    if not start_files:
        # Try without wildcard
        start_file = bindings_dir / "StartPreset.start"
        if start_file.exists():
            start_files = [start_file]

    for start_file in start_files:
        try:
            with open(start_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        return line
        except OSError:
            continue

    return None


# ---------------------------------------------------------------------------
# .binds XML parsing
# ---------------------------------------------------------------------------

def parse_binds(binds_file: str | Path) -> dict[str, KeyBinding]:
    """
    Parse a .binds XML file and return a mapping of action names
    to KeyBinding objects.

    Only keyboard bindings are extracted. Mouse/joystick bindings
    are ignored.

    Parameters
    ----------
    binds_file : path to the .binds XML file

    Returns
    -------
    dict mapping action name (e.g. "GalaxyMapOpen") to KeyBinding
    """
    binds_path = Path(binds_file)
    if not binds_path.exists():
        print(f"[BINDS] File not found: {binds_path}")
        return {}

    try:
        tree = ET.parse(binds_path)
    except ET.ParseError as e:
        print(f"[BINDS] XML parse error: {e}")
        return {}

    root = tree.getroot()
    bindings: dict[str, KeyBinding] = {}

    for action_elem in root:
        action_name = action_elem.tag
        binding = _parse_action_element(action_elem)
        if binding:
            bindings[action_name] = binding

    return bindings


def parse_binds_xml(xml_content: str) -> dict[str, KeyBinding]:
    """
    Parse .binds XML from a string (useful for testing).

    Parameters
    ----------
    xml_content : raw XML string

    Returns
    -------
    dict mapping action name to KeyBinding
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        print(f"[BINDS] XML parse error: {e}")
        return {}

    bindings: dict[str, KeyBinding] = {}

    for action_elem in root:
        action_name = action_elem.tag
        binding = _parse_action_element(action_elem)
        if binding:
            bindings[action_name] = binding

    return bindings


def _parse_action_element(action_elem: ET.Element) -> KeyBinding | None:
    """
    Parse a single action element from the .binds XML.

    Looks for <Primary> then <Secondary> keyboard bindings.
    Secondary overwrites Primary if both are keyboard.
    Non-keyboard bindings are skipped.
    """
    binding = None

    # Check Primary first, then Secondary (secondary can override)
    for child_tag in ("Primary", "Secondary"):
        child = action_elem.find(child_tag)
        if child is None:
            continue

        device = child.get("Device", "")
        if device != "Keyboard":
            continue

        key_name = child.get("Key", "")
        if not key_name:
            continue

        mapped_key = map_key_name(key_name)
        if mapped_key is None:
            continue

        # Check for hold
        hold = child.get("Hold", "0") == "1"

        # Check for modifiers
        modifiers = []
        for modifier_elem in child.findall("Modifier"):
            mod_key = modifier_elem.get("Key", "")
            mapped_mod = map_key_name(mod_key)
            if mapped_mod:
                modifiers.append(mapped_mod)

        binding = KeyBinding(key=mapped_key, modifiers=modifiers, hold=hold)

    return binding
