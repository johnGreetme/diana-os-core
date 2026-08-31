import io
import os
import logging
import asyncio

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import mss
except ImportError:
    mss = None

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import ollama
except ImportError:
    ollama = None

logger = logging.getLogger(__name__)

class OpticParser:
    def __init__(self, model_name: str = "moondream"):
        self.model_name = model_name

    def capture_screen(self) -> bytes:
        """Captures the primary monitor and returns JPEG image bytes."""
        with mss.mss() as sct:
            monitor = sct.monitors[1]  # Primary monitor
            sct_img = sct.grab(monitor)
            
            # Convert to PIL Image
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            
            # Save to byte buffer
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return buffer.getvalue()

    def capture_webcam(self, device_index: int = 0) -> bytes:
        """Captures a single frame from the specified camera device."""
        cap = cv2.VideoCapture(device_index)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open video device at index {device_index}")

        try:
            # Warm up camera sensor with a few reads
            for _ in range(5):
                ret, frame = cap.read()

            if not ret or frame is None:
                raise RuntimeError("Failed to read frame from webcam.")

            # Convert BGR (OpenCV) to RGB (PIL)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(rgb_frame)

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return buffer.getvalue()

        finally:
            cap.release()

    async def analyze_frame(self, image_bytes: bytes, prompt: str = "Describe what is visible in this image in detail.") -> str:
        """Sends image bytes to local Moondream model via Ollama with VRAM management."""
        try:
            def _generate():
                return ollama.generate(
                    model=self.model_name,
                    prompt=prompt,
                    images=[image_bytes],
                    options={
                        "num_gpu": 99,
                        "num_thread": 4,
                        "low_vram": False
                    },
                    keep_alive="3m"  # Unload from VRAM after 3 mins
                )
            
            response = await asyncio.to_thread(_generate)
            return response.get("response", "").strip()
        except Exception as e:
            logger.error(f"Ollama vision error: {e}")
            raise RuntimeError(f"VLM analysis failed: {e}")
