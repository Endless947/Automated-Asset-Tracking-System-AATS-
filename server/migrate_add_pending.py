"""Migration helper: apply versioned database migrations.

This script automatically applies any pending migrations that haven't been applied yet.
It tracks applied migrations in the schema_version table to allow safe re-runs.

Run this once after updating the server code to create new tables in existing databases.
"""
import sqlite3
from pathlib import Path
from database import Database
from config import settings


# Define all available migrations
# Each migration: (version, name, SQL to execute)
MIGRATIONS = [
    (
        1,
        "add_pending_window",
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
        """,
    ),
    (
        2,
        "add_schema_version",
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY,
            migration_name TEXT NOT NULL UNIQUE,
            applied_at TEXT NOT NULL
        )
        """,
    ),
]


def migrate():
    """Apply all pending migrations."""
    db = Database(settings.db_path)
    
    applied_count = 0
    for version, name, sql in MIGRATIONS:
        if db.check_migration_applied(version, name):
            print(f"[*] Migration {version} ({name}): already applied")
            continue
        
        try:
            # Execute the migration SQL
            with db._conn() as conn:
                conn.execute(sql)
                conn.commit()
            
            # Mark it as applied
            db.mark_migration_applied(version, name)
            print(f"[+] Migration {version} ({name}): applied successfully")
            applied_count += 1
        except Exception as e:
            print(f"[!] Migration {version} ({name}): FAILED — {e}")
            raise
    
    if applied_count == 0:
        print(f"[+] All migrations already applied to {settings.db_path}")
    else:
        print(f"[+] Applied {applied_count} new migration(s) to {settings.db_path}")


if __name__ == "__main__":
    migrate()

