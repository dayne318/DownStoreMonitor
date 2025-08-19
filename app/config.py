"""
Design (config.py)
- Purpose: Centralize constants and configuration.
- Inputs: None.
- Outputs: Constants (lists, URLs, intervals, icon file name).
- Side effects: None.
- Thread-safety: N/A (read-only constants).
"""

# NEW: maximum number of log lines kept in the Logs panel (oldest trimmed)
LOG_MAX_LINES = 1000

ISP_OPTIONS = [
    "", "Granite", "GlobalGig", "GTT", "Comcast",
    "CradlePoint: Verizon", "CradlePoint: ATT", "CradlePoint: T-Mobile"
]

HELPDESK_URL_PREFIX = "https://lidshelp.atlassian.net/jira/servicedesk/projects/HD/queues/custom/20/"

PING_INTERVAL_SEC = 30

ICON_FILE = "logo.ico"  # Expected at app/icons/logo.ico (added to the exe with --add-data)
