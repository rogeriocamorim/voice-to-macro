# Voice-to-Macro

An AI-powered voice command system for PC games and apps. Uses local speech recognition and a lightweight LLM to understand natural language commands and map them to keyboard/mouse actions -- no exact phrases required.

Built as a modern, AI-powered alternative to rule-based tools like VoiceAttack.

---

## Features

- **Natural language** -- say commands how you naturally speak them ("punch it", "get us out of here")
- **No cloud required** -- fully local: Whisper STT + Ollama LLM + pyttsx3 TTS
- **Self-learning** -- remembers your phrases over time, improves with use
- **Clarification feedback** -- if unsure, asks "Did you mean hyperdrive or silent running?"
- **PTT + always-on** -- push-to-talk or voice activity detection modes
- **Rich action types** -- single keys, combos, sequences with delays, hold actions
- **Game personalities** -- in-character responses per game profile
- **Profiles included** -- Elite Dangerous, Star Citizen, Generic

### Elite Dangerous Integration

- **Game state awareness** -- reads journal logs, Status.json, and player keybindings in real time
- **Real keybindings** -- reads your `.binds` file so commands use your actual key mappings
- **Galaxy map automation** -- voice-controlled system plotting via UI automation
- **EDSM integration** -- system info, scan values, danger assessment, nearby systems, server status
- **Spansh integration** -- commodity search, multi-hop trade routes
- **Commander data** -- credits, ranks, materials via EDSM authenticated API
- **Trade intelligence** -- analyze your plotted route for profitable trades

---

## Requirements

- Windows 10/11
- Python 3.10+
- [Ollama](https://ollama.com) installed
- A microphone
- For Elite Dangerous: `httpx` and `watchdog` (included in requirements.txt)

---

## Installation

```bash
git clone https://github.com/rogeriocamorim/voice-to-macro.git
cd voice-to-macro
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

---

## First-run setup

```bash
python setup.py
```

The wizard will:
1. Detect your GPU and recommend the best Ollama model
2. Pull the model via Ollama
3. Ask you to press your preferred PTT key
4. Let you choose active game profile and personality

---

## Usage

```bash
# Start the assistant
python main.py

# Start with Elite Dangerous profile
python main.py --profile elite_dangerous

# Always-on mode (VAD)
python main.py --mode always_on

# Review and approve/reject learned commands
python main.py --review
```

---

## Elite Dangerous Voice Commands

The Elite Dangerous profile supports two types of voice commands:

### Simple Actions (keystroke dispatch)

These trigger immediate key presses using your real keybindings from the `.binds` file:

| What you say (examples) | Action | What happens |
|---|---|---|
| "Jump" / "Engage hyperdrive" / "Punch it" | `fsd_jump` | Presses your Hyperspace key |
| "Supercruise" / "Cruise" | `supercruise` | Engages supercruise |
| "Boost" / "Full power" | `boost` | Engine boost |
| "Landing gear" / "Gear down" | `landing_gear` | Toggles landing gear |
| "Silent running" / "Go dark" | `silent_running` | Toggles silent running |
| "Deploy hardpoints" / "Weapons out" | `hardpoints` | Deploy/retract weapons |
| "Galaxy map" / "Open map" | `galaxy_map` | Opens galaxy map |
| "Cut engines" / "Full stop" | `throttle_zero` | Throttle to zero |
| "Night vision" | `night_vision` | Toggles night vision |
| "Lights" / "Ship lights" | `lights` | Toggles external lights |

### Compound Actions (API-powered, multi-step)

These trigger complex handlers that call external APIs, automate the galaxy map, and respond via TTS:

| What you say (examples) | Action | What ARIA does |
|---|---|---|
| "Navigate to Sol" / "Plot route to Colonia" | `navigate_to` | Validates system on EDSM, opens galaxy map, types name, plots route |
| "Tell me about this system" / "System info for Deciat" | `system_info` | Fetches allegiance, economy, population, security, star scoopability |
| "How much is this system worth?" / "Scan value" | `scan_value` | Reports estimated exploration value and most valuable body |
| "Is this system dangerous?" / "Danger check for Deciat" | `danger_check` | Calculates danger from death/traffic ratio, reports deaths today/week |
| "What's nearby?" / "Systems within 30 light years" | `nearby_systems` | Lists nearby systems with distances from EDSM |
| "Where can I buy gold?" / "Find tritium" | `find_commodity` | Searches Spansh for nearest stations with that commodity |
| "Any good trades on my route?" | `monetize_route` | Analyzes your plotted NavRoute for the most profitable buy/sell pair |
| "Calculate a trade route" | `trade_route` | Uses Spansh to find optimal multi-hop trade route from your station |
| "How many credits do I have?" | `commander_status` | Reports balance from EDSM (needs API key) |
| "What are my ranks?" | `commander_status` | Reports Combat/Trade/Explore/Federation/Empire ranks |
| "Check server status" | `server_status` | Reports if ED servers are online/warning/down |

### How it works

```
You speak -> Whisper STT -> "navigate to sol"
    -> Fuzzy match (fast path) or LLM classification
    -> LLM returns: {"action": "navigate_to", "params": {"target": "Sol"}}
    -> navigate_to handler:
        1. EDSM: validate "Sol" exists, get correct name
        2. TTS: "Plotting route to Sol, Commander."
        3. pyautogui: open galaxy map (your real keybind)
        4. pyautogui: type "Sol" character by character
        5. pyautogui: select autocomplete + plot route
        6. pyautogui: close galaxy map
        7. TTS: "Route plotted to Sol."
```

### Configuration

Add these to `config.yaml` for Elite Dangerous:

```yaml
# Profile
active_profile: elite_dangerous

# Journal path (where Elite writes logs)
elite_journal_path: "C:\\Users\\YourName\\AppData\\Local\\Frontier Developments\\Elite Dangerous"

# Keybindings (leave blank to auto-detect)
elite_binds_file: ""

# EDSM API (for commander data - register at edsm.net)
edsm_commander_name: "Your Commander Name"
edsm_api_key: "your-api-key-here"

# Trade defaults
trade_max_cargo: 200
trade_max_hops: 5
trade_max_hop_distance: 30
trade_requires_large_pad: true
trade_starting_capital: 10000000
```

---

## Action types in profiles

```json
{ "type": "key",      "key": "j" }
{ "type": "combo",    "keys": ["shift", "s"] }
{ "type": "hold",     "key": "w", "duration_ms": 1000 }
{ "type": "sequence", "steps": [
    { "key": "j" },
    { "delay_ms": 300 },
    { "combo": ["ctrl", "alt", "f"] }
]}
```

---

## Adding a custom profile

Create a file in `profiles/my_game.json`:

```json
{
  "game": "My Game",
  "personality": "You are a tactical AI assistant. Respond in character.",
  "actions": {
    "reload": {
      "description": "Reload weapon",
      "action": { "type": "key", "key": "r" }
    },
    "grenade": {
      "description": "Throw grenade",
      "action": { "type": "key", "key": "g" }
    }
  }
}
```

Then run: `python main.py --profile my_game`

---

## Self-learning

Every time you use a command, it is logged to `learned_commands.json`. Over time the assistant gets faster and more accurate with your specific phrases.

To review pending (unconfirmed) learned commands:

```bash
python main.py --review
```

---

## GPU / model recommendations

| VRAM | Recommended model |
|---|---|
| < 4 GB or CPU only | `gemma2:2b` |
| 4-6 GB | `phi3:mini` |
| 6-8 GB | `phi3:mini` or `mistral:7b-q4` |
| 8 GB+ | `mistral:7b-q4` or `llama3.1:8b-q4` |

---

## Project structure

```
voice-to-macro/
├── main.py                  # Entry point and event loop
├── setup.py                 # First-run wizard
├── config.yaml              # User configuration (generated by setup)
├── requirements.txt
├── stt/
│   └── whisper_stt.py       # Speech-to-text via faster-whisper
├── vad/
│   └── silero_vad.py        # Voice activity detection + PTT
├── agent/
│   ├── intent_parser.py     # LLM intent classification (ParsedIntent)
│   ├── context_builder.py   # Prompt assembly with game state
│   └── feedback.py          # Clarification loop
├── executor/
│   └── action_dispatcher.py # Key dispatch + bind-aware dispatch
├── tts/
│   └── speaker.py           # Text-to-speech (edge-tts + pyttsx3)
├── learning/
│   └── command_store.py     # Self-learning store
├── gameapi/                 # Elite Dangerous game state
│   ├── events.py            # Journal event dataclasses
│   ├── journal_watcher.py   # Journal log tailer (daemon thread)
│   ├── status_reader.py     # Status.json poller (daemon thread)
│   ├── binds_parser.py      # .binds XML parser + key mapping
│   └── game_state.py        # Aggregated state (thread-safe)
├── search/                  # External API clients
│   ├── edsm.py              # EDSM: 15 endpoints (public + auth)
│   └── spansh.py            # Spansh: trade routes, station search
├── handlers/                # Compound action handlers
│   ├── navigate_to.py       # Galaxy map automation
│   ├── system_info.py       # System info, scan value, danger, nearby
│   ├── find_commodity.py    # Spansh station search
│   ├── monetize_route.py    # NavRoute trade analysis
│   ├── trade_route.py       # Spansh multi-hop trade route
│   └── commander_status.py  # EDSM auth: credits, ranks, materials
├── profiles/
│   ├── elite_dangerous.json # Simple + compound actions
│   ├── star_citizen.json
│   └── generic.json
└── tests/
    ├── test_action_dispatcher.py
    ├── test_binds_parser.py
    ├── test_journal_watcher.py
    ├── test_game_state.py
    ├── test_status_reader.py
    ├── test_edsm.py
    └── test_handlers.py
```

---

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_binds_parser.py -v

# Run specific test
pytest -k "test_navigate"
```

All external I/O (HTTP, files, pyautogui) is mocked. No Ollama, mic, or live APIs needed.

---

## License

MIT
