import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS device_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT UNIQUE,
                    lab_id TEXT NOT NULL,
                    pc_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    device_label TEXT,
                    device_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    alert_status TEXT NOT NULL,
                    rssi INTEGER,
                    observed_at TEXT,
                    agent_time TEXT,
                    received_at TEXT NOT NULL,
                    source TEXT,
                    details_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS device_state_current (
                    lab_id TEXT NOT NULL,
                    pc_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    device_label TEXT,
                    device_type TEXT NOT NULL,
                    current_status TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    alert_status TEXT NOT NULL,
                    rssi INTEGER,
                    pending_since TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (lab_id, pc_id, device_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pc_heartbeat (
                    lab_id TEXT NOT NULL,
                    pc_id TEXT NOT NULL,
                    pc_status TEXT NOT NULL,
                    last_seen TEXT,
                    agent_version TEXT,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (lab_id, pc_id)
                )
                """
            )

    def upsert_heartbeat(self, payload: Dict[str, Any]) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO pc_heartbeat (lab_id, pc_id, pc_status, last_seen, agent_version, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(lab_id, pc_id) DO UPDATE SET
                    pc_status=excluded.pc_status,
                    last_seen=excluded.last_seen,
                    agent_version=excluded.agent_version,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["lab_id"],
                    payload["pc_id"],
                    payload["pc_status"],
                    payload.get("last_seen"),
                    payload.get("agent_version"),
                    now_iso(),
                ),
            )

    def upsert_device_state(
        self,
        payload: Dict[str, Any],
        severity: str,
        alert_status: str,
        pending_since: Optional[str],
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO device_state_current (
                    lab_id, pc_id, device_id, device_label, device_type,
                    current_status, severity, alert_status, rssi, pending_since, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(lab_id, pc_id, device_id) DO UPDATE SET
                    device_label=excluded.device_label,
                    device_type=excluded.device_type,
                    current_status=excluded.current_status,
                    severity=excluded.severity,
                    alert_status=excluded.alert_status,
                    rssi=excluded.rssi,
                    pending_since=excluded.pending_since,
                    updated_at=excluded.updated_at
                """,
                (
                    payload["lab_id"],
                    payload["pc_id"],
                    payload["device_id"],
                    payload.get("device_label"),
                    payload["device_type"],
                    payload["status"],
                    severity,
                    alert_status,
                    payload.get("rssi"),
                    pending_since,
                    now_iso(),
                ),
            )

    def insert_event(self, payload: Dict[str, Any], severity: str, alert_status: str, details: Optional[Dict[str, Any]] = None) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO device_events (
                    event_id, lab_id, pc_id, device_id, device_label, device_type,
                    status, severity, alert_status, rssi, observed_at, agent_time,
                    received_at, source, details_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("event_id"),
                    payload["lab_id"],
                    payload["pc_id"],
                    payload["device_id"],
                    payload.get("device_label"),
                    payload["device_type"],
                    payload["status"],
                    severity,
                    alert_status,
                    payload.get("rssi"),
                    payload.get("observed_at"),
                    payload.get("agent_time"),
                    now_iso(),
                    payload.get("source"),
                    json.dumps(details or {}),
                ),
            )

    def list_lab_devices(self, lab_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM device_state_current
                WHERE lab_id = ?
                ORDER BY pc_id, device_type, device_id
                """,
                (lab_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def list_events(
        self,
        lab_id: Optional[str] = None,
        pc_id: Optional[str] = None,
        device_id: Optional[str] = None,
        severity: Optional[str] = None,
        alert_status: Optional[str] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        clauses = ["1=1"]
        params: List[Any] = []

        if lab_id:
            clauses.append("lab_id = ?")
            params.append(lab_id)
        if pc_id:
            clauses.append("pc_id = ?")
            params.append(pc_id)
        if device_id:
            clauses.append("device_id = ?")
            params.append(device_id)
        if severity:
            clauses.append("severity = ?")
            params.append(severity)
        if alert_status:
            clauses.append("alert_status = ?")
            params.append(alert_status)
        if from_time:
            clauses.append("received_at >= ?")
            params.append(from_time)
        if to_time:
            clauses.append("received_at <= ?")
            params.append(to_time)

        sql = f"""
            SELECT * FROM device_events
            WHERE {' AND '.join(clauses)}
            ORDER BY received_at DESC
            LIMIT ?
        """
        params.append(limit)

        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [dict(row) for row in rows]

    def list_pc_heartbeat(self, lab_id: str) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT *
                FROM pc_heartbeat
                WHERE lab_id = ?
                ORDER BY pc_id
                """,
                (lab_id,),
            ).fetchall()
            return [dict(row) for row in rows]
