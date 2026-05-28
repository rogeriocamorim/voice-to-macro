"""
stt/whisper_stt.py — Speech-to-text using faster-whisper.

Wraps the WhisperModel to transcribe raw audio (numpy float32 array)
into a text string. Designed to be cheap to import and re-use across calls.

Quality levers applied:
  - beam_size=5         : much better accuracy vs greedy (beam_size=1), tiny GPU cost
  - initial_prompt      : inject game action vocabulary so Whisper recognises
                          domain words like "hyperdrive", "FSD", "quantum drive"
  - audio normalisation : peak-normalise mic input so quiet/loud voices
                          both land in Whisper's optimal input range
  - language="en"       : force language, skip auto-detect overhead
"""

import os
import re
import warnings
import numpy as np
from typing import Optional

# Suppress huggingface_hub symlink and auth warnings (cosmetic, no functional impact)
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_IMPLICIT_TOKEN", "1")
warnings.filterwarnings("ignore", message=".*symlinks.*")
warnings.filterwarnings("ignore", message=".*unauthenticated.*")


# ---------------------------------------------------------------------------
# Hallucination filter
# ---------------------------------------------------------------------------

# Whisper hallucinates these patterns when given silence or very short noise.
# Any transcript matching these patterns is treated as empty.
_HALLUCINATION_PATTERNS = [
    re.compile(r"^[_\s]+$"),                          # all underscores/spaces: "__ __ __"
    re.compile(r"(_\s*){4,}"),                        # 4+ repeated underscore tokens
    re.compile(r"^[\.\,\!\?\s]+$"),                   # only punctuation
    re.compile(r"(thank you\.?\s*){2,}", re.I),       # repeated "thank you"
    re.compile(r"(you\.?\s*){3,}", re.I),             # repeated "you"
    re.compile(r"^\s*(\.{2,}|…)\s*$"),               # ellipsis only
]

def _is_hallucination(text: str) -> bool:
    """Return True if the transcript looks like a Whisper hallucination."""
    if not text.strip():
        return True
    for pattern in _HALLUCINATION_PATTERNS:
        if pattern.search(text):
            return True
    return False


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _normalize_audio(audio: np.ndarray) -> np.ndarray:
    """
    Peak-normalise audio to [-1, 1].
    Prevents quiet mic input from degrading Whisper accuracy.
    If audio is silent (all zeros), returns as-is.
    """
    peak = np.abs(audio).max()
    if peak > 0:
        audio = audio / peak * 0.95   # 0.95 leaves a small headroom
    return audio


def _build_initial_prompt(profile: Optional[dict]) -> str:
    """
    Build a Whisper initial_prompt from the active game profile.

    Whisper uses this as prior context — injecting action names and
    descriptions biases the transcription towards game vocabulary,
    dramatically improving recognition of domain-specific words.

    Example output:
      "hyperdrive, FSD jump, landing gear, silent running, boost, shields"
    """
    if not profile:
        return ""

    actions = profile.get("actions", {})
    terms = set()

    for name, meta in actions.items():
        # Add the action name (spaces, not underscores)
        terms.add(name.replace("_", " "))
        # Add significant words from the description (skip short stop words)
        desc = meta.get("description", "")
        for word in desc.split():
            if len(word) > 3 and word.lower() not in {"your", "the", "and", "for", "with"}:
                terms.add(word.lower())

    # Also add the game name itself
    game = profile.get("game", "")
    if game:
        terms.add(game)

    return ", ".join(sorted(terms))


# ---------------------------------------------------------------------------
# WhisperSTT
# ---------------------------------------------------------------------------

class WhisperSTT:
    """
    Lightweight wrapper around faster-whisper's WhisperModel.

    Parameters
    ----------
    model_size : str
        Whisper model size: tiny | base | small | medium | large-v3
        Recommendation: large-v3 on GPU, small/medium on CPU.
    device : str
        'cuda' or 'cpu'
    compute_type : str or None
        'float16' (GPU) or 'int8' (CPU). Auto-selected if None.
    language : str
        ISO language code, e.g. 'en'. Forced — no auto-detect overhead.
    beam_size : int
        Beam search width. 5 gives much better accuracy than 1 (greedy)
        at minimal GPU cost. Lower if latency is critical on CPU.
    profile : dict or None
        Active game profile. Used to build the initial_prompt vocabulary hint.
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: Optional[str] = None,
        language: str = "en",
        beam_size: int = 5,
        profile: Optional[dict] = None,
    ):
        self.language = language
        self.beam_size = beam_size
        self._model = None
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type  # resolved in _load()
        self._initial_prompt = _build_initial_prompt(profile)

        if self._initial_prompt:
            print(f"[STT] Vocabulary hint: {self._initial_prompt[:80]}{'...' if len(self._initial_prompt) > 80 else ''}")

    def update_profile(self, profile: dict) -> None:
        """Rebuild initial_prompt when the active profile changes."""
        self._initial_prompt = _build_initial_prompt(profile)

    def _load(self) -> None:
        """Lazy-load the model on first transcription call."""
        if self._model is not None:
            return

        # Verify CUDA is actually available — fall back to CPU silently
        if self._device == "cuda":
            import torch  # type: ignore
            if not torch.cuda.is_available():
                print("[STT] CUDA requested but not available in this torch build — falling back to CPU.")
                self._device = "cpu"
                self._compute_type = "int8"
                # large-v3 on CPU is impractically slow — downgrade automatically
                if self._model_size == "large-v3":
                    print("[STT] Downgrading to 'medium' for CPU — large-v3 is too slow without GPU.")
                    self._model_size = "medium"

        if self._compute_type is None:
            self._compute_type = "float16" if self._device == "cuda" else "int8"

        from faster_whisper import WhisperModel  # type: ignore
        print(f"[STT] Loading Whisper '{self._model_size}' on {self._device} ({self._compute_type})...")
        self._model = WhisperModel(
            self._model_size,
            device=self._device,
            compute_type=self._compute_type,
        )
        print("[STT] Model ready.")

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> str:
        """
        Transcribe a numpy float32 audio array into text.

        Parameters
        ----------
        audio : np.ndarray
            Float32 mono audio array, values in [-1.0, 1.0].
        sample_rate : int
            Sample rate of the audio (faster-whisper expects 16000 Hz).

        Returns
        -------
        str
            The transcribed text (stripped, lowercased).
        """
        self._load()

        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)

        # Resample if necessary
        if sample_rate != 16000:
            import math
            ratio = 16000 / sample_rate
            new_len = math.ceil(len(audio) * ratio)
            audio = np.interp(
                np.linspace(0, len(audio) - 1, new_len),
                np.arange(len(audio)),
                audio,
            ).astype(np.float32)

        # Peak-normalise — ensures quiet/loud mic input is always in range
        audio = _normalize_audio(audio)

        segments, _info = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=self.beam_size,
            vad_filter=False,           # VAD handled separately by silero
            initial_prompt=self._initial_prompt or None,
            condition_on_previous_text=False,  # each command is independent
            temperature=0.0,            # deterministic — no need for sampling
        )

        text = " ".join(seg.text for seg in segments).strip().lower()

        if _is_hallucination(text):
            return ""

        return text

    def transcribe_file(self, path: str) -> str:
        """Convenience method to transcribe an audio file path."""
        import soundfile as sf  # type: ignore
        audio, sr = sf.read(path, dtype="float32", always_2d=False)
        if audio.ndim == 2:
            audio = audio.mean(axis=1)  # stereo → mono
        return self.transcribe(audio, sample_rate=sr)
