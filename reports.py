"""Attendance report: one row per employee per day."""
from datetime import datetime, timedelta

DEFAULT_SHIFT = {"start_time": "08:00", "end_time": "17:00", "grace_min": 10, "workdays": "0,1,2,3,4"}


def hm(minutes):
    """Format minutes as H:MM (e.g. 485 -> '8:05')."""
    minutes = int(minutes or 0)
    return f"{minutes // 60}:{minutes % 60:02d}"


def _minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _mod(dt):
    return dt.hour * 60 + dt.minute


def build_report(conn, start, end, dept=None):
    emps = conn.execute(
        "SELECT e.code, e.name, e.department, s.name AS shift_name, s.start_time, s.end_time, "
        "s.grace_min, s.workdays FROM employees e LEFT JOIN shifts s ON s.id = e.shift_id "
        "WHERE e.active = 1 ORDER BY e.name"
    ).fetchall()

    lo = start.isoformat() + " 00:00:00"
    hi = (end + timedelta(days=1)).isoformat() + " 00:00:00"
    by_day = {}
    for p in conn.execute(
        "SELECT employee_code, ts FROM punches WHERE ts >= ? AND ts < ? ORDER BY ts", (lo, hi)
    ):
        by_day.setdefault((p["employee_code"], p["ts"][:10]), []).append(
            datetime.strptime(p["ts"], "%Y-%m-%d %H:%M:%S")
        )

    rows = []
    summary = {}
    day = start
    while day <= end:
        for e in emps:
            if dept and (e["department"] or "") != dept:
                continue
            shift = {
                "start_time": e["start_time"] or DEFAULT_SHIFT["start_time"],
                "end_time": e["end_time"] or DEFAULT_SHIFT["end_time"],
                "grace_min": e["grace_min"] if e["grace_min"] is not None else DEFAULT_SHIFT["grace_min"],
                "workdays": e["workdays"] or DEFAULT_SHIFT["workdays"],
            }
            is_workday = str(day.weekday()) in shift["workdays"].split(",")
            ps = by_day.get((e["code"], day.isoformat()), [])
            s = summary.setdefault(
                e["code"],
                {"code": e["code"], "name": e["name"], "department": e["department"] or "",
                 "present": 0, "late": 0, "absent": 0, "minutes": 0, "overtime": 0},
            )

            first = last = None
            worked = late = overtime = 0
            if not ps:
                if not is_workday:
                    continue
                status = "Absent"
                s["absent"] += 1
            else:
                first, last = ps[0], ps[-1]
                if len(ps) == 1:
                    status = "Missing out"
                else:
                    worked = int((last - first).total_seconds() // 60)
                    overtime = max(0, _mod(last) - _minutes(shift["end_time"])) if is_workday else worked
                late = max(0, _mod(first) - (_minutes(shift["start_time"]) + shift["grace_min"])) if is_workday else 0
                if len(ps) > 1:
                    status = "Late" if late else "Present"
                if not is_workday:
                    status = "Off-day work"
                s["present"] += 1
                s["late"] += 1 if late else 0
                s["minutes"] += worked
                s["overtime"] += overtime

            rows.append({
                "date": day.isoformat(), "code": e["code"], "name": e["name"],
                "department": e["department"] or "", "shift": e["shift_name"] or "Default",
                "first_in": first.strftime("%H:%M") if first else "",
                "last_out": last.strftime("%H:%M") if last and len(ps) > 1 else "",
                "worked_hours": round(worked / 60, 2), "total_time": hm(worked) if worked else "", "late_min": late,
                "overtime_min": overtime, "status": status,
            })
        day += timedelta(days=1)

    for s in summary.values():
        s["hours"] = round(s["minutes"] / 60, 2)
        s["total_time"] = hm(s["minutes"])
        s["ot_time"] = hm(s["overtime"])
    return rows, list(summary.values())
