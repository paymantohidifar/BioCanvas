# biocanvas/utils/helpers.py
"""Shared primitives: type aliases, exceptions, and cross-cutting table helpers."""

import io
import os
import cProfile
import pstats
import pandas as pd  # type: ignore
from typing import Callable, Tuple, TypeVar, Any  # type: ignore
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Type alias for a structured HTML log entry: (message, severity_level)
LogEntry = Tuple[str, str]


def is_seed_tank(tank: Any) -> bool:
    """Returns True if *tank* identifies a seed vessel (name starts with ``S``).

    Seed tanks use an ``S`` prefix (e.g. ``S1``). Comparison is case-sensitive on
    the first character to match metadata conventions.

    Args:
        tank: Tank label from metadata, Benchling, or process tables.

    Returns:
        True when the tank should be treated as a seed stage.
    """
    if tank is None or (isinstance(tank, float) and pd.isna(tank)):  # type: ignore
        return False
    name = str(tank)
    return len(name) > 0 and name[0] == "S"


def profile_method(method: Callable[..., T]) -> Callable[..., T]:
    """Profiles run time of a class method.

    This decorator wraps a method to profile its execution time and print
    performance statistics using cProfile.

    Args:
        method: The method to be profiled.

    Returns:
        A wrapped method that profiles execution time.

    Example:
        @profile_method
        def my_function():
            # function implementation
            pass
    """

    def wrapper(*args: Any, **kwargs: Any) -> T:
        if not os.environ.get("BIOCANVAS_PROFILE"):
            return method(*args, **kwargs)
        profiler = cProfile.Profile()
        profiler.enable()
        result = method(*args, **kwargs)
        profiler.disable()
        s: io.StringIO = io.StringIO()
        ps: pstats.Stats = pstats.Stats(profiler, stream=s).sort_stats("cumulative")
        ps.print_stats()
        logger.debug("profile_method [%s]:\n%s", method.__qualname__, s.getvalue())
        return result

    return wrapper


def flatten_multiindex_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Returns a copy of df with MultiIndex columns flattened to plain strings.

    Column tuples are joined as 'Level0 | Level1'. If Level1 is an empty string,
    only Level0 is used as the column name.

    Args:
        df: DataFrame whose columns form a two-level MultiIndex.

    Returns:
        A deep copy of df with flattened, human-readable column names.
    """
    flat = df.copy(deep=True)
    flat.columns = pd.Index(
        [col[0] if col[1] == "" else f"{col[0]} | {col[1]}" for col in flat.columns]
    )  # type: ignore
    return flat


def join_kpi_data_on_index(
    kpi1_data: pd.DataFrame, kpi2_data: pd.DataFrame
) -> pd.DataFrame:
    """Joins two KPI dataframes on the index.

    Args:
        kpi1_data: First KPI data.
        kpi2_data: Second KPI data.

    Returns:
        Inner-joined DataFrame on Tank, Time (h), and Replicate columns.
    """
    joined_data = kpi1_data.set_index(
        [  # type: ignore
            ("Tank", ""),
            ("Time (h)", ""),
            ("Replicate", ""),
        ]
    ).join(
        kpi2_data.set_index([("Tank", ""), ("Time (h)", ""), ("Replicate", "")]),
        how="inner",
    )  # type: ignore
    return joined_data.reset_index()


class EmptyTableError(Exception):
    """Exception raised when a table is empty.

    This exception is raised when operations are attempted on empty
    data tables where data is expected to be present.
    """

    pass


class PlottingError(Exception):
    """Exception raised when a plotting operation fails.

    This exception is raised when plotting operations fail due to unexpected issues.
    """

    pass
