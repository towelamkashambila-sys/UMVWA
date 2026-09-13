from pathlib import Path

from app.db import _postgres_executescript


class FakeConnection:
    def __init__(self):
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)


def test_postgres_schema_parser_ignores_semicolons_in_comments_quotes_and_dollar_quotes():
    script = """
    -- Defense-in-depth: direct backend access uses the server connection; the Supabase Data API must not
    CREATE TABLE example_a (name TEXT DEFAULT 'a;b');
    /* block comment; semicolon must not terminate */
    CREATE TABLE example_b (name TEXT);
    DO $body$
    BEGIN
        PERFORM 1;
        PERFORM 2;
    END
    $body$;
    """

    conn = FakeConnection()
    _postgres_executescript(conn, script)

    assert len(conn.statements) == 3
    assert "Defense-in-depth" in conn.statements[0]
    assert "a;b" in conn.statements[0]
    assert "block comment; semicolon must not terminate" in conn.statements[1]
    assert "PERFORM 1;" in conn.statements[2]
    assert "PERFORM 2;" in conn.statements[2]
