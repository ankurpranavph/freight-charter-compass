"""Create tables from schema.sql. Safe to re-run (CREATE TABLE IF NOT EXISTS)."""
from pathlib import Path
from app.db.connection import get_connection

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def init_db() -> None:
    conn = get_connection()
    try:
        conn.executescript(SCHEMA_PATH.read_text())
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Schema applied.")
