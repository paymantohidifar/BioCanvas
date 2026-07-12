"""Tests for biocanvas.helix benchling and ferm_process panel classes."""
import io
import zipfile
from typing import Dict, Type

import numpy as np
import pandas as pd
import pytest

from biocanvas.helix import benchling, ferm_process
from biocanvas.utils.helpers import EmptyTableError


def _make_zip_csv(arcname: str, df: pd.DataFrame) -> zipfile.ZipFile:
    """Build an in-memory ZipFile containing one CSV written from *df*."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        csv_buf = io.StringIO()
        df.to_csv(csv_buf, index=False)
        zf.writestr(arcname, csv_buf.getvalue())
    buf.seek(0)
    return zipfile.ZipFile(buf, 'r')


def _panel_from_df(panel_cls, df: pd.DataFrame, arcname: str = 'exp.Panel.csv'):
    """Instantiate a benchling panel class from a DataFrame via an in-memory zip."""
    with _make_zip_csv(arcname, df) as zip_ref:
        return panel_cls(zip_ref, arcname)


def _make_eve_zip(arcname: str, csv_body: str) -> zipfile.ZipFile:
    """Build an in-memory ZipFile containing one Eve semicolon-delimited CSV."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(arcname, csv_body)
    buf.seek(0)
    return zipfile.ZipFile(buf, 'r')


def _ferm_panel_from_csv(
    panel_cls: Type,
    csv_body: str,
    arcname: str = 'exp.M1.csv',
    tank: str = 'M1',
    *,
    eve: bool = False,
):
    """Instantiate an Eve/Pi panel class from CSV text via an in-memory zip."""
    if eve:
        zip_ref = _make_eve_zip(arcname, csv_body)
    else:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(arcname, csv_body)
        buf.seek(0)
        zip_ref = zipfile.ZipFile(buf, 'r')
    with zip_ref:
        return panel_cls(zip_ref, arcname, tank)


# ---------------------------------------------------------------------------
# Sample
# ---------------------------------------------------------------------------


class TestSample:
    """Tests for Sample.process()."""
    @staticmethod
    def _sample_df(**overrides) -> pd.DataFrame:
        rows: Dict[str, list] = {
            'Entity': ['S1-R1-T0h', 'M1-R1-T24h'],
            'Sample': ['placeholder', 'placeholder'],
            'Sample Volume (mL)': [1.0, 2.0],
            'Timepoint (h)': [0.0, 24.0],
        }
        rows.update(overrides)
        return pd.DataFrame(rows)

    def test_process_returns_sample_multiindex_columns(self):
        result = _panel_from_df(benchling.Sample, self._sample_df()).process()
        assert not result.empty
        assert result.columns.names == [None, None]
        assert set(result.columns.get_level_values(0)) == {'Tank', 'Time (h)', 'Sample Vol (ml)'}
        assert result.columns.get_level_values(1).unique().tolist() == ['']

    def test_tank_seed_vs_ferment(self):
        result = _panel_from_df(benchling.Sample, self._sample_df()).process()
        assert result.loc['S1-R1-T0h', ('Tank', '')] == 'S1'
        assert result.loc['M1-R1-T24h', ('Tank', '')] == 'M1'

    def test_fillna_zero_for_missing_timepoint(self):
        df = self._sample_df()
        df.loc[0, 'Timepoint (h)'] = float('nan')
        result = _panel_from_df(benchling.Sample, df).process()
        assert result.loc['S1-R1-T0h', ('Time (h)', '')] == 0

    def test_tank_column_accessible_for_data_service(self):
        """Sample uses (column, '') MultiIndex so consolidated df['Tank'] works."""
        result = _panel_from_df(benchling.Sample, self._sample_df()).process()
        assert result['Tank'].tolist() == ['S1', 'M1']
        assert result[('Tank', '')].tolist() == ['S1', 'M1']

    def test_empty_table_raises(self):
        df = pd.DataFrame(columns=['Entity', 'Sample', 'Sample Volume (mL)'])
        with pytest.raises(EmptyTableError, match='Sample table is empty'):
            _panel_from_df(benchling.Sample, df).process()

    def test_missing_essential_column_raises(self):
        df = self._sample_df()
        df = df.drop(columns=['Sample Volume (mL)'])
        with pytest.raises(ValueError, match='Sample Volume'):
            _panel_from_df(benchling.Sample, df).process()


# ---------------------------------------------------------------------------
# Ferm
# ---------------------------------------------------------------------------


class TestFerm:
    """Tests for Ferm.process()."""
    @staticmethod
    def _ferm_df(n_rows: int = 2, sample: str = 'M1-R1-T24h') -> pd.DataFrame:
        return pd.DataFrame(
            {
                'Sample': [sample] * n_rows,
                '% Insoluble Solids': [0.1, 0.3],
                'DCW g/L': [10.0, 14.0],
                'Broth Mass (mg)': [1000.0, 1200.0],
                'Sample Volume (uL)': [1000.0, 1000.0],
            }
        )

    def test_aggregates_mean_and_std(self):
        result = _panel_from_df(benchling.Ferm, self._ferm_df()).process()
        assert result.columns.get_level_values(0).unique().tolist() == ['Ferm']
        dcw = [10.0, 14.0]
        assert result.loc['M1-R1-T24h', ('Ferm', 'DCW (g/L)')] == pytest.approx(np.mean(dcw))
        assert result.loc['M1-R1-T24h', ('Ferm', 'DCW_std (g/L)')] == pytest.approx(np.std(dcw, ddof=1))

    def test_renames_insoluble_and_dcw_columns(self):
        result = _panel_from_df(benchling.Ferm, self._ferm_df()).process()
        inner = result.columns.get_level_values(1).tolist()
        assert '% Insoluble Solids (g/g)' in inner
        assert 'DCW (g/L)' in inner

    def test_weight_branch_recomputes_dcw(self):
        df = pd.DataFrame(
            {
                'Sample': ['M1-R1-T24h'],
                '% Insoluble Solids': [0.2],
                'DCW g/L': [0.0],
                'Weight (g)': [1.0],
                'Sample Volume (uL)': [1000.0],
                'DCW (g/kg)': [50.0],
            }
        )
        result = _panel_from_df(benchling.Ferm, df).process()
        # density = 1000 mg / 1000 uL = 1 g/ml; DCW g/L = 50 * 1 = 50
        assert result.loc['M1-R1-T24h', ('Ferm', 'DCW (g/L)')] == pytest.approx(50.0)

    def test_empty_table_raises(self):
        df = pd.DataFrame(columns=['Sample', '% Insoluble Solids', 'DCW g/L'])
        with pytest.raises(EmptyTableError, match='Ferm table is empty'):
            _panel_from_df(benchling.Ferm, df).process()

    def test_missing_sample_column_raises(self):
        df = self._ferm_df().drop(columns=['Sample'])
        with pytest.raises(ValueError, match='Sample column is missing'):
            _panel_from_df(benchling.Ferm, df).process()


# ---------------------------------------------------------------------------
# Brad / Biochem (GeneralAnalyteTable subclasses)
# ---------------------------------------------------------------------------


class TestBrad:
    """Tests for Brad.process() column rename."""
    def test_renames_bradford_to_total_protein(self):
        df = pd.DataFrame({
            'Sample': ['M1-R1-T24h'],
            'Bradford Protein (g/L)': [1.5],
        })
        result = _panel_from_df(benchling.Brad, df, arcname='exp.Brad.csv').process()
        assert result.columns.get_level_values(0).unique().tolist() == ['Brad']
        assert 'Total Protein (g/L)' in result.columns.get_level_values(1)

    def test_empty_table_raises(self):
        df = pd.DataFrame(columns=['Sample'])
        with pytest.raises(EmptyTableError, match='Analyte table is empty'):
            _panel_from_df(benchling.Brad, df).process()


class TestBiochem:
    """Tests for Biochem.process() legacy column renames."""
    def test_renames_cellobiohydrolase_column(self):
        df = pd.DataFrame({
            'Sample': ['M1-R1-T24h'],
            'Cellobiohydrolase Activity (umoles/g/s)': [0.42],
        })
        result = _panel_from_df(benchling.Biochem, df, arcname='exp.Biochem.csv').process()
        assert result.columns.get_level_values(0).unique().tolist() == ['Biochem']
        assert 'pnpC Activity (umoles/g/s)' in result.columns.get_level_values(1)

    def test_renames_beta_glucosidase_column(self):
        df = pd.DataFrame({
            'Sample': ['M1-R1-T24h'],
            'Beta-glucosidase Activity (nmoles/mg)': [1.0],
        })
        result = _panel_from_df(benchling.Biochem, df).process()
        assert 'pnpG Activity (umoles/g/s)' in result.columns.get_level_values(1)


class TestSugar:
    """Smoke test that GeneralAnalyteTable uses subclass name for MultiIndex."""
    def test_outer_level_is_subclass_name(self):
        df = pd.DataFrame({
            'Sample': ['M1-R1-T24h'],
            'Glucose (g/L)': [5.0],
        })
        result = _panel_from_df(benchling.Sugar, df, arcname='exp.Sugar.csv').process()
        assert result.columns.get_level_values(0).unique().tolist() == ['Sugar']


# ---------------------------------------------------------------------------
# EveTable / PiTable
# ---------------------------------------------------------------------------


class TestEveTable:
    """Tests for EveTable.process()."""

    def test_process_adds_tank_time_and_gas_metrics(self):
        csv_body = (
            "metadata row\n"
            "Batch Time (since inoc.), sec;GM Flow, ml/min;PrimaBT.N2, %;PrimaBT.O2, %;PrimaBT.CO2, %\n"
            "3600;100;78;18;2\n"
            "7200;100;78;17;2.5\n"
        )
        result = _ferm_panel_from_csv(
            ferm_process.EveTable, csv_body, eve=True
        ).process()
        assert not result.empty
        assert (result['Tank'] == 'M1').all()
        assert 'Time (h)' in result.columns
        assert 'OUR (mmol/h)' in result.columns
        assert 'CER (mmol/h)' in result.columns
        assert result['Time (h)'].iloc[0] == pytest.approx(1.0)

    def test_empty_table_returns_empty_dataframe(self):
        csv_body = (
            "metadata row\n"
            "Batch Time (since inoc.), sec;GM Flow, ml/min\n"
        )
        result = _ferm_panel_from_csv(
            ferm_process.EveTable, csv_body, eve=True
        ).process()
        assert result.empty


class TestPiTable:
    """Tests for PiTable.process()."""

    def test_process_renames_columns_and_computes_gas_metrics(self):
        csv_buf = io.StringIO()
        pd.DataFrame({
            'TFT': [0.0, 1.0],
            'Agitation (RPM)': [300, 350],
            'Airflow (LPM)': [1.0, 1.0],
            'N2, mol%': [78.0, 78.0],
            'O2, mol%': [18.0, 17.0],
            'CO2, mol%': [2.0, 2.5],
        }).to_csv(csv_buf, index=False)
        result = _ferm_panel_from_csv(
            ferm_process.PiTable, csv_buf.getvalue()
        ).process()
        assert not result.empty
        assert (result['Tank'] == 'M1').all()
        assert 'Time (h)' in result.columns
        assert 'Stirrer (rpm)' in result.columns
        assert 'OUR (mmol/h)' in result.columns
        assert 'CER (mmol/h)' in result.columns

    def test_empty_table_returns_empty_dataframe(self):
        csv_buf = io.StringIO()
        pd.DataFrame(columns=['TFT', 'Airflow (LPM)']).to_csv(csv_buf, index=False)
        result = _ferm_panel_from_csv(
            ferm_process.PiTable, csv_buf.getvalue()
        ).process()
        assert result.empty
