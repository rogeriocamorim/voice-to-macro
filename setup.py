"""
setup.py — First-run wizard for Voice-to-Macro.

Detects GPU, recommends and pulls an Ollama model,
captures the PTT key, and writes config.yaml.
"""

import os
import subprocess
import sys
import re
import yaml
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.yaml"

# ---------------------------------------------------------------------------
# GPU detection
# ---------------------------------------------------------------------------

def detect_gpu() -> tuple[str, int]:
    """
    Returns (gpu_name, vram_mb).
    Falls back to ('CPU', 0) if nothing is detected.
    """
    # Try nvidia-smi first
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            line = result.stdout.strip().split("\n")[0]
            parts = line.split(",")
            name = parts[0].strip()
            vram_mb = int(parts[1].strip())
            return name, vram_mb
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass

    # Try wmic for AMD/Intel (Windows)
    try:
        result = subprocess.run(
            ["wmic", "path", "win32_VideoController", "get", "Name,AdapterRAM"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            lines = [l.strip() for l in result.stdout.strip().split("\n") if l.strip()]
            # Skip header line
            for line in lines[1:]:
                parts = line.rsplit(None, 1)
                if len(parts) == 2:
                    name = parts[0].strip()
                    try:
                        vram_mb = int(parts[1]) // (1024 * 1024)
                        return name, vram_mb
                    except ValueError:
                        continue
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return "CPU", 0


def recommend_model(vram_mb: int) -> str:
    if vram_mb >= 8192:
        return "mistral:7b-q4"
    elif vram_mb >= 6144:
        return "phi3:mini"
    elif vram_mb >= 4096:
        return "phi3:mini"
    else:
        return "gemma2:2b"


def _install_cuda_torch() -> bool:
    """
    Reinstall torch and torchaudio with CUDA 12.1 support.
    Uses --force-reinstall so pip swaps the CPU build even if versions match.
    Returns True if successful.
    """
    print("\n  Installing CUDA-enabled torch (this may take a few minutes)...")
    try:
        subprocess.run(
            [
                sys.executable, "-m", "pip", "install",
                "torch", "torchaudio",
                "--index-url", "https://download.pytorch.org/whl/cu121",
                "--force-reinstall",
            ],
            check=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"  [ERROR] Installation failed: {e}")
        return False


def detect_device(vram_mb: int) -> str:
    """
    Returns 'cuda' only if a GPU was found AND the installed torch
    was compiled with CUDA support.

    If a GPU is found but torch has no CUDA, offers to install the
    CUDA torch build automatically, then re-checks.
    """
    if vram_mb <= 0:
        return "cpu"
    try:
        import torch  # type: ignore
        if torch.cuda.is_available():
            return "cuda"

        # GPU found but CPU-only torch installed — offer to fix it
        print("\n  [!] GPU detected but the installed torch has no CUDA support.")
        print(f"      Your RTX / GPU will be idle — everything runs on CPU.")
        choice = input("\n  Install CUDA-enabled torch now? [Y/n]: ").strip().lower()
        if choice in ("", "y", "yes"):
            success = _install_cuda_torch()
            if success:
                # Verify in a fresh subprocess — torch cannot be reloaded in-process
                check = subprocess.run(
                    [sys.executable, "-c", "import torch; print(torch.cuda.is_available())"],
                    capture_output=True, text=True,
                )
                if check.stdout.strip() == "True":
                    print("  CUDA torch installed successfully. GPU will be used.")
                    return "cuda"
                else:
                    print("  Install succeeded but CUDA still not detected.")
                    print("  This usually means the venv needs a full restart.")
                    print("  Close this terminal, re-activate the venv, then re-run: python setup.py")
            print("  Falling back to CPU for now.")
        else:
            print("  Skipping — using CPU.")
            print("  To enable GPU later: pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu121")
        return "cpu"

    except ImportError:
        return "cpu"


# ---------------------------------------------------------------------------
# Ollama helpers
# ---------------------------------------------------------------------------

def _ollama_binary_exists() -> bool:
    """Check if the ollama binary is findable on PATH or common install locations."""
    import shutil
    if shutil.which("ollama"):
        return True
    # Windows default install path
    common = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path("C:/Program Files/Ollama/ollama.exe"),
    ]
    return any(p.exists() for p in common)


def _ollama_server_running() -> bool:
    """Check if the Ollama API server is reachable on localhost:11434."""
    import urllib.request
    import urllib.error
    try:
        urllib.request.urlopen("http://localhost:11434", timeout=3)
        return True
    except Exception:
        return False


def check_ollama() -> tuple[bool, bool]:
    """
    Returns (binary_found, server_running).
    Both must be True for ollama pull/generate to work.
    """
    binary = _ollama_binary_exists()
    server = _ollama_server_running() if binary else False
    return binary, server


def pull_model(model: str) -> None:
    print(f"\n> Pulling model '{model}' via Ollama (this may take a while)...")
    subprocess.run(["ollama", "pull", model], check=True)


# ---------------------------------------------------------------------------
# PTT key capture
# ---------------------------------------------------------------------------

def capture_ptt_key() -> str:
    """
    Waits for the user to press a key and returns its name.
    Uses pynput so it works for keyboard AND mouse side buttons.
    """
    print("\n> Press the key you want to use as Push-To-Talk (PTT)...")
    print("  (keyboard key, mouse button, etc.)")

    captured = {"key": None}

    try:
        from pynput import keyboard as kb

        def on_press(key):
            try:
                captured["key"] = key.char if hasattr(key, "char") and key.char else str(key).replace("Key.", "")
            except Exception:
                captured["key"] = str(key).replace("Key.", "")
            return False  # stop listener

        with kb.Listener(on_press=on_press) as listener:
            listener.join()

        return captured["key"] or "caps_lock"

    except ImportError:
        print("  pynput not installed — defaulting to 'caps_lock'")
        return "caps_lock"


# ---------------------------------------------------------------------------
# Profile selection
# ---------------------------------------------------------------------------

PROFILES = {
    "1": "elite_dangerous",
    "2": "star_citizen",
    "3": "generic",
}

PERSONALITIES = {
    "1": "game_themed",
    "2": "generic",
}

WHISPER_MODELS = {
    "1": ("tiny",   "Fastest, least accurate — good for testing"),
    "2": ("base",   "Fast, decent accuracy — recommended default"),
    "3": ("small",  "Slower, better accuracy"),
    "4": ("medium", "Slowest, best accuracy"),
}

MODES = {
    "1": ("ptt",        "Hold a key to activate mic"),
    "2": ("always_on",  "Always listening, uses VAD to detect speech"),
}


def prompt_choice(prompt: str, choices: dict, default: str) -> str:
    while True:
        answer = input(f"{prompt} [{default}]: ").strip()
        if answer == "":
            return default
        if answer in choices:
            return choices[answer]
        print(f"  Invalid choice. Enter one of: {', '.join(choices.keys())}")


# ---------------------------------------------------------------------------
# Main wizard
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("  Voice-to-Macro — First-Run Setup Wizard")
    print("=" * 60)

    # 1. GPU detection
    print("\n> Detecting GPU...")
    gpu_name, vram_mb = detect_gpu()
    if vram_mb > 0:
        print(f"  Found: {gpu_name} ({vram_mb} MB VRAM)")
    else:
        print(f"  No dedicated GPU found — will run on CPU (slower)")

    # 2. Model recommendation
    recommended = recommend_model(vram_mb)
    device = detect_device(vram_mb)
    print(f"\n> Recommended Ollama model: {recommended}")
    custom_model = input(f"  Use this model? Press Enter to confirm or type another: ").strip()
    model = custom_model if custom_model else recommended

    # 3. Ollama check + pull
    print("\n> Checking Ollama...")
    binary_found, server_running = check_ollama()

    if not binary_found:
        print("  [ERROR] Ollama binary not found.")
        print("  Install it from https://ollama.com/download then re-run setup.")
        print("  After installing, launch the Ollama app (it runs a local server).")
        cont = input("\n  Continue setup without pulling a model? [y/N]: ").strip().lower()
        if cont not in ("y", "yes"):
            sys.exit(1)
    elif not server_running:
        print("  [WARNING] Ollama is installed but the server is not running.")
        print("  Start it by launching the Ollama app or running: ollama serve")
        print()
        cont = input("  Start Ollama now, then press Enter to retry, or type 's' to skip: ").strip().lower()
        if cont != "s":
            # Re-check after user says they started it
            _, server_running = check_ollama()
            if not server_running:
                print("  Still not reachable. Skipping model pull — run 'ollama pull' manually later.")
            else:
                print("  Ollama server detected.")
    else:
        print("  Ollama is installed and running.")

    if binary_found and server_running:
        do_pull = input(f"\n> Pull model '{model}' now? [Y/n]: ").strip().lower()
        if do_pull in ("", "y", "yes"):
            try:
                pull_model(model)
                print(f"  Model '{model}' ready.")
            except subprocess.CalledProcessError:
                print(f"  [ERROR] Pull failed. Try manually: ollama pull {model}")
    else:
        print(f"\n  Skipped model pull. Run manually later: ollama pull {model}")

    # 4. Mode selection
    print("\n> Choose listening mode:")
    for k, (v, desc) in MODES.items():
        print(f"  [{k}] {v} — {desc}")
    mode = prompt_choice("  Enter choice", {k: v for k, (v, _) in MODES.items()}, "1")

    # 5. PTT key (only if ptt mode)
    ptt_key = "caps_lock"
    if mode == "ptt":
        ptt_key = capture_ptt_key()
        print(f"  PTT key set to: '{ptt_key}'")

    # 6. Profile
    print("\n> Choose active game profile:")
    for k, v in PROFILES.items():
        print(f"  [{k}] {v}")
    active_profile = prompt_choice("  Enter choice", PROFILES, "3")

    # 7. Personality
    print("\n> Choose response personality:")
    for k, v in PERSONALITIES.items():
        print(f"  [{k}] {v}")
    personality = prompt_choice("  Enter choice", PERSONALITIES, "1")

    # 8. Whisper model
    print("\n> Choose Whisper STT model size:")
    for k, (v, desc) in WHISPER_MODELS.items():
        print(f"  [{k}] {v} — {desc}")
    whisper_model = prompt_choice("  Enter choice", {k: v for k, (v, _) in WHISPER_MODELS.items()}, "2")

    # 9. Write config.yaml
    config = {
        "mode": mode,
        "ptt_key": ptt_key,
        "active_profile": active_profile,
        "personality": personality,
        "model": model,
        "device": device,
        "whisper_model": whisper_model,
        "sample_rate": 16000,
        "vad_threshold": 0.5,
        "confidence_threshold": 0.6,
    }

    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)

    print("\n" + "=" * 60)
    print("  Setup complete! Configuration saved to config.yaml")
    print(f"  Run: python main.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
