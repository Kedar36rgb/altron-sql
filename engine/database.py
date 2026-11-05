import io
import os
import re
import sqlite3
import time

import pandas as pd

# Default to 1 GB, can be overridden in .env
MAX_BYTES = int(os.getenv("MAX_UPLOAD_MB", "1024")) * 1024 * 1024

def clean_columns(cols):
    seen, out = {}, []
    for i, c in enumerate(cols):
        name = re.sub(r"\W+", "_", str(c).strip()).strip("_") or f"col_{i}"
        if name[0].isdigit():
            name = f"c_{name}"
        key = name.lower()
        if key in seen:
            seen[key] += 1
            name = f"{name}_{seen[key]}"
        else:
            seen[key] = 0
        out.append(name)
    return out

def build_schema(df: pd.DataFrame) -> str:
    lines = [f"Table user_data ({len(df)} rows):"]
    for col in df.columns:
        s = df[col].dropna()
        kind = {"i": "INTEGER", "u": "INTEGER", "f": "REAL"}.get(df[col].dtype.kind, "TEXT")
        
        if kind == "TEXT":
            uniq = s.astype(str).unique()
            shown = uniq[:12] if len(uniq) <= 12 else uniq[:3]
            ex = ", ".join(repr(v[:30]) for v in shown)
            lines.append(f"- {col} (TEXT), values like: {ex}")
        else:
            if s.empty:
                lines.append(f"- {col} ({kind}), empty")
            else:
                lines.append(f"- {col} ({kind}), range {s.min()} to {s.max()}")
    return "\n".join(lines)

def lock_down(conn: sqlite3.Connection):
    conn.execute("PRAGMA query_only = ON")
    allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, 33}

    def authorizer(action, arg1, arg2, db, source):
        if action == sqlite3.SQLITE_FUNCTION and str(arg2).lower() == "load_extension":
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY

    conn.set_authorizer(authorizer)

def load_file_to_sqlite(file_bytes: bytes, filename: str):
    if len(file_bytes) > MAX_BYTES:
        raise ValueError(f"File too large ({MAX_BYTES // (1024*1024)} MB max).")
        
    name = filename.lower()
    
    if name.endswith(".csv"):
        try:
            df = pd.read_csv(io.BytesIO(file_bytes))
        except UnicodeDecodeError:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding="latin-1")
    elif name.endswith(".xlsx"):
        df = pd.read_excel(io.BytesIO(file_bytes))
    else:
        raise ValueError("Unsupported file type. Please upload CSV or Excel.")
        
    df = df.dropna(how="all").dropna(axis=1, how="all")
    df.columns = clean_columns(df.columns)

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    # Use chunksize to handle large files safely
    df.to_sql("user_data", conn, index=False, chunksize=50_000)
    
    schema = build_schema(df)
    lock_down(conn) 
    
    return conn, schema, df.head(10)

def run_query(conn, sql, max_rows=1000, timeout_s=5):
    deadline = time.monotonic() + timeout_s
    conn.set_progress_handler(lambda: time.monotonic() > deadline, 10_000)
    try:
        cur = conn.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(max_rows + 1)
    finally:
        conn.set_progress_handler(None, 0)
    return pd.DataFrame(rows[:max_rows], columns=cols), len(rows) > max_rows