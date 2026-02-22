"""
Design (utils.py)
- Purpose: Reusable helpers: icon path detection (PyInstaller), ping wrapper, ticket formatting,
           and hit-testing for the helpdesk icon area.
- Inputs: Various helper parameters (ip, click coords, etc.).
- Outputs: Helper results (bools, strings, paths).
- Side effects: is_online runs a subprocess (ping).
- Thread-safety: Stateless; safe to call from any thread.
"""

import os
import sys
import subprocess
import re

from .config import PING_TIMEOUT_MS, PING_QUORUM


def get_icon_path(filename: str) -> str:
    """
    Purpose: Resolve icon path for both dev (script) and PyInstaller (frozen) runs.
    Inputs: filename (e.g., "logo.ico")
    Outputs: Absolute/relative path usable with Tk.iconbitmap.
    Side Effects: None.
    Thread-safety: Safe.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, filename)  # type: ignore[attr-defined]
    # In development, icon is expected at app/icons/logo.ico relative to project root
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "icons", filename)


def is_online(ip: str) -> bool:
    """
    Purpose: Ping the given IP once to determine online/offline.
    Inputs: ip (str)
    Outputs: True if reachable (Windows ping shows 'TTL='), else False.
    Side Effects: Spawns a 'ping' subprocess with timeout to avoid blocking.
    Thread-safety: Safe; no shared state.
    """
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        timeout_sec = PING_TIMEOUT_MS / 1000.0
        result = subprocess.run(
            ["ping", "-n", "1", ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            text=True,
            timeout=timeout_sec,
        )
        return "TTL=" in (result.stdout or "")
    except (subprocess.TimeoutExpired, OSError, ValueError, Exception):
        return False


def ping_with_stats(ip: str, count: int) -> tuple[bool, int | None, int]:
    """
    Purpose: Run ping -n count and parse Windows output for online, average RTT, and success count.
    Inputs: ip (str), count (int) number of echo requests.
    Outputs: (online, avg_latency_ms, success_count). online = success_count >= PING_QUORUM;
             avg_latency_ms from "Average = Xms" when success_count > 0, else None.
    Side Effects: Spawns a ping subprocess.
    Thread-safety: Safe; no shared state.
    """
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        timeout_sec = (PING_TIMEOUT_MS / 1000.0) * count
        result = subprocess.run(
            ["ping", "-n", str(count), ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            text=True,
            timeout=timeout_sec,
        )
        stdout = result.stdout or ""
        # Received = N from "Packets: Sent = 4, Received = 4, Lost = 0"
        received_m = re.search(r"Received\s*=\s*(\d+)", stdout)
        success_count = int(received_m.group(1)) if received_m else 0
        online = success_count >= PING_QUORUM
        avg_latency_ms: int | None = None
        if success_count > 0:
            avg_m = re.search(r"Average\s*=\s*(\d+)ms", stdout)
            if avg_m:
                avg_latency_ms = int(avg_m.group(1))
        return (online, avg_latency_ms, success_count)
    except (subprocess.TimeoutExpired, OSError, ValueError, Exception):
        return (False, None, 0)


def format_ticket(raw: str) -> str:
    """
    Purpose: Normalize a helpdesk ticket to always start with 'HD-'.
    Inputs: raw (possibly empty or already prefixed).
    Outputs: Normalized ticket ('' if empty).
    Side Effects: None.
    Thread-safety: Safe.
    """
    if not raw:
        return ""
    raw = raw.strip()
    if not raw:
        return ""
    return raw if raw.startswith("HD-") else f"HD-{raw}"


def make_helpdesk_url(ticket: str, prefix: str) -> str:
    """
    Purpose: Construct a browsable helpdesk URL from a normalized ticket.
    Inputs: ticket (must already be normalized to HD-xxxx), prefix base URL.
    Outputs: Full URL as string.
    Side Effects: None.
    Thread-safety: Safe.
    """
    return f"{prefix}{ticket}"


def ticket_icon_hit(cell_bbox: tuple[int, int, int, int] | None, click_x: int) -> bool:
    """
    Purpose: Detect if a click is within the left-most ~20px of a Treeview cell (where we draw '↗').
    Inputs: cell_bbox = (x, y, width, height) from tree.bbox(...), click_x = event.x
    Outputs: True if inside the icon area; else False.
    Side Effects: None.
    Thread-safety: Safe.
    """
    if not cell_bbox:
        return False
    x1, _, _, _ = cell_bbox
    return (click_x - x1) <= 20
