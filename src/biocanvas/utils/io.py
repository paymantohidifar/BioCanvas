# biocanvas/utils/io.py
"""File I/O utilities: directories, module loading, table classes, reports, ZIP, and local data client."""

import os
import shutil
import base64
import importlib
import pandas as pd  # type: ignore
from zipfile import ZipFile, ZIP_DEFLATED
from datetime import datetime
from typing import Dict, List, Optional, Tuple  # type: ignore
import logging
from biocanvas.db.local_database import LocalDataBase
from biocanvas.utils import helpers

logger = logging.getLogger(__name__)


def setup_output_dirs(dir_li: List[str]) -> None:
    """Sets up output directories for analysis.

    Removes the first directory if it exists and creates all directories
    in the provided list.

    Args:
        dir_li: List of directory paths. The first directory will be removed
                if it exists, and all directories will be created.
    """
    if os.path.isdir(dir_li[0]):
        recursive_remove_dir(dir_li[0])
    for subdir in dir_li[1:]:
        os.makedirs(subdir)


def load_module(module_path: str) -> Optional[object]:
    """Loads a Python module dynamically.

    Args:
        module_path: The path to the module to import.

    Returns:
        The imported module object, or None if import fails.
    """
    return importlib.import_module(module_path)


def resolve_process_zip_candidates() -> Tuple[Tuple[str, str], Tuple[str, str]]:
    """Returns ordered (zip_filename, panel_class_name) pairs to try without listing.

    Returns:
        ``(('Eve.zip', 'EveTable'), ('Pi.zip', 'PiTable'))``.
    """
    return ("Eve.zip", "EveTable"), ("Pi.zip", "PiTable")


def detect_process_file_type(filenames: List[str]) -> Tuple[str, str]:
    """Determines whether an experiment uses Eve or Pi fermentation process files.

    Args:
        filenames: List of filenames present in the experiment's local data directory.

    Returns:
        A (process_filename, process_panel_classname) tuple,
        e.g. ('Eve.zip', 'EveTable') or ('Pi.zip', 'PiTable').

    Raises:
        FileNotFoundError: If neither 'Eve.zip' nor 'Pi.zip' is found in filenames.
    """
    if "Eve.zip" in filenames:
        return "Eve.zip", "EveTable"
    if "Pi.zip" in filenames:
        return "Pi.zip", "PiTable"
    raise FileNotFoundError("Neither Eve.zip nor Pi.zip found in experiment directory.")


def normalize_sample_labels(series: pd.Series) -> pd.Series:
    """Normalise Benchling sample label strings to a standard 3-segment format.

    Replaces any spaces with hyphens (to handle labels that deviate from the
    standard format), then truncates to the first three hyphen-delimited
    segments (e.g. 'M1-R1-T24h').

    Args:
        series: Series of raw sample label strings.

    Returns:
        Series of normalised sample label strings.
    """
    return (
        series.str.replace(" ", "-", regex=False).str.split("-").str[:3].str.join("-")
    )  # type: ignore


def zip_files(
    source_dir: str, save_dir: str, zip_name: str = "compressed_results.zip"
) -> None:
    """Creates a compressed zip file from source directory contents.

    Recursively compresses all files in the source directory into a zip file
    saved in the specified save directory.

    Args:
        source_dir: Directory path containing files to compress.
        save_dir: Directory path to save the compressed zip file.
        zip_name: Name of the output zip file. Defaults to "compressed_results.zip".

    Raises:
        ValueError: If source_dir or save_dir is empty.
    """
    if not source_dir or not save_dir:
        raise ValueError("Both source_dir and save_dir must be provided.")

    zip_path = os.path.join(save_dir, zip_name)
    with ZipFile(zip_path, "w", ZIP_DEFLATED) as zip_file:
        for root, _, files in os.walk(source_dir):
            for file in files:
                abs_path = os.path.join(root, file)
                arc_path = os.path.relpath(abs_path, os.path.join(source_dir, ".."))
                zip_file.write(abs_path, arc_path)


def _read_csv_cached(path: str, cache: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Reads a CSV file once per *cache* dict keyed by absolute path."""
    if path not in cache:
        cache[path] = pd.read_csv(path)  # type: ignore
    return cache[path]


def create_xlsx_report(
    plot_names: List[str],
    plot_description: Dict[str, pd.DataFrame],
    source_dir: str,
    save_dir: str,
    report_name: str = "report.xlsx",
) -> None:
    """Creates an Excel report with plot data and descriptions.

    Generates a comprehensive Excel report containing plot descriptions,
    raw data, summary statistics, and significance test results for each plot.

    Args:
        plot_names: List of plot names to include in the report.
        plot_description: Mapping of plot name to its description DataFrame.
        source_dir: Directory path containing source data files.
        save_dir: Directory path to save the Excel report.
        report_name: Name of the output Excel file. Defaults to "report.xlsx".

    Raises:
        ValueError: If any required argument is empty or None.
    """
    if not plot_names or not plot_description or not source_dir or not save_dir:
        raise ValueError(
            "plot_names, plot_description, source_dir and save_dir must all be provided."
        )

    report_path = os.path.join(save_dir, report_name)
    csv_cache: Dict[str, pd.DataFrame] = {}
    with pd.ExcelWriter(report_path, engine="xlsxwriter") as writer:  # type: ignore
        for plot_name in plot_names:
            startrow = 0
            startcol = 0

            if plot_name in plot_description:
                plot_description[plot_name].to_excel(
                    writer, sheet_name=plot_name, startrow=startrow, startcol=startcol
                )  # type: ignore
                startcol += plot_description[plot_name].shape[1] + 2

            raw_data_file_path = os.path.join(source_dir, f"raw_data_{plot_name}.csv")
            if os.path.exists(raw_data_file_path):
                raw_data = _read_csv_cached(raw_data_file_path, csv_cache)
                raw_data.to_excel(
                    writer,
                    sheet_name=plot_name,
                    startrow=startrow,
                    startcol=startcol,
                    index=False,
                )  # type: ignore
                startcol += raw_data.shape[1] + 1

            summary_stats_file_path = os.path.join(
                source_dir, f"summary_stats_{plot_name}.csv"
            )
            if os.path.exists(summary_stats_file_path):
                summary_stats = _read_csv_cached(summary_stats_file_path, csv_cache)
                summary_stats.to_excel(
                    writer,
                    sheet_name=plot_name,
                    startrow=startrow,
                    startcol=startcol,
                    index=False,
                )  # type: ignore
                startcol += summary_stats.shape[1] + 1

            stat_test_file_path = os.path.join(
                source_dir, f"significance_stats_{plot_name}.csv"
            )
            if os.path.exists(stat_test_file_path):
                stat_test = _read_csv_cached(stat_test_file_path, csv_cache)
                stat_test.to_excel(
                    writer,
                    sheet_name=plot_name,
                    startrow=startrow,
                    startcol=startcol,
                    index=False,
                )  # type: ignore
                startcol += stat_test.shape[1] + 1
                del stat_test

            worksheet = writer.sheets[plot_name]
            worksheet.insert_image(
                1, startcol, os.path.join(source_dir, f"{plot_name}.png")
            )


def _render_collapsible_table(
    label: str,
    df: pd.DataFrame,
    header: bool = True,
    index: bool = True,
    open_by_default: bool = False,
) -> str:
    """Renders a pandas DataFrame as a collapsible HTML <details> block.

    Args:
        label: Display text shown in the <summary> toggle.
        df: DataFrame to render as an HTML table.
        header: If True the table has a header. Defaults to True.
        index: If True the table has an index. Defaults to True.
        open_by_default: If True the section starts expanded. Defaults to False.

    Returns:
        An HTML string containing a <details> block with the table inside.
    """
    open_attr = " open" if open_by_default else ""
    table_html = df.to_html(
        classes="report-table", border=0, index=index, header=header
    )  # type: ignore
    return f"<details{open_attr}>\n  <summary>{label}</summary>\n  {table_html}\n</details>\n"


def create_html_report(
    plot_names: List[str],
    plot_description: Dict[str, pd.DataFrame],
    source_dir: str,
    save_dir: str,
    project_version: str,
    report_name: str = "report.html",
) -> None:
    """Creates a self-contained HTML report with collapsible data sections per plot.

    For each plot the report embeds the PNG image and renders the plot description,
    raw data, summary statistics, and significance test results in collapsible
    <details> blocks. All images are base64-encoded so the HTML file is portable.

    Args:
        plot_names: List of plot names to include in the report.
        plot_description: Mapping of plot name to its description DataFrame.
        source_dir: Directory path containing source CSV and PNG files.
        save_dir: Directory path to save the HTML report.
        project_version: Version of the project.
        report_name: Name of the output HTML file. Defaults to "report.html".

    Raises:
        ValueError: If any required argument is empty or None.
    """
    if not plot_names or not plot_description or not source_dir or not save_dir:
        raise ValueError(
            "plot_names, plot_description, source_dir and save_dir must all be provided."
        )

    _HTML_CSS = """
    <style>
      body { font-family: sans-serif; margin: 2rem; color: #333; }
      h1 { border-bottom: 3px solid #ccc; padding-bottom: 0.4rem; }
      section { margin-bottom: 3rem; border-bottom: 1px solid #ccc; padding-bottom: 0.4rem; margin-top: 0.4rem; }
      h2 { margin-top: 0; }
      img.plot-image { max-width: 100%; height: auto; display: block; margin-bottom: 1rem; }
      details { margin: 0.5rem 0; border: 1px solid #ddd; border-radius: 4px; padding: 0.5rem; }
      summary { cursor: pointer; font-weight: bold; padding: 0.25rem 0; }
      table.report-table { border-collapse: collapse; font-size: 0.85rem; width: 100%; }
      table.report-table th, table.report-table td {
        border: 1px solid #ccc; padding: 4px 8px; text-align: left; }
      table.report-table tr:nth-child(even) { background: #f9f9f9; }
    </style>
    """

    sections: List[str] = []
    csv_cache: Dict[str, pd.DataFrame] = {}
    for plot_name in plot_names:
        parts: List[str] = [f"<section>\n<h2>{plot_name}</h2>\n"]

        image_path = os.path.join(source_dir, f"{plot_name}.png")
        if os.path.exists(image_path):
            with open(image_path, "rb") as img_file:
                img_b64 = base64.b64encode(img_file.read()).decode("utf-8")
            parts.append(
                f'<img class="plot-image" src="data:image/png;base64,{img_b64}" alt="{plot_name}" />\n'
            )

        if plot_name in plot_description:
            parts.append(
                _render_collapsible_table(
                    "Description",
                    plot_description[plot_name],
                    header=False,
                    open_by_default=True,
                )
            )

        raw_data_path = os.path.join(source_dir, f"raw_data_{plot_name}.csv")
        if os.path.exists(raw_data_path):
            parts.append(
                _render_collapsible_table(
                    "Raw Data", _read_csv_cached(raw_data_path, csv_cache), index=False
                )
            )

        summary_stats_path = os.path.join(source_dir, f"summary_stats_{plot_name}.csv")
        if os.path.exists(summary_stats_path):
            parts.append(
                _render_collapsible_table(
                    "Summary Statistics",
                    _read_csv_cached(summary_stats_path, csv_cache),
                    index=False,
                )
            )

        stat_test_path = os.path.join(source_dir, f"significance_stats_{plot_name}.csv")
        if os.path.exists(stat_test_path):
            parts.append(
                _render_collapsible_table(
                    "Significance Tests",
                    _read_csv_cached(stat_test_path, csv_cache),
                    index=False,
                )
            )

        parts.append("</section>\n")
        sections.append("".join(parts))

    html_doc = (
        "<!DOCTYPE html>\n<html lang='en'>\n<head>\n"
        "<meta charset='UTF-8' />\n"
        "<meta name='viewport' content='width=device-width, initial-scale=1.0' />\n"
        "<title>BioSynic Report</title>\n"
        f"{_HTML_CSS}\n"
        "</head>\n<body>\n"
        f"<h1>BioSynic Report</h1>\n"
        f"<section>"
        f"<span><b>Project version:</b> {project_version}</span><br>"
        f"<span><b>Date:</b> {datetime.now().date()}</span><br>"
        f"<span><b>Time:</b> {datetime.now().time().strftime('%H:%M')}</span><br>"
        "</section>" + "".join(sections) + "</body>\n</html>\n"
    )

    report_path = os.path.join(save_dir, report_name)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html_doc)


def recursive_remove_dir(dir_path: str) -> None:
    """Recursively removes a directory and all its contents.

    Args:
        dir_path: Path to the directory to remove.

    Raises:
        ValueError: If dir_path does not exist or is not a directory.
    """
    if not os.path.isdir(dir_path):
        raise ValueError(f"Path does not exist or is not a directory: {dir_path}")
    shutil.rmtree(dir_path)


class GeneralTable:
    """A class for reading and processing result tables from zip files.

    Provides functionality to load and process different types of result tables
    from zipped file contents into pandas DataFrames.

    Attributes:
        table: The loaded table in its original format.

    Args:
        zip_ref: Zipped file contents containing the table data.
        file_name: Name of the file within the zipped content to load.
    """

    def __init__(self, zip_ref: ZipFile, file_name: str):
        self.table = GeneralTable._load_table(zip_ref, file_name)

    @staticmethod
    def _load_table(zip_ref: ZipFile, file_name: str) -> pd.DataFrame:
        """Reads a CSV file from zip contents into a pandas DataFrame.

        Args:
            zip_ref: Zipped file contents.
            file_name: Name of the file within the zipped content.

        Returns:
            DataFrame containing the original table content.
        """
        with zip_ref.open(file_name) as f:
            return pd.read_csv(f, na_values=["", "NA", "#VALUE!"])  # type: ignore

    @classmethod
    def get_classname(cls) -> str:
        """Returns the class name."""
        return cls.__name__


class GeneralAnalyteTable(GeneralTable):
    """A class for processing Benchling Bioanalytical result tables.

    Inherits from GeneralTable and provides specialized functionality for
    processing and parsing analyte concentration data from Benchling tables.

    Attributes:
        table: Original analyte table in its raw format.
        proc_table: Processed analyte table with parsed data.

    Args:
        zip_ref: Zipped file contents containing the analyte table.
        file_name: Name of the file within the zipped content to load.
    """

    def __init__(self, zip_ref: ZipFile, file_name: str):
        super().__init__(zip_ref, file_name)

    def process(self) -> pd.DataFrame:
        """Processes and normalizes the analyte results table from Benchling.

        This function supports both legacy (old format with 'Analyte' columns) and
        modern (one-sample-per-row) table structures. It standardizes sample labels,
        sets the index to the normalized sample, and, if in the old format, parses
        analyte columns into individual measurements with proper naming and units.

        Returns:
            pd.DataFrame: Processed analyte data organized such that columns are grouped
                under the panel class (e.g., 'Sugar', 'Brad') and indexed by normalized sample label.

        Raises:
            EmptyTableError: If the analyte table is empty or missing the 'Sample' column.
        """

        # Sanity check
        df = self.table.copy().dropna(axis="columns", how="all")
        if df.empty or df.get("Sample", None) is None:  # type: ignore
            raise helpers.EmptyTableError("Cannot proceed! Analyte table is empty!")

        # Normalize sample labels
        df["Sample"] = normalize_sample_labels(df["Sample"])  # type: ignore
        df.set_index("Sample", inplace=True)  # type: ignore

        proc_table: pd.DataFrame

        # Check if the table is in the old format
        old_format_table: bool = (
            df.columns.str.contains("Analyte").any()
            or df.columns.str.contains("Assay").any()
        )  # type: ignore

        if old_format_table:
            # Parse the table in the old format
            parsed_analytes: Dict[str, pd.Series] = {}
            for i in range(0, df.shape[1], 3):
                name, unit, values = GeneralAnalyteTable._parse_analyte_table(
                    df.iloc[:, i : i + 3]
                )  # type: ignore
                if name:
                    parsed_analytes[f"{name} ({unit})"] = values  # type: ignore
            proc_table = pd.DataFrame(parsed_analytes).reset_index().set_index("Sample")  # type: ignore
        else:
            # No need to parse the table in the new format as it is already in the correct format
            proc_table = df

        # Group the columns under the concrete panel class name (e.g. Sugar, Brad)
        return GeneralAnalyteTable._group_cols(
            proc_table, self.__class__.get_classname()
        )

    @staticmethod
    def _parse_analyte_table(
        df_chunk: pd.DataFrame,
    ) -> Tuple[Optional[str], Optional[str], pd.Series]:
        """
        Parses a DataFrame chunk representing a single analyte and extracts its name, normalized unit,
        and values as a Series.

        Args:
            df_chunk (pd.DataFrame): DataFrame slice corresponding to one analyte,
                typically with three columns (name, values, unit).

        Returns:
            Tuple[str | None, str | None, pd.Series]: A tuple containing:
                - The analyte name (str), or None if not found.
                - The standardized unit as a string (e.g., 'g/L', or original if not convertible), or None.
                - The values as a normalized pandas Series (float), or an empty Series if extraction fails.

        Notes:
            - Automatically normalizes values to 'g/L' if a supported unit conversion is used.
            - Returns (None, None, empty Series) if the analyte cannot be parsed from the chunk.
        """

        unit_conversion = {"g/L": 1.0, "mg/L": 1e3, "ug/L": 1e6}

        if df_chunk.dropna(axis="columns", how="all").shape[1] == 3:
            name: str = df_chunk.iloc[0, 0]  # type: ignore
            orig_unit: str = df_chunk.iloc[0, 2]  # type: ignore
            unit: str = "g/L" if orig_unit in unit_conversion.keys() else orig_unit  # type: ignore
            values: pd.Series = df_chunk.iloc[:, 1] / unit_conversion.get(
                orig_unit, 1.0
            )  # type: ignore
            return name, unit, values  # type: ignore
        else:
            return (None, None, pd.Series(dtype="object"))

    @staticmethod
    def _group_cols(df: pd.DataFrame, class_name: str) -> pd.DataFrame:
        """Categorizes processed table columns under class name outer level."""
        new_columns = pd.MultiIndex.from_product([[class_name], df.columns])
        df.columns = new_columns
        return df


class LocalDataClient:
    """A class for interacting with a project's local SQLite-backed drive.

    Previously backed by SharePoint/Microsoft Drive via an MS Graph client;
    now backed by :class:`~biocanvas.db.local_database.LocalDataBase`, a
    local SQLite database (one file per project). The public interface
    (``connect``, ``get_item_names``, ``load_data``) is unchanged so callers
    do not need to know the storage backend.

    Attributes:
        drive: LocalDataBase instance for local database interactions.
        data_dir: Filesystem path to the project's SQLite ``.db`` file.
    """

    def __init__(self):
        self.drive = LocalDataBase()
        self.data_dir = ""
        self._data_cache: Dict[str, bytes] = {}
        self._list_cache: Dict[str, List[str]] = {}

    def clear_cache(self) -> None:
        """Clears in-memory caches for ``load_data`` and ``get_item_names``."""
        self._data_cache.clear()
        self._list_cache.clear()

    def connect(self, project_name: str, data_dir: str):
        """Connects to a project's local SQLite database.

        Args:
            project_name: Name of the project (currently unused by the
                SQLite backend; kept for interface compatibility).
            data_dir: Filesystem path to the project's SQLite ``.db`` file.
        """
        self.clear_cache()
        self.data_dir: str = data_dir
        self.drive.connect(data_dir)

    def get_item_names(self, item: str = "") -> List[str]:
        """Gets list of item names from a directory in the local database.

        Args:
            item: Optional subdirectory path to list items from.

        Returns:
            List of item names in the specified directory.
        """
        cache_key = item
        if cache_key in self._list_cache:
            return list(self._list_cache[cache_key])
        names = self.drive.list_items(item)
        self._list_cache[cache_key] = names
        return names

    def load_data(self, item: str):
        """Loads data content for an item from the local database.

        Args:
            item: Path of the item to load data from.

        Returns:
            Data content from the specified item.
        """
        if item in self._data_cache:
            return self._data_cache[item]
        content = self.drive.data_content(item)
        self._data_cache[item] = content
        return content
