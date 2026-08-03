# biocanvas/db/importer.py
"""Typed import API: loads parsed Meta / Benchling / Process DataFrames into the
BioCanvas raw-data SQLite schema.

These functions consume the DataFrames already produced by the existing
per-project parsers (``helix.meta.Meta.proc_table``, the consolidated
Benchling table built by ``data_service.DataService._process_benchling_files``,
and the consolidated process table built by
``data_service.DataService._process_ferm_process_panels``) -- they never
reparse raw CSV/zip file content themselves.
"""

import sqlite3
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd  # type: ignore

FEED_TYPES: Tuple[str, ...] = ("Feed", "Co-feed", "Bolus", "Acid", "Base")

# Meta.csv key columns whose source column name is unambiguous.
_META_SIMPLE_COLUMNS: Dict[str, str] = {
    "condition": "Condition",
    "strain_batch": "Strain Batch",
    "strain": "Strain",
    "platform": "Platform",
    "media": "Media",
    "run": "Run",
}

# Meta.csv key columns whose source column name has varied across raw-file
# revisions; the first candidate present in the table wins.
_META_CANDIDATE_COLUMNS: Dict[str, Tuple[str, ...]] = {
    "ph_setpoint": ("pH Setpoint",),
    "temp_setpoint_c": ("Temp (°C) Setpoint", "Temperature Setpoint (°C)"),
    "do_setpoint_pct": ("DO (%) Setpoint", "DO Setpoint (%)"),
}

# Benchling consolidated-table key column names (outer MultiIndex level, or
# plain column name in non-MultiIndex test fixtures).
_BENCH_KEY_NAMES = {
    "Sample",
    "Tank",
    "Time (h)",
    "Sample Vol (ml)",
    "Exp",
    "Replicate",
    "Strain",
}

# Process consolidated-table key columns (never imported as measurements).
_PROCESS_KEY_COLUMNS = {"Tank", "Time (h)", "Exp", "Replicate"}


def _to_optional_str(value: Any) -> Optional[str]:
    """Returns str(value), or None if value is missing/NaN."""
    if value is None or pd.isna(value):
        return None
    return str(value)


def _to_optional_float(value: Any) -> Optional[float]:
    """Returns float(value), or None if value is missing/NaN/non-numeric."""
    text = _to_optional_str(value)
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_optional_int(value: Any) -> Optional[int]:
    """Returns int(value), or None if value is missing/NaN/non-numeric."""
    as_float = _to_optional_float(value)
    return None if as_float is None else int(as_float)


def _row_get(row: "pd.Series[Any]", column: str) -> Any:
    """Returns row[column] if column exists in row's index, else None."""
    return row[column] if column in row.index else None


def _row_get_first(row: "pd.Series[Any]", candidates: Tuple[str, ...]) -> Any:
    """Returns the first populated value among candidate column names."""
    for column in candidates:
        if column in row.index:
            value = row[column]
            if not (value is None or pd.isna(value)):
                return value
    return None


def get_or_create_project(conn: sqlite3.Connection, project_name: str) -> int:
    """Returns the project_id for project_name, inserting it if new.

    Args:
        conn: Open SQLite connection.
        project_name: Project discriminator, e.g. 'helix' or 'spore'.

    Returns:
        The project's integer primary key.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT project_id FROM project WHERE project_name = ?", (project_name,)
    )
    row = cur.fetchone()
    if row is not None:
        return int(row[0])
    cur.execute("INSERT INTO project (project_name) VALUES (?)", (project_name,))
    conn.commit()
    return int(cur.lastrowid)


def get_or_create_experiment(
    conn: sqlite3.Connection, project_id: int, exp: str
) -> int:
    """Returns the experiment_id for (project_id, exp), inserting it if new.

    Args:
        conn: Open SQLite connection.
        project_id: Parent project's primary key.
        exp: Experiment identifier, e.g. 'E001'.

    Returns:
        The experiment's integer primary key.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT experiment_id FROM experiment WHERE project_id = ? AND exp = ?",
        (project_id, exp),
    )
    row = cur.fetchone()
    if row is not None:
        return int(row[0])
    cur.execute(
        "INSERT INTO experiment (project_id, exp) VALUES (?, ?)", (project_id, exp)
    )
    conn.commit()
    return int(cur.lastrowid)


def _import_feed_profiles(
    cur: sqlite3.Cursor, tank_meta_id: int, row: "pd.Series[Any]"
) -> None:
    """Inserts one tank_feed_profile row per populated feed type on row.

    A feed type is considered populated when its 'Source' column is present
    and is neither missing nor the 'NA' sentinel used by Meta.csv QC.
    """
    for feed_type in FEED_TYPES:
        source = _to_optional_str(_row_get(row, f"{feed_type} Source"))
        if source is None or source == "NA":
            continue
        cur.execute(
            """INSERT INTO tank_feed_profile (
                tank_meta_id, feed_type, source, element, density_g_ml,
                eve_pi_controlled, max_calib_pump_rate_ml_s,
                manual_time_profile_h, manual_target_rate_ml_h,
                measured_added_ml, target_conc_g_l
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tank_meta_id,
                feed_type,
                source,
                _to_optional_str(_row_get(row, f"{feed_type} Element")),
                _to_optional_float(_row_get(row, f"{feed_type} Density (g/ml)")),
                _to_optional_str(_row_get(row, f"Eve/Pi Controlled {feed_type}")),
                _to_optional_str(
                    _row_get(row, f"Max Calib. {feed_type} Pump Rate (ml/s)")
                ),
                _to_optional_str(_row_get(row, f"Manual {feed_type} Time Profile (h)")),
                _to_optional_str(
                    _row_get(row, f"Manual Target {feed_type} Rate (ml/h)")
                ),
                _to_optional_str(_row_get(row, f"Measured Added {feed_type} (ml)")),
                _to_optional_str(_row_get(row, f"Target {feed_type} Conc. (g/l)")),
            ),
        )


def import_meta_table(
    conn: sqlite3.Connection, experiment_id: int, meta_table: pd.DataFrame
) -> None:
    """Imports a Meta.proc_table-shaped DataFrame into tank_meta + tank_feed_profile.

    Expects one row per Tank with the flat wide columns produced by
    ``helix.meta.Meta`` (or a project's equivalent), including the repeated
    feed-type column groups. Re-importing the same (experiment_id, tank)
    deletes and replaces the existing row (and its feed profiles).

    Args:
        conn: Open SQLite connection.
        experiment_id: Parent experiment's primary key.
        meta_table: Processed metadata table, one row per tank.
    """
    if meta_table.empty:
        return
    cur = conn.cursor()
    for _, row in meta_table.iterrows():
        tank = str(row["Tank"])
        cur.execute(
            "DELETE FROM tank_meta WHERE experiment_id = ? AND tank = ?",
            (experiment_id, tank),
        )
        cur.execute(
            """INSERT INTO tank_meta (
                experiment_id, tank, condition, replicate, strain_batch, strain,
                platform, eft_h, media, initial_broth_vol_ml,
                ph_setpoint, temp_setpoint_c, do_setpoint_pct, run
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                experiment_id,
                tank,
                _to_optional_str(_row_get(row, _META_SIMPLE_COLUMNS["condition"])),
                _to_optional_int(_row_get(row, "Replicate")),
                _to_optional_str(_row_get(row, _META_SIMPLE_COLUMNS["strain_batch"])),
                _to_optional_str(_row_get(row, _META_SIMPLE_COLUMNS["strain"])),
                _to_optional_str(_row_get(row, _META_SIMPLE_COLUMNS["platform"])),
                _to_optional_float(_row_get(row, "EFT (h)")),
                _to_optional_str(_row_get(row, _META_SIMPLE_COLUMNS["media"])),
                _to_optional_float(_row_get(row, "Initial Broth Vol (ml)")),
                _to_optional_str(
                    _row_get_first(row, _META_CANDIDATE_COLUMNS["ph_setpoint"])
                ),
                _to_optional_str(
                    _row_get_first(row, _META_CANDIDATE_COLUMNS["temp_setpoint_c"])
                ),
                _to_optional_str(
                    _row_get_first(row, _META_CANDIDATE_COLUMNS["do_setpoint_pct"])
                ),
                _to_optional_str(_row_get(row, _META_SIMPLE_COLUMNS["run"])),
            ),
        )
        tank_meta_id = int(cur.lastrowid)
        _import_feed_profiles(cur, tank_meta_id, row)
    conn.commit()


def _column_key(column: Any) -> Tuple[str, str]:
    """Normalizes a Benchling table column to a (panel, metric) pair.

    Handles both a true 2-level MultiIndex (production shape) and a plain
    string column (some test fixtures), where a bare string is treated as a
    key column with an empty metric level.
    """
    if isinstance(column, tuple) and len(column) == 2:
        return str(column[0]), str(column[1])
    return str(column), ""


def import_benchling_table(
    conn: sqlite3.Connection, experiment_id: int, bench_table: pd.DataFrame
) -> None:
    """Imports a consolidated Benchling DataFrame into benchling_sample + benchling_measurement.

    Expects the shape returned by
    ``DataService._process_benchling_files``: MultiIndex ``(panel, metric)``
    columns for panel data, plus ``Sample``/``Tank``/``Time (h)``/
    ``Sample Vol (ml)`` key columns. A metric name containing ``'_std'``
    is stored as the companion standard-deviation value (``is_std=1``) under
    the base metric name. Re-importing the same (experiment_id, sample)
    deletes and replaces the existing sample row and its measurements.

    Args:
        conn: Open SQLite connection.
        experiment_id: Parent experiment's primary key.
        bench_table: Consolidated Benchling table, one row per sample.
    """
    if bench_table.empty:
        return
    cur = conn.cursor()

    key_columns: Dict[str, Any] = {}
    metric_columns: List[Any] = []
    for column in bench_table.columns:
        panel, metric = _column_key(column)
        if metric == "" and panel in _BENCH_KEY_NAMES:
            key_columns[panel] = column
        else:
            metric_columns.append(column)

    for _, row in bench_table.iterrows():
        tank = str(row[key_columns["Tank"]])
        time_h = float(row[key_columns["Time (h)"]])

        sample_value = (
            _to_optional_str(row[key_columns["Sample"]])
            if "Sample" in key_columns
            else None
        )
        sample = sample_value if sample_value is not None else f"{tank}-T{time_h:g}h"

        sample_vol_ml = (
            _to_optional_float(row[key_columns["Sample Vol (ml)"]])
            if "Sample Vol (ml)" in key_columns
            else None
        )

        cur.execute(
            "DELETE FROM benchling_sample WHERE experiment_id = ? AND sample = ?",
            (experiment_id, sample),
        )
        cur.execute(
            "INSERT INTO benchling_sample (experiment_id, sample, tank, time_h, sample_vol_ml) "
            "VALUES (?, ?, ?, ?, ?)",
            (experiment_id, sample, tank, time_h, sample_vol_ml),
        )
        sample_id = int(cur.lastrowid)

        measurement_rows: List[Tuple[int, str, str, Optional[float], int]] = []
        for column in metric_columns:
            panel, metric = _column_key(column)
            value = _to_optional_float(row[column])
            if value is None:
                continue
            is_std = 0
            if "_std" in metric:
                metric = metric.replace("_std", "", 1)
                is_std = 1
            measurement_rows.append((sample_id, panel, metric, value, is_std))

        if measurement_rows:
            cur.executemany(
                "INSERT OR REPLACE INTO benchling_measurement "
                "(sample_id, panel, metric, value, is_std) VALUES (?, ?, ?, ?, ?)",
                measurement_rows,
            )
    conn.commit()


def import_process_table(
    conn: sqlite3.Connection,
    experiment_id: int,
    process_table: pd.DataFrame,
    vendor: str,
) -> None:
    """Imports a consolidated process DataFrame into process_file + process_measurement.

    Expects the shape returned by
    ``DataService._process_ferm_process_panels``: flat columns with
    ``Tank``/``Time (h)`` keys and raw vendor channel columns. Re-importing
    the same (experiment_id, tank) deletes and replaces the existing process
    file row and its measurements.

    Args:
        conn: Open SQLite connection.
        experiment_id: Parent experiment's primary key.
        process_table: Consolidated process table, one row per tank per timepoint.
        vendor: Process file vendor/format, 'Eve' or 'Pi'.
    """
    if process_table.empty:
        return
    cur = conn.cursor()
    metric_columns = [c for c in process_table.columns if c not in _PROCESS_KEY_COLUMNS]

    for tank, group in process_table.groupby("Tank"):
        tank = str(tank)
        cur.execute(
            "DELETE FROM process_file WHERE experiment_id = ? AND tank = ?",
            (experiment_id, tank),
        )
        cur.execute(
            "INSERT INTO process_file (experiment_id, tank, vendor) VALUES (?, ?, ?)",
            (experiment_id, tank, vendor),
        )
        process_file_id = int(cur.lastrowid)

        measurement_rows: List[Tuple[int, float, str, float]] = []
        for _, row in group.iterrows():
            time_h = float(row["Time (h)"])
            for column in metric_columns:
                value = _to_optional_float(row[column])
                if value is None:
                    continue
                measurement_rows.append((process_file_id, time_h, str(column), value))

        if measurement_rows:
            cur.executemany(
                "INSERT OR REPLACE INTO process_measurement "
                "(process_file_id, time_h, channel, value) VALUES (?, ?, ?, ?)",
                measurement_rows,
            )
    conn.commit()


def import_experiment(
    conn: sqlite3.Connection,
    project_name: str,
    exp: str,
    meta_table: pd.DataFrame,
    bench_table: pd.DataFrame,
    process_table: pd.DataFrame,
    process_vendor: str,
) -> int:
    """Imports all three raw tables for one experiment in a single call.

    Args:
        conn: Open SQLite connection.
        project_name: Project discriminator, e.g. 'helix' or 'spore'.
        exp: Experiment identifier, e.g. 'E001'.
        meta_table: Processed metadata table, one row per tank.
        bench_table: Consolidated Benchling table, one row per sample.
        process_table: Consolidated process table, one row per tank per timepoint.
        process_vendor: Process file vendor/format, 'Eve' or 'Pi'.

    Returns:
        The experiment's integer primary key.
    """
    project_id = get_or_create_project(conn, project_name)
    experiment_id = get_or_create_experiment(conn, project_id, exp)
    import_meta_table(conn, experiment_id, meta_table)
    import_benchling_table(conn, experiment_id, bench_table)
    import_process_table(conn, experiment_id, process_table, process_vendor)
    return experiment_id
