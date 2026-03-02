import argparse
import sqlite3
from pathlib import Path

from config import settings


def connect():
    db_path = Path(settings.db_path)
    if not db_path.exists():
        raise SystemExit(f"Database not found at {db_path!s}. Has the server created it yet?")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def print_header(title: str) -> None:
    print("=" * len(title))
    print(title)
    print("=" * len(title))


def show_recent_events(lab_id: str | None, pc_id: str | None, limit: int) -> None:
    conn = connect()
    clauses = ["1=1"]
    params: list[object] = []

    if lab_id:
        clauses.append("lab_id = ?")
        params.append(lab_id)
    if pc_id:
        clauses.append("pc_id = ?")
        params.append(pc_id)

    sql = f"""
        SELECT received_at, lab_id, pc_id, device_id, device_type, status, severity, alert_status
        FROM device_events
        WHERE {' AND '.join(clauses)}
        ORDER BY received_at DESC
        LIMIT ?
    """
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()

    print_header(f"Recent events (limit={limit})")
    if not rows:
        print("No rows found.")
        return

    for row in rows:
        print(
            f"{row['received_at']} | lab={row['lab_id']} pc={row['pc_id']} "
            f"device={row['device_id']} type={row['device_type']} "
            f"status={row['status']} severity={row['severity']} alert={row['alert_status']}"
        )


def show_device_state(lab_id: str) -> None:
    conn = connect()
    rows = conn.execute(
        """
        SELECT lab_id, pc_id, device_id, device_type, current_status, severity, alert_status,
               pending_since, updated_at
        FROM device_state_current
        WHERE lab_id = ?
        ORDER BY pc_id, device_type, device_id
        """,
        (lab_id,),
    ).fetchall()

    print_header(f"Current device state for lab {lab_id}")
    if not rows:
        print("No rows found.")
        return

    for row in rows:
        pending = f", pending_since={row['pending_since']}" if row["pending_since"] else ""
        print(
            f"pc={row['pc_id']} device={row['device_id']} type={row['device_type']} "
            f"status={row['current_status']} severity={row['severity']} "
            f"alert={row['alert_status']}{pending} (updated_at={row['updated_at']})"
        )


def show_pc_heartbeat(lab_id: str) -> None:
    conn = connect()
    rows = conn.execute(
        """
        SELECT lab_id, pc_id, pc_status, last_seen, agent_version, updated_at
        FROM pc_heartbeat
        WHERE lab_id = ?
        ORDER BY pc_id
        """,
        (lab_id,),
    ).fetchall()

    print_header(f"PC heartbeat for lab {lab_id}")
    if not rows:
        print("No rows found.")
        return

    for row in rows:
        print(
            f"pc={row['pc_id']} status={row['pc_status']} last_seen={row['last_seen']} "
            f"agent_version={row['agent_version']} updated_at={row['updated_at']}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Quick SQLite inspection helper for AATS (for screenshots in the report)."
    )
    parser.add_argument("--lab", dest="lab_id", help="Lab ID to filter on (e.g. LAB1)")
    parser.add_argument("--pc", dest="pc_id", help="PC ID to filter events on (optional)")
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Maximum number of events to show (default: 50)",
    )
    parser.add_argument(
        "--mode",
        choices=["events", "state", "heartbeat"],
        default="events",
        help="What to inspect: events, state, or heartbeat (default: events)",
    )

    args = parser.parse_args()

    if args.mode in {"state", "heartbeat"} and not args.lab_id:
        raise SystemExit("--lab is required when using --mode state or heartbeat")

    if args.mode == "events":
        show_recent_events(args.lab_id, args.pc_id, args.limit)
    elif args.mode == "state":
        show_device_state(args.lab_id)
    else:
        show_pc_heartbeat(args.lab_id)


if __name__ == "__main__":
    main()

