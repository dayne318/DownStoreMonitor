"""
Design (storage.py)
- Purpose: Load and save the store list to/from disk (JSON).
- Inputs: Path (from get_stores_path()), list of Store for save.
- Outputs: list[Store] on load; None on save.
- Side effects: Reads/writes file. On load failure returns empty list; on save failure ignores.
- Thread-safety: Call from main thread only (e.g. after repo mutations).
"""

import json
import os
import sys
from pathlib import Path
from typing import List

from .config import STORES_FILENAME
from .models import Store


def get_stores_path() -> Path:
    """
    Resolve path for stores.json. Prefer app data dir so it works when installed
    (e.g. Program Files) and survives reinstalls. Fallback to dir next to executable.
    """
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            base = Path(appdata) / "Down Store Monitor"
            try:
                base.mkdir(parents=True, exist_ok=True)
                return base / STORES_FILENAME
            except OSError:
                pass
    # Fallback: next to executable (or cwd when running as script)
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent.parent
    return base / STORES_FILENAME


def load_stores(path: Path) -> List[Store]:
    """
    Load stores from JSON file. Returns empty list on missing file or parse error.
    """
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    stores: List[Store] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            stores.append(
                Store(
                    number=str(item.get("number", "")),
                    ip=str(item.get("ip", "")),
                    isp=str(item.get("isp", "")),
                    helpdesk_ticket=str(item.get("helpdesk_ticket", "")),
                )
            )
        except (TypeError, ValueError):
            continue
    return stores


def save_stores(stores: List[Store], path: Path) -> None:
    """
    Save store list to JSON file. Ignores IOError (e.g. read-only location).
    """
    data = [
        {
            "number": s.number,
            "ip": s.ip,
            "isp": s.isp,
            "helpdesk_ticket": s.helpdesk_ticket,
        }
        for s in stores
    ]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass
