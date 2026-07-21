import os
import logging
from faster_whisper import WhisperModel

logger = logging.getLogger(__name__)

class AcousticParser:
    def __init__(self):
        self.model_size = os.environ.get("FASTER_WHISPER_MODEL", "base")
        self.device = "cuda"
        self.compute_type = os.environ.get("FASTER_WHISPER_COMPUTE", "int8")
        self._init_model()

    def _init_model(self):
        logger.info(f"Initializing acoustic parser on {self.device.upper()} ({self.compute_type})...")
        self.model = WhisperModel(
            self.model_size,
            device=self.device,
            compute_type=self.compute_type,
            cpu_threads=4
        )

    def transcribe(self, audio_path: str) -> str:
        """Transcribes audio file to clean text for AST Sieve validation."""
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        try:
            return self._run_transcription(audio_path)
        except Exception as e:
            if self.device == "cuda" and ("cublas" in str(e).lower() or "cuda" in str(e).lower() or "library" in str(e).lower()):
                logger.warning(f"CUDA exception caught during transcription: {e}. Falling back to CPU.")
                self.device = "cpu"
                self._init_model()
                return self._run_transcription(audio_path)
            raise e

    def _run_transcription(self, audio_path: str) -> str:
        segments, _ = self.model.transcribe(
            audio_path,
            language="en",
            beam_size=5,
            condition_on_previous_text=False  # Prevents repetitive hallucination loops
        )
        return " ".join([segment.text for segment in segments]).strip()

