"""Windows desktop launcher for 4nextech Time.
Starts the web server in the background, opens the browser and shows a small
control window with the PC and phone addresses."""
import json
import os
import secrets
import socket
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox, simpledialog

APP_NAME = "4nextech Time"
DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), APP_NAME)
CONFIG = os.path.join(DATA_DIR, "config.json")
os.makedirs(DATA_DIR, exist_ok=True)


def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(cfg):
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f)


def lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def port_free(port):
    s = socket.socket()
    try:
        s.bind(("0.0.0.0", port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def open_pc(url):
    """Open the site as its own app window (Edge/Chrome --app), else the normal browser."""
    import subprocess
    for exe in ("msedge", "chrome"):
        try:
            subprocess.Popen(f'start "" {exe} --app={url}', shell=True)
            return
        except Exception:
            pass
    webbrowser.open(url)


def start_mdns(ip, port):
    """Advertise http://4nextech.local so phones and PCs find it without typing an IP."""
    try:
        from zeroconf import ServiceInfo, Zeroconf
        info = ServiceInfo("_http._tcp.local.", "4nextech Time._http._tcp.local.",
                           addresses=[socket.inet_aton(ip)], port=port,
                           server="4nextech.local.")
        zc = Zeroconf()
        zc.register_service(info)
        return zc
    except Exception:
        return None


def main():
    root = tk.Tk()
    root.withdraw()
    cfg = load_config()
    if not cfg.get("admin_password"):
        pw = simpledialog.askstring(APP_NAME, "First run. Choose an admin password:", show="*", parent=root)
        if not pw:
            return
        cfg["admin_password"] = pw
    cfg.setdefault("secret_key", secrets.token_hex(32))
    save_config(cfg)
    # port 80 gives a clean address (http://4nextech.local); fall back to 5000
    port = next((p for p in (80, 5000) if port_free(p)), None)
    if port is None:  # both busy: assume it is already running and just open it
        open_pc("http://localhost")
        return

    os.environ["ATT_DB"] = os.path.join(DATA_DIR, "attendance.db")
    os.environ["ADMIN_PASSWORD"] = cfg["admin_password"]
    os.environ["SECRET_KEY"] = cfg["secret_key"]
    import app as webapp  # after env vars: db path is read on import
    import devices
    from werkzeug.serving import make_server

    server = make_server("0.0.0.0", port, webapp.app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    devices.start_scheduler()

    suffix = "" if port == 80 else f":{port}"
    ip = lan_ip()
    start_mdns(ip, port)
    pc_url = f"http://localhost{suffix}"
    phone_url = f"http://4nextech.local{suffix}/"
    ip_url = f"http://{ip}{suffix}/"
    open_pc(pc_url)

    root.deiconify()
    root.title(APP_NAME)
    root.geometry("440x640")
    root.resizable(False, False)
    try:
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        root.iconbitmap(os.path.join(base, "static", "icons", "app.ico"))
    except Exception:
        pass
    tk.Label(root, text="4nextech Time is running", font=("Segoe UI", 13, "bold")).pack(pady=(14, 2))
    tk.Label(root, text="Keep this window open (minimise it). Closing it stops the server.",
             fg="#555").pack()

    def row(label, value):
        f = tk.Frame(root)
        f.pack(fill="x", padx=16, pady=(10, 0))
        tk.Label(f, text=label, anchor="w").pack(anchor="w")
        e = tk.Entry(f)
        e.insert(0, value)
        e.configure(state="readonly")
        e.pack(fill="x")
    row("Open on this PC:", pc_url)
    row("Open on phones (same Wi-Fi):", phone_url)
    row("If that name does not work, use:", ip_url)

    try:  # QR code: scan once with the phone camera, then add to home screen
        import io
        import qrcode
        buf = io.BytesIO()
        qrcode.make(phone_url).save(buf, format="PNG")
        img = tk.PhotoImage(data=buf.getvalue())
        factor = max(1, img.width() // 200)
        img = img.subsample(factor, factor)
        lbl = tk.Label(root, image=img)
        lbl.image = img
        lbl.pack(pady=(12, 0))
        tk.Label(root, text="Scan with the phone camera (same Wi-Fi) - it opens straight into the app",
                 fg="#555", wraplength=400).pack()
    except Exception:
        pass

    btns = tk.Frame(root)
    btns.pack(pady=14)
    tk.Button(btns, text="Open on this PC", command=lambda: open_pc(pc_url)).pack(side="left", padx=4)

    def copy_phone():
        root.clipboard_clear()
        root.clipboard_append(phone_url)
    tk.Button(btns, text="Copy phone address", command=copy_phone).pack(side="left", padx=4)

    def change_pw():
        pw = simpledialog.askstring(APP_NAME, "New admin password (applies after restart):", show="*", parent=root)
        if pw:
            cfg["admin_password"] = pw
            save_config(cfg)
            messagebox.showinfo(APP_NAME, "Saved. Restart the app to use it.")
    tk.Button(btns, text="Change password", command=change_pw).pack(side="left", padx=4)

    def quit_app():
        if messagebox.askyesno(APP_NAME, "Stop 4nextech Time? Phones and the clock-in page will stop working."):
            server.shutdown()
            root.destroy()
    root.protocol("WM_DELETE_WINDOW", quit_app)
    root.mainloop()


if __name__ == "__main__":
    main()
