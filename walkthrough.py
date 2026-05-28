"""
walkthrough.py — HOROWA AI first-run setup wizard
Triggered from main.py if config.json doesn't exist.
"""
import os
import json
import threading
import tkinter as tk
import customtkinter as ctk

CONFIG_PATH = "config.json"

BG     = "#080d14"
PANEL  = "#0b1520"
CARD   = "#0d1a24"
BORDER = "#1a4a6a"
CYAN   = "#00fbff"
GREEN  = "#00ffaa"
DIM    = "#8ecfdf"
RED    = "#ff4444"
ORANGE = "#ffaa00"

PROVIDER_COLORS = {
    "gemini":    "#4285F4",
    "openai":    "#10a37f",
    "anthropic": "#b5836e",
}

DEFAULT_CONFIG = {
    "ollama_model":         "",
    "ollama_url":           "http://localhost:11434",
    "ollama_models_dir":    "",
    "temperature":          0.7,
    "top_p":                0.9,
    "top_k":                40,
    "repeat_penalty":       1.1,
    "context_length":       4096,
    "num_gpu_layers":       -1,
    "num_threads":          4,
    "system_prompt": (
        "You are HOROWA AI, a high-tech terminal-based AI assistant. "
        "Your responses should be concise, professional, and slightly robotic. "
        "Never output markdown formatting or asterisks. "
        "When asked to write code, output it in a plain fenced code block "
        "using triple backticks and the language name. "
        "When the user asks you to do something on their computer, use the available tools. "
        "You remember previous messages in this conversation."
    ),
    "online_system_prompt": (
        "You are HOROWA AI, a high-tech terminal-based AI assistant. "
        "Your responses should be concise, professional, and slightly robotic. "
        "Never output markdown formatting or asterisks."
    ),
    "seed":            -1,
    "keep_alive":      "5m",
    "api_keys":        {},
    "online_provider": "gemini",
    "online_model":    "",
    "anim_sphere":         True,
    "anim_ripple":         True,
    "anim_message_fade":   True,
    "anim_button_pulse":   True,
    "anim_thinking_scan":  True,
    "anim_status_flash":   True,
    "disabled_skills":     [],
    "skills_dir":          "skills",
}


def _lbl(parent, text, font=("Courier", 11), color=DIM, **kw):
    return ctk.CTkLabel(parent, text=text, font=font, text_color=color, **kw)

def _btn(parent, text, command, color=CYAN, text_color="#000d11", **kw):
    cfg = dict(font=("Courier", 11, "bold"), corner_radius=8,
               fg_color=color, text_color=text_color, height=36)
    cfg.update(kw)
    return ctk.CTkButton(parent, text=text, command=command, **cfg)

def _skip_btn(parent, command):
    return ctk.CTkButton(
        parent, text="Skip →", command=command,
        font=("Courier", 10), corner_radius=6,
        fg_color="transparent", text_color="#555",
        border_width=1, border_color="#333",
        height=28, width=70
    )

def _back_btn(parent, command):
    return ctk.CTkButton(
        parent, text="← Back", command=command,
        font=("Courier", 10), corner_radius=6,
        fg_color="transparent", text_color="#555",
        border_width=1, border_color="#333",
        height=28, width=70
    )


class WalkthroughApp(ctk.CTk):
    STEPS = ["welcome", "provider", "api_key", "model", "hotword", "done"]

    def __init__(self):
        super().__init__()
        self.title("HOROWA AI — Setup Wizard")
        self.geometry("580x520")
        self.minsize(480, 460)
        self.resizable(True, True)          # maximizable
        self.configure(fg_color=BG)
        ctk.set_appearance_mode("dark")

        self._step_idx = 0
        self._cfg      = dict(DEFAULT_CONFIG)
        self._provider = "gemini"
        self._api_key  = ""
        self._model    = ""
        self._models   = []

        self._build_shell()
        self._show_step()

    # ── Shell (persistent chrome) ─────────────────────────────

    def _build_shell(self):
        # Progress dots
        self._dot_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._dot_frame.pack(pady=(18, 0))

        # Content card
        self._content = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=20,
                                      border_width=1, border_color=BORDER)
        self._content.pack(fill="both", expand=True, padx=24, pady=16)

    def _refresh_dots(self):
        for w in self._dot_frame.winfo_children():
            w.destroy()
        for i, _ in enumerate(self.STEPS):
            active  = (i == self._step_idx)
            visited = (i < self._step_idx)
            color   = CYAN if active else (GREEN if visited else "#1a3a4a")
            size    = 11 if active else 8
            dot = ctk.CTkLabel(self._dot_frame, text="●",
                               font=("Courier", size), text_color=color,
                               cursor="hand2" if i < self._step_idx else "")
            dot.pack(side="left", padx=3)
            # clicking a visited dot goes back to it
            if i < self._step_idx:
                dot.bind("<Button-1>", lambda e, idx=i: self._jump(idx))

    def _clear_content(self):
        for w in self._content.winfo_children():
            w.destroy()
        self._refresh_dots()

    # ── Navigation ────────────────────────────────────────────

    def _show_step(self):
        self._clear_content()
        getattr(self, f"_step_{self.STEPS[self._step_idx]}")()

    def _next(self):
        self._step_idx = min(self._step_idx + 1, len(self.STEPS) - 1)
        self._show_step()

    def _back(self):
        self._step_idx = max(self._step_idx - 1, 0)
        self._show_step()

    def _jump(self, idx):
        self._step_idx = idx
        self._show_step()

    def _skip(self):
        self._next()

    # ── Bottom nav bar helper ─────────────────────────────────

    def _nav_bar(self, parent, on_next, on_skip=None, show_back=True,
                 next_label="Next  →", next_width=120):
        """Renders the bottom nav: [← Back] [Skip →]  [Next →]
        Pass on_skip=None to hide skip button."""
        bot = ctk.CTkFrame(parent, fg_color="transparent")
        bot.pack(side="bottom", fill="x", padx=24, pady=20)

        # Left side: back + skip
        left = ctk.CTkFrame(bot, fg_color="transparent")
        left.pack(side="left")

        if show_back and self._step_idx > 0:
            _back_btn(left, self._back).pack(side="left", padx=(0, 6))

        if on_skip is not None:
            _skip_btn(left, on_skip).pack(side="left")

        # Right side: next
        _btn(bot, next_label, on_next, width=next_width).pack(side="right")

    # ─────────────────────────────────────────────────────────
    #  STEPS
    # ─────────────────────────────────────────────────────────

    def _step_welcome(self):
        f = self._content
        _lbl(f, "◈  HOROWA AI", font=("Courier", 28, "bold"), color=CYAN).pack(pady=(40, 6))
        _lbl(f, "First-run setup wizard", font=("Courier", 13), color=DIM).pack()
        _lbl(f, "This will take about 2 minutes.", font=("Courier", 11), color="#555").pack(pady=(4, 28))

        _lbl(f, "We'll help you:", font=("Courier", 11), color=DIM).pack()
        for item in ["Connect an AI provider (Gemini, ChatGPT, or Claude)",
                     "Select a model",
                     "Set your wake word preference"]:
            _lbl(f, f"  ›  {item}", font=("Courier", 11), color="#5a8a9a").pack(anchor="w", padx=60)

        # Welcome: no back, no skip — just Get Started
        bot = ctk.CTkFrame(f, fg_color="transparent")
        bot.pack(side="bottom", fill="x", padx=24, pady=20)
        _btn(bot, "Get Started  →", self._next, width=180).pack(side="right")

    def _step_provider(self):
        f = self._content
        _lbl(f, "Choose AI Provider", font=("Courier", 18, "bold"), color=CYAN).pack(pady=(28, 4))
        _lbl(f, "Which AI service do you want HOROWA to use?",
             font=("Courier", 11), color=DIM).pack(pady=(0, 18))

        cards = ctk.CTkFrame(f, fg_color="transparent")
        cards.pack(fill="x", padx=30)

        providers = [
            ("gemini",    "Google Gemini",      "Free tier available. Recommended for new users."),
            ("openai",    "OpenAI / ChatGPT",   "GPT-4o and GPT-4o-mini. Requires paid plan."),
            ("anthropic", "Anthropic / Claude", "Claude models. Requires paid plan."),
        ]
        self._provider_var = tk.StringVar(value=self._provider)

        for pid, label, desc in providers:
            color = PROVIDER_COLORS[pid]
            card  = ctk.CTkFrame(cards, fg_color=CARD, corner_radius=12,
                                  border_width=1, border_color=BORDER)
            card.pack(fill="x", pady=4)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=10)
            inner.grid_columnconfigure(1, weight=1)

            rb = ctk.CTkRadioButton(inner, text="", variable=self._provider_var,
                                    value=pid, fg_color=color, border_color=BORDER)
            rb.grid(row=0, column=0, rowspan=2, padx=(0, 12))
            _lbl(inner, label, font=("Courier", 12, "bold"), color=color,
                 anchor="w").grid(row=0, column=1, sticky="ew")
            _lbl(inner, desc, font=("Courier", 10), color=DIM,
                 anchor="w").grid(row=1, column=1, sticky="ew")

            for w in [card, inner] + inner.winfo_children():
                w.bind("<Button-1>", lambda e, p=pid: self._provider_var.set(p))
                try: w.configure(cursor="hand2")
                except: pass

        def _go():
            self._provider = self._provider_var.get()
            self._cfg["online_provider"] = self._provider
            self._next()

        self._nav_bar(f, on_next=_go, on_skip=self._skip)

    def _step_api_key(self):
        f = self._content
        color = PROVIDER_COLORS.get(self._provider, CYAN)
        label = {"gemini": "Google Gemini", "openai": "OpenAI",
                 "anthropic": "Anthropic"}.get(self._provider, self._provider.title())
        hint  = {"gemini": "AIza…", "openai": "sk-…",
                 "anthropic": "sk-ant-…"}.get(self._provider, "")
        links = {
            "gemini":    "aistudio.google.com/apikey",
            "openai":    "platform.openai.com/api-keys",
            "anthropic": "console.anthropic.com/settings/keys",
        }

        _lbl(f, f"{label} API Key", font=("Courier", 18, "bold"), color=color).pack(pady=(28, 4))
        _lbl(f, f"Get your key at: {links.get(self._provider, '')}",
             font=("Courier", 10), color="#3a6a7a").pack()
        _lbl(f, f"Format: {hint}", font=("Courier", 10), color="#444").pack(pady=(2, 18))

        key_frame = ctk.CTkFrame(f, fg_color="transparent")
        key_frame.pack(fill="x", padx=40)
        key_frame.grid_columnconfigure(0, weight=1)

        entry = ctk.CTkEntry(
            key_frame, font=("Courier", 12), fg_color=CARD,
            text_color=CYAN, border_color=BORDER, border_width=1,
            corner_radius=8, show="•",
            placeholder_text=f"Paste {label} API key here…", height=40
        )
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        # Pre-fill if user came back
        saved = self._cfg.get("api_keys", {}).get(self._provider, self._api_key)
        if saved:
            entry.insert(0, saved)

        show_var = tk.BooleanVar(value=False)
        def _toggle():
            show_var.set(not show_var.get())
            entry.configure(show="" if show_var.get() else "•")
        ctk.CTkButton(key_frame, text="👁", width=36, height=40,
                      fg_color=CARD, border_width=1, border_color=BORDER,
                      text_color=DIM, command=_toggle,
                      corner_radius=8).grid(row=0, column=1)

        self._key_status = _lbl(f, "", font=("Courier", 10), color=GREEN)
        self._key_status.pack(pady=(8, 0))

        def _go():
            key = entry.get().strip()
            if not key:
                self._key_status.configure(text="⚠ Please enter an API key.", text_color=RED)
                return
            self._api_key = key
            keys = self._cfg.get("api_keys", {})
            keys[self._provider] = key
            self._cfg["api_keys"] = keys
            # Reset fetched models when key changes
            self._models = []
            self._next()

        self._nav_bar(f, on_next=_go, on_skip=self._skip)

    def _step_model(self):
        f = self._content
        _lbl(f, "Select Model", font=("Courier", 18, "bold"), color=CYAN).pack(pady=(28, 4))
        _lbl(f, "Fetch available models or enter one manually.",
             font=("Courier", 11), color=DIM).pack(pady=(0, 14))

        self._model_var = tk.StringVar(value=self._model or "— fetch models first —")

        mrow = ctk.CTkFrame(f, fg_color="transparent")
        mrow.pack(fill="x", padx=40)
        mrow.grid_columnconfigure(0, weight=1)

        self._model_menu = ctk.CTkOptionMenu(
            mrow, variable=self._model_var,
            values=self._models if self._models else ["— fetch models first —"],
            font=("Courier", 12), fg_color=CARD,
            button_color=BORDER, button_hover_color="#2a5a7a",
            text_color=CYAN, dropdown_fg_color=CARD,
            dropdown_text_color=CYAN, corner_radius=8, height=38,
            command=self._on_model_dropdown_select   # clear manual on select
        )
        self._model_menu.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        _btn(mrow, "⟳ Fetch", self._fetch_models_step,
             width=80, height=38, color=BORDER, text_color=CYAN).grid(row=0, column=1)

        self._fetch_status = _lbl(f, "", font=("Courier", 10), color=DIM)
        self._fetch_status.pack(pady=(6, 0))

        _lbl(f, "Or type model name manually:", font=("Courier", 10),
             color=DIM).pack(anchor="w", padx=40, pady=(10, 2))
        self._manual = ctk.CTkEntry(
            f, font=("Courier", 12), fg_color=CARD, text_color=CYAN,
            border_color=BORDER, border_width=1, corner_radius=8,
            placeholder_text="e.g. gemini-2.5-flash-lite", height=36
        )
        self._manual.pack(fill="x", padx=40)
        self._manual.bind("<Key>", self._on_manual_type)

        def _go():
            manual = self._manual.get().strip()
            # manual box takes priority; else use dropdown
            chosen = manual if manual else self._model_var.get()
            if chosen in ("— fetch models first —", "— fetch models —"):
                chosen = ""
            self._model = chosen
            self._cfg["online_model"] = chosen
            self._next()

        self._nav_bar(f, on_next=_go, on_skip=self._skip)

        # Auto-fetch if we have a key and haven't fetched yet
        if self._api_key and not self._models:
            self.after(300, self._fetch_models_step)
        elif self._models:
            # Re-populate from cache when coming back
            self._model_menu.configure(values=self._models)
            if self._model and self._model in self._models:
                self._model_var.set(self._model)

    def _on_model_dropdown_select(self, value):
        """When user picks from dropdown, clear the manual entry."""
        if hasattr(self, "_manual"):
            self._manual.delete(0, "end")

    def _on_manual_type(self, event=None):
        """When user types in manual box, reset dropdown to placeholder."""
        # Only reset if they're actually typing (not just focusing)
        self.after(10, self._reset_dropdown_if_manual)

    def _reset_dropdown_if_manual(self):
        if hasattr(self, "_manual") and hasattr(self, "_model_var"):
            if self._manual.get().strip():
                # Don't change dropdown — just leave it, manual takes priority on _go
                pass

    def _fetch_models_step(self):
        self._fetch_status.configure(text="⟳ Fetching…", text_color=ORANGE)
        threading.Thread(target=self._do_fetch_step,
                         args=(self._provider, self._api_key), daemon=True).start()

    def _do_fetch_step(self, provider, api_key):
        try:
            if provider == "gemini":
                from google import genai
                c = genai.Client(api_key=api_key)
                models = sorted([
                    m.name.replace("models/", "") for m in c.models.list()
                    if "generateContent" in (getattr(m, "supported_actions", None) or [])
                ])
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
            models = []
            print(f"[WALKTHROUGH FETCH] {e}")
        self.after(0, lambda: self._apply_fetched(models))

    def _apply_fetched(self, models):
        self._models = models
        if not models:
            self._fetch_status.configure(
                text="⚠ Could not fetch. Check API key or type model manually.",
                text_color=RED)
            return
        self._model_menu.configure(values=models)
        first = models[0]
        self._model_var.set(first)
        # Don't fill manual box — leave it empty so dropdown is used
        if hasattr(self, "_manual"):
            self._manual.delete(0, "end")
        self._fetch_status.configure(text=f"✓ {len(models)} models found.", text_color=GREEN)

    def _step_hotword(self):
        f = self._content
        _lbl(f, "Wake Word", font=("Courier", 18, "bold"), color=CYAN).pack(pady=(28, 4))
        _lbl(f, 'Say "Hey Horowa" to wake HOROWA AI by voice.',
             font=("Courier", 11), color=DIM).pack(pady=(0, 6))
        _lbl(f, "Runs in background, always listening for your wake word.",
             font=("Courier", 11), color="#3a6a7a", justify="center").pack(pady=(0, 20))

        hw_frame = ctk.CTkFrame(f, fg_color=CARD, corner_radius=12,
                                 border_width=1, border_color=BORDER)
        hw_frame.pack(fill="x", padx=40, pady=6)
        inner = ctk.CTkFrame(hw_frame, fg_color="transparent")
        inner.pack(padx=20, pady=14)
        _lbl(inner, "👂  Wake Word:", font=("Courier", 12), color=DIM).pack(side="left", padx=(0, 10))
        _lbl(inner, '"Hey Horowa"', font=("Courier", 14, "bold"), color=CYAN).pack(side="left")

        self._hw_var = tk.BooleanVar(value=self._cfg.get("hotword_enabled", True))
        hw_row = ctk.CTkFrame(f, fg_color="transparent")
        hw_row.pack(pady=10)
        ctk.CTkSwitch(hw_row, text=" Enable hotword detection",
                      variable=self._hw_var, button_color=CYAN,
                      progress_color=BORDER, font=("Courier", 11),
                      text_color=DIM).pack()

        def _go():
            self._cfg["hotword_enabled"] = self._hw_var.get()
            self._next()

        self._nav_bar(f, on_next=_go, on_skip=self._skip)

    def _step_done(self):
        f = self._content
        _lbl(f, "✓", font=("Courier", 48, "bold"), color=GREEN).pack(pady=(30, 2))
        _lbl(f, "HOROWA AI is ready.", font=("Courier", 18, "bold"), color=CYAN).pack()
        _lbl(f, "Your settings have been saved.\nChange anything later in Settings ⚙.",
             font=("Courier", 11), color=DIM, justify="center").pack(pady=(10, 0))

        summary = ctk.CTkFrame(f, fg_color=CARD, corner_radius=12,
                                border_width=1, border_color=BORDER)
        summary.pack(fill="x", padx=40, pady=16)
        provider_label = {"gemini": "Google Gemini", "openai": "OpenAI",
                          "anthropic": "Anthropic"}.get(self._provider, self._provider.title())
        for k, v in [
            ("Provider", provider_label),
            ("Model",    self._model or "default"),
            ("Hotword",  "Enabled" if self._cfg.get("hotword_enabled", True) else "Disabled"),
        ]:
            row = ctk.CTkFrame(summary, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=5)
            _lbl(row, f"{k}:", font=("Courier", 11), color=DIM).pack(side="left")
            _lbl(row, v, font=("Courier", 11, "bold"), color=CYAN).pack(side="left", padx=(8, 0))

        # Done screen: back allowed, no skip
        bot = ctk.CTkFrame(f, fg_color="transparent")
        bot.pack(side="bottom", fill="x", padx=24, pady=20)
        _back_btn(bot, self._back).pack(side="left")
        _btn(bot, "Launch HOROWA AI  →", self._finish, width=200).pack(side="right")

    # ── Finish ────────────────────────────────────────────────

    def _finish(self):
        with open(CONFIG_PATH, "w") as f:
            json.dump(self._cfg, f, indent=2)
        self.destroy()


def run_if_first_time():
    """Call from main.py — shows wizard if config.json missing, blocks until done."""
    if os.path.exists(CONFIG_PATH):
        return
    ctk.set_appearance_mode("dark")
    WalkthroughApp().mainloop()


if __name__ == "__main__":
    if os.path.exists(CONFIG_PATH):
        os.rename(CONFIG_PATH, CONFIG_PATH + ".bak")
    ctk.set_appearance_mode("dark")
    WalkthroughApp().mainloop()
