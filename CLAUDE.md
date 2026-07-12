# CLAUDE.md

## System Architecture & Tech Stack

BioCanvas is an ipywidgets-based Jupyter notebook GUI (`ui.ipynb`) for
processing and visualizing biological fermentation experiment data. Python
3.11, managed entirely through `pixi`.

**Layers** (`src/biocanvas/`):

- `core.py` — `App`: thin view-orchestrator. Owns the top-level ipywidgets
  `Tab`, wires all widget event handlers, and delegates every data operation
  to `DataService`. No business logic lives here.
- `ui_components.py` — one `*TabWidgets` class per notebook tab (Process
  Data, QC Plots, KPI Overlap, Condition Comparison, Global Comparison,
  Publish Results). Builds/owns widgets only, no data logic.
- `data_service.py` — `DataService`: pure data-pipeline logic, no ipywidgets
  dependency. Owns drive connectivity, dynamic project-module loading, raw
  file parsing, master-table construction (`AugmentTables`), and
  plot-property filtering.
- `utils/` — `auth.py` (PBKDF2 passcode hashing/verification), `io.py`
  (dir setup, dynamic module loading, `GeneralTable`/`GeneralAnalyteTable`,
  `SharePoint` client, xlsx/html report generation), `drive.py` (`MSDrive`
  placeholder — see below), `logging_config.py`, `stats.py` (descriptive +
  significance testing), `visualization.py` (`QCPlotter`, `OLPlotter`,
  `CCPlotter`, `GCPlotter`), `helpers.py` (shared types/exceptions).
- `helix/`, `spore/` — per-project subpackages, loaded dynamically by name
  (`biocanvas.<project>.{meta,benchling,ferm_process,config}`) based on the
  project selected in the UI. Project name → passcode hash mapping lives in
  `passcodes.json`. `spore/` is currently a stub (`__init__.py` only).

**Data flow:** `App` → `DataService.build_master_tables` → drive client
(`utils/io.SharePoint`, backed by `utils/drive.MSDrive`) fetches raw
`Meta.csv` / `Benchling.zip` / `Eve.zip`|`Pi.zip` per experiment → parsed by
the active project's `meta.py`/`benchling.py`/`ferm_process.py` → augmented
by `AugmentTables` (TRY KPIs, mass balance, carbon accounting) → concatenated
into `master_meta_table` / `master_bench_table` / `master_process_table` →
filtered per-tab via `bench_plot_properties`/`process_plot_properties`
(defined in each project's `config.py`) → rendered by the `visualization.py`
plotters into matplotlib figures shown in ipywidgets `Output` widgets →
optionally saved with `utils/stats.py` significance tables → consolidated
into an xlsx/html report by the Publish Results tab.

**Note:** `utils/drive.MSDrive` was originally a placeholder standing in for
the real SharePoint client (`bifrost.auth.drive.MSDrive`), which came from a
now-unavailable external monorepo. It has since been replaced with a local
SQLite-backed implementation: one `.db` file per project (path configured
via each project's `SHAREPOINT_DATA_DIR`, kept under that name for interface
compatibility), storing raw experiment files (`Meta.csv`, `Benchling.zip`,
`Eve.zip`/`Pi.zip`) as BLOBs in a simple virtual-filesystem table. See
`drive-backend-changes.md` for the schema and details. `utils/io.SharePoint`
still exposes the same `connect`/`get_item_names`/`load_data` interface, so
`DataService` needed no call-site changes. Populating a project's database
with real data (ingestion tooling) is a separate follow-up.

## Workspace Dependency Architecture (`pixi.toml`)

- **Dependency Management:** Monitored and locked natively via `pixi`.
- **Version Control:** Absolute Git branch isolation. Merge to `main` ONLY via verified GitHub Pull Requests. Day-to-day work occurs on the `dev` branch or local git worktrees for multi-agent work.

## Operational Commands for Claude Code using pixi.task

- `pixi install` — sync the environment from `pixi.lock` after editing
  `pixi.toml`.
- `pixi run test` — `pytest tests/`.
- `pixi run lint` — `ruff check .` and `ruff format --check .` (check-only,
  matches CI; use `pixi run format` to actually rewrite files).
- `pixi run format` — `ruff format src/ tests/`.
- `pixi run python -m pytest tests/unit/test_x.py::TestY::test_z` — run a
  single test inside the pixi environment.

## Development Constraints & Guardrails

* **No Global System Traps:** Do NOT install Python dependencies using global or un-isolated `pip install`. Everything must pass through the `pixi.toml` manifest file.
* **Static Type Safety:** All custom Python code written inside `src/` must contain explicit types using the `typing` module. Verify validation parameters cleanly before building.
* **Atomic Git Workflows:** Code adjustments must be written via micro-commits matching semantic descriptions. Never push unreviewed files straight to `main`.

## Deployment & CI/CD

* **Remote:** [`paymantohidifar/BioCanvas`](https://github.com/paymantohidifar/BioCanvas)
* **CI (`.github/workflows/ci.yml`):** Triggers on pushes and pull requests targeting `main`/`master` only (not `dev`). Runs `pixi run lint` then `pixi run test` via `prefix-dev/setup-pixi`, using the locked `pixi.lock` environment.
