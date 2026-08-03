"""Tests for biocanvas.db (schema creation and raw-data import)."""

import sqlite3

import pandas as pd
import pytest

from biocanvas.db import importer, schema


class TestCreateSchema:
    """Tests for schema.create_schema."""

    def test_create_schema_is_idempotent(self, db_conn: sqlite3.Connection):
        """Calling create_schema twice on the same connection does not raise."""
        schema.create_schema(db_conn)
        cur = db_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='tank_meta'"
        )
        assert cur.fetchone() is not None


class TestImportMetaTable:
    """Tests for importer.import_meta_table."""

    @staticmethod
    def _import(
        db_conn: sqlite3.Connection, meta_table_for_augment: pd.DataFrame
    ) -> int:
        project_id = importer.get_or_create_project(db_conn, "helix")
        experiment_id = importer.get_or_create_experiment(db_conn, project_id, "E001")
        importer.import_meta_table(db_conn, experiment_id, meta_table_for_augment)
        return experiment_id

    def test_round_trip(
        self, db_conn: sqlite3.Connection, meta_table_for_augment: pd.DataFrame
    ):
        """One tank_meta row per Tank, with QC'd numeric columns preserved."""
        experiment_id = self._import(db_conn, meta_table_for_augment)
        rows = db_conn.execute(
            "SELECT tank, eft_h, ph_setpoint, do_setpoint_pct FROM tank_meta "
            "WHERE experiment_id = ? ORDER BY tank",
            (experiment_id,),
        ).fetchall()
        assert [r[0] for r in rows] == ["L1", "L2", "S1"]
        assert rows[0][1] == pytest.approx(100.0)
        assert rows[2][1] == pytest.approx(24.0)
        assert rows[0][2] == "4.8;4.0"
        assert rows[0][3] == "40.0"

    def test_feed_profiles_populated_only_for_real_sources(
        self, db_conn: sqlite3.Connection, meta_table_for_augment: pd.DataFrame
    ):
        """Feed profile rows exist only for feed types with a non-'NA' Source; sentinels preserved."""
        experiment_id = self._import(db_conn, meta_table_for_augment)

        l1_id = db_conn.execute(
            "SELECT tank_meta_id FROM tank_meta WHERE experiment_id = ? AND tank = ?",
            (experiment_id, "L1"),
        ).fetchone()[0]
        l1_feed_types = {
            r[0]
            for r in db_conn.execute(
                "SELECT feed_type FROM tank_feed_profile WHERE tank_meta_id = ?",
                (l1_id,),
            ).fetchall()
        }
        assert l1_feed_types == {"Feed", "Co-feed", "Bolus", "Acid", "Base"}

        s1_id = db_conn.execute(
            "SELECT tank_meta_id FROM tank_meta WHERE experiment_id = ? AND tank = ?",
            (experiment_id, "S1"),
        ).fetchone()[0]
        s1_count = db_conn.execute(
            "SELECT COUNT(*) FROM tank_feed_profile WHERE tank_meta_id = ?", (s1_id,)
        ).fetchone()[0]
        assert s1_count == 0

        l2_measured_added_feed = db_conn.execute(
            "SELECT measured_added_ml FROM tank_feed_profile "
            "WHERE tank_meta_id = (SELECT tank_meta_id FROM tank_meta WHERE experiment_id = ? AND tank = ?) "
            "AND feed_type = 'Feed'",
            (experiment_id, "L2"),
        ).fetchone()[0]
        assert l2_measured_added_feed == "NA"

    def test_reimport_overwrites_in_place(
        self, db_conn: sqlite3.Connection, meta_table_for_augment: pd.DataFrame
    ):
        """Re-importing the same (experiment_id, tank) replaces rather than duplicates rows."""
        experiment_id = self._import(db_conn, meta_table_for_augment)
        importer.import_meta_table(db_conn, experiment_id, meta_table_for_augment)

        tank_count = db_conn.execute(
            "SELECT COUNT(*) FROM tank_meta WHERE experiment_id = ?", (experiment_id,)
        ).fetchone()[0]
        assert tank_count == 3

        feed_count = db_conn.execute(
            "SELECT COUNT(*) FROM tank_feed_profile tfp "
            "JOIN tank_meta tm ON tm.tank_meta_id = tfp.tank_meta_id "
            "WHERE tm.experiment_id = ?",
            (experiment_id,),
        ).fetchone()[0]
        assert feed_count == 10  # 5 feed types x 2 populated tanks (L1, L2)


class TestImportBenchlingTable:
    """Tests for importer.import_benchling_table."""

    @staticmethod
    def _import(
        db_conn: sqlite3.Connection, raw_bench_table_for_augment: pd.DataFrame
    ) -> int:
        project_id = importer.get_or_create_project(db_conn, "helix")
        experiment_id = importer.get_or_create_experiment(db_conn, project_id, "E001")
        importer.import_benchling_table(
            db_conn, experiment_id, raw_bench_table_for_augment
        )
        return experiment_id

    def test_melts_to_long(
        self, db_conn: sqlite3.Connection, raw_bench_table_for_augment: pd.DataFrame
    ):
        """One benchling_sample row per (Tank, Time (h)) and one measurement row per populated cell."""
        experiment_id = self._import(db_conn, raw_bench_table_for_augment)

        sample_count = db_conn.execute(
            "SELECT COUNT(*) FROM benchling_sample WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()[0]
        assert sample_count == len(raw_bench_table_for_augment)

        measurement_count = db_conn.execute(
            "SELECT COUNT(*) FROM benchling_measurement bm "
            "JOIN benchling_sample bs ON bs.sample_id = bm.sample_id "
            "WHERE bs.experiment_id = ?",
            (experiment_id,),
        ).fetchone()[0]
        assert measurement_count == 60  # 6 metric columns x 10 rows, all populated

    def test_reconstructs_tank_and_value_via_join(
        self, db_conn: sqlite3.Connection, raw_bench_table_for_augment: pd.DataFrame
    ):
        """Joining benchling_measurement -> benchling_sample reconstructs Tank/Time (h)/value."""
        experiment_id = self._import(db_conn, raw_bench_table_for_augment)

        expected = raw_bench_table_for_augment[
            (raw_bench_table_for_augment["Tank"] == "L1")
            & (raw_bench_table_for_augment["Time (h)"] == 0.0)
        ][("Sugar", "Glucose (g/L)")].iloc[0]

        value = db_conn.execute(
            "SELECT bm.value FROM benchling_measurement bm "
            "JOIN benchling_sample bs ON bs.sample_id = bm.sample_id "
            "WHERE bs.experiment_id = ? AND bs.tank = ? AND bs.time_h = ? "
            "AND bm.panel = 'Sugar' AND bm.metric = 'Glucose (g/L)'",
            (experiment_id, "L1", 0.0),
        ).fetchone()[0]
        assert value == pytest.approx(expected)

    def test_pivots_back_to_wide_bench_table(
        self, db_conn: sqlite3.Connection, raw_bench_table_for_augment: pd.DataFrame
    ):
        """Long benchling_measurement rows pivot back to the original (panel, metric) values."""
        experiment_id = self._import(db_conn, raw_bench_table_for_augment)

        rows = db_conn.execute(
            "SELECT bs.tank, bs.time_h, bm.panel, bm.metric, bm.value "
            "FROM benchling_measurement bm "
            "JOIN benchling_sample bs ON bs.sample_id = bm.sample_id "
            "WHERE bs.experiment_id = ?",
            (experiment_id,),
        ).fetchall()
        long_df = pd.DataFrame(
            rows, columns=["Tank", "Time (h)", "panel", "metric", "value"]
        )
        wide = long_df.pivot_table(
            index=["Tank", "Time (h)"], columns=["panel", "metric"], values="value"
        ).reset_index()

        for tank, time_h, expected_dcw in [("L1", 0.0, 2.0), ("L2", 100.0, 5.0)]:
            reconstructed = wide[(wide["Tank"] == tank) & (wide["Time (h)"] == time_h)][
                ("Growth", "DCW (g/L)")
            ].iloc[0]
            assert reconstructed == pytest.approx(expected_dcw)


class TestImportProcessTable:
    """Tests for importer.import_process_table."""

    @staticmethod
    def _import(
        db_conn: sqlite3.Connection, raw_process_table_for_augment: pd.DataFrame
    ) -> int:
        project_id = importer.get_or_create_project(db_conn, "helix")
        experiment_id = importer.get_or_create_experiment(db_conn, project_id, "E001")
        importer.import_process_table(
            db_conn, experiment_id, raw_process_table_for_augment, "Eve"
        )
        return experiment_id

    def test_melts_to_long(
        self, db_conn: sqlite3.Connection, raw_process_table_for_augment: pd.DataFrame
    ):
        """One process_file row per Tank and one process_measurement row per populated cell."""
        experiment_id = self._import(db_conn, raw_process_table_for_augment)

        file_rows = db_conn.execute(
            "SELECT tank, vendor FROM process_file WHERE experiment_id = ? ORDER BY tank",
            (experiment_id,),
        ).fetchall()
        assert [r[0] for r in file_rows] == ["L1", "L2", "S1"]
        assert all(r[1] == "Eve" for r in file_rows)

        measurement_count = db_conn.execute(
            "SELECT COUNT(*) FROM process_measurement pm "
            "JOIN process_file pf ON pf.process_file_id = pm.process_file_id "
            "WHERE pf.experiment_id = ?",
            (experiment_id,),
        ).fetchone()[0]
        assert (
            measurement_count == len(raw_process_table_for_augment) * 2
        )  # 2 pump-volume channels

    def test_value_round_trip(
        self, db_conn: sqlite3.Connection, raw_process_table_for_augment: pd.DataFrame
    ):
        """A known (tank, time_h, channel) triple round-trips to its original value."""
        experiment_id = self._import(db_conn, raw_process_table_for_augment)
        value = db_conn.execute(
            "SELECT pm.value FROM process_measurement pm "
            "JOIN process_file pf ON pf.process_file_id = pm.process_file_id "
            "WHERE pf.experiment_id = ? AND pf.tank = ? AND pm.time_h = ? AND pm.channel = ?",
            (experiment_id, "L1", 24.0, "Acid Pump.Total volume, ml"),
        ).fetchone()[0]
        assert value == pytest.approx(0.0)

    def test_reimport_does_not_duplicate(
        self, db_conn: sqlite3.Connection, raw_process_table_for_augment: pd.DataFrame
    ):
        """Re-importing the same (experiment_id, tank) replaces rather than duplicates rows."""
        experiment_id = self._import(db_conn, raw_process_table_for_augment)
        importer.import_process_table(
            db_conn, experiment_id, raw_process_table_for_augment, "Eve"
        )

        file_count = db_conn.execute(
            "SELECT COUNT(*) FROM process_file WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()[0]
        assert file_count == 3

        measurement_count = db_conn.execute(
            "SELECT COUNT(*) FROM process_measurement pm "
            "JOIN process_file pf ON pf.process_file_id = pm.process_file_id "
            "WHERE pf.experiment_id = ?",
            (experiment_id,),
        ).fetchone()[0]
        assert measurement_count == len(raw_process_table_for_augment) * 2


class TestImportExperiment:
    """Tests for importer.import_experiment and multi-project isolation."""

    def test_multi_project_isolation(
        self,
        db_conn: sqlite3.Connection,
        meta_table_for_augment: pd.DataFrame,
        raw_bench_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
    ):
        """The same Exp id under two different projects stays isolated with no cross leakage."""
        helix_experiment_id = importer.import_experiment(
            db_conn,
            "helix",
            "E001",
            meta_table_for_augment,
            raw_bench_table_for_augment,
            raw_process_table_for_augment,
            "Eve",
        )
        spore_experiment_id = importer.import_experiment(
            db_conn,
            "spore",
            "E001",
            meta_table_for_augment,
            raw_bench_table_for_augment,
            raw_process_table_for_augment,
            "Eve",
        )

        assert helix_experiment_id != spore_experiment_id

        helix_tank_count = db_conn.execute(
            "SELECT COUNT(*) FROM tank_meta WHERE experiment_id = ?",
            (helix_experiment_id,),
        ).fetchone()[0]
        spore_tank_count = db_conn.execute(
            "SELECT COUNT(*) FROM tank_meta WHERE experiment_id = ?",
            (spore_experiment_id,),
        ).fetchone()[0]
        assert helix_tank_count == 3
        assert spore_tank_count == 3

        total_experiments = db_conn.execute(
            "SELECT COUNT(*) FROM experiment"
        ).fetchone()[0]
        assert total_experiments == 2
