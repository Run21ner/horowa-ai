import tkinter as tk
import customtkinter as ctk
import math


class MiniSphere(tk.Toplevel):
    """
    Standalone borderless mini window shown when LEO minimizes.
    Positioned bottom-left, 220x260, sphere + 3 toggle buttons.
    Click sphere → restore callback fires.
    """

    def __init__(self, master, mic_on, speaker_on, hotword_on,
                 cb_mic, cb_spk, cb_hotword, restore_callback):
        super().__init__(master)

        self._restore_callback = restore_callback
        self._sphere_amplitude  = 0.0
        self._sphere_target     = 0.0
        self._wave_offset       = 0.0
        self._breath            = 0.0
        self._breath_dir        = 1
        self._blob_points       = 120

        # ── window chrome ──────────────────────────────────
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg="#000f15")

        screen_h = self.winfo_screenheight()
        self.geometry(f"220x260+0+{screen_h - 300}")
        self.update_idletasks()

        # ── outer frame ────────────────────────────────────
        frame = ctk.CTkFrame(
            self, fg_color="#000f15", corner_radius=20,
            border_width=1, border_color="#00fbff"
        )
        frame.pack(fill="both", expand=True, padx=4, pady=4)
        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # ── sphere canvas ──────────────────────────────────
        self.canvas = tk.Canvas(
            frame, bg="#000f15", highlightthickness=0,
            width=180, height=180
        )
        self.canvas.grid(row=0, column=0, padx=8, pady=(8, 4), sticky="nsew")
        self.canvas.bind("<Button-1>", lambda e: self._restore_callback())

        # ── button row ─────────────────────────────────────
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.grid(row=1, column=0, pady=(0, 8))

        rb = dict(width=36, height=36, corner_radius=18,
                  font=("Courier", 10, "bold"), border_width=1)

        self.mic_btn = ctk.CTkButton(
            btn_row, text="MIC",
            fg_color="#00fbff" if mic_on else "#1a1a1a",
            text_color="#000d11" if mic_on else "#555",
            border_color="#00fbff",
            command=cb_mic, **rb
        )
        self.mic_btn.pack(side="left", padx=4)

        self.spk_btn = ctk.CTkButton(
            btn_row, text="SPK",
            fg_color="#00fbff" if speaker_on else "#1a1a1a",
            text_color="#000d11" if speaker_on else "#555",
            border_color="#00fbff",
            command=cb_spk, **rb
        )
        self.spk_btn.pack(side="left", padx=4)

        self.hw_btn = ctk.CTkButton(
            btn_row, text="HW",
            fg_color="#00ffaa" if hotword_on else "#1a1a1a",
            text_color="#000d11" if hotword_on else "#555",
            border_color="#00ffaa",
            command=cb_hotword, **rb
        )
        self.hw_btn.pack(side="left", padx=4)

        self._animate()

    # ── public ─────────────────────────────────────────────

    def set_active(self, active, amplitude=0.0):
        self._sphere_target = max(0.0, min(1.0, amplitude)) if active else 0.0

    # ── animation ──────────────────────────────────────────

    def _animate(self):
        self._sphere_amplitude += (self._sphere_target - self._sphere_amplitude) * 0.12
        if self._sphere_target == 0.0:
            self._sphere_target *= 0.88
        self._wave_offset += 0.06
        self._breath += 0.02 * self._breath_dir
        if self._breath >= 1.0:
            self._breath_dir = -1
        elif self._breath <= 0.0:
            self._breath_dir = 1
        self._draw()
        self.after(30, self._animate)

    def _draw(self):
        c  = self.canvas
        c.delete("all")
        w  = c.winfo_width()
        h  = c.winfo_height()
        if w < 10 or h < 10:
            return

        cx, cy = w / 2, h / 2
        base_r = min(w, h) * 0.26
        amp    = self._sphere_amplitude
        bs     = 1.0 + self._breath * 0.04 if amp < 0.05 else 1.0

        if amp > 0.05:
            for gm, gc in [(1.6, "#1a0830"), (1.35, "#2d0f55")]:
                gr = base_r * gm * bs
                c.create_oval(cx-gr, cy-gr, cx+gr, cy+gr, fill=gc, outline="")

        layers = [
            {"color": "#bf5fff", "phase": 0,           "freq": 3, "scale": 1.10},
            {"color": "#7b6fff", "phase": math.pi/2,   "freq": 4, "scale": 1.02},
            {"color": "#5b8fff", "phase": math.pi/1.5, "freq": 4, "scale": 0.97},
            {"color": "#ff6eb4", "phase": math.pi/3,   "freq": 5, "scale": 0.90},
        ]
        for layer in layers:
            pts = []
            n   = self._blob_points
            ls  = layer["scale"] * bs
            for i in range(n):
                angle  = 2 * math.pi * i / n
                wobble = (
                    amp * base_r * 0.42 * math.sin(layer["freq"] * angle + self._wave_offset + layer["phase"]) +
                    amp * base_r * 0.20 * math.sin((layer["freq"]+2) * angle - self._wave_offset*1.4 + layer["phase"]) +
                    amp * base_r * 0.10 * math.sin((layer["freq"]+4) * angle + self._wave_offset*0.7)
                )
                r = base_r * ls + wobble
                pts.extend([cx + r*math.cos(angle), cy + r*math.sin(angle)])
            if len(pts) >= 4:
                c.create_polygon(pts, fill=layer["color"], outline="", smooth=True)

        core_r = base_r*0.22*bs + amp*base_r*0.12
        glow_r = core_r * 2.4
        mid_r  = core_r * 1.5
        c.create_oval(cx-glow_r, cy-glow_r, cx+glow_r, cy+glow_r, fill="#2a0a4a", outline="")
        c.create_oval(cx-mid_r,  cy-mid_r,  cx+mid_r,  cy+mid_r,  fill="#7030c0", outline="")
        c.create_oval(cx-core_r, cy-core_r, cx+core_r, cy+core_r, fill="#e8b4ff", outline="")

        ring_r = base_r * (1.25 if amp > 0.1 else 0.88) * bs
        color  = "#bf5fff" if amp > 0.1 else "#003344"
        width  = 1
        c.create_oval(cx-ring_r, cy-ring_r, cx+ring_r, cy+ring_r,
                      outline=color, width=width)
        if amp <= 0.1:
            for i in range(12):
                a  = 2*math.pi*i/12 + self._wave_offset*0.25
                tl = 8 if i % 3 == 0 else 4
                x1 = cx + ring_r*math.cos(a)
                y1 = cy + ring_r*math.sin(a)
                x2 = cx + (ring_r+tl)*math.cos(a)
                y2 = cy + (ring_r+tl)*math.sin(a)
                c.create_line(x1, y1, x2, y2,
                              fill="#00fbff" if i%3==0 else "#005566", width=1)
