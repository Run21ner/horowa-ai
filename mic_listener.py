"""
mic_listener.py — LEO microphone loop
Hotword detection ("Hey Horowa") → command listening.
Amplitude callbacks drive the sphere animation.
"""
import speech_recognition as sr
import threading
import time


class HorowaMic:
    def __init__(self, gui_callback, amplitude_callback=None,
                 hotword_callback=None):
        self.gui_callback       = gui_callback
        self.amplitude_callback = amplitude_callback
        self.hotword_callback   = hotword_callback
        self.active             = True
        self.hotword_active     = True
        self._thread            = None

    # ── Public API ────────────────────────────────────────────

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self.active = False

    # ── Internal loop ─────────────────────────────────────────

    def _loop(self):
        r = sr.Recognizer()
        r.dynamic_energy_threshold = True
        r.energy_threshold         = 2500
        hotword_triggered          = not self.hotword_active
        print("[MIC] Listener started")

        while self.active:
            try:
                with sr.Microphone() as source:
                    r.adjust_for_ambient_noise(source, duration=0.2)

                    # ── Hotword gate ──────────────────────────
                    if not hotword_triggered and self.hotword_active:
                        self._amp(False)
                        audio = r.listen(source, phrase_time_limit=3)
                        try:
                            phrase = r.recognize_google(audio).lower()
                            if "hey horowa" in phrase or "hey, horowa" in phrase:
                                hotword_triggered = True
                                if self.hotword_callback:
                                    self.hotword_callback()
                        except:
                            pass

                    # ── Command mode ──────────────────────────
                    else:
                        self._amp(True, 0.3)
                        audio = r.listen(source, phrase_time_limit=6)
                        amp   = min(1.0, len(audio.get_raw_data()) / 80000)
                        self._amp(True, amp)
                        try:
                            command = r.recognize_google(audio).lower()
                            self._amp(False)
                            if "hey horowa" not in command:
                                self.gui_callback(command, "VOICE")
                        except:
                            self._amp(False)

            except Exception as e:
                print(f"[MIC ERROR] {e}")
                self._amp(False)
                time.sleep(0.5)

    def _amp(self, active, level=0.0):
        if self.amplitude_callback:
            self.amplitude_callback(active, level)
