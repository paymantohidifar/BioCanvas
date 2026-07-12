# Database Changes

## Summary

Added a SQLite schema and typed import API for storing **raw** experiment
data (Meta.csv, Benchling.zip, Eve.zip/Pi.zip) locally, as the first piece of
the SQLite-backed replacement for `utils/drive.MSDrive` referenced in that
module's docstring. This is greenfield — no prior SQLite/ORM code existed in
the repo.

Scope is intentionally limited to **schema + import of already-parsed
DataFrames**:
- It does **not** persist `AugmentTables`' computed/augmented columns (TRY
  KPIs, mass balance, carbon accounting) — those continue to be computed
  in-memory from raw data, exactly as today.
- It does **not** reimplement `MSDrive`/`SharePoint` — the schema is
  designed so a future `MSDrive` implementation can read/write through it,
  but that wiring is a follow-up.
- It does **not** archive raw file bytes (CSV/zip content) for provenance.
- Re-imports overwrite in place (delete-then-insert per tank/sample/file);
  no row-level history is kept.

## New files

```
src/biocanvas/db/
    __init__.py
    schema.sql      # DDL
    schema.py        # create_schema(conn), connect(db_path)
    importer.py       # typed import API
tests/unit/test_db.py
```

`tests/conftest.py` gained a `db_conn` fixture (function-scoped, in-memory
SQLite connection with the schema created).

## Schema design

### Wide vs. long (EAV) — key decision

Benchling panel columns (`Ferm`, `Sugar`, `Alpha`, ...) and their analyte
metric names, and Process time-series channel names, are **driven by each
project's `config.yaml`** (see `helix/config.py`: substrate/product/enzyme
lists build column names like `f"{substrate} (g/L)"`, `f"{product} Titer
(g/L)"`). This vocabulary differs per project and grows over time as
`config.yaml` is edited — and the `spore` project (currently a stub) will
have its own, unknown vocabulary.

A fixed wide table (one column per metric) would require a schema migration
every time a substrate/product/panel is added, and would need either a
column superset shared across projects or per-project schemas once `spore`
is implemented. Instead, **Benchling and Process measurements are stored
long/EAV-style**: one row per `(sample_or_file, panel_or_channel, metric,
value)`. This needs zero schema changes for new metrics or projects, and
matches how the data is actually consumed downstream — loaded in bulk per
experiment and immediately pivoted into a wide pandas DataFrame (which
`pandas.pivot_table` does cheaply at BioCanvas's lab-scale data volumes).

**Meta.csv stays wide**, since its columns are fixed and QC'd per
row-per-tank (`helix/meta.py`'s `essential_cols`). Its 5 repeated feed-type
column groups (`Feed` / `Co-feed` / `Bolus` / `Acid` / `Base`) are
normalized into a separate narrow `tank_feed_profile` table, one row per
`(tank, feed_type)`, since the sub-column shape is fixed but repeats 5x.

### Tables

| Table | Purpose | Key constraint |
|---|---|---|
| `project` | Project discriminator (`helix`, `spore`, ...) | `UNIQUE(project_name)` |
| `experiment` | One row per `(project, Exp)` | `UNIQUE(project_id, exp)` |
| `tank_meta` | Meta.csv, one row per Tank (wide, QC'd columns) | `UNIQUE(experiment_id, tank)` |
| `tank_feed_profile` | Normalized Feed/Co-feed/Bolus/Acid/Base groups | `UNIQUE(tank_meta_id, feed_type)` |
| `benchling_sample` | Benchling `Sample` panel — canonical join key, decomposes to `(Tank, Time (h))` | `UNIQUE(experiment_id, sample)` |
| `benchling_measurement` | All other Benchling panel values, long/EAV | `UNIQUE(sample_id, panel, metric, is_std)` |
| `process_file` | One row per `(experiment, tank)` process import, tags vendor (Eve/Pi) | `UNIQUE(experiment_id, tank)` |
| `process_measurement` | Process time-series values, long/EAV, keyed by `(Tank, Time (h))` | `UNIQUE(process_file_id, time_h, channel)` |

Sentinel-preserving columns (`'NA'`, `'var'`, semicolon-delimited profile
strings used throughout Meta.csv) are stored as `TEXT`, not coerced to
`NULL`/`REAL`, to preserve raw semantics exactly as `meta.py`'s QC step
produces them (`.fillna('NA')`).

`tank_feed_profile.feed_type` and `benchling_measurement.metric` /
`process_measurement.channel` are free text with no `CHECK` constraint, so
the schema stays project-agnostic — `spore`'s eventual feed-type/analyte
vocabulary doesn't require a migration. `process_file.vendor` does keep a
`CHECK (vendor IN ('Eve', 'Pi'))`, since those are fixed file-format
constants, not a config-driven vocabulary.

Child tables (`tank_feed_profile`, `benchling_measurement`,
`process_measurement`) use `ON DELETE CASCADE` on their parent foreign key,
so the importer's delete-then-insert overwrite pattern works cleanly under
`PRAGMA foreign_keys = ON`.

## Import API (`src/biocanvas/db/importer.py`)

Consumes the DataFrames already produced by existing parsers — it never
reparses raw CSV/zip content:

- `get_or_create_project(conn, project_name) -> int`
- `get_or_create_experiment(conn, project_id, exp) -> int`
- `import_meta_table(conn, experiment_id, meta_table)` — expects
  `helix.meta.Meta.proc_table`'s shape (one row per tank); melts the 5
  feed-type column groups into `tank_feed_profile` rows, skipping feed types
  whose `Source` is missing or `'NA'`.
- `import_benchling_table(conn, experiment_id, bench_table)` — expects
  `DataService._process_benchling_files`'s shape (MultiIndex `(panel,
  metric)` columns plus `Sample`/`Tank`/`Time (h)`/`Sample Vol (ml)` keys);
  melts panel columns into `benchling_measurement` rows. A metric name
  containing `'_std'` is stored as the companion value with `is_std=1` under
  the base metric name. If no `Sample` column is present, a sample label is
  synthesized from `Tank`+`Time (h)`.
- `import_process_table(conn, experiment_id, process_table, vendor)` —
  expects `DataService._process_ferm_process_panels`'s shape (flat
  `Tank`/`Time (h)` keys plus raw vendor channel columns); melts channel
  columns into `process_measurement` rows.
- `import_experiment(conn, project_name, exp, meta_table, bench_table,
  process_table, process_vendor) -> int` — convenience wrapper that creates
  the project/experiment rows and imports all three raw tables for one
  experiment.

All signatures use explicit `typing` per the project's static type safety
convention.

## Testing

`tests/unit/test_db.py` (11 tests, all passing) exercises schema creation,
round-trip import for all three raw tables, feed-profile normalization and
sentinel preservation, overwrite-on-reimport semantics, long-to-wide
pivoting back to the original panel/metric shape, and multi-project
isolation — using an in-memory SQLite connection (`db_conn` fixture in
`tests/conftest.py`) and the existing `meta_table_for_augment` /
`raw_bench_table_for_augment` / `raw_process_table_for_augment` fixtures as
inputs. Full suite (`pixi run test`, 123 tests) and `pixi run lint` both
pass with no regressions.

## Follow-ups (not in this change)

- Wire `utils/drive.MSDrive` to read/write through `biocanvas.db` instead of
  raising `NotImplementedError`.
- Decide whether `AugmentTables` output should ever be cached/persisted.
- Decide whether raw file bytes should be archived for provenance.
- Validate the schema against `spore`'s config once it has real
  `meta.py`/`benchling.py`/`ferm_process.py`/`config.py` modules.
