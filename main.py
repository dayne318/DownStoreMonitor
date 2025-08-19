import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import time
from datetime import datetime
from plyer import notification
import os
import webbrowser
import sys

store_data = {}
ISP_OPTIONS = ["", "Granite", "GlobalGig", "GTT", "Comcast", "CradlePoint: Verizon", "CradlePoint: ATT", "CradlePoint: T-Mobile"]

status_dict = {}
last_change_dict = {}
lock = threading.Lock()
sort_state = {"column": None, "order": None}

HELPDESK_URL_PREFIX = "https://lidshelp.atlassian.net/jira/servicedesk/projects/HD/queues/custom/20/"

def is_online(ip):
    try:
        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(["ping", "-n", "1", ip],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                creationflags=creationflags,
                                text=True)
        return "TTL=" in result.stdout
    except Exception:
        return False

class StoreMonitorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Store Connection Monitor")
        if getattr(sys, 'frozen', False):
            icon_path = os.path.join(sys._MEIPASS, 'logo.ico')
        else:
            icon_path = 'logo.ico'
        self.root.iconbitmap(icon_path)

        self.enable_notifications = tk.BooleanVar(value=True)
        self.show_notes = tk.BooleanVar(value=False)

        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        self.root.configure(bg="#1e1e1e")

        style = ttk.Style(self.root)
        style.theme_use("default")
        style.configure("Treeview",
                        background="#2b2b2b",
                        foreground="#f0f0f0",
                        fieldbackground="#2b2b2b",
                        rowheight=24,
                        font=("Segoe UI", 10))
        style.configure("Treeview.Heading",
                        background="#1e1e1e",
                        foreground="#ffffff",
                        font=("Segoe UI", 10, "bold"))
        style.map("Treeview",
                  background=[('selected', '#444')],
                  foreground=[])

        columns = ("store", "ip", "status", "last_change", "isp", "helpdesk_ticket")
        self.tree = ttk.Treeview(root, columns=columns, show="headings")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 5))

        self.tree.tag_configure("green", foreground="#7CFC00")
        self.tree.tag_configure("red", foreground="#FF6A6A")

        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Button-1>", self.on_single_click)

        headers = {
            "store": "Store #", "ip": "IP Address", "status": "Status",
            "last_change": "Last Changed", "isp": "ISP", "helpdesk_ticket": "Help Desk Ticket"
        }
        for col in columns:
            self.tree.heading(col, text=headers[col], command=lambda c=col: self.sort_by_column(c))

        self.notes_box = tk.Text(root, height=5, bg="#2b2b2b", fg="white")
        self.notes_box.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 5))
        self.notes_box.grid_remove()  # Hidden by default

        button_frame = tk.Frame(root, bg="#1e1e1e")
        button_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        ttk.Button(button_frame, text="Add Store", command=self.add_store).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Remove Store", command=self.remove_store).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Edit Store", command=self.edit_store).pack(side=tk.LEFT, padx=5)

        tk.Checkbutton(button_frame, text="Enable Notifications", variable=self.enable_notifications,
                       fg="white", bg="#1e1e1e", selectcolor="#2b2b2b",
                       activebackground="#1e1e1e", activeforeground="white").pack(side=tk.LEFT, padx=5)

        tk.Checkbutton(button_frame, text="Show Notes", variable=self.show_notes,
                       fg="white", bg="#1e1e1e", selectcolor="#2b2b2b",
                       command=self.toggle_notes).pack(side=tk.LEFT, padx=5)

        self.update_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.update_thread.start()
        self.refresh_ui()

    def toggle_notes(self):
        if self.show_notes.get():
            self.notes_box.grid()
        else:
            self.notes_box.grid_remove()

    def refresh_ui(self):
        with lock:
            entries = []
            for store, data in store_data.items():
                ip = data["ip"]
                online = status_dict.get(store, False)
                status = "ONLINE" if online else "OFFLINE"
                last_change = last_change_dict.get(store, "")
                isp = data.get("isp", "")
                ticket_number = data.get("helpdesk_ticket", "")
                if ticket_number and not ticket_number.startswith("HD-"):
                    ticket_number = f"HD-{ticket_number}"
                entries.append((store, ip, status, last_change, isp, ticket_number, online))

            col, order = sort_state["column"], sort_state["order"]
            if col:
                idx = {"store": 0, "ip": 1, "status": 2, "last_change": 3, "isp": 4, "helpdesk_ticket": 5}[col]
                reverse = (order == "desc")
                if col == "status":
                    entries.sort(key=lambda x: not x[6], reverse=reverse)
                else:
                    entries.sort(key=lambda x: x[idx], reverse=reverse)

            self.tree.delete(*self.tree.get_children())
            for store, ip, status, last_change, isp, ticket_number, online in entries:
                color = "green" if online else "red"
                # ICON FIRST + ticket number; empty if no ticket
                ticket_display = f"↗ {ticket_number}" if ticket_number else ""
                self.tree.insert("", "end", values=(store, ip, status, last_change, isp, ticket_display), tags=(color,))

    def on_single_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region != "cell":
            return

        row_id = self.tree.identify_row(event.y)
        col_id = self.tree.identify_column(event.x)
        if not row_id or not col_id:
            return

        col_index = int(col_id[1:]) - 1

        # Help Desk Ticket column
        if col_index == 5:
            bbox = self.tree.bbox(row_id, col_id)  # (x, y, width, height)
            if not bbox:
                return
            x1, y1, width, height = bbox

            # Only clicks in the first ~20px (the icon area) should open the link
            if event.x - x1 <= 20:
                item = self.tree.item(row_id)
                store = str(item["values"][0]).zfill(4)
                raw_ticket = store_data.get(store, {}).get("helpdesk_ticket", "").strip()
                if raw_ticket:
                    if not raw_ticket.startswith("HD-"):
                        raw_ticket = f"HD-{raw_ticket}"
                    webbrowser.open(f"{HELPDESK_URL_PREFIX}{raw_ticket}")

    def on_double_click(self, event):
        pass  # Notes field moved outside table

    def sort_by_column(self, col):
        order = "asc"
        if sort_state["column"] == col and sort_state["order"] == "asc":
            order = "desc"
        elif sort_state["column"] == col and sort_state["order"] == "desc":
            col, order = None, None
        sort_state["column"] = col
        sort_state["order"] = order
        self.refresh_ui()

    def monitor_loop(self):
        while True:
            with lock:
                for store, data in store_data.items():
                    ip = data["ip"]
                    current_status = is_online(ip)
                    previous_status = status_dict.get(store, None)
                    if previous_status is None:
                        status_dict[store] = current_status
                        if current_status:
                            last_change_dict[store] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    elif previous_status != current_status:
                        status_dict[store] = current_status
                        last_change_dict[store] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        if self.enable_notifications.get():
                            status = "ONLINE" if current_status else "OFFLINE"
                            notification.notify(
                                title="Store Status Change",
                                message=f"Store {store} status is now: {status}",
                                timeout=5
                            )
            self.root.after(0, self.refresh_ui)
            time.sleep(30)

    def add_store(self):
        popup = tk.Toplevel(self.root)
        popup.title("Add Store")
        popup.configure(bg="#1e1e1e")

        tk.Label(popup, text="Store #", fg="white", bg="#1e1e1e").grid(row=0, column=0, sticky="e", padx=5, pady=5)
        store_entry = tk.Entry(popup)
        store_entry.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(popup, text="IP Address", fg="white", bg="#1e1e1e").grid(row=1, column=0, sticky="e", padx=5, pady=5)
        ip_entry = tk.Entry(popup)
        ip_entry.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(popup, text="ISP", fg="white", bg="#1e1e1e").grid(row=2, column=0, sticky="e", padx=5, pady=5)
        isp_var = tk.StringVar()
        isp_dropdown = ttk.Combobox(popup, textvariable=isp_var, values=ISP_OPTIONS)
        isp_dropdown.grid(row=2, column=1, padx=5, pady=5)

        tk.Label(popup, text="Help Desk Ticket", fg="white", bg="#1e1e1e").grid(row=3, column=0, sticky="e", padx=5, pady=5)
        ticket_entry = tk.Entry(popup)
        ticket_entry.grid(row=3, column=1, padx=5, pady=5)

        def finish_add():
            store = store_entry.get().zfill(4)
            ip = ip_entry.get()
            ticket = ticket_entry.get().strip()
            if not store or not ip:
                return
            if ticket and not ticket.startswith("HD-"):
                ticket = f"HD-{ticket}"
            with lock:
                store_data[store] = {
                    "ip": ip,
                    "isp": isp_var.get(),
                    "helpdesk_ticket": ticket
                }
            popup.destroy()
            self.refresh_ui()

        ttk.Button(popup, text="Save", command=finish_add).grid(row=4, column=0, columnspan=2, pady=10)

    def remove_store(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Remove Store", "Select a store to remove.")
            return
        store = self.tree.item(selected[0])["values"][0]
        with lock:
            store_data.pop(store, None)
            status_dict.pop(store, None)
            last_change_dict.pop(store, None)
        self.refresh_ui()

    def edit_store(self):
        # This would mirror add_store but prepopulate and allow editing. Same form layout.
        pass

if __name__ == "__main__":
    root = tk.Tk()
    app = StoreMonitorApp(root)
    root.mainloop()
