"""
Background monitoring worker.

Design:
- Runs in its own thread so the UI stays responsive.
- Every cycle:
    1) Snapshot the list of stores and IPs from the repository.
    2) Ping each IP once and compute (online, latency_ms).
    3) If status changes, update repo, stamp last_change, and notify UI/OS.
    4) Always emit a per-ping event so the UI can append to Logs.
 - Methods:
    start(): begin the daemon thread
    stop(): signal the thread to stop (not used here but handy)
- Thread-safety: Repo does its own locking; UI calls are posted back to main thread.
"""

import threading
import time
from typing import Callable, Optional

from .repository import Repo
from .utils import is_online
from .config import PING_INTERVAL_SEC


class StoreMonitor:
    def __init__(self, repo: Repo, on_any_change: Callable[[], None], notify: Callable[[str, bool], None], on_ping: Optional[Callable[[str, str, bool, int | None], None]] = None):
        self.repo = repo
        self.on_any_change = on_any_change
        self.notify = notify
        self.on_ping = on_ping
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            stores, status, _ = self.repo.snapshot()
            for number, store in stores.items():
                t0 = time.perf_counter()
                online = is_online(store.ip)
                elapsed_ms = int((time.perf_counter() - t0) * 1000)

                # emit a per-ping event for logs (does not affect UI sorting)
                if self.on_ping is not None:
                    try:
                        self.on_ping(number, store.ip, online, elapsed_ms)
                    except Exception:
                        pass

                prev = status.get(number)
                if prev is None:
                    self.repo.set_status(number, online)
                    self.on_any_change()
                elif prev != online:
                    self.repo.set_status(number, online)
                    # Schedule a UI refresh and fire a notification
                    self.on_any_change()
                    self.notify(number, online)
            time.sleep(PING_INTERVAL_SEC)
