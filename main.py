import threading
from GUI import HorowaGUI
from core import HorowaCore
from walkthrough import run_if_first_time


def main():
    # First-run wizard — blocks until config.json is written
    run_if_first_time()
    _stream_started = False

    def stream_partial(text, final=False):
        nonlocal _stream_started
        if not _stream_started:
            app.after(0, lambda: app._console_write("[HOROWA]: "))
            _stream_started = True
        app.after(0, lambda t=text: app._console_write(t))
        if final:
            app.after(0, lambda: app._console_write("\n"))
            _stream_started = False

    def confirm_command(command, reason):
        import customtkinter as ctk
        result = [False]
        dialog = ctk.CTkToplevel(app)
        dialog.title("HOROWA AI — Command Approval")
        dialog.geometry("500x220")
        dialog.configure(fg_color="#080d14")
        dialog.attributes("-alpha", 0.96)
        dialog.attributes("-topmost", True)
        dialog.grab_set()

        ctk.CTkLabel(dialog, text="HOROWA wants to run a command:",
                     font=("Courier", 13, "bold"), text_color="#ffaa00").pack(pady=(18, 4))
        ctk.CTkLabel(dialog, text=f"  {command}",
                     font=("Courier", 12), text_color="#00fbff",
                     fg_color="#0d1a24", corner_radius=6).pack(fill="x", padx=20, pady=4)
        ctk.CTkLabel(dialog, text=f"Reason: {reason}",
                     font=("Courier", 11), text_color="#888").pack(pady=4)

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=12)

        def approve(): result[0] = True;  dialog.destroy()
        def deny():    result[0] = False; dialog.destroy()

        ctk.CTkButton(btn_frame, text="APPROVE", width=120,
                      fg_color="#00fbff", text_color="#000d11",
                      font=("Courier", 12, "bold"), command=approve).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="DENY", width=120,
                      fg_color="transparent", border_width=1,
                      border_color="#ff4444", text_color="#ff4444",
                      font=("Courier", 12, "bold"), command=deny).pack(side="left", padx=10)

        dialog.wait_window()
        return result[0]

    def handle_input_pipeline(query, sender="USER"):
        if not query.strip(): return

        clean = query.lower()
        if "switch to online"  in clean: app.update_status("ONLINE")
        elif "switch to offline" in clean: app.update_status("OFFLINE")

        app.log_msg(query, sender)
        app.show_thinking(True)
        app.set_sphere_active(True, 0.4)

        def process():
            nonlocal _stream_started
            _stream_started = False
            response = core.process_command(query, speaker_on=app.speaker_on)
            app.after(0, lambda: finish(response))

        def finish(response):
            app.show_thinking(False)
            if response is None: return

            if core._streaming_completed:
                core._streaming_completed = False
                app.after(0, lambda: app._console_write("\n"))
                return

            app.log_msg(response, "HOROWA AI")
            if app.speaker_on:
                core.add_to_speech(response)

        threading.Thread(target=process, daemon=True).start()

    def on_hotword_detected():
        app.after(0, _wake_from_hotword)

    def _wake_from_hotword():
        app.set_sphere_active(True, 0.8)
        msg = "Online. How can I help?"
        app.log_msg(msg, "HOROWA AI")
        app.log_msg("Hotword detected — HOROWA activated.", "SYSTEM")
        if app.speaker_on: core.add_to_speech(msg)
        app.after(1500, lambda: app.set_sphere_active(False))

    def on_amplitude(active, amp=0.0):
        app.set_sphere_active(active, amp)

    def toggle_mic():
        app.mic_on = not app.mic_on
        core.mic_active = app.mic_on
        state = "ON" if app.mic_on else "OFF"
        app.mic_btn.configure(
            text=f"MIC: {state}",
            fg_color="#00fbff" if app.mic_on else "#1a1a1a",
            text_color="#000d11" if app.mic_on else "#555"
        )
        if app.mic_on: core.start_mic()

    def toggle_speaker():
        app.speaker_on = not app.speaker_on
        state = "ON" if app.speaker_on else "OFF"
        app.spk_btn.configure(
            text=f"SPEAKER: {state}",
            fg_color="#00fbff" if app.speaker_on else "#1a1a1a",
            text_color="#000d11" if app.speaker_on else "#555"
        )

    def toggle_mode():
        current = app.get_mode()
        cfg     = core._read_config()
        pname   = cfg.get("online_provider", "gemini")
        model   = cfg.get("online_model", "")
        if current == "OFFLINE":
            app.update_status("ONLINE")
            core.mode = "ONLINE"
            msg = f"Neural link established. {pname.title()} / {model or 'default'} active."
        else:
            app.update_status("OFFLINE")
            core.mode = "OFFLINE"
            offline = core.offline_model or "not set"
            msg = f"Satellite link severed. Offline model: {offline}."
        app.log_msg(msg, "SYSTEM")
        if app.speaker_on: core.add_to_speech(msg)

    def toggle_hotword():
        app.hotword_on = not app.hotword_on
        core.hotword_active = app.hotword_on
        app.update_hotword_ui(app.hotword_on)
        state = "enabled" if app.hotword_on else "disabled"
        app.log_msg(f"Hotword detection {state}.", "SYSTEM")

    def minimize_window():
        app.after(0, app.minimize_to_sphere)

    app = HorowaGUI(
        handle_input_pipeline, toggle_mic,
        toggle_speaker, toggle_mode, toggle_hotword
    )

    core = HorowaCore(
        handle_input_pipeline,
        amplitude_callback=on_amplitude,
        hotword_callback=on_hotword_detected,
        stream_callback=stream_partial,
        confirm_callback=confirm_command,
        minimize_callback=minimize_window
    )

    # Give GUI a reference to core so API overlay can hot-reload provider
    app._core_ref = core

    app.log_msg("HOROWA AI Booting...", "SYSTEM")
    app.log_msg("Active. Say 'Hey Horowa' then your command.", "SYSTEM")
    app.update_status("OFFLINE")
    app.set_sleeping_ui(False)

    core.start_mic()
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
