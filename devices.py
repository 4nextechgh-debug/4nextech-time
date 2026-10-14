"""Pull users and punch logs from ZKTeco devices (any number of them) using pyzk."""
import os
import threading
import time
from datetime import datetime

import db

_sync_lock = threading.Lock()


def _connect(dev):
    from zk import ZK  # imported lazily so the web app still starts without pyzk

    zk = ZK(
        dev["ip"],
        port=int(dev["port"]),
        timeout=8,
        password=int(dev["comm_key"] or 0),
        force_udp=False,
        ommit_ping=True,
    )
    return zk.connect()


def test_device(dev):
    """Return (ok, message)."""
    conn = None
    try:
        conn = _connect(dev)
        serial = conn.get_serialnumber()
        name = conn.get_device_name()
        return True, f"Connected: {name} (serial {serial})"
    except Exception as exc:  # noqa: BLE001
        return False, f"Could not connect: {exc}"
    finally:
        if conn:
            try:
                conn.disconnect()
            except Exception:  # noqa: BLE001
                pass


def sync_device(sqlconn, dev):
    """Import users and punches from one device. Returns (ok, message)."""
    zconn = None
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        zconn = _connect(dev)
        zconn.disable_device()
        try:
            for user in zconn.get_users():
                code = str(user.user_id)
                name = (user.name or "").strip() or code
                sqlconn.execute(
                    "INSERT OR IGNORE INTO employees (code, name) VALUES (?, ?)",
                    (code, name),
                )
            new = 0
            for rec in zconn.get_attendance():
                ts = rec.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                cur = sqlconn.execute(
                    "INSERT OR IGNORE INTO punches (employee_code, ts, source, device_id) "
                    "VALUES (?, ?, 'device', ?)",
                    (str(rec.user_id), ts, dev["id"]),
                )
                new += cur.rowcount
        finally:
            zconn.enable_device()
        msg = f"OK, {new} new punch(es)"
        sqlconn.execute(
            "UPDATE devices SET last_sync=?, last_status=? WHERE id=?", (now, msg, dev["id"])
        )
        sqlconn.commit()
        return True, msg
    except Exception as exc:  # noqa: BLE001
        msg = f"Error: {exc}"
        sqlconn.execute(
            "UPDATE devices SET last_sync=?, last_status=? WHERE id=?", (now, msg, dev["id"])
        )
        sqlconn.commit()
        return False, msg
    finally:
        if zconn:
            try:
                zconn.disconnect()
            except Exception:  # noqa: BLE001
                pass


def sync_all():
    """Sync every active device. One failing device never stops the others."""
    results = []
    if not _sync_lock.acquire(blocking=False):
        return [("(busy)", False, "A sync is already running")]
    try:
        sqlconn = db.connect()
        try:
            for dev in sqlconn.execute("SELECT * FROM devices WHERE active=1").fetchall():
                ok, msg = sync_device(sqlconn, dev)
                results.append((dev["name"], ok, msg))
        finally:
            sqlconn.close()
    finally:
        _sync_lock.release()
    return results


def start_scheduler(minutes=None):
    minutes = minutes or int(os.environ.get("SYNC_MINUTES", "5"))

    def loop():
        while True:
            time.sleep(minutes * 60)
            try:
                sync_all()
            except Exception:  # noqa: BLE001
                pass

    t = threading.Thread(target=loop, daemon=True, name="device-sync")
    t.start()
    return t
