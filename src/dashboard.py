"""StreamPilot Dashboard - a small always-visible reassurance window.

Replaces "glance at the terminal spam" with a sleek status window for the
second monitor: a big OK/ISSUE/OFFLINE badge, a live-pulsing heartbeat dot
that proves the dashboard itself is alive, and the same fields the terminal
heartbeat shows. Reads data/logs/status.json on a timer - zero coupling to
the daemon process, stdlib only (tkinter), no new dependencies.
"""

import os
import time
import tkinter as tk

import status_file

STATUS_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'logs', 'status.json')
POLL_MS = 500          # how often the dashboard re-reads status.json
PULSE_PERIOD_MS = 1000  # one full heartbeat pulse cycle

BG = "#12151a"
PANEL = "#1a1e26"
TEXT = "#c9d1d9"
TEXT_DIM = "#6b7280"
GREEN = "#3fd67a"
AMBER = "#f5a623"
RED = "#ff5d5d"
GREY = "#4b5563"

STATUS_COLORS = {"OK": GREEN, "IDLE": TEXT_DIM, "ISSUE": RED}


class Dashboard:
    def __init__(self, root: tk.Tk, status_path: str = STATUS_PATH):
        self.root = root
        self.status_path = status_path
        self._pulse_t0 = time.time()

        root.title("StreamPilot")
        root.configure(bg=BG)
        root.geometry("360x260")
        root.attributes("-topmost", True)
        root.resizable(True, True)

        self.canvas = tk.Canvas(root, width=44, height=44, bg=BG, highlightthickness=0)
        self.canvas.pack(pady=(18, 4))
        self._dot = self.canvas.create_oval(12, 12, 32, 32, fill=GREY, outline="")

        self.badge = tk.Label(root, text="OFFLINE", font=("Segoe UI", 20, "bold"), fg=GREY, bg=BG)
        self.badge.pack(pady=(0, 12))

        panel = tk.Frame(root, bg=PANEL)
        panel.pack(fill="x", padx=16, pady=(0, 10))

        self.rows = {}
        for key, label in (("game", "Game"), ("category", "Category"), ("sabnzbd", "SABnzbd")):
            row = tk.Frame(panel, bg=PANEL)
            row.pack(fill="x", padx=12, pady=6)
            tk.Label(row, text=label, font=("Segoe UI", 10), fg=TEXT_DIM, bg=PANEL, width=9, anchor="w").pack(side="left")
            val = tk.Label(row, text="-", font=("Segoe UI", 10, "bold"), fg=TEXT, bg=PANEL, anchor="w")
            val.pack(side="left", fill="x", expand=True)
            self.rows[key] = val

        self.footer = tk.Label(root, text="waiting for daemon...", font=("Segoe UI", 8), fg=TEXT_DIM, bg=BG)
        self.footer.pack(side="bottom", pady=8)

        self._tick()
        self._pulse()

    # -- polling: re-read status.json --------------------------------------
    def _tick(self):
        status = status_file.read_status(self.status_path)
        self._render(status)
        self.root.after(POLL_MS, self._tick)

    def _render(self, status):
        if status_file.is_stale(status):
            self.badge.config(text="OFFLINE", fg=GREY)
            self.footer.config(text="No signal from daemon - is it running?")
            for v in self.rows.values():
                v.config(text="-")
            return

        state = status.get("status", "IDLE")
        color = STATUS_COLORS.get(state, AMBER)
        self.badge.config(text=state, fg=color)

        self.rows["game"].config(text=status.get("game") or "Idle")
        self.rows["category"].config(text=status.get("category") or "Unknown")
        self.rows["sabnzbd"].config(text=status.get("sabnzbd") or "-")

        age = max(0, int(time.time() - status.get("timestamp", time.time())))
        self.footer.config(text=f"updated {age}s ago  |  polling every {status.get('poll_interval', '?')}s")

    # -- animation: continuous pulse proves the WINDOW is alive -------------
    def _pulse(self):
        phase = ((time.time() - self._pulse_t0) * 1000 % PULSE_PERIOD_MS) / PULSE_PERIOD_MS
        # triangle wave 0->1->0 across the cycle, drives radius 10-16px
        scale = 1 - abs(phase - 0.5) * 2
        r = 10 + scale * 6
        cx, cy = 22, 22
        self.canvas.coords(self._dot, cx - r, cy - r, cx + r, cy + r)

        status = status_file.read_status(self.status_path)
        dot_color = GREY
        if status and not status_file.is_stale(status):
            dot_color = STATUS_COLORS.get(status.get("status", "IDLE"), AMBER)
        self.canvas.itemconfig(self._dot, fill=dot_color)

        self.root.after(33, self._pulse)  # ~30fps, cheap


def run():
    root = tk.Tk()
    Dashboard(root)
    root.mainloop()


if __name__ == "__main__":
    run()
