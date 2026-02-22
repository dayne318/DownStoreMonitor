"""
Design (main.py)
- Purpose: Entrypoint that wires together the UI (Tkinter), repository (shared state),
           and background monitor (pings). Starts the Tk main loop.
- Inputs: None (reads config/icons via utils/config and loads UI).
- Outputs: None (UI application window).
- Side Effects: Spawns a background thread for pings; may show system notifications.
- Thread-safety: The Repo class internally manages a lock; UI updates are scheduled via root.after().
"""

import tkinter as tk
from plyer import notification

from app.ui import AppUI
from app.repository import Repo
from app.monitor import StoreMonitor
from app.storage import get_stores_path, load_stores, save_stores


def make_notifier(ui: AppUI):
    """
    Design
    - Purpose: Build a notification function the monitor can call on changes.
    - Inputs: ui (AppUI) to check if notifications are enabled.
    - Outputs: A function(number: str, online: bool) -> None that fires a notification if allowed.
    - Side effects: Triggers a native OS notification via plyer.
    - Thread-safety: Called from monitor thread; plyer is okay; no UI state mutated directly.
    """
    def _notify(number: str, online: bool):
        if not ui.enable_notifications.get():
            return
        status = "ONLINE" if online else "OFFLINE"
        notification.notify(
            title="Store Status Change",
            message=f"Store {number} status is now: {status}",
            timeout=5
        )
    return _notify


if __name__ == "__main__":
    root = tk.Tk()

    # Shared state
    repo = Repo()
    stores_path = get_stores_path()
    for store in load_stores(stores_path):
        repo.upsert(store)

    def save_callback():
        save_stores(list(repo.snapshot()[0].values()), stores_path)

    # UI
    ui = AppUI(root, repo, save_callback)

    def on_close():
        save_callback()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)

    # Monitor (background ping thread)
    monitor = StoreMonitor(
        repo=repo,
        on_any_change=ui.schedule_refresh,   # schedules a safe UI refresh on the main thread
        notify=make_notifier(ui),             # conditionally fires a system notification
        on_ping=ui.on_ping                   # per-ping logging callback (UI appends to Logs panel)
    )
    monitor.start()

    root.mainloop()
