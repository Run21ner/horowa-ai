import customtkinter as ctk
import tkinter as tk
import math
import re
import json
import os
import sys
import threading
import requests

# ─────────────────────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────────────────────
CONFIG_PATH = "config.json"
DEFAULT_CONFIG = {
    "ollama_model":       "",
    "ollama_url":         "http://localhost:11434",
    "ollama_models_dir":  "",
    "temperature":        0.7,
    "top_p":              0.9,
    "top_k":              40,
    "repeat_penalty":     1.1,
    "context_length":     4096,
    "num_gpu_layers":     -1,
    "num_threads":        4,
    "system_prompt":      (
        "You are HOROWA AI, a high-tech terminal-based AI assistant. "
        "Your responses should be concise, professional, and slightly robotic. "
        "Never output markdown formatting or asterisks. "
        "When asked to write code, output it in a plain fenced code block using triple backticks and the language name. "
        "Never attempt to execute or run code. You have no run_code tool. "
        "When the user asks you to do something on their computer, use the available tools. "
        "You remember previous messages in this conversation."
    ),
    "seed":               -1,
    "keep_alive":         "5m",
    # Animation toggles — all on by default
    "anim_message_fade":    True,
    "anim_button_pulse":    True,
    "anim_thinking_scan":   True,
    "anim_sphere":          True,
    "anim_ripple":          True,
    "anim_status_flash":    True,
}

def load_config():
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH) as f:
                data = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                data.setdefault(k, v)
            return data
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg):
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=2)


# ─────────────────────────────────────────────────────────────
#  SYNTAX HIGHLIGHTING
# ─────────────────────────────────────────────────────────────
SYNTAX_RULES = {
    "keyword":    (r'\b(def|class|return|import|from|as|if|elif|else|for|while|try|except|finally|with|in|not|and|or|is|None|True|False|pass|break|continue|yield|lambda|raise|assert|del|global|nonlocal|async|await)\b', "#bf5fff"),
    "builtin":    (r'\b(print|len|range|int|str|float|list|dict|set|tuple|type|isinstance|open|super|self|cls|input|enumerate|zip|map|filter|any|all|min|max|sum|abs)\b', "#7b6fff"),
    "string":     (r'(\"\"\"[\s\S]*?\"\"\"|\'\'\'[\s\S]*?\'\'\'|\"[^\"\\]*\"|\'[^\'\\]*\')', "#00cc88"),
    "comment":    (r'(#[^\n]*)', "#555577"),
    "number":     (r'\b(\d+\.?\d*)\b', "#ffaa44"),
    "decorator":  (r'(@\w+)', "#ff6eb4"),
    "function":   (r'\bdef\s+(\w+)', "#00fbff"),
    "class_name": (r'\bclass\s+(\w+)', "#ffdd57"),
}

def apply_syntax_highlighting(text_widget, code):
    text_widget.configure(state="normal")
    text_widget.delete("1.0", "end")
    text_widget.insert("1.0", code)
    for tag, (pattern, color) in SYNTAX_RULES.items():
        text_widget.tag_configure(tag, foreground=color)
        for m in re.finditer(pattern, code, re.MULTILINE):
            g = 1 if m.lastindex and m.lastindex >= 1 and tag in ("function","class_name","string","comment","decorator") else 0
            si = m.start(g); ei = m.end(g)
            ls = code.rfind('\n', 0, si) + 1
            cs = si - ls
            lns = code[:si].count('\n') + 1
            lne = code[:ei].count('\n') + 1
            ce  = ei - (code.rfind('\n', 0, ei) + 1)
            text_widget.tag_add(tag, f"{lns}.{cs}", f"{lne}.{ce}")
    text_widget.configure(state="disabled")


# ─────────────────────────────────────────────────────────────
#  SHARED STYLE HELPERS
# ─────────────────────────────────────────────────────────────
BG      = "#080d14"
PANEL   = "#0b1520"
CARD    = "#0d1a24"
BORDER  = "#1a4a6a"
BORDER2 = "#1a3a4a"
CYAN    = "#00fbff"
GREEN   = "#00ffaa"
DIM     = "#8ecfdf"
RED     = "#ff4444"
ORANGE  = "#ffaa00"
PURPLE  = "#bf5fff"

def _lbl(parent, text, font=("Courier",11), color=DIM, **kw):
    return ctk.CTkLabel(parent, text=text, font=font, text_color=color, **kw)

def _entry(parent, width=None, **kw):
    cfg = dict(font=("Courier",12), fg_color=CARD, text_color=CYAN,
               border_color=BORDER, border_width=1, corner_radius=8)
    cfg.update(kw)
    if width: cfg["width"] = width
    return ctk.CTkEntry(parent, **cfg)

def _btn(parent, text, command, color=CYAN, text_color="#000d11", **kw):
    cfg = dict(font=("Courier",11,"bold"), corner_radius=8,
               fg_color=color, text_color=text_color, height=32)
    cfg.update(kw)
    return ctk.CTkButton(parent, text=text, command=command, **cfg)

def _ghost_btn(parent, text, command, **kw):
    cfg = dict(font=("Courier",11,"bold"), corner_radius=8,
               fg_color="transparent", border_width=1,
               border_color=BORDER, text_color=DIM, height=32)
    cfg.update(kw)
    return ctk.CTkButton(parent, text=text, command=command, **cfg)

def _section_card(parent, **kw):
    return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12,
                        border_width=1, border_color=BORDER2, **kw)

def _nav_bar(parent, title, back_cmd):
    bar = ctk.CTkFrame(parent, fg_color="transparent")
    bar.pack(fill="x", padx=16, pady=(14, 8))
    if back_cmd:
        _ghost_btn(bar, "←", back_cmd, width=36, height=32, border_color=BORDER).pack(side="left", padx=(0,8))
    _lbl(bar, title, font=("Courier",15,"bold"), color=CYAN).pack(side="left")
    return bar


# ─────────────────────────────────────────────────────────────
#  BUTTON PULSE ANIMATION HELPER
# ─────────────────────────────────────────────────────────────
def pulse_button(btn, original_color, pulse_color, steps=6, interval=40):
    """Flash a button between pulse_color → original_color over steps frames."""
    def _step(i):
        if i >= steps:
            try: btn.configure(fg_color=original_color)
            except Exception: pass
            return
        color = pulse_color if i % 2 == 0 else original_color
        try:
            btn.configure(fg_color=color)
            btn.after(interval, lambda: _step(i + 1))
        except Exception:
            pass
    _step(0)


# ─────────────────────────────────────────────────────────────
#  SETTINGS MAIN OVERLAY
# ─────────────────────────────────────────────────────────────
class HorowaSettingsOverlay(ctk.CTkToplevel):
    def __init__(self, master, on_restart=None):
        super().__init__(master)
        self.on_restart = on_restart
        self.title("HOROWA AI — Settings")
        self.geometry("480x490")
        self.configure(fg_color=BG)
        self.attributes("-alpha", 0.96)
        self.attributes("-topmost", True)
        self.resizable(False, False)
        self.grab_set()
        self.lift()
        self._build()

    def _build(self):
        for w in self.winfo_children(): w.destroy()

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 8))
        _lbl(hdr, "⚙  SETTINGS", font=("Courier",15,"bold"), color=CYAN).pack(side="left")
        _btn(hdr, "✕", self.destroy, color="transparent",
             text_color=RED, border_width=1, border_color=RED, width=32, height=32).pack(side="right")

        sep = ctk.CTkFrame(self, fg_color=BORDER, height=1)
        sep.pack(fill="x", padx=16, pady=(0, 14))

        cards_frame = ctk.CTkFrame(self, fg_color="transparent")
        cards_frame.pack(fill="both", expand=True, padx=16, pady=(0, 16))

        self._make_section_card(
            cards_frame,
            icon="⬡", title="Local Model",
            subtitle="Ollama model, temperature, context, system prompt…",
            command=self._open_local_llm
        )
        self._make_section_card(
            cards_frame,
            icon="🔑", title="API & Online Models",
            subtitle="Connect Gemini, ChatGPT, Claude. Select model, set system prompt…",
            command=self._open_api
        )
        self._make_section_card(
            cards_frame,
            icon="◈", title="Animations",
            subtitle="Toggle sphere, ripples, message fade, button pulse, scan line…",
            command=self._open_animations
        )
        self._make_section_card(
            cards_frame,
            icon="⬡", title="Skills",
            subtitle="Manage skill plugins — enable, disable, import .py skills…",
            command=self._open_skills
        )

        # ── Credit line ───────────────────────────────────────
        ctk.CTkFrame(self, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=(8, 0))
        _lbl(self, "by Run21ner", font=("Courier", 10), color="#334455").pack(pady=(5, 8))

    def _make_section_card(self, parent, icon, title, subtitle, command):
        card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14,
                            border_width=1, border_color=BORDER, cursor="hand2")
        card.pack(fill="x", pady=6)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=14)
        inner.grid_columnconfigure(1, weight=1)

        _lbl(inner, icon, font=("Courier",22), color=CYAN).grid(row=0, column=0, rowspan=2, padx=(0,14), sticky="ns")
        _lbl(inner, title, font=("Courier",13,"bold"), color=CYAN, anchor="w").grid(row=0, column=1, sticky="ew")
        _lbl(inner, subtitle, font=("Courier",10), color=DIM, anchor="w", wraplength=320, justify="left").grid(row=1, column=1, sticky="ew")
        _lbl(inner, "›", font=("Courier",20,"bold"), color=BORDER).grid(row=0, column=2, rowspan=2, padx=(10,0))

        for widget in [card, inner] + inner.winfo_children():
            widget.bind("<Button-1>", lambda e, cmd=command: cmd())
            try: widget.configure(cursor="hand2")
            except Exception: pass

    def _open_local_llm(self):
        self.withdraw()
        LocalModelOverlay(self.master, on_back=self._reshow, on_restart=self.on_restart)

    def _open_api(self):
        self.withdraw()
        HorowaAPIOverlay(self.master, on_back=self._reshow)

    def _open_animations(self):
        self.withdraw()
        HorowaAnimationsOverlay(self.master, on_back=self._reshow)

    def _open_skills(self):
        self.withdraw()
        HorowaSkillsOverlay(self.master, on_back=self._reshow)

    def _reshow(self):
        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.grab_set()


# ─────────────────────────────────────────────────────────────
#  ANIMATIONS OVERLAY
# ─────────────────────────────────────────────────────────────
class HorowaAnimationsOverlay(ctk.CTkToplevel):
    ANIM_OPTIONS = [
        ("anim_sphere",        "Sphere animation",         "Animated Siri-style color sphere in left panel"),
        ("anim_ripple",        "Sonar ripple rings",        "Ripple pulse rings after each LEO response"),
        ("anim_message_fade",  "Message fade-in",           "New terminal messages fade in smoothly"),
        ("anim_button_pulse",  "Button pulse on click",     "Buttons flash on press for tactile feedback"),
        ("anim_thinking_scan", "Thinking scan line",        "Animated scan bar while HOROWA is processing"),
        ("anim_status_flash",  "Status bar flash",          "Status bar flashes on mode toggle"),
    ]

    def __init__(self, master, on_back=None):
        super().__init__(master)
        self.on_back = on_back
        self.title("HOROWA AI — Animations")
        self.geometry("500x480")
        self.configure(fg_color=BG)
        self.attributes("-alpha", 0.97)
        self.resizable(False, False)
        self.grab_set()
        self.cfg = load_config()
        self._vars = {}
        self._build()

    def _build(self):
        _nav_bar(self, "◈  ANIMATIONS", back_cmd=self._back)
        sep = ctk.CTkFrame(self, fg_color=BORDER, height=1)
        sep.pack(fill="x", padx=16, pady=(0,10))

        _lbl(self, "Toggle visual effects. All animations are on by default.",
             font=("Courier",11), color=DIM).pack(anchor="w", padx=20, pady=(0,10))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                         scrollbar_button_color=CYAN)
        scroll.pack(fill="both", expand=True, padx=12, pady=(0,0))

        for key, label, desc in self.ANIM_OPTIONS:
            card = _section_card(scroll); card.pack(fill="x", pady=5)
            row  = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=12)
            row.grid_columnconfigure(1, weight=1)

            var = tk.BooleanVar(value=self.cfg.get(key, True))
            self._vars[key] = var

            sw = ctk.CTkSwitch(row, text="", variable=var, width=44,
                               button_color=CYAN, progress_color=BORDER)
            sw.grid(row=0, column=0, rowspan=2, padx=(0,14))

            _lbl(row, label, font=("Courier",12,"bold"), color=CYAN, anchor="w").grid(row=0, column=1, sticky="ew")
            _lbl(row, desc,  font=("Courier",10),        color=DIM,  anchor="w", wraplength=340).grid(row=1, column=1, sticky="ew")

        self._status_lbl = _lbl(self, "", color=GREEN)
        self._status_lbl.pack(pady=(6,0))

        bot = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0)
        bot.pack(fill="x", side="bottom")
        bot_inner = ctk.CTkFrame(bot, fg_color="transparent")
        bot_inner.pack(fill="x", padx=16, pady=10)
        _btn(bot_inner, "✓  Save", self._save, width=100).pack(side="right")
        _ghost_btn(bot_inner, "All On",  self._all_on,  width=80).pack(side="right", padx=(0,8))
        _ghost_btn(bot_inner, "All Off", self._all_off, width=80).pack(side="right", padx=(0,8))

    def _all_on(self):
        for v in self._vars.values(): v.set(True)

    def _all_off(self):
        for v in self._vars.values(): v.set(False)

    def _save(self):
        cfg = load_config()
        for key, var in self._vars.items():
            cfg[key] = var.get()
        save_config(cfg)
        # Push live to GUI if possible
        try:
            gui = self.master
            if hasattr(gui, '_anim_flags'):
                for key, var in self._vars.items():
                    gui._anim_flags[key] = var.get()
        except Exception:
            pass
        self._status_lbl.configure(text="✓ Saved — restart not required", text_color=GREEN)
        self.after(2000, lambda: self._status_lbl.configure(text=""))

    def _back(self):
        self.destroy()
        if self.on_back: self.on_back()


# ─────────────────────────────────────────────────────────────
#  API & ONLINE MODELS OVERLAY
# ─────────────────────────────────────────────────────────────
PROVIDER_INFO = {
    "gemini":    {"label": "Google Gemini",  "color": "#4285F4", "key_hint": "AIza…"},
    "openai":    {"label": "OpenAI / ChatGPT","color": "#10a37f","key_hint": "sk-…"},
    "anthropic": {"label": "Anthropic / Claude","color": "#b5836e","key_hint": "sk-ant-…"},
}

class HorowaAPIOverlay(ctk.CTkToplevel):
    def __init__(self, master, on_back=None):
        super().__init__(master)
        self.on_back = on_back
        self.title("HOROWA AI — API & Online Models")
        self.geometry("580x720")
        self.configure(fg_color=BG)
        self.attributes("-alpha", 0.97)
        self.attributes("-topmost", True)
        self.resizable(False, True)
        self.grab_set()

        self.cfg            = load_config()
        self._provider_var  = tk.StringVar(value=self.cfg.get("online_provider", "gemini"))
        self._model_var     = tk.StringVar(value=self.cfg.get("online_model", ""))
        self._key_entries   = {}   # provider → CTkEntry
        self._model_options = []
        self._build()

    # ── Build ─────────────────────────────────────────────────

    def _build(self):
        _nav_bar(self, "🔑  API & ONLINE MODELS", back_cmd=self._back)
        ctk.CTkFrame(self, fg_color=BORDER, height=1).pack(fill="x", padx=16, pady=(0,10))

        scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                         scrollbar_button_color=CYAN)
        scroll.pack(fill="both", expand=True, padx=12, pady=(0,0))

        # ── Active provider selector ──────────────────────────
        pc = _section_card(scroll); pc.pack(fill="x", pady=5)
        _lbl(pc, "Active Provider", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,4))
        _lbl(pc, "LEO uses this provider for all online queries.", color=DIM).pack(anchor="w", padx=14)

        prow = ctk.CTkFrame(pc, fg_color="transparent")
        prow.pack(fill="x", padx=14, pady=(8,12))
        for pid, info in PROVIDER_INFO.items():
            active = (pid == self._provider_var.get())
            btn = ctk.CTkButton(
                prow, text=info["label"], width=150, height=36,
                font=("Courier",11,"bold"), corner_radius=10,
                fg_color=info["color"] if active else "transparent",
                text_color="#ffffff" if active else DIM,
                border_width=1, border_color=info["color"],
                command=lambda p=pid: self._select_provider(p)
            )
            btn.pack(side="left", padx=(0,8))

        # Store provider buttons for re-styling
        self._provider_btns = prow

        # ── Per-provider API key cards ────────────────────────
        self._key_vars = {}   # pid → StringVar storing actual key text
        for pid, info in PROVIDER_INFO.items():
            c = _section_card(scroll); c.pack(fill="x", pady=5)
            hdr = ctk.CTkFrame(c, fg_color="transparent")
            hdr.pack(fill="x", padx=14, pady=(10,2))
            dot = ctk.CTkLabel(hdr, text="●", font=("Courier",14),
                               text_color=info["color"])
            dot.pack(side="left", padx=(0,6))
            _lbl(hdr, info["label"], font=("Courier",12,"bold"), color=CYAN).pack(side="left")

            _lbl(c, f"API Key  ({info['key_hint']})", color=DIM).pack(anchor="w", padx=14)
            key_row = ctk.CTkFrame(c, fg_color="transparent")
            key_row.pack(fill="x", padx=14, pady=(4,10))
            key_row.grid_columnconfigure(0, weight=1)

            saved_key = self.cfg.get("api_keys", {}).get(pid, "")
            key_var = tk.StringVar(value=saved_key)
            self._key_vars[pid] = key_var

            # Use plain tk.Entry so show="*" + .get() works reliably
            e = tk.Entry(key_row, textvariable=key_var, show="•",
                         font=("Courier", 12), bg="#0d1a24", fg="#00fbff",
                         insertbackground="#00fbff", relief="flat",
                         highlightthickness=1, highlightbackground="#1a4a6a",
                         highlightcolor="#00fbff")
            e.grid(row=0, column=0, sticky="ew", padx=(0,8), ipady=6)
            self._key_entries[pid] = e   # keep for compat

            show_var = tk.BooleanVar(value=False)
            def _toggle_show(entry=e, var=show_var):
                var.set(not var.get())
                entry.configure(show="" if var.get() else "•")
            _ghost_btn(key_row, "👁", _toggle_show, width=36, height=32).grid(row=0, column=1)

        # ── Model selector ────────────────────────────────────
        mc = _section_card(scroll); mc.pack(fill="x", pady=5)
        _lbl(mc, "Model", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(mc, "Select from fetched models or type manually.", color=DIM).pack(anchor="w", padx=14)

        mrow = ctk.CTkFrame(mc, fg_color="transparent")
        mrow.pack(fill="x", padx=14, pady=(6,4))
        mrow.grid_columnconfigure(0, weight=1)

        self._model_menu = ctk.CTkOptionMenu(
            mrow, variable=self._model_var,
            values=[self._model_var.get() or "— fetch models first —"],
            font=("Courier",12), fg_color=CARD,
            button_color=BORDER, button_hover_color="#2a5a7a",
            text_color=CYAN, dropdown_fg_color=CARD,
            dropdown_text_color=CYAN, corner_radius=8
        )
        self._model_menu.grid(row=0, column=0, sticky="ew", padx=(0,8))
        _btn(mrow, "⟳ Fetch", self._fetch_models, width=80, height=32).grid(row=0, column=1)

        # Manual entry
        _lbl(mc, "Or type model name manually:", color=DIM).pack(anchor="w", padx=14, pady=(6,2))
        self._manual_model = _entry(mc)
        self._manual_model.pack(fill="x", padx=14, pady=(0,10))
        if self._model_var.get():
            self._manual_model.insert(0, self._model_var.get())

        # ── Online system prompt ──────────────────────────────
        sc = _section_card(scroll); sc.pack(fill="x", pady=5)
        _lbl(sc, "Online System Prompt", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(sc, "Injected into every online conversation.", color=DIM).pack(anchor="w", padx=14)
        self._sys_box = ctk.CTkTextbox(
            sc, font=("Courier",11), fg_color=CARD, text_color=CYAN,
            border_color=BORDER, border_width=1, corner_radius=8, height=110
        )
        self._sys_box.pack(fill="x", padx=14, pady=(6,10))
        default_prompt = (
            "You are HOROWA AI, a high-tech terminal-based AI assistant. "
            "Your responses should be concise, professional, and slightly robotic. "
            "Never output markdown formatting or asterisks."
        )
        self._sys_box.insert("1.0", self.cfg.get("online_system_prompt", default_prompt))

        # ── Status + bottom bar ───────────────────────────────
        self._status_lbl = _lbl(self, "", color=GREEN)
        self._status_lbl.pack(pady=(4,0))

        bot = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0)
        bot.pack(fill="x", side="bottom")
        bot_inner = ctk.CTkFrame(bot, fg_color="transparent")
        bot_inner.pack(fill="x", padx=16, pady=10)
        _btn(bot_inner, "✓  Save & Apply", self._save, width=140).pack(side="right")

    # ── Provider select ───────────────────────────────────────

    def _select_provider(self, pid):
        self._provider_var.set(pid)
        # Re-style all buttons
        for widget in self._provider_btns.winfo_children():
            label = widget.cget("text")
            for p, info in PROVIDER_INFO.items():
                if info["label"] == label:
                    active = (p == pid)
                    widget.configure(
                        fg_color=info["color"] if active else "transparent",
                        text_color="#ffffff" if active else DIM
                    )
                    break
        # Pre-fill model dropdown with cached or default
        default = {"gemini": "gemini-2.5-flash-lite",
                   "openai": "gpt-4o-mini",
                   "anthropic": "claude-sonnet-4-5"}.get(pid, "")
        current = self.cfg.get("online_model", default)
        self._model_var.set(current)
        self._manual_model.delete(0, "end")
        self._manual_model.insert(0, current)

    # ── Fetch models ──────────────────────────────────────────

    def _fetch_models(self):
        self._status_lbl.configure(text="⟳ Fetching models…", text_color=ORANGE)
        provider = self._provider_var.get()
        # Read from StringVar (reliable, unmasked)
        api_key  = self._key_vars.get(provider, tk.StringVar()).get().strip()
        if not api_key:
            self._status_lbl.configure(text="⚠ Enter API key first.", text_color=RED)
            return
        threading.Thread(target=self._do_fetch, args=(provider, api_key), daemon=True).start()

    def _do_fetch(self, provider, api_key):
        try:
            if provider == "gemini":
                from google import genai
                c      = genai.Client(api_key=api_key)
                models = []
                for m in c.models.list():
                    actions = getattr(m, "supported_actions", None) or \
                              getattr(m, "supported_generation_methods", [])
                    if "generateContent" in (actions or []):
                        models.append(m.name.replace("models/", ""))
                models = sorted(models)

            elif provider == "openai":
                import requests as req
                r = req.get("https://api.openai.com/v1/models",
                            headers={"Authorization": f"Bearer {api_key}"}, timeout=8)
                r.raise_for_status()
                models = sorted([m["id"] for m in r.json()["data"]
                                 if "gpt" in m["id"].lower()], reverse=True)

            elif provider == "anthropic":
                import requests as req
                r = req.get("https://api.anthropic.com/v1/models",
                            headers={"x-api-key": api_key,
                                     "anthropic-version": "2023-06-01"}, timeout=8)
                r.raise_for_status()
                models = [m["id"] for m in r.json().get("data", [])]

            else:
                models = []

        except Exception as e:
            print(f"[FETCH MODELS] {provider}: {e}")
            models = []

        self.after(0, lambda: self._apply_models(models))

    def _apply_models(self, models):
        if not models:
            self._status_lbl.configure(text="⚠ No models returned. Check key.", text_color=RED)
            return
        self._model_options = models
        self._model_menu.configure(values=models)
        # pick current or first
        cur = self._model_var.get()
        val = cur if cur in models else models[0]
        self._model_var.set(val)
        self._manual_model.delete(0, "end")
        self._manual_model.insert(0, val)
        self._status_lbl.configure(text=f"✓ {len(models)} models fetched.", text_color=GREEN)
        self.after(3000, lambda: self._status_lbl.configure(text=""))

    # ── Save ──────────────────────────────────────────────────

    def _save(self):
        cfg = load_config()

        # API keys — read from StringVars (reliable, unmasked)
        keys = cfg.get("api_keys", {})
        for pid, var in self._key_vars.items():
            v = var.get().strip()
            if v: keys[pid] = v
        cfg["api_keys"] = keys

        # Provider + model
        cfg["online_provider"] = self._provider_var.get()
        # manual entry takes priority if filled
        manual = self._manual_model.get().strip()
        cfg["online_model"] = manual if manual else self._model_var.get()

        # System prompt
        cfg["online_system_prompt"] = self._sys_box.get("1.0", "end-1c").strip()

        save_config(cfg)

        # Hot-reload provider in core if accessible
        try:
            gui = self.master
            if hasattr(gui, '_core_ref') and gui._core_ref:
                gui._core_ref.reload_provider()
        except Exception:
            pass

        self._status_lbl.configure(text="✓ Saved & applied.", text_color=GREEN)
        self.after(2500, lambda: self._status_lbl.configure(text=""))

    def _back(self):
        self.destroy()
        if self.on_back: self.on_back()


# ─────────────────────────────────────────────────────────────
#  LOCAL LLM OVERLAY
# ─────────────────────────────────────────────────────────────
class LocalModelOverlay(ctk.CTkToplevel):
    def __init__(self, master, on_back=None, on_restart=None):
        super().__init__(master)
        self.on_back    = on_back
        self.on_restart = on_restart
        self.title("HOROWA AI — Local LLM Settings")
        self.geometry("560x700")
        self.configure(fg_color=BG)
        self.attributes("-alpha", 0.97)
        self.resizable(False, True)
        self.grab_set()

        self.cfg = load_config()
        self._vars = {}
        self._model_var = tk.StringVar(value=self.cfg.get("ollama_model",""))

        self._build()
        self._fetch_models_async()

    def _build(self):
        _nav_bar(self, "⬡  LOCAL LLM", back_cmd=self._back)

        sep = ctk.CTkFrame(self, fg_color=BORDER, height=1)
        sep.pack(fill="x", padx=16, pady=(0,10))

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                               scrollbar_button_color=CYAN)
        self._scroll.pack(fill="both", expand=True, padx=12, pady=(0,0))

        s = self._scroll

        c = _section_card(s); c.pack(fill="x", pady=5)
        _lbl(c, "Model", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(c, "Select from Ollama models installed on your machine.", color=DIM).pack(anchor="w", padx=14)

        self._model_menu = ctk.CTkOptionMenu(
            c, variable=self._model_var,
            values=["Fetching…"],
            font=("Courier",12), fg_color=CARD,
            button_color=BORDER, button_hover_color="#2a5a7a",
            text_color=CYAN, dropdown_fg_color=CARD,
            dropdown_text_color=CYAN, corner_radius=8
        )
        self._model_menu.pack(fill="x", padx=14, pady=(6,10))

        c2 = _section_card(s); c2.pack(fill="x", pady=5)
        _lbl(c2, "Ollama Server URL", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        self._vars["ollama_url"] = self._text_field(c2, "ollama_url", "http://localhost:11434")

        c3 = _section_card(s); c3.pack(fill="x", pady=5)
        _lbl(c3, "Models Storage Directory", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(c3, "Override OLLAMA_MODELS env var. Leave blank to use default.", color=DIM).pack(anchor="w", padx=14)
        row = ctk.CTkFrame(c3, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(6,10))
        row.grid_columnconfigure(0, weight=1)
        e = _entry(row); e.grid(row=0, column=0, sticky="ew", padx=(0,8))
        e.insert(0, self.cfg.get("ollama_models_dir",""))
        self._vars["ollama_models_dir"] = e
        _ghost_btn(row, "Browse", self._browse_dir, width=70).grid(row=0, column=1)

        c4 = _section_card(s); c4.pack(fill="x", pady=5)
        _lbl(c4, "Temperature", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(c4, "Controls randomness. Lower = more focused, Higher = more creative.", color=DIM).pack(anchor="w", padx=14)
        self._slider_row(c4, "temperature", 0.0, 2.0, self.cfg.get("temperature", 0.7), resolution=0.01)

        c5 = _section_card(s); c5.pack(fill="x", pady=5)
        _lbl(c5, "Top-P (Nucleus Sampling)", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(c5, "Only tokens with cumulative probability ≤ Top-P are considered.", color=DIM).pack(anchor="w", padx=14)
        self._slider_row(c5, "top_p", 0.0, 1.0, self.cfg.get("top_p", 0.9), resolution=0.01)

        c6 = _section_card(s); c6.pack(fill="x", pady=5)
        _lbl(c6, "Top-K", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(c6, "Limits next token selection to top-K candidates.", color=DIM).pack(anchor="w", padx=14)
        self._slider_row(c6, "top_k", 1, 200, self.cfg.get("top_k", 40), resolution=1, as_int=True)

        c7 = _section_card(s); c7.pack(fill="x", pady=5)
        _lbl(c7, "Repeat Penalty", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(c7, "Penalises repeated tokens. >1 = less repetition.", color=DIM).pack(anchor="w", padx=14)
        self._slider_row(c7, "repeat_penalty", 0.5, 2.0, self.cfg.get("repeat_penalty", 1.1), resolution=0.01)

        c8 = _section_card(s); c8.pack(fill="x", pady=5)
        _lbl(c8, "Context Length (num_ctx)", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(c8, "Max tokens the model keeps in memory.", color=DIM).pack(anchor="w", padx=14)
        self._slider_row(c8, "context_length", 512, 32768, self.cfg.get("context_length", 4096), resolution=128, as_int=True)

        c9 = _section_card(s); c9.pack(fill="x", pady=5)
        _lbl(c9, "GPU Layers (num_gpu)", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(c9, "-1 = auto (all layers on GPU). 0 = CPU only.", color=DIM).pack(anchor="w", padx=14)
        self._slider_row(c9, "num_gpu_layers", -1, 128, self.cfg.get("num_gpu_layers", -1), resolution=1, as_int=True)

        c10 = _section_card(s); c10.pack(fill="x", pady=5)
        _lbl(c10, "CPU Threads", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(c10, "Number of CPU threads for inference.", color=DIM).pack(anchor="w", padx=14)
        self._slider_row(c10, "num_threads", 1, 32, self.cfg.get("num_threads", 4), resolution=1, as_int=True)

        c11 = _section_card(s); c11.pack(fill="x", pady=5)
        _lbl(c11, "Seed", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(c11, "-1 = random each time. Any other value = reproducible output.", color=DIM).pack(anchor="w", padx=14)
        self._vars["seed"] = self._text_field(c11, "seed", str(self.cfg.get("seed",-1)))

        c12 = _section_card(s); c12.pack(fill="x", pady=5)
        _lbl(c12, "Keep Alive", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(c12, "How long Ollama keeps model loaded (e.g. 5m, 1h, 0 = unload immediately).", color=DIM).pack(anchor="w", padx=14)
        self._vars["keep_alive"] = self._text_field(c12, "keep_alive", self.cfg.get("keep_alive","5m"))

        c13 = _section_card(s); c13.pack(fill="x", pady=5)
        _lbl(c13, "System Prompt", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(c13, "Injected at the start of every Ollama conversation.", color=DIM).pack(anchor="w", padx=14)
        self._sys_prompt_box = ctk.CTkTextbox(
            c13, font=("Courier",11), fg_color=CARD, text_color=CYAN,
            border_color=BORDER, border_width=1, corner_radius=8, height=100
        )
        self._sys_prompt_box.pack(fill="x", padx=14, pady=(6,10))
        self._sys_prompt_box.insert("1.0", self.cfg.get("system_prompt", DEFAULT_CONFIG["system_prompt"]))

        bot = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0)
        bot.pack(fill="x", side="bottom")
        bot_inner = ctk.CTkFrame(bot, fg_color="transparent")
        bot_inner.pack(fill="x", padx=16, pady=10)

        self._status_lbl = _lbl(bot_inner, "", color=GREEN)
        self._status_lbl.pack(side="left")

        _btn(bot_inner, "↺  RESTART", self._save_and_restart,
             color="#1a3a00", text_color=GREEN,
             border_width=1, border_color=GREEN, width=130).pack(side="right", padx=(8,0))
        _btn(bot_inner, "✓  SAVE", self._save_only, width=100).pack(side="right")

    def _text_field(self, parent, key, placeholder=""):
        e = _entry(parent)
        e.pack(fill="x", padx=14, pady=(6,10))
        e.insert(0, str(self.cfg.get(key, placeholder)))
        return e

    def _slider_row(self, parent, key, min_val, max_val, init_val, resolution=0.01, as_int=False):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(6,10))
        row.grid_columnconfigure(0, weight=1)

        val_var   = tk.DoubleVar(value=float(init_val))
        entry_var = tk.StringVar(value=self._fmt(init_val, as_int))
        entry = ctk.CTkEntry(row, textvariable=entry_var, width=68,
                              font=("Courier",12), fg_color=CARD,
                              text_color=CYAN, border_color=BORDER,
                              border_width=1, corner_radius=6, justify="center")
        entry.grid(row=0, column=1, padx=(8,0))

        def on_slider(v):
            raw = float(v)
            if as_int: raw = int(round(raw))
            raw = max(min_val, min(max_val, raw))
            val_var.set(raw); entry_var.set(self._fmt(raw, as_int))

        def on_entry_commit(event=None):
            try:
                raw = float(entry_var.get())
                if as_int: raw = int(round(raw))
                raw = max(min_val, min(max_val, raw))
            except ValueError:
                raw = val_var.get()
            val_var.set(raw); entry_var.set(self._fmt(raw, as_int)); sl.set(raw)

        entry.bind("<Return>",   on_entry_commit)
        entry.bind("<FocusOut>", on_entry_commit)

        sl = ctk.CTkSlider(row, from_=min_val, to=max_val, variable=val_var,
                           command=on_slider, button_color=CYAN,
                           button_hover_color="#00ccdd", progress_color=BORDER)
        sl.grid(row=0, column=0, sticky="ew")
        self._vars[key] = val_var

    @staticmethod
    def _fmt(v, as_int):
        return str(int(v)) if as_int else f"{float(v):.2f}"

    def _fetch_models_async(self):
        threading.Thread(target=self._fetch_models, daemon=True).start()

    def _fetch_models(self):
        url = self.cfg.get("ollama_url","http://localhost:11434")
        try:
            r = requests.get(f"{url}/api/tags", timeout=4)
            models = [m["name"] for m in r.json().get("models", [])]
        except Exception:
            models = []
        self.after(0, lambda: self._set_model_list(models))

    def _set_model_list(self, models):
        if not models:
            models = ["(no models found — is Ollama running?)"]
        self._model_menu.configure(values=models)
        current = self.cfg.get("ollama_model","")
        if current in models:
            self._model_var.set(current)
        else:
            self._model_var.set(models[0])

    def _browse_dir(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(title="Select Ollama Models Directory")
        if path:
            e = self._vars.get("ollama_models_dir")
            if e: e.delete(0, "end"); e.insert(0, path)

    def _collect(self):
        cfg = dict(self.cfg)
        cfg["ollama_model"]      = self._model_var.get()
        cfg["system_prompt"]     = self._sys_prompt_box.get("1.0","end-1c").strip()
        cfg["ollama_url"]        = self._vars["ollama_url"].get().strip()
        cfg["ollama_models_dir"] = self._vars["ollama_models_dir"].get().strip()
        cfg["seed"]              = int(self._vars["seed"].get().strip() or -1)
        cfg["keep_alive"]        = self._vars["keep_alive"].get().strip()
        for key in ["temperature","top_p","top_k","repeat_penalty",
                    "context_length","num_gpu_layers","num_threads"]:
            v = self._vars[key].get()
            cfg[key] = int(round(v)) if key in ("top_k","context_length","num_gpu_layers","num_threads") else round(v, 3)
        return cfg

    def _save_only(self):
        save_config(self._collect())
        self._status_lbl.configure(text="✓ Saved", text_color=GREEN)
        self.after(2000, lambda: self._status_lbl.configure(text=""))

    def _save_and_restart(self):
        save_config(self._collect())
        self._status_lbl.configure(text="⟳  Restarting…", text_color=ORANGE)
        self.after(800, self._do_restart)

    def _do_restart(self):
        if self.on_restart:
            self.on_restart()
        else:
            python = sys.executable
            os.execl(python, python, *sys.argv)

    def _back(self):
        self.destroy()
        if self.on_back: self.on_back()


# ─────────────────────────────────────────────────────────────
#  CODE PANEL
# ─────────────────────────────────────────────────────────────
class HorowaCodePanel(ctk.CTkFrame):
    def __init__(self, master, on_close, **kwargs):
        super().__init__(master, fg_color="#080d14", corner_radius=20,
                         border_width=1, border_color=CYAN, **kwargs)
        self.on_close = on_close
        self._tabs = []; self._active = 0
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=12, pady=(12,0))
        hdr.grid_columnconfigure(1, weight=1)

        _btn(hdr, "✕", self._close, color="transparent",
             text_color=RED, border_width=1, border_color=RED, width=28, height=28
             ).grid(row=0, column=0, padx=(0,8))
        _lbl(hdr, "CODE VIEWER", font=("Courier",14,"bold"), color=CYAN).grid(row=0, column=1, sticky="w")

        self.copy_btn = _ghost_btn(hdr, "⎘ COPY", self._copy_active, width=80, height=28)
        self.copy_btn.grid(row=0, column=2, sticky="e")

        self.tab_bar = ctk.CTkFrame(self, fg_color="transparent")
        self.tab_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(6,0))

        cf = ctk.CTkFrame(self, fg_color="#06080f", corner_radius=8,
                          border_width=1, border_color="#1a3a3a")
        cf.grid(row=2, column=0, sticky="nsew", padx=12, pady=(6,12))
        cf.grid_rowconfigure(0, weight=1); cf.grid_columnconfigure(0, weight=1)

        self.code_text = tk.Text(cf, font=("Courier",12), bg="#06080f", fg=CYAN,
                                  insertbackground="#06080f", selectbackground="#1a3a5a",
                                  wrap="none", state="disabled", relief="flat", bd=0, padx=10, pady=8)
        vsb = tk.Scrollbar(cf, orient="vertical", command=self.code_text.yview)
        hsb = tk.Scrollbar(cf, orient="horizontal", command=self.code_text.xview)
        self.code_text.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.code_text.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns"); hsb.grid(row=1, column=0, sticky="ew")

    def _close(self):
        self._tabs=[]; self._active=0; self.on_close()

    def _copy_active(self):
        if not self._tabs: return
        self.clipboard_clear(); self.clipboard_append(self._tabs[self._active][1])
        self.copy_btn.configure(text="✓ COPIED", text_color=GREEN, border_color=GREEN)
        self.after(1500, lambda: self.copy_btn.configure(text="⎘ COPY", text_color=DIM, border_color=BORDER))

    def _rebuild_tabs(self):
        for w in self.tab_bar.winfo_children(): w.destroy()
        for i,(label,_) in enumerate(self._tabs):
            active = (i==self._active)
            ctk.CTkButton(self.tab_bar, text=label, width=90, height=26,
                          font=("Courier",11,"bold"),
                          fg_color=CYAN if active else "transparent",
                          text_color="#000d11" if active else CYAN,
                          border_width=1, border_color=CYAN, corner_radius=6,
                          command=lambda idx=i: self._switch_tab(idx)).pack(side="left", padx=(0,6))

    def _switch_tab(self, idx):
        self._active=idx; self._rebuild_tabs(); self._render_active()

    def _render_active(self):
        if not self._tabs: return
        _, code = self._tabs[self._active]
        apply_syntax_highlighting(self.code_text, code)

    def load_blocks(self, blocks):
        self._tabs=[]; self._active=0
        for i,(lang,code) in enumerate(blocks):
            self._tabs.append((lang.upper() if lang else f"BLOCK {i+1}", code))
        self._rebuild_tabs(); self._render_active()


# ─────────────────────────────────────────────────────────────
#  MAIN GUI
# ─────────────────────────────────────────────────────────────
class HorowaGUI(ctk.CTk):
    def __init__(self, on_input_callback, on_toggle_mic,
                 on_toggle_speaker, on_toggle_mode, on_toggle_hotword,
                 on_restart=None):
        super().__init__()
        self.mic_on            = True
        self.speaker_on        = True
        self.hotword_on        = True
        self.on_input_callback = on_input_callback
        self.on_toggle_mic     = on_toggle_mic
        self.on_toggle_speaker = on_toggle_speaker
        self.on_toggle_mode    = on_toggle_mode
        self.on_toggle_hotword = on_toggle_hotword
        self.on_restart        = on_restart

        self._current_mode     = "OFFLINE"
        self._maximized        = False
        self._sphere_active    = False
        self._sphere_amplitude = 0.0
        self._sphere_target    = 0.0
        self._wave_offset      = 0.0
        self._blob_points      = 120
        self._is_thinking      = False
        self._thinking_dots    = 0
        self._thinking_scan    = 0.0    # 0.0–1.0 scan position
        self._breath           = 0.0
        self._breath_dir       = 1
        self._is_sleeping      = False
        self._minimized        = False
        self._code_open        = False
        self._siri_hue         = 0.0
        self._ripples          = []
        self._msg_fade_jobs    = []     # active fade-in jobs
        self._status_flash     = 0     # counter for status flash

        # Load animation flags live
        cfg = load_config()
        self._anim_flags = {
            "anim_sphere":          cfg.get("anim_sphere",        True),
            "anim_ripple":          cfg.get("anim_ripple",        True),
            "anim_message_fade":    cfg.get("anim_message_fade",  True),
            "anim_button_pulse":    cfg.get("anim_button_pulse",  True),
            "anim_thinking_scan":   cfg.get("anim_thinking_scan", True),
            "anim_status_flash":    cfg.get("anim_status_flash",  True),
        }

        self.title("HOROWA AI")
        self.geometry("1100x700")
        self.resizable(True, True)
        ctk.set_appearance_mode("dark")
        self.configure(fg_color=BG)
        self.attributes("-alpha", 0.96)

        self._build_normal_layout()
        self.after(100, self._animate_sphere)

    # ═══════════════════════════════════════════════════════════
    #  LAYOUT
    # ═══════════════════════════════════════════════════════════

    def _build_normal_layout(self):
        self.grid_columnconfigure(0, weight=1, uniform="col")
        self.grid_columnconfigure(1, weight=2, uniform="col")
        self.grid_columnconfigure(2, weight=2, uniform="col")
        self.grid_rowconfigure(0, weight=1)

        # LEFT PANEL
        self.left_panel = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=20,
                                        border_width=1, border_color=BORDER)
        self.left_panel.grid(row=0, column=0, padx=(16,8), pady=16, sticky="nsew")
        self.left_panel.grid_rowconfigure(2, weight=1)
        self.left_panel.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(self.left_panel, text="◈ HOROWA // ACTIVE",
                                          font=("Courier",13,"bold"), text_color=CYAN,
                                          wraplength=180, justify="center")
        self.status_label.grid(row=0, column=0, pady=(18,0), padx=6)

        self.hotword_label = ctk.CTkLabel(self.left_panel, text="⬤  HOTWORD: ON",
                                           font=("Courier",11), text_color=GREEN)
        self.hotword_label.grid(row=1, column=0, pady=(4,0))

        self.sphere_canvas = tk.Canvas(self.left_panel, bg=PANEL, highlightthickness=0)
        self.sphere_canvas.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)

        lb = ctk.CTkFrame(self.left_panel, fg_color="transparent")
        lb.grid(row=3, column=0, pady=(0,8), padx=16, sticky="ew")
        lb.grid_columnconfigure((0,1), weight=1)
        bc = dict(height=32, font=("Courier",11,"bold"), corner_radius=8)

        self.mic_btn = ctk.CTkButton(lb, text="MIC: ON", fg_color=CYAN, text_color="#000d11",
                                      command=self._mic_btn_click, **bc)
        self.mic_btn.grid(row=0, column=0, padx=4, pady=3, sticky="ew")

        self.hotword_btn = ctk.CTkButton(lb, text="HOTWORD: ON", border_width=1,
                                          border_color=GREEN, fg_color="transparent",
                                          text_color=GREEN, command=self._hotword_btn_click, **bc)
        self.hotword_btn.grid(row=0, column=1, padx=4, pady=3, sticky="ew")

        self.spk_btn = ctk.CTkButton(lb, text="SPEAKER: ON", fg_color=CYAN, text_color="#000d11",
                                      command=self._spk_btn_click, **bc)
        self.spk_btn.grid(row=1, column=0, columnspan=2, padx=4, pady=3, sticky="ew")

        # CODE PANEL
        self.code_panel = HorowaCodePanel(self, on_close=self._close_code_panel)

        # RIGHT PANEL
        self.right_panel = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=20,
                                         border_width=1, border_color=BORDER)
        self.right_panel.grid(row=0, column=1, columnspan=2, padx=(8,16), pady=16, sticky="nsew")
        self.right_panel.grid_rowconfigure(1, weight=1)
        self.right_panel.grid_columnconfigure(0, weight=1)

        rh = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        rh.grid(row=0, column=0, sticky="ew", padx=16, pady=(14,0))
        rh.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(rh, text="TERMINAL", font=("Courier",16,"bold"),
                     text_color=CYAN).grid(row=0, column=0, sticky="w")

        self.settings_btn = ctk.CTkButton(
            rh, text="⚙", width=36, height=36,
            fg_color=CARD, border_width=1, border_color=BORDER,
            text_color=CYAN, font=("Courier",16,"bold"),
            corner_radius=10, command=self._open_settings
        )
        self.settings_btn.grid(row=0, column=1, sticky="e", padx=(0,4))

        self.max_btn = ctk.CTkButton(
            rh, text="⛶", width=32, height=32,
            fg_color="transparent", border_width=1,
            border_color=BORDER, text_color=CYAN,
            font=("Courier",13), command=self._toggle_maximize
        )
        self.max_btn.grid(row=0, column=2, sticky="e")

        cf = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        cf.grid(row=1, column=0, padx=14, pady=(8,0), sticky="nsew")
        cf.grid_rowconfigure(0, weight=1); cf.grid_columnconfigure(0, weight=1)

        self.console = tk.Text(cf, font=("Courier",13), bg="#06080f", fg=CYAN,
                                insertbackground="#06080f", selectbackground="#1a3a5a",
                                wrap="word", state="disabled", relief="flat", bd=0, padx=8, pady=6)
        vsb = tk.Scrollbar(cf, orient="vertical", command=self.console.yview)
        self.console.configure(yscrollcommand=vsb.set)
        self.console.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        # Thinking label — now also hosts scan bar via canvas
        self.thinking_frame = ctk.CTkFrame(self.right_panel, fg_color="transparent", height=22)
        self.thinking_frame.grid(row=2, column=0, padx=18, pady=(2,0), sticky="ew")
        self.thinking_frame.grid_propagate(False)
        self.thinking_frame.grid_columnconfigure(0, weight=1)

        self.thinking_label = ctk.CTkLabel(self.thinking_frame, text="",
                                            font=("Courier",12), text_color=PURPLE, anchor="w")
        self.thinking_label.grid(row=0, column=0, sticky="ew")

        self.scan_canvas = tk.Canvas(self.thinking_frame, bg=BG,
                                      highlightthickness=0, height=3)
        self.scan_canvas.grid(row=1, column=0, sticky="ew", pady=(2,0))

        inf = ctk.CTkFrame(self.right_panel, fg_color="transparent")
        inf.grid(row=3, column=0, padx=14, pady=(4,12), sticky="ew")
        inf.grid_columnconfigure(0, weight=1)

        self.user_input = ctk.CTkTextbox(inf, font=("Courier",13),
                                          border_color=BORDER, border_width=2,
                                          fg_color="#06080f", text_color=CYAN,
                                          scrollbar_button_color=CYAN,
                                          wrap="word", height=42, activate_scrollbars=True)
        self.user_input.grid(row=0, column=0, sticky="ew", padx=(0,8))
        self.user_input.bind("<Return>", self._on_input_return)
        self.user_input.bind("<KeyRelease>", self._resize_input)
        self.user_input.bind("<Shift-Return>", lambda e: None)

        self.send_btn = ctk.CTkButton(inf, text="SEND", fg_color=CYAN, text_color="#000d11",
                                       font=("Courier",13,"bold"), width=80, height=42,
                                       corner_radius=8, command=self._submit_with_pulse)
        self.send_btn.grid(row=0, column=1)

        self.status_bar = ctk.CTkLabel(self.right_panel,
                                        text="○  MODE: OFFLINE   [click to toggle]",
                                        anchor="w", fg_color=CARD, text_color=CYAN,
                                        font=("Courier",11), padx=12, height=28,
                                        cursor="hand2", corner_radius=10)
        self.status_bar.grid(row=4, column=0, padx=14, pady=(0,12), sticky="ew")
        self.status_bar.bind("<Button-1>", lambda e: self._mode_toggle_with_flash())

        self._cb_mic=self.on_toggle_mic
        self._cb_spk=self.on_toggle_speaker
        self._cb_hotword=self.on_toggle_hotword

    # ═══════════════════════════════════════════════════════════
    #  ANIMATED BUTTON CALLBACKS
    # ═══════════════════════════════════════════════════════════

    def _mic_btn_click(self):
        self.on_toggle_mic()
        # pulse after toggle so color reflects new state
        new_color = CYAN if self.mic_on else "#1a1a1a"
        if self._anim_flags.get("anim_button_pulse"):
            pulse_button(self.mic_btn, new_color, "#ffffff")

    def _spk_btn_click(self):
        self.on_toggle_speaker()
        new_color = CYAN if self.speaker_on else "#1a1a1a"
        if self._anim_flags.get("anim_button_pulse"):
            pulse_button(self.spk_btn, new_color, "#ffffff")

    def _hotword_btn_click(self):
        if self._anim_flags.get("anim_button_pulse"):
            pulse_button(self.hotword_btn, "transparent", GREEN)
        self.on_toggle_hotword()

    def _submit_with_pulse(self):
        if self._anim_flags.get("anim_button_pulse"):
            pulse_button(self.send_btn, CYAN, "#ffffff")
        self._submit()

    def _mode_toggle_with_flash(self):
        self.on_toggle_mode()
        if self._anim_flags.get("anim_status_flash"):
            self._status_flash = 6
            self._flash_status_bar()

    def _flash_status_bar(self):
        if self._status_flash <= 0:
            return
        color = ORANGE if self._status_flash % 2 == 0 else CARD
        try:
            self.status_bar.configure(fg_color=color)
            self._status_flash -= 1
            self.after(80, self._flash_status_bar)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════
    #  SETTINGS
    # ═══════════════════════════════════════════════════════════

    def _open_settings(self):
        HorowaSettingsOverlay(self, on_restart=self.on_restart)

    # ═══════════════════════════════════════════════════════════
    #  CODE PANEL
    # ═══════════════════════════════════════════════════════════

    def show_code_panel(self, blocks):
        self.code_panel.load_blocks(blocks)
        if not self._code_open:
            self._code_open = True
            self.right_panel.grid_configure(column=2, columnspan=1, padx=(8,16))
            self.code_panel.grid(row=0, column=1, padx=(8,8), pady=16, sticky="nsew")

    def _close_code_panel(self):
        self._code_open = False
        self.code_panel.grid_remove()
        self.right_panel.grid_configure(column=1, columnspan=2, padx=(8,16))

    # ═══════════════════════════════════════════════════════════
    #  MINIMIZE — smooth shrink to bottom-right
    # ═══════════════════════════════════════════════════════════

    def minimize_to_sphere(self):
        if self._minimized: return
        self._minimized = True

        # Snapshot current geometry
        self.update_idletasks()
        start_w = self.winfo_width()
        start_h = self.winfo_height()
        start_x = self.winfo_x()
        start_y = self.winfo_y()

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        end_w, end_h = 220, 280
        end_x = sw - end_w - 12
        end_y = sh - end_h - 48   # just above taskbar

        steps  = 18
        self._mini_step = 0

        def _shrink():
            t = self._mini_step / steps
            # ease-out cubic
            e = 1 - (1 - t) ** 3
            cur_w = int(start_w + (end_w - start_w) * e)
            cur_h = int(start_h + (end_h - start_h) * e)
            cur_x = int(start_x + (end_x - start_x) * e)
            cur_y = int(start_y + (end_y - start_y) * e)

            # Hide panels partway through
            if self._mini_step == 4:
                self.left_panel.grid_remove()
                self.right_panel.grid_remove()
                if self._code_open: self.code_panel.grid_remove()
                self.overrideredirect(True)

            self.geometry(f"{cur_w}x{cur_h}+{cur_x}+{cur_y}")
            self._mini_step += 1

            if self._mini_step <= steps:
                self.after(16, _shrink)
            else:
                self.geometry(f"{end_w}x{end_h}+{end_x}+{end_y}")
                self._build_mini_ui()

        _shrink()

    def _build_mini_ui(self):
        """Build the mini floating sphere UI after shrink animation completes."""
        self._mini_frame = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=18,
                                         border_width=1, border_color=BORDER)
        self._mini_frame.pack(fill="both", expand=True, padx=0, pady=0)
        self._mini_frame.grid_rowconfigure(1, weight=1)
        self._mini_frame.grid_columnconfigure(0, weight=1)

        # ── iPhone-style drag bar ──────────────────────────
        drag_bar = tk.Canvas(self._mini_frame, bg=PANEL, highlightthickness=0, height=18)
        drag_bar.grid(row=0, column=0, sticky="ew", padx=0, pady=(6,0))
        # Draw the pill
        drag_bar.bind("<Configure>", lambda e: self._draw_drag_pill(drag_bar))
        drag_bar.bind("<Button-1>",     self._mini_drag_start)
        drag_bar.bind("<B1-Motion>",    self._mini_drag_move)
        drag_bar.bind("<Double-Button-1>", lambda e: self.restore_from_sphere())
        self._drag_bar = drag_bar
        self._drag_offset = (0, 0)

        # ── Sphere canvas ──────────────────────────────────
        self.sphere_canvas = tk.Canvas(self._mini_frame, bg=PANEL,
                                        highlightthickness=0, width=200, height=180)
        self.sphere_canvas.grid(row=1, column=0, padx=4, pady=(0,4), sticky="nsew")
        self.sphere_canvas.bind("<Button-1>", lambda e: self.restore_from_sphere())

        # ── Icon button row ────────────────────────────────
        br = ctk.CTkFrame(self._mini_frame, fg_color="transparent")
        br.grid(row=2, column=0, pady=(0,10))

        icon_cfg = dict(width=40, height=40, corner_radius=20,
                        font=("Segoe UI Emoji", 14), border_width=1)

        # MIC
        mic_icon = "🎙" if self.mic_on else "🔇"
        self._mini_mic_btn = ctk.CTkButton(
            br, text=mic_icon,
            fg_color=CYAN if self.mic_on else "#1a1a1a",
            text_color="#000d11" if self.mic_on else "#555",
            border_color=CYAN,
            command=self._mini_toggle_mic, **icon_cfg)
        self._mini_mic_btn.pack(side="left", padx=4)

        # SPK
        spk_icon = "🔊" if self.speaker_on else "🔕"
        self._mini_spk_btn = ctk.CTkButton(
            br, text=spk_icon,
            fg_color=CYAN if self.speaker_on else "#1a1a1a",
            text_color="#000d11" if self.speaker_on else "#555",
            border_color=CYAN,
            command=self._mini_toggle_spk, **icon_cfg)
        self._mini_spk_btn.pack(side="left", padx=4)

        # HW
        hw_icon = "👂" if self.hotword_on else "🚫"
        self._mini_hw_btn = ctk.CTkButton(
            br, text=hw_icon,
            fg_color=GREEN if self.hotword_on else "#1a1a1a",
            text_color="#000d11" if self.hotword_on else "#555",
            border_color=GREEN,
            command=self._mini_toggle_hw, **icon_cfg)
        self._mini_hw_btn.pack(side="left", padx=4)

        self.after(50, lambda: self._draw_drag_pill(drag_bar))

    def _draw_drag_pill(self, canvas):
        canvas.delete("all")
        w = canvas.winfo_width()
        if w < 10: return
        pw, ph = 40, 5
        x = (w - pw) // 2
        y = 6
        canvas.create_rounded_rect = None  # not available; use oval trick
        canvas.create_oval(x, y, x+ph, y+ph, fill="#444", outline="")
        canvas.create_rectangle(x+ph//2, y, x+pw-ph//2, y+ph, fill="#444", outline="")
        canvas.create_oval(x+pw-ph, y, x+pw, y+ph, fill="#444", outline="")

    def _mini_drag_start(self, event):
        self._drag_offset = (event.x_root - self.winfo_x(),
                             event.y_root - self.winfo_y())

    def _mini_drag_move(self, event):
        x = event.x_root - self._drag_offset[0]
        y = event.y_root - self._drag_offset[1]
        self.geometry(f"+{x}+{y}")

    def _mini_toggle_mic(self):
        self._cb_mic()
        icon = "🎙" if self.mic_on else "🔇"
        self._mini_mic_btn.configure(
            text=icon,
            fg_color=CYAN if self.mic_on else "#1a1a1a",
            text_color="#000d11" if self.mic_on else "#555")

    def _mini_toggle_spk(self):
        self._cb_spk()
        icon = "🔊" if self.speaker_on else "🔕"
        self._mini_spk_btn.configure(
            text=icon,
            fg_color=CYAN if self.speaker_on else "#1a1a1a",
            text_color="#000d11" if self.speaker_on else "#555")

    def _mini_toggle_hw(self):
        self._cb_hotword()
        icon = "👂" if self.hotword_on else "🚫"
        self._mini_hw_btn.configure(
            text=icon,
            fg_color=GREEN if self.hotword_on else "#1a1a1a",
            text_color="#000d11" if self.hotword_on else "#555")

    def restore_from_sphere(self):
        if not self._minimized: return

        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        end_w, end_h = 1100, 700
        end_x = (sw - end_w) // 2
        end_y = (sh - end_h) // 2

        start_x = self.winfo_x()
        start_y = self.winfo_y()
        start_w = self.winfo_width()
        start_h = self.winfo_height()

        steps = 18
        step  = [0]

        # Remove mini UI immediately
        try: self._mini_frame.destroy()
        except Exception: pass
        self.overrideredirect(False)
        self.resizable(True, True)

        # Rebuild sphere canvas placeholder
        self.sphere_canvas = tk.Canvas(self.left_panel, bg=PANEL, highlightthickness=0)

        def _expand():
            t = step[0] / steps
            e = 1 - (1 - t) ** 3
            cur_w = int(start_w + (end_w - start_w) * e)
            cur_h = int(start_h + (end_h - start_h) * e)
            cur_x = int(start_x + (end_x - start_x) * e)
            cur_y = int(start_y + (end_y - start_y) * e)
            self.geometry(f"{cur_w}x{cur_h}+{cur_x}+{cur_y}")
            step[0] += 1
            if step[0] <= steps:
                self.after(16, _expand)
            else:
                self._minimized = False
                self.geometry(f"{end_w}x{end_h}+{end_x}+{end_y}")
                self.sphere_canvas.grid(row=2, column=0, sticky="nsew", padx=10, pady=10)
                self.left_panel.grid(row=0, column=0, padx=(16,8), pady=16, sticky="nsew")
                self.right_panel.grid(
                    row=0,
                    column=2 if self._code_open else 1,
                    columnspan=1 if self._code_open else 2,
                    padx=(8,16), pady=16, sticky="nsew")
                if self._code_open:
                    self.code_panel.grid(row=0, column=1, padx=(8,8), pady=16, sticky="nsew")

        _expand()

    # ═══════════════════════════════════════════════════════════
    #  CONSOLE — with fade-in animation
    # ═══════════════════════════════════════════════════════════

    def _console_write(self, text):
        self.console.configure(state="normal")
        self.console.insert("end", text)
        self.console.configure(state="disabled")
        self.console.see("end")

    def log_msg(self, msg, sender="SYSTEM"):
        if self._anim_flags.get("anim_message_fade") and sender in ("HOROWA AI", "USER"):
            self._console_fade_in(f"[{sender}]: {msg}\n", sender)
        else:
            self._console_write(f"[{sender}]: {msg}\n")

        if sender == "HOROWA AI":
            self.set_sphere_active(True, 0.65)
            if self._anim_flags.get("anim_ripple"):
                self._trigger_ripple()
            self.after(2500, lambda: self.set_sphere_active(False))
            blocks = self._extract_code_blocks(msg)
            if blocks: self.show_code_panel(blocks)

    def _console_fade_in(self, text, sender):
        """Fade text in by cycling through dim → bright colour tags over ~300ms."""
        self.console.configure(state="normal")
        tag = f"fade_{id(text)}_{sender}"
        fade_colors = ["#1a3a3a", "#2a5a5a", "#3a7a7a", "#4a9a9a", "#5ab5b5", CYAN]
        if sender == "HOROWA AI":
            fade_colors = ["#1a0830", "#2d1060", "#4a1a8a", "#7030c0", "#a060e0", PURPLE]
        elif sender == "USER":
            fade_colors = ["#003322", "#006644", "#009966", "#00bb88", "#00dd99", GREEN]

        start_idx = self.console.index("end-1c")
        self.console.insert("end", text)
        end_idx   = self.console.index("end-1c")
        self.console.tag_add(tag, start_idx, end_idx)
        self.console.tag_configure(tag, foreground=fade_colors[0])
        self.console.configure(state="disabled")
        self.console.see("end")

        def _step(i):
            if i >= len(fade_colors):
                try:
                    self.console.configure(state="normal")
                    self.console.tag_delete(tag)
                    self.console.configure(state="disabled")
                except Exception:
                    pass
                return
            try:
                self.console.tag_configure(tag, foreground=fade_colors[i])
                self.after(50, lambda: _step(i + 1))
            except Exception:
                pass

        self.after(30, lambda: _step(1))

    def _extract_code_blocks(self, text):
        matches = re.findall(r'```(\w*)\n([\s\S]*?)```', text)
        return [(lang or "code", code.strip()) for lang, code in matches] if matches else []

    # ═══════════════════════════════════════════════════════════
    #  INPUT
    # ═══════════════════════════════════════════════════════════

    def _on_input_return(self, event):
        if event.state & 0x1: return
        self._submit_with_pulse(); return "break"

    def _resize_input(self, event=None):
        content = self.user_input.get("1.0","end-1c")
        cpl = max(1, (self.user_input.winfo_width()-20)//8)
        vl = sum(max(1,(len(l)+cpl-1)//cpl) for l in content.split("\n"))
        self.user_input.configure(height=42+(max(1,min(5,vl))-1)*22)

    def _submit(self):
        text = self.user_input.get("1.0","end-1c").strip()
        if text:
            self.user_input.delete("1.0","end")
            self.user_input.configure(height=42)
            self.on_input_callback(text)

    # ═══════════════════════════════════════════════════════════
    #  SPHERE
    # ═══════════════════════════════════════════════════════════

    def set_sphere_active(self, active, amplitude=0.0):
        self._sphere_active = active
        self._sphere_target = max(0.0, min(1.0, amplitude))

    def show_thinking(self, thinking):
        self._is_thinking = thinking
        if not thinking:
            self.thinking_label.configure(text="")
            try: self.scan_canvas.delete("all")
            except Exception: pass

    def _trigger_ripple(self):
        self._ripples.append({"r": 0.0, "alpha": 1.0})

    def _hsv_to_hex(self, h, s, v):
        h=h%360; c=v*s; x=c*(1-abs((h/60)%2-1)); m=v-c
        if   h<60:  r,g,b=c,x,0
        elif h<120: r,g,b=x,c,0
        elif h<180: r,g,b=0,c,x
        elif h<240: r,g,b=0,x,c
        elif h<300: r,g,b=x,0,c
        else:       r,g,b=c,0,x
        return f"#{int((r+m)*255):02x}{int((g+m)*255):02x}{int((b+m)*255):02x}"

    def _animate_sphere(self):
        self._sphere_amplitude += (self._sphere_target-self._sphere_amplitude)*0.12
        if not self._sphere_active: self._sphere_target *= 0.88
        self._wave_offset += 0.06
        self._breath += 0.02*self._breath_dir
        if self._breath>=1.0: self._breath_dir=-1
        elif self._breath<=0.0: self._breath_dir=1
        speed = 1.2 if self._sphere_amplitude>0.1 else 0.4
        self._siri_hue = (self._siri_hue+speed)%360

        if self._anim_flags.get("anim_ripple"):
            self._ripples = [rp for rp in [{**r,"r":r["r"]+0.025,"alpha":r["alpha"]-0.018} for r in self._ripples] if rp["alpha"]>0]
        else:
            self._ripples = []

        if self._is_thinking and not self._minimized:
            self._thinking_dots=(self._thinking_dots+1)%4
            self.thinking_label.configure(text=f"HOROWA is processing{'.'*self._thinking_dots}")
            if self._anim_flags.get("anim_thinking_scan"):
                self._thinking_scan = (self._thinking_scan + 0.04) % 1.0
                self._draw_scan_bar()
            else:
                try: self.scan_canvas.delete("all")
                except Exception: pass

        if self._anim_flags.get("anim_sphere"):
            self._draw_sphere()

        self.after(30, self._animate_sphere)

    def _draw_scan_bar(self):
        try:
            c = self.scan_canvas
            c.delete("all")
            w = c.winfo_width()
            if w < 10: return
            # Bouncing gradient bar
            pos = self._thinking_scan
            # ping-pong: 0→1→0
            if pos > 0.5:
                pos = 1.0 - pos
            pos = pos * 2.0  # 0→1
            bar_w = int(w * 0.35)
            x = int(pos * (w - bar_w))
            # Draw gradient segments
            segments = 20
            for i in range(segments):
                t  = i / segments
                bx = x + int(t * bar_w)
                ex = x + int((i+1)/segments * bar_w)
                # brightest in centre
                intensity = 1.0 - abs(t - 0.5) * 2
                color = self._hsv_to_hex(self._siri_hue + 30, 0.8, 0.4 + intensity * 0.6)
                c.create_rectangle(bx, 0, ex, 3, fill=color, outline="")
        except Exception:
            pass

    def _draw_sphere(self):
        canvas=self.sphere_canvas; canvas.delete("all")
        w=canvas.winfo_width(); h=canvas.winfo_height()
        if w<10 or h<10: return
        cx,cy=w/2,h/2; base_r=min(w,h)*0.26
        amp=self._sphere_amplitude
        bs=1.0+(self._breath*0.04) if amp<0.05 else 1.0

        if amp>0.05 or self._is_thinking:
            for gm,af in [(1.7,0.15),(1.4,0.3)]:
                gr=base_r*gm*bs
                gc=self._hsv_to_hex(self._siri_hue+(30 if af>0.2 else 0),0.9,0.25*af+0.05)
                canvas.create_oval(cx-gr,cy-gr,cx+gr,cy+gr,fill=gc,outline="")

        for ho,ph,fr,sc in [(0,0,3,1.10),(60,math.pi/2,4,1.02),(120,math.pi/1.5,4,0.97),(200,math.pi/3,5,0.90)]:
            pts=[]; ls=sc*bs; color=self._hsv_to_hex(self._siri_hue+ho,0.75,0.8)
            for i in range(self._blob_points):
                angle=2*math.pi*i/self._blob_points
                wobble=(amp*base_r*0.42*math.sin(fr*angle+self._wave_offset+ph)+
                        amp*base_r*0.20*math.sin((fr+2)*angle-self._wave_offset*1.4+ph)+
                        amp*base_r*0.10*math.sin((fr+4)*angle+self._wave_offset*0.7))
                r=base_r*ls+wobble
                pts.extend([cx+r*math.cos(angle),cy+r*math.sin(angle)])
            if len(pts)>=4: canvas.create_polygon(pts,fill=color,outline="",smooth=True)

        for i in range(5):
            bh=(self._siri_hue+i*72)%360; bc=self._hsv_to_hex(bh,0.95,1.0)
            br=base_r*(0.78+i*0.055)*bs
            arc_start=(self._wave_offset*28+i*37)%360; arc_ext=55+amp*80
            canvas.create_arc(cx-br,cy-br,cx+br,cy+br,start=arc_start,extent=arc_ext,
                              style="arc",outline=bc,width=max(1,int(2+amp*4)))
            canvas.create_arc(cx-br,cy-br,cx+br,cy+br,start=arc_start+180,extent=arc_ext*0.7,
                              style="arc",outline=bc,width=max(1,int(1+amp*2)))

        core_r=base_r*0.22*bs+amp*base_r*0.12
        canvas.create_oval(cx-core_r*2.4,cy-core_r*2.4,cx+core_r*2.4,cy+core_r*2.4,
                           fill=self._hsv_to_hex(self._siri_hue,0.8,0.18),outline="")
        canvas.create_oval(cx-core_r*1.5,cy-core_r*1.5,cx+core_r*1.5,cy+core_r*1.5,
                           fill=self._hsv_to_hex(self._siri_hue+40,0.6,0.85),outline="")
        canvas.create_oval(cx-core_r,cy-core_r,cx+core_r,cy+core_r,
                           fill=self._hsv_to_hex(self._siri_hue,0.3,1.0),outline="")

        if self._anim_flags.get("anim_ripple"):
            for rp in self._ripples:
                rr=base_r*(1.0+rp["r"]*1.8); rc=self._hsv_to_hex(self._siri_hue,0.6,1.0)
                canvas.create_oval(cx-rr,cy-rr,cx+rr,cy+rr,outline=rc,
                                   width=max(1,int(rp["alpha"]*2.5)),
                                   dash=(int(4+rp["r"]*6),int(2+rp["r"]*3)) if rp["r"]>0.3 else ())

        if amp<0.05 and self._is_sleeping:
            rr=base_r*0.88*bs
            canvas.create_oval(cx-rr,cy-rr,cx+rr,cy+rr,outline="#1a3a4a",width=1,dash=(4,4))
        elif amp<0.05:
            rr=base_r*0.88*bs; tc=self._hsv_to_hex(self._siri_hue,0.7,0.9)
            canvas.create_oval(cx-rr,cy-rr,cx+rr,cy+rr,outline=BORDER,width=1)
            for i in range(12):
                a=2*math.pi*i/12+self._wave_offset*0.25; tl=8 if i%3==0 else 4
                canvas.create_line(cx+rr*math.cos(a),cy+rr*math.sin(a),
                                   cx+(rr+tl)*math.cos(a),cy+(rr+tl)*math.sin(a),
                                   fill=tc if i%3==0 else "#1a3a5a",width=1)

    # ═══════════════════════════════════════════════════════════
    #  PUBLIC API
    # ═══════════════════════════════════════════════════════════

    def _toggle_maximize(self):
        self._maximized=not self._maximized
        self.state("zoomed" if self._maximized else "normal")

    def set_sleeping_ui(self, sleeping):
        self._is_sleeping=sleeping
        self.status_label.configure(
            text="◈ HOROWA // SLEEPING" if sleeping else "◈ HOROWA // ACTIVE",
            text_color="#555" if sleeping else CYAN,
            font=("Courier",13,"bold"))

    def update_status(self, mode):
        self._current_mode=mode
        if mode=="ONLINE":
            self.status_bar.configure(text="●  MODE: ONLINE   [click to toggle]",text_color=GREEN)
        else:
            self.status_bar.configure(text="○  MODE: OFFLINE   [click to toggle]",text_color=CYAN)

    def update_hotword_ui(self, on):
        if on:
            self.hotword_btn.configure(text="HOTWORD: ON",border_color=GREEN,text_color=GREEN)
            self.hotword_label.configure(text="⬤  HOTWORD: ON",text_color=GREEN)
        else:
            self.hotword_btn.configure(text="HOTWORD: OFF",border_color="#555",text_color="#555")
            self.hotword_label.configure(text="⬤  HOTWORD: OFF",text_color="#555")

    def get_mode(self):
        return self._current_mode


# ─────────────────────────────────────────────────────────────
#  SKILLS OVERLAY
# ─────────────────────────────────────────────────────────────
class HorowaSkillsOverlay(ctk.CTkToplevel):
    def __init__(self, master, on_back=None):
        super().__init__(master)
        self.on_back = on_back
        self.title("HOROWA AI — Skills")
        self.geometry("540x640")
        self.configure(fg_color=BG)
        self.attributes("-alpha", 0.97)
        self.resizable(False, True)
        self.grab_set()

        self.cfg  = load_config()
        self._skill_toggles = {}
        self._build()

    def _build(self):
        _nav_bar(self, "⬡  SKILLS", back_cmd=self._back)
        sep = ctk.CTkFrame(self, fg_color=BORDER, height=1)
        sep.pack(fill="x", padx=16, pady=(0,10))

        fc = _section_card(self); fc.pack(fill="x", padx=14, pady=(0,8))
        _lbl(fc, "Skills Folder", font=("Courier",12,"bold"), color=CYAN).pack(anchor="w", padx=14, pady=(10,2))
        _lbl(fc, "LEO scans this folder for .py skill files on startup.", color=DIM).pack(anchor="w", padx=14)

        row = ctk.CTkFrame(fc, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(6,10))
        row.grid_columnconfigure(0, weight=1)

        self._dir_entry = _entry(row)
        self._dir_entry.insert(0, self.cfg.get("skills_dir","skills"))
        self._dir_entry.grid(row=0, column=0, sticky="ew", padx=(0,8))

        _ghost_btn(row, "Browse", self._browse_dir, width=70).grid(row=0, column=1, padx=(0,8))
        _btn(row, "Rescan", self._rescan, width=70).grid(row=0, column=2)

        imp_row = ctk.CTkFrame(self, fg_color="transparent")
        imp_row.pack(fill="x", padx=14, pady=(0,8))
        _btn(imp_row, "⊕  Import Skill (.py)", self._import_skill,
             color="transparent", text_color=GREEN,
             border_width=1, border_color=GREEN, height=34).pack(fill="x")

        self._scroll = ctk.CTkScrollableFrame(self, fg_color="transparent",
                                               scrollbar_button_color=CYAN)
        self._scroll.pack(fill="both", expand=True, padx=12, pady=(0,0))

        self._status_lbl = _lbl(self, "", color=GREEN)
        self._status_lbl.pack(pady=(4,0))

        bot = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=0)
        bot.pack(fill="x", side="bottom")
        _btn(bot, "✓  Save", self._save, width=100).pack(side="right", padx=16, pady=10)

        self._rescan()

    def _rescan(self):
        skills_dir = self._dir_entry.get().strip() or "skills"
        from skills_handler import discover_skills, _disabled_skills
        results = discover_skills(skills_dir)

        for w in self._scroll.winfo_children(): w.destroy()
        self._skill_toggles = {}

        if not results:
            _lbl(self._scroll, "No skill files found in this folder.", color=DIM).pack(pady=20)
            return

        for fname, mod, err in results:
            card = _section_card(self._scroll); card.pack(fill="x", pady=4)
            row  = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=10)
            row.grid_columnconfigure(1, weight=1)

            enabled = fname not in _disabled_skills
            var = tk.BooleanVar(value=enabled)
            self._skill_toggles[fname] = var
            sw = ctk.CTkSwitch(row, text="", variable=var, width=44,
                               button_color=CYAN, progress_color=BORDER)
            sw.grid(row=0, column=0, rowspan=2, padx=(0,12))

            if mod:
                name = getattr(mod, "SKILL_NAME", fname)
                desc = getattr(mod, "SKILL_DESCRIPTION", "No description.")
                ver  = getattr(mod, "SKILL_VERSION", "")
                label = f"{name}" + (f"  v{ver}" if ver else "")
                _lbl(row, label, font=("Courier",12,"bold"), color=CYAN, anchor="w").grid(row=0, column=1, sticky="ew")
                _lbl(row, desc, font=("Courier",10), color=DIM, anchor="w", wraplength=350, justify="left").grid(row=1, column=1, sticky="ew")
                n_tools = len(getattr(mod,"TOOLS",[]))
                _lbl(row, f"{n_tools} tool{'s' if n_tools!=1 else ''}", font=("Courier",10), color=BORDER).grid(row=0, column=2, padx=(8,0), sticky="e")
            else:
                _lbl(row, fname, font=("Courier",12,"bold"), color=RED, anchor="w").grid(row=0, column=1, sticky="ew")
                _lbl(row, f"Load error: {err}", font=("Courier",10), color=RED, anchor="w", wraplength=350).grid(row=1, column=1, sticky="ew")

        self._status_lbl.configure(text=f"{len(results)} skill file(s) found.", text_color=DIM)

    def _browse_dir(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(title="Select Skills Folder")
        if path:
            self._dir_entry.delete(0,"end")
            self._dir_entry.insert(0, path)

    def _import_skill(self):
        from tkinter import filedialog
        import shutil
        path = filedialog.askopenfilename(
            title="Import Skill",
            filetypes=[("Python files","*.py")]
        )
        if not path: return
        skills_dir = self._dir_entry.get().strip() or "skills"
        os.makedirs(skills_dir, exist_ok=True)
        dest = os.path.join(skills_dir, os.path.basename(path))
        shutil.copy2(path, dest)
        self._status_lbl.configure(text=f"Imported: {os.path.basename(path)}", text_color=GREEN)
        self._rescan()

    def _save(self):
        from skills_handler import set_skill_enabled
        for fname, var in self._skill_toggles.items():
            set_skill_enabled(fname, var.get())
        cfg = load_config()
        cfg["skills_dir"] = self._dir_entry.get().strip() or "skills"
        save_config(cfg)
        self._status_lbl.configure(text="✓ Saved", text_color=GREEN)
        self.after(2000, lambda: self._status_lbl.configure(text=""))

    def _back(self):
        self.destroy()
        if self.on_back: self.on_back()
