"""
core.py — LEO command pipeline + AI provider routing
Providers: Gemini, OpenAI (ChatGPT), Anthropic (Claude), Ollama (offline)
"""
import winsound
import os
import re
import time
import threading
import requests
import json

from speech       import HorowaSpeech
from mic_listener import HorowaMic
from skills_handler import HorowaAgent as LeoAgent, execute_tool, discover_skills


# ── Provider adapters ─────────────────────────────────────────────────────────

class GeminiProvider:
    NAME = "gemini"

    def __init__(self, api_key, model, system_prompt):
        from google import genai
        self.client        = genai.Client(api_key=api_key)
        self.model         = model
        self.system_prompt = system_prompt
        self._agent        = None

    def init_agent(self, api_key, model, system_prompt,
                   confirm_cb, minimize_cb, speech_cb):
        from skills_handler import HorowaAgent as LeoAgent
        self._agent = LeoAgent(
            api_key=api_key,
            model_name=model,
            system_prompt=system_prompt,
            confirm_callback=confirm_cb,
            minimize_callback=minimize_cb,
            speech_callback=speech_cb,
            gemini_client=self.client
        )

    def chat(self, query):
        if self._agent:
            self._agent.model_name = self.model
            return self._agent.run(query)
        resp = self.client.models.generate_content(
            model=self.model,
            contents=f"{self.system_prompt}\n\nUser: {query}"
        )
        return resp.text

    def clear_memory(self):
        if self._agent: self._agent.clear_memory()

    @staticmethod
    def fetch_models(api_key):
        try:
            from google import genai
            c = genai.Client(api_key=api_key)
            models = []
            for m in c.models.list():
                actions = getattr(m, "supported_actions", None) or \
                          getattr(m, "supported_generation_methods", [])
                if "generateContent" in actions:
                    name = m.name.replace("models/", "")
                    models.append(name)
            return sorted(models) if models else ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]
        except Exception as e:
            print(f"[GEMINI MODELS] {e}")
            return ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]


class OpenAIProvider:
    NAME = "openai"

    def __init__(self, api_key, model, system_prompt):
        self.api_key       = api_key
        self.model         = model
        self.system_prompt = system_prompt
        self._history      = []

    def chat(self, query):
        self._history.append({"role": "user", "content": query})
        messages = [{"role": "system", "content": self.system_prompt}] + self._history
        try:
            resp = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}",
                         "Content-Type": "application/json"},
                json={"model": self.model, "messages": messages},
                timeout=60
            )
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"]
            self._history.append({"role": "assistant", "content": text})
            if len(self._history) > 40:
                self._history = self._history[-40:]
            return text
        except Exception as e:
            return f"OpenAI error: {e}"

    def clear_memory(self):
        self._history = []

    @staticmethod
    def fetch_models(api_key):
        try:
            resp = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=8
            )
            resp.raise_for_status()
            ids = [m["id"] for m in resp.json()["data"]
                   if "gpt" in m["id"].lower()]
            return sorted(ids, reverse=True)
        except Exception as e:
            print(f"[OPENAI MODELS] {e}")
            return ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]


class AnthropicProvider:
    NAME = "anthropic"

    def __init__(self, api_key, model, system_prompt):
        self.api_key       = api_key
        self.model         = model
        self.system_prompt = system_prompt
        self._history      = []

    def chat(self, query):
        self._history.append({"role": "user", "content": query})
        if len(self._history) > 40:
            self._history = self._history[-40:]
        try:
            resp = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key":         self.api_key,
                    "anthropic-version":  "2023-06-01",
                    "content-type":       "application/json"
                },
                json={
                    "model":      self.model,
                    "max_tokens": 2048,
                    "system":     self.system_prompt,
                    "messages":   self._history
                },
                timeout=60
            )
            resp.raise_for_status()
            text = resp.json()["content"][0]["text"]
            self._history.append({"role": "assistant", "content": text})
            return text
        except Exception as e:
            return f"Anthropic error: {e}"

    def clear_memory(self):
        self._history = []

    @staticmethod
    def fetch_models(api_key):
        try:
            resp = requests.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key":        api_key,
                    "anthropic-version": "2023-06-01"
                },
                timeout=8
            )
            resp.raise_for_status()
            return [m["id"] for m in resp.json().get("data", [])]
        except Exception as e:
            print(f"[ANTHROPIC MODELS] {e}")
            return ["claude-sonnet-4-5", "claude-opus-4-5",
                    "claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022"]


PROVIDER_MAP = {
    "gemini":    GeminiProvider,
    "openai":    OpenAIProvider,
    "anthropic": AnthropicProvider,
}


# ── Horowa Core ───────────────────────────────────────────────────────────────────

class HorowaCore:
    def __init__(self, gui_callback, amplitude_callback=None,
                 hotword_callback=None, stream_callback=None,
                 confirm_callback=None, minimize_callback=None):
        self.gui_callback     = gui_callback
        self.stream_callback  = stream_callback
        self.confirm_callback = confirm_callback
        self.minimize_callback= minimize_callback
        self.mode             = "OFFLINE"
        self._streaming_completed = False

        self.config = self._read_config()

        # System prompt lives in config.json only — no hardcoded fallback here
        self.system_prompt = self.config.get("system_prompt", "")

        # TTS
        self.speech = HorowaSpeech()

        # Mic
        self.mic = HorowaMic(
            gui_callback=gui_callback,
            amplitude_callback=amplitude_callback,
            hotword_callback=hotword_callback
        )

        # Skills
        discover_skills()

        # Online provider
        self._provider = None
        self._init_provider()

        # Offline model
        self.offline_model = self.config.get("ollama_model", "")

    # ── Config ────────────────────────────────────────────────

    def _read_config(self):
        if os.path.exists("config.json"):
            try:
                with open("config.json") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_config(self, cfg):
        with open("config.json", "w") as f:
            json.dump(cfg, f, indent=2)

    # ── Provider init ─────────────────────────────────────────

    def _init_provider(self):
        cfg      = self._read_config()
        provider = cfg.get("online_provider", "gemini")
        apis     = cfg.get("api_keys", {})
        api_key  = apis.get(provider, "")

        # fallback: read legacy api.txt for gemini
        if not api_key and provider == "gemini" and os.path.exists("api.txt"):
            with open("api.txt") as f:
                api_key = f.read().strip()

        model         = cfg.get("online_model", self._default_model(provider))
        # Always pull prompts fresh from config — no hardcoded fallbacks
        self.system_prompt         = cfg.get("system_prompt", "")
        system_prompt              = cfg.get("online_system_prompt", self.system_prompt)

        cls = PROVIDER_MAP.get(provider, GeminiProvider)
        try:
            self._provider = cls(api_key, model, system_prompt)
            if provider == "gemini":
                self._provider.init_agent(
                    api_key, model, system_prompt,
                    self.confirm_callback,
                    self.minimize_callback,
                    self.speech.speak
                )
            print(f"[PROVIDER] {provider} / {model}")
        except Exception as e:
            print(f"[PROVIDER ERROR] {e}")
            self._provider = None

    @staticmethod
    def _default_model(provider):
        defaults = {
            "gemini":    "gemini-2.5-flash-lite",
            "openai":    "gpt-4o-mini",
            "anthropic": "claude-sonnet-4-5",
        }
        return defaults.get(provider, "")

    def reload_provider(self):
        """Call after saving API settings to hot-swap the provider."""
        self.config = self._read_config()
        self._init_provider()

    # ── Mic proxy properties (main.py compatibility) ──────────

    @property
    def mic_active(self):
        return self.mic.active

    @mic_active.setter
    def mic_active(self, v):
        self.mic.active = v

    @property
    def hotword_active(self):
        return self.mic.hotword_active

    @hotword_active.setter
    def hotword_active(self, v):
        self.mic.hotword_active = v

    def start_mic(self):
        self.mic.start()

    # ── Speech proxy (main.py compatibility) ──────────────────

    def add_to_speech(self, text):
        self.speech.speak(text)

    def interrupt_speech(self):
        self.speech.interrupt()

    # ── Ollama streaming ──────────────────────────────────────

    def _ollama_stream(self, query, speaker_on=True):
        cfg   = self._read_config()
        model = cfg.get("ollama_model", "") or self.offline_model
        if not model:
            return "No offline model configured. Set one in Settings → Local Model."

        url        = cfg.get("ollama_url", "http://localhost:11434")
        sys_prompt = cfg.get("system_prompt", self.system_prompt)

        payload = {
            "model":  model,
            "prompt": f"{sys_prompt}\n\nUser: {query}\nLEO:",
            "stream": True,
            "options": {
                "temperature":    cfg.get("temperature",    0.7),
                "top_p":          cfg.get("top_p",          0.9),
                "top_k":          cfg.get("top_k",          40),
                "repeat_penalty": cfg.get("repeat_penalty", 1.1),
                "num_ctx":        cfg.get("context_length", 4096),
                "num_gpu":        cfg.get("num_gpu_layers", -1),
                "num_thread":     cfg.get("num_threads",    4),
                "seed":           cfg.get("seed",           -1),
            },
            "keep_alive": cfg.get("keep_alive", "5m"),
        }

        full_text = ""; sentence_buf = ""
        sentence_end = re.compile(r'([.!?]+)\s')

        try:
            with requests.post(f"{url}/api/generate",
                               json=payload, stream=True, timeout=60) as resp:
                if resp.status_code != 200:
                    return f"Ollama error {resp.status_code}: {resp.text[:200]}"
                for raw_line in resp.iter_lines():
                    if not raw_line: continue
                    try:    chunk = json.loads(raw_line)
                    except: continue
                    token = chunk.get("response", "")
                    full_text    += token
                    sentence_buf += token
                    if self.stream_callback:
                        self.stream_callback(token)
                    if speaker_on:
                        while True:
                            m = sentence_end.search(sentence_buf)
                            if not m: break
                            self.speech.speak(sentence_buf[:m.end()].strip())
                            sentence_buf = sentence_buf[m.end():]
                    if chunk.get("done"): break
        except requests.exceptions.ConnectionError:
            return "Ollama not running. Start it with: ollama serve"
        except Exception as e:
            return f"Ollama stream error: {e}"

        if speaker_on and sentence_buf.strip():
            self.speech.speak(sentence_buf.strip())

        self._streaming_completed = True
        return full_text.strip()

    # ── Online AI response ────────────────────────────────────

    def get_ai_response(self, query, speaker_on=True):
        self._init_provider()   # pick up any config changes
        try:
            if self.mode == "ONLINE":
                if not self._provider:
                    return "No online provider configured. Add an API key in Settings → API."
                return self._provider.chat(query)
            else:
                return self._ollama_stream(query, speaker_on=speaker_on)
        except Exception as e:
            return f"AI error: {e}"

    # ── Fast path ───────

    def _fast_path(self, query):
        lower = query.lower().strip()

        vol_match = (re.search(r'volume\s+(?:to\s+)?(\d{1,3})', lower) or
                     re.search(r'(?:set|turn)\s+(?:the\s+)?volume\s+(?:to\s+)?(\d{1,3})', lower))
        if vol_match:
            level = max(0, min(100, int(vol_match.group(1))))
            execute_tool("set_volume", {"level": level})
            return f"Audio fidelity locked at {level} percent."

        if lower in ("mute","mute volume","silence"):
            execute_tool("set_volume", {"level": 0}); return "System muted."
        if lower in ("new tab","open tab","tab"):
            execute_tool("browser_control", {"action":"new_tab"}); return "New tab opened."
        if lower in ("new window","open window","window"):
            execute_tool("browser_control", {"action":"new_window"}); return "New window opened."
        if lower in ("close tab","close this tab"):
            execute_tool("browser_control", {"action":"close_tab"}); return "Tab closed."
        if lower in ("refresh","reload"):
            execute_tool("browser_control", {"action":"refresh"}); return "Page refreshed."
        if "battery"  in lower: return execute_tool("get_system_info", {"info_type":"battery"})
        if "cpu"      in lower or "processor" in lower:
            return execute_tool("get_system_info", {"info_type":"cpu"})
        if "ram"      in lower or "memory" in lower:
            return execute_tool("get_system_info", {"info_type":"ram"})
        if "disk"     in lower or "storage" in lower or "drive" in lower:
            return execute_tool("get_system_info", {"info_type":"disk"})

        folder_match = re.search(
            r'(?:create|make)\s+(?:a\s+)?folder\s+(?:in\s+|at\s+|called\s+)?'
            r'([A-Za-z]:[\\\/][^\s,]+|[\\\/][^\s,]+|[\w\-]+)', lower)
        if folder_match:
            orig = re.search(
                r'(?:create|make)\s+(?:a\s+)?folder\s+(?:in\s+|at\s+|called\s+)?'
                r'([A-Za-z]:[\\\/]\S+|[\\\/]\S+|\S+)', query, re.IGNORECASE)
            path = orig.group(1).rstrip('.,') if orig else folder_match.group(1)
            return execute_tool("create_folder", {"path": path},
                                confirm_callback=self.confirm_callback)

        fc = re.search(r'(?:create|make|write)\s+(?:a\s+)?file\s+(?:at\s+|in\s+|called\s+)?(\S+)',
                       query, re.IGNORECASE)
        if fc:
            return execute_tool("write_file",
                                {"path": fc.group(1).rstrip('.,'), "content": ""},
                                confirm_callback=self.confirm_callback)

        rm = re.search(r'(?:read|open|show)\s+(?:the\s+)?file\s+(?:at\s+|in\s+)?(\S+)',
                       query, re.IGNORECASE)
        if rm:
            return execute_tool("read_file", {"path": rm.group(1).rstrip('.,')})

        lm = re.search(
            r'(?:list|show|what(?:\'s| is) in)\s+(?:the\s+)?(?:folder\s+|directory\s+)?'
            r'([A-Za-z]:[\\\/]\S+|[\\\/]\S+)', query, re.IGNORECASE)
        if lm:
            return execute_tool("list_folder", {"path": lm.group(1).rstrip('.,')})

        om = re.search(r'^open\s+(\w[\w\s]*?)$', lower)
        if om:
            execute_tool("open_app", {"app_name": om.group(1).strip()},
                         minimize_callback=self.minimize_callback)
            return f"Accessing {om.group(1).strip()}."

        sm = re.search(r'(?:search|google|look up)\s+(?:for\s+)?(.+)', lower)
        if sm:
            q = sm.group(1).strip()
            execute_tool("search_web", {"query": q})
            return f"Searching for: {q}"

        um = re.search(r'(?:open|go to|visit)\s+((?:https?://)?[\w\-]+\.[\w\-./]+)', lower)
        if um:
            execute_tool("open_url", {"url": um.group(1)})
            return f"Opening {um.group(1)}."

        if lower in ("clear memory", "forget everything", "reset memory"):
            if self._provider: self._provider.clear_memory()
            return "Memory cleared. Starting fresh."

        return None

    # ── Command pipeline ──────────────────────────────────────

    def process_command(self, query, speaker_on=True):
        self.interrupt_speech()
        winsound.Beep(800, 40)
        lower = query.lower()

        if "switch to online" in lower:
            self.mode = "ONLINE"
            cfg   = self._read_config()
            pname = cfg.get("online_provider", "gemini")
            model = cfg.get("online_model", self._default_model(pname))
            return f"Neural link established. {pname.title()} / {model} active."
        if "switch to offline" in lower:
            self.mode = "OFFLINE"
            return f"Satellite link severed. Offline model: {self.offline_model or 'not set'}."
        if "hey horowa" in lower:
            return None

        fast = self._fast_path(query)
        if fast: return fast

        return self.get_ai_response(query, speaker_on=speaker_on)
