"""
Background monitoring worker.

Design:
- Runs in its own thread so the UI stays responsive.
- Every cycle:
    1) Snapshot the list of stores and IPs from the repository.
    2) Ping all IPs concurrently (asyncio + ThreadPoolExecutor).
    3) If status changes, update repo, stamp last_change, and notify UI/OS.
    4) Always emit a per-ping aggregate event so the UI can append to Logs.
- Methods:
    start(): begin the daemon thread
    stop(): signal the thread to stop (not used here but handy)
- Thread-safety: Repo does its own locking; UI calls are posted back to main thread.
"""

import asyncio
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from .repository import Repo
from .utils import ping_with_stats
from .store_ip_list import get_ip_for_store
from .config import PING_INTERVAL_SEC
from .config import PING_COUNT

# Max threads for concurrent pings (cap to avoid spawning hundreds)
PING_EXECUTOR_MAX_WORKERS = 50


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
        - Purpose: Main monitor loop; snapshots stores and probes all IPs concurrently.
        - Behavior: Each cycle runs pings in parallel via asyncio + ThreadPoolExecutor,
          then processes results in fixed order and updates repo / UI / logs.
        - Thread-safety: interacts with Repo via thread-safe methods; UI calls are scheduled.
        """
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        executor = ThreadPoolExecutor(max_workers=PING_EXECUTOR_MAX_WORKERS)
        try:
            while not self._stop.is_set():
                loop.run_until_complete(self._run_cycle(loop, executor))
                time.sleep(PING_INTERVAL_SEC)
        finally:
            executor.shutdown(wait=True)
            loop.close()

    async def _run_cycle(self, loop: asyncio.AbstractEventLoop, executor: ThreadPoolExecutor) -> None:
        """One cycle: snapshot stores, ping all concurrently, then process results in order."""
        stores, status, _ = self.repo.snapshot()
        # Build ordered list: (number, store, effective_ip, display_ip)
        ordered: list[tuple[str, object, str, str]] = []
        for number, store in stores.items():
            effective_ip = (store.ip or "").strip() or get_ip_for_store(store.number)
            display_ip = effective_ip if effective_ip else "—"
            ordered.append((number, store, effective_ip or "", display_ip))

        # Submit tasks for stores that have an IP
        tasks: list[tuple[int, asyncio.Future]] = []
        for i, (number, store, effective_ip, display_ip) in enumerate(ordered):
            if effective_ip:
                fut = loop.run_in_executor(
                    executor,
                    ping_with_stats,
                    effective_ip,
                    PING_COUNT,
                )
                tasks.append((i, fut))

        # Gather all ping results (same order as tasks)
        if tasks:
            indices, futures = zip(*tasks)
            results_list = await asyncio.gather(*futures, return_exceptions=True)
            result_by_index = dict(zip(indices, results_list))
        else:
            result_by_index = {}

        # Build result per ordered index (no-IP stores get (False, None, 0))
        for i, (number, store, effective_ip, display_ip) in enumerate(ordered):
            try:
                if i in result_by_index:
                    res = result_by_index[i]
                    if isinstance(res, BaseException):
                        online, avg_latency, success_count = False, None, 0
                    else:
                        online, avg_latency, success_count = res
                else:
                    online, avg_latency, success_count = False, None, 0

                if self.on_ping is not None:
                    try:
                        self.on_ping(number, display_ip, online, avg_latency, success_count)
                    except Exception:
                        pass

                prev = status.get(number)
                if prev is None:
                    self.repo.set_status(number, online)
                    self.on_any_change()
                elif prev != online:
                    self.repo.set_status(number, online)
                    self.on_any_change()
                    self.notify(number, online)
            except Exception:
                pass
