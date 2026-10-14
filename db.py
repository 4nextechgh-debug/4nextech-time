import os
import sqlite3
from flask import g

DB_PATH = os.environ.get(
    "ATT_DB", os.path.join(os.path.dirname(os.path.abspath(__file__)), "attendance.db")
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS shifts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    start_time TEXT NOT NULL,          -- HH:MM
    end_time TEXT NOT NULL,            -- HH:MM
    grace_min INTEGER NOT NULL DEFAULT 10,
    workdays TEXT NOT NULL DEFAULT '0,1,2,3,4'   -- Monday=0
);
CREATE TABLE IF NOT EXISTS employees (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,         -- must match the user ID on the device
    name TEXT NOT NULL,
    department TEXT DEFAULT '',
    shift_id INTEGER REFERENCES shifts(id),
    pin_hash TEXT,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS devices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    ip TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 4370,
    comm_key INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    last_sync TEXT,
    last_status TEXT
);
CREATE TABLE IF NOT EXISTS punches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_code TEXT NOT NULL,
    ts TEXT NOT NULL,                  -- YYYY-MM-DD HH:MM:SS
    source TEXT NOT NULL,              -- device | web | manual
    device_id INTEGER NOT NULL DEFAULT 0,
    note TEXT DEFAULT '',
    UNIQUE (employee_code, ts, device_id)
);
CREATE INDEX IF NOT EXISTS idx_punch_ts ON punches(ts);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def get_db():
    if "db" not in g:
        g.db = connect()
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def get_setting(conn, key, default=""):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
    conn.commit()


def init_db():
    conn = connect()
    conn.executescript(SCHEMA)
    if conn.execute("SELECT COUNT(*) FROM shifts").fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO shifts (name, start_time, end_time, grace_min, workdays) "
            "VALUES ('General', '08:00', '17:00', 10, '0,1,2,3,4')"
        )
    conn.commit()
    conn.close()
