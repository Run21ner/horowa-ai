import subprocess
import webbrowser
import os
import pyautogui
import sys
import time
import threading
import base64
import re
from google import genai
from google.genai import types

TOOLS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="open_app",
            description="Open any application on the computer by name",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "app_name": types.Schema(type=types.Type.STRING, description="Name of the app to open")
                },
                required=["app_name"]
            )
        ),
        types.FunctionDeclaration(
            name="open_url",
            description="Open a URL or website in the default browser",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "url": types.Schema(type=types.Type.STRING, description="Full URL to open")
                },
                required=["url"]
            )
        ),
        types.FunctionDeclaration(
            name="search_web",
            description="Search Google for something and open results in browser",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "query": types.Schema(type=types.Type.STRING, description="Search query")
                },
                required=["query"]
            )
        ),
        types.FunctionDeclaration(
            name="set_volume",
            description="Set the system volume to a percentage between 0 and 100",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "level": types.Schema(type=types.Type.INTEGER, description="Volume level 0-100")
                },
                required=["level"]
            )
        ),
        types.FunctionDeclaration(
            name="run_command",
            description="Run a safe Windows shell command for system info or diagnostics. Never destructive.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "command": types.Schema(type=types.Type.STRING, description="Shell command to run"),
                    "reason": types.Schema(type=types.Type.STRING, description="Why this command is needed")
                },
                required=["command", "reason"]
            )
        ),
        types.FunctionDeclaration(
            name="read_file",
            description="Read contents of a file",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(type=types.Type.STRING, description="Full file path to read")
                },
                required=["path"]
            )
        ),
        types.FunctionDeclaration(
            name="write_file",
            description="Write or create a file with given content. Requires user approval.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(type=types.Type.STRING, description="Full file path"),
                    "content": types.Schema(type=types.Type.STRING, description="Content to write")
                },
                required=["path", "content"]
            )
        ),
        types.FunctionDeclaration(
            name="list_folder",
            description="List files and folders inside a directory",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(type=types.Type.STRING, description="Folder path to list")
                },
                required=["path"]
            )
        ),
        types.FunctionDeclaration(
            name="create_folder",
            description="Create a new folder. Requires user approval.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "path": types.Schema(type=types.Type.STRING, description="Folder path to create")
                },
                required=["path"]
            )
        ),
        types.FunctionDeclaration(
            name="type_text",
            description="Type text into the currently active window",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "text": types.Schema(type=types.Type.STRING, description="Text to type")
                },
                required=["text"]
            )
        ),
        types.FunctionDeclaration(
            name="browser_control",
            description="Control the browser: new_tab, new_window, close_tab, refresh",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "action": types.Schema(type=types.Type.STRING, description="new_tab, new_window, close_tab, or refresh")
                },
                required=["action"]
            )
        ),
        types.FunctionDeclaration(
            name="get_system_info",
            description="Get system information like battery, CPU usage, RAM, or disk space",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "info_type": types.Schema(type=types.Type.STRING, description="battery, cpu, ram, or disk")
                },
                required=["info_type"]
            )
        ),
        types.FunctionDeclaration(
            name="set_reminder",
            description="Set a reminder. LEO will speak the message aloud after the given number of seconds.",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "seconds": types.Schema(type=types.Type.INTEGER, description="Seconds from now to trigger the reminder"),
                    "message": types.Schema(type=types.Type.STRING, description="The reminder message to speak")
                },
                required=["seconds", "message"]
            )
        ),
        types.FunctionDeclaration(
            name="clipboard_read",
            description="Read the current contents of the system clipboard",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={}
            )
        ),
        types.FunctionDeclaration(
            name="clipboard_write",
            description="Write text to the system clipboard",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "text": types.Schema(type=types.Type.STRING, description="Text to copy to clipboard")
                },
                required=["text"]
            )
        ),
        types.FunctionDeclaration(
            name="screenshot_describe",
            description="Take a screenshot of the screen and describe what is visible using AI vision",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={}
            )
        ),
        types.FunctionDeclaration(
            name="media_control",
            description="Control media playback: play_pause, next_track, prev_track, volume_up, volume_down, mute",
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "action": types.Schema(
                        type=types.Type.STRING,
                        description="play_pause, next_track, prev_track, volume_up, volume_down, or mute"
                    )
                },
                required=["action"]
            )
        ),
    ])
]

NEEDS_APPROVAL = {"write_file", "create_folder", "run_command"}

# Global speech callback — set by LeoCore after init
_speech_callback = None

def set_speech_callback(fn):
    global _speech_callback
    _speech_callback = fn

# Global Gemini client ref for screenshot_describe — set by LeoCore
_gemini_client = None
_gemini_model  = None

def set_gemini_refs(client, model):
    global _gemini_client, _gemini_model
    _gemini_client = client
    _gemini_model  = model


def execute_tool(name, args, confirm_callback=None, minimize_callback=None):
    try:
        # --- approval gate ---
        if name in NEEDS_APPROVAL and confirm_callback:
            if name == "write_file":
                desc = f"Write to file: {args.get('path')}"
            elif name == "create_folder":
                desc = f"Create folder: {args.get('path')}"
            else:
                desc = args.get("command", "")
            reason = args.get("reason", "LEO wants to perform this action")
            approved = confirm_callback(desc, reason)
            if not approved:
                return "Action cancelled by user."

        if name == "open_app":
            app_name = args.get("app_name", "").strip()
            try:
                import ctypes
                # SW_SHOWDEFAULT=10 respects the app's own default size, avoids fullscreen snap
                ret = ctypes.windll.shell32.ShellExecuteW(
                    None, "open", app_name, None, None, 10
                )
                if ret <= 32:
                    raise Exception(f"ShellExecute returned {ret}")
            except Exception:
                subprocess.Popen(
                    f'start "" "{app_name}"',
                    shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            time.sleep(1.5)
            if minimize_callback:
                minimize_callback()
            return f"Opened {app_name}."

        elif name == "open_url":
            url = args.get("url", "")
            if not url.startswith("http"):
                url = "https://" + url
            webbrowser.open(url)
            time.sleep(1.0)
            if minimize_callback:
                minimize_callback()
            return f"Opened {url}."

        elif name == "search_web":
            query = args.get("query", "")
            webbrowser.open(f"https://www.google.com/search?q={query.replace(' ', '+')}")
            time.sleep(1.0)
            if minimize_callback:
                minimize_callback()
            return f"Searched for: {query}"

        elif name == "set_volume":
            level = max(0, min(100, int(args.get("level", 50))))
            script = f"""
from ctypes import cast, POINTER
from comtypes import CLSCTX_ALL, CoInitialize
from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
CoInitialize()
d = AudioUtilities.GetDeviceEnumerator()
s = d.GetDefaultAudioEndpoint(0, 0)
i = s.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
from ctypes import cast, POINTER
v = cast(i, POINTER(IAudioEndpointVolume))
v.SetMasterVolumeLevelScalar({level}/100, None)
"""
            subprocess.run(
                [sys.executable, "-c", script],
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return f"Volume set to {level} percent."

        elif name == "run_command":
            cmd = args.get("command", "")
            result = subprocess.run(
                cmd, shell=True, capture_output=True,
                text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            out = result.stdout.strip() or result.stderr.strip() or "Done."
            return out[:600]

        elif name == "read_file":
            path = args.get("path", "")
            if not os.path.exists(path):
                return f"File not found: {path}"
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()[:1500]

        elif name == "write_file":
            path = args.get("path", "")
            content = args.get("content", "")
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Written to {path}."

        elif name == "list_folder":
            path = args.get("path", "")
            if not os.path.exists(path):
                return f"Folder not found: {path}"
            items = os.listdir(path)
            folders = [i for i in items if os.path.isdir(os.path.join(path, i))]
            files   = [i for i in items if os.path.isfile(os.path.join(path, i))]
            return f"Folders: {', '.join(folders) or 'none'}\nFiles: {', '.join(files) or 'none'}"

        elif name == "create_folder":
            path = args.get("path", "")
            os.makedirs(path, exist_ok=True)
            return f"Folder created: {path}"

        elif name == "type_text":
            text = args.get("text", "")
            pyautogui.sleep(0.3)
            pyautogui.write(text, interval=0.03)
            return f"Typed: {text}"

        elif name == "browser_control":
            action = args.get("action", "")
            hotkeys = {
                "new_tab":    ('ctrl', 't'),
                "new_window": ('ctrl', 'n'),
                "close_tab":  ('ctrl', 'w'),
                "refresh":    ('f5',),
            }
            if action in hotkeys:
                pyautogui.hotkey(*hotkeys[action])
                return f"Browser: {action}"
            return f"Unknown action: {action}"

        elif name == "get_system_info":
            info_type = args.get("info_type", "").lower()
            try:
                import psutil
                if info_type == "battery":
                    b = psutil.sensors_battery()
                    if b:
                        status = "charging" if b.power_plugged else "discharging"
                        return f"Battery: {b.percent:.0f}% — {status}"
                    return "No battery detected."
                elif info_type == "cpu":
                    return f"CPU usage: {psutil.cpu_percent(interval=1):.0f}%"
                elif info_type == "ram":
                    r = psutil.virtual_memory()
                    return f"RAM: {r.percent:.0f}% used — {r.available // (1024**2)} MB free of {r.total // (1024**2)} MB"
                elif info_type == "disk":
                    d = psutil.disk_usage('/')
                    return f"Disk: {d.percent:.0f}% used — {d.free // (1024**3)} GB free of {d.total // (1024**3)} GB"
            except ImportError:
                return "psutil not installed."

        # ── NEW TOOLS ────────────────────────────────────────────

        elif name == "set_reminder":
            seconds = int(args.get("seconds", 60))
            message = args.get("message", "Reminder.")

            def _fire():
                import winsound
                winsound.Beep(1000, 300)
                if _speech_callback:
                    _speech_callback(f"Reminder: {message}")

            t = threading.Timer(seconds, _fire)
            t.daemon = True
            t.start()
            mins = seconds // 60
            secs = seconds % 60
            time_str = f"{mins} minute{'s' if mins != 1 else ''}" if mins > 0 else f"{secs} second{'s' if secs != 1 else ''}"
            if mins > 0 and secs > 0:
                time_str = f"{mins}m {secs}s"
            return f"Reminder set for {time_str}: {message}"

        elif name == "clipboard_read":
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            try:
                content = root.clipboard_get()
            except Exception:
                content = ""
            root.destroy()
            return content[:1000] if content else "Clipboard is empty."

        elif name == "clipboard_write":
            text = args.get("text", "")
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            root.clipboard_clear()
            root.clipboard_append(text)
            root.update()
            root.destroy()
            return f"Copied to clipboard: {text[:80]}{'...' if len(text) > 80 else ''}"

        elif name == "screenshot_describe":
            if not _gemini_client or not _gemini_model:
                return "Vision not available — Gemini client not initialised."
            screenshot = pyautogui.screenshot()
            import io
            buf = io.BytesIO()
            screenshot.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            response = _gemini_client.models.generate_content(
                model=_gemini_model,
                contents=[
                    types.Content(role="user", parts=[
                        types.Part(
                            inline_data=types.Blob(
                                mime_type="image/png",
                                data=img_b64
                            )
                        ),
                        types.Part(text=(
                            "Describe what is currently visible on this screen. "
                            "Be concise and factual. No markdown."
                        ))
                    ])
                ]
            )
            return response.text.strip()

        elif name == "media_control":
            action = args.get("action", "")
            media_keys = {
                "play_pause":  "playpause",
                "next_track":  "nexttrack",
                "prev_track":  "prevtrack",
                "volume_up":   "volumeup",
                "volume_down": "volumedown",
                "mute":        "volumemute",
            }
            if action in media_keys:
                pyautogui.press(media_keys[action])
                return f"Media: {action.replace('_', ' ')}."
            return f"Unknown media action: {action}"

    except Exception as e:
        return f"Tool error ({name}): {str(e)}"

    return "Tool not recognized."


# ── Skills discovery ──────────────────────────────────────────────────────────

import importlib.util

_disabled_skills = set()
_discovered      = []   # list of (fname, module, error)


def discover_skills(skills_dir="skills"):
    global _discovered
    _discovered = []
    if not os.path.isdir(skills_dir):
        return _discovered
    for fname in sorted(os.listdir(skills_dir)):
        if not fname.endswith(".py"):
            continue
        path = os.path.join(skills_dir, fname)
        try:
            spec = importlib.util.spec_from_file_location(fname[:-3], path)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _discovered.append((fname, mod, None))
        except Exception as e:
            _discovered.append((fname, None, str(e)))
    return _discovered


def set_skill_enabled(fname, enabled):
    if enabled:
        _disabled_skills.discard(fname)
    else:
        _disabled_skills.add(fname)

    # Persist to config
    import json
    cfg_path = "config.json"
    try:
        cfg = {}
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                cfg = json.load(f)
        cfg["disabled_skills"] = list(_disabled_skills)
        with open(cfg_path, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception as e:
        print(f"[SKILLS] Failed to save: {e}")


# ── Agent ─────────────────────────────────────────────────────────────────────

# Alias so imports using LeoAgent still work
LeoAgent = None   # defined below as HorowaAgent, aliased at bottom


class HorowaAgent:
    def __init__(self, api_key, model_name, system_prompt,
                 confirm_callback=None, minimize_callback=None,
                 speech_callback=None, gemini_client=None):
        self.client            = gemini_client or genai.Client(api_key=api_key)
        self.model_name        = model_name
        self.system_prompt     = system_prompt
        self.confirm_callback  = confirm_callback
        self.minimize_callback = minimize_callback
        self.speech_callback   = speech_callback
        self.history           = []

    def run(self, query):
        self.history.append(types.Content(
            role="user", parts=[types.Part(text=query)]
        ))

        messages = [
            types.Content(role="user",  parts=[types.Part(text=self.system_prompt)]),
            types.Content(role="model", parts=[types.Part(text="Understood. I am HOROWA AI, ready to assist.")]),
        ] + self.history

        for _ in range(6):
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=messages,
                config=types.GenerateContentConfig(tools=TOOLS)
            )

            candidate = response.candidates[0]
            parts     = candidate.content.parts
            has_tool_call = any(
                hasattr(p, 'function_call') and p.function_call for p in parts
            )

            if not has_tool_call:
                text = "".join(
                    p.text for p in parts if hasattr(p, 'text') and p.text
                ).strip()
                self.history.append(types.Content(
                    role="model", parts=[types.Part(text=text)]
                ))
                if len(self.history) > 40:
                    self.history = self.history[-40:]
                return text

            messages.append(candidate.content)

            tool_results = []
            for part in parts:
                if hasattr(part, 'function_call') and part.function_call:
                    fc     = part.function_call
                    result = execute_tool(
                        fc.name,
                        dict(fc.args),
                        confirm_callback=self.confirm_callback,
                        minimize_callback=self.minimize_callback
                    )
                    tool_results.append(types.Part(
                        function_response=types.FunctionResponse(
                            name=fc.name,
                            response={"result": result}
                        )
                    ))

            messages.append(types.Content(role="user", parts=tool_results))

        return "Agent loop limit reached."

    def clear_memory(self):
        self.history = []


# Backwards-compat alias
LeoAgent = HorowaAgent
