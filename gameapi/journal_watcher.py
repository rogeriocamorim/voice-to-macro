"""
gameapi/journal_watcher.py — Tail Elite Dangerous journal log files.

Runs in a daemon thread. Finds the newest Journal.*.log file, reads new
JSON lines as they're appended, parses events, and dispatches them to
the GameState manager.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from gameapi.events import EVENT_REGISTRY, JournalEvent

if TYPE_CHECKING:
    from gameapi.game_state import GameState


def find_latest_journal(journal_dir: str | Path) -> Path | None:
    """Find the most recently modified Journal.*.log file."""
    journal_path = Path(journal_dir)
    journals = sorted(
        journal_path.glob("Journal.*.log"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return journals[0] if journals else None


def read_nav_route(journal_dir: str | Path) -> list[dict] | None:
    """Read NavRoute.json and return the route stops."""
    nav_file = Path(journal_dir) / "NavRoute.json"
    if not nav_file.exists():
        return None
    try:
        with open(nav_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("Route", [])
    except (json.JSONDecodeError, OSError) as e:
        print(f"[JOURNAL] Error reading NavRoute.json: {e}")
        return None


def parse_journal_line(line: str) -> JournalEvent | None:
    """
    Parse a single journal JSON line into a typed event dataclass.
    Returns None for unknown events or malformed JSON.
    """
    line = line.strip()
    if not line:
        return None

    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    event_name = data.get("event")
    if not event_name:
        return None

    event_class = EVENT_REGISTRY.get(event_name)
    if event_class is None:
        return None  # silently ignore unknown events

    # Build dataclass from JSON fields
    timestamp = data.get("timestamp", "")
    kwargs = {"timestamp": timestamp, "event": event_name}

    # Map JSON fields to dataclass fields (skip timestamp/event)
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(event_class)} - {"timestamp", "event"}

    for field_name in field_names:
        if field_name in data:
            kwargs[field_name] = data[field_name]

    try:
        return event_class(**kwargs)
    except TypeError:
        return None


class JournalWatcher(threading.Thread):
    """
    Background thread that tails the Elite Dangerous journal log.

    Monitors for new lines appended to the current journal file,
    and watches for new journal files (game restart).
    """

    def __init__(self, journal_dir: str | Path, game_state: GameState):
        super().__init__(daemon=True, name="JournalWatcher")
        self.journal_dir = Path(journal_dir)
        self.game_state = game_state
        self._stop_event = threading.Event()
        self._poll_interval = 0.25  # seconds

    def stop(self):
        self._stop_event.set()

    def run(self):
        current_file: Path | None = None
        file_handle = None
        last_check_time = 0.0

        while not self._stop_event.is_set():
            try:
                # Check for new/changed journal file every 5 seconds
                now = time.time()
                if now - last_check_time > 5.0 or current_file is None:
                    latest = find_latest_journal(self.journal_dir)
                    if latest and latest != current_file:
                        if file_handle:
                            file_handle.close()
                        current_file = latest
                        file_handle = open(current_file, "r", encoding="utf-8")
                        # Seek to end — only read new lines
                        file_handle.seek(0, os.SEEK_END)
                        print(f"[JOURNAL] Watching: {current_file.name}")
                    last_check_time = now

                if file_handle is None:
                    time.sleep(self._poll_interval)
                    continue

                # Read new lines
                line = file_handle.readline()
                if line:
                    event = parse_journal_line(line)
                    if event:
                        self.game_state.handle_event(event)
                else:
                    time.sleep(self._poll_interval)

            except Exception as e:
                print(f"[JOURNAL] Watcher error: {e}")
                time.sleep(1.0)

        if file_handle:
            file_handle.close()
