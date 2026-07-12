# SQLite backend for raw experiment data

## Why

`biocanvas/utils/drive.py`'s `MSDrive` was a placeholder left behind when
the project was extracted from the `bifrost` monorepo: every method raised
`NotImplementedError` because the real SharePoint client
(`bifrost.auth.drive.MSDrive`) lived in a now-unavailable external repo.
This change replaces that placeholder with a real, local SQLite-backed
implementation, restoring the ability to fetch raw experiment files
(`Meta.csv`, `Benchling.zip`, `Eve.zip`/`Pi.zip`) without any external
service.

## Design

- **One SQLite `.db` file per project.** Each project's `config.yaml`
  points at its own database file via the `sharepoint_data_dir` key (kept
  under that name — see "Naming" below).
- **Public interface unchanged.** `biocanvas.utils.io.SharePoint` still
  exposes `connect(project_name, data_dir)`, `get_item_names(item="")`, and
  `load_data(item)` with the same signatures and caching behavior as
  before. `biocanvas.data_service.DataService` needed **no call-site
  changes** — it calls `self.sharepoint.connect(...)`,
  `self.sharepoint.get_item_names(...)`, and `self.sharepoint.load_data(...)`
  exactly as it did against the SharePoint backend.
- **Virtual filesystem in a single table.** Experiment folders and their
  raw files are modeled as rows in one `items` table, addressed by a
  `path` relative to the project's database (e.g.
  `'Exp 001 MyRun/Meta.csv'`), mirroring the folder structure the old
  SharePoint drive exposed.

### Schema

```sql
CREATE TABLE IF NOT EXISTS items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    path        TEXT NOT NULL UNIQUE,   -- e.g. 'Exp 001 MyRun/Meta.csv'
    parent_path TEXT NOT NULL,          -- '' for top-level, 'Exp 001 MyRun' for children
    name        TEXT NOT NULL,          -- 'Meta.csv' / 'Exp 001 MyRun'
    is_dir      INTEGER NOT NULL DEFAULT 0,
    content     BLOB                    -- NULL for directories
);
CREATE INDEX IF NOT EXISTS idx_items_parent_path ON items(parent_path);
```

`MSDrive.connect()` runs this DDL with `CREATE TABLE IF NOT EXISTS` on every
connect, so it is a no-op against an already-populated database and lets
tests build a throwaway `.db` from scratch with no setup step.

Top-level experiment directories have `parent_path = ''`. Files within an
experiment directory have `parent_path` equal to that experiment's `path`
(no trailing slash). Directory rows have `is_dir = 1` and `content = NULL`;
file rows have `is_dir = 0` and their raw bytes in `content`.

### `MSDrive` (`biocanvas/utils/drive.py`)

Rewritten from a `NotImplementedError`-raising placeholder into a real
client with three methods:

- `connect(db_path: str) -> None` — opens the SQLite file at `db_path`,
  raising `FileNotFoundError` if it doesn't exist (SQLite would otherwise
  silently create an empty file, which would mask a misconfigured path).
  Closes any previously open connection first.
- `list_items(folder_path: str) -> List[str]` — returns child item names
  for a folder (`""` for the root), sorted by name; returns `[]` if the
  folder is empty or doesn't exist.
- `data_content(item_path: str) -> bytes` — returns the raw bytes for a
  file, raising `FileNotFoundError` if no such file exists. This exception
  type is load-bearing: `DataService.process_single_experiment` catches
  `FileNotFoundError` to handle optional files (a missing `Benchling.zip`,
  or trying `Eve.zip` before falling back to `Pi.zip`).

The old MS Graph-specific `search_for_site`/`list_site_drives` methods were
removed — they encoded a two-step SharePoint site/drive ID lookup with no
SQLite equivalent, and nothing outside `SharePoint` called them.

### `SharePoint` (`biocanvas/utils/io.py`)

Simplified to match the new `MSDrive`: `connect()` now just opens the
project's database (no site/drive ID resolution); `get_item_names()` and
`load_data()` no longer prefix paths with `self.data_dir` (that field is
now the database file path, consumed once by `MSDrive.connect`, not a
per-call folder prefix). Existing `_data_cache`/`_list_cache` memoization
is unchanged.

## Naming

Per project decision, existing names were kept to minimize the diff and
avoid touching UI text, docstrings, and config keys throughout the
codebase:

- Class name `SharePoint`, attribute `DataService.sharepoint`.
- Method names `connect`, `get_item_names`, `load_data`.
- Config key `SHAREPOINT_DATA_DIR` / YAML key `sharepoint_data_dir` — this
  now holds the **filesystem path to the project's SQLite `.db` file**
  instead of a SharePoint folder path (e.g. Project Helix's
  `sharepoint_data_dir` changed from
  `/General/WS3 Fermentation/fermenter runs/data/` to `helix/helix.db`).

## What's not included

**Ingestion tooling is a follow-up, not part of this change.** There is no
script or CLI to bulk-load an existing SharePoint export or local folder
tree into a project's SQLite database yet. Anyone populating a database
today should insert rows directly following the schema above (e.g. one row
per experiment directory with `is_dir=1`, one row per raw file underneath
with the file's bytes in `content`).

## Tests

`tests/unit/test_drive.py` covers `MSDrive` directly (connect failure
modes, `list_items`, `data_content`, missing-file `FileNotFoundError`) and
`SharePoint` end-to-end using the exact call pattern `data_service.py` uses
(`connect` → `get_item_names("")` → `get_item_names(f"{exp}/")` →
`load_data(f"{exp}/Meta.csv")`), plus cache population/clearing on
reconnect.
