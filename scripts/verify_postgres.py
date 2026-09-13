"""Verify a real UMVWA PostgreSQL connection without printing credentials."""
from __future__ import annotations

import os
import sys

if not os.environ.get("DATABASE_URL", "").strip():
    raise SystemExit("DATABASE_URL is not set; refusing to run a hosted PostgreSQL check.")

from app import db

EXPECTED_TABLES = {
    "organizations", "users", "sessions", "people", "outcomes", "threads",
    "work_items", "authorities", "decisions", "evidence", "history", "capacity",
    "notifications", "contexts", "dependencies", "communications", "meetings",
    "artifacts", "object_links", "recommendations", "contact_details",
    "person_relationships", "voice_notes", "realtime_events", "user_preferences",
    "workspace_configuration",
}


def main() -> int:
    db.init_db()
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        ).fetchall()
        actual = {row["table_name"] for row in rows}
        missing = EXPECTED_TABLES - actual
        if missing:
            print("POSTGRES_SCHEMA_FAIL")
            print("Missing tables:", ", ".join(sorted(missing)))
            return 1
        db_name = conn.execute("SELECT current_database() AS database_name").fetchone()["database_name"]
        conn.execute("SELECT 1 AS ok")
    print("POSTGRES_CONNECTION_PASS")
    print(f"database={db_name}")
    print(f"tables={len(EXPECTED_TABLES)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
