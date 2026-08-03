"""Generates a synthetic Project Helix SQLite database for local demo/testing.

Builds ``helix/helix.db`` (the local SQLite drive backing
:class:`biocanvas.db.local_database.LocalDataBase`, per
``sharepoint_data_dir`` in ``src/biocanvas/helix/config.yaml``) with
``N_EXPERIMENTS`` synthetic experiments, each with ``CONDITIONS`` ×
``REPLICATES_PER_CONDITION`` fermentation tanks. Every experiment gets a
Meta.csv, a Benchling.zip (one CSV per panel in ``benchling_panels``), and a
Pi.zip (one CSV per tank) with simple condition-dependent synthetic trends,
so the whole Connect -> Process -> plot pipeline has something to render.

Run with: ``pixi run python scripts/generate_demo_helix_db.py``
"""

import io
import os
import sqlite3
import zipfile
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from biocanvas.db.local_database import _SCHEMA_SQL

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(REPO_ROOT, "helix", "helix.db")

N_EXPERIMENTS = 10
CONDITIONS: Tuple[str, ...] = ("CondA", "CondB", "CondC")
REPLICATES_PER_CONDITION = 2
TIMEPOINTS_H: Tuple[float, ...] = (0.0, 24.0, 48.0, 72.0)
PROCESS_TIMEPOINTS_H: Tuple[float, ...] = tuple(float(t) for t in range(0, 73, 3))
EFT_H = 72.0
# Per-condition growth-rate multiplier driving all synthetic trends below.
CONDITION_RATE: Dict[str, float] = {"CondA": 1.0, "CondB": 1.25, "CondC": 0.8}
RNG = np.random.default_rng(seed=42)

BENCHLING_PANELS: Tuple[str, ...] = (
    "Sample",
    "Ferm",
    "Sugar",
    "Acids",
    "Ammonia",
    "Phs",
    "Lcuv",
    "Brad",
    "Biochem",
)


class Tank:
    """One synthetic fermentation tank within an experiment."""

    def __init__(self, tank_num: int, condition: str, replicate: int) -> None:
        self.tank_num = tank_num
        self.tank_id = f"L{tank_num}"
        self.condition = condition
        self.replicate = replicate
        self.rate = CONDITION_RATE[condition]

    def sample_label(self, t: float) -> str:
        return f"{self.tank_id}-R{self.replicate}-T{int(t)}h"


def _build_tanks() -> List[Tank]:
    tanks: List[Tank] = []
    tank_num = 1
    for condition in CONDITIONS:
        for replicate in range(1, REPLICATES_PER_CONDITION + 1):
            tanks.append(Tank(tank_num, condition, replicate))
            tank_num += 1
    return tanks


def _noise(scale: float) -> float:
    return float(RNG.normal(loc=0.0, scale=scale))


def build_meta_csv(tanks: List[Tank]) -> bytes:
    """Builds Meta.csv content: one row per tank, all feed types Eve/Pi-controlled."""
    rows: List[Dict[str, object]] = []
    for tank in tanks:
        row: Dict[str, object] = {
            "Tank": tank.tank_id,
            "Condition": tank.condition,
            "Replicate": tank.replicate,
            "Strain Batch": f"STR{tank.tank_num:03d}-v1",
            "EFT (h)": EFT_H,
            "Media": "BasalMedia-v1",
            "Initial Broth Vol (ml)": 500.0,
            "pH Setpoint": 7.0,
            "Temp (°C) Setpoint": 30.0,
            "DO (%) Setpoint": 30.0,
        }
        for feed_type in ("Feed", "Co-feed", "Bolus", "Acid", "Base"):
            row[f"{feed_type} Source"] = ""
            row[f"Eve/Pi Controlled {feed_type}"] = "Yes"
            row[f"Manual {feed_type} Time Profile (h)"] = ""
            row[f"Manual Target {feed_type} Rate (ml/h)"] = ""
            # Read unconditionally by data_service._add_key_cols_to_eve for every
            # feed type (even when unused), so these must exist regardless of Source.
            row[f"{feed_type} Density (g/ml)"] = ""
            if feed_type in ("Feed", "Co-feed", "Bolus"):
                row[f"{feed_type} Element"] = ""
                row[f"Target {feed_type} Conc. (g/l)"] = ""
        rows.append(row)
    buf = io.StringIO()
    pd.DataFrame(rows).to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def _csv_bytes(df: pd.DataFrame) -> bytes:
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def build_benchling_zip(tanks: List[Tank]) -> bytes:
    """Builds Benchling.zip with one CSV per panel, covering every tank x timepoint."""
    panel_rows: Dict[str, List[Dict[str, object]]] = {
        panel: [] for panel in BENCHLING_PANELS
    }

    for tank in tanks:
        for t in TIMEPOINTS_H:
            frac = t / EFT_H
            sample = tank.sample_label(t)
            rate = tank.rate

            panel_rows["Sample"].append(
                {
                    "Entity": sample,
                    "Sample Volume (mL)": 2.0,
                    "Timepoint (h)": t,
                }
            )
            dcw = 2.0 + rate * 18.0 * frac + _noise(0.3)
            panel_rows["Ferm"].append(
                {
                    "Sample": sample,
                    "% Insoluble Solids": max(0.02, 0.08 + _noise(0.01)),
                    "DCW g/L": max(0.1, dcw),
                    "Broth Mass (mg)": 1000.0,
                    "Sample Volume (uL)": 1000.0,
                }
            )
            glucose = max(0.2, 20.0 * np.exp(-3.0 * rate * frac) + _noise(0.4))
            panel_rows["Sugar"].append({"Sample": sample, "Glucose (g/L)": glucose})
            acetate = max(0.0, rate * 3.0 * frac + _noise(0.15))
            panel_rows["Acids"].append({"Sample": sample, "Acetate (g/L)": acetate})
            ammonia = max(0.1, 5.0 - rate * 4.0 * frac + _noise(0.2))
            panel_rows["Ammonia"].append({"Sample": sample, "Ammonia (g/L)": ammonia})
            phosphate = max(0.1, 2.0 - 1.5 * frac + _noise(0.1))
            panel_rows["Phs"].append({"Sample": sample, "Phosphate (g/L)": phosphate})
            total_protein_lcuv = max(0.0, rate * 2.5 * frac + _noise(0.1))
            panel_rows["Lcuv"].append(
                {"Sample": sample, "Total Protein (g/L)": total_protein_lcuv}
            )
            bradford = max(0.0, rate * 2.0 * frac + _noise(0.1))
            panel_rows["Brad"].append(
                {"Sample": sample, "Bradford Protein (g/L)": bradford}
            )
            activity = max(0.0, rate * 0.5 * frac + _noise(0.03))
            panel_rows["Biochem"].append(
                {
                    "Sample": sample,
                    "Cellobiohydrolase Activity (umoles/g/s)": activity,
                }
            )

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for panel in BENCHLING_PANELS:
            df = pd.DataFrame(panel_rows[panel])
            zf.writestr(f"exp.{panel}.csv", _csv_bytes(df))
    return zip_buf.getvalue()


def build_pi_zip(tanks: List[Tank]) -> bytes:
    """Builds Pi.zip with one CSV per tank (filename ``exp.{tank_num}.csv``)."""
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for tank in tanks:
            rows: List[Dict[str, object]] = []
            for t in PROCESS_TIMEPOINTS_H:
                frac = t / EFT_H
                o2 = max(10.0, 21.0 - tank.rate * 6.0 * frac + _noise(0.2))
                co2 = max(0.04, 0.04 + tank.rate * 3.0 * frac + _noise(0.1))
                rows.append(
                    {
                        "TFT": t,
                        "Agitation (RPM)": 300.0 + _noise(3.0),
                        "Airflow (LPM)": 1.0,
                        "Dissolved Oxygen (%)": max(
                            5.0, 30.0 - tank.rate * 10.0 * frac + _noise(1.0)
                        ),
                        "N2, mol%": 78.0,
                        "O2, mol%": o2,
                        "CO2, mol%": co2,
                    }
                )
            df = pd.DataFrame(rows)
            zf.writestr(f"exp.{tank.tank_num}.csv", _csv_bytes(df))
    return zip_buf.getvalue()


def main() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA_SQL)

    exp_count = 0
    tank_count = 0
    for exp_num in range(1, N_EXPERIMENTS + 1):
        exp_name = f"Exp {exp_num:03d} Demo Run"
        tanks = _build_tanks()
        tank_count += len(tanks)

        meta_bytes = build_meta_csv(tanks)
        bench_bytes = build_benchling_zip(tanks)
        pi_bytes = build_pi_zip(tanks)

        conn.execute(
            "INSERT INTO items (path, parent_path, name, is_dir, content) VALUES (?, ?, ?, ?, ?)",
            (exp_name, "", exp_name, 1, None),
        )
        for fname, content in (
            ("Meta.csv", meta_bytes),
            ("Benchling.zip", bench_bytes),
            ("Pi.zip", pi_bytes),
        ):
            conn.execute(
                "INSERT INTO items (path, parent_path, name, is_dir, content) VALUES (?, ?, ?, ?, ?)",
                (f"{exp_name}/{fname}", exp_name, fname, 0, content),
            )
        exp_count += 1

    conn.commit()
    conn.close()
    print(f"Wrote {exp_count} experiment(s), {tank_count} tank(s) total, to {DB_PATH}")


if __name__ == "__main__":
    main()
