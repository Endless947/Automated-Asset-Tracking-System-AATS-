import threading
import time
from datetime import datetime, timezone
from typing import Dict, Tuple

from fastapi import Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from database import Database
from mqtt_listener import MQTTListener


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


db = Database(settings.db_path)
app = FastAPI(title="AATS Server", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PendingKey = Tuple[str, str, str]
pending: Dict[PendingKey, Dict] = {}
_pending_lock = threading.Lock()
listener: MQTTListener | None = None


def get_admin_token() -> str:
    # For this student project we use a single shared admin token derived from the configured password.
    # In production this would be replaced by proper session management (JWTs, per-user accounts, etc.).
    return settings.admin_password


def require_admin(x_admin_token: str | None = Header(default=None, alias="x-admin-token")) -> None:
    expected = get_admin_token()
    if not expected:
        # If no password is configured, treat all requests as authenticated.
        return
    if x_admin_token is None or x_admin_token != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authentication required")


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResult(BaseModel):
    token: str


def severity_for(status: str) -> str:
    if status == "CONNECTED":
        return "OK"
    if status == "WEAK_SIGNAL":
        return "WARNING"
    return "WARNING"


def timeout_for(payload: Dict) -> int:
    if payload.get("device_type") == "usb" and payload.get("status") == "MISSING":
        return settings.usb_missing_timeout_sec
    if payload.get("device_type") == "bluetooth" and payload.get("status") in {"MISSING", "WEAK_SIGNAL"}:
        return settings.bluetooth_missing_timeout_sec
    return 0


def handle_status(payload: Dict) -> None:
    db.upsert_heartbeat(payload)


def handle_event(payload: Dict) -> None:
    key = (payload["lab_id"], payload["pc_id"], payload["device_id"])
    status = payload["status"]

    if status == "CONNECTED":
        with _pending_lock:
            pending_event = pending.pop(key, None)

        db.upsert_device_state(payload, severity="OK", alert_status="CLOSED", pending_since=None)
        db.insert_event(payload, severity="OK", alert_status="CLOSED")

        if pending_event:
            db.insert_event(
                payload,
                severity="WARNING",
                alert_status="CLOSED",
                details={"resolved_pending_started_at": pending_event["started_at"], "reason": "glitch_resolved"},
            )
        return

    timeout_sec = timeout_for(payload)
    if timeout_sec <= 0:
        db.upsert_device_state(payload, severity=severity_for(status), alert_status="OPEN", pending_since=None)
        db.insert_event(payload, severity=severity_for(status), alert_status="OPEN")
        return

    with _pending_lock:
        if key not in pending:
            pending[key] = {
                "started_at": time.time(),
                "timeout_sec": timeout_sec,
                "payload": payload,
                "confirmed": False,
            }
        pending_state = pending[key]
        pending_since = datetime.fromtimestamp(pending_state["started_at"], tz=timezone.utc).isoformat()

    db.upsert_device_state(payload, severity="WARNING", alert_status="PENDING", pending_since=pending_since)


def pending_watcher() -> None:
    while True:
        now = time.time()
        to_confirm: list[tuple[PendingKey, Dict]] = []

        with _pending_lock:
            for key, item in pending.items():
                if item["confirmed"]:
                    continue
                if now - item["started_at"] >= item["timeout_sec"]:
                    item["confirmed"] = True
                    to_confirm.append((key, item))

        for _, item in to_confirm:
            payload = item["payload"]
            db.upsert_device_state(payload, severity="CRITICAL", alert_status="OPEN", pending_since=None)
            db.insert_event(payload, severity="CRITICAL", alert_status="OPEN", details={"debounce_seconds": item["timeout_sec"]})

        time.sleep(1)


@app.on_event("startup")
def on_startup() -> None:
    global listener
    listener = MQTTListener(
        broker=settings.mqtt_broker,
        port=settings.mqtt_port,
        on_status=handle_status,
        on_event=handle_event,
    )
    listener.start()
    threading.Thread(target=pending_watcher, daemon=True).start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    if listener is not None:
        listener.stop()


@app.get("/health")
def health() -> Dict[str, str]:
    return {"status": "ok", "time": now_iso()}


@app.post("/auth/login", response_model=LoginResult)
def login(body: LoginRequest) -> LoginResult:
    if body.username != settings.admin_username or body.password != settings.admin_password:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return LoginResult(token=get_admin_token())


@app.get("/labs/{lab_id}/devices")
def get_lab_devices(lab_id: str, _: None = Depends(require_admin)):
    return db.list_lab_devices(lab_id)


@app.get("/labs/{lab_id}/pcs")
def get_lab_pcs(lab_id: str, _: None = Depends(require_admin)):
    return db.list_pc_heartbeat(lab_id)


@app.get("/alerts")
def get_alerts(
    from_time: str | None = Query(default=None, alias="from"),
    to_time: str | None = Query(default=None, alias="to"),
    severity: str | None = None,
    status: str | None = None,
) -> list[Dict]:
    _ = require_admin()  # explicit call for dependency when used outside FastAPI injection
    if severity is None:
        critical = db.list_events(severity="CRITICAL", alert_status=status, from_time=from_time, to_time=to_time, limit=500)
        warning = db.list_events(severity="WARNING", alert_status=status, from_time=from_time, to_time=to_time, limit=500)
        return sorted(critical + warning, key=lambda x: x["received_at"], reverse=True)

    return db.list_events(severity=severity, alert_status=status, from_time=from_time, to_time=to_time, limit=500)


@app.get("/events")
def get_events(
    lab_id: str | None = None,
    pc_id: str | None = None,
    device_id: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    from_time: str | None = Query(default=None, alias="from"),
    to_time: str | None = Query(default=None, alias="to"),
    limit: int = 200,
) -> list[Dict]:
    _ = require_admin()
    return db.list_events(
        lab_id=lab_id,
        pc_id=pc_id,
        device_id=device_id,
        severity=severity,
        alert_status=status,
        from_time=from_time,
        to_time=to_time,
        limit=max(1, min(limit, 1000)),
    )
