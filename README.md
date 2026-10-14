# 4nextech Time

A small self-hosted time and attendance app (Flask + SQLite). No licence or activation needed.

- Pull punches from any number of ZKTeco devices (via the open-source `pyzk` library)
- Web clock-in for employees (code + PIN) and manual punches added by an admin
- Employees, shifts (grace period, work days), late / overtime / absent calculation
- Reports with Excel (.xlsx), PDF and CSV export

## Run it

```bash
python -m venv venv && source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt
export ADMIN_PASSWORD='choose-a-strong-password'      # Windows: set ADMIN_PASSWORD=...
export SECRET_KEY='any-long-random-string'
python app.py
```

Open http://localhost:5000 . Employees use `/clock`; admins log in at `/login`.
If you don't set ADMIN_PASSWORD, the default is `admin`. Change it before real use.

## Reports

- Open **Reports** and enter your **company name** the first time. It is saved and printed as the
  heading of the report on screen, Excel, PDF and CSV. Change it on the same page whenever needed.
- Opening a report (or exporting it) automatically pulls the latest clock-in/out data from every
  active device first, at most once per minute (`REPORT_SYNC_SECONDS`). **Refresh from devices**
  forces a pull. If a device is unreachable, the last data received is shown with a warning.
- Every user shows clock in, clock out and total time per day, a per-user total time summary
  and a grand total row.

## Adding devices

1. Devices page > Add device: name, IP, port (default 4370), comm key (0 unless you set one on the device).
2. Press Test to confirm the server can reach it, then Sync.
3. All active devices are pulled automatically every 5 minutes (set `SYNC_MINUTES` to change).
4. Users enrolled on a device are created as employees automatically; the employee code is the device user ID.

The server and the devices must be on the same network (or routable), with TCP port 4370 open.

## Notes

- Punch times are stored as the device or server local time, so keep device clocks correct.
- The report uses the first punch of the day as "in" and the last as "out".
- Device punches are read-only and are never duplicated, so syncing repeatedly is safe.
- Web clock PINs are hashed. Five wrong attempts per IP block that IP for 5 minutes.
- For production, put it behind HTTPS (nginx or Caddy) and back up `attendance.db`.
- Installable: open the site in Chrome/Edge (PC) or Chrome/Safari (phone) and use "Install app" / "Add to Home Screen". Needs HTTPS (or localhost).
- Run it with `python app.py`, which also starts the automatic device sync. If you switch to
  gunicorn, the background sync does not start, so use the "Sync all devices now" button or
  schedule a call to `devices.sync_all()` yourself.
- PDF export uses DejaVu Sans or Arial when found on the server, so names with letters such as
  Ɔ and ɛ print correctly. On a minimal Linux server, install the `fonts-dejavu-core` package.
- The ZKTeco part uses the `pyzk` library. It was tested here against a stand-in device, not real
  hardware, so press Test on the Devices page with your first real device before relying on it.

## Windows program and phone page

- `build_windows.bat` (run on Windows) builds `dist\4nextech Time\4nextech Time.exe`; with Inno Setup installed it also builds `installer_output\4nextech-Time-Setup.exe`.
- The program stores its data in `%LOCALAPPDATA%\4nextech Time`, asks for the admin password on first run, and shows the PC and phone addresses.
- On a phone (same Wi-Fi) open `http://PC-IP:5000/phone`, or send `static/phone.html` to the phone and enter the PC address once.
