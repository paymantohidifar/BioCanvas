# biocanvas/helix/benchling.py
"""Benchling zip panel loaders and processors for Project Helix.

Each class corresponds to a Benchling assay panel CSV inside a zip export. Panels
load raw tables via :class:`~biocanvas.utils.io.GeneralTable` and
return processed :class:`pandas.DataFrame` objects from :meth:`process`, with columns
wrapped in a two-level :class:`pandas.MultiIndex` (panel class name for assay panels;
``(column_name, '')`` for :class:`Sample`).
"""
import zipfile
import pandas as pd # type: ignore
import logging
from biocanvas.utils.io import GeneralTable, GeneralAnalyteTable, normalize_sample_labels
from biocanvas.utils.helpers import EmptyTableError

logger = logging.getLogger(__name__)


class Sample(GeneralTable):
    """Processes Sample metadata tables exported from Benchling.

    Loads a sample information CSV from a Benchling zip archive, normalises sample
    labels from ``Entity``, and derives ``Tank``, ``Time (h)``, and ``Sample Vol (ml)``.
    The returned table is indexed by normalised sample name with columns wrapped as
    ``(column_name, '')`` MultiIndex tuples so ``Tank`` / ``Time (h)`` align with
    :mod:`data_service` consolidation and filtering.

    Args:
        zip_ref: Zipped file contents containing the sample table.
        file_name: Filename within the zip archive to load.

    Attributes:
        table: Raw sample table as read from Benchling.
    """
    def __init__(self, zip_ref: zipfile.ZipFile, file_name: str):
        super().__init__(zip_ref, file_name)

    def process(self) -> pd.DataFrame:
        """Normalises sample metadata and returns a MultiIndex-columned table.

        Renames Benchling column headers to standard names, builds normalised
        ``Sample`` labels from ``Entity``,         assigns ``Tank`` from the first hyphen segment of each sample label, fills
        numeric NaNs with 0, and wraps
        columns as ``(column_name, '')`` for downstream consolidation.

        Returns:
            DataFrame indexed by normalised sample label with MultiIndex columns
            ``('Tank', '')``, ``('Time (h)', '')``, and ``('Sample Vol (ml)', '')``.

        Raises:
            EmptyTableError: If the table is empty after dropping all-NaN columns.
            ValueError: If ``Sample`` or ``Sample Volume (mL)`` is missing.
        """
        df = self.table.copy().dropna(axis='columns', how='all')
        if df.empty:
            raise EmptyTableError('Sample table is empty!')

        essential_cols = ['Entity', 'Sample Volume (mL)']
        for col in essential_cols:
            if df.get(col, None) is None:  # type: ignore
                raise ValueError(f'Essential column {col} is missing from the Sample table!')

        # Update key columns' names in standard format
        df.rename(
            columns={
                'Timepoint (h)': 'Time (h)',
                'Parent Strain': 'Strain',
                'Sample Volume (mL)': 'Sample Vol (ml)',
            },
            inplace=True
        )
        # Update 'Sample' value to standard format
        df['Sample'] = normalize_sample_labels(df['Entity'])  # type: ignore
        
        # Add 'Tank' column: get the first hyphen-segment
        df['Tank'] = df['Sample'].str.split('-').str[0] # type: ignore

        proc_table = df[['Sample', 'Tank', 'Time (h)', 'Sample Vol (ml)']].set_index('Sample').fillna(0)  # type: ignore
        return Sample._group_cols(proc_table) # type: ignore
        # return proc_table

    @staticmethod
    def _group_cols(df: pd.DataFrame) -> pd.DataFrame:
        """Wraps columns in a two-level MultiIndex with the column names as the outer level.

        Args:
            df: Processed table with single-level column names.

        Returns:
            The same data with a ``(column, '')`` column MultiIndex.
        """
        new_columns = pd.MultiIndex.from_product([df.columns, ['']])
        df.columns = new_columns
        return df


class Ferm(GeneralTable):
    """Processes fermentation / growth result tables exported from Benchling.

    Loads a fermentation assay CSV, optionally derives broth mass and sample density
    from weight-based columns, normalises sample labels, and aggregates replicate
    measurements per sample (mean and sample standard deviation). Output columns are
    grouped under the ``Ferm`` outer MultiIndex level.

    Args:
        zip_ref: Zipped file contents containing the fermentation table.
        file_name: Filename within the zip archive to load.

    Attributes:
        table: Raw fermentation or growth result table as read from Benchling.
    """
    def __init__(self, zip_ref: zipfile.ZipFile, file_name: str):
        super().__init__(zip_ref, file_name)

    def process(self) -> pd.DataFrame:
        """Aggregates fermentation metrics per sample into a MultiIndex-columned table.

        Validates required columns, optionally converts ``Weight (g)`` and
        ``DCW (g/kg)`` into ``Broth Mass (mg)``, sample density, and ``DCW g/L``,
        normalises ``Sample`` labels, then computes per-sample mean and standard
        deviation for insoluble solids, DCW, and sample density. Renames columns to
        standard output names and wraps them under the ``Ferm`` outer MultiIndex level.

        Returns:
            DataFrame indexed by normalised sample label with aggregated columns
            such as ``DCW (g/L)``, ``DCW_std (g/L)``, and ``% Insoluble Solids (g/g)``.

        Raises:
            EmptyTableError: If the table is empty after dropping all-NaN columns.
            ValueError: If the ``Sample`` column is missing.
        """
        # Sanity check
        df = self.table.copy().dropna(axis='columns', how='all')
        if df.empty:
            raise EmptyTableError('Ferm table is empty!')

        if 'Sample' not in df.columns:
            raise ValueError('Sample column is missing from the Ferm table.')
        df['Sample'] = normalize_sample_labels(df['Sample'])  # type: ignore

        # Check if the table is in the old format
        old_format_table: bool = df.columns.str.contains('Broth Mass').any() # type: ignore
        
        # Compute the necessary columns
        if old_format_table:
            df['Sample Density (g/ml)'] = df['Broth Mass (mg)'] / df['Sample Volume (uL)']
            
        else:
            df['Sample Density (g/ml)'] = df['Weight (g)'] * 1000 / df['Sample Volume (uL)']
            df['DCW g/L'] = df['DCW (g/kg)'] * df['Sample Density (g/ml)']

        # Rename the columns to the standard names
        df.rename(
            columns={
                '% Insoluble Solids': '% Insoluble Solids (g/g)',
                'DCW g/L': 'DCW (g/L)',
            },
            inplace=True,
            errors='ignore'
        )        

        # Aggegation functions for important columns
        agg_funcs = {
            '% Insoluble Solids (g/g)': ('% Insoluble Solids (g/g)', 'mean'),
            '% Insoluble Solids_std (g/g)': ('% Insoluble Solids (g/g)', 'std'),
            'DCW (g/L)': ('DCW (g/L)', 'mean'),
            'DCW_std (g/L)': ('DCW (g/L)', 'std'),
            'Sample Density (g/ml)': ('Sample Density (g/ml)', 'mean'),
            'Sample Density_std (g/ml)': ('Sample Density (g/ml)', 'std'),
        }
        proc_table: pd.DataFrame = df.groupby('Sample').agg(**agg_funcs  # type: ignore
                                                            ).reset_index().set_index('Sample')  # type: ignore

        return Ferm._group_cols(proc_table, Ferm.get_classname()) # type: ignore

    @staticmethod
    def _group_cols(df: pd.DataFrame, class_name: str) -> pd.DataFrame:
        """Wraps columns in a two-level MultiIndex with *class_name* as the outer level.

        Args:
            df: Processed table with single-level column names.
            class_name: Outer MultiIndex label (typically the panel class name).

        Returns:
            The same data with a ``(class_name, column)`` column MultiIndex.
        """
        new_columns = pd.MultiIndex.from_product([[class_name], df.columns])
        df.columns = new_columns
        return df


class Sugar(GeneralAnalyteTable):
    """Processes sugar analyte concentration tables exported from Benchling.

    Inherits :meth:`~biocanvas.utils.io.GeneralAnalyteTable.process`,
    which normalises sample labels, supports legacy and modern table layouts, and
    groups analyte columns under the ``Sugar`` outer MultiIndex level.

    Args:
        zip_ref: Zipped file contents containing the sugar panel CSV.
        file_name: Filename within the zip archive to load.

    Attributes:
        table: Raw sugar analyte table as read from Benchling.
    """


class Acids(GeneralAnalyteTable):
    """Processes organic acid analyte tables exported from Benchling.

    Inherits :meth:`~biocanvas.utils.io.GeneralAnalyteTable.process`
    and groups columns under the ``Acids`` outer MultiIndex level.

    Args:
        zip_ref: Zipped file contents containing the organic acids panel CSV.
        file_name: Filename within the zip archive to load.

    Attributes:
        table: Raw organic acids table as read from Benchling.
    """


class Ammonia(GeneralAnalyteTable):
    """Processes ammonia (NH4) analyte tables exported from Benchling.

    Inherits :meth:`~biocanvas.utils.io.GeneralAnalyteTable.process`
    and groups columns under the ``Ammonia`` outer MultiIndex level.

    Args:
        zip_ref: Zipped file contents containing the ammonia panel CSV.
        file_name: Filename within the zip archive to load.

    Attributes:
        table: Raw ammonia table as read from Benchling.
    """


class Phs(GeneralAnalyteTable):
    """Processes phosphate / sulfate analyte tables exported from Benchling.

    Inherits :meth:`~biocanvas.utils.io.GeneralAnalyteTable.process`
    and groups columns under the ``Phs`` outer MultiIndex level.

    Args:
        zip_ref: Zipped file contents containing the phosphate-sulfate panel CSV.
        file_name: Filename within the zip archive to load.

    Attributes:
        table: Raw phosphate / sulfate table as read from Benchling.
    """


class Lcuv(GeneralAnalyteTable):
    """Processes LC-UV analyte tables exported from Benchling.

    Inherits :meth:`~biocanvas.utils.io.GeneralAnalyteTable.process`
    and groups columns under the ``Lcuv`` outer MultiIndex level.

    Args:
        zip_ref: Zipped file contents containing the LC-UV panel CSV.
        file_name: Filename within the zip archive to load.

    Attributes:
        table: Raw LC-UV table as read from Benchling.
    """


class Brad(GeneralAnalyteTable):
    """Processes Bradford protein assay tables exported from Benchling.

    Runs the standard analyte pipeline via
    :meth:`~biocanvas.utils.io.GeneralAnalyteTable.process`, then
    renames ``Bradford Protein (g/L)`` to ``Total Protein (g/L)`` at the inner
    MultiIndex level.

    Args:
        zip_ref: Zipped file contents containing the Bradford panel CSV.
        file_name: Filename within the zip archive to load.

    Attributes:
        table: Raw Bradford assay table as read from Benchling.
    """
    def process(self) -> pd.DataFrame:
        """Processes the Bradford panel and standardises the protein column name.

        Returns:
            DataFrame indexed by normalised sample label with analyte columns under
            the ``Brad`` outer MultiIndex level and ``Total Protein (g/L)`` at the
            inner level (renamed from ``Bradford Protein (g/L)``).
        """
        return super().process().rename(
            columns={'Bradford Protein (g/L)': 'Total Protein (g/L)'}, level=1
        )  # type: ignore


class Biochem(GeneralAnalyteTable):
    """Processes biochemistry enzyme assay tables exported from Benchling.

    Runs the standard analyte pipeline via
    :meth:`~biocanvas.utils.io.GeneralAnalyteTable.process`, then
    maps legacy cellobiohydrolase and beta-glucosidase column names to the standard
    ``pnpC Activity (umoles/g/s)`` and ``pnpG Activity (umoles/g/s)`` labels at the
    inner MultiIndex level.

    Args:
        zip_ref: Zipped file contents containing the biochemistry panel CSV.
        file_name: Filename within the zip archive to load.

    Attributes:
        table: Raw biochemistry assays table as read from Benchling.
    """
    def process(self) -> pd.DataFrame:
        """Processes the biochemistry panel and normalises legacy enzyme column names.

        Returns:
            DataFrame indexed by normalised sample label with analyte columns under
            the ``Biochem`` outer MultiIndex level and standardised activity column
            names at the inner level.
        """
        return super().process().rename(
            columns={
                'Cellobiohydrolase Activity (umoles/g/s)': 'pnpC Activity (umoles/g/s)',
                'Cellobiohydrolase Activity (nmoles/mg)': 'pnpC Activity (umoles/g/s)',
                'pnpC Activity (nmoles/mg)': 'pnpC Activity (umoles/g/s)',
                'Beta-glucosidase Activity (nmoles/mg)': 'pnpG Activity (umoles/g/s)',
            },
            level=1
        )  # type: ignore
