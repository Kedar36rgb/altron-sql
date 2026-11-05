import sqlite3

import pytest

from engine.database import load_file_to_sqlite
from engine.security import is_safe_sql


def test_safe_select():
    assert is_safe_sql("SELECT * FROM user_data WHERE age > 20")

def test_union_allowed():
    assert is_safe_sql("SELECT a FROM user_data UNION SELECT b FROM user_data")

@pytest.mark.parametrize("q", [
    "DROP TABLE user_data",
    "UPDATE user_data SET age = 0",
    "SELECT 1; DROP TABLE user_data", # multi-statement
    "WITH x AS (DELETE FROM user_data RETURNING *) SELECT * FROM x",
    "PRAGMA writable_schema = ON",
    "ATTACH DATABASE 'x.db' AS x",
    "SELECT load_extension('evil')",
    "DELETE FROM user_data",
])
def test_blocked(q):
    assert is_safe_sql(q) is False

def test_db_layer_blocks_writes_even_if_validator_bypassed():
    """Tests that the SQLite authorizer blocks writes even if the AST validator fails."""
    conn, _, _ = load_file_to_sqlite(b"a,b\n1,2\n", "t.csv")
    with pytest.raises(sqlite3.Error):
        conn.execute("DELETE FROM user_data")

from types import SimpleNamespace as S

from engine.llm import generate_sql


def test_self_healing():
    # 1. Load a dummy DB
    conn, schema, _ = load_file_to_sqlite(b"a,b\n1,2\n", "t.csv")
    
    # 2. Mock the LLM to return a bad column, then a good column
    replies = iter([
        "SELECT nope FROM user_data",  # Bad (fails execution because 'nope' doesn't exist)
        "SELECT a FROM user_data"      # Good (passes)
    ])
    
    class Fake:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    return S(choices=[S(message=S(content=next(replies)))])
                    
    # 3. Run generate_sql with the fake client
    r = generate_sql("q", schema, conn, client=Fake())
    
    # 4. Assert it took 2 attempts and succeeded on the 2nd
    assert len(r.attempts) == 2
    assert r.attempts[0]["error"] is not None
    assert r.attempts[1]["error"] is None