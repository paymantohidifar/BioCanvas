# biocanvas/helix/meta.py
"""Class for reading and processing metadata table from Project Helix."""

from typing import List, Set, IO
import logging
import pandas as pd  # type: ignore
from biocanvas.utils import helpers

# Maps the leading letter of a tank ID to its bioreactor platform name
TANK_ID_TO_PLATFORM = {
    "S": "Seed",
    "M": "0.3L",
    "L": "2L",
    "X": "10L",
    "F": "40L",
    "A": "Flask",
    "B": "BioLector",
}

logger = logging.getLogger(__name__)


class Meta:
    """Metadata table for a fermentation experiment loaded from Project Helix.

    Args:
        file_content (IO[str]): Metadata CSV file content.
        exp_id (str): Fermentation experiment ID.

    Attributes:
        exp_id (str): Fermentation experiment ID.
        table (pd.DataFrame): Original metadata table.
        proc_table (pd.DataFrame): Processed and quality-checked metadata table.
    """

    def __init__(self, file_content: IO[str], exp_id: str):
        self.exp_id: str = exp_id
        self.table: pd.DataFrame = self._load_table(file_content)
        self.proc_table: pd.DataFrame = self._process()

    def _load_table(self, file_content: IO[str]) -> pd.DataFrame:
        """Reads the metadata CSV file content into a DataFrame.

        Args:
            file_content (IO[str]): Metadata CSV file content.

        Returns:
            pd.DataFrame: Original metadata table.
        """
        return pd.read_csv(file_content)  # type: ignore

    def _process(self) -> pd.DataFrame:
        """QC-checks, then derives Platform and Strain columns and standardises source labels.

        Returns:
            pd.DataFrame: Processed metadata table.
        """
        logger.info("Processing metadata for Exp '%s'", self.exp_id)
        proc_table = self._qc_check()

        proc_table["Platform"] = proc_table["Tank"].str[0].map(TANK_ID_TO_PLATFORM)  # type: ignore
        proc_table["Strain"] = proc_table["Strain Batch"].str.split("-").str[0].str[3:]  # type: ignore

        proc_table.insert(0, "Exp", self.exp_id)  # type: ignore
        proc_table.insert(2, "Platform", proc_table.pop("Platform"))  # type: ignore
        proc_table.insert(7, "Strain", proc_table.pop("Strain"))  # type: ignore

        # Remove the trailing version suffix (last hyphen-segment) from source labels
        for col in ["Media", "Feed Source", "Co-feed Source", "Bolus Source"]:
            proc_table[col] = proc_table[col].str.rsplit("-", n=1).str[0]  # type: ignore

        return proc_table

    def _qc_check(self) -> pd.DataFrame:
        """Quality-checks the metadata table and drops rows that fail.

        Checks that all essential columns are populated and that manual feed
        time profiles and target rates have matching segment counts. QC failures
        are emitted as warnings via the module logger.

        Returns:
            pd.DataFrame: Quality-checked table with missing cells filled as 'NA'.

        Raises:
            helpers.EmptyTableError: If no rows survive the quality check.
        """
        essential_cols: List[str] = [
            "Tank",
            "Condition",
            "Replicate",
            "Strain Batch",
            "EFT (h)",
            "Media",
            "Initial Broth Vol (ml)",
            "pH Setpoint",
            "Temp (°C) Setpoint",
            "DO (%) Setpoint",
        ]
        drop_tanks_set: Set[int] = set()

        # Flag rows missing any essential value
        bad_essential = self.table[essential_cols].isna().any(axis=1)  # type: ignore
        for idx in self.table.index[bad_essential]:  # type: ignore
            logger.warning(
                "Exp '%s': metadata for tank '%s' is missing values in essential columns; dropping from analysis.",
                self.exp_id,
                self.table.at[idx, "Tank"],  # type: ignore
            )
        drop_tanks_set.update(self.table.index[bad_essential])  # type: ignore

        # Flag rows whose manual feed profiles have mismatched segment counts
        for feed_type in ["Feed", "Co-feed", "Bolus", "Acid", "Base"]:
            has_source = pd.notna(self.table[f"{feed_type} Source"])  # type: ignore
            not_eve_pi = self.table[f"Eve/Pi Controlled {feed_type}"] == "No"  # type: ignore
            time_segs = (
                self.table[f"Manual {feed_type} Time Profile (h)"]
                .astype(str)
                .str.count(";")
            )  # type: ignore
            rate_segs = (
                self.table[f"Manual Target {feed_type} Rate (ml/h)"]
                .astype(str)
                .str.count(";")
            )  # type: ignore
            bad_feed = has_source & not_eve_pi & (time_segs != rate_segs)  # type: ignore
            for idx in self.table.index[bad_feed]:  # type: ignore
                logger.warning(
                    "Exp '%s': metadata for tank '%s' has wrong format in 'Manual %s Time Profile (h)' "
                    "and/or 'Manual Target %s Rate (ml/h)'; dropping from analysis.",
                    self.exp_id,
                    self.table.at[idx, "Tank"],
                    feed_type,
                    feed_type,  # type: ignore
                )
            drop_tanks_set.update(self.table.index[bad_feed])  # type: ignore

        qced_table = self.table.drop(index=list(drop_tanks_set)).fillna("NA")  # type: ignore
        if not qced_table.empty:
            return qced_table
        else:
            raise helpers.EmptyTableError(
                "Processed metadata table is empty. Skipping analysis of the whole experiment!"
            )

    def get_num_tanks(self):
        """Counts seed and fermentation tanks in the processed table.

        Returns:
            tuple[int, int]: Number of seed tanks and fermentation tanks.
        """
        seed_mask = self.proc_table["Tank"].apply(helpers.is_seed_tank)  # type: ignore
        seed_tanks = int(seed_mask.sum())  # type: ignore
        ferm_tanks = int((~seed_mask).sum())  # type: ignore
        return seed_tanks, ferm_tanks

    def is_empty(self):
        """Checks whether the processed metadata table is empty.

        Returns:
            bool: True if the processed table is empty, False otherwise.
        """
        return self.proc_table.empty

    @classmethod
    def get_classname(cls):
        """Returns the class name.

        Returns:
            str: Name of the class.
        """
        return cls.__name__
