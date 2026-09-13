import importlib
import os


def test_postgres_backup_boundary(monkeypatch):
    import app.db as db
    monkeypatch.setattr(db, 'DATABASE_URL', 'postgresql://redacted@host/db')
    try:
        db.backup_database()
    except RuntimeError as exc:
        assert 'provider-managed database backups' in str(exc)
    else:
        raise AssertionError('PostgreSQL must not use the local SQLite backup path')


def test_compose_persists_runtime_state_under_volume():
    from pathlib import Path
    compose = Path(__file__).resolve().parents[1] / 'docker-compose.yml'
    text = compose.read_text()
    assert 'UMVWA_DB_PATH: /data/umvwa.sqlite3' in text
    assert 'UMVWA_BACKUP_DIR: /data/backups' in text
    assert 'UMVWA_VOICE_DIR: /data/voice' in text


def test_supabase_schema_enables_rls_on_all_application_tables():
    from pathlib import Path
    schema = Path(__file__).resolve().parents[1] / 'supabase_schema.sql'
    text = schema.read_text().lower()
    expected = [
        'organizations','users','sessions','people','outcomes','threads','work_items',
        'authorities','decisions','evidence','history','capacity','notifications','contexts',
        'dependencies','communications','meetings','artifacts','object_links','recommendations',
        'contact_details','person_relationships','voice_notes','realtime_events',
        'user_preferences','workspace_configuration'
    ]
    for table in expected:
        assert f'alter table {table} enable row level security;' in text


def test_supabase_schema_does_not_contain_connection_credentials():
    from pathlib import Path
    import re
    text = (Path(__file__).resolve().parents[1] / 'supabase_schema.sql').read_text()
    assert 'postgresql://' not in text.lower()
    assert not re.search(r'password\s*[=:]', text, re.I)


def test_production_requires_database_url(monkeypatch):
    import subprocess, sys, os
    env = os.environ.copy()
    env.pop("DATABASE_URL", None)
    env["UMVWA_ENV"] = "production"
    code = "import app.db"
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "DATABASE_URL is required when UMVWA_ENV=production" in result.stderr
