# biocanvas/utils/stats.py
"""Statistical analysis pipeline: descriptive stats and significance testing."""

import numpy as np
import pandas as pd
from scipy import stats
from typing import Dict, List, Optional, Tuple, Any
import logging
from biocanvas.helix.config import SIGNIFICANCE_TEST_CONFIG

logger = logging.getLogger(__name__)

ALPHA: float = SIGNIFICANCE_TEST_CONFIG.get("alpha", 0.05)
SHAPIRO_THRESHOLD: float = SIGNIFICANCE_TEST_CONFIG.get("shapiro_threshold", 0.05)
MIN_SAMPLE_SIZE_FOR_TESTS: int = SIGNIFICANCE_TEST_CONFIG.get(
    "min_sample_size_for_tests", 3
)


class StatsCalculationError(Exception):
    """Raised when statistical analysis fails on valid plot data."""

    pass


def _pivot_analysis_data(
    data: pd.DataFrame,
    x: str,
    y: List[Tuple[str, str]],
    hue: Optional[str],
) -> pd.DataFrame:
    """Reshapes data into a wide pivot table ready for statistical testing.

    When multiple y-columns are provided they are summed into a single 'Total'
    column before pivoting, so downstream test helpers always work with one
    value column.

    Args:
        data: Source DataFrame.
        x: Column name for the primary grouping variable (becomes pivot columns).
        y: One or more column names containing the values to analyse.
        hue: Optional secondary grouping variable (adds a second column level).

    Returns:
        Wide-format DataFrame whose columns are the unique x values (or
        (hue, x) tuples when hue is provided).
    """
    if len(y) > 1:
        # Sum multiple y-columns into a single 'Total' series before pivoting
        data = data.copy()
        data["Total"] = data[y].sum(axis=1).values  # type: ignore
        y = ["Total"]  # type: ignore

    pivot_cols = [hue, x] if hue is not None else x
    return data.pivot(columns=pivot_cols, values=y[0])  # type: ignore


def _check_normality(groups: List[np.ndarray[Any, Any]]) -> bool:
    """
    Checks whether all provided groups pass the Shapiro-Wilk normality test, using set thresholds.

    Any group with fewer than MIN_SAMPLE_SIZE_FOR_TESTS valid observations, or with zero variance,
    is automatically treated as non-normal (returns False), since the Shapiro-Wilk test is unreliable
    for such groups.

    Args:
        groups (List[np.ndarray[Any, Any]]): A list of numeric arrays (one per group), each representing
            the data samples within that group.

    Returns:
        bool: True if all groups are plausibly normal (i.e., each passes the Shapiro-Wilk test at
              SHAPIRO_THRESHOLD and contains at least MIN_SAMPLE_SIZE_FOR_TESTS distinct values);
              False otherwise.

    Notes:
        - The Shapiro-Wilk threshold and minimum sample size are configurable via config.
        - This function is used to determine which statistical test (parametric or non-parametric)
          to use downstream in significance testing.
    """
    for group in groups:
        # Sample size check
        if len(group) < MIN_SAMPLE_SIZE_FOR_TESTS:
            return False

        # Variance check
        if np.ptp(group) == 0:  # type: ignore
            return False

        # Normality check
        _, p_value = stats.shapiro(group)  # type: ignore
        if p_value < SHAPIRO_THRESHOLD:
            return False
    return True


def _benjamini_hochberg_adjust(p_values: List[float]) -> List[float]:
    """Adjust p-values using the Benjamini-Hochberg false discovery rate procedure.

    Args:
        p_values: Raw p-values in the same order as the pairwise comparisons.

    Returns:
        FDR-adjusted p-values in the original input order.
    """
    if not p_values:
        return []

    n_tests = len(p_values)
    adjusted = [1.0] * n_tests
    sorted_indices = sorted(range(n_tests), key=lambda idx: p_values[idx])
    previous_adjusted = 1.0

    for rank, original_idx in enumerate(reversed(sorted_indices), start=1):
        p_value = p_values[original_idx]
        bh_rank = n_tests - rank + 1
        adjusted_p = min((p_value * n_tests) / bh_rank, previous_adjusted, 1.0)
        adjusted[original_idx] = adjusted_p
        previous_adjusted = adjusted_p

    return adjusted


def _run_pairwise_significance(
    pivot_data: pd.DataFrame,
    x: str,
    x_vals: List[Any],
    hue: Optional[str],
    hue_vals: Optional[List[Any]],
) -> pd.DataFrame:
    """
    Perform a significance test between two groups (pairwise comparison) for a given variable,
    automatically selecting Welch's t-test or Mann-Whitney U test based on normality.

    This function checks for normality in each group using the Shapiro-Wilk test. For each stratum (hue value, if provided):
      - If both groups are large enough and pass the normality test, use Welch's t-test with permutations.
      - If data are not normal, use the Mann-Whitney U test.
      - If sample sizes are too small (<3), no test is conducted.

    Args:
        pivot_data (pd.DataFrame): Wide-format DataFrame produced by _pivot_analysis_data
            (columns = groups, optionally MultiIndex if hue is present), containing numeric data.
        x (str): Name of the primary grouping variable.
        x_vals (List[Any]): The two unique values of the primary grouping variable.
        hue (Optional[str]): Name of the secondary grouping variable, or None.
        hue_vals (Optional[List[Any]]): Unique values of the hue variable, or None.

    Returns:
        pd.DataFrame: DataFrame indexed by (hue, (group1, group2)) if hue present, otherwise by (group1, group2),
        with columns:
            - 'Test' (str): Test used ("Welch's t-test", "Mann-Whitney U", or "No test").
            - 'Fold Change' (float or None): Fold change between group 1 and group 2.

            - 'Statistic' (float or None): Test statistic value.
            - 'p-value' (float or None): Significance p-value.
            - f'Significant (α={ALPHA})' (str): "Yes" or "No" specifying significance at chosen threshold.
            - 'Note' (str): Information about sample sizes, normality, or the chosen method.

    Raises:
        KeyError: If pivot_data does not contain the required group columns.
    """
    _COLS = [
        "Test",
        "Fold Change",
        "Statistic",
        "p-value",
        f"Significant (α={ALPHA})",
        "Note",
    ]
    pair = (x_vals[0], x_vals[1])
    note = ""
    rows: Dict[Any, Any] = {}  # type: ignore

    # Create strata for the hue column
    strata = [(h,) for h in hue_vals] if hue_vals is not None else [None]

    for stratum in strata:
        # Get the data for the two groups
        if stratum is not None:
            g1: np.ndarray[float, Any] = (
                pivot_data.get(
                    (stratum[0], pair[0]),  # type: ignore
                    pd.Series(dtype=float),
                )
                .dropna()
                .to_numpy()
            )  # type: ignore
            g2: np.ndarray[float, Any] = (
                pivot_data.get(
                    (stratum[0], pair[1]),  # type: ignore
                    pd.Series(dtype=float),
                )
                .dropna()
                .to_numpy()
            )  # type: ignore
            idx_key = (stratum[0], pair)
        else:
            g1: np.ndarray[float, Any] = (
                pivot_data.get(pair[0], pd.Series(dtype=float)).dropna().to_numpy()
            )  # type: ignore
            g2: np.ndarray[float, Any] = (
                pivot_data.get(pair[1], pd.Series(dtype=float)).dropna().to_numpy()
            )  # type: ignore
            idx_key = pair

        # Run Welch's t-test or Mann-Whitney U test based on sample size and normality
        if len(g1) < MIN_SAMPLE_SIZE_FOR_TESTS or len(g2) < MIN_SAMPLE_SIZE_FOR_TESTS:  # type: ignore
            test_name = "No test"
            stat, p_val = None, None
            note = f"Sample size is small (n < {MIN_SAMPLE_SIZE_FOR_TESTS}). No test was performed."
        elif len(g1) < 10 or len(g2) < 10:  # type: ignore
            test_name = "Welch's t-test"
            stat, p_val = stats.ttest_ind(
                g1, g2, equal_var=False, alternative="two-sided"
            )  # type: ignore
            note = "Sample size is small (n < 10). Welch's t-test with permutation test to avoid bias."
        else:
            # Run normality check for groups with sample size >= 10
            if _check_normality([g1, g2]):  # type: ignore
                test_name = "Welch's t-test"
                stat, p_val = stats.ttest_ind(  # type: ignore
                    g1,
                    g2,
                    equal_var=False,
                    alternative="two-sided",
                    method=stats.PermutationMethod(n_resamples=1000, random_state=42),
                )
                note = "Shapiro-Wilk test: Data seems to be normally distributed."
            else:
                test_name = "Mann-Whitney U"
                stat, p_val = stats.mannwhitneyu(g1, g2, alternative="two-sided")  # type: ignore
                note = "Shapiro-Wilk test: Data seems to be not normally distributed."

        fold_change = (
            round(float(np.mean(g2) / np.mean(g1)), 3) if np.mean(g1) != 0 else None
        )  # type: ignore
        stat_out = round(float(stat), 3) if stat is not None else None  # type: ignore
        p_out = round(float(p_val), 3) if p_val is not None else None  # type: ignore
        sig_out = "Yes" if (p_val is not None and p_val < ALPHA) else "No"  # type: ignore
        rows[idx_key] = [test_name, fold_change, stat_out, p_out, sig_out, note]  # type: ignore

    if hue_vals is not None:
        index = pd.MultiIndex.from_tuples(rows.keys(), names=[hue, x])  # type: ignore
    else:
        # tupleize_cols=False prevents pandas from auto-promoting the single
        # (val1, val2) tuple entry into a MultiIndex, which would then reject
        # the plain-string name= argument with a ValueError.
        index = pd.Index([pair], name=x, tupleize_cols=False)

    return pd.DataFrame.from_dict(rows, orient="index", columns=_COLS).set_axis(index)  # type: ignore


def _run_omnibus_significance(
    pivot_data: pd.DataFrame,
    x: str,
    x_vals: List[Any],
    hue: Optional[str],
    hue_vals: Optional[List[Any]],
) -> pd.DataFrame:
    """Runs a two-stage omnibus + post-hoc test across 3 or more groups.

    Stage 1 — Omnibus (always run, one result per stratum):
        - Normal data  → one-way ANOVA  (scipy.stats.f_oneway)
        - Non-normal   → Kruskal-Wallis (scipy.stats.kruskal)

    Stage 2 — Post-hoc pairwise (only when omnibus p < 0.05):
        - Normal data  → Tukey HSD/Tukey-Kramer (scipy.stats.tukey_hsd), family-wise corrected.
        - Non-normal   → pairwise Mann-Whitney U with Benjamini-Hochberg FDR correction.
        - Pairs with either group below MIN_SAMPLE_SIZE_FOR_TESTS are skipped.

    Args:
        pivot_data: Wide-format DataFrame from _pivot_analysis_data.
        x: Primary grouping column name (used as index label).
        x_vals: Unique values of the primary grouping variable.
        hue: Optional secondary grouping column name.
        hue_vals: Unique values of the hue column, or None when hue is absent.

    Returns:
        DataFrame with columns ['Test', 'Fold Change', 'Statistic', 'p-value', f'Significant (α={ALPHA})', 'Note'].
        Each stratum has an 'Omnibus' row first, followed by post-hoc pair rows if
        the omnibus was significant. When hue is present, strata are stacked with a
        MultiIndex keyed on the hue values.
    """
    _COLS = [
        "Test",
        "Fold Change",
        "Statistic",
        "p-value",
        f"Significant (α={ALPHA})",
        "Note",
    ]
    k = len(x_vals)

    strata = [(h,) for h in hue_vals] if hue_vals is not None else [None]
    stratum_frames: List[pd.DataFrame] = []
    stratum_keys: List[Any] = []

    for stratum in strata:
        rows: Dict[Any, Any] = {}

        if stratum is not None:
            groups: List[np.ndarray[float, Any]] = [  # type: ignore
                pivot_data.get((stratum[0], v), pd.Series(dtype=float)).to_numpy()
                for v in x_vals  # type: ignore
            ]
        else:
            groups: List[np.ndarray[float, Any]] = [  # type: ignore
                pivot_data.get(v, pd.Series(dtype=float)).to_numpy()
                for v in x_vals  # type: ignore
            ]

        # Remove NaN values
        clean_groups = [g[~np.isnan(g)] for g in groups]

        # Remove groups with less than MIN_SAMPLE_SIZE_FOR_TESTS valid observations
        omnibus_groups = [g for g in clean_groups if len(g) > 0]
        group_sizes = [len(g) for g in clean_groups]
        has_small_group = any(size < MIN_SAMPLE_SIZE_FOR_TESTS for size in group_sizes)
        has_group_under_10 = any(size < 10 for size in group_sizes)

        # Groups with n < 10 are treated as non-normal to avoid unstable Shapiro-Wilk decisions.
        is_normal = False if has_group_under_10 else _check_normality(clean_groups)
        note = ""
        if has_small_group:
            note = f"At least one group has n < {MIN_SAMPLE_SIZE_FOR_TESTS}; post-hoc pairs involving small groups are skipped."
        elif has_group_under_10:
            note = "At least one group has n < 10; data are treated as non-normal."

        # --- Stage 1: omnibus ---
        if len(omnibus_groups) < 2:
            omni_name = "No test"
            omni_stat, omni_p = None, None
            note = "Fewer than two groups contain data. No omnibus test was performed."
        elif is_normal:
            # Run one-way ANOVA
            omni_stat, omni_p = stats.f_oneway(*clean_groups)  # type: ignore
            omni_name = "One-way ANOVA"
            if not np.isfinite(omni_p):  # type: ignore
                omni_p = 1.0
            if not np.isfinite(omni_stat):  # type: ignore
                omni_stat = 0.0
        else:
            # Run Kruskal-Wallis test
            omni_name = "Kruskal-Wallis"
            combined = (
                np.concatenate(omnibus_groups)
                if omnibus_groups
                else np.empty(0, dtype=float)
            )  # type: ignore
            if combined.size > 0 and np.ptp(combined) == 0:  # type: ignore
                omni_stat, omni_p = 0.0, 1.0
            else:
                try:
                    omni_stat, omni_p = stats.kruskal(*omnibus_groups)  # type: ignore
                except ValueError as exc:
                    if "identical" in str(exc).lower():
                        omni_stat, omni_p = 0.0, 1.0
                    else:
                        raise

        fold_change_out = "N/A"
        omni_stat_out = round(float(omni_stat), 3) if omni_stat is not None else None  # type: ignore
        omni_p_out = round(float(omni_p), 3) if omni_p is not None else None  # type: ignore
        omni_sig_out = "Yes" if (omni_p is not None and omni_p < ALPHA) else "No"  # type: ignore
        rows["Omnibus"] = [
            omni_name,
            fold_change_out,
            omni_stat_out,
            omni_p_out,
            omni_sig_out,
            note,
        ]

        # --- Stage 2: post-hoc (only when omnibus is significant) ---
        if omni_p is not None and omni_p < ALPHA:
            if is_normal:
                tukey = stats.tukey_hsd(*clean_groups)  # type: ignore
                for i in range(k):
                    for j in range(i + 1, k):
                        p_adj = float(tukey.pvalue[i, j])
                        stat_val = float(tukey.statistic[i, j])
                        pair_key = (x_vals[i], x_vals[j])
                        fold_change = (
                            round(
                                float(
                                    np.mean(clean_groups[j]) / np.mean(clean_groups[i])
                                ),
                                3,
                            )
                            if np.mean(clean_groups[i]) != 0
                            else None
                        )  # type: ignore
                        stat_out = round(stat_val, 3) if stat_val is not None else None  # type: ignore
                        p_out = round(p_adj, 3) if p_adj is not None else None  # type: ignore
                        sig_out = (
                            "Yes" if (p_adj is not None and p_adj < ALPHA) else "No"
                        )  # type: ignore
                        note = "Tukey HSD controls family-wise error; SciPy applies Tukey-Kramer for unequal group sizes."
                        rows[pair_key] = [
                            "Tukey HSD / Tukey-Kramer",
                            fold_change,
                            stat_out,
                            p_out,
                            sig_out,
                            note,
                        ]
            else:
                pairwise_results: List[Tuple[Any, float, float, float]] = []
                for i in range(k):
                    for j in range(i + 1, k):
                        pair_key = (x_vals[i], x_vals[j])
                        fold_change_out = (
                            round(
                                float(
                                    np.mean(clean_groups[j]) / np.mean(clean_groups[i])
                                ),
                                3,
                            )
                            if np.mean(clean_groups[i]) != 0
                            else None
                        )  # type: ignore
                        if (
                            len(clean_groups[i]) < MIN_SAMPLE_SIZE_FOR_TESTS
                            or len(clean_groups[j]) < MIN_SAMPLE_SIZE_FOR_TESTS
                        ):
                            rows[pair_key] = [
                                "No test",
                                fold_change_out,
                                None,
                                None,
                                "No",
                                f"Sample size is small (n < {MIN_SAMPLE_SIZE_FOR_TESTS}). No post-hoc test was performed.",
                            ]
                            continue
                        mwu_stat, p_raw = stats.mannwhitneyu(
                            clean_groups[i], clean_groups[j], alternative="two-sided"
                        )  # type: ignore
                        pairwise_results.append(
                            (pair_key, fold_change_out, float(mwu_stat), float(p_raw))
                        )  # type: ignore

                adjusted_p_values = _benjamini_hochberg_adjust(
                    [result[3] for result in pairwise_results]
                )
                for (pair_key, fold_change_out, mwu_stat, _p_raw), p_adj in zip(
                    pairwise_results, adjusted_p_values
                ):
                    rows[pair_key] = [
                        "MWU (FDR-BH)",
                        fold_change_out,
                        round(float(mwu_stat), 3),
                        round(p_adj, 3),
                        "Yes" if p_adj < ALPHA else "No",
                        "Mann-Whitney U p-value adjusted using Benjamini-Hochberg FDR.",
                    ]
        stratum_frames.append(
            pd.DataFrame.from_dict(rows, orient="index", columns=_COLS)
        )  # type: ignore
        if stratum is not None:
            stratum_keys.append(stratum[0])

    if hue_vals is not None:
        return pd.concat(stratum_frames, keys=stratum_keys, names=[hue])
    return stratum_frames[0]


def calculate_stats(
    data: pd.DataFrame,
    x: str,
    y: List[Tuple[str, str]],
    hue: Optional[str],
    run_sig_test: bool = False,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Calculates descriptive statistics and significance tests with automatic test selection.

    Normality is assessed per-group via Shapiro-Wilk (α=0.05). The test chosen
    depends on the number of unique x-values:

    - 2 groups, normal     → Welch's t-test
    - 2 groups, non-normal → Mann-Whitney U
    - 3+ groups            → two-stage approach:
        Stage 1 (always): one-way ANOVA (normal) or Kruskal-Wallis (non-normal)
        Stage 2 (if stage-1 p < 0.05): Tukey HSD/Tukey-Kramer (normal) or
            FDR-adjusted pairwise Mann-Whitney U (non-normal)

    Args:
        data: DataFrame containing the data to analyse.
        x: Column name for the primary grouping variable.
        y: One or more column names containing the values to analyse. When
            multiple columns are supplied they are summed into a 'Total' column.
        hue: Optional secondary grouping variable. Tests are run independently
            within each stratum defined by this column.
        run_sig_test: Whether to run the significance test.
    Returns:
        Tuple of (descriptive_stats, significance_stats):
            - descriptive_stats: DataFrame of summary statistics (mean, std, …)
              indexed by group.
            - significance_stats: DataFrame with columns
              ['Test', 'Statistic', 'p-value', 'Significant (α=0.05)']. For the
              3+ group case, an 'Omnibus' row appears first per stratum, followed
              by post-hoc pair rows if the omnibus test was significant.
    """
    # Check if data, x, or y is empty and log (WARNING = error)
    if data.empty or not x or not y:
        logger.warning("calculate_stats: data is empty or x or y is empty.")
        raise StatsCalculationError(
            "calculate_stats: data is empty or x or y is empty."
        )

    try:
        # Pivot the data for pairwise or omnibus significance test and log (DEBUG = detailed)
        pivot_data = _pivot_analysis_data(data, x, y, hue)
        logger.debug("calculate_stats: pivot_data shape=%s", pivot_data.shape)

        # Determine number of groups for each x and hue value and log (DEBUG = detailed)
        x_vals: List[Any] = data[x].unique().tolist()  # type: ignore
        logger.debug("calculate_stats: x_vals=%s", x_vals)  # type: ignore
        hue_vals: List[Any] = data[hue].unique().tolist() if hue is not None else None  # type: ignore
        logger.debug("calculate_stats: hue_vals=%s", hue_vals)

        # Run the significance test if requested and if the number of groups is appropriate
        sig_table: pd.DataFrame = pd.DataFrame()
        if run_sig_test and len(x_vals) == 2:  # type: ignore
            sig_table = _run_pairwise_significance(pivot_data, x, x_vals, hue, hue_vals)  # type: ignore
        elif run_sig_test and len(x_vals) > 2:  # type: ignore
            sig_table = _run_omnibus_significance(pivot_data, x, x_vals, hue, hue_vals)  # type: ignore
        else:
            logger.warning(
                "calculate_stats: no significance test run because the number of groups is not appropriate."
            )

        return pivot_data.describe().round(5).T.sort_index(), sig_table  # type: ignore
    except StatsCalculationError:
        raise
    except Exception as e:
        raise StatsCalculationError(f"Statistics calculation failed: {e}") from e
