"""
Background monitoring worker.

Design:
- Runs in its own thread so the UI stays responsive.
- Every cycle:
    1) Snapshot the list of stores and IPs from the repository.
    2) Ping each IP multiple times and compute (online via quorum, avg latency_ms).
    3) If status changes, update repo, stamp last_change, and notify UI/OS.
    4) Always emit a per-ping aggregate event so the UI can append to Logs.
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
from .config import PING_COUNT, PING_QUORUM  # NEW: multi-ping behavior


class StoreMonitor:
    def __init__(
        self,
        repo: Repo,
        on_any_change: Callable[[], None],
        notify: Callable[[str, bool], None],
        on_ping: Optional[Callable[[str, str, bool, int | None, int], None]] = None,
    ):
        """
        Design (StoreMonitor.__init__)
        - Purpose: Wire dependencies and prepare a background thread.
        - Inputs:
            repo: shared state repository
            on_any_change: callback to schedule a UI refresh
            notify: callback to fire OS notifications when status flips
            on_ping: optional callback to log each aggregate ping result
        - Side effects: none here (thread not started yet)
        - Thread-safety: N/A (constructor)
        """
        self.repo = repo
        self.on_any_change = on_any_change
        self.notify = notify
        self.on_ping = on_ping
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def start(self) -> None:
        """Start the daemon monitor thread."""
        self._thread.start()

    def stop(self) -> None:
        """Signal the loop to stop (thread will exit after current sleep)."""
        self._stop.set()

    def _loop(self) -> None:
        """
        Design (StoreMonitor._loop)
        - Purpose: Main monitor loop; snapshots stores and probes each IP.
        - Behavior:
            * For each store, send PING_COUNT probes.
            * online = (success_count >= PING_QUORUM)
            * avg_latency = average of successful probes (ms) or None if none succeeded.
            * Emit on_ping aggregate line for logs.
            * Update Repo & notify UI/OS when status flips (or first seen).
        - Thread-safety: interacts with Repo via thread-safe methods; UI calls are scheduled.
        """
        while not self._stop.is_set():
            stores, status, _ = self.repo.snapshot()
            for number, store in stores.items():
                try:
                    # Perform multiple pings and track successes + timings
                    success_count = 0
                    total_ms = 0
                    for _ in range(PING_COUNT):
                        t0 = time.perf_counter()
                        ok = is_online(store.ip)
                        elapsed_ms = int((time.perf_counter() - t0) * 1000)
                        if ok:
                            success_count += 1
                            total_ms += elapsed_ms

                    # Decide final state by quorum; compute average latency if any success
                    online = success_count >= PING_QUORUM
                    avg_latency = int(total_ms / success_count) if success_count > 0 else None

                    # Emit per-store aggregate ping result (for the Logs panel)
                    if self.on_ping is not None:
                        try:
                            self.on_ping(number, store.ip, online, avg_latency, success_count)
                        except Exception:
                            pass

                    # Update status & notify if changed (or first seen)
                    prev = status.get(number)
                    if prev is None:
                        self.repo.set_status(number, online)
                        self.on_any_change()  # first paint to UI
                    elif prev != online:
                        self.repo.set_status(number, online)
                        self.on_any_change()
                        self.notify(number, online)
                except Exception:
                    # One store failure must not kill the monitor thread; continue to next store
                    pass

            time.sleep(PING_INTERVAL_SEC)
