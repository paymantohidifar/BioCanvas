"""Tests for the SQLite-backed biocanvas.db.local_database.LocalDataBase and biocanvas.utils.io.LocalDataClient."""

import sqlite3
from pathlib import Path

import pytest

from biocanvas.db.local_database import LocalDataBase, _SCHEMA_SQL
from biocanvas.utils.io import LocalDataClient


def _build_db(db_path: Path) -> None:
    """Creates a small SQLite db mirroring one experiment folder with two files."""
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA_SQL)
    conn.executemany(
        "INSERT INTO items (path, parent_path, name, is_dir, content) VALUES (?, ?, ?, ?, ?)",
        [
            ("Exp 001 MyRun", "", "Exp 001 MyRun", 1, None),
            ("Exp 001 MyRun/Meta.csv", "Exp 001 MyRun", "Meta.csv", 0, b"meta-content"),
            (
                "Exp 001 MyRun/Benchling.zip",
                "Exp 001 MyRun",
                "Benchling.zip",
                0,
                b"bench-content",
            ),
        ],
    )
    conn.commit()
    conn.close()


class TestLocalDataBase:
    def test_connect_missing_file_raises(self, tmp_path: Path):
        drive = LocalDataBase()
        with pytest.raises(FileNotFoundError):
            drive.connect(str(tmp_path / "does_not_exist.db"))

    def test_list_items_returns_names(self, tmp_path: Path):
        db_path = tmp_path / "helix.db"
        _build_db(db_path)
        drive = LocalDataBase()
        drive.connect(str(db_path))

        assert drive.list_items("") == ["Exp 001 MyRun"]
        assert drive.list_items("Exp 001 MyRun") == ["Benchling.zip", "Meta.csv"]
        assert drive.list_items("Exp 001 MyRun/") == ["Benchling.zip", "Meta.csv"]

    def test_list_items_empty_folder_returns_empty_list(self, tmp_path: Path):
        db_path = tmp_path / "helix.db"
        _build_db(db_path)
        drive = LocalDataBase()
        drive.connect(str(db_path))

        assert drive.list_items("Nonexistent Folder") == []

    def test_data_content_returns_bytes(self, tmp_path: Path):
        db_path = tmp_path / "helix.db"
        _build_db(db_path)
        drive = LocalDataBase()
        drive.connect(str(db_path))

        assert drive.data_content("Exp 001 MyRun/Meta.csv") == b"meta-content"

    def test_data_content_missing_file_raises(self, tmp_path: Path):
        db_path = tmp_path / "helix.db"
        _build_db(db_path)
        drive = LocalDataBase()
        drive.connect(str(db_path))

        with pytest.raises(FileNotFoundError):
            drive.data_content("Exp 001 MyRun/Eve.zip")

    def test_connect_reopens_and_closes_prior_connection(self, tmp_path: Path):
        db_path = tmp_path / "helix.db"
        _build_db(db_path)
        drive = LocalDataBase()
        drive.connect(str(db_path))
        first_conn = drive._conn
        drive.connect(str(db_path))

        assert drive._conn is not first_conn
        with pytest.raises(sqlite3.ProgrammingError):
            first_conn.execute("SELECT 1")


class TestLocalDataClient:
    def test_end_to_end_matches_data_service_call_pattern(self, tmp_path: Path):
        db_path = tmp_path / "helix.db"
        _build_db(db_path)

        sp = LocalDataClient()
        sp.connect("Project Helix", str(db_path))

        exp_names = [
            item for item in sp.get_item_names() if item.lower().startswith("exp")
        ]
        assert exp_names == ["Exp 001 MyRun"]

        files = sp.get_item_names(exp_names[0] + "/")
        assert files == ["Benchling.zip", "Meta.csv"]

        assert sp.load_data(exp_names[0] + "/Meta.csv") == b"meta-content"

    def test_load_data_missing_item_raises_file_not_found(self, tmp_path: Path):
        db_path = tmp_path / "helix.db"
        _build_db(db_path)

        sp = LocalDataClient()
        sp.connect("Project Helix", str(db_path))

        with pytest.raises(FileNotFoundError):
            sp.load_data("Exp 001 MyRun/Eve.zip")

    def test_caches_are_populated_and_cleared_on_reconnect(self, tmp_path: Path):
        db_path = tmp_path / "helix.db"
        _build_db(db_path)

        sp = LocalDataClient()
        sp.connect("Project Helix", str(db_path))
        sp.get_item_names()
        sp.load_data("Exp 001 MyRun/Meta.csv")
        assert sp._list_cache
        assert sp._data_cache

        sp.connect("Project Helix", str(db_path))
        assert sp._list_cache == {}
        assert sp._data_cache == {}
