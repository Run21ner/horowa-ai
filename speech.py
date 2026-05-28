"""
speech.py — LEO TTS engine
Persistent pyttsx3/SAPI5 on a dedicated COM thread.
Win11 fix: uses startLoop(False)/iterate()/endLoop() instead of runAndWait().
"""
import pyttsx3
import pythoncom
import threading
import queue
import time


class HorowaSpeech:
    def __init__(self):
        self._queue      = queue.Queue()
        self._stop_event = threading.Event()
        threading.Thread(target=self._worker, daemon=True).start()

    # ── Public API ────────────────────────────────────────────

    def speak(self, text: str):
        """Queue text for speech. Skips code/error lines."""
        if not text or not text.strip():
            return
        lower = text.lower()
        skip  = ["link failure", "error", "exception", "traceback",
                 "```", "def ", "import "]
        if any(kw in lower for kw in skip):
            return
        self._queue.put(text)

    def interrupt(self):
        """Stop current speech and discard queued items."""
        self._stop_event.set()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except Exception:
                break

    # ── Internal worker ───────────────────────────────────────

    def _worker(self):
        pythoncom.CoInitialize()
        engine = None

        def _init():
            nonlocal engine
            try:
                eng = pyttsx3.init('sapi5')
                eng.setProperty('rate', 175)
                eng.setProperty('volume', 1.0)
                for v in eng.getProperty('voices'):
                    if "david" in v.name.lower() or "zira" in v.name.lower():
                        eng.setProperty('voice', v.id)
                        break
                engine = eng
            except Exception as e:
                print(f"[SPEECH INIT] {e}")
                engine = None

        _init()

        while True:
            text = self._queue.get()
            if not text:
                self._queue.task_done()
                continue

            self._stop_event.clear()

            try:
                if engine is None:
                    _init()
                if engine is None:
                    self._queue.task_done()
                    continue

                engine.say(text)
                engine.startLoop(False)
                while engine.isBusy():
                    if self._stop_event.is_set():
                        engine.stop()
                        break
                    engine.iterate()
                    time.sleep(0.02)
                engine.endLoop()

            except Exception as e:
                print(f"[SPEECH ERROR] {e}")
                try:    engine.stop()
                except: pass
                engine = None
                _init()
            finally:
                self._queue.task_done()
