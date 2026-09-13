from pathlib import Path
import app.db as db


def test_connect_context_closes_connection_and_commits(tmp_path):
    original = db.DB_PATH
    db.DB_PATH = tmp_path / 'hygiene.sqlite3'
    try:
        db.init_db()
        with db.connect() as c:
            c.execute("INSERT INTO organizations VALUES (?,?)", ('org_hygiene', 'Hygiene'))
        with db.connect() as c:
            assert c.execute("SELECT name FROM organizations WHERE id=?", ('org_hygiene',)).fetchone()['name'] == 'Hygiene'
    finally:
        db.DB_PATH = original
