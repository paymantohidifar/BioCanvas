# biocanvas/db/schema.py
"""Schema creation for the BioCanvas raw-data SQLite database."""
import sqlite3
from pathlib import Path

_SCHEMA_PATH: Path = Path(__file__).parent / 'schema.sql'


def create_schema(conn: sqlite3.Connection) -> None:
    """Creates all BioCanvas tables on the given connection, if not already present.

    Args:
        conn: Open SQLite connection.
    """
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.commit()


def connect(db_path: str = ':memory:') -> sqlite3.Connection:
    """Opens a SQLite connection with foreign keys enabled and the schema ensured.

    Args:
        db_path: Path to the SQLite database file, or ':memory:' for an
            in-memory database.

    Returns:
        An open connection with the BioCanvas schema created.
    """
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA foreign_keys = ON')
    create_schema(conn)
    return conn
