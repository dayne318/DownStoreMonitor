"""
Design (repository.py)
- Purpose: Encapsulate all mutable state behind a tiny API (and a lock), so UI and Monitor
           don't touch global dicts directly. Makes threading safer and future persistence easy.
- Inputs: Store objects and status booleans.
- Outputs: Snapshots (copies) of current stores, statuses, and last-change timestamps.
- Side effects: Updates internal dictionaries; timestamps changes.
- Thread-safety: All mutating methods take the internal lock; snapshot returns copies.
"""

import threading
from datetime import datetime
from typing import Dict, Tuple

from .models import Store


class Repo:
    """
    Design (Repo)
    - State:
        _stores: {store_number -> Store}
        _status: {store_number -> bool} online/offline
        _last_change: {store_number -> str} timestamp when status changed or first seen ONLINE
        _lock: threading.Lock to protect all mutating/reading operations
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stores: Dict[str, Store] = {}
        self._status: Dict[str, bool] = {}
        self._last_change: Dict[str, str] = {}

    # -------- CRUD for stores --------

    def upsert(self, store: Store) -> None:
        """
        Purpose: Insert or update a store by number.
        Inputs: store (Store)
        Outputs: None
        Side effects: Mutates _stores dict.
        Thread-safety: Protected by _lock.
        """
        with self._lock:
            self._stores[store.number] = store

    def get(self, number: str) -> Store | None:
        """
        Purpose: Retrieve a store by number.
        Inputs: number (str)
        Outputs: Store or None
        Thread-safety: Protected by _lock (returns object reference; do not mutate without upsert()).
        """
        with self._lock:
            return self._stores.get(number)

    def remove(self, number: str) -> None:
        """
        Purpose: Remove a store and any status metadata.
        Inputs: number (str)
        Outputs: None
        Side effects: Removes from _stores/_status/_last_change.
        Thread-safety: Protected by _lock.
        """
        with self._lock:
            self._stores.pop(number, None)
            self._status.pop(number, None)
            self._last_change.pop(number, None)

    def clear_all(self) -> None:
        """
        Purpose: Remove all stores and all status metadata.
        Outputs: None
        Side effects: Clears _stores, _status, _last_change.
        Thread-safety: Protected by _lock.
        """
        with self._lock:
            self._stores.clear()
            self._status.clear()
            self._last_change.clear()

    # -------- Status handling --------

    def set_status(self, number: str, online: bool) -> None:
        """
        Purpose: Update online/offline status and stamp last_change if needed.
        Inputs: number (str), online (bool)
        Outputs: None
        Side effects: Mutates _status and possibly _last_change.
        Thread-safety: Protected by _lock.
        """
        with self._lock:
            prev = self._status.get(number)
            self._status[number] = online
            if prev is not None and prev != online:
                self._last_change[number] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # -------- Snapshots for safe reading --------

    def snapshot(self) -> Tuple[Dict[str, Store], Dict[str, bool], Dict[str, str]]:
        """
        Purpose: Return copies of stores/status/last_change for safe iteration.
        Outputs: (stores_copy, status_copy, last_change_copy)
        Thread-safety: Protected by _lock; returns copies to avoid mutation races.
        """
        with self._lock:
            return dict(self._stores), dict(self._status), dict(self._last_change)
