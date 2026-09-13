from __future__ import annotations
import json, os, sqlite3, shutil, hashlib, re
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timezone
import re

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
UMVWA_ENV = os.environ.get("UMVWA_ENV", "development").strip().lower()

if UMVWA_ENV == "production" and not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is required when UMVWA_ENV=production; refusing to start with local SQLite")

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get('UMVWA_DB_PATH', str(ROOT / 'umvwa.sqlite3'))).expanduser().resolve()
BACKUP_ROOT = Path(os.environ.get('UMVWA_BACKUP_DIR', str(ROOT / 'backups'))).expanduser().resolve()

def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def connect():
    """Yield a transactional database connection.

    SQLite remains the default for local/test runs. Setting DATABASE_URL switches
    the same application contract to PostgreSQL (including Supabase).
    """
    if DATABASE_URL:
        import psycopg
        from psycopg.rows import dict_row

        class _CompatCursor:
            def __init__(self, cursor): self._cursor = cursor
            def execute(self, sql, params=None):
                sql = sql.replace('?', '%s')
                return self._cursor.execute(sql, params)
            def executemany(self, sql, params_seq):
                sql = sql.replace('?', '%s')
                return self._cursor.executemany(sql, params_seq)
            def fetchone(self): return self._cursor.fetchone()
            def fetchall(self): return self._cursor.fetchall()
            @property
            def rowcount(self): return self._cursor.rowcount

        class _CompatConnection:
            def __init__(self, conn): self._conn = conn
            def execute(self, sql, params=None):
                cur = self._conn.cursor()
                return _CompatCursor(cur).execute(sql, params)
            def executemany(self, sql, params_seq):
                cur = self._conn.cursor()
                return _CompatCursor(cur).executemany(sql, params_seq)
            def commit(self): return self._conn.commit()
            def rollback(self): return self._conn.rollback()
            def close(self): return self._conn.close()

        raw = psycopg.connect(DATABASE_URL, row_factory=dict_row)
        conn = _CompatConnection(raw)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH, timeout=10.0)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA synchronous=NORMAL')
    c.execute('PRAGMA busy_timeout=10000')
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()

def _postgres_executescript(conn, script: str):
    """Execute a PostgreSQL schema script without corrupting SQL statements.

    Splitting on every semicolon is unsafe because semicolons may occur inside
    comments, quoted strings, or PostgreSQL dollar-quoted bodies. This scanner
    only treats a semicolon as a statement terminator while in normal SQL mode.
    """
    statements = []
    start = 0
    i = 0
    n = len(script)
    state = "normal"
    dollar_tag = None

    while i < n:
        ch = script[i]
        nxt = script[i + 1] if i + 1 < n else ""

        if state == "normal":
            if ch == "-" and nxt == "-":
                state = "line_comment"
                i += 2
                continue
            if ch == "/" and nxt == "*":
                state = "block_comment"
                i += 2
                continue
            if ch == "'":
                state = "single_quote"
                i += 1
                continue
            if ch == '"':
                state = "double_quote"
                i += 1
                continue
            if ch == "$":
                match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", script[i:])
                if match:
                    dollar_tag = match.group(0)
                    state = "dollar_quote"
                    i += len(dollar_tag)
                    continue
            if ch == ";":
                statement = script[start:i].strip()
                if statement:
                    statements.append(statement)
                start = i + 1
            i += 1
            continue

        if state == "line_comment":
            if ch in "\r\n":
                state = "normal"
            i += 1
            continue

        if state == "block_comment":
            if ch == "*" and nxt == "/":
                state = "normal"
                i += 2
            else:
                i += 1
            continue

        if state == "single_quote":
            if ch == "'" and nxt == "'":
                i += 2
            elif ch == "'":
                state = "normal"
                i += 1
            else:
                i += 1
            continue

        if state == "double_quote":
            if ch == '"' and nxt == '"':
                i += 2
            elif ch == '"':
                state = "normal"
                i += 1
            else:
                i += 1
            continue

        if state == "dollar_quote":
            if script.startswith(dollar_tag, i):
                i += len(dollar_tag)
                state = "normal"
            else:
                i += 1

    statement = script[start:].strip()
    if statement:
        statements.append(statement)

    for statement in statements:
        conn.execute(statement)

def _is_postgres() -> bool:
    return bool(DATABASE_URL)


def init_db():
    schema = Path(__file__).resolve().parents[1] / 'supabase_schema.sql'
    if _is_postgres():
        with connect() as c:
            _postgres_executescript(c, schema.read_text())
        return

    with connect() as c:
        sqlite_schema = schema.read_text()
        # The shared schema also contains PostgreSQL-only RLS hardening statements.
        # Keep SQLite as a faithful local/test fallback without attempting to execute
        # PostgreSQL syntax in SQLite.
        sqlite_schema = re.sub(r'^\s*alter table [a-zA-Z_][a-zA-Z0-9_]* enable row level security;\s*$', '', sqlite_schema, flags=re.MULTILINE | re.IGNORECASE)
        c.executescript(sqlite_schema.replace('create table if not exists', 'CREATE TABLE IF NOT EXISTS').replace('create index if not exists', 'CREATE INDEX IF NOT EXISTS'))
        cols = {r['name'] for r in c.execute("PRAGMA table_info(voice_notes)").fetchall()}
        if 'transcription_status' not in cols:
            c.execute("ALTER TABLE voice_notes ADD COLUMN transcription_status TEXT NOT NULL DEFAULT 'PENDING_PROVIDER'")


def seed_demo():
    with connect() as c:
        if c.execute('SELECT 1 FROM organizations LIMIT 1').fetchone(): return
        now = utcnow_iso()
        org, david, sarah, outcome, thread = 'org_demo','person_david','person_sarah','out_demo','thread_abc'
        c.execute('INSERT INTO organizations VALUES (?,?)',(org,'UMVWA Demo Workspace'))
        c.executemany('INSERT INTO people VALUES (?,?,?,?)',[(david,org,'David','EXECUTIVE'),(sarah,org,'Sarah','ASSISTANT')])
        c.execute('INSERT INTO outcomes VALUES (?,?,?)',(outcome,org,'Prepare and complete the ABC Limited quotation before the client meeting.'))
        c.execute('INSERT INTO threads VALUES (?,?,?,?)',(thread,org,outcome,'ABC Limited — Quotation & Friday Meeting'))
        c.execute('INSERT INTO capacity VALUES (?,?,?,?,?)',('cap_demo',org,sarah,'AVAILABLE',now))
        from .auth import create_user
        create_user(c, david, org, 'David', 'EXECUTIVE', 'demo-david')
        create_user(c, sarah, org, 'Sarah', 'ASSISTANT', 'demo-sarah')
        c.commit()


def database_integrity_check() -> bool:
    if _is_postgres():
        with connect() as c:
            row = c.execute("SELECT current_database() AS database_name").fetchone()
        return bool(row and row.get('database_name'))
    with connect() as c:
        row = c.execute("PRAGMA integrity_check").fetchone()
    return bool(row and row[0] == 'ok')

def backup_database() -> Path:
    """Create and verify a consistent SQLite backup without exposing the DB file itself.

    Hosted PostgreSQL backups are provider-managed and must not be treated as a
    local SQLite file backup.
    """
    if _is_postgres():
        raise RuntimeError('local SQLite backup is unavailable when PostgreSQL is active; use provider-managed database backups')
    BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    destination = BACKUP_ROOT / f'umvwa-{stamp}.sqlite3'
    source = sqlite3.connect(DB_PATH)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
        target.execute('PRAGMA integrity_check').fetchone()
        target.commit()
    finally:
        target.close(); source.close()
    # Refuse to return an unverified backup.
    check = sqlite3.connect(destination)
    try:
        row = check.execute('PRAGMA integrity_check').fetchone()
        if not row or row[0] != 'ok':
            raise RuntimeError('backup integrity check failed')
    finally:
        check.close()
    return destination

def backup_metadata(path: Path) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {'filename': path.name, 'bytes': path.stat().st_size, 'sha256': digest}
