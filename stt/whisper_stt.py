"""
stt/whisper_stt.py — Speech-to-text using faster-whisper.

Wraps the WhisperModel to transcribe raw audio (numpy float32 array)
into a text string. Designed to be cheap to import and re-use across calls.
"""

import numpy as np
from typing import Optional


class WhisperSTT:
    """
    Lightweight wrapper around faster-whisper's WhisperModel.

    Parameters
    ----------
    model_size : str
        Whisper model size: tiny | base | small | medium
    device : str
        'cuda' or 'cpu'
    compute_type : str
        'float16' (GPU) or 'int8' (CPU, quantized)
    language : str
        ISO language code, e.g. 'en'. None = auto-detect.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: Optional[str] = None,
        language: str = "en",
    ):
        self.language = language
        self._model = None
        self._model_size = model_size
        self._device = device
        # compute_type is resolved at load time after CUDA verification
        self._compute_type = compute_type  # None = decide in _load()

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

        if self._compute_type is None:
            self._compute_type = "float16" if self._device == "cuda" else "int8"

        from faster_whisper import WhisperModel  # type: ignore
        print(f"[STT] Loading Whisper '{self._model_size}' on {self._device}...")
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

        # Resample if necessary (basic linear — for proper use, consider resampy)
        if sample_rate != 16000:
            import math
            ratio = 16000 / sample_rate
            new_len = math.ceil(len(audio) * ratio)
            audio = np.interp(
                np.linspace(0, len(audio) - 1, new_len),
                np.arange(len(audio)),
                audio,
            ).astype(np.float32)

        segments, _info = self._model.transcribe(
            audio,
            language=self.language,
            beam_size=1,           # fast, sufficient for short commands
            vad_filter=False,      # VAD handled separately by silero
        )

        text = " ".join(seg.text for seg in segments).strip().lower()
        return text

    def transcribe_file(self, path: str) -> str:
        """Convenience method to transcribe an audio file path."""
        import soundfile as sf  # type: ignore
        audio, sr = sf.read(path, dtype="float32", always_2d=False)
        if audio.ndim == 2:
            audio = audio.mean(axis=1)  # stereo → mono
        return self.transcribe(audio, sample_rate=sr)
