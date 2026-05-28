"""
gui/engine.py — Background voice engine thread.

Runs the PTT / always-on loop in a QThread and emits Qt signals
back to the GUI for every lifecycle event: recording, transcribing,
heard, intent matched, executed, error.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Optional

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from agent.feedback import clarify
from agent.intent_parser import parse_intent
from executor.action_dispatcher import dispatch_profile_action
from learning.command_store import increment_uses, lookup, save_mapping
from stt.whisper_stt import WhisperSTT
from tts.speaker import Speaker
from vad.silero_vad import PTTRecorder, SileroVAD


def _ts() -> str:
    return datetime.now().strftime("%m/%d/%Y %I:%M:%S %p")


class VoiceEngine(QThread):
    """
    Signals
    -------
    log(str)          — timestamped message for the log tab
    status(str)       — short status for the status bar: IDLE / RECORDING / TRANSCRIBING / etc.
    recording(bool)   — True when mic is active, False when released
    """

    log = pyqtSignal(str)
    status = pyqtSignal(str)
    recording = pyqtSignal(bool)

    def __init__(
        self,
        config: dict,
        profile: dict,
        parent=None,
    ):
        super().__init__(parent)
        self._config = config
        self._profile = profile
        self._running = False

    # ------------------------------------------------------------------
    # Public control
    # ------------------------------------------------------------------

    def stop(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Thread entry
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._running = True
        config = self._config
        profile = self._profile

        # Initialise STT
        self.log.emit(f"[{_ts()}] Initialising Whisper STT...")
        self.status.emit("LOADING STT")
        stt = WhisperSTT(
            model_size=config.get("whisper_model", "small"),
            device=config.get("device", "cpu"),
            beam_size=config.get("whisper_beam_size", 5),
            profile=profile,
        )
        # Force-load model now so first command is fast
        stt._load()

        # Initialise TTS
        speaker = Speaker(
            personality=config.get("personality", "generic"),
            profile=profile,
            voice_override=config.get("tts_voice") or None,
        )

        mode = config.get("mode", "ptt")
        if mode == "ptt":
            self._run_ptt(config, profile, stt, speaker)
        else:
            self._run_always_on(config, profile, stt, speaker)

    # ------------------------------------------------------------------
    # PTT loop
    # ------------------------------------------------------------------

    def _run_ptt(self, config: dict, profile: dict, stt: WhisperSTT, speaker: Speaker) -> None:
        ptt_key = config.get("ptt_key", "caps_lock")
        sample_rate = config.get("sample_rate", 16000)
        recorder = PTTRecorder(ptt_key=ptt_key, sample_rate=sample_rate)

        self.log.emit(f"[{_ts()}] PTT mode active. Hold '{ptt_key}' to speak.")
        self.status.emit("IDLE")
        speaker.say("Voice to Macro ready. Push to talk mode active.")

        while self._running:
            self.status.emit("IDLE")
            self.recording.emit(False)

            audio = recorder.record()
            if not self._running:
                break
            if audio is None or len(audio) < sample_rate * 0.3:
                self.log.emit(f"[{_ts()}] (too short — ignored)")
                continue

            self.recording.emit(True)
            self.status.emit("TRANSCRIBING")
            self.log.emit(f"[{_ts()}] Transcribing...")

            t0 = time.perf_counter()
            transcript = stt.transcribe(audio, sample_rate=sample_rate)
            stt_ms = (time.perf_counter() - t0) * 1000
            self.recording.emit(False)

            self.log.emit(f"[{_ts()}] [STT] Transcribed in {stt_ms:.0f}ms")

            self._process(transcript, profile, speaker, config, recorder, stt)

    # ------------------------------------------------------------------
    # Always-on (VAD) loop
    # ------------------------------------------------------------------

    def _run_always_on(self, config: dict, profile: dict, stt: WhisperSTT, speaker: Speaker) -> None:
        device = config.get("device", "cpu")
        threshold = config.get("vad_threshold", 0.5)
        sample_rate = config.get("sample_rate", 16000)

        vad = SileroVAD(
            threshold=threshold,
            device=device,
            max_silence_ms=config.get("max_silence_ms", 700),
        )

        self.log.emit(f"[{_ts()}] Always-on mode active. Speak naturally.")
        self.status.emit("LISTENING")
        speaker.say("Voice to Macro ready. Always on mode active.")

        try:
            for audio_segment in vad.stream():
                if not self._running:
                    vad.stop()
                    break

                self.status.emit("TRANSCRIBING")
                self.recording.emit(True)

                t0 = time.perf_counter()
                transcript = stt.transcribe(audio_segment, sample_rate=sample_rate)
                stt_ms = (time.perf_counter() - t0) * 1000
                self.recording.emit(False)

                self.log.emit(f"[{_ts()}] [STT] Transcribed in {stt_ms:.0f}ms")
                self._process(transcript, profile, speaker, config, None, stt)
                self.status.emit("LISTENING")
        except Exception as e:
            self.log.emit(f"[{_ts()}] [ERROR] {e}")

    # ------------------------------------------------------------------
    # Shared command processing
    # ------------------------------------------------------------------

    def _process(
        self,
        transcript: str,
        profile: dict,
        speaker: Speaker,
        config: dict,
        recorder: Optional[PTTRecorder],
        stt: WhisperSTT,
    ) -> None:
        if not transcript.strip():
            self.log.emit(f"[{_ts()}] (nothing heard — silence or hallucination)")
            self.status.emit("IDLE")
            return

        self.log.emit(f"[{_ts()}] Heard: '{transcript}'")

        # Help
        if "help" in transcript:
            speaker.help(profile)
            return

        # Learned fast-path
        learned = lookup(transcript)
        if learned:
            action_name = learned["intent"]
            self.log.emit(f"[{_ts()}] Learned match: '{transcript}' -> {action_name}")
            self.status.emit(f"EXEC: {action_name}")
            ok = dispatch_profile_action(action_name, profile)
            if ok:
                increment_uses(transcript)
                speaker.confirm(action_name)
            self.status.emit("IDLE")
            return

        # LLM / fuzzy classification
        model = config.get("model", "phi3:mini")
        confidence_threshold = config.get("confidence_threshold", 0.6)

        self.status.emit("CLASSIFYING")
        t0 = time.perf_counter()
        action_name, confidence = parse_intent(transcript, profile, model=model)
        llm_ms = (time.perf_counter() - t0) * 1000
        self.log.emit(f"[{_ts()}] Intent: '{action_name}' (confidence={confidence:.2f}) [{llm_ms:.0f}ms]")

        if action_name != "unknown" and confidence >= confidence_threshold:
            self.status.emit(f"EXEC: {action_name}")
            t1 = time.perf_counter()
            ok = dispatch_profile_action(action_name, profile)
            exec_ms = (time.perf_counter() - t1) * 1000
            if ok:
                self.log.emit(f"[{_ts()}] Executed '{action_name}' [{exec_ms:.0f}ms]")
                save_mapping(transcript, action_name, action_name, confirmed=False)
                increment_uses(transcript)
                speaker.confirm(action_name)
        else:
            self.status.emit("CLARIFYING")
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
                    self.log.emit(f"[{_ts()}] Clarified -> '{confirmed_action}'")
                    save_mapping(transcript, confirmed_action, confirmed_action, confirmed=True)
                    increment_uses(transcript)

        self.status.emit("IDLE")
