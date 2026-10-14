import csv
import hmac
import io
import json
import os
import time
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, Response, jsonify, send_from_directory, flash, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db
import devices
import reports

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-change-me")
app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_HTTPONLY=True)
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin")
app.teardown_appcontext(db.close_db)

_failures = {}  # ip -> [timestamps] for web-clock PIN throttling


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------- auth ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if hmac.compare_digest(request.form.get("password", ""), ADMIN_PASSWORD):
            session["admin"] = True
            nxt = request.args.get("next", "")
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = url_for("dashboard")
            return redirect(nxt)
        flash("Wrong password", "bad")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("clock"))


# ---------- dashboard ----------
@app.route("/")
@login_required
def dashboard():
    conn = db.get_db()
    today = date.today().isoformat() + " 00:00:00"
    stats = {
        "employees": conn.execute("SELECT COUNT(*) FROM employees WHERE active=1").fetchone()[0],
        "present": conn.execute(
            "SELECT COUNT(DISTINCT employee_code) FROM punches WHERE ts >= ?", (today,)).fetchone()[0],
        "devices": conn.execute("SELECT COUNT(*) FROM devices WHERE active=1").fetchone()[0],
    }
    recent = conn.execute(
        "SELECT p.*, COALESCE(e.name, '(unknown)') AS name, COALESCE(d.name, '') AS device_name "
        "FROM punches p LEFT JOIN employees e ON e.code = p.employee_code "
        "LEFT JOIN devices d ON d.id = p.device_id ORDER BY p.ts DESC LIMIT 15").fetchall()
    return render_template("dashboard.html", stats=stats, recent=recent)


# ---------- employees ----------
@app.route("/employees")
@login_required
def employees():
    conn = db.get_db()
    edit_id = request.args.get("edit")
    emp = conn.execute("SELECT * FROM employees WHERE id=?", (edit_id,)).fetchone() if edit_id else None
    rows = conn.execute(
        "SELECT e.*, s.name AS shift_name FROM employees e LEFT JOIN shifts s ON s.id=e.shift_id "
        "ORDER BY e.active DESC, e.name").fetchall()
    shifts = conn.execute("SELECT * FROM shifts ORDER BY name").fetchall()
    return render_template("employees.html", emp=emp, rows=rows, shifts=shifts)


@app.route("/employees/save", methods=["POST"])
@login_required
def employee_save():
    conn = db.get_db()
    f = request.form
    code, name = f.get("code", "").strip(), f.get("name", "").strip()
    if not code or not name:
        flash("Code and name are required", "bad")
        return redirect(url_for("employees"))
    shift_id = f.get("shift_id") or None
    pin = f.get("pin", "").strip()
    try:
        if f.get("id"):
            conn.execute("UPDATE employees SET code=?, name=?, department=?, shift_id=? WHERE id=?",
                         (code, name, f.get("department", "").strip(), shift_id, f["id"]))
            if pin:
                conn.execute("UPDATE employees SET pin_hash=? WHERE id=?",
                             (generate_password_hash(pin), f["id"]))
        else:
            conn.execute(
                "INSERT INTO employees (code, name, department, shift_id, pin_hash) VALUES (?,?,?,?,?)",
                (code, name, f.get("department", "").strip(), shift_id,
                 generate_password_hash(pin) if pin else None))
        conn.commit()
        flash("Employee saved", "ok")
    except Exception:  # duplicate code
        conn.rollback()
        flash("That employee code already exists", "bad")
    return redirect(url_for("employees"))


@app.route("/employees/<int:eid>/toggle", methods=["POST"])
@login_required
def employee_toggle(eid):
    conn = db.get_db()
    conn.execute("UPDATE employees SET active = 1 - active WHERE id=?", (eid,))
    conn.commit()
    return redirect(url_for("employees"))


# ---------- shifts ----------
@app.route("/shifts", methods=["GET", "POST"])
@login_required
def shifts():
    conn = db.get_db()
    if request.method == "POST":
        f = request.form
        days = ",".join(f.getlist("workdays")) or "0,1,2,3,4"
        try:
            grace = int(f.get("grace_min") or 0)
        except ValueError:
            grace = 0
        conn.execute(
            "INSERT INTO shifts (name, start_time, end_time, grace_min, workdays) VALUES (?,?,?,?,?)",
            (f.get("name", "").strip() or "Shift", f.get("start_time", "08:00"),
             f.get("end_time", "17:00"), grace, days))
        conn.commit()
        flash("Shift added", "ok")
        return redirect(url_for("shifts"))
    rows = conn.execute("SELECT s.*, (SELECT COUNT(*) FROM employees e WHERE e.shift_id=s.id) AS used "
                        "FROM shifts s ORDER BY name").fetchall()
    return render_template("shifts.html", rows=rows)


@app.route("/shifts/<int:sid>/delete", methods=["POST"])
@login_required
def shift_delete(sid):
    conn = db.get_db()
    used = conn.execute("SELECT COUNT(*) FROM employees WHERE shift_id=?", (sid,)).fetchone()[0]
    if used:
        flash("Shift is assigned to employees; reassign them first", "bad")
    else:
        conn.execute("DELETE FROM shifts WHERE id=?", (sid,))
        conn.commit()
    return redirect(url_for("shifts"))


# ---------- devices ----------
@app.route("/devices", methods=["GET", "POST"])
@login_required
def device_list():
    conn = db.get_db()
    if request.method == "POST":
        f = request.form
        try:
            port, key = int(f.get("port") or 4370), int(f.get("comm_key") or 0)
        except ValueError:
            flash("Port and comm key must be numbers", "bad")
            return redirect(url_for("device_list"))
        conn.execute("INSERT INTO devices (name, ip, port, comm_key) VALUES (?,?,?,?)",
                     (f.get("name", "").strip() or f.get("ip", ""), f.get("ip", "").strip(), port, key))
        conn.commit()
        flash("Device added", "ok")
        return redirect(url_for("device_list"))
    rows = conn.execute("SELECT * FROM devices ORDER BY name").fetchall()
    return render_template("devices.html", rows=rows)


def _device(did):
    return db.get_db().execute("SELECT * FROM devices WHERE id=?", (did,)).fetchone()


@app.route("/devices/<int:did>/test", methods=["POST"])
@login_required
def device_test(did):
    dev = _device(did)
    if dev:
        ok, msg = devices.test_device(dev)
        flash(f"{dev['name']}: {msg}", "ok" if ok else "bad")
    return redirect(url_for("device_list"))


@app.route("/devices/<int:did>/sync", methods=["POST"])
@login_required
def device_sync(did):
    dev = _device(did)
    if dev:
        ok, msg = devices.sync_device(db.get_db(), dev)
        flash(f"{dev['name']}: {msg}", "ok" if ok else "bad")
    return redirect(url_for("device_list"))


@app.route("/devices/sync-all", methods=["POST"])
@login_required
def device_sync_all():
    for name, ok, msg in devices.sync_all():
        flash(f"{name}: {msg}", "ok" if ok else "bad")
    return redirect(url_for("device_list"))


@app.route("/devices/<int:did>/toggle", methods=["POST"])
@login_required
def device_toggle(did):
    conn = db.get_db()
    conn.execute("UPDATE devices SET active = 1 - active WHERE id=?", (did,))
    conn.commit()
    return redirect(url_for("device_list"))


@app.route("/devices/<int:did>/delete", methods=["POST"])
@login_required
def device_delete(did):
    conn = db.get_db()
    conn.execute("DELETE FROM devices WHERE id=?", (did,))
    conn.commit()
    return redirect(url_for("device_list"))


# ---------- punches (manual entry + log) ----------
@app.route("/punches", methods=["GET", "POST"])
@login_required
def punches():
    conn = db.get_db()
    if request.method == "POST":
        code = request.form.get("code", "").strip()
        try:
            ts = datetime.fromisoformat(request.form.get("ts", "")).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            flash("Enter a valid date and time", "bad")
            return redirect(url_for("punches"))
        try:
            conn.execute("INSERT INTO punches (employee_code, ts, source, device_id, note) "
                         "VALUES (?,?, 'manual', 0, ?)", (code, ts, request.form.get("note", "").strip()))
            conn.commit()
            flash("Punch added", "ok")
        except Exception:
            conn.rollback()
            flash("That punch already exists", "bad")
        return redirect(url_for("punches"))

    start = request.args.get("start") or (date.today() - timedelta(days=7)).isoformat()
    end = request.args.get("end") or date.today().isoformat()
    code = request.args.get("code", "").strip()
    sql = ("SELECT p.*, COALESCE(e.name, '(unknown)') AS name, COALESCE(d.name, '') AS device_name "
           "FROM punches p LEFT JOIN employees e ON e.code = p.employee_code "
           "LEFT JOIN devices d ON d.id = p.device_id WHERE p.ts >= ? AND p.ts < ?")
    args = [start + " 00:00:00", (date.fromisoformat(end) + timedelta(days=1)).isoformat() + " 00:00:00"]
    if code:
        sql += " AND p.employee_code = ?"
        args.append(code)
    rows = conn.execute(sql + " ORDER BY p.ts DESC LIMIT 500", args).fetchall()
    emps = conn.execute("SELECT code, name FROM employees WHERE active=1 ORDER BY name").fetchall()
    return render_template("punches.html", rows=rows, emps=emps, start=start, end=end, code=code,
                           now=datetime.now().strftime("%Y-%m-%dT%H:%M"))


@app.route("/punches/<int:pid>/delete", methods=["POST"])
@login_required
def punch_delete(pid):
    conn = db.get_db()
    conn.execute("DELETE FROM punches WHERE id=? AND source != 'device'", (pid,))
    conn.commit()
    return redirect(request.referrer or url_for("punches"))


# ---------- public web clock-in ----------
@app.route("/clock", methods=["GET", "POST"])
def clock():
    result = None
    if request.method == "POST":
        ip = request.remote_addr or "?"
        recent = [t for t in _failures.get(ip, []) if time.time() - t < 300]
        _failures[ip] = recent
        if len(recent) >= 5:
            flash("Too many failed attempts. Try again in a few minutes.", "bad")
            return render_template("clock.html", result=None)
        conn = db.get_db()
        code, pin = request.form.get("code", "").strip(), request.form.get("pin", "")
        emp = conn.execute("SELECT * FROM employees WHERE code=? AND active=1", (code,)).fetchone()
        if not emp or not emp["pin_hash"] or not check_password_hash(emp["pin_hash"], pin):
            _failures[ip].append(time.time())
            flash("Invalid code or PIN", "bad")
        else:
            last = conn.execute("SELECT ts FROM punches WHERE employee_code=? ORDER BY ts DESC LIMIT 1",
                                (code,)).fetchone()
            if last and (datetime.now() - datetime.strptime(last["ts"], "%Y-%m-%d %H:%M:%S")).total_seconds() < 60:
                flash("You already clocked a moment ago", "bad")
            else:
                ts = now_str()
                conn.execute("INSERT OR IGNORE INTO punches (employee_code, ts, source, device_id) "
                             "VALUES (?,?, 'web', 0)", (code, ts))
                conn.commit()
                result = {"name": emp["name"], "ts": ts}
    return render_template("clock.html", result=result)


# ---------- reports ----------
AUTO_SYNC_SECONDS = int(os.environ.get("REPORT_SYNC_SECONDS", "60"))


def _auto_sync(conn, force=False):
    """Pull the latest punches from every active device before a report is built.

    Skipped when the devices were synced less than AUTO_SYNC_SECONDS ago (failed attempts count
    too, so an unreachable device cannot slow down every page load). Returns a list of
    (device name, ok, message) for devices that were contacted.
    """
    rows = conn.execute("SELECT last_sync FROM devices WHERE active=1").fetchall()
    if not rows:
        return []
    if not force:
        stamps = [r["last_sync"] for r in rows if r["last_sync"]]
        if len(stamps) == len(rows):
            newest = max(datetime.strptime(t, "%Y-%m-%d %H:%M:%S") for t in stamps)
            if (datetime.now() - newest).total_seconds() < AUTO_SYNC_SECONDS:
                return []
    try:
        return devices.sync_all()
    except Exception as exc:  # noqa: BLE001
        return [("(devices)", False, str(exc))]


@app.route("/reports")
@login_required
def report_view():
    conn = db.get_db()
    today = date.today()
    try:
        start = date.fromisoformat(request.args.get("start") or today.replace(day=1).isoformat())
        end = date.fromisoformat(request.args.get("end") or today.isoformat())
    except ValueError:
        flash("Invalid dates", "bad")
        return redirect(url_for("report_view"))
    if end < start or (end - start).days > 366:
        flash("Pick a range of up to one year", "bad")
        return redirect(url_for("report_view"))
    dept = request.args.get("dept", "").strip() or None

    # Company name: asked for on the report page, remembered, and used as the report heading.
    given = request.args.get("company")
    if given is not None and given.strip():
        db.set_setting(conn, "company_name", given.strip()[:120])
    company = db.get_setting(conn, "company_name")
    fmt = request.args.get("format")
    if not company:
        if fmt:
            flash("Enter the company name first. It is printed as the heading of the report.", "bad")
        return render_template("reports.html", rows=[], summary=[], totals=None, start=start, end=end,
                               dept=dept or "", depts=[], company="", need_company=True)

    # Pull fresh clock-in/out data from the devices automatically.
    for name, ok, msg in _auto_sync(conn, force=request.args.get("refresh") == "1"):
        if not ok:
            flash(f"{name}: {msg} (showing the last data received)", "bad")
    rows, summary = reports.build_report(conn, start, end, dept)

    if fmt in ("xlsx", "pdf"):
        try:
            import exports
            if fmt == "xlsx":
                data = exports.xlsx_bytes(rows, summary, start, end, dept, company)
                mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            else:
                data = exports.pdf_bytes(rows, summary, start, end, dept, company)
                mime = "application/pdf"
        except ImportError:
            flash("Excel/PDF export needs openpyxl and reportlab: pip install -r requirements.txt", "bad")
            return redirect(url_for("report_view", start=start, end=end, dept=dept or ""))
        return Response(data, mimetype=mime, headers={
            "Content-Disposition": f"attachment; filename=4nextech_time_{start}_{end}.{fmt}"})

    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        cols = ["date", "code", "name", "department", "shift", "first_in", "last_out",
                "total_time", "worked_hours", "late_min", "overtime_min", "status"]

        def safe(v):  # stop spreadsheet formula injection from names/company
            v = str(v)
            return "'" + v if v[:1] in ("=", "+", "-", "@") else v
        w.writerow([safe(company)])
        w.writerow([f"Attendance report {start} to {end}" + (f" | Department: {dept}" if dept else "")])
        w.writerow([])
        w.writerow(["Summary"])
        w.writerow(["code", "name", "department", "days_present", "late_days", "absent_days",
                    "total_time", "hours", "overtime"])
        for s_ in summary:
            w.writerow([safe(s_["code"]), safe(s_["name"]), safe(s_["department"]), s_["present"], s_["late"],
                        s_["absent"], s_["total_time"], s_["hours"], s_["ot_time"]])
        w.writerow([])
        w.writerow(["Daily detail"])
        w.writerow(cols)
        for r in rows:
            w.writerow([safe(r[c]) if c in ("code", "name", "department", "shift") else r[c] for c in cols])
        return Response(buf.getvalue(), mimetype="text/csv", headers={
            "Content-Disposition": f"attachment; filename=4nextech_time_{start}_{end}.csv"})

    depts = [r[0] for r in conn.execute(
        "SELECT DISTINCT department FROM employees WHERE department != '' ORDER BY department")]
    totals = {"minutes": sum(x["minutes"] for x in summary),
              "overtime": sum(x["overtime"] for x in summary),
              "present": sum(x["present"] for x in summary),
              "late": sum(x["late"] for x in summary),
              "absent": sum(x["absent"] for x in summary)}
    totals["total_time"] = reports.hm(totals["minutes"])
    totals["ot_time"] = reports.hm(totals["overtime"])
    return render_template("reports.html", rows=rows, summary=summary, totals=totals, start=start, end=end,
                           dept=dept or "", depts=depts, company=company, need_company=False)


# ---------- installable app (PWA) ----------
@app.route("/manifest.webmanifest")
def manifest():
    icons = [
        {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "/static/icons/maskable-192.png", "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
        {"src": "/static/icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ]
    data = {"name": "4nextech Time", "short_name": "4nextech", "description": "Time and attendance",
            "start_url": "/", "scope": "/", "id": "/", "display": "standalone",
            "background_color": "#494a4d", "theme_color": "#2457d6", "icons": icons,
            "shortcuts": [{"name": "Clock in / out", "url": "/clock"}]}
    return Response(json.dumps(data), mimetype="application/manifest+json")


@app.route("/sw.js")
def service_worker():
    resp = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.route("/phone")
def phone():
    return redirect("/")


@app.route("/offline")
def offline():
    return render_template("offline.html")


db.init_db()

if __name__ == "__main__":
    devices.start_scheduler()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")), debug=False, use_reloader=False)
