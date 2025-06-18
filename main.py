import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import subprocess
import threading
import time
from datetime import datetime
from plyer import notification
import os
import sys

store_list = {
    "1234": "192.168.1.10",
    "5678": "192.168.1.11",
}
status_dict = {}
last_change_dict = {}
lock = threading.Lock()
sort_state = {"column": None, "order": None}  # Tracks current sort state


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
        self.enable_notifications = tk.BooleanVar(value=True)

        # Window grid config
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)

        # Dark theme setup
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

        # Treeview
        self.tree = ttk.Treeview(root, columns=("store", "ip", "status", "last_change"), show="headings")
        self.tree.heading("store", text="Store #")
        self.tree.heading("ip", text="IP Address")
        self.tree.heading("status", text="Status")
        self.tree.heading("last_change", text="Last Change")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=10, pady=(10, 5))

        # Button frame at bottom
        button_frame = tk.Frame(root, bg="#1e1e1e")
        button_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))

        ttk.Button(button_frame, text="Add Store", command=self.add_store).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Remove Store", command=self.remove_store).pack(side=tk.LEFT, padx=5)
        tk.Checkbutton(button_frame, text="Enable Notifications", variable=self.enable_notifications,
                       fg="white", bg="#1e1e1e", selectcolor="#2b2b2b",
                       activebackground="#1e1e1e", activeforeground="white").pack(side=tk.LEFT, padx=5)

        # Tag styles
        self.tree.tag_configure("green", foreground="#7CFC00")
        self.tree.tag_configure("red", foreground="#FF6A6A")

        # Start monitor thread
        self.update_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.update_thread.start()

        self.refresh_ui()
        # Enable sortable column headers
        for col in ("store", "ip", "status", "last_change"):
            self.tree.heading(col, text=self.tree.heading(col)["text"], command=lambda c=col: self.sort_by_column(c))


    def refresh_ui(self):
        with lock:
            store_data = []
            for store, ip in store_list.items():
                online = status_dict.get(store, False)
                status = "ONLINE" if online else "OFFLINE"
                last_change = last_change_dict.get(store, "")
                store_data.append((store, ip, status, last_change, online))

            # Apply sorting
            col, order = sort_state["column"], sort_state["order"]
            if col:
                idx = {"store": 0, "ip": 1, "status": 2, "last_change": 3}[col]
                reverse = (order == "desc")
                if col == "status":
                    store_data.sort(key=lambda x: not x[4], reverse=reverse)  # sort by online boolean
                else:
                    store_data.sort(key=lambda x: x[idx], reverse=reverse)

            # Update header arrows
            for column in ("store", "ip", "status", "last_change"):
                arrow = ""
                if column == col:
                    arrow = " ▲" if order == "asc" else " ▼"
                titles = {"store": "Store #", "ip": "IP Address", "status": "Status", "last_change": "Last Changed"}
                self.tree.heading(column, text=titles.get(column, column.title()) + arrow)

            self.tree.delete(*self.tree.get_children())
            for store, ip, status, last_change, online in store_data:
                color = "green" if online else "red"
                self.tree.insert("", "end", values=(store, ip, status, last_change), tags=(color,))


    def monitor_loop(self):
        while True:
            with lock:
                store_items = list(store_list.items())
            for store, ip in store_items:
                current_status = is_online(ip)
                with lock:
                    previous_status = status_dict.get(store, None)
                    if previous_status is None:
                        status_dict[store] = current_status
                        last_change_dict[store] = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if current_status else ""
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
        store = simpledialog.askstring("Add Store", "Enter store number:", parent=self.root)
        if not store:
            return
        ip = simpledialog.askstring("Add Store", "Enter IP address for store:", parent=self.root)
        if store and ip:
            online = is_online(ip)
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S") if online else ""
            with lock:
                store_list[store] = ip
                status_dict[store] = online
                last_change_dict[store] = now
            self.refresh_ui()

    def remove_store(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showinfo("Remove Store", "Select a store to remove.")
            return
        with lock:
            for sel in selected:
                store_num = self.tree.item(sel, "values")[0]
                store_list.pop(store_num, None)
                status_dict.pop(store_num, None)
                last_change_dict.pop(store_num, None)
        self.refresh_ui()

    def sort_by_column(self, col):
        # Toggle sort order
        order = "asc"
        if sort_state["column"] == col and sort_state["order"] == "asc":
            order = "desc"
        elif sort_state["column"] == col and sort_state["order"] == "desc":
            col, order = None, None  # Reset sort

        sort_state["column"] = col
        sort_state["order"] = order

        self.refresh_ui()


if __name__ == "__main__":
    root = tk.Tk()
    app = StoreMonitorApp(root)
    root.mainloop()
