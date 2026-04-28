# Automated Asset Tracking System (AATS)

AATS is a hybrid IoT system for lab anti-theft monitoring.

## Demo scenarios

In evaluations you can demonstrate AATS using these example flows:

- **USB theft attempt**
  - Start Mosquitto, the FastAPI server, and the student agent on a lab PC that has a tracked USB mouse/keyboard configured in `student_agent/config.json`.
  - Show the device as **CONNECTED (OK)** on the admin dashboard.
  - Unplug the tracked USB device:
    - Within a few seconds the device card turns **WARNING / PENDING** (yellow) while the server debounce timer runs (default 60s).
    - If the device remains unplugged beyond the timeout, the card turns **CRITICAL (red)**, an audio alert plays, and a `CRITICAL` event is stored in the database with precise timestamps.
  - Plug the device back in and show how the state returns to **OK** and the dashboard history table includes the full sequence of events.

- **Bluetooth device moving out of range**
  - Configure a Bluetooth device MAC address in `student_agent/config.json` and keep it near the PC so it shows as **CONNECTED**.
  - Gradually move the device away:
    - When RSSI drops below the configured threshold, the status becomes **WEAK_SIGNAL (WARNING)**.
    - If the device stays out of range beyond the longer Bluetooth timeout (default 300s), the server raises a **CRITICAL** alert similar to the USB case.
  - Bring the device back into range and show that the alert eventually closes and severity returns to **OK**.

- **PC abruptly powered off**
  - With the student agent connected to the MQTT broker, confirm the PC appears as **online** in the dashboard's PC status section.
  - Forcefully power off or disconnect the PC from the network.
  - The broker publishes the MQTT Last Will & Testament, and the server updates the PC heartbeat to **offline**, which is reflected on the dashboard without requiring a clean shutdown from the agent.

## Implemented in this repo

- `student_agent/`:
  - USB monitoring by configured `VID/PID`
  - Bluetooth monitoring by configured `MAC` + RSSI thresholds
  - MQTT event publishing (`.../event`)
  - MQTT LWT + retained status publishing (`.../status`)
- `server/`:
  - FastAPI backend
  - MQTT ingestion for `status` and `event`
  - Debounce logic:
    - USB `MISSING` -> critical after 60s (configurable)
    - Bluetooth `MISSING/WEAK_SIGNAL` -> critical after 300s default (configurable)
  - SQLite persistence and query APIs
- `admin_dashboard/`:
  - Device state grid (green/yellow/red)
  - Event/alert table
  - Auto-refresh + audio/beep on new critical alerts

## MQTT topics

- `aats/lab/{lab_id}/pc/{pc_id}/status`
- `aats/lab/{lab_id}/pc/{pc_id}/event`

## API endpoints

- `GET /health`
- `GET /labs/{lab_id}/devices`
- `GET /labs/{lab_id}/pcs`
- `GET /alerts?from=&to=&severity=&status=`
- `GET /events?lab_id=&pc_id=&device_id=&severity=&status=&from=&to=&limit=`
- `POST /auth/login`

---

## Quick Start (Recommended)

AATS ships with two setup scripts that handle everything automatically.

### Prerequisites (install once on every PC)
- [Python 3.10+](https://www.python.org/downloads/) — make sure to check **"Add Python to PATH"** during install
- Mosquitto on Admin PC:
  - `admin_setup.exe` now tries to auto-install via `winget` if Mosquitto is missing
  - Offline fallback: place `mosquitto.exe` at `mqtt_broker/mosquitto.exe` in the project root
  - Optional integrity file for bundled binary: `mqtt_broker/mosquitto.sha256`
  - If auto-install fails (offline/proxy/no winget), install manually from [Mosquitto MQTT Broker](https://mosquitto.org/download/)
- Lab PC agent connection requirements:
  - `agent_setup.exe` does **not** install Mosquitto locally
  - It only needs the Admin PC broker address and the tracked device config

Optional secure installer download mode (Admin PC):
- Set `AATS_MOSQUITTO_INSTALLER_URL` and `AATS_MOSQUITTO_INSTALLER_SHA256`
- `admin_setup.exe` will download only if both are set and SHA-256 matches exactly

### Step 1 — Clone the repo (on every PC)
```powershell
git clone https://github.com/yourname/AATS
cd AATS
```

### Step 2 — Install dependencies (on every PC)
```powershell
pip install -r server/requirements.txt
pip install -r student_agent/requirements.txt
pip install pyinstaller
```

### Step 3 — Build the EXEs (on every PC, one time only)
```powershell
# Admin PC EXE
pyinstaller --onefile --uac-admin admin_setup.py

# Lab PC EXE
pyinstaller --onefile agent_setup.py

# Optional but recommended for service mode:
# run dist/agent_setup.exe as Administrator once

```
Both EXEs will appear in the `dist/` folder.

### Step 4 — Run on Admin PC
Double-click `dist/admin_setup.exe` (Windows will ask for Administrator permissions — click Yes).

Note: Admin services are **manual-start only** (no reboot auto-start). The dashboard/server run only when the admin launches `admin_setup.exe`.

It will automatically:
- Open firewall ports for MQTT, the API, and the dashboard
- Start Mosquitto broker
- Start the FastAPI server
- Serve the admin dashboard
- Open the dashboard login page in your browser
- Broadcast its IP address so Lab PCs can find it automatically
- Print the Mosquitto provisioning source (service/installed/bundled/winget/download) for quick verification

> Login credentials: username `admin`, password `admin`

> Close the window to stop all services and automatically close the firewall ports.

### Step 5 — Run on each Lab PC
Double-click `dist/agent_setup.exe`.

**First time only**, it will ask you to:
1. Wait while it auto-detects the Admin PC IP from the broadcast (30s timeout — if not found it will ask you to type the IP manually)
2. Enter a unique PC ID for this machine (e.g. `PC01`, `PC02`)
3. Pick which connected USB devices to monitor from a list

It will then write `config.json` automatically and configure startup mode.

- If run as Administrator, it installs a Windows service so the agent starts at boot.
- If not run as Administrator, it falls back to registry startup after user login.

In both cases it then launches the agent.

Only Lab PC agent components are configured for reboot auto-start.

Startup mode priority on Lab PCs:
- If run as Administrator, setup installs/starts a Windows service (`AATSAgentService`) for boot-resilient startup.
- If not Administrator, setup falls back to user registry startup (starts after user login).

The Lab PC setup output now also prints a startup status line so you can confirm the effective mode.

**On all future runs** it skips setup and launches the agent directly.

---

## Manual Setup (Advanced)

If you prefer to run without the EXEs:

1) Start MQTT broker (Mosquitto) at `localhost:1883`.

2) Run server:

```powershell
cd server
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

3) Run student agent:

```powershell
cd student_agent
pip install -r requirements.txt
# Option A: run in foreground (for testing)
python main.py

# Option B: install as Windows service (requires admin PowerShell)
python windows_service.py install
python windows_service.py start
```

4) Open `admin_dashboard/index.html` in a browser (or serve via `python -m http.server 5500` and open `http://localhost:5500/login.html`).

5) Make sure `const API_BASE` in `admin_dashboard/script.js` points to the correct server URL.

---

## Config notes

- Agent config: `student_agent/config.json`
- NTP sync is recommended so CCTV and event times match.
- Server env vars:
  - `AATS_HOST`, `AATS_PORT`
  - `AATS_MQTT_BROKER`, `AATS_MQTT_PORT`
  - `AATS_DB_PATH`
  - `AATS_USB_TIMEOUT_SEC` (default `60`)
  - `AATS_BT_TIMEOUT_SEC` (default `300`)
  - `AATS_ADMIN_USERNAME`, `AATS_ADMIN_PASSWORD` (single shared admin account for the dashboard)

## Database observability & debounce mapping

- **Debounce timeouts (configurable):**
  - USB missing timeout: `AATS_USB_TIMEOUT_SEC` → used by the server in `server/config.py` as `Settings.usb_missing_timeout_sec`, and consumed in `server/app.py` by the `timeout_for(...)` helper when a USB device reports `status="MISSING"`.
  - Bluetooth missing/weak timeout: `AATS_BT_TIMEOUT_SEC` → used as `Settings.bluetooth_missing_timeout_sec`, applied in `timeout_for(...)` when a Bluetooth device reports `status="MISSING"` or `status="WEAK_SIGNAL"`.
- **How debounce works (server-side):**
  - Incoming device events are handled in `server/app.py` by `handle_event(...)`.
  - When a device first goes missing/out-of-range, it is placed into an in-memory `pending` map with a `started_at` timestamp and the chosen timeout.
  - While pending, the current state in SQLite (`device_state_current`) is set to:
    - `severity="WARNING"`
    - `alert_status="PENDING"`
    - `pending_since=<ISO timestamp for when the debounce window started>`
  - A background thread `pending_watcher()` periodically checks for entries whose `now - started_at >= timeout_sec` and promotes them to:
    - `severity="CRITICAL"`
    - `alert_status="OPEN"`
    - `pending_since=NULL`
    - A `CRITICAL` row is inserted into `device_events` with a `details_json` field that includes `"debounce_seconds": <timeout>`.

**SQLite tables vs requirements:**

- `device_events` (history / forensic timeline)
  - One row per significant state change.
  - Maps to: **warnings, critical alarms, and historical timeline** required for post-incident analysis.
  - Key columns:
    - `status` – raw device status from the agent: `CONNECTED`, `MISSING`, `WEAK_SIGNAL`, etc.
    - `severity` – normalized severity (`OK`, `WARNING`, `CRITICAL`) used by the dashboard colour-coding.
    - `alert_status` – lifecycle of the alert (`OPEN`, `CLOSED`).
    - `observed_at`, `agent_time`, `received_at` – timestamps to cross-check CCTV footage vs device/PC clocks.
    - `details_json` – JSON string for extra context (e.g. `{"debounce_seconds": 60}`).
- `device_state_current` (live view)
  - One row per `(lab_id, pc_id, device_id)` representing the **latest known state**.
  - Maps to: **current warning/critical status cards** on the dashboard.
  - Key columns:
    - `current_status`, `severity`, `alert_status` – snapshot shown in the "Current Device States" grid.
    - `pending_since` – non-null only when the device is in **PENDING debounce window** (used to explain "yellow for 60 seconds" in the demo).
    - `updated_at` – last server-side update time for that device.
- `pc_heartbeat` (PC online/offline)
  - One row per `(lab_id, pc_id)` updated whenever the agent publishes a `status` message or when the MQTT Last Will & Testament fires.
  - Maps to: **PC online/offline status** in the dashboard's PC status panel.
  - Key columns:
    - `pc_status` – high-level state such as `online` / `offline`.
    - `last_seen` – timestamp originating from the agent (if present).
    - `updated_at` – when the server last touched this record.

### Quick DB queries for screenshots

For report screenshots or live debugging, you can either use `sqlite3` directly or the helper script `server/inspect_db.py`.

**Option A – raw `sqlite3`**

```powershell
cd server
sqlite3 database/aats.db
```

Inside the SQLite shell:

```sql
-- 1) Recent critical alerts for a given lab/PC
SELECT received_at, lab_id, pc_id, device_id, device_type, status, severity, alert_status
FROM device_events
WHERE lab_id = 'LAB1' AND pc_id = 'PC1' AND severity = 'CRITICAL'
ORDER BY received_at DESC
LIMIT 20;

-- 2) Current state of all devices in a lab (good for "current dashboard" screenshots)
SELECT lab_id, pc_id, device_id, device_type, current_status, severity, alert_status, pending_since, updated_at
FROM device_state_current
WHERE lab_id = 'LAB1'
ORDER BY pc_id, device_type, device_id;

-- 3) PC heartbeat view (online/offline)
SELECT lab_id, pc_id, pc_status, last_seen, agent_version, updated_at
FROM pc_heartbeat
WHERE lab_id = 'LAB1'
ORDER BY pc_id;
```

**Option B – Python helper script (recommended for demos)**

```powershell
cd server
python inspect_db.py --mode events --lab LAB1 --pc PC1 --limit 20

python inspect_db.py --mode state --lab LAB1

python inspect_db.py --mode heartbeat --lab LAB1
```

These commands print nicely formatted summaries that are easy to screenshot and paste into the project report.

## System architecture (report-ready)

- **Edge layer – Student agent (`student_agent/`)**
  - Monitors USB devices (by `VID/PID`) and Bluetooth devices (by MAC + RSSI) on each lab PC.
  - Publishes:
    - `status` messages with PC heartbeat and LWT: see `student_agent/mqtt_client.py` and the topic scheme in `config.json`.
    - `event` messages whenever a tracked device connects, disconnects, or goes out of range.
  - Runs either in the foreground (`python main.py`) or as a Windows service (see `windows_service.py` in the same folder).
- **Messaging layer – MQTT broker**
  - Mosquitto (or any MQTT broker) is used as the transport between agents and the server.
  - Topics:
    - `aats/lab/{lab_id}/pc/{pc_id}/status` – PC heartbeat + LWT.
    - `aats/lab/{lab_id}/pc/{pc_id}/event` – per-device events.
- **Backend + storage – Admin server (`server/`)**
  - `app.py` hosts a FastAPI app that:
    - Starts `MQTTListener` (`mqtt_listener.py`) on startup to subscribe to both `status` and `event` topics.
    - Normalizes device events into severity (`OK/WARNING/CRITICAL`) and debounced alert state (`PENDING/OPEN/CLOSED`).
    - Persists history and live state into SQLite through `Database` in `database.py`.
  - `config.py` holds all tunable settings (MQTT, DB path, timeouts).
- **Presentation layer – Admin dashboard (`admin_dashboard/`)**
  - `index.html`, `styles.css`, and `script.js` implement a small SPA-like page.
  - Pulls JSON from the server's REST APIs to render:
    - PC heartbeat cards (online/offline by lab).
    - Current device state cards (severity colour + PENDING vs OPEN).
    - Recent events/alerts table with an audible alarm for new `CRITICAL` events.
  - Access is restricted to a single admin username/password, which the page exchanges for a shared header token (`x-admin-token`) derived from the configured admin password via `POST /auth/login`.

## End-to-end workflow tied to code

1. **Normal operation**
   - The student agent periodically scans USB/Bluetooth devices (`student_agent/device_monitor.py`, `student_agent/bluetooth_monitor.py`).
   - Heartbeat/status messages are published to MQTT with PC metadata and LWT (`student_agent/mqtt_client.py`).
2. **Device unplugged / moved out of range**
   - On a change, the agent publishes an `event` message with:
     - `lab_id`, `pc_id`, `device_id`, `device_type`, `status`, and timestamps such as `observed_at`.
   - MQTT delivers this JSON to the server-side `MQTTListener` (`server/mqtt_listener.py`), which calls `handle_event(...)` in `server/app.py`.
3. **Debounce and alert promotion (server)**
   - `handle_event(...)`:
     - Immediately writes a `WARNING` + `PENDING` state into `device_state_current` via `Database.upsert_device_state(...)` when a timeout applies.
     - Stores the event payload in memory in the `pending` map with `started_at` and a per-device timeout derived from `timeout_for(...)`.
   - The `pending_watcher()` background thread periodically:
     - Checks for entries that have exceeded the timeout.
     - Promotes them to `CRITICAL` + `OPEN` both in `device_state_current` and `device_events`, including `debounce_seconds` in `details_json`.
4. **PC powered off / disconnected**
   - When a PC goes down unexpectedly, the broker publishes the agent's LWT on the `status` topic.
   - The server's `handle_status(...)` updates `pc_heartbeat` through `Database.upsert_heartbeat(...)`, flipping that PC to an offline state with timestamps.
5. **Dashboard rendering**
  - `script.js` calls:
     - `GET /labs/{lab_id}/pcs` → shows PC heartbeat cards (online vs offline).
     - `GET /labs/{lab_id}/devices` → shows current device cards, including `pending_since` for devices in the debounce window.
     - `GET /events` → shows the historical timeline of events.
   - New `CRITICAL` events trigger the audio alert once per `event_id`.

## Configuration and deployment (report section)

- **Prerequisites**
  - Python 3.10+ on both server and lab PCs.
  - Mosquitto MQTT broker reachable from all PCs.
  - Basic Bluetooth and USB drivers installed on the lab machines.
- **Server deployment**
  - Configure environment variables (on Windows PowerShell):
    - `AATS_MQTT_BROKER`, `AATS_MQTT_PORT`
    - `AATS_DB_PATH` (optional, default `server/database/aats.db`)
    - `AATS_USB_TIMEOUT_SEC`, `AATS_BT_TIMEOUT_SEC` as needed for your lab policy.
  - Install dependencies and start FastAPI with Uvicorn as shown in the **Setup** section.
- **Agent deployment on each lab PC**
  - Run `dist/agent_setup.exe` once to auto-configure and register auto-start on boot.
  - For manual setup, edit `student_agent/config.json` to set `lab_id`, `pc_id`, broker IP, and tracked device list.
- **Dashboard deployment**
  - Served automatically by `dist/admin_setup.exe`.
  - For manual setup, host `admin_dashboard/` from any simple HTTP server and ensure `API_BASE` in `script.js` points to the correct FastAPI server URL.
- **Time synchronization**
  - Use Windows Time service or an NTP client on all lab PCs and the server.
  - This keeps `observed_at`, `agent_time`, `received_at`, and CCTV timestamps aligned for forensic analysis.

## Limitations and future scope

- **Authentication and security**
  - Current implementation uses a **single shared admin account** configured via `AATS_ADMIN_USERNAME` / `AATS_ADMIN_PASSWORD` and a simple header token (`x-admin-token`) from the dashboard.
  - There is no per-user audit trail and MQTT/HTTP traffic are not encrypted (no TLS by default).
  - For a production deployment you would add:
    - Proper authentication (e.g. JWT-based sessions for admins).
    - Role-based access control (RBAC) distinguishing viewing vs configuration rights.
    - TLS for both MQTT and the HTTP API, plus hardened broker credentials.
- **Debounce state durability**
  - The debounce `pending` map lives in memory inside the FastAPI process.
  - If the server restarts, pending windows are forgotten and will restart from the next incoming event.
  - Future work could persist pending state into the database or an external cache (e.g. Redis) to survive restarts.
- **Scalability**
  - SQLite is ideal for a single-server lab prototype but not for a large campus deployment.
  - Future work would replace it with PostgreSQL or another central DB and scale out the FastAPI workers.
- **Agent coverage**
  - The current agent monitors a curated list of USB/Bluetooth devices.
  - Extending coverage to Wi-Fi adapters, storage devices, or system processes would require additional collectors in `student_agent/`.

## Future Works

### 1. Scoped Firewall Rules
Currently the setup EXE opens ports to the entire local subnet. Future versions should scope the firewall rules to only known lab PC IP ranges:
```
remoteip=192.******/24
```

### 2. MQTT Authentication
Add password protection to Mosquitto so only authorized agents can connect:
- Set `allow_anonymous false` in `mosquitto.conf`
- Create agent credentials: `mosquitto_passwd -c C:\mosquitto\passwd labagent`
- Add `mqtt_username` and `mqtt_password` fields to `student_agent/config.json`
- Update `student_agent/mqtt_client.py` to send credentials on connect

### 3. FastAPI Rate Limiting
Add a rate limiter to the `POST /auth/login` endpoint to prevent brute force attacks on the admin token. Use the `slowapi` library.

### 4. Dashboard Improvements
Improve the admin dashboard UI with richer filtering, charts, and a more polished visual design.

### 5. Agent exe improvements
add a feautre to auto detect the usb devices maybe have user plug in and plug out the devices.
make it so the exe can be closed and the agent still works
the auto ip detection from admin pc does not work

### 6. PC switched off
need to find solution to what if the device is stollen after the pc is turned off, maybe shift the dectection from pc to a microcontroller like arduino or esp32 or rasbery pie

### 7. Passwords
passwords need to be added to delete the exe on agent pc or the exe has to be run on the admin user which the student has no access to.