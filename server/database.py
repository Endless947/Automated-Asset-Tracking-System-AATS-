import json
import sqlite3
from datetime import datetime, timezone, timedelta
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
                CREATE TABLE IF NOT EXISTS excluded_pcs (
                    lab_id TEXT NOT NULL,
                    pc_id TEXT NOT NULL,
                    removed_at TEXT NOT NULL,
                    PRIMARY KEY (lab_id, pc_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS excluded_devices (
                    lab_id TEXT NOT NULL,
                    pc_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    removed_at TEXT NOT NULL,
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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS pending_window (
                    lab_id TEXT NOT NULL,
                    pc_id TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    timeout_sec INTEGER NOT NULL,
                    confirmed INTEGER NOT NULL,
                    payload_json TEXT,
                    PRIMARY KEY (lab_id, pc_id, device_id)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    migration_name TEXT NOT NULL UNIQUE,
                    applied_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS labs (
                    lab_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def _is_pc_excluded(self, conn: sqlite3.Connection, lab_id: str, pc_id: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM excluded_pcs WHERE lab_id = ? AND pc_id = ?",
            (lab_id, pc_id),
        ).fetchone()
        return row is not None

    def _is_device_excluded(self, conn: sqlite3.Connection, lab_id: str, pc_id: str, device_id: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM excluded_devices WHERE lab_id = ? AND pc_id = ? AND device_id = ?",
            (lab_id, pc_id, device_id),
        ).fetchone()
        return row is not None

    def is_pc_excluded(self, lab_id: str, pc_id: str) -> bool:
        with self._conn() as conn:
            return self._is_pc_excluded(conn, lab_id, pc_id)

    def is_device_excluded(self, lab_id: str, pc_id: str, device_id: str) -> bool:
        with self._conn() as conn:
            return self._is_device_excluded(conn, lab_id, pc_id, device_id)

    def remove_pc_from_tracking(self, lab_id: str, pc_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO excluded_pcs (lab_id, pc_id, removed_at)
                VALUES (?, ?, ?)
                """,
                (lab_id, pc_id, now_iso()),
            )
            conn.execute("DELETE FROM pc_heartbeat WHERE lab_id = ? AND pc_id = ?", (lab_id, pc_id))
            conn.execute("DELETE FROM device_state_current WHERE lab_id = ? AND pc_id = ?", (lab_id, pc_id))
            conn.execute("DELETE FROM pending_window WHERE lab_id = ? AND pc_id = ?", (lab_id, pc_id))

    def remove_device_from_tracking(self, lab_id: str, pc_id: str, device_id: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO excluded_devices (lab_id, pc_id, device_id, removed_at)
                VALUES (?, ?, ?, ?)
                """,
                (lab_id, pc_id, device_id, now_iso()),
            )
            conn.execute(
                "DELETE FROM device_state_current WHERE lab_id = ? AND pc_id = ? AND device_id = ?",
                (lab_id, pc_id, device_id),
            )
            conn.execute(
                "DELETE FROM pending_window WHERE lab_id = ? AND pc_id = ? AND device_id = ?",
                (lab_id, pc_id, device_id),
            )

    def upsert_heartbeat(self, payload: Dict[str, Any]) -> None:
        with self._conn() as conn:
            if self._is_pc_excluded(conn, payload["lab_id"], payload["pc_id"]):
                return
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
            if self._is_pc_excluded(conn, payload["lab_id"], payload["pc_id"]):
                return
            if self._is_device_excluded(conn, payload["lab_id"], payload["pc_id"], payload["device_id"]):
                return
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
            if self._is_pc_excluded(conn, payload["lab_id"], payload["pc_id"]):
                return
            if self._is_device_excluded(conn, payload["lab_id"], payload["pc_id"], payload["device_id"]):
                return
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
                                    AND NOT EXISTS (
                                        SELECT 1 FROM excluded_pcs p
                                        WHERE p.lab_id = device_state_current.lab_id AND p.pc_id = device_state_current.pc_id
                                    )
                                    AND NOT EXISTS (
                                        SELECT 1 FROM excluded_devices d
                                        WHERE d.lab_id = device_state_current.lab_id
                                            AND d.pc_id = device_state_current.pc_id
                                            AND d.device_id = device_state_current.device_id
                                    )
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
                                    AND NOT EXISTS (
                                        SELECT 1 FROM excluded_pcs p
                                        WHERE p.lab_id = pc_heartbeat.lab_id AND p.pc_id = pc_heartbeat.pc_id
                                    )
                ORDER BY pc_id
                """,
                (lab_id,),
            ).fetchall()
            return [dict(row) for row in rows]

    def save_pending(self, key: tuple, item: Dict[str, Any]) -> None:
        lab_id, pc_id, device_id = key
        started_at_iso = datetime.fromtimestamp(item["started_at"], tz=timezone.utc).isoformat()
        payload_json = json.dumps(item.get("payload") or {})
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO pending_window
                (lab_id, pc_id, device_id, started_at, timeout_sec, confirmed, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (lab_id, pc_id, device_id, started_at_iso, int(item["timeout_sec"]), 1 if item.get("confirmed") else 0, payload_json),
            )

    def delete_pending(self, key: tuple) -> None:
        lab_id, pc_id, device_id = key
        with self._conn() as conn:
            conn.execute(
                """
                DELETE FROM pending_window WHERE lab_id = ? AND pc_id = ? AND device_id = ?
                """,
                (lab_id, pc_id, device_id),
            )

    def load_pending(self) -> Dict[tuple, Dict[str, Any]]:
        pending: Dict[tuple, Dict[str, Any]] = {}
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM pending_window").fetchall()
            for row in rows:
                key = (row["lab_id"], row["pc_id"], row["device_id"])
                try:
                    started_ts = datetime.fromisoformat(row["started_at"]).timestamp()
                except Exception:
                    # fallback: treat as now
                    started_ts = datetime.now(timezone.utc).timestamp()
                try:
                    payload = json.loads(row["payload_json"] or "{}")
                except Exception:
                    payload = {}
                pending[key] = {
                    "started_at": started_ts,
                    "timeout_sec": int(row["timeout_sec"]),
                    "confirmed": bool(row["confirmed"]),
                    "payload": payload,
                }
        return pending

    def mark_stale_pcs(self, lab_id: str, staleness_sec: int) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=staleness_sec)
        cutoff_iso = cutoff.isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE pc_heartbeat
                SET pc_status = 'offline_stale'
                WHERE lab_id = ? AND updated_at < ? AND pc_status = 'online'
                """,
                (lab_id, cutoff_iso),
            )

    def check_migration_applied(self, version: int, migration_name: str) -> bool:
        """Return True if the given migration has already been applied."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM schema_version WHERE version = ? AND migration_name = ?",
                (version, migration_name)
            ).fetchone()
            return row is not None

    def mark_migration_applied(self, version: int, migration_name: str) -> None:
        """Mark a migration as applied."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO schema_version (version, migration_name, applied_at)
                VALUES (?, ?, ?)
                """,
                (version, migration_name, now_iso())
            )

    def list_labs(self) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT lab_id FROM labs
                ORDER BY lab_id
                """
            ).fetchall()
            
            lab_list = []
            for row in rows:
                lab_id = row["lab_id"]
                
                # Count PCs in this lab (excluding removed ones)
                pc_count = conn.execute(
                    """
                    SELECT COUNT(DISTINCT p.pc_id)
                    FROM pc_heartbeat p
                    WHERE p.lab_id = ?
                        AND NOT EXISTS (
                            SELECT 1 FROM excluded_pcs e
                            WHERE e.lab_id = p.lab_id AND e.pc_id = p.pc_id
                        )
                    """,
                    (lab_id,)
                ).fetchone()[0]
                
                # Count devices in this lab (excluding removed ones)
                device_count = conn.execute(
                    """
                    SELECT COUNT(*)
                    FROM device_state_current d
                    WHERE d.lab_id = ?
                        AND NOT EXISTS (
                            SELECT 1 FROM excluded_pcs p
                            WHERE p.lab_id = d.lab_id AND p.pc_id = d.pc_id
                        )
                        AND NOT EXISTS (
                            SELECT 1 FROM excluded_devices e
                            WHERE e.lab_id = d.lab_id AND e.pc_id = d.pc_id AND e.device_id = d.device_id
                        )
                    """,
                    (lab_id,)
                ).fetchone()[0]

                # Get status summary
                status_counts = conn.execute(
                    """
                    SELECT current_status, COUNT(*) as cnt
                    FROM device_state_current d
                    WHERE d.lab_id = ?
                        AND NOT EXISTS (
                            SELECT 1 FROM excluded_pcs p
                            WHERE p.lab_id = d.lab_id AND p.pc_id = d.pc_id
                        )
                        AND NOT EXISTS (
                            SELECT 1 FROM excluded_devices e
                            WHERE e.lab_id = d.lab_id AND e.pc_id = d.pc_id AND e.device_id = d.device_id
                        )
                    GROUP BY current_status
                    """,
                    (lab_id,)
                ).fetchall()

                lab_list.append({
                    "lab_id": lab_id,
                    "pc_count": pc_count,
                    "device_count": device_count,
                    "status_summary": {s["current_status"]: s["cnt"] for s in status_counts}
                })
            return lab_list

    def create_lab(self, lab_id: str) -> None:
        """Create a lab entry in the labs table.
        
        This creates a lab record so the lab persists in the system even if it has no PCs.
        """
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO labs (lab_id, created_at, updated_at)
                VALUES (?, ?, ?)
                """,
                (lab_id, now_iso(), now_iso()),
            )

    def delete_lab(self, lab_id: str) -> None:
        """Delete a lab and all associated data (PCs, devices, events, etc.)."""
        with self._conn() as conn:
            # Delete the lab record
            conn.execute("DELETE FROM labs WHERE lab_id = ?", (lab_id,))
            # Delete all related data
            conn.execute("DELETE FROM device_events WHERE lab_id = ?", (lab_id,))
            conn.execute("DELETE FROM device_state_current WHERE lab_id = ?", (lab_id,))
            conn.execute("DELETE FROM pc_heartbeat WHERE lab_id = ?", (lab_id,))
            conn.execute("DELETE FROM excluded_pcs WHERE lab_id = ?", (lab_id,))
            conn.execute("DELETE FROM excluded_devices WHERE lab_id = ?", (lab_id,))
            conn.execute("DELETE FROM pending_window WHERE lab_id = ?", (lab_id,))
