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
    Side Effects: Spawns a 'ping' subprocess.
    Thread-safety: Safe; no shared state.
    """
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        # Windows ping (-n 1); if needed, handle other OS with different flags
        result = subprocess.run(
            ["ping", "-n", "1", ip],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=creationflags,
            text=True,
        )
        return "TTL=" in result.stdout
    except Exception:
        return False


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
