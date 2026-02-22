"""
Design (store_ip_list.py)
- Purpose: Load Store_IP_List.csv at startup and provide lookup by store number.
- Inputs: None at import; load_store_ip_list() uses path from storage + config.
- Outputs: get_ip_for_store(number) -> str | None.
- Side effects: load_store_ip_list() reads CSV once and populates module-level dict.
- Thread-safety: Dict is read-only after load; safe to call get_ip_for_store from any thread.
"""

import csv
from pathlib import Path

from .config import STORE_IP_LIST_FILENAME
from .storage import get_stores_path

# Populated by load_store_ip_list(); key = store ID normalized to 4 digits, value = IP string
_store_ip_map: dict[str, str] = {}


def load_store_ip_list() -> None:
    """
    Read Store_IP_List.csv and build the in-memory dict. Call once at startup.
    Uses same base directory as get_stores_path(); falls back to app dir if file not there.
    """
    global _store_ip_map
    _store_ip_map = {}
    base = get_stores_path().parent
    path = base / STORE_IP_LIST_FILENAME
    if not path.exists():
        # When running from source, CSV may live in app/
        app_dir = Path(__file__).resolve().parent
        alt = app_dir / STORE_IP_LIST_FILENAME
        path = alt if alt.exists() else path
    if not path.exists():
        return
    try:
        with open(path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                store_id = (row.get("Store ID") or "").strip()
                ip = (row.get("IP Address") or "").strip()
                if store_id and ip:
                    key = store_id.zfill(4)
                    _store_ip_map[key] = ip
    except (OSError, csv.Error):
        _store_ip_map = {}


def get_ip_for_store(number: str) -> str | None:
    """
    Return IP for the store number from the loaded CSV dict, or None if not found.
    number is normalized to 4-digit zero-padded for lookup.
    """
    if not number:
        return None
    key = str(number).strip().zfill(4)
    return _store_ip_map.get(key)
