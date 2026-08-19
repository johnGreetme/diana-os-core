import asyncio
import io
import time
import logging
import pyautogui
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

# Enforce pyautogui fail-safe (moving mouse to top-left corner aborts execution)
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1

class VisualActuator:
    def __init__(self):
        pass

    def click_text_target(self, target_text: str, double_click: bool = False) -> str:
        """Locates target_text on screen using Tesseract OCR (Linux Native) and clicks its center."""
        try:
            return asyncio.run(self._async_click_text_target(target_text, double_click))
        except Exception as e:
            return f"[GUI ERROR] Actuation failed: {str(e)}"

    async def _async_click_text_target(self, target_text: str, double_click: bool) -> str:
        def _find_and_click():
            # 1. Take full-screen screenshot
            screenshot = pyautogui.screenshot()
            
            # 2. Run Tesseract OCR scan over image buffer
            data = pytesseract.image_to_data(screenshot, output_type=pytesseract.Output.DICT)
            
            # 3. Search for matching text bounding box
            target_lower = target_text.lower().strip()
            match_rect = None
            
            for i, text in enumerate(data['text']):
                if target_lower in text.lower():
                    # Check confidence
                    if int(data['conf'][i]) > 30:
                        x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                        match_rect = {'x': x, 'y': y, 'width': w, 'height': h}
                        break
            
            if not match_rect:
                return f"[GUI ERROR] Target text '{target_text}' was not found on screen."
                
            # 4. Calculate geometric center coordinates
            center_x = int(match_rect['x'] + (match_rect['width'] / 2))
            center_y = int(match_rect['y'] + (match_rect['height'] / 2))
            
            # 5. Take physical control of mouse
            pyautogui.moveTo(center_x, center_y, duration=0.2, tween=pyautogui.easeOutQuad)
            if double_click:
                pyautogui.doubleClick()
            else:
                pyautogui.click()
                
            # Brief sleep for screen state changes to settle
            time.sleep(0.5)
            
            return f"[GUI SUCCESS] Clicked '{target_text}' at coordinates ({center_x}, {center_y})."
            
        return await asyncio.to_thread(_find_and_click)

    def type_text(self, text: str) -> str:
        """Types the specified text via the keyboard."""
        try:
            pyautogui.write(text, interval=0.05)
            time.sleep(0.5)
            return f"[GUI SUCCESS] Typed text: '{text}'"
        except Exception as e:
            return f"[GUI ERROR] Failed to type text: {str(e)}"

    def press_key(self, key: str) -> str:
        """Presses a specific keyboard key (e.g., 'enter', 'tab', 'pagedown')."""
        try:
            pyautogui.press(key)
            time.sleep(0.5)
            return f"[GUI SUCCESS] Pressed key: '{key}'"
        except Exception as e:
            return f"[GUI ERROR] Failed to press key '{key}': {str(e)}"

    def scroll(self, clicks: int) -> str:
        """Scrolls the mouse wheel. Positive clicks scroll up, negative scroll down."""
        try:
            pyautogui.scroll(clicks)
            time.sleep(0.5)
            direction = "up" if clicks > 0 else "down"
            return f"[GUI SUCCESS] Scrolled {direction} by {abs(clicks)} clicks"
        except Exception as e:
            return f"[GUI ERROR] Failed to scroll: {str(e)}"
