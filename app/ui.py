"""
Design (ui.py)
- Purpose: Build and manage the Tkinter UI (Treeview, dialogs, sorting, clicks).
- Inputs: Repo (shared state).
- Outputs: None (renders UI, writes to Repo).
- Side effects: Creates windows; opens web browser for helpdesk links.
- Thread-safety: UI code runs on main thread; background monitor calls schedule_refresh to update safely.
"""

import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
from datetime import datetime
from typing import Callable

from .repository import Repo
from .models import Store
from .config import ISP_OPTIONS, HELPDESK_URL_PREFIX, ICON_FILE, LOG_MAX_LINES, PING_COUNT
from .utils import (
    get_icon_path,
    format_ticket,
    make_helpdesk_url,
    ticket_icon_hit,
)
from .store_ip_list import get_ip_for_store


class AppUI:
    """
    Design (AppUI)
    - Purpose: Encapsulate all UI creation and behavior.
    - Public attributes:
        enable_notifications (tk.BooleanVar): toggles system notifications
        show_notes (tk.BooleanVar): toggles visibility of the notes box (global notes area)
        show_logs (tk.BooleanVar): toggles visibility of the logs panel (ping events)
    - Public methods:
        schedule_refresh(): thread-safe way to refresh Treeview from monitor thread
        on_ping(): thread-safe adapter to append one (aggregate) ping line into Logs
    """

    def __init__(self, root: tk.Tk, repo: Repo, save_callback: Callable[[], None]):
        self.root = root
        self.repo = repo
        self.save_callback = save_callback

        # UI state variables
        self.enable_notifications = tk.BooleanVar(value=True)
        self.show_notes = tk.BooleanVar(value=False)
        self.show_logs = tk.BooleanVar(value=False)
        self.sort_state = {"column": None, "order": None}

        # Window
        self.root.title("Store Connection Monitor")
        self.root.iconbitmap(get_icon_path(ICON_FILE))
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        self.root.configure(bg="#1e1e1e")

        # Paned window: top = content (tree, buttons), bottom = notes OR logs (when shown)
        self.paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        self.paned.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        content_frame = tk.Frame(self.paned, bg="#1e1e1e")
        content_frame.rowconfigure(0, weight=1)
        content_frame.columnconfigure(0, weight=1)
        self.paned.add(content_frame, weight=1)

        # Bottom pane: always in paned window; resize with pane() to show/hide (weight=0/minsize=0 when hidden)
        self.bottom_frame = tk.Frame(self.paned, bg="#1e1e1e")
        self.notes_box = tk.Text(self.bottom_frame, height=5, bg="#2b2b2b", fg="white")
        self.notes_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))
        self.notes_box.pack_forget()  # hidden by default
        self.logs_box = tk.Text(self.bottom_frame, height=6, bg="#1b1b1b", fg="#dddddd", wrap="none")
        self.logs_box.configure(state="disabled")
        self.logs_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 6))
        self.logs_box.pack_forget()  # hidden by default
        self.paned.add(self.bottom_frame, weight=0)  # start collapsed; expand when Notes/Logs checked

        def _keep_sash_collapsed(_event=None):
            """When both Notes and Logs are unchecked, keep sash at bottom so window can resize down."""
            if not self.show_notes.get() and not self.show_logs.get():
                self.paned.update_idletasks()
                total = self.paned.winfo_height()
                if total > 0:
                    self.paned.sashpos(0, total)

        self.paned.bind("<Configure>", _keep_sash_collapsed)

        # Style
        style = ttk.Style(self.root)
        style.theme_use("default")
        style.configure(
            "Treeview",
            background="#2b2b2b",
            foreground="#f0f0f0",
            fieldbackground="#2b2b2b",
            rowheight=24,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Treeview.Heading",
            background="#1e1e1e",
            foreground="#ffffff",
            font=("Segoe UI", 10, "bold"),
        )
        style.map("Treeview", background=[('selected', '#444')], foreground=[])

        # Treeview
        self.columns = ("store", "ip", "status", "last_change", "isp", "helpdesk_ticket")
        self.tree = ttk.Treeview(content_frame, columns=self.columns, show="headings")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 5))

        self.tree.tag_configure("green", foreground="#7CFC00")
        self.tree.tag_configure("red", foreground="#FF6A6A")
        self.tree.tag_configure("orange", foreground="#FFA500")  # degraded (partial success)

        # Cache of last probe success count: {store_number -> int(0..4)}
        self._last_probe_success: dict[str, int] = {}

        headers = {
            "store": "Store #",
            "ip": "IP Address",
            "status": "Status",
            "last_change": "Last Changed",
            "isp": "ISP",
            "helpdesk_ticket": "Help Desk Ticket",
        }
        for col in self.columns:
            self.tree.heading(col, text=headers[col], command=lambda c=col: self.sort_by_column(c))

        # Bindings
        self.tree.bind("<Button-1>", self.on_single_click)
        self.tree.bind("<Double-1>", self.on_double_click)  # Currently unused (notes moved out)

        # Buttons & toggles (content_frame: tree row 0, buttons row 4 only)
        button_frame = tk.Frame(content_frame, bg="#1e1e1e")
        button_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))

        ttk.Button(button_frame, text="Add Store", command=self.add_store).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Remove Store", command=self.remove_store).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Edit Store", command=self.edit_store).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Delete All", command=self.delete_all).pack(side=tk.LEFT, padx=5)

        tk.Checkbutton(
            button_frame,
            text="Enable Notifications",
            variable=self.enable_notifications,
            fg="white",
            bg="#1e1e1e",
            selectcolor="#2b2b2b",
            activebackground="#1e1e1e",
            activeforeground="white",
        ).pack(side=tk.LEFT, padx=5)

        tk.Checkbutton(
            button_frame,
            text="Show Notes",
            variable=self.show_notes,
            fg="white",
            bg="#1e1e1e",
            selectcolor="#2b2b2b",
            command=self.toggle_notes,
        ).pack(side=tk.LEFT, padx=5)

        # Show Logs toggle
        tk.Checkbutton(
            button_frame,
            text="Show Logs",
            variable=self.show_logs,
            fg="white",
            bg="#1e1e1e",
            selectcolor="#2b2b2b",
            command=self.toggle_logs,
        ).pack(side=tk.LEFT, padx=5)

        # Initial paint
        self.refresh_ui()

    # ---------- Public API for monitor ----------

    def schedule_refresh(self) -> None:
        """
        Purpose: Allow the background monitor to request a UI update safely.
        Side effects: Schedules refresh_ui on the main thread via Tk.after().
        Thread-safety: Safe to call from any thread.
        """
        self.root.after(0, self.refresh_ui)

    # ---------- per-ping hook (called from monitor thread) --------
    def on_ping(self, number: str, ip: str, online: bool, latency_ms: int | None, success_count: int) -> None:
        """
        Purpose: Append an aggregate ping result to the Logs panel and remember success count.
        Inputs:
            number: store number
            ip: probed IP
            online: final state after quorum
            latency_ms: average of successful probes (None if no success)
            success_count: number of successful probes (e.g., 0..4)
        Thread-safety: Reschedules append on main thread.
        """
        # remember last success count for coloring in refresh_ui
        self._last_probe_success[number] = success_count

        status = "ONLINE" if online else "OFFLINE"
        latency = f"{latency_ms} ms" if latency_ms is not None else "timeout"
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{stamp}] {str(number).zfill(4)} ping {ip} -> {status} ({success_count}/{PING_COUNT} ok, {latency})\n"
        self.root.after(0, lambda: self._append_log(line))

    # ---------- UI callbacks & utilities ----------

    def toggle_notes(self) -> None:
        """Show notes in bottom pane; mutually exclusive with logs. Resize pane to show/hide."""
        if self.show_notes.get():
            self.show_logs.set(False)
            self.paned.pane(self.bottom_frame, weight=1)
            self.logs_box.pack_forget()
            self.notes_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 5))
            self.paned.update_idletasks()
            total = self.paned.winfo_height()
            pos = int(total * 0.8) if total > 0 else None
            if total > 0:
                self.paned.sashpos(0, pos)
        else:
            self.notes_box.pack_forget()
            if not self.show_logs.get():
                self.paned.pane(self.bottom_frame, weight=0)
                self.paned.update_idletasks()
                total = self.paned.winfo_height()
                if total > 0:
                    self.paned.sashpos(0, total)

    def toggle_logs(self) -> None:
        """Show logs in bottom pane; mutually exclusive with notes. Resize pane to show/hide."""
        if self.show_logs.get():
            self.show_notes.set(False)
            self.paned.pane(self.bottom_frame, weight=1)
            self.notes_box.pack_forget()
            self.logs_box.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 6))
            self.paned.update_idletasks()
            total = self.paned.winfo_height()
            pos = int(total * 0.8) if total > 0 else None
            if total > 0:
                self.paned.sashpos(0, pos)
        else:
            self.logs_box.pack_forget()
            if not self.show_notes.get():
                self.paned.pane(self.bottom_frame, weight=0)
                self.paned.update_idletasks()
                total = self.paned.winfo_height()
                if total > 0:
                    self.paned.sashpos(0, total)

    def refresh_ui(self) -> None:
        """
        Purpose: Rebuild the Tree rows from the repository snapshot and apply sorting.
        Side effects: Mutates Treeview items (UI only).
        Thread-safety: Must run on main thread (use schedule_refresh from other threads).
        """
        stores, status, last_change = self.repo.snapshot()

        # Build display entries: (store, ip, status, last_change, isp, ticket, online)
        entries = []
        for number, store in stores.items():
            online = status.get(number, False)
            st = "ONLINE" if online else "OFFLINE"
            lc = last_change.get(number, "")
            ticket_normalized = format_ticket(store.helpdesk_ticket)
            effective_ip = (store.ip or "").strip() or get_ip_for_store(store.number) or "—"
            entries.append((number, effective_ip, st, lc, store.isp, ticket_normalized, online))

        # Sorting
        col, order = self.sort_state["column"], self.sort_state["order"]
        if col:
            idx_map = {c: i for i, c in enumerate(self.columns)}
            idx = idx_map[col]
            reverse = (order == "desc")
            if col == "status":
                # status sorts by online flag (entries[-1])
                entries.sort(key=lambda x: not x[-1], reverse=reverse)
            else:
                entries.sort(key=lambda x: x[idx], reverse=reverse)

        # Repaint
        self.tree.delete(*self.tree.get_children())
        for (number, ip, st, lc, isp, ticket, online) in entries:
            # Determine color:
            #   red = offline (0/4)
            #   orange = degraded (1-3/4)
            #   green = healthy (4/4)
            if not online:
                color = "red"
            else:
                sc = self._last_probe_success.get(number, 4)
                if sc == 4:
                    color = "green"
                elif 1 <= sc < 4:
                    color = "orange"
                else:
                    color = "green"

            # render icon at the front if ticket present
            ticket_display = f"↗ {ticket}" if ticket else ""
            self.tree.insert("", "end", values=(number, ip, st, lc, isp, ticket_display), tags=(color,))

    def on_single_click(self, event) -> None:
        """
        Purpose: Handle single clicks, including the helpdesk icon-only click.
        Inputs: Tk event (provides x/y for hit-testing).
        Side effects: May open web browser if icon area is clicked.
        Thread-safety: UI thread only.
        """
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if not row_id or not col_id:
            return

        col_index = int(col_id[1:]) - 1
        helpdesk_idx = self.columns.index("helpdesk_ticket")
        if col_index != helpdesk_idx:
            return

        # Hit test for icon area (~first 20px)
        bbox = self.tree.bbox(row_id, col_id)
        if not ticket_icon_hit(bbox, event.x):
            return

        # Open URL if ticket exists
        item = self.tree.item(row_id)
        number = str(item["values"][0]).zfill(4)
        store = self.repo.get(number)
        if not store:
            return
        ticket = format_ticket(store.helpdesk_ticket)
        if not ticket:
            return
        webbrowser.open(make_helpdesk_url(ticket, HELPDESK_URL_PREFIX))

    def on_double_click(self, event) -> None:
        """Currently unused (notes moved outside the table)."""
        pass

    def sort_by_column(self, col: str) -> None:
        """
        Purpose: Toggle header sort order and refresh.
        Inputs: col (column key from self.columns).
        """
        order = "asc"
        if self.sort_state["column"] == col and self.sort_state["order"] == "asc":
            order = "desc"
        elif self.sort_state["column"] == col and self.sort_state["order"] == "desc":
            col, order = None, None  # reset sort
        self.sort_state["column"] = col
        self.sort_state["order"] = order
        self.refresh_ui()

    # ---------- internal helper for Logs ----------

    def _append_log(self, text: str) -> None:
        """
        Purpose: Append one line to the Logs panel and trim to LOG_MAX_LINES.
        Thread-safety: Main thread only (called via after()).
        """
        self.logs_box.configure(state="normal")
        self.logs_box.insert("end", text)
        self.logs_box.see("end")
        # Trim oldest lines if exceeding cap
        try:
            total_lines = int(self.logs_box.index("end-1c").split(".")[0])
            if total_lines > LOG_MAX_LINES:
                remove = total_lines - LOG_MAX_LINES
                self.logs_box.delete("1.0", f"{remove + 1}.0")
        except Exception:
            pass
        self.logs_box.configure(state="disabled")

    # ---------- CRUD dialogs ----------

    def add_store(self) -> None:
        """
        Purpose: Open a small dialog to add a new store (Store #, IP, ISP, Help Desk Ticket).
        Side effects: Mutates Repo on save.
        """

        win = tk.Toplevel(self.root)
        win.title("Add Store")
        win.configure(bg="#1e1e1e")

        # Fields
        tk.Label(win, text="Store #", fg="white", bg="#1e1e1e").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        e_store = tk.Entry(win)
        e_store.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(win, text="IP Address (optional)", fg="white", bg="#1e1e1e").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        e_ip = tk.Entry(win)
        e_ip.grid(row=1, column=1, padx=5, pady=5)
        tk.Label(win, text="Leave blank to use IP from list.", fg="gray", bg="#1e1e1e", font=("Segoe UI", 8)).grid(row=1, column=2, sticky="w", padx=(0, 5))

        tk.Label(win, text="ISP", fg="white", bg="#1e1e1e").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        v_isp = tk.StringVar()
        cb_isp = ttk.Combobox(win, textvariable=v_isp, values=ISP_OPTIONS)
        cb_isp.grid(row=2, column=1, padx=5, pady=5)

        tk.Label(win, text="Help Desk Ticket", fg="white", bg="#1e1e1e").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        e_ticket = tk.Entry(win)
        e_ticket.grid(row=3, column=1, padx=5, pady=5)

        def save():
            number = (e_store.get() or "").strip().zfill(4)
            ip = (e_ip.get() or "").strip()
            isp = v_isp.get()
            ticket = format_ticket((e_ticket.get() or "").strip())
            if not number:
                return
            if not ip:
                if get_ip_for_store(number) is None:
                    messagebox.showerror("Add Store", "Error: Store does not have an ip saved please fill out the IP field")
                    return
            self.repo.upsert(Store(number=number, ip=ip, isp=isp, helpdesk_ticket=ticket))
            win.destroy()
            self.refresh_ui()
            self.save_callback()

        ttk.Button(win, text="Save", command=save).grid(row=4, column=0, columnspan=2, pady=10)

    def remove_store(self) -> None:
        """
        Purpose: Remove the selected store (single-select).
        Side effects: Mutates Repo.
        """
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Remove Store", "Select a store to remove.")
            return
        number = str(self.tree.item(selected[0])["values"][0]).zfill(4)
        self.repo.remove(number)
        self.refresh_ui()
        self.save_callback()

    def delete_all(self) -> None:
        """
        Purpose: Remove all stores after user confirmation.
        Side effects: Mutates Repo; calls save_callback so persisted file is updated.
        """
        if not messagebox.askyesno("Delete All", "Remove all stores from the list? This cannot be undone."):
            return
        self.repo.clear_all()
        self.refresh_ui()
        self.save_callback()

    def edit_store(self) -> None:
        """
        Purpose: Open a dialog to edit the selected store's IP/ISP/Help Desk Ticket.
                 The store number is locked (non-editable).
        Side effects: Mutates Repo on save.
        """
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Edit Store", "Select a store to edit.")
            return

        number = str(self.tree.item(selected[0])["values"][0]).zfill(4)
        store = self.repo.get(number)
        if not store:
            messagebox.showerror("Edit Store", "Store not found in repository.")
            return

        win = tk.Toplevel(self.root)
        win.title(f"Edit Store {number}")
        win.configure(bg="#1e1e1e")

        # Store # (disabled)
        tk.Label(win, text="Store #", fg="white", bg="#1e1e1e").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        e_store = tk.Entry(win)
        e_store.insert(0, number)
        e_store.config(state="disabled")
        e_store.grid(row=0, column=1, padx=5, pady=5)

        # IP Address (optional)
        tk.Label(win, text="IP Address (optional)", fg="white", bg="#1e1e1e").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        e_ip = tk.Entry(win)
        e_ip.insert(0, store.ip)
        e_ip.grid(row=1, column=1, padx=5, pady=5)

        # ISP
        tk.Label(win, text="ISP", fg="white", bg="#1e1e1e").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        v_isp = tk.StringVar(value=store.isp)
        cb_isp = ttk.Combobox(win, textvariable=v_isp, values=ISP_OPTIONS)
        cb_isp.grid(row=2, column=1, padx=5, pady=5)

        # Help Desk Ticket
        tk.Label(win, text="Help Desk Ticket", fg="white", bg="#1e1e1e").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        e_ticket = tk.Entry(win)
        e_ticket.insert(0, store.helpdesk_ticket)
        e_ticket.grid(row=3, column=1, padx=5, pady=5)

        def save():
            ip = (e_ip.get() or "").strip()
            isp = v_isp.get()
            ticket = format_ticket((e_ticket.get() or "").strip())
            if not ip and get_ip_for_store(number) is None:
                messagebox.showerror("Edit Store", "Error: Store does not have an ip saved please fill out the IP field")
                return
            self.repo.upsert(Store(number=number, ip=ip, isp=isp, helpdesk_ticket=ticket))
            win.destroy()
            self.refresh_ui()
            self.save_callback()

        ttk.Button(win, text="Save", command=save).grid(row=4, column=0, columnspan=2, pady=10)
