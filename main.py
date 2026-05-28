"""
main.py — Voice-to-Macro entry point and main event loop.

Usage:
  python main.py                        # use config.yaml defaults
  python main.py --profile elite_dangerous
  python main.py --mode always_on
  python main.py --mode ptt
  python main.py --review               # review learned commands
"""

from __future__ import annotations
import argparse
import json
import os
import sys
import warnings
from pathlib import Path

# Suppress noisy but harmless warnings before any heavy imports
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")  # huggingface symlink warning on Windows
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")    # unauthenticated HF Hub notice
warnings.filterwarnings("ignore", message=".*symlinks.*")
warnings.filterwarnings("ignore", message=".*unauthenticated.*")

import shutil
import urllib.request

import yaml  # type: ignore

from agent.feedback import clarify
from agent.intent_parser import parse_intent
from executor.action_dispatcher import dispatch_profile_action
from learning.command_store import (
    get_all,
    increment_uses,
    lookup,
    review_interactive,
    save_mapping,
)
from stt.whisper_stt import WhisperSTT
from tts.speaker import Speaker
from vad.silero_vad import PTTRecorder, SileroVAD

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.yaml"
PROFILES_DIR = BASE_DIR / "profiles"


# ---------------------------------------------------------------------------
# Ollama pre-flight check
# ---------------------------------------------------------------------------

def _check_ollama(model: str) -> None:
    """
    Verify Ollama is installed and its server is reachable.
    Print clear, actionable messages — never silently fail.
    """
    binary_found = bool(shutil.which("ollama"))

    if not binary_found:
        print("\n[OLLAMA] Binary not found on PATH.")
        print("         Install from https://ollama.com/download")
        print("         After installing, launch the Ollama app to start the server.")
        print(f"         Then run: ollama pull {model}")
        print("\n[OLLAMA] Continuing anyway — LLM calls will fail until Ollama is running.\n")
        return

    server_running = False
    try:
        urllib.request.urlopen("http://localhost:11434", timeout=3)
        server_running = True
    except Exception:
        pass

    if not server_running:
        print("\n[OLLAMA] Ollama is installed but the server is NOT running.")
        print("         Fix: launch the Ollama desktop app, or run in a terminal:")
        print("              ollama serve")
        print(f"         Then pull the model if you haven't: ollama pull {model}")
        print("\n[OLLAMA] Continuing anyway — LLM calls will fail until the server is up.\n")
    else:
        print(f"[OLLAMA] Server running. Model: {model}")




def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print("[MAIN] config.yaml not found. Run: python setup.py")
        sys.exit(1)
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_profile(name: str) -> dict:
    path = PROFILES_DIR / f"{name}.json"
    if not path.exists():
        print(f"[MAIN] Profile '{name}' not found at {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Command processing — shared between PTT and always-on modes
# ---------------------------------------------------------------------------

def process_transcript(
    transcript: str,
    profile: dict,
    speaker: Speaker,
    config: dict,
    recorder=None,
    stt: WhisperSTT = None,
) -> None:
    """
    Full pipeline for a single voice transcript:
    1. Check learned commands fast-path
    2. LLM intent classification
    3. Execute or clarify
    4. Save to learned store
    """
    if not transcript.strip():
        print("\r\033[K[MAIN] (nothing heard — too short or silent)", flush=True)
        return

    print(f"\r\033[K[MAIN] Heard: \033[96m'{transcript}'\033[0m", flush=True)

    # Special built-in commands
    if "help" in transcript:
        speaker.help(profile)
        return

    # Fast-path: check confirmed learned mappings first
    learned = lookup(transcript)
    if learned:
        action_name = learned["intent"]
        print(f"[MAIN] Learned match: '{transcript}' → {action_name}")
        ok = dispatch_profile_action(action_name, profile)
        if ok:
            increment_uses(transcript)
            speaker.confirm(action_name)
        return

    # LLM classification
    model = config.get("model", "phi3:mini")
    confidence_threshold = config.get("confidence_threshold", 0.6)

    action_name, confidence = parse_intent(transcript, profile, model=model)
    print(f"[MAIN] LLM result: '{action_name}' (confidence={confidence:.2f})")

    if action_name != "unknown" and confidence >= confidence_threshold:
        ok = dispatch_profile_action(action_name, profile)
        if ok:
            # Save as unconfirmed — auto-confirms after 3 uses
            save_mapping(transcript, action_name, action_name, confirmed=False)
            increment_uses(transcript)
            speaker.confirm(action_name)
    else:
        # Clarification loop (Option B)
        ptt_mode = config.get("mode", "ptt") == "ptt"
        confirmed_action = clarify(
            transcript=transcript,
            profile=profile,
            speaker=speaker,
            recorder=recorder,
            stt=stt,
            ptt_mode=ptt_mode,
        )
        if confirmed_action:
            ok = dispatch_profile_action(confirmed_action, profile)
            if ok:
                save_mapping(transcript, confirmed_action, confirmed_action, confirmed=True)
                increment_uses(transcript)


# ---------------------------------------------------------------------------
# PTT mode loop
# ---------------------------------------------------------------------------

def run_ptt(config: dict, profile: dict, speaker: Speaker, stt: WhisperSTT) -> None:
    ptt_key = config.get("ptt_key", "caps_lock")
    sample_rate = config.get("sample_rate", 16000)
    recorder = PTTRecorder(ptt_key=ptt_key, sample_rate=sample_rate)

    print(f"\n[MAIN] PTT mode active. Hold '{ptt_key}' to speak. Ctrl+C to quit.\n")
    speaker.say("Voice to Macro ready. Push to talk mode active.")

    while True:
        print(f"\r\033[K[MAIN] Hold '{ptt_key}' to speak...", end="", flush=True)
        audio = recorder.record()
        if audio is None or len(audio) < sample_rate * 0.3:
            print("\r\033[K[MAIN] (too short — ignored)", flush=True)
            continue

        transcript = stt.transcribe(audio, sample_rate=sample_rate)
        process_transcript(
            transcript=transcript,
            profile=profile,
            speaker=speaker,
            config=config,
            recorder=recorder,
            stt=stt,
        )


# ---------------------------------------------------------------------------
# Always-on (VAD) mode loop
# ---------------------------------------------------------------------------

def run_always_on(config: dict, profile: dict, speaker: Speaker, stt: WhisperSTT) -> None:
    device = config.get("device", "cpu")
    threshold = config.get("vad_threshold", 0.5)
    sample_rate = config.get("sample_rate", 16000)

    vad = SileroVAD(
        threshold=threshold,
        device=device,
        max_silence_ms=config.get("max_silence_ms", 700),
    )

    print("\n[MAIN] Always-on mode active. Speak naturally. Ctrl+C to quit.\n")
    speaker.say("Voice to Macro ready. Always on mode active.")

    try:
        for audio_segment in vad.stream():
            transcript = stt.transcribe(audio_segment, sample_rate=sample_rate)
            process_transcript(
                transcript=transcript,
                profile=profile,
                speaker=speaker,
                config=config,
                recorder=None,
                stt=stt,
            )
    except KeyboardInterrupt:
        vad.stop()
        raise


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Voice-to-Macro AI assistant")
    parser.add_argument("--profile", type=str, help="Profile name to load")
    parser.add_argument("--mode", type=str, choices=["ptt", "always_on"], help="Listening mode")
    parser.add_argument("--review", action="store_true", help="Review learned commands")
    args = parser.parse_args()

    # Review mode — no audio needed
    if args.review:
        review_interactive()
        return

    config = load_config()

    # CLI overrides
    if args.profile:
        config["active_profile"] = args.profile
    if args.mode:
        config["mode"] = args.mode

    profile_name = config.get("active_profile", "generic")
    profile = load_profile(profile_name)

    print(f"\n{'='*55}")
    print(f"  Voice-to-Macro")
    print(f"  Profile   : {profile.get('game', profile_name)}")
    print(f"  Mode      : {config.get('mode', 'ptt').upper()}")
    print(f"  Model     : {config.get('model', 'phi3:mini')}")
    print(f"  Personality: {config.get('personality', 'generic')}")
    print(f"{'='*55}\n")

    # Ollama pre-flight — inform user clearly if something is wrong
    _check_ollama(config.get("model", "phi3:mini"))

    # Initialise shared components
    stt = WhisperSTT(
        model_size=config.get("whisper_model", "small"),
        device=config.get("device", "cpu"),
        beam_size=config.get("whisper_beam_size", 5),
        profile=profile,
    )

    speaker = Speaker(
        personality=config.get("personality", "generic"),
        profile=profile,
        voice_override=config.get("tts_voice") or None,
    )

    try:
        mode = config.get("mode", "ptt")
        if mode == "always_on":
            run_always_on(config, profile, speaker, stt)
        else:
            run_ptt(config, profile, speaker, stt)
    except KeyboardInterrupt:
        print("\n[MAIN] Shutting down. Goodbye.")
        speaker.say("Shutting down. Goodbye.")


if __name__ == "__main__":
    main()
