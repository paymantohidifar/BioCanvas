# biocanvas/db/local_database.py
"""Local SQLite-backed drive client.

``LocalDataBase`` supports local SQLite database: one ``.db`` file per
project, storing raw experiment files (``Meta.csv``, ``Benchling.zip``, ``Eve.zip``/``Pi.zip``)
as BLOBs in a simple virtual-filesystem table. See ``database-changes.md``
at the repo root for the schema and migration notes.
"""

import os
import sqlite3
from typing import List, Optional

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT NOT NULL UNIQUE,
    parent_path TEXT NOT NULL,
    name        TEXT NOT NULL,
    is_dir      INTEGER NOT NULL DEFAULT 0,
    content     BLOB
);
CREATE INDEX IF NOT EXISTS idx_items_parent_path ON items(parent_path);
"""


class LocalDataBase:
    """Local SQLite-backed client matching the interface consumed by LocalDataClient.

    Models the raw-file drive as a single ``items`` table: each row is
    either a directory (``is_dir=1``, ``content`` NULL) or a file
    (``is_dir=0``, ``content`` holding the raw bytes), addressed by a
    ``path`` relative to the project's database file (e.g.
    ``'Exp 001 MyRun/Meta.csv'``).
    """

    def __init__(self) -> None:
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self, db_path: str) -> None:
        """Opens a connection to the project's SQLite database file.

        Args:
            db_path: Filesystem path to the project's SQLite ``.db`` file.

        Raises:
            FileNotFoundError: If ``db_path`` does not exist. SQLite would
                otherwise silently create an empty file, masking a
                misconfigured or missing database.
        """
        if not os.path.isfile(db_path):
            raise FileNotFoundError(f"SQLite database not found at '{db_path}'.")
        if self._conn is not None:
            self._conn.close()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(_SCHEMA_SQL)
        self._conn.commit()

    def list_items(self, folder_path: str) -> List[str]:
        """Lists item names directly under *folder_path*.

        Args:
            folder_path: Path of the parent folder, ``""`` for the root.
                A trailing ``/`` is stripped before matching.

        Returns:
            Sorted list of item (file or directory) names. Empty if the
            folder does not exist or has no children.
        """
        assert self._conn is not None, "LocalDataBase.connect() must be called first."
        parent_path = folder_path.rstrip("/")
        cursor = self._conn.execute(
            "SELECT name FROM items WHERE parent_path = ? ORDER BY name", (parent_path,)
        )
        return [row[0] for row in cursor.fetchall()]

    def data_content(self, item_path: str) -> bytes:
        """Returns the raw bytes stored for *item_path*.

        Args:
            item_path: Full path of the file, e.g. ``'Exp 001 MyRun/Meta.csv'``.

        Returns:
            The file's raw content.

        Raises:
            FileNotFoundError: If no file exists at ``item_path``.
        """
        assert self._conn is not None, "LocalDataBase.connect() must be called first."
        cursor = self._conn.execute(
            "SELECT content FROM items WHERE path = ? AND is_dir = 0", (item_path,)
        )
        row = cursor.fetchone()
        if row is None or row[0] is None:
            raise FileNotFoundError(f"No item found at '{item_path}'.")
        return row[0]
