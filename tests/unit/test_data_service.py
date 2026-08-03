"""Tests for biocanvas.data_service."""
import numpy as np
import pytest
import pandas as pd
from unittest.mock import MagicMock

from biocanvas import data_service


class TestAugmentTables:
    """
    Tests for the AugmentTables utility class in utils, ensuring correct augmentation
    of metadata, process, and bench tables. Covers:
      - Meta table integrity and output messages
      - Proper augmentation and column addition in process and bench tables
      - Handling of special cases like TRY KPI calculation and pump volume tracking

    These tests validate table transformations, output messaging, and conditional
    column population under various augmentation scenarios.
    """

    @staticmethod
    def _make_instance(
        meta: pd.DataFrame,
        bench: pd.DataFrame,
        process: pd.DataFrame,
        cfg: dict,
    ) -> data_service.AugmentTables:
        """Construct an AugmentTables instance and run augmentation using the given tables and config dict."""
        instance = data_service.AugmentTables(meta=meta, bench=bench, process=process)
        instance.augment(
            carbon_panels=cfg['carbon_panels'],
            panels_for_try=cfg['panels_for_try'],
            bench_cols_to_keep=cfg['bench_cols_to_keep'],
            process_cols_to_keep=cfg['process_cols_to_keep'],
            panel_display_names=cfg['panel_display_names'],
        )
        return instance

    # ------------------------------------------------------------------ #
    # Meta augmentation                                                    #
    # ------------------------------------------------------------------ #

    def test_meta_table_unchanged(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Checks that the augmented_meta_table is a deep copy of the input meta table,
        ensuring that no columns are added, removed, or modified during augmentation."""
   
        augmented = self._make_instance(
            meta_table_for_augment, pd.DataFrame(), raw_process_table_for_augment, augment_config
        )
        pd.testing.assert_frame_equal(augmented.augmented_meta_table, meta_table_for_augment)

    def test_meta_success_message(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """First output message confirms metadata was successfully augmented."""
        augmented = self._make_instance(
            meta_table_for_augment, pd.DataFrame(), raw_process_table_for_augment, augment_config
        )
        assert augmented.output_messages[0] == "Successfully augmented Metadata table."

    # ------------------------------------------------------------------ #
    # Process augmentation — empty input (synthetic table path)           #
    # ------------------------------------------------------------------ #

    def test_empty_process_creates_synthetic_table(
        self,
        meta_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Empty process input triggers synthetic table creation for fermentation tanks."""
        augmented = self._make_instance(
            meta_table_for_augment, pd.DataFrame(), pd.DataFrame(), augment_config
        )
        assert not augmented.augmented_process_table.empty

    def test_empty_process_excludes_seed_tanks(
        self,
        meta_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Seed tanks (names starting with 'S') are absent from the synthetic process table."""
        augmented = self._make_instance(
            meta_table_for_augment, pd.DataFrame(), pd.DataFrame(), augment_config
        )
        proc = augmented.augmented_process_table
        # After MultiIndex wrapping Tank lives at level ('Tank', '')
        tank_col = ('Tank', '') if isinstance(proc.columns, pd.MultiIndex) else 'Tank'
        tanks_in_process = proc[tank_col].unique()
        assert not any(str(t).startswith('S') for t in tanks_in_process)

    def test_empty_process_time_span_matches_eft(
        self,
        meta_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Synthetic process time range for each ferm tank extends to its EFT (h)."""
        augmented = self._make_instance(
            meta_table_for_augment, pd.DataFrame(), pd.DataFrame(), augment_config
        )
        proc = augmented.augmented_process_table
        tank_col = ('Tank', '') if isinstance(proc.columns, pd.MultiIndex) else 'Tank'
        time_col = ('Time (h)', '') if isinstance(proc.columns, pd.MultiIndex) else 'Time (h)'
        for _, row in meta_table_for_augment.iterrows():
            if not row['Tank'].startswith('S'):
                max_time = proc[proc[tank_col] == row['Tank']][time_col].max()
                assert max_time == pytest.approx(row['EFT (h)'])

    # ------------------------------------------------------------------ #
    # Process augmentation — non-empty input                              #
    # ------------------------------------------------------------------ #

    def test_process_augment_adds_exp_col(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """'Exp' column is added to the process table and wrapped into MultiIndex."""
        augmented = self._make_instance(
            meta_table_for_augment, pd.DataFrame(), raw_process_table_for_augment, augment_config
        )
        assert ('Exp', '') in augmented.augmented_process_table.columns

    def test_process_augment_adds_replicate_col(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """'Replicate' values in the augmented process table match the metadata per tank."""
        augmented = self._make_instance(
            meta_table_for_augment, pd.DataFrame(), raw_process_table_for_augment, augment_config
        )
        proc = augmented.augmented_process_table
        expected = meta_table_for_augment.set_index('Tank')['Replicate'].to_dict()
        for tank, expected_rep in expected.items():
            rows = proc[proc[('Tank', '')] == tank]
            assert (rows[('Replicate', '')] == expected_rep).all(), (
                f"Tank {tank}: expected Replicate={expected_rep}"
            )

    def test_process_augment_feed_totals_are_finite_for_ferm_tanks(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Feed-total columns exist and contain no NaN for ferm tanks after augmentation.

        With Acid and Base providing 'Acid Pump.Total volume, ml' = 0 in the process
        fixture, their Eve/Pi path returns 0 rather than NaN, so Total Fed Vol stays
        finite. The Bolus (manual, active at t = 50.05 h and t = 60.05 h) contributes
        a non-zero volume for L1 (Carbon Bolus) while L2 receives a Nitrogen Bolus
        (excluded from Added Carbon Weight).
        """
        augmented = self._make_instance(
            meta_table_for_augment, pd.DataFrame(), raw_process_table_for_augment, augment_config
        )
        proc = augmented.augmented_process_table
        ferm_mask = ~proc[('Tank', '')].str.startswith('S')
        for col_name in ['Total Fed Vol (ml)', 'Combined Feeds Weight (g)', 'Added Carbon Weight (g)']:
            col = proc.loc[ferm_mask, ('Process', col_name)]
            assert not col.isna().any(), f"NaN values found in '{col_name}' for ferm tanks"

    def test_process_augment_bolus_vol_nonzero_at_pulse_timepoints(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Total Fed Vol is non-zero at and after the Bolus pulse timepoints (t = 50.05 h
        and t = 60.05 h) confirming the manual pump calculation ran for ferm tanks."""
        augmented = self._make_instance(
            meta_table_for_augment, pd.DataFrame(), raw_process_table_for_augment, augment_config
        )
        proc = augmented.augmented_process_table
        tank_col = ('Tank', '')
        time_col = ('Time (h)', '')
        fed_col = ('Process', 'Total Fed Vol (ml)')
        for tank in ['L1', 'L2']:
            tank_rows = proc[proc[tank_col] == tank]
            # At t = 100 h (final timepoint), cumulative fed volume must be > 0
            final_vol = tank_rows.loc[tank_rows[time_col] == 100.0, fed_col]
            assert not final_vol.empty, f"No row at t=100 for tank {tank}"
            assert float(final_vol.iloc[0]) > 0, (
                f"Expected positive Total Fed Vol at t=100 for {tank}"
            )

    def test_process_final_columns_are_multiindex(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Final augmented process table exposes a MultiIndex column structure."""
        augmented = self._make_instance(
            meta_table_for_augment, pd.DataFrame(), raw_process_table_for_augment, augment_config
        )
        assert isinstance(augmented.augmented_process_table.columns, pd.MultiIndex)

    # ------------------------------------------------------------------ #
    # Bench augmentation — empty input                                    #
    # ------------------------------------------------------------------ #

    def test_empty_bench_stays_empty(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Empty bench input produces an empty augmented bench table with no success message."""
        augmented = self._make_instance(
            meta_table_for_augment, pd.DataFrame(), raw_process_table_for_augment, augment_config
        )
        assert augmented.augmented_bench_table.empty
        assert "Successfully augmented Benchling result table." not in augmented.output_messages

    # ------------------------------------------------------------------ #
    # Bench augmentation — non-empty input (seed-tank path)               #
    # ------------------------------------------------------------------ #

    def test_bench_augment_adds_exp_col(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_bench_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """'Exp' column is added to the bench table during augmentation."""
        augmented = self._make_instance(
            meta_table_for_augment, raw_bench_table_for_augment, raw_process_table_for_augment,
            augment_config,
        )
        assert 'Exp' in augmented.augmented_bench_table.columns

    def test_bench_augment_adds_replicate_col(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_bench_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """'Replicate' values in the augmented bench table match the metadata."""
        augmented = self._make_instance(
            meta_table_for_augment, raw_bench_table_for_augment, raw_process_table_for_augment,
            augment_config,
        )
        bench = augmented.augmented_bench_table
        expected_rep = meta_table_for_augment.set_index('Tank').loc['S1', 'Replicate']
        s1_rows = bench[bench['Tank'] == 'S1']
        assert (s1_rows['Replicate'] == expected_rep).all()

    def test_bench_seed_tank_broth_vol_equals_initial(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_bench_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Seed tank Total Broth Vol is set to Initial Broth Vol from the metadata."""
        augmented = self._make_instance(
            meta_table_for_augment, raw_bench_table_for_augment, raw_process_table_for_augment,
            augment_config,
        )
        expected_vol = meta_table_for_augment.set_index('Tank').loc['S1', 'Initial Broth Vol (ml)']
        s1_rows = augmented.augmented_bench_table[augmented.augmented_bench_table['Tank'] == 'S1']
        assert s1_rows['Total Broth Vol (ml)'].tolist() == pytest.approx([expected_vol] * len(s1_rows))

    # ------------------------------------------------------------------ #
    # TRY KPI calculation                                                  #
    # ------------------------------------------------------------------ #

    def test_ferm_kpi_exact_values_all_tables(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_bench_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Exact-value check for all four TRY KPI columns for ferm tank L1 using all three
        data sources (meta, process, bench).

        The four KPIs (Titer, Sp. Titer, cumulative Rate, Instantaneous Rate) are
        purely bench-derived and do not depend on the process-table feed volumes:

        Corrected Titer = raw (g/L) × (1 − IS% / 100)
        Sp. Titer       = Corrected Titer / DCW
        Rate            = Corrected Titer / Time  (NaN at t = 0)
        Ins. Rate       = ΔTiter / ΔTime          (NaN at t = 0)

        L1 bench fixture rows at [0, 24, 72, 100] h:
          t=0:   raw=0.0,  IS=2.0%,  DCW=2.0  → Titer=0.0,     Sp.=0.0,      Rate=NaN, Ins=NaN
          t=24:  raw=1.5,  IS=3.5%,  DCW=3.5  → Titer=1.4475,  Sp.=1.4475/3.5, Rate=1.4475/24, Ins=1.4475/24
          t=72:  raw=2.5,  IS=4.0%,  DCW=4.0  → Titer=2.4,     Sp.=0.6,        Rate=2.4/72,    Ins=0.9525/48
          t=100: raw=3.5,  IS=5.0%,  DCW=5.0  → Titer=3.325,   Sp.=0.665,      Rate=3.325/100, Ins=0.925/28
        """
        augmented = self._make_instance(
            meta_table_for_augment, raw_bench_table_for_augment, raw_process_table_for_augment,
            augment_config,
        )
        bench = augmented.augmented_bench_table
        l1 = bench[bench['Tank'] == 'L1'].sort_values('Time (h)').reset_index(drop=True)

        expected_titer    = [0.0,     1.4475,          2.4,       3.325    ]
        expected_sp_titer = [0.0,     1.4475 / 3.5,   2.4 / 4.0, 3.325 / 5.0]
        expected_rate     = [np.nan,  1.4475 / 24,    2.4 / 72,  3.325 / 100]
        expected_ins_rate = [np.nan,  1.4475 / 24,    0.9525 / 48, 0.925 / 28]

        for i, t in enumerate([0.0, 24.0, 72.0, 100.0]):
            row = l1.iloc[i]
            assert row[('Lcuv', 'TestProduct Titer (g/L)')] == pytest.approx(
                expected_titer[i]
            ), f"Titer mismatch at t={t}"

            assert row[('Lcuv', 'TestProduct Sp. Titer (g/g)')] == pytest.approx(
                expected_sp_titer[i]
            ), f"Sp. Titer mismatch at t={t}"

            if np.isnan(expected_rate[i]):
                assert np.isnan(row[('Lcuv', 'TestProduct Rate (g/L/h)')]), (
                    f"Rate at t={t} must be NaN"
                )
            else:
                assert row[('Lcuv', 'TestProduct Rate (g/L/h)')] == pytest.approx(
                    expected_rate[i]
                ), f"Rate mismatch at t={t}"

            if np.isnan(expected_ins_rate[i]):
                assert np.isnan(row[('Lcuv', 'TestProduct Ins. Rate (g/L/h)')]), (
                    f"Ins. Rate at t={t} must be NaN"
                )
            else:
                assert row[('Lcuv', 'TestProduct Ins. Rate (g/L/h)')] == pytest.approx(
                    expected_ins_rate[i]
                ), f"Ins. Rate mismatch at t={t}"

    def test_try_kpi_titer_corrected_for_insoluble_solids(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_bench_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Corrected titer = raw (g/L) × (1 − IS% / 100) for seed tank at t=24 h."""
        augmented = self._make_instance(
            meta_table_for_augment, raw_bench_table_for_augment, raw_process_table_for_augment,
            augment_config,
        )
        # raw_bench_table_for_augment fixture: S1 row at t=24 has TestProduct=1.5 g/L
        # and '% Insoluble Solids (g/g)' = 2.0 (the 10th row, index 9 in the fixture).
        raw_titer = 1.5
        insoluble_solids_pct = 2.0
        expected_titer = raw_titer * (1 - insoluble_solids_pct / 100)

        bench = augmented.augmented_bench_table
        s1_t24 = bench[(bench['Tank'] == 'S1') & (bench['Time (h)'] == 24.0)].iloc[0]
        assert s1_t24[('Lcuv', 'TestProduct Titer (g/L)')] == pytest.approx(expected_titer)

    def test_try_kpi_drops_raw_titer_column(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_bench_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Raw (g/L) product column is removed from the bench table after KPI correction."""
        augmented = self._make_instance(
            meta_table_for_augment, raw_bench_table_for_augment, raw_process_table_for_augment,
            augment_config,
        )
        assert ('Lcuv', 'TestProduct (g/L)') not in augmented.augmented_bench_table.columns

    def test_try_kpi_rate_columns_present(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_bench_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Sp. Titer, cumulative Rate, and Instantaneous Rate columns are added."""
        augmented = self._make_instance(
            meta_table_for_augment, raw_bench_table_for_augment, raw_process_table_for_augment,
            augment_config,
        )
        cols = augmented.augmented_bench_table.columns
        assert ('Lcuv', 'TestProduct Sp. Titer (g/g)') in cols
        assert ('Lcuv', 'TestProduct Rate (g/L/h)') in cols
        assert ('Lcuv', 'TestProduct Ins. Rate (g/L/h)') in cols

    def test_try_kpi_weight_yield_only_when_flag_true(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_bench_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Product Weight and Yield columns exist in the combined bench table (populated by
        ferm tanks) but are NaN for seed-tank rows because _compute_try_kpis is called
        with include_weight_yield=False for seed tanks."""
        augmented = self._make_instance(
            meta_table_for_augment, raw_bench_table_for_augment, raw_process_table_for_augment,
            augment_config,
        )
        bench = augmented.augmented_bench_table
        s1_rows = bench[bench['Tank'] == 'S1']

        # Columns exist in the table (populated by ferm-tank rows)
        assert ('Lcuv', 'TestProduct Weight (g)') in bench.columns
        assert ('Lcuv', 'TestProduct Yield (g/g)') in bench.columns

        # Seed-tank rows carry NaN for those columns
        assert s1_rows[('Lcuv', 'TestProduct Weight (g)')].isna().all()
        assert s1_rows[('Lcuv', 'TestProduct Yield (g/g)')].isna().all()

        # Verify the same product columns DO appear with include_weight_yield=True
        grp = pd.DataFrame({
            ('Lcuv', 'TestProduct (g/L)'):                 [0.0,   1.5],
            ('Growth', '% Insoluble Solids (g/g)'):         [0.0,  10.0],
            ('Growth', 'DCW (g/L)'):                        [2.0,   3.5],
            'Time (h)':                                      [0.0,  12.0],
            'Total Broth Vol (ml)':                          [200.0, 200.0],
            'Total Carbon Consumed (g)':                     [0.0,   5.0],
        })
        result = augmented._compute_try_kpis(
            grp.copy(),
            augment_config['panels_for_try'],
            augment_config['panel_display_names'],
            include_weight_yield=True,
        )
        assert ('Lcuv', 'TestProduct Weight (g)') in result.columns
        assert ('Lcuv', 'TestProduct Yield (g/g)') in result.columns

    # ------------------------------------------------------------------ #
    # Output messages                                                      #
    # ------------------------------------------------------------------ #

    def test_output_messages_full_success(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_bench_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """All three success messages appear when meta, process, and bench augment cleanly."""
        augmented = self._make_instance(
            meta_table_for_augment, raw_bench_table_for_augment, raw_process_table_for_augment,
            augment_config,
        )
        msgs = augmented.output_messages
        assert any("Successfully augmented Metadata table" in m for m in msgs)
        assert any("Successfully augmented Eve table" in m for m in msgs)
        assert any("Successfully augmented Benchling result table" in m for m in msgs)

    # ------------------------------------------------------------------ #
    # Pump volume — Path A (Eve/Pi internal pump total)                   #
    # ------------------------------------------------------------------ #

    def test_path_a_pumped_vol_equals_pump_total_column(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Path A: Pumped Feed Vol is read verbatim from the pump-total process column.

        The EX-tank process fixture sets ``Feed Pump.Total volume, ml`` to
        [0, 10, 10, 10, 20, 30] at t = [0, 10, 10.05, 10.1, 20, 30].
        The pump total is held constant at the two bolus-bracket timepoints
        (10.05 and 10.1) because no Feed pump activity occurs there.
        After augmentation ``Pumped Feed Vol (ml)`` must reproduce those values.
        """
        augmented = self._make_instance(
            meta_exact_for_augment, pd.DataFrame(), process_exact_for_augment, augment_config_exact
        )
        proc = augmented.augmented_process_table
        ex_rows = proc[proc[('Tank', '')] == 'EX'].sort_values(('Time (h)', ''))
        pumped_feed = ex_rows[('Process', 'Pumped Feed Vol (ml)')].tolist()
        assert pumped_feed == pytest.approx([0.0, 10.0, 10.0, 10.0, 20.0, 30.0])

    # ------------------------------------------------------------------ #
    # Pump volume — Path B (calibrated pump rate)                         #
    # ------------------------------------------------------------------ #

    def test_path_b_pumped_vol_equals_calibrated_formula(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Path B: Pumped Co-feed Vol = max_calib_rate × duty% × duration_s.

        Max Calib. Co-feed Pump Rate = 0.002 ml/s.  The Co-feed %, Duration
        snapshot values are held constant at the two bolus-bracket timepoints
        (10.05 and 10.1), so those rows produce the same value as t = 10.

        t=0:    0.002 × 0   × 0   =  0 ml
        t=10:   0.002 × 50  × 100 = 10 ml
        t=10.05 0.002 × 50  × 100 = 10 ml  (snapshot unchanged)
        t=10.1: 0.002 × 50  × 100 = 10 ml  (snapshot unchanged)
        t=20:   0.002 × 100 × 200 = 40 ml
        t=30:   0.002 × 100 × 300 = 60 ml
        """
        augmented = self._make_instance(
            meta_exact_for_augment, pd.DataFrame(), process_exact_for_augment, augment_config_exact
        )
        proc = augmented.augmented_process_table
        ex_rows = proc[proc[('Tank', '')] == 'EX'].sort_values(('Time (h)', ''))
        cofeed = ex_rows[('Process', 'Pumped Co-feed Vol (ml)')].tolist()
        assert cofeed == pytest.approx([0.0, 10.0, 10.0, 10.0, 40.0, 60.0])

    # ------------------------------------------------------------------ #
    # Pump volume — Path C (manual profile, trapezoidal integration)      #
    # ------------------------------------------------------------------ #

    def test_path_c_pumped_vol_via_trapezoidal_integration(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Path C: Bolus is a delta-function pulse captured by two bracketing timepoints.

        Profile '10-10.05' at 200 ml/h over process times [0, 10, 10.05, 10.1, 20, 30]:
        - Rates:        [0,   0,   200, 0,   0,   0]
          (condition: t > 10 AND t <= 10.05; only t=10.05 is inside the window)
        - rolling(2).mean():  [NaN, 0,  100, 100, 0,   0]
        - × diff(t):          [NaN, 10, 0.05, 0.05, 9.9, 10]
        - products:           [  0, 0,   5,   5,   0,   0]
        - cumsum (fillna=0):  [  0, 0,   5,  10,  10,  10]

        t=10.05 captures the leading half; t=10.1 captures the trailing half,
        both totalling 10 ml.  The volume stays constant at 10 ml afterwards.
        """
        augmented = self._make_instance(
            meta_exact_for_augment, pd.DataFrame(), process_exact_for_augment, augment_config_exact
        )
        proc = augmented.augmented_process_table
        ex_rows = proc[proc[('Tank', '')] == 'EX'].sort_values(('Time (h)', ''))
        bolus = ex_rows[('Process', 'Pumped Bolus Vol (ml)')].tolist()
        assert bolus == pytest.approx([0.0, 0.0, 5.0, 10.0, 10.0, 10.0])

    # ------------------------------------------------------------------ #
    # Pump volume — bottle-weight correction                              #
    # ------------------------------------------------------------------ #

    def test_bottle_weight_correction_scales_profile_by_factor(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Bottle-weight correction scales the entire pumped-vol profile by measured/total_at_EFT.

        CR tank: raw pump total at EFT=30 h is 30 ml; Measured Added Feed = 60 ml.
        Correction factor = 60 / 30 = 2.0  →  corrected vols = [0, 20, 40, 60].
        """
        augmented = self._make_instance(
            meta_exact_for_augment, pd.DataFrame(), process_exact_for_augment, augment_config_exact
        )
        proc = augmented.augmented_process_table
        cr_rows = proc[proc[('Tank', '')] == 'CR'].sort_values(('Time (h)', ''))
        pumped_feed = cr_rows[('Process', 'Pumped Feed Vol (ml)')].tolist()
        assert pumped_feed == pytest.approx([0.0, 20.0, 40.0, 60.0])

    # ------------------------------------------------------------------ #
    # Aggregate feed columns                                              #
    # ------------------------------------------------------------------ #

    def test_total_fed_vol_equals_sum_of_individual_feeds(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Total Fed Vol = sum of all active Pumped {type} Vol columns at each timepoint.

        EX tank at t = [0, 10, 10.05, 10.1, 20, 30]:
        - Feed (A):    [0,  10,  10,  10,  20,  30]
        - Co-feed (B): [0,  10,  10,  10,  40,  60]
        - Bolus (C):   [0,   0,   5,  10,  10,  10]
        Total:         [0,  20,  25,  30,  70, 100]
        """
        augmented = self._make_instance(
            meta_exact_for_augment, pd.DataFrame(), process_exact_for_augment, augment_config_exact
        )
        proc = augmented.augmented_process_table
        ex_rows = proc[proc[('Tank', '')] == 'EX'].sort_values(('Time (h)', ''))
        total_fed = ex_rows[('Process', 'Total Fed Vol (ml)')].tolist()
        assert total_fed == pytest.approx([0.0, 20.0, 25.0, 30.0, 70.0, 100.0])

    def test_combined_feeds_weight_uses_feed_density(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Combined Feeds Weight = sum of Pumped Vol × density for each active feed.

        Densities: Feed=1.0, Co-feed=1.1, Bolus=1.2 g/ml.

        EX at t = [0, 10, 10.05, 10.1, 20, 30]:
        - Feed (A)   × 1.0: [0,  10,  10,  10,  20,  30]
        - Co-feed (B)× 1.1: [0,  11,  11,  11,  44,  66]
        - Bolus (C)  × 1.2: [0,   0,   6,  12,  12,  12]
        Total:              [0,  21,  27,  33,  76, 108]
        """
        augmented = self._make_instance(
            meta_exact_for_augment, pd.DataFrame(), process_exact_for_augment, augment_config_exact
        )
        proc = augmented.augmented_process_table
        ex_rows = proc[proc[('Tank', '')] == 'EX'].sort_values(('Time (h)', ''))
        weights = ex_rows[('Process', 'Combined Feeds Weight (g)')].tolist()
        assert weights == pytest.approx([0.0, 21.0, 27.0, 33.0, 76.0, 108.0])

    def test_added_carbon_weight_excludes_non_carbon_feeds(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Added Carbon Weight sums only feeds whose Element = 'Carbon'.

        EX tank: Co-feed Element = 'Nitrogen', so it is excluded.

        At t = [0, 10, 10.05, 10.1, 20, 30]
        (Feed @500 g/L, Bolus @200 g/L; Co-feed excluded as Nitrogen):
        - Feed:  vol/1000 × 500: [0,   5,   5,   5,  10,  15]
        - Bolus: vol/1000 × 200: [0,   0,   1,   2,   2,   2]
        Total:                   [0,   5,   6,   7,  12,  17]
        """
        augmented = self._make_instance(
            meta_exact_for_augment, pd.DataFrame(), process_exact_for_augment, augment_config_exact
        )
        proc = augmented.augmented_process_table
        ex_rows = proc[proc[('Tank', '')] == 'EX'].sort_values(('Time (h)', ''))
        carbon_wt = ex_rows[('Process', 'Added Carbon Weight (g)')].tolist()
        assert carbon_wt == pytest.approx([0.0, 5.0, 6.0, 7.0, 12.0, 17.0])

    # ------------------------------------------------------------------ #
    # Sample tracking                                                     #
    # ------------------------------------------------------------------ #

    def test_removed_sample_vol_accumulates_stepwise_in_process(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        bench_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Removed Sample Vol accumulates in the process table at process times > each sample time.

        Bench fixture: samples taken at t=10 (5 ml) and t=20 (5 ml).
        Condition is strict: ``process_t > sample_t``.

        Expected at process times [0, 10, 10.05, 10.1, 20, 30]:
        - t=0:     0  (no samples yet)
        - t=10:    0  (10 > 10 is False)
        - t=10.05: 5  (10.05 > 10 True;  10.05 > 20 False)
        - t=10.1:  5  (10.1  > 10 True;  10.1  > 20 False)
        - t=20:    5  (20    > 10 True;   20    > 20 False)
        - t=30:   10  (30    > 10 True;   30    > 20 True)
        """
        augmented = self._make_instance(
            meta_exact_for_augment, bench_exact_for_augment, process_exact_for_augment,
            augment_config_exact,
        )
        proc = augmented.augmented_process_table
        ex_rows = proc[proc[('Tank', '')] == 'EX'].sort_values(('Time (h)', ''))
        removed_vol = ex_rows[('Process', 'Removed Sample Vol (ml)')].tolist()
        assert removed_vol == pytest.approx([0.0, 0.0, 5.0, 5.0, 5.0, 10.0])

    # ------------------------------------------------------------------ #
    # Bench — ferm tank broth volume                                      #
    # ------------------------------------------------------------------ #

    def test_bench_ferm_broth_vol_accounts_for_feed_and_sampling(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        bench_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Ferm-tank Total Broth Vol = Initial + Total Fed Vol − cumulative Sample Vol.

        The bench table joins to the process table at exact bench timepoints
        [0, 10, 20, 30].  With the delta-bolus fixture, Total Fed Vol from the
        process table at those times is [0, 20, 70, 100] ml (Bolus contributes
        0 at t=10, as the pulse occurs between t=10 and t=10.1).

        EX tank (Initial = 1000 ml), Sample cumsum = [0, 5, 10, 10]:
        - t=0:  1000 +   0 −  0 = 1000 ml
        - t=10: 1000 +  20 −  5 = 1015 ml
        - t=20: 1000 +  70 − 10 = 1060 ml
        - t=30: 1000 + 100 − 10 = 1090 ml
        """
        augmented = self._make_instance(
            meta_exact_for_augment, bench_exact_for_augment, process_exact_for_augment,
            augment_config_exact,
        )
        bench = augmented.augmented_bench_table
        ex_rows = bench[bench['Tank'] == 'EX'].sort_values('Time (h)')
        broth_vol = ex_rows['Total Broth Vol (ml)'].tolist()
        assert broth_vol == pytest.approx([1000.0, 1015.0, 1060.0, 1090.0])

    # ------------------------------------------------------------------ #
    # Bench — carbon balance                                              #
    # ------------------------------------------------------------------ #

    def test_bench_total_carbon_in_broth_exact_value(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        bench_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Total Carbon in Broth = Total Broth Vol / 1000 × sum(carbon-panel analytes).

        Carbon panels: {'Sugar': ['Glucose', 'Lactose']}.

        EX broth vols (with delta-bolus fixture): [1000, 1015, 1060, 1090] ml.
        Substrate concentrations: Glucose+Lactose = [12, 6, 0, 0] g/L.

        EX at t=0:  1000/1000 × 12 = 12.0 g
        EX at t=10: 1015/1000 × 6  =  6.09 g
        EX at t=20: 1060/1000 × 0  =  0 g
        """
        augmented = self._make_instance(
            meta_exact_for_augment, bench_exact_for_augment, process_exact_for_augment,
            augment_config_exact,
        )
        bench = augmented.augmented_bench_table
        ex_rows = bench[bench['Tank'] == 'EX'].sort_values('Time (h)')
        carbon_in = ex_rows['Total Carbon in Broth (g)'].tolist()
        assert carbon_in[0] == pytest.approx(12.0)            # t=0:  1000/1000 × 12
        assert carbon_in[1] == pytest.approx(6.09)            # t=10: 1015/1000 × 6
        assert carbon_in[2] == pytest.approx(0.0)             # t=20: substrate depleted
        assert carbon_in[3] == pytest.approx(0.0)             # t=30

    def test_bench_total_carbon_consumed_exact_value(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        bench_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Total Carbon Consumed = initial_C_in_broth + Added Carbon Weight − Carbon in Broth.

        initial_C = 12 g (at t=0).
        Added Carbon Weight at bench times [0, 10, 20, 30] = [0, 5, 12, 17] g
        (Bolus contributes 0 at bench t=10 because the pulse fires between
        t=10 and t=10.1, which are not bench timepoints).

        t=0:  12 +  0 − 12    = 0 g
        t=20: 12 + 12 −  0    = 24 g
        t=30: 12 + 17 −  0    = 29 g
        """
        augmented = self._make_instance(
            meta_exact_for_augment, bench_exact_for_augment, process_exact_for_augment,
            augment_config_exact,
        )
        bench = augmented.augmented_bench_table
        ex_rows = bench[bench['Tank'] == 'EX'].sort_values('Time (h)')
        consumed = ex_rows['Total Carbon Consumed (g)'].tolist()
        assert consumed[0] == pytest.approx(0.0)              # t=0:  no net consumption yet
        assert consumed[2] == pytest.approx(24.0)             # t=20
        assert consumed[3] == pytest.approx(29.0)             # t=30

    def test_bench_carbon_consumed_is_non_decreasing(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        bench_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Total Carbon Consumed must be non-decreasing when substrates deplete over time."""
        augmented = self._make_instance(
            meta_exact_for_augment, bench_exact_for_augment, process_exact_for_augment,
            augment_config_exact,
        )
        bench = augmented.augmented_bench_table
        ex_rows = bench[bench['Tank'] == 'EX'].sort_values('Time (h)')
        consumed = ex_rows['Total Carbon Consumed (g)'].tolist()
        assert all(consumed[i] <= consumed[i + 1] for i in range(len(consumed) - 1))

    # ------------------------------------------------------------------ #
    # TRY KPIs — exact values                                             #
    # ------------------------------------------------------------------ #

    def test_try_kpi_zero_is_leaves_titer_unchanged(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        bench_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """When % Insoluble Solids = 0, corrected titer equals the raw titer."""
        augmented = self._make_instance(
            meta_exact_for_augment, bench_exact_for_augment, process_exact_for_augment,
            augment_config_exact,
        )
        bench = augmented.augmented_bench_table
        ex_rows = bench[bench['Tank'] == 'EX'].sort_values('Time (h)')
        titer = ex_rows[('Lcuv', 'TestProduct Titer (g/L)')].tolist()
        assert titer == pytest.approx([0.0, 0.5, 1.0, 1.5])

    def test_try_kpi_specific_titer_exact_value(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        bench_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Sp. Titer = Corrected Titer / DCW at each timepoint.

        EX: Titer=[0, 0.5, 1.0, 1.5], DCW=[1, 2, 3, 4]
        → Sp. Titer = [0, 0.25, 0.333…, 0.375]
        """
        augmented = self._make_instance(
            meta_exact_for_augment, bench_exact_for_augment, process_exact_for_augment,
            augment_config_exact,
        )
        bench = augmented.augmented_bench_table
        ex_rows = bench[bench['Tank'] == 'EX'].sort_values('Time (h)')
        sp_titer = ex_rows[('Lcuv', 'TestProduct Sp. Titer (g/g)')].tolist()
        assert sp_titer[0] == pytest.approx(0.0)
        assert sp_titer[1] == pytest.approx(0.25)
        assert sp_titer[2] == pytest.approx(1.0 / 3.0)
        assert sp_titer[3] == pytest.approx(0.375)

    def test_try_kpi_cumulative_rate_exact_value(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        bench_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Cumulative Rate = Titer / Time at each timepoint (NaN at t=0).

        EX: Titer=[0, 0.5, 1.0, 1.5], Time=[0, 10, 20, 30]
        → Rate = [NaN, 0.05, 0.05, 0.05] g/L/h
        """
        augmented = self._make_instance(
            meta_exact_for_augment, bench_exact_for_augment, process_exact_for_augment,
            augment_config_exact,
        )
        bench = augmented.augmented_bench_table
        ex_rows = bench[bench['Tank'] == 'EX'].sort_values('Time (h)')
        rate = ex_rows[('Lcuv', 'TestProduct Rate (g/L/h)')].tolist()
        assert np.isnan(rate[0]), "Cumulative Rate at t=0 must be NaN (0/0)"
        assert rate[1] == pytest.approx(0.05)
        assert rate[2] == pytest.approx(0.05)
        assert rate[3] == pytest.approx(0.05)

    def test_try_kpi_instantaneous_rate_nan_at_t0(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        bench_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Instantaneous Rate at t=0 must be NaN because diff() has no previous timepoint."""
        augmented = self._make_instance(
            meta_exact_for_augment, bench_exact_for_augment, process_exact_for_augment,
            augment_config_exact,
        )
        bench = augmented.augmented_bench_table
        ex_rows = bench[bench['Tank'] == 'EX'].sort_values('Time (h)')
        ins_rate_t0 = ex_rows[('Lcuv', 'TestProduct Ins. Rate (g/L/h)')].iloc[0]
        assert np.isnan(ins_rate_t0)

    def test_try_kpi_instantaneous_rate_exact_value(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        bench_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Instantaneous Rate = ΔTiter / ΔTime between consecutive bench samples.

        EX: Titer steps of +0.5 g/L every 10 h → Ins. Rate = 0.05 g/L/h at t > 0.
        """
        augmented = self._make_instance(
            meta_exact_for_augment, bench_exact_for_augment, process_exact_for_augment,
            augment_config_exact,
        )
        bench = augmented.augmented_bench_table
        ex_rows = bench[bench['Tank'] == 'EX'].sort_values('Time (h)')
        ins_rate = ex_rows[('Lcuv', 'TestProduct Ins. Rate (g/L/h)')].tolist()
        assert ins_rate[1] == pytest.approx(0.05)    # t=10: (0.5-0)/10
        assert ins_rate[2] == pytest.approx(0.05)    # t=20: (1.0-0.5)/10
        assert ins_rate[3] == pytest.approx(0.05)    # t=30: (1.5-1.0)/10

    def test_try_kpi_product_weight_exact_value(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        bench_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Product Weight = Corrected Titer × Total Broth Vol / 1000 (g).

        EX broth vols (delta-bolus fixture): [1000, 1015, 1060, 1090] ml.

        - t=0:  0.0 × 1000 / 1000 = 0.0   g
        - t=10: 0.5 × 1015 / 1000 = 0.5075 g
        - t=30: 1.5 × 1090 / 1000 = 1.635  g
        """
        augmented = self._make_instance(
            meta_exact_for_augment, bench_exact_for_augment, process_exact_for_augment,
            augment_config_exact,
        )
        bench = augmented.augmented_bench_table
        ex_rows = bench[bench['Tank'] == 'EX'].sort_values('Time (h)')
        weight = ex_rows[('Lcuv', 'TestProduct Weight (g)')].tolist()
        assert weight[0] == pytest.approx(0.0)
        assert weight[1] == pytest.approx(0.5075)
        assert weight[3] == pytest.approx(1.635)

    def test_try_kpi_product_yield_exact_value(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        bench_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """Product Yield = Product Weight / Total Carbon Consumed (g/g).

        EX (delta-bolus fixture):
        - t=20: Weight = 1.0 × 1060/1000 = 1.060 g,  Consumed = 24 g → 1.060/24
        - t=30: Weight = 1.5 × 1090/1000 = 1.635 g,  Consumed = 29 g → 1.635/29
        """
        augmented = self._make_instance(
            meta_exact_for_augment, bench_exact_for_augment, process_exact_for_augment,
            augment_config_exact,
        )
        bench = augmented.augmented_bench_table
        ex_rows = bench[bench['Tank'] == 'EX'].sort_values('Time (h)')
        yield_ = ex_rows[('Lcuv', 'TestProduct Yield (g/g)')].tolist()
        assert np.isnan(yield_[0]), "Yield at t=0 must be NaN (Carbon Consumed = 0)"
        assert yield_[2] == pytest.approx(1.060 / 24.0)
        assert yield_[3] == pytest.approx(1.635 / 29.0)

    def test_try_kpi_missing_product_column_is_gracefully_skipped(
        self,
        meta_exact_for_augment: pd.DataFrame,
        process_exact_for_augment: pd.DataFrame,
        bench_exact_for_augment: pd.DataFrame,
        augment_config_exact: dict,
    ):
        """A panels_for_try entry whose column is absent from the bench table causes no error.

        Override panels_for_try with a product ('GhostProduct') that does not
        exist in bench_exact_for_augment. Augmentation must succeed and the
        bench table must not contain any 'GhostProduct' column.
        """
        cfg = dict(augment_config_exact)
        cfg['panels_for_try'] = {'Lcuv': ['GhostProduct']}
        augmented = self._make_instance(
            meta_exact_for_augment, bench_exact_for_augment, process_exact_for_augment, cfg
        )
        assert any("Successfully augmented Benchling result table" in m
                   for m in augmented.output_messages)
        bench_cols = augmented.augmented_bench_table.columns.tolist()
        assert not any('GhostProduct' in str(c) for c in bench_cols)

    # ------------------------------------------------------------------ #
    # Structural — seed-tank feed skip                                    #
    # ------------------------------------------------------------------ #

    def test_process_seed_tank_skips_all_feed_columns(
        self,
        meta_table_for_augment: pd.DataFrame,
        raw_process_table_for_augment: pd.DataFrame,
        augment_config: dict,
    ):
        """Seed tanks (name starts with 'S') have no Pumped-Vol or feed-aggregate columns.

        The augmentation logic returns early for seed tanks after setting
        Replicate, so no 'Pumped * Vol', 'Total Fed Vol', 'Combined Feeds
        Weight', or 'Added Carbon Weight' columns should appear for S1 in the
        flat (pre-filter) process table.
        """
        augmented = self._make_instance(
            meta_table_for_augment, pd.DataFrame(), raw_process_table_for_augment, augment_config
        )
        proc = augmented.augmented_process_table
        s1_rows = proc[proc[('Tank', '')] == 'S1']
        feed_cols = [c for c in proc.columns
                     if isinstance(c, tuple) and c[0] == 'Process'
                     and any(kw in c[1] for kw in ['Pumped', 'Fed', 'Feeds', 'Carbon'])]
        for col in feed_cols:
            assert s1_rows[col].isna().all(), (
                f"Seed tank S1 should have NaN for feed column {col}"
            )


class TestProcessFermPanels:
    """Tests for DataService._process_ferm_process_panels partial concat behaviour."""

    def test_partial_success_when_one_tank_missing(
        self,
        service_with_ferm_module,
        meta_two_ferm_tanks: pd.DataFrame,
        eve_zip_with_tanks,
    ):
        """Zip with only M1 still returns data for the successful tank."""
        zf = eve_zip_with_tanks([1])
        table, messages = service_with_ferm_module._process_ferm_process_panels(
            zf, meta_two_ferm_tanks, 'EveTable',
        )
        assert not table.empty
        assert 'M1' in table['Tank'].values
        assert any('Successfully processed' in m for m in messages)

    def test_empty_when_all_ferm_tanks_fail(
        self,
        service_with_ferm_module,
        meta_two_ferm_tanks: pd.DataFrame,
        eve_zip_with_tanks,
    ):
        """Zip with no matching ferm tanks returns an empty table."""
        zf = eve_zip_with_tanks([99])
        table, messages = service_with_ferm_module._process_ferm_process_panels(
            zf, meta_two_ferm_tanks, 'EveTable',
        )
        assert table.empty
        assert any('No Eve/Pi tanks processed successfully' in m for m in messages)

    def test_extra_zip_member_does_not_block_partial_result(
        self,
        service_with_ferm_module,
        meta_two_ferm_tanks: pd.DataFrame,
        eve_zip_with_tanks,
    ):
        """Unrecognized numeric zip stem is ignored; M1 data is still returned."""
        zf = eve_zip_with_tanks([1, 99])
        table, _ = service_with_ferm_module._process_ferm_process_panels(
            zf, meta_two_ferm_tanks, 'EveTable',
        )
        assert not table.empty
        assert set(table['Tank'].unique()) == {'M1'}
