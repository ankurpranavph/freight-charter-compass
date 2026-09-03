"""
SQLite connection helper.

Decisions logged here (full rationale in DECISIONS.md):
- Plain sqlite3 (stdlib), not a SQLAlchemy ORM — the schema is still two
  tables; revisit only if Module 6's optimizer needs joins complex enough
  that hand-written SQL becomes the harder path.
- journal_mode=MEMORY + synchronous=OFF — some networked/virtual dev
  filesystems (encountered on this project via a remote folder-sync bridge)
  reject SQLite's default rollback-journal file locking with
  "disk I/O error". MEMORY journal mode avoids creating that on-disk journal
  file. This trades strict crash-durability for portability and speed, which
  is the right call for a hackathon demo database that gets rebuilt from
  seed JSON on every startup anyway — never do this for a system where
  losing the last transaction on a crash matters.
"""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "freight.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = MEMORY;")
    conn.execute("PRAGMA synchronous = OFF;")
    return conn


@contextmanager
def db_session():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
