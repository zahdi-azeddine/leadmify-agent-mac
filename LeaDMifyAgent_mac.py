import threading, subprocess, sys, os, json, time, signal
import tkinter as tk
from tkinter import messagebox
import urllib.request

# --- Config ---
API_BASE_URL = "https://api.leadmify.com"
GECKO_HINT = "GeckoDriver not found. Install with Homebrew: brew install geckodriver"

# Use the engine that you already have
# It exposes: IBotAutomation(token=...).monitor_campaigns() and treats 401 as invalid token.
from ibot_hub import IBotAutomation, TokenExpiredException, safe_print  # noqa: F401

class AgentApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LeaDMify Agent")
        self.geometry("640x280")
        self.configure(bg="#0B0F14")
        self.resizable(False, False)

        try:
            # macOS titlebar dark appearance hint (no crash if not supported)
            self.tk.call("tk::unsupported::MacWindowStyle", "style", self._w, "help", "noActivates")
        except Exception:
            pass

        self.proc_thread = None
        self.stop_flag = threading.Event()

        # UI
        self._build_ui()

    def _build_ui(self):
        pad = 18

        title = tk.Label(self, text="Welcome to LeaDMify Automation",
                         font=("SF Pro Display", 18, "bold"),
                         bg="#0B0F14", fg="#E6EDF3")
        title.pack(pady=(20, 10))

        subtitle = tk.Label(self, text="Enter your authentication token to start the engine.",
                            font=("SF Pro Text", 12),
                            bg="#0B0F14", fg="#9BA7B4")
        subtitle.pack()

        self.entry = tk.Entry(self, width=72, relief="flat", bd=0, fg="#E6EDF3", bg="#151B23",
                              insertbackground="#E6EDF3", font=("SF Mono", 12))
        self.entry.pack(pady=(20, 6), ipady=10)

        info = tk.Label(self, text="Note: find the TOKEN in your account settings on leaDMify.com",
                        font=("SF Pro Text", 10), bg="#0B0F14", fg="#64707D")
        info.pack(pady=(0, 10))

        # Buttons
        btn_frame = tk.Frame(self, bg="#0B0F14")
        btn_frame.pack(pady=(0, pad))

        self.connect_btn = tk.Button(
            btn_frame, text="Connect & Run",
            command=self.on_connect, bg="#22C55E", activebackground="#22C55E",
            fg="white", relief="flat", bd=0, padx=22, pady=10, font=("SF Pro Text", 12, "bold"))
        self.connect_btn.grid(row=0, column=0, padx=10)

        self.stop_btn = tk.Button(
            btn_frame, text="Stop",
            command=self.on_stop, bg="#374151", activebackground="#374151",
            fg="white", relief="flat", bd=0, padx=22, pady=10, font=("SF Pro Text", 12))
        self.stop_btn.grid(row=0, column=1, padx=10)
        self.stop_btn.configure(state="disabled")

        self.status = tk.Label(self, text="Idle", font=("SF Pro Text", 12),
                               bg="#0B0F14", fg="#93C5FD")
        self.status.pack()

    def validate_token(self, token: str) -> (bool, str):
        """Ping an endpoint with Bearer token; 200=valid, 401=invalid."""
        try:
            req = urllib.request.Request(
                API_BASE_URL + "/api/campaigns",
                method="GET",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                code = resp.getcode()
                if 200 <= code < 300:
                    return True, "OK"
                return False, f"HTTP {code}"
        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "Invalid or expired token"
            return False, f"HTTP {e.code}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    def _engine_loop(self, token: str):
        """Run your monitoring loop until stop_flag is set."""
        try:
            automation = IBotAutomation(token=token)
            self._set_status("Running…")
            automation.monitor_campaigns()  # blocking loop
        except TokenExpiredException:
            self._set_status("Invalid token")
            messagebox.showerror("LeaDMify Agent", "Token expired/invalid. Please try again.")
        except Exception as e:
            self._set_status("Error")
            messagebox.showerror("LeaDMify Agent", f"Engine error: {e}")
        finally:
            self._set_status("Stopped")
            self._toggle_running(False)

    def on_connect(self):
        token = (self.entry.get() or "").strip()
        if not token:
            messagebox.showwarning("LeaDMify Agent", "Please paste your TOKEN.")
            return

        # Validate token first
        self._set_status("Validating TOKEN…")
        self.connect_btn.configure(state="disabled")
        self.update_idletasks()

        ok, msg = self.validate_token(token)
        if not ok:
            self.connect_btn.configure(state="normal")
            self._set_status("Idle")
            messagebox.showerror("LeaDMify Agent", f"TOKEN invalid: {msg}")
            return

        # Optional: verify geckodriver presence (used by the engine)
        if not self._has_geckodriver():
            messagebox.showwarning("LeaDMify Agent", GECKO_HINT)

        # Start the engine in a thread
        self._toggle_running(True)
        self.proc_thread = threading.Thread(target=self._engine_loop, args=(token,), daemon=True)
        self.proc_thread.start()

    def on_stop(self):
        # Engine monitors KeyboardInterrupt / flags internally; safest is to exit the app
        self._toggle_running(False)
        self._set_status("Stopping…")
        # Best-effort clean exit
        os._exit(0)

    def _toggle_running(self, running: bool):
        self.connect_btn.configure(state="disabled" if running else "normal")
        self.stop_btn.configure(state="normal" if running else "disabled")
        self.entry.configure(state="disabled" if running else "normal")

    def _set_status(self, text: str):
        self.status.configure(text=text)
        self.status.update_idletasks()

    def _has_geckodriver(self) -> bool:
        # Common macOS install location after "brew install geckodriver"
        candidates = ["/usr/local/bin/geckodriver", "/opt/homebrew/bin/geckodriver", "/usr/bin/geckodriver"]
        return any(os.path.exists(p) for p in candidates)

if __name__ == "__main__":
    app = AgentApp()
    app.mainloop()