-- BioCanvas raw-data SQLite schema.
--
-- Stores raw imported Meta.csv / Benchling.zip / Eve.zip|Pi.zip data per
-- experiment. Computed/augmented columns (TRY KPIs, mass balance, carbon
-- accounting) are NOT stored here -- they continue to be computed in-memory
-- by data_service.AugmentTables from the raw data pulled out of this schema.
--
-- Benchling panel measurements and Process time-series channels are stored
-- long/EAV-style (one row per metric) rather than as fixed wide columns,
-- because their vocabulary is driven by each project's config.yaml
-- (substrates, products, enzyme assays) and therefore varies per project
-- and grows over time without requiring a schema migration. Meta.csv stays
-- wide since its columns are fixed and QC'd per row-per-tank.
--
-- Re-imports overwrite in place (delete-then-insert per tank/sample/file);
-- no row-level history is kept.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS project (
    project_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    project_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS experiment (
    experiment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    INTEGER NOT NULL REFERENCES project(project_id),
    exp           TEXT NOT NULL,
    imported_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (project_id, exp)
);

-- Meta.csv: one row per Tank per experiment (wide -- fixed, QC'd columns).
CREATE TABLE IF NOT EXISTS tank_meta (
    tank_meta_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id         INTEGER NOT NULL REFERENCES experiment(experiment_id),
    tank                  TEXT NOT NULL,
    condition             TEXT,
    replicate             INTEGER,
    strain_batch          TEXT,
    strain                TEXT,               -- derived from Strain Batch
    platform              TEXT,               -- derived from Tank prefix
    eft_h                 REAL,
    media                 TEXT,
    initial_broth_vol_ml  REAL,
    ph_setpoint           TEXT,               -- may hold 'var' or a semicolon profile
    temp_setpoint_c       TEXT,
    do_setpoint_pct       TEXT,
    run                   TEXT,               -- derived f'{Exp}-{Tank}'
    UNIQUE (experiment_id, tank)
);

-- Repeated feed-type column groups from Meta.csv (Feed / Co-feed / Bolus /
-- Acid / Base, or a future project's equivalent set), normalized into rows.
-- feed_type is free text (no CHECK constraint) so this stays project-
-- agnostic -- 'spore' may define a different feed-type vocabulary.
CREATE TABLE IF NOT EXISTS tank_feed_profile (
    feed_profile_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tank_meta_id              INTEGER NOT NULL REFERENCES tank_meta(tank_meta_id) ON DELETE CASCADE,
    feed_type                 TEXT NOT NULL,
    source                    TEXT,
    element                   TEXT,
    density_g_ml              REAL,
    eve_pi_controlled         TEXT,
    max_calib_pump_rate_ml_s  TEXT,            -- 'NA' sentinel preserved verbatim
    manual_time_profile_h     TEXT,            -- raw semicolon-delimited profile string
    manual_target_rate_ml_h   TEXT,            -- raw semicolon-delimited profile string
    measured_added_ml         TEXT,            -- 'NA' sentinel preserved verbatim
    target_conc_g_l           TEXT,            -- 'NA' sentinel preserved verbatim
    UNIQUE (tank_meta_id, feed_type)
);

-- Benchling Sample panel: canonical join-key rows per experiment.
CREATE TABLE IF NOT EXISTS benchling_sample (
    sample_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id  INTEGER NOT NULL REFERENCES experiment(experiment_id),
    sample         TEXT NOT NULL,              -- normalized 'M1-R1-T24h' label
    tank           TEXT NOT NULL,
    time_h         REAL NOT NULL,
    sample_vol_ml  REAL,
    UNIQUE (experiment_id, sample)
);

-- All non-Sample Benchling panel measurements (Ferm, Sugar, Alpha, ...):
-- long/EAV so new panels/analytes never require a schema change.
CREATE TABLE IF NOT EXISTS benchling_measurement (
    measurement_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    sample_id       INTEGER NOT NULL REFERENCES benchling_sample(sample_id) ON DELETE CASCADE,
    panel           TEXT NOT NULL,             -- 'Ferm', 'Sugar', 'Alpha', ...
    metric          TEXT NOT NULL,             -- 'DCW (g/L)', 'Glucose (g/L)', ...
    value           REAL,
    is_std          INTEGER NOT NULL DEFAULT 0, -- 1 for the '_std' companion value
    UNIQUE (sample_id, panel, metric, is_std)
);
CREATE INDEX IF NOT EXISTS ix_benchling_measurement_panel_metric
    ON benchling_measurement(panel, metric);

-- Process file provenance: one row per (experiment, tank) process import.
CREATE TABLE IF NOT EXISTS process_file (
    process_file_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    experiment_id    INTEGER NOT NULL REFERENCES experiment(experiment_id),
    tank             TEXT NOT NULL,
    vendor           TEXT NOT NULL CHECK (vendor IN ('Eve', 'Pi')),
    UNIQUE (experiment_id, tank)
);

-- Process time-series measurements: long/EAV, keyed by (Tank, Time (h)).
CREATE TABLE IF NOT EXISTS process_measurement (
    process_measurement_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    process_file_id         INTEGER NOT NULL REFERENCES process_file(process_file_id) ON DELETE CASCADE,
    time_h                   REAL NOT NULL,
    channel                  TEXT NOT NULL,    -- raw vendor column name, e.g. 'Temperature, °C'
    value                     REAL,
    UNIQUE (process_file_id, time_h, channel)
);
CREATE INDEX IF NOT EXISTS ix_process_measurement_channel
    ON process_measurement(channel);
CREATE INDEX IF NOT EXISTS ix_process_measurement_time
    ON process_measurement(process_file_id, time_h);
