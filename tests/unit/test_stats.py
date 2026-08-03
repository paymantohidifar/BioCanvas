"""Tests for biocanvas.utils.stats."""

import numpy as np
import pytest
import pandas as pd
from unittest.mock import patch

from biocanvas.utils import stats as utils_stats
from biocanvas.helix.config import SIGNIFICANCE_TEST_CONFIG


# =============================================================================
# calculate_stats — degenerate omnibus cases (Kruskal edge case)
# =============================================================================


class TestCalculateStatsDegenerateOmnibus:
    """calculate_stats tests when KPI values are constant across groups (SciPy Kruskal edge case)."""

    def test_three_groups_constant_y_completes_with_non_significant_omnibus(self):
        rows = []
        for x in (1, 2, 3):
            for _ in range(5):
                rows.append({"Condition_num": x, "KPI": 42.0})
        data = pd.DataFrame(rows)
        _summary, sig = utils_stats.calculate_stats(
            data=data, x="Condition_num", y=["KPI"], hue=None, run_sig_test=True
        )
        omnibus = sig.loc["Omnibus"]
        assert omnibus["Significant (α=0.05)"] == "No"
        assert float(omnibus["p-value"]) == pytest.approx(1.0)

    @patch("biocanvas.utils.stats._check_normality", return_value=False)
    def test_constant_y_kruskal_path_omnibus_p_one(self, _mock_norm):
        rows = []
        for x in (1, 2, 3):
            for _ in range(5):
                rows.append({"Condition_num": x, "KPI": 3.14})
        data = pd.DataFrame(rows)
        _summary, sig = utils_stats.calculate_stats(
            data=data, x="Condition_num", y=["KPI"], hue=None, run_sig_test=True
        )
        omnibus = sig.loc["Omnibus"]
        assert omnibus["Test"] == "Kruskal-Wallis"
        assert omnibus["p-value"] == 1.0
        assert omnibus["Statistic"] == 0.0

    @patch("biocanvas.utils.stats._check_normality", return_value=False)
    def test_constant_y_kruskal_path_with_hue_strata(self, _mock_norm):
        rows = []
        for hue_val in ("early", "late"):
            for x in (10, 20, 30):
                for _ in range(4):
                    rows.append({"Time": hue_val, "Condition_num": x, "KPI": 0.0})
        data = pd.DataFrame(rows)
        _summary, sig = utils_stats.calculate_stats(
            data=data, x="Condition_num", y=["KPI"], hue="Time", run_sig_test=True
        )
        for hue_val in data["Time"].unique():
            row = sig.loc[(hue_val, "Omnibus")]
            assert row["Test"] == "Kruskal-Wallis"
            assert row["p-value"] == 1.0
            assert row["Significant (α=0.05)"] == "No"


# =============================================================================
# _run_pairwise_significance — test-selection logic, output schema, significance
# =============================================================================

ALPHA = float(SIGNIFICANCE_TEST_CONFIG.get("alpha", 0.05))
_EXPECTED_PAIRWISE_COLS = [
    "Test",
    "Fold Change",
    "Statistic",
    "p-value",
    f"Significant (α={ALPHA})",
    "Note",
]

_PATCH_NORMALITY = "biocanvas.utils.stats._check_normality"


class TestRunPairwiseSignificance:
    """_run_pairwise_significance selects the correct test and shapes its output."""

    @staticmethod
    def _make_pivot(
        g1_vals: list,
        g2_vals: list,
        key1: int = 1,
        key2: int = 2,
    ) -> pd.DataFrame:
        """Build a two-column pivot DataFrame directly without going through _pivot_analysis_data."""
        return pd.DataFrame({key1: pd.Series(g1_vals), key2: pd.Series(g2_vals)})

    @staticmethod
    def _make_hue_pivot(g1_early, g2_early, g1_late, g2_late) -> pd.DataFrame:
        """Build a MultiIndex-column pivot for two hue strata ('early', 'late') and two groups (1, 2)."""
        data = pd.DataFrame(
            {
                "Cond": [1] * len(g1_early)
                + [2] * len(g2_early)
                + [1] * len(g1_late)
                + [2] * len(g2_late),
                "KPI": g1_early + g2_early + g1_late + g2_late,
                "Time": (
                    ["early"] * (len(g1_early) + len(g2_early))
                    + ["late"] * (len(g1_late) + len(g2_late))
                ),
            }
        )
        return utils_stats._pivot_analysis_data(data, x="Cond", y=["KPI"], hue="Time")

    # ------------------------------------------------------------------
    # 1. Output schema
    # ------------------------------------------------------------------

    @patch(_PATCH_NORMALITY, return_value=False)
    def test_returns_correct_columns(self, _mock_norm):
        pivot = self._make_pivot([1.0, 2.0, 3.0, 4.0, 5.0], [6.0, 7.0, 8.0, 9.0, 10.0])
        result = utils_stats._run_pairwise_significance(
            pivot, "Cond", [1, 2], None, None
        )
        assert list(result.columns) == _EXPECTED_PAIRWISE_COLS

    # ------------------------------------------------------------------
    # 2. Index shape without hue
    # ------------------------------------------------------------------

    @patch(_PATCH_NORMALITY, return_value=False)
    def test_index_is_plain_pair_tuple_without_hue(self, _mock_norm):
        pivot = self._make_pivot([1.0, 2.0, 3.0, 4.0, 5.0], [6.0, 7.0, 8.0, 9.0, 10.0])
        result = utils_stats._run_pairwise_significance(
            pivot, "Cond", [1, 2], None, None
        )
        assert not isinstance(result.index, pd.MultiIndex)
        assert result.index[0] == (1, 2)

    # ------------------------------------------------------------------
    # 3. Index shape with hue
    # ------------------------------------------------------------------

    @patch(_PATCH_NORMALITY, return_value=False)
    def test_index_is_multiindex_when_hue_supplied(self, _mock_norm):
        vals = [1.0, 2.0, 3.0, 4.0, 5.0]
        pivot = self._make_hue_pivot(vals, vals, vals, vals)
        result = utils_stats._run_pairwise_significance(
            pivot, "Cond", [1, 2], "Time", ["early", "late"]
        )
        assert isinstance(result.index, pd.MultiIndex)
        assert result.index.names == ["Time", "Cond"]
        assert ("early", (1, 2)) in result.index
        assert ("late", (1, 2)) in result.index

    # ------------------------------------------------------------------
    # 4. Test selection: Mann-Whitney U for non-normal data (n >= 10)
    # ------------------------------------------------------------------

    @patch(_PATCH_NORMALITY, return_value=False)
    def test_uses_mann_whitney_for_non_normal_data(self, _mock_norm):
        g = list(range(1, 16))  # n = 15
        pivot = self._make_pivot(g, [v + 50 for v in g])
        result = utils_stats._run_pairwise_significance(
            pivot, "Cond", [1, 2], None, None
        )
        row = result.iloc[0]
        assert row["Test"] == "Mann-Whitney U"
        assert "not normally distributed" in row["Note"]

    # ------------------------------------------------------------------
    # 5. Test selection: Welch's t-test for normal data (n >= 10)
    # ------------------------------------------------------------------

    @patch(_PATCH_NORMALITY, return_value=True)
    def test_uses_welch_ttest_for_normal_data(self, _mock_norm):
        rng = np.random.default_rng(42)
        g1 = rng.normal(loc=0.0, scale=1.0, size=15).tolist()
        g2 = rng.normal(loc=0.0, scale=1.0, size=15).tolist()
        pivot = self._make_pivot(g1, g2)
        result = utils_stats._run_pairwise_significance(
            pivot, "Cond", [1, 2], None, None
        )
        row = result.iloc[0]
        assert row["Test"] == "Welch's t-test"
        assert "normally distributed" in row["Note"]

    # ------------------------------------------------------------------
    # 6. Significance label: clearly separated groups → "Yes"
    # ------------------------------------------------------------------

    def test_marks_significant_for_clearly_separated_groups(self):
        g1 = list(np.linspace(0, 0.5, 15))
        g2 = list(np.linspace(100, 100.5, 15))
        pivot = self._make_pivot(g1, g2)
        result = utils_stats._run_pairwise_significance(
            pivot, "Cond", [1, 2], None, None
        )
        assert result.iloc[0]["Significant (α=0.05)"] == "Yes"

    # ------------------------------------------------------------------
    # 7. Significance label: identical groups → "No"
    # ------------------------------------------------------------------

    def test_marks_not_significant_for_identical_groups(self):
        g = list(range(1, 16))
        pivot = self._make_pivot(g, g)
        result = utils_stats._run_pairwise_significance(
            pivot, "Cond", [1, 2], None, None
        )
        assert result.iloc[0]["Significant (α=0.05)"] == "No"

    # ------------------------------------------------------------------
    # 8. n < 3 → intended behaviour per docstring
    # ------------------------------------------------------------------

    def test_no_test_intended_when_n_lt_3(self):
        # The docstring states: "If sample sizes are too small (<3), no test is conducted."
        # BUG: the normality-check block (lines 147-154 of stats.py) runs unconditionally
        # and overwrites the "No test" assignment, so the function currently returns
        # "Mann-Whitney U" for n < 3.  This test documents the INTENDED behaviour and
        # will pass once the bug is fixed by nesting lines 147-154 inside the `else` branch.
        pivot = self._make_pivot([1.0, 2.0], [3.0, 4.0])  # n = 2 per group
        result = utils_stats._run_pairwise_significance(
            pivot, "Cond", [1, 2], None, None
        )
        row = result.iloc[0]
        assert row["Test"] == "No test"
        assert row["Statistic"] is None
        assert row["p-value"] is None
