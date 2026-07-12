# SQLite Schema Guide

## What was built

A new `src/biocanvas/db/` subpackage that gives BioCanvas a local SQLite
store for **raw** experiment data (Meta.csv, Benchling.zip panels,
Eve.zip/Pi.zip process files), plus a typed import API to load already-parsed
pandas data into it.

This is the storage layer that `utils/drive.MSDrive` (currently a stub that
raises `NotImplementedError` everywhere) is expected to eventually be backed
by — but wiring `MSDrive` up is a separate follow-up, not part of this
change. Today, the import API is called directly with DataFrames.

```
src/biocanvas/db/
    __init__.py
    schema.sql      # table DDL
    schema.py        # create_schema(conn), connect(db_path)
    importer.py       # import_* functions
tests/unit/test_db.py    # 11 tests, all passing
database-changes.md      # full design rationale
```

Scope, by design:
- **Raw data only.** Computed columns from `AugmentTables` (TRY KPIs, mass
  balance, carbon accounting) are *not* stored — they're still computed
  in-memory from raw data on every load, same as today.
- **Overwrite in place on re-import.** No row-level history.
- **No raw file bytes archived** (no CSV/zip BLOBs).
- **No `MSDrive` wiring yet** — this only covers schema + import.

## Design in one paragraph

Meta.csv is stored as **wide** rows (one row per tank, fixed QC'd columns),
with its 5 repeated feed-type column groups (Feed/Co-feed/Bolus/Acid/Base)
normalized into their own table. Benchling and Process measurements are
stored **long/EAV-style** (one row per metric value) instead of one column
per metric, because both vocabularies are driven by each project's
`config.yaml` and will differ once the `spore` project is implemented — long
format needs zero schema changes as new substrates/products/panels are
added. See `database-changes.md` for the full reasoning and table-by-table
breakdown.

## Tables at a glance

| Table | One row per | Notes |
|---|---|---|
| `project` | project (`helix`, `spore`, ...) | |
| `experiment` | `(project, Exp)` | e.g. `(helix, 'E001')` |
| `tank_meta` | `(experiment, Tank)` | wide Meta.csv columns |
| `tank_feed_profile` | `(tank, feed_type)` | Feed/Co-feed/Bolus/Acid/Base |
| `benchling_sample` | `(experiment, Sample)` | decomposes to `Tank` + `Time (h)` |
| `benchling_measurement` | `(sample, panel, metric)` | long/EAV, e.g. `('Sugar','Glucose (g/L)')` |
| `process_file` | `(experiment, Tank)` | tags vendor (`Eve`/`Pi`) |
| `process_measurement` | `(process_file, time_h, channel)` | long/EAV, e.g. `'Temperature, °C'` |

## How to import data

### 1. Open a connection (creates the schema automatically)

```python
from biocanvas.db import schema

conn = schema.connect('biocanvas.sqlite')   # or ':memory:' for a scratch DB
```

`schema.connect` enables `PRAGMA foreign_keys = ON` and runs the DDL in
`schema.sql` (`CREATE TABLE IF NOT EXISTS`, so it's safe to call repeatedly
against an existing file).

### 2. Get the three raw DataFrames the same way `DataService` already does

The importer expects the DataFrames as they exist **before**
`AugmentTables` runs — i.e. the direct output of the existing parsers:

```python
from biocanvas.data_service import DataService

svc = DataService()
svc.load_project_modules('helix')   # sets svc.meta_module / benchling_module / ferm_process_module / config_module

meta = svc.meta_module.Meta(open('Meta.csv'), exp_id='E001')
meta_table = meta.proc_table

bench_table, bench_msgs = svc._process_benchling_files(
    open('Benchling.zip', 'rb'), meta_table
)

process_table, process_msgs = svc._process_ferm_process_panels(
    open('Eve.zip', 'rb'), meta_table, process_panel='EveTable'  # or 'PiTable'
)
```

(Exact loading calls depend on where your files live — SharePoint vs. local
disk — but the DataFrames you hand to the importer are these three:
`meta_table`, `bench_table`, `process_table`.)

### 3. Import one experiment in a single call

```python
from biocanvas.db import importer

experiment_id = importer.import_experiment(
    conn,
    project_name='helix',
    exp='E001',
    meta_table=meta_table,
    bench_table=bench_table,
    process_table=process_table,
    process_vendor='Eve',   # or 'Pi', matching which zip you loaded
)
conn.close()  # or keep it open to import more experiments
```

That's it — `import_experiment` creates the `project`/`experiment` rows if
they don't exist yet, then imports all three tables in order.

### Importing tables individually (if you already have an `experiment_id`)

```python
from biocanvas.db import importer

project_id = importer.get_or_create_project(conn, 'helix')
experiment_id = importer.get_or_create_experiment(conn, project_id, 'E001')

importer.import_meta_table(conn, experiment_id, meta_table)
importer.import_benchling_table(conn, experiment_id, bench_table)
importer.import_process_table(conn, experiment_id, process_table, vendor='Eve')
```

### Re-importing a corrected file

Just call the same `import_*` function again with the corrected DataFrame —
rows for that `(experiment, tank)` / `(experiment, sample)` are deleted and
replaced. No special "update" call is needed, and nothing is duplicated.

## Reading data back out

Since measurements are stored long/EAV, query them and pivot back to a wide
DataFrame with pandas — this is cheap at BioCanvas's data volumes and is the
intended usage pattern (not raw SQL analysis).

```python
import pandas as pd

rows = conn.execute(
    """
    SELECT bs.tank AS "Tank", bs.time_h AS "Time (h)", bm.panel, bm.metric, bm.value
    FROM benchling_measurement bm
    JOIN benchling_sample bs ON bs.sample_id = bm.sample_id
    WHERE bs.experiment_id = ?
    """,
    (experiment_id,),
).fetchall()

long_df = pd.DataFrame(rows, columns=['Tank', 'Time (h)', 'panel', 'metric', 'value'])
wide = long_df.pivot_table(
    index=['Tank', 'Time (h)'], columns=['panel', 'metric'], values='value'
).reset_index()
```

This reconstructs the same `(panel, metric)`-MultiIndex-columned shape that
`_process_benchling_files` produces — `tests/unit/test_db.py::
TestImportBenchlingTable::test_pivots_back_to_wide_bench_table` verifies this
round-trip exactly. The same pattern applies to `process_measurement` (pivot
on `channel` instead of `(panel, metric)`).

`tank_meta` and `tank_feed_profile` are already wide/normalized relational
tables, so a plain `SELECT` (with a `JOIN` for feed profiles) is enough —
no pivot needed:

```python
meta_df = pd.read_sql(
    "SELECT * FROM tank_meta WHERE experiment_id = ?", conn, params=(experiment_id,)
)
feeds_df = pd.read_sql(
    """
    SELECT tm.tank, tfp.*
    FROM tank_feed_profile tfp
    JOIN tank_meta tm ON tm.tank_meta_id = tfp.tank_meta_id
    WHERE tm.experiment_id = ?
    """,
    conn, params=(experiment_id,),
)
```

## Things worth knowing before you import

- **`'NA'` and `'var'` sentinels are preserved as text, not NULL.** Columns
  like `tank_feed_profile.measured_added_ml` are `TEXT`, so a raw `'NA'`
  value round-trips as the string `'NA'` — don't assume `NULL` means
  missing there; it means the column genuinely wasn't in the source row.
- **Feed profiles are only created when `{Type} Source` is populated and not
  `'NA'`.** A seed tank with all-`'NA'` feed columns gets zero
  `tank_feed_profile` rows.
- **`Sample` is synthesized if missing.** If a bench table has no `Sample`
  column (e.g. some test fixtures), the importer builds one as
  `f'{tank}-T{time_h:g}h'`.
- **`process_table` must have a `Tank` column** — rows are grouped by tank to
  create one `process_file` row each.
- **Multiple projects can share one DB file** without collision — `exp` ids
  are only unique per `project_id`, so `('helix', 'E001')` and `('spore',
  'E001')` are distinct experiments.

## Verifying your own import

```bash
pixi run python -m pytest tests/unit/test_db.py -v
```

Or open the file directly and poke around:

```bash
sqlite3 biocanvas.sqlite ".tables"
sqlite3 biocanvas.sqlite "SELECT * FROM experiment;"
```

For full design rationale (why EAV, why these keys, what was explicitly
deferred), see `database-changes.md` in the repo root.
