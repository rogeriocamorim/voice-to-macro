"""
vad/silero_vad.py — Voice Activity Detection using Silero VAD.

Used in always_on mode to detect when the user is speaking
without requiring a push-to-talk key. Buffers audio from the
microphone and yields complete speech segments as numpy arrays.
"""

import queue
import threading
import numpy as np
from typing import Generator, Optional


class SileroVAD:
    """
    Streams audio from the microphone and yields speech segments.

    Uses Silero VAD model to detect start/end of speech.
    Runs in a background thread, feeding audio chunks into a queue.

    Parameters
    ----------
    sample_rate : int
        Must be 16000 for Silero VAD.
    threshold : float
        Speech probability threshold (0.0–1.0). Default 0.5.
    min_speech_ms : int
        Minimum speech duration to be considered a command (ms).
    max_silence_ms : int
        Silence duration that ends a speech segment (ms).
    device : str
        'cuda' or 'cpu'.
    """

    SAMPLE_RATE = 16000
    CHUNK_SIZE = 512  # samples per chunk (Silero requires 512 @ 16kHz)

    def __init__(
        self,
        threshold: float = 0.5,
        min_speech_ms: int = 300,
        max_silence_ms: int = 700,
        device: str = "cpu",
    ):
        self.threshold = threshold
        self.min_speech_samples = int(self.SAMPLE_RATE * min_speech_ms / 1000)
        self.max_silence_samples = int(self.SAMPLE_RATE * max_silence_ms / 1000)
        self.device = device
        self._model = None
        self._audio_queue: queue.Queue = queue.Queue()
        self._stop_event = threading.Event()

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch  # type: ignore

        # Verify CUDA is actually available in this torch build — fall back to CPU silently
        if self.device == "cuda" and not torch.cuda.is_available():
            print("[VAD] CUDA requested but not available in this torch build — falling back to CPU.")
            self.device = "cpu"

        print("[VAD] Loading Silero VAD model...")
        model, _ = torch.hub.load(
            repo_or_dir="snakers4/silero-vad",
            model="silero_vad",
            force_reload=False,
            trust_repo=True,
        )
        self._model = model.to(self.device)
        print("[VAD] Model ready.")

    def _get_speech_prob(self, chunk: np.ndarray) -> float:
        import torch  # type: ignore
        tensor = torch.from_numpy(chunk).float()
        if self.device == "cuda":
            tensor = tensor.cuda()
        with torch.no_grad():
            prob = self._model(tensor, self.SAMPLE_RATE).item()
        return prob

    def _mic_callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        """sounddevice callback — puts raw audio into the queue."""
        audio = indata[:, 0].copy() if indata.ndim == 2 else indata.copy()
        self._audio_queue.put(audio.astype(np.float32))

    def stream(self) -> Generator[np.ndarray, None, None]:
        """
        Generator that yields complete speech segments as float32 numpy arrays.
        Blocks until a speech segment is detected, then yields it.

        Usage
        -----
        for segment in vad.stream():
            text = stt.transcribe(segment)
            ...
        """
        import sounddevice as sd  # type: ignore

        self._load()
        self._stop_event.clear()

        speech_buffer: list[np.ndarray] = []
        silence_samples = 0
        in_speech = False

        with sd.InputStream(
            samplerate=self.SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=self.CHUNK_SIZE,
            callback=self._mic_callback,
        ):
            print("[VAD] Listening (always-on mode)...")
            while not self._stop_event.is_set():
                try:
                    chunk = self._audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                prob = self._get_speech_prob(chunk)

                if prob >= self.threshold:
                    in_speech = True
                    silence_samples = 0
                    speech_buffer.append(chunk)
                elif in_speech:
                    speech_buffer.append(chunk)
                    silence_samples += len(chunk)
                    if silence_samples >= self.max_silence_samples:
                        segment = np.concatenate(speech_buffer)
                        if len(segment) >= self.min_speech_samples:
                            yield segment
                        # Reset
                        speech_buffer = []
                        silence_samples = 0
                        in_speech = False

    def stop(self) -> None:
        """Signal the stream generator to stop."""
        self._stop_event.set()


# ---------------------------------------------------------------------------
# PTT (push-to-talk) audio capture — used when mode == 'ptt'
# ---------------------------------------------------------------------------

class PTTRecorder:
    """
    Records audio while a key is held down.
    Returns the recorded audio as a float32 numpy array when the key is released.

    Parameters
    ----------
    ptt_key : str
        Key name as returned by pynput (e.g. 'caps_lock', 'f13').
    sample_rate : int
        Recording sample rate (16000 recommended).
    """

    def __init__(self, ptt_key: str = "caps_lock", sample_rate: int = 16000):
        self.ptt_key = ptt_key.lower()
        self.sample_rate = sample_rate
        self._recording = False
        self._buffer: list[np.ndarray] = []
        self._lock = threading.Lock()

    def _normalize_key(self, key) -> str:
        from pynput import keyboard as kb  # type: ignore
        try:
            return key.char.lower() if key.char else ""
        except AttributeError:
            return str(key).replace("Key.", "").lower()

    def _mic_callback(self, indata: np.ndarray, frames: int, time, status) -> None:
        if self._recording:
            with self._lock:
                self._buffer.append(indata[:, 0].copy().astype(np.float32))

    def record(self) -> Optional[np.ndarray]:
        """
        Blocks until PTT key is pressed, records while held, returns audio on release.
        Returns None if no audio was captured.
        """
        import sounddevice as sd  # type: ignore
        from pynput import keyboard as kb  # type: ignore

        pressed_event = threading.Event()
        released_event = threading.Event()

        def on_press(key):
            if self._normalize_key(key) == self.ptt_key:
                if not self._recording:
                    self._recording = True
                    self._buffer.clear()
                    pressed_event.set()

        def on_release(key):
            if self._normalize_key(key) == self.ptt_key and self._recording:
                self._recording = False
                released_event.set()
                return False  # stop listener

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=512,
            callback=self._mic_callback,
        ):
            with kb.Listener(on_press=on_press, on_release=on_release) as listener:
                listener.join()

        with self._lock:
            if not self._buffer:
                return None
            return np.concatenate(self._buffer)
