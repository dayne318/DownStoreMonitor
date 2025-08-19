"""
Design (models.py)
- Purpose: Define simple, typed data structures for domain entities (Store).
- Inputs: Field values (str).
- Outputs: Dataclass instances.
- Side effects: None.
- Thread-safety: Dataclasses are plain containers; Repo protects concurrent access.
"""

from dataclasses import dataclass


@dataclass
class Store:
    """
    Design (Store)
    - Purpose: Represents a single store entry in the monitor.
    - Fields:
        number: 4-digit store number (string, zero-padded).
        ip: IP address to ping.
        isp: Optional ISP name (string).
        helpdesk_ticket: Optional helpdesk ticket (raw value; UI will render HD- prefix).
    """
    number: str
    ip: str
    isp: str = ""
    helpdesk_ticket: str = ""
