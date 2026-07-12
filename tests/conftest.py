"""Pytest fixtures for biocanvas tests."""
import io
import sqlite3
import zipfile
from unittest.mock import patch as _patch

import pandas as pd
import numpy as np
from typing import Dict, Any
import pytest

from biocanvas.db import schema as db_schema


class _SessionMocker:
    """Session-scoped mocker for root conftest's setup_module(session_mocker)."""

    class patch:
        """Mirrors unittest.mock.patch so session_mocker.patch.object(...) works."""

        @staticmethod
        def object(target, attribute, **kwargs):
            p = _patch.object(target, attribute, **kwargs)
            p.start()
            return p


@pytest.fixture(scope="session")
def session_mocker():
    """Provide session_mocker required by root tests/conftest.py setup_module."""
    return _SessionMocker()

########################################################
# Fixtures for biocanvas.db tests
########################################################
@pytest.fixture
def db_conn() -> sqlite3.Connection:
    """Function-scoped in-memory SQLite connection with the BioCanvas schema created."""
    conn = db_schema.connect(':memory:')
    yield conn
    conn.close()


########################################################
# Sample data fixtures for general test cases
########################################################
@pytest.fixture(scope="session")
def bench_table() -> pd.DataFrame:
    """Minimal bench DataFrame with MultiIndex columns for general tests."""
    return pd.DataFrame(
        {
            ("Exp", ""): [1] * 9,
            ("Condition", ""): ["Condition1"] * 9,
            ("Tank", ""): np.repeat(["L1", "L2", "L3"], 3),
            ("Replicate", ""): np.repeat([1, 2, 3], 3),
            ("Time (h)", ""): np.tile([0.0, 1.0, 2.0], 3),
            ("Ferm", "DCW (g/L)"): np.random.rand(9),
            ("Ferm", "% Insoluble Solids (g/g)"): np.random.rand(9)
        }
    )


@pytest.fixture(scope="session")
def process_table() -> pd.DataFrame:
    """Minimal process DataFrame with MultiIndex columns for general tests."""
    return pd.DataFrame(
        {
            ("Exp", ""): [1] * 9,
            ("Condition", ""): ["Condition1"] * 9,
            ("Tank", ""): np.repeat(["L1", "L2", "L3"], 3),
            ("Replicate", ""): np.repeat([1, 2, 3], 3),
            ("Time (h)", ""): np.tile([0.0, 1.0, 2.0], 3),
            ("Process", "pH"): 5.0 + 0.1*np.random.rand(9),
            ("Process", "Temperature (°C)"): 5.0 + 0.1*np.random.rand(9)
        }
    )

@pytest.fixture(scope='session')
def bench_plot_properties(bench_table: pd.DataFrame) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Minimal bench plot_properties for OLPlotter."""
    return {
        "Ferm": {
            "Biomass": {
                "cols": ["DCW (g/L)"],
                "col_exist": [1] if ("Ferm", "DCW (g/L)") in bench_table.columns else [0],
                "xlim": (None, None),
                "ylim": (None, None),
                "ylabel": "DCW (g/L)",
            },
            "IS (%)": {
                "cols": ["% Insoluble Solids (g/g)"],
                "col_exist": [1] if ("Ferm", "% Insoluble Solids (g/g)") in bench_table.columns else [0],
                "xlim": (None, None),
                "ylim": (None, None),
                "ylabel": "% Insoluble Solids (g/g)",
            }
        }
    }

@pytest.fixture(scope="session")
def process_plot_properties(process_table: pd.DataFrame) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Minimal process plot_properties for OLPlotter."""
    return {
        "Process": {
            "Temperature": {
                "cols": ["Temperature (°C)"],   
                "col_exist": [1] if ("Process", "Temperature (°C)") in process_table.columns else [0],
                "xlim": (None, None),  
                "ylim": (None, None),
                "ylabel": "Temperature (°C)",
            },
            "pH Profile": {
                "cols": ["pH"],
                "col_exist": [1] if ("Process", "pH") in process_table.columns else [0],
                "xlim": (None, None),
                "ylim": (None, None),
                "ylabel": "pH",
            }
        }
    }


########################################################
# Sample data fixtures for OLPlotter test cases
########################################################
@pytest.fixture(scope='session')
def bench_table_for_ol(bench_table: pd.DataFrame) -> pd.DataFrame:
    """Minimal bench table for OLPlotter."""
    return bench_table.drop(columns=[('Exp', ''), ('Condition', '')])


@pytest.fixture(scope='session')
def process_table_for_ol(process_table: pd.DataFrame) -> pd.DataFrame:
    """Minimal process table for OLPlotter."""
    return process_table.drop(columns=[('Exp', ''), ('Condition', '')])


@pytest.fixture(scope="session")
def plot_properties_for_ol(
    bench_plot_properties: Dict[str, Dict[str, Dict[str, Any]]],
    process_plot_properties: Dict[str, Dict[str, Dict[str, Any]]],
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Combine bench and process plot properties."""
    return {'Ferm': bench_plot_properties['Ferm'], 'Process': process_plot_properties['Process']}


########################################################
# Sample data fixtures for CCPlotter test cases
########################################################
@pytest.fixture(scope='session')
def update_table_for_cc() -> pd.DataFrame:
    """Minimal MultiIndex-column DataFrame returned by a mocked update_table for CCPlotter tests.

    Contains the columns required by _extract_information: Tank, Time (h), Replicate, plus
    sample Ferm and Process KPI columns covering both bench and process panel tests.
    """
    return pd.DataFrame({
        ('Exp', ''): [1] * 4,
        ('Condition', ''): ['Condition1', 'Condition2', 'Condition3', 'Condition3'],
        ('Condition_num', ''): [1, 2, 3, 3],
        ('Tank', ''): ['L1', 'L2', 'L3', 'L4'],
        ('Time (h)', ''): [1.0, 1.0, 1.0, 1.0],
        ('Replicate', ''): [1, 1, 1, 2],
        ('Ferm', 'DCW (g/L)'): [0.10, 0.20, 0.15, 0.16],
        ('Ferm', '% Insoluble Solids (g/g)'): [0.05, 0.06, 0.07, 0.08],
        ('Sugar', 'Glucose (g/L)'): [0.05, 0.06, 0.07, 0.08],
        ('Sugar', 'Fructose (g/L)'): [0.05, 0.06, 0.07, 0.08],
        ('Sugar', 'Sucrose (g/L)'): [0.05, 0.06, 0.07, 0.08],
    })


@pytest.fixture(scope='session')
def plot_properties_for_cc() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Minimal plot_properties for CCPlotter."""
    return {
        "Ferm": {
            "Biomass": {
                "cols": ["DCW (g/L)"],
                "col_exist": [1],
                "xlim": (None, None),
                "ylim": (None, None),
                "ylabel": "DCW (g/L)",
            },
            "IS (%)": {
                "cols": ["% Insoluble Solids (g/g)"],
                "col_exist": [1],
                "xlim": (None, None),
                "ylim": (None, None),
                "ylabel": "% Insoluble Solids (g/g)",
            }
        },
        "Sugar": {
            "Growth Substrate": {
                "cols": ["Glucose (g/L)", "Fructose (g/L)", "Sucrose (g/L)"],
                "col_exist": [1] * 3,
                "xlim": (None, None),
                "ylim": (None, None),
                "ylabel": "Titer (g/L)",
            }
        }
    }


########################################################
# Sample data fixtures for AugmentTables test cases
########################################################
@pytest.fixture(scope="session")
def meta_table_for_augment() -> pd.DataFrame:
    """Flat metadata table for AugmentTables tests.

    Contains two fermentation tanks (L1, L2) and one seed tank (S1). EFT is 100 h
    for ferm tanks. Feed and Co-feed use manually dosed profiles that are inactive
    during the 0-100 h window (rate = 0 in the first phase), so their pumped
    volumes are zero. A Bolus delivers brief pulses at t = 50 h and t = 60 h.
    Acid and Base are Eve/Pi controlled via internal pump totals (Max Calib = NA).
    """
    return pd.DataFrame({
        'Tank':                            ['L1',  'L2',  'S1'],
        'Exp':                             ['E001', 'E001', 'E001'],
        'Replicate':                       [1,      2,      1],
        'EFT (h)':                         [100.0,   100.0,   24.0],
        'Initial Broth Vol (ml)':          [400.0,  400.0,  200.0],
        # --- feed ---
        'Feed Element':                    ['Carbon', 'Carbon', 'NA'],
        'Feed Source':                     ['Glucose', 'Glucose', 'NA'],
        'Feed Density (g/ml)':             [1.0,    1.0,    1.0],
        'Eve/Pi Controlled Feed':          ['No',   'No',   'NA'],
        'Manual Feed Time Profile (h)':    ['0-24;24-48',  '0-24;24-48', 'NA'],
        'Manual Target Feed Rate (ml/h)':  ['0;2.8', '0;2.8', 'NA'],
        'Measured Added Feed (ml)':        [68.0,   'NA',   'NA'], # Value added by rate x duration=67.2 ml; setting to 68.0 to ensure the correction factor is applied
        'Target Feed Conc. (g/l)':         [50.0,   50.0,   'NA'],
        # --- co-feed ---
        'Co-feed Element':                 ['Carbon', 'Carbon', 'NA'],
        'Co-feed Source':                  ['Fructose', 'Fructose', 'NA'],
        'Co-feed Density (g/ml)':          [1.0,    1.0,    1.0],
        'Eve/Pi Controlled Co-feed':       ['No',   'No',   'NA'],
        'Manual Co-feed Time Profile (h)': ['0-24;24-48',  '0-24;24-48', 'NA'],
        'Manual Target Co-feed Rate (ml/h)': ['0;2.8', '0;2.8', 'NA'],
        'Measured Added Co-feed (ml)':     [68.0,   68.0,   'NA'], # Value added by rate x duration=67.2 ml; setting to 68.0 to ensure the correction factor is applied
        'Target Co-feed Conc. (g/l)':      [50.0,   50.0,   'NA'],
        # --- Bolus feed ---
        'Bolus Element':                       ['Carbon',          'Nitrogen',        'NA'],
        'Bolus Source':                        ['Glucose',         '45% (NH4)2SO4',   'NA'],
        'Bolus Density (g/ml)':                [1.0,               1.3,               'NA'],
        'Eve/Pi Controlled Bolus':             ['No',              'No',              'NA'],
        'Max Calib. Bolus Pump Rate (ml/s)':   ['NA',              'NA',              'NA'],
        'Manual Bolus Time Profile (h)':       ['50-50.05;60-60.05', '50-50.05;60-60.05', 'NA'],
        'Manual Target Bolus Rate (ml/h)':     ['110;110',         '110;110',         'NA'],
        'Measured Added Bolus (ml)':           ['NA',              'NA',             'NA'],
        'Target Bolus Conc. (g/l)':            [50.0,             50.0,             'NA'],
        # --- Acid feed ---
        'Acid Source':                         ['2N H3PO4',     '2N H3PO4',     'NA'],
        'Acid Density (g/ml)':                 [0.9,               0.9,               'NA'],
        'Eve/Pi Controlled Acid':              ['Yes',             'Yes',             'NA'],
        'Max Calib. Acid Pump Rate (ml/s)':    ['NA',              'NA',              'NA'],
        'Manual Acid Time Profile (h)':        ['NA',              'NA',              'NA'],
        'Manual Target Acid Rate (ml/h)':      ['NA',              'NA',              'NA'],
        'Measured Added Acid (ml)':            ['NA',              'NA',               'NA'],
        # --- Base feed ---
        'Base Source':                         ['5.5N NaOH',      '5.5N NaOH',      'NA'],
        'Base Density (g/ml)':                 [1.2,               1.2,               'NA'],
        'Eve/Pi Controlled Base':              ['Yes',             'Yes',             'NA'],
        'Max Calib. Base Pump Rate (ml/s)':    ['NA',              'NA',              'NA'],
        'Manual Base Time Profile (h)':        ['NA',              'NA',              'NA'],
        'Manual Target Base Rate (ml/h)':      ['NA',              'NA',              'NA'],
        'Measured Added Base (ml)':            ['NA',              'NA',              'NA'],
        # --- Experimental setpoints ---
        'pH Setpoint':                         ['4.8;4.0',          '4.8;4.0',         'var'],
        'Temperature Setpoint (°C)':           ['27;25',            '27;25',           30],
        'DO Setpoint (%)':                     [40.0,               40.0,              'var'],
    })


@pytest.fixture(scope="session")
def raw_process_table_for_augment() -> pd.DataFrame:
    """Minimal pre-augmentation process table for AugmentTables tests.

    Ferm tanks (L1, L2) have nine timepoints: t = 0, 24, 48, 50, 50.05, 60, 60.05, 72, 100 h.
    t = 48 is included so that phase 2 of the manual feed/co-feed profile ('0-24;24-48' at
    rate '0;2.8' ml/h) has at least one process row in its active window (24, 48].  Without
    t = 48 the trapezoidal integration produces zero feed volume at EFT, which causes
    ZeroDivisionError when the bottle-weight correction (Measured Added Feed/Co-feed = 68.0)
    is applied.

    t = 50.05 and t = 60.05 capture the two brief Bolus pulses defined in
    meta_table_for_augment ('50-50.05;60-60.05' profile), which require a process row
    that satisfies (t > 50) & (t <= 50.05) for the pump calculation.

    Seed tank (S1) has two timepoints: t = 0 and t = 24 h.

    'Acid Pump.Total volume, ml' and 'Base Pump.Total volume, ml' are included as zeros
    so that Eve/Pi-controlled Acid and Base return Pumped Vol = 0 rather than NaN,
    keeping Total Fed Vol free of NaN for ferm tanks.
    """
    ferm_times = [0.0, 24.0, 48.0, 50.0, 50.05, 60.0, 60.05, 72.0, 100.0]
    seed_times = [0.0, 24.0]
    n_ferm = len(ferm_times)
    n_seed = len(seed_times)
    tanks = np.hstack([np.repeat(['L1', 'L2'], n_ferm), np.repeat(['S1'], n_seed)])
    times = np.hstack([np.tile(ferm_times, 2), seed_times])
    n_total = len(tanks)
    return pd.DataFrame({
        'Tank':                          tanks,
        'Time (h)':                      times,
        'Acid Pump.Total volume, ml':    np.zeros(n_total),
        'Base Pump.Total volume, ml':    np.zeros(n_total),
    })


@pytest.fixture(scope="session")
def raw_bench_table_for_augment() -> pd.DataFrame:
    """Pre-augmentation bench table covering all three tanks in meta_table_for_augment.

    Ferm tanks (L1, L2) have four sampling timepoints: t = 0, 24, 72, 100 h,
    matching their EFT and the process table timepoints. Seed tank S1 has two
    timepoints: t = 0 and t = 24 h (matching its EFT = 24 h).

    'Sample Vol (ml)' is set to 1.0 for all rows so the ferm-tank broth-volume
    calculation accumulates sample removal; not omitting this column would
    cause grp.get(...) returns a list whose .cumsum() would raise AttributeError.
    This is the same logic as in the test_utils.py test_try_kpi_weight_yield_only_when_flag_true.

    Panel data columns use tuple names matching the pagoda PANEL_DISPLAY_NAMES
    mapping ('Ferm' → 'Growth'). A product column drives _compute_try_kpis.
    """
    return pd.DataFrame({
        'Tank':    np.hstack([np.repeat(['L1', 'L2'], 4), np.array(['S1', 'S1'])]),
        'Time (h)': np.hstack([np.tile([0.0, 24.0, 72.0, 100.0], 2), np.array([0.0, 24.0])]),
        'Sample Vol (ml)':                         [1.0]*10,
        ('Growth', 'DCW (g/L)'):                   [2.0, 3.5, 4.0, 5.0,  2.0, 3.5, 4.0, 5.0,  0.1, 2.0],
        ('Growth', '% Insoluble Solids (g/g)'):    [2.0, 3.5, 4.0, 5.0,  2.0, 3.5, 4.0, 5.0,  0.1, 2.0],
        ('Sugar', 'Glucose (g/L)'):                [20.0, 10.0, 0.0, 0.0,  20.0, 10.0, 0.0, 0.0,  10, 0.0],
        ('Sugar', 'Fructose (g/L)'):               [0.0, 2.0, 0.0, 0.0,  0.0, 2.0, 0.0, 0.0,  0.0, 0.0],
        ('Sugar', 'Lactose (g/L)'):                [0.0, 2.0, 0.0, 0.0,  0.0, 2.0, 0.0, 0.0,  0.0, 0.0],
        ('Alpha', 'TestProduct (g/L)'):            [0.0, 1.5, 2.5, 3.5,  0.0, 1.5, 2.5, 3.5,  0.0, 1.5],
    })


@pytest.fixture(scope="session")
def augment_config() -> Dict[str, Any]:
    """Config parameters required by AugmentTables.__init__ for augmentation tests.

    carbon_panels maps the Sugar panel to Glucose, Fructose, and Lactose so that the carbon-balance sum
    produces a zero (the column is absent from the bench fixture, so grp.get()
    returns the zero-series default). panels_for_try exercises _compute_try_kpis
    via the Alpha panel's TestProduct column in raw_bench_table_for_augment.
    """
    return {
        'carbon_panels': {'Sugar': ['Glucose', 'Fructose', 'Lactose']},
        'panels_for_try': {'Alpha': ['TestProduct']},
        'panel_display_names': {'Ferm': 'Growth'},
        'bench_cols_to_keep': [
            'Exp', 'Tank', 'Replicate', 'Time (h)',
            'Total Broth Vol (ml)',
            ('Growth', 'DCW (g/L)'),
            ('Growth', '% Insoluble Solids (g/g)'),
            ('Sugar', 'Glucose (g/L)'),
            ('Sugar', 'Fructose (g/L)'),
            ('Sugar', 'Lactose (g/L)'),
            ('Alpha', 'TestProduct Titer (g/L)'),
            ('Alpha', 'TestProduct Sp. Titer (g/g)'),
            ('Alpha', 'TestProduct Weight (g)'),
            ('Alpha', 'TestProduct Yield (g/g)'),
            ('Alpha', 'TestProduct Rate (g/L/h)'),
            ('Alpha', 'TestProduct Ins. Rate (g/L/h)'),
        ],
        'process_cols_to_keep': [
            'Exp', 'Tank', 'Replicate', 'Time (h)',
            'Removed Sample Vol (ml)', 'Removed Sample Weight (g)',
            'Total Fed Vol (ml)', 'Combined Feeds Weight (g)', 'Added Carbon Weight (g)',
        ],
    }


@pytest.fixture(scope="session")
def meta_exact_for_augment() -> pd.DataFrame:
    """Flat metadata table for exact-value AugmentTables tests.

    Contains two fermentation tanks:

    * EX — exercises all three pump-volume paths in a single tank using
      separate feed types:

      - Feed   (Path A): Eve/Pi-controlled with no calibration; pumped vol
        is read directly from the ``Feed Pump.Total volume, ml`` column.
      - Co-feed (Path B): Eve/Pi-controlled with ``Max Calib.`` rate of 0.002
        ml/s; pumped vol = ``max_rate × duty% × duration_s``.  The element is
        *Nitrogen*, so the Co-feed is deliberately **excluded** from
        ``Added Carbon Weight``.
      - Bolus   (Path C): delta pulse ``'10-10.05'`` at 200 ml/h (10 ml
        nominal volume).  Two bracketing process timepoints at t = 10.05 and
        t = 10.1 ensure the trapezoidal integrator accumulates exactly 10 ml
        and holds that value constant afterwards.  The element is Carbon so it
        is included in ``Added Carbon Weight``.

    * CR — identical to EX but with ``Measured Added Feed (ml) = 60``
      (raw pump total at EFT = 30 ml) to test the bottle-weight correction
      factor of 2.0.

    All other feed types (Acid, Base) are set to ``Source = 'NA'`` and are
    skipped by the augmentation logic.
    """
    return pd.DataFrame({
        'Tank':                                     ['EX',    'CR'],
        'Exp':                                      ['EX01',  'EX01'],
        'Replicate':                                [1,       2],
        'EFT (h)':                                  [30.0,    30.0],
        'Initial Broth Vol (ml)':                   [1000.0,  1000.0],
        # --- Feed: Path A (Eve/Pi internal pump total) ---
        'Feed Element':                             ['Carbon',  'Carbon'],
        'Feed Source':                              ['GlucoseSol', 'GlucoseSol'],
        'Feed Density (g/ml)':                      [1.0,       1.0],
        'Eve/Pi Controlled Feed':                   ['Yes',     'Yes'],
        'Max Calib. Feed Pump Rate (ml/s)':         ['NA',      'NA'],
        'Manual Feed Time Profile (h)':             ['NA',      'NA'],
        'Manual Target Feed Rate (ml/h)':           ['NA',      'NA'],
        'Measured Added Feed (ml)':                 ['NA',      60.0],  # CR uses correction
        'Target Feed Conc. (g/l)':                  [500.0,     500.0],
        # --- Co-feed: Path B (calibrated pump rate, Nitrogen — non-carbon) ---
        'Co-feed Element':                          ['Nitrogen', 'NA'],
        'Co-feed Source':                           ['AmmoniumSulfate', 'NA'],
        'Co-feed Density (g/ml)':                   [1.1,       'NA'],
        'Eve/Pi Controlled Co-feed':                ['Yes',     'NA'],
        'Max Calib. Co-feed Pump Rate (ml/s)':      [0.002,     'NA'],
        'Manual Co-feed Time Profile (h)':          ['NA',      'NA'],
        'Manual Target Co-feed Rate (ml/h)':        ['NA',      'NA'],
        'Measured Added Co-feed (ml)':              ['NA',      'NA'],
        'Target Co-feed Conc. (g/l)':               ['NA',      'NA'],
        # --- Bolus: Path C (manual constant-rate profile, Carbon) ---
        'Bolus Element':                            ['Carbon',  'NA'],
        'Bolus Source':                             ['GlucosePulse', 'NA'],
        'Bolus Density (g/ml)':                     [1.2,       'NA'],
        'Eve/Pi Controlled Bolus':                  ['No',      'NA'],
        'Max Calib. Bolus Pump Rate (ml/s)':        ['NA',      'NA'],
        'Manual Bolus Time Profile (h)':            ['10-10.05', 'NA'],
        'Manual Target Bolus Rate (ml/h)':          ['200',     'NA'],
        'Measured Added Bolus (ml)':                ['NA',      'NA'],
        'Target Bolus Conc. (g/l)':                 [200.0,     'NA'],
        # --- Acid: skipped ---
        'Acid Source':                              ['NA',      'NA'],
        'Acid Density (g/ml)':                      ['NA',      'NA'],
        'Eve/Pi Controlled Acid':                   ['NA',      'NA'],
        'Max Calib. Acid Pump Rate (ml/s)':         ['NA',      'NA'],
        'Manual Acid Time Profile (h)':             ['NA',      'NA'],
        'Manual Target Acid Rate (ml/h)':           ['NA',      'NA'],
        'Measured Added Acid (ml)':                 ['NA',      'NA'],
        # --- Base: skipped ---
        'Base Source':                              ['NA',      'NA'],
        'Base Density (g/ml)':                      ['NA',      'NA'],
        'Eve/Pi Controlled Base':                   ['NA',      'NA'],
        'Max Calib. Base Pump Rate (ml/s)':         ['NA',      'NA'],
        'Manual Base Time Profile (h)':             ['NA',      'NA'],
        'Manual Target Base Rate (ml/h)':           ['NA',      'NA'],
        'Measured Added Base (ml)':                 ['NA',      'NA'],
    })


@pytest.fixture(scope="session")
def process_exact_for_augment() -> pd.DataFrame:
    """Pre-augmentation process table for exact-value AugmentTables tests.

    Tanks EX and CR each have four timepoints: t = 0, 10, 20, 30 h.

    * ``Feed Pump.Total volume, ml`` is the cumulative pump total used by
      Path A for both tanks.
    * ``Co-feed, %`` and ``Co-feed.Duration, s`` are the calibrated-path
      inputs for Path B (EX tank only; CR has no Co-feed).

    With these values the expected Path B Co-feed volumes are:
        t=10:   0.002 × 50  × 100 = 10 ml
        t=10.05 0.002 × 50  × 100 = 10 ml  (snapshot unchanged)
        t=10.1: 0.002 × 50  × 100 = 10 ml  (snapshot unchanged)
        t=20:   0.002 × 100 × 200 = 40 ml
        t=30:   0.002 × 100 × 300 = 60 ml

    EX has two extra timepoints at t = 10.05 and t = 10.1 to correctly bracket
    the Bolus delta pulse (profile '10-10.05').  The trapezoidal integrator
    captures the leading half at t = 10.05 (+5 ml) and the trailing half at
    t = 10.1 (+5 ml), giving cumulative Bolus vols of [0, 0, 5, 10, 10, 10]
    at times [0, 10, 10.05, 10.1, 20, 30].  CR has no Bolus and keeps the
    original four timepoints.
    """
    ex_times = [0.0, 10.0, 10.05, 10.1, 20.0, 30.0]
    n_ex = len(ex_times)
    ex_rows = pd.DataFrame({
        'Tank':                         ['EX'] * n_ex,
        'Time (h)':                     ex_times,
        # Feed Pump total is cumulative; no pump activity between t=10 and t=10.1
        'Feed Pump.Total volume, ml':   [0.0, 10.0, 10.0, 10.0, 20.0, 30.0],
        # Co-feed snapshot values unchanged at the intermediate timepoints
        'Co-feed, %':                   [0.0, 50.0, 50.0, 50.0, 100.0, 100.0],
        'Co-feed.Duration, s':          [0.0, 100.0, 100.0, 100.0, 200.0, 300.0],
    })
    cr_times = [0.0, 10.0, 20.0, 30.0]
    n_cr = len(cr_times)
    cr_rows = pd.DataFrame({
        'Tank':                         ['CR'] * n_cr,
        'Time (h)':                     cr_times,
        'Feed Pump.Total volume, ml':   [0.0, 10.0, 20.0, 30.0],
        'Co-feed, %':                   [np.nan] * n_cr,
        'Co-feed.Duration, s':          [np.nan] * n_cr,
    })
    return pd.concat([ex_rows, cr_rows], ignore_index=True)


@pytest.fixture(scope="session")
def bench_exact_for_augment() -> pd.DataFrame:
    """Pre-augmentation bench table for exact-value AugmentTables tests.

    Tank EX only, four timepoints: t = 0, 10, 20, 30 h.

    ``Sample Vol (ml)`` and ``Sample Weight (g)`` are non-zero at t = 10 and
    t = 20 (5 ml / 5 g each) to exercise sample-tracking and its effect on
    broth volume and carbon balance.

    ``('Growth', '% Insoluble Solids (g/g)')`` is zero throughout so that
    corrected titer = raw titer, making TRY KPI assertions unambiguous.

    Carbon substrates deplete from [10, 5, 0, 0] g/L (Glucose) and
    [2, 1, 0, 0] g/L (Lactose), giving predictable carbon-balance values.
    """
    return pd.DataFrame({
        'Tank':                                     ['EX', 'EX', 'EX', 'EX'],
        'Time (h)':                                 [0.0,   10.0,  20.0,  30.0],
        'Sample Vol (ml)':                          [0.0,    5.0,   5.0,   0.0],
        'Sample Weight (g)':                        [0.0,    5.0,   5.0,   0.0],
        ('Growth', 'DCW (g/L)'):                    [1.0,    2.0,   3.0,   4.0],
        ('Growth', '% Insoluble Solids (g/g)'):     [0.0,    0.0,   0.0,   0.0],
        ('Sugar', 'Glucose (g/L)'):                 [10.0,   5.0,   0.0,   0.0],
        ('Sugar', 'Lactose (g/L)'):                 [2.0,    1.0,   0.0,   0.0],
        ('Alpha', 'TestProduct (g/L)'):             [0.0,    0.5,   1.0,   1.5],
    })


@pytest.fixture(scope="session")
def augment_config_exact() -> Dict[str, Any]:
    """AugmentTables config for exact-value tests.

    Identical panels to ``augment_config`` (Sugar→Glucose/Lactose carbon
    panel; Alpha→TestProduct TRY panel) but with expanded column-keep lists
    so that individual pump volumes, sample-tracking columns, broth-volume
    and carbon-balance columns, and all TRY KPI columns are retained in the
    final augmented tables for assertion.
    """
    return {
        'carbon_panels': {'Sugar': ['Glucose', 'Lactose']},
        'panels_for_try': {'Alpha': ['TestProduct']},
        'panel_display_names': {'Ferm': 'Growth'},
        'bench_cols_to_keep': [
            'Exp', 'Tank', 'Replicate', 'Time (h)',
            'Sample Vol (ml)',
            'Total Broth Vol (ml)',
            'Added Carbon Weight (g)',
            'Total Carbon in Broth (g)',
            'Total Carbon Consumed (g)',
            ('Growth', 'DCW (g/L)'),
            ('Sugar', 'Glucose (g/L)'),
            ('Sugar', 'Lactose (g/L)'),
            ('Alpha', 'TestProduct Titer (g/L)'),
            ('Alpha', 'TestProduct Sp. Titer (g/g)'),
            ('Alpha', 'TestProduct Weight (g)'),
            ('Alpha', 'TestProduct Yield (g/g)'),
            ('Alpha', 'TestProduct Rate (g/L/h)'),
            ('Alpha', 'TestProduct Ins. Rate (g/L/h)'),
        ],
        'process_cols_to_keep': [
            'Exp', 'Tank', 'Replicate', 'Time (h)',
            'Pumped Feed Vol (ml)',
            'Pumped Co-feed Vol (ml)',
            'Pumped Bolus Vol (ml)',
            'Removed Sample Vol (ml)',
            'Removed Sample Weight (g)',
            'Total Fed Vol (ml)',
            'Combined Feeds Weight (g)',
            'Added Carbon Weight (g)',
        ],
    }


########################################################
# Sample data fixtures for GCPlotter test cases
########################################################
@pytest.fixture(scope='session')
def update_table_for_gc() -> pd.DataFrame:
    """Minimal MultiIndex-column DataFrame returned by a mocked update_table for GCPlotter tests.

    Contains 8 rows (4 tanks × 2 time points) covering both bench (Ferm) and
    process (Process) KPI columns required by _extract_information.
    """
    return pd.DataFrame({
        ('Exp', ''): [1] * 8,
        ('Tank', ''): ['L1', 'L1', 'L2', 'L2', 'L3', 'L3', 'L4', 'L4'],
        ('Time (h)', ''): [0.0, 24.0, 0.0, 24.0, 0.0, 24.0, 0.0, 24.0],
        ('Ferm', 'DCW (g/L)'): [0.05, 0.10, 0.08, 0.20, 0.07, 0.15, 0.09, 0.18],
        ('Process', 'pH'): [7.0, 7.2, 7.1, 7.3, 6.9, 7.0, 7.0, 7.1],
    })


@pytest.fixture(scope='session')
def master_meta_table_for_gc() -> pd.DataFrame:
    """Master metadata table for GCPlotter tests.

    Indexed by (Exp, Tank) MultiIndex. Provides 'Condition' and 'Strain' columns
    used by _extract_information when first_grping_param or second_grping_param is
    a non-time metadata key.
    """
    index = pd.MultiIndex.from_tuples(
        [(1, 'L1'), (1, 'L2'), (1, 'L3'), (1, 'L4')],
        names=['Exp', 'Tank'],
    )
    return pd.DataFrame(
        {
            'Condition': ['CondA', 'CondA', 'CondB', 'CondB'],
            'Strain':    ['S1',    'S1',    'S2',    'S2'],
        },
        index=index,
    )


@pytest.fixture(scope='session')
def plot_properties_for_gc() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Minimal plot_properties for GCPlotter covering one bench and one process KPI group."""
    return {
        'Ferm': {
            'Biomass': {
                'cols': ['DCW (g/L)'],
                'col_exist': [1],
                'xlim': (None, None),
                'ylim': (None, None),
                'ylabel': 'DCW (g/L)',
            },
        },
        'Process': {
            'pH Profile': {
                'cols': ['pH'],
                'col_exist': [1],
                'xlim': (None, None),
                'ylim': (None, None),
                'ylabel': 'pH',
            },
        },
    }


########################################################
# Eve/Pi zip fixtures for DataService._process_ferm_process_panels
########################################################

def minimal_eve_csv_body() -> str:
    """Minimal semicolon-delimited Eve CSV body for in-memory zip tests."""
    return (
        "metadata row\n"
        "Batch Time (since inoc.), sec;GM Flow, ml/min;PrimaBT.N2, %;PrimaBT.O2, %;PrimaBT.CO2, %\n"
        "3600;100;78;18;2\n"
        "7200;100;78;17;2.5\n"
    )

def _build_eve_zip_with_tanks(tank_ids: list[int]) -> io.BytesIO:
    """Build an in-memory zip containing one Eve CSV per numeric tank id."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for tid in tank_ids:
            zf.writestr(f'exp.{tid}.csv', minimal_eve_csv_body())
    buf.seek(0)
    return buf


@pytest.fixture
def eve_zip_with_tanks():
    """Factory fixture: call as ``eve_zip_with_tanks([1])`` to build an Eve/Pi zip."""
    return _build_eve_zip_with_tanks


@pytest.fixture(scope='session')
def meta_two_ferm_tanks() -> pd.DataFrame:
    """Metadata with one seed tank and two fermentation tanks for Eve/Pi tests."""
    return pd.DataFrame({
        'Tank': ['S1', 'M1', 'M2'],
        'Replicate': [1, 1, 2],
        'EFT (h)': [24.0, 48.0, 48.0],
    })


@pytest.fixture(scope='session')
def service_with_ferm_module():
    """DataService with pagoda ferm_process module wired for panel parsing tests."""
    from biocanvas.data_service import DataService
    from biocanvas.helix import ferm_process

    svc = DataService()
    svc.ferm_process_module = ferm_process
    return svc
