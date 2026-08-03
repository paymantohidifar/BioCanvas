# biocanvas/data_service.py
"""Pure data-pipeline service for the biocanvas App.

DataService owns all state and logic that is independent of ipywidgets:
local SQLite-backed drive connectivity, project-module loading, file
parsing, master-table construction, and plot-property filtering.  The App
view layer instantiates one DataService and delegates every data operation
to it.
"""
import io
import gc
import copy
import logging
from datetime import datetime
from pathlib import Path
from zipfile import ZipFile
from typing import Any, Dict, Iterable, List, Optional, Tuple
import numpy as np
import pandas as pd

from biocanvas.utils import auth, helpers, logging_config, io as utils_io

logger = logging.getLogger(__name__)


class DataService:
    """Encapsulates all data-pipeline logic for the biocanvas application.

    Owns local SQLite-backed drive connectivity, project-module loading,
    raw-file parsing, master-table construction, and plot-property
    filtering.  Contains no ipywidgets dependency.

    Class attributes:
        PROJECT_LIST: Mapping of project name → PBKDF2 passcode hash, loaded
            once from passcodes.json.
    """

    _PASSCODES_PATH: Path = Path(__file__).parent / 'passcodes.json'
    PROJECT_LIST: Dict[str, str] = auth.load_passcode_hashes(str(_PASSCODES_PATH))

    def __init__(self) -> None:
        """Initialises all data-state fields to their empty defaults."""

        # Dynamic project subpackage modules
        self.subpackage_path: str = ""
        self.config_module: Optional[object] = None
        self.meta_module: Optional[object] = None
        self.benchling_module: Optional[object] = None
        self.ferm_process_module: Optional[object] = None

        # Output directory paths (populated by setup_project_dirs)
        self.root_dir: str = ""
        self.logs_dir: str = ""
        self.results_dir: str = ""
        self.tabs_dir: str = ""
        self.figs_dir: str = ""

        # Local SQLite-backed drive client
        self.local_client = utils_io.LocalDataClient()

        # Master data tables
        self.master_meta_table: pd.DataFrame = pd.DataFrame()
        self.master_bench_table: pd.DataFrame = pd.DataFrame()
        self.master_process_table: pd.DataFrame = pd.DataFrame()

        # KPI plot-property dicts (deep-copied from config on project load)
        self.bench_plot_properties: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self.process_plot_properties: Dict[str, Dict[str, Dict[str, Any]]] = {}

        # Running count used to name saved figure files
        self.save_fig_call_count: int = 0

    # ------------------------------------------------------------------
    # Directory and logging setup
    # ------------------------------------------------------------------

    def setup_project_dirs(self, project_name: str, log_level: int) -> None:
        """Creates the output directory tree for the selected project.

        Args:
            project_name: Name of the selected project (used as root dir prefix).
            log_level: Logging level integer (e.g. ``logging.DEBUG``) to apply
                when configuring file handlers.
        """
        self.root_dir = f"{project_name}_output_{datetime.now().date()}"
        self.logs_dir = f"{self.root_dir}/logs"
        self.results_dir = f"{self.root_dir}/results"
        self.tabs_dir = f"{self.results_dir}/processed_tables"
        self.figs_dir = f"{self.results_dir}/plots"
        logger.debug("Setting up output directories under '%s'", self.root_dir)
        utils_io.setup_output_dirs([
            self.root_dir,
            self.logs_dir,
            self.results_dir,
            self.tabs_dir,
            self.figs_dir,
        ])
        logging_config.setup_logging(
            log_level=log_level,
            log_file=self.logs_dir + "/biocanvas_debug.log",
            console=False,
            file_only_package="biocanvas",
        )
        logging_config.setup_logging(
            log_file=self.logs_dir + "/meta_qc.log",
            console=False,
            reset_handlers=False,
            update_root_level=False,
            file_only_package=f"biocanvas.{project_name}.meta",
        )
        logger.info("Output directories created under '%s'", self.root_dir)

    # ------------------------------------------------------------------
    # Project-module loading
    # ------------------------------------------------------------------

    def load_project_modules(self, project_name: str) -> Tuple[bool, List[helpers.LogEntry]]:
        """Loads meta, benchling, ferm_process, and config modules for the project.

        Also deep-copies the plot-property dicts from the config module.

        Args:
            project_name: Name of the selected project subpackage.

        Returns:
            ``(success, log_entries)`` — ``success`` is ``False`` on any
            ``ImportError``; the caller must not access ``config_module`` when
            ``False``.
        """
        log_entries: List[helpers.LogEntry] = []
        subpackage_path = f"biocanvas.{project_name}"
        try:
            logger.debug("Loading project modules from '%s'", subpackage_path)
            self.meta_module = utils_io.load_module(f"{subpackage_path}.meta")
            self.benchling_module = utils_io.load_module(f"{subpackage_path}.benchling")
            self.ferm_process_module = utils_io.load_module(f"{subpackage_path}.ferm_process")
            self.config_module = utils_io.load_module(f"{subpackage_path}.config")
            self.bench_plot_properties = copy.deepcopy(
                self.config_module.bench_plot_properties  # type: ignore
            )
            self.process_plot_properties = copy.deepcopy(
                self.config_module.process_plot_properties  # type: ignore
            )
            log_entries.append(
                (f"Project '{project_name}' loaded successfully. Happy analysis!", 'success')
            )
            logger.info("All project modules loaded for '%s'", project_name)
            return True, log_entries
        except ImportError as e:
            log_entries.append(
                (f"Could not import one or more modules from '{project_name}' (see logs for details)", 'error')
            )
            logger.error("ImportError loading project '%s': %s", project_name, e, exc_info=True)
            return False, log_entries

    # ------------------------------------------------------------------
    # Local SQLite-backed drive connectivity
    # ------------------------------------------------------------------

    def fetch_experiment_names(self) -> Tuple[List[str], List[helpers.LogEntry]]:
        """Connects to the project's local SQLite database and returns experiment directory names.

        Must only be called after :meth:`load_project_modules` succeeds.

        Returns:
            ``(exp_names, log_entries)`` — ``exp_names`` is empty if the
            connection fails or no experiments are found.
        """
        log_entries: List[helpers.LogEntry] = []
        try:
            logger.debug(
                "Connecting to local database for project '%s'",
                self.config_module.PROJECT_NAME,  # type: ignore
            )
            self.local_client.connect(
                self.config_module.PROJECT_NAME,  # type: ignore
                self.config_module.SHAREPOINT_DATA_DIR,  # type: ignore
            )
            items = self.local_client.get_item_names()
            exp_names = [item for item in items if item.lower().startswith('exp')]
            logger.info("Found %d experiment(s) in the local database", len(exp_names))
            if not exp_names:
                log_entries.append(("No experiments found in the project directory.", 'warning'))
            return exp_names, log_entries
        except Exception as e:
            log_entries.append(("Error connecting to the local database (see logs for details)", 'error'))
            logger.error("Local database connection failed: %s", e, exc_info=True)
            return [], log_entries

    # ------------------------------------------------------------------
    # Experiment processing
    # ------------------------------------------------------------------

    @helpers.profile_method
    def process_single_experiment(
        self, exp_name: str
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, List[helpers.LogEntry]]:
        """Loads and processes all data files for one experiment from the local database.

        Contains no widget reads or writes; safe to call from any context.

        Args:
            exp_name: The experiment directory name (e.g. ``"Exp 001 MyRun"``).

        Returns:
            ``(meta_df, bench_df, process_df, log_entries)``.  On fatal failure
            all three DataFrames are empty.
        """
        log_entries: List[helpers.LogEntry] = [(exp_name, 'header')]

        try:
            # --- Meta.csv ---
            meta_file_loaded = self.local_client.load_data(exp_name + '/Meta.csv')
            logger.info("Loaded Meta.csv for '%s'", exp_name)
            meta_table, meta_msgs = self._process_meta_file(
                io.StringIO(meta_file_loaded.decode('utf-8')), exp_name
            )
            for msg in meta_msgs:
                log_entries.append((msg, 'success' if not meta_table.empty else 'warning'))
            if meta_table.empty:
                raise helpers.EmptyTableError('Meta table is empty — skipping experiment.')

            # --- Benchling.zip ---
            try:
                bench_zip_loaded = self.local_client.load_data(exp_name + '/Benchling.zip')
                logger.info("Loaded Benchling.zip for '%s'", exp_name)
                consolidated_bench_table, bench_msgs = self._process_benchling_files(
                    io.BytesIO(bench_zip_loaded), meta_table
                )
                for msg in bench_msgs:
                    log_entries.append((msg, logging_config.classify_msg_level(msg)))
            except FileNotFoundError:
                consolidated_bench_table = pd.DataFrame()
                log_entries.append(
                    ("Benchling zip file is not available. Skipping Benchling data!", 'warning')
                )
                logger.warning("Benchling.zip not found for '%s'", exp_name)
            except Exception as e:
                consolidated_bench_table = pd.DataFrame()
                log_entries.append(
                    (f"Error processing Benchling zipped file. (see logs for details). Skipping Benchling data!", 'error'))
                logger.error("Failed to process Benchling.zip: %s", e, exc_info=True)

            # --- Eve.zip / Pi.zip (try known filenames before directory listing) ---
            try:
                process_file: Optional[str] = None
                process_panel: Optional[str] = None
                process_zip_loaded: Optional[bytes] = None
                for candidate, panel in utils_io.resolve_process_zip_candidates():
                    try:
                        process_zip_loaded = self.local_client.load_data(exp_name + f'/{candidate}')
                        process_file = candidate
                        process_panel = panel
                        break
                    except FileNotFoundError:
                        pass
                if process_file is None or process_panel is None or process_zip_loaded is None:
                    filenames = self.local_client.get_item_names(exp_name + '/')
                    process_file, process_panel = utils_io.detect_process_file_type(filenames)
                    process_zip_loaded = self.local_client.load_data(exp_name + f'/{process_file}')
                logger.info("Loaded %s for '%s'", process_file, exp_name)
                consolidated_process_table, process_msgs = self._process_ferm_process_panels(
                    io.BytesIO(process_zip_loaded), meta_table, process_panel
                )
                for msg in process_msgs:
                    log_entries.append((msg, logging_config.classify_msg_level(msg)))
            except FileNotFoundError:
                consolidated_process_table = pd.DataFrame()
                log_entries.append((
                    "Eve/Pi zip file is not available. Skipping Eve/Pi data and "
                    "creating a mock Eve/Pi table!",
                    'warning',
                ))
                logger.warning("Eve/Pi zip not found for '%s'", exp_name)
            except Exception as e:
                consolidated_process_table = pd.DataFrame()
                log_entries.append((
                    f"Error processing Eve/Pi zipped file from '{exp_name}' (see logs for details)."
                    "Skipping Eve/Pi data!",
                    'error',
                ))
                logger.error(
                    "Failed to process Eve/Pi zip for '%s': %s", exp_name, e, exc_info=True
                )

            # --- Augment tables and calculate Titer, Rate, and Yield (TRY) KPIs ---
            augmented_tables = AugmentTables(
                meta_table,
                consolidated_bench_table,
                consolidated_process_table,
            )
            augmented_tables.augment(
                self.config_module.CARBON_PANELS,  # type: ignore
                self.config_module.PANELS_FOR_TRY,  # type: ignore
                self.config_module.FINAL_BENCHLING_COLS,  # type: ignore
                self.config_module.FINAL_PROCESS_COLS,  # type: ignore
                self.config_module.PANEL_DISPLAY_NAMES,  # type: ignore
            )
            for msg in augmented_tables.output_messages:
                log_entries.append((msg, logging_config.classify_msg_level(msg)))
            log_entries.append(('', 'separator'))

            logger.info("Successfully processed experiment '%s'", exp_name)
            return (
                augmented_tables.augmented_meta_table,
                augmented_tables.augmented_bench_table,
                augmented_tables.augmented_process_table,
                log_entries,
            )

        except (FileNotFoundError, helpers.EmptyTableError) as e:
            log_entries.append(
                ("Meta file unavailable or empty — skipping experiment (see logs for details).", 'error')
            )
            log_entries.append(('', 'separator'))
            logger.warning("Skipping experiment '%s': %s", exp_name, e)
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), log_entries
        except Exception as e:
            log_entries.append(
                ("Unexpected error processing Meta file — skipping experiment (see logs for details).", 'error')
            )
            log_entries.append(('', 'separator'))
            logger.error(
                "Unexpected error for experiment '%s': %s", exp_name, e, exc_info=True
            )
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), log_entries

    def build_master_tables(
        self,
        exp_names: Iterable[str],
    ) -> List[helpers.LogEntry]:
        """Processes all experiments and assembles the master DataFrames.

        Iterates ``exp_names``, calling :meth:`process_single_experiment` for
        each, concatenates the per-experiment results into ``master_meta_table``,
        ``master_bench_table``, and ``master_process_table``, and returns all
        collected log entries in document order.

        Args:
            exp_names: Experiment directory names to process (may be a plain
                list or a view-layer iterable such as ``tqdm`` wrapping a list).

        Returns:
            Flat list of :data:`utils.LogEntry` tuples covering every experiment
            plus a final completion header entry.

        Notes:
            Uses sequential processing; see :meth:`process_single_experiment`
            for the rationale against parallelism.
        """
        all_entries: List[helpers.LogEntry] = []
        exp_meta_li: List[pd.DataFrame] = []
        exp_bench_li: List[pd.DataFrame] = []
        exp_process_li: List[pd.DataFrame] = []

        if hasattr(exp_names, "__len__"):
            logger.debug(
                "Starting sequential processing for %d experiment(s)",
                len(exp_names),  # type: ignore[arg-type]
            )
        else:
            logger.debug("Starting sequential processing")

        for exp_name in exp_names:
            meta_df, bench_df, process_df, log_entries = self.process_single_experiment(
                exp_name
            )
            all_entries.extend(log_entries)
            if not meta_df.empty:
                exp_meta_li.append(meta_df)
                exp_bench_li.append(bench_df)
                exp_process_li.append(process_df)
            del meta_df, bench_df, process_df, log_entries

        all_entries.append(("Sequential processing complete", 'header'))
        logger.debug("Sequential processing complete")

        # Concatenate per-experiment tables into master DataFrames
        if exp_meta_li:
            self.master_meta_table = pd.concat(
                exp_meta_li, axis='index', ignore_index=True
            )
            self.master_meta_table.set_index(['Exp', 'Tank'], drop=True, inplace=True)  # type: ignore
            self.master_meta_table['Run'] = [
                f'{idx[0]}-{idx[1]}' for idx in self.master_meta_table.index.values # type: ignore
            ]
        if exp_bench_li:
            self.master_bench_table = pd.concat(
                exp_bench_li, axis='index', ignore_index=True
            )
        if exp_process_li:
            self.master_process_table = pd.concat(
                exp_process_li, axis='index', ignore_index=True
            )
        
        # Free up memory
        del exp_meta_li, exp_bench_li, exp_process_li
        gc.collect()
        
        return all_entries

    def save_master_tables(self, save: bool) -> bool:
        """Saves master tables to CSV if *save* is ``True``.

        Args:
            save: When ``True`` writes three CSV files to ``_tabs_dir``.

        Returns:
            ``True`` when files were written, ``False`` otherwise.
        """
        if not save:
            return False

        meta_path = f'{self.tabs_dir}/master_meta_table.csv'
        self.master_meta_table.to_csv(meta_path) # type: ignore
        logger.info("Saved master meta table to '%s'", meta_path)

        bench_path = f'{self.tabs_dir}/master_bench_table.csv'
        helpers.flatten_multiindex_columns(self.master_bench_table.round(3)).to_csv( # type: ignore
            bench_path, index=False
        )
        logger.info("Saved master benchling table to '%s'", bench_path)

        process_path = f'{self.tabs_dir}/master_process_table.csv'
        helpers.flatten_multiindex_columns(self.master_process_table.round(3)).to_csv( # type: ignore
            process_path, index=False
        )
        logger.info("Saved master process table to '%s'", process_path)
        return True

    # ------------------------------------------------------------------
    # Private file-parsing helpers
    # ------------------------------------------------------------------

    def _process_meta_file(
        self, file_content: io.StringIO, exp_title: str
    ) -> Tuple[pd.DataFrame, List[str]]:
        """Processes a raw Meta CSV stream into a validated metadata DataFrame.

        Args:
            file_content: In-memory text stream of the Meta.csv file.
            exp_title: Full experiment title (e.g. ``"Exp 001 MyRun"``); the
                experiment ID is the second whitespace-delimited token.

        Returns:
            ``(processed_table, output_messages)`` — ``processed_table`` is
            empty if processing failed.
        """
        exp_id = exp_title.split(' ')[1]
        MetaClass = getattr(self.meta_module, 'Meta')
        meta = MetaClass(file_content, exp_id)
        processed_table = meta.proc_table
        num_seed_tanks, num_ferm_tanks = meta.get_num_tanks()

        if not processed_table.empty:
            output_messages = [
                f"Successfully processed metadata for {num_ferm_tanks} ferm tanks and "
                f"{num_seed_tanks} seed tanks out of total "
                f"{num_seed_tanks + num_ferm_tanks} tanks."
            ]
        else:
            output_messages = ["Processing meta file was not successful."]

        return processed_table, output_messages

    def _process_benchling_files(
        self, file_content: io.BytesIO, meta_table: pd.DataFrame
    ) -> Tuple[pd.DataFrame, List[str]]:
        """Processes a Benchling zip archive into one horizontally merged table.

        Each archive member is mapped to a panel class via the filename stem
        (e.g. ``exp.Sample.csv`` → ``Sample``). Unrecognized panels, empty
        results, and per-file failures are skipped with messages appended to
        ``output_messages``; processing continues for remaining files.

        Successful panels are concatenated on columns (shared sample index).
        The outer MultiIndex level is renamed when
        ``config_module.PANEL_DISPLAY_NAMES`` maps the class name to a display
        label. Rows are then restricted to tanks listed in *meta_table*,
        sorted by ``Tank`` and ``Time (h)``, and the sample index is reset to a
        column.

        Args:
            file_content: In-memory binary stream of the Benchling.zip archive.
            meta_table: Processed metadata table; its ``Tank`` column defines
                which rows are kept in the consolidated output.

        Returns:
            Tuple of ``(consolidated_table, output_messages)``.

            * ``consolidated_table`` — Merged panel data with MultiIndex
              columns, or an empty DataFrame when the essential ``Sample``
              panel could not be processed, when no panels succeeded, or when
              consolidation would yield no rows after tank filtering.
            * ``output_messages`` — Human-readable status lines for each panel
              (recognized, skipped, succeeded, or failed).
        """
        bench_table_li: List[pd.DataFrame] = []
        processed_panel_names: List[str] = []
        skipped_panel_names: List[str] = []
        output_messages: List[str] = []

        # Get the passed tanks from the metadata table
        passed_tanks: List[str] = meta_table['Tank'].tolist()  # type: ignore

        with ZipFile(file_content) as zip_ref:
            # Get the sorted filenames from the zip archive
            file_names = zip_ref.namelist()
            
            # Process each file
            for file_name in file_names:
                try:
                    # Get the panel name from the file name
                    panel_name = file_name.split('.')[-2].capitalize()    
                    # Skip processing if the panel name is not in the list of accepted panel names
                    if panel_name not in self.config_module.PANEL_DISPLAY_NAMES:  # type: ignore
                        skipped_panel_names.append(panel_name)
                        output_messages.append(f"Did not recognize {panel_name} Benchling panel name.")
                        logger.warning("Did not recognize %s Benchling panel name.", panel_name)
                        continue
                    
                    # Process the panel
                    BenchlingPanel = getattr(self.benchling_module, panel_name)
                    processed_table = BenchlingPanel(zip_ref, file_name).process()
                    if processed_table.empty:
                        skipped_panel_names.append(panel_name)
                        output_messages.append(f"Processed {panel_name} Benchling panel is empty.")
                        logger.warning("Processed %s Benchling panel is empty.", panel_name)
                        continue

                    display_name = self.config_module.PANEL_DISPLAY_NAMES.get(  # type: ignore
                        panel_name, panel_name
                    )
                    if display_name != panel_name:
                        processed_table.columns = (
                            processed_table.columns.set_levels([display_name], level=0)
                        )
                    
                    processed_panel_names.append(panel_name)
                    bench_table_li.append(processed_table)
                    output_messages.append(
                        f"Successfully processed '{panel_name}' "
                        f"Benchling panel with "
                        f"{processed_table.shape[0]} samples."
                    )
                    logger.info(
                        "Processed '%s' Benchling panel with %s samples.",
                        panel_name, processed_table.shape[0],
                    )
                except Exception as e:
                    output_messages.append(f"Processing failed for {panel_name}: {e}. Skipping this panel!") # type: ignore
                    logger.warning("Processing failed for %s: %s. Skipping this panel!", panel_name, e) # type: ignore

        # Log the skipped and processed panels
        logger.info(f"Skipped Benchling panels: {skipped_panel_names}")
        logger.info(f"Processed Benchling panels: {processed_panel_names}")

        # Abort if the Sample panel was skipped because it holds essential information for the analysis
        if 'Sample' in skipped_panel_names:
            logger.warning("Essential Sample could not be processed! Cannot continue.")
            output_messages.append("Essential Sample could not be processed! Cannot continue.")
            return pd.DataFrame(), output_messages

        if len(processed_panel_names) == 0:
            logger.warning("Could not consolidate any Benchling panels. Returning an empty dataframe.")
            output_messages.append("Could not consolidate any Benchling panels. Returning an empty dataframe.")
            return pd.DataFrame(), output_messages

        # Combine all processed tables into a single DataFrame and filter to only include the passed tanks
        consolidated_table = pd.concat(bench_table_li, axis='columns')
        consolidated_table = consolidated_table[ # type: ignore
            consolidated_table['Tank'].isin(passed_tanks) # type: ignore
        ].sort_values(by=['Tank', 'Time (h)'])        
        
        # Clean up the memory
        del bench_table_li
        gc.collect()
        return consolidated_table.reset_index(), output_messages # type: ignore

    def _process_ferm_process_panels(
        self,
        file_content: io.BytesIO,
        meta_table: pd.DataFrame,
        process_panel: str,
    ) -> Tuple[pd.DataFrame, List[str]]:
        """Processes an Eve or Pi zip archive into one vertically stacked table.

        Archive members are sorted by numeric tank id in the filename stem
        (e.g. ``exp.1.csv`` → tank ``1``). Only fermentation tanks from
        *meta_table* are considered (seed tanks whose id starts with ``s`` are
        excluded). Each matching file is passed to the panel class named by
        *process_panel*; unrecognized tanks, empty results, and per-file
        failures are recorded in ``output_messages`` and the tank is skipped.

        Per-tank failures are logged and skipped. When at least one tank succeeds,
        successful per-tank tables are concatenated along the row axis. An empty
        DataFrame is returned only when no tank was processed successfully.

        Args:
            file_content: In-memory binary stream of the Eve.zip or Pi.zip
                archive.
            meta_table: Processed metadata table used to build the set of
                fermentation tank labels (e.g. ``M1``, ``M2``).
            process_panel: ``ferm_process`` class name to instantiate, typically
                ``'EveTable'`` or ``'PiTable'``.

        Returns:
            Tuple of ``(consolidated_table, output_messages)``.

            * ``consolidated_table`` — Stacked process time-series for all
              successfully processed tanks, or an empty DataFrame when no tank
              files were processed successfully.
            * ``output_messages`` — Human-readable status lines for each tank
              (recognized, skipped, succeeded, or failed).
        """
        process_table_li: List[pd.DataFrame] = []
        skipped_tanks: List[str] = []
        processed_tanks: List[str] = []
        output_messages: List[str] = []

        # Get the passed tanks from the metadata table
        passed_tanks: Dict[int, str] = {
            int(tank[1:]): tank # type: ignore
            for tank in meta_table['Tank'].values  # type: ignore
            if not tank.lower().startswith('s') # type: ignore
        }

        # Get the process panel class
        ProcessPanel = getattr(self.ferm_process_module, process_panel)

        with ZipFile(file_content) as zip_ref:
            
            # Get the sorted filenames from the zip archive and sort by tank number
            filenames = sorted(
                zip_ref.namelist(), key=lambda el: int(el.split('.')[-2])
            )

            # Process each tank
            for filename in filenames:
                try:
                    tank_num = int(filename.split('.')[-2])
                    logger.info(f"Processing Eve/Pi file: {filename}, tank number: {tank_num}")

                    # Skip processing if the tank number is not in the list of passed tanks
                    if tank_num not in passed_tanks.keys():
                        output_messages.append(f"Tank {tank_num} is not in metadata.")
                        logger.debug("Tank %s is not in metadata.", tank_num)
                        continue

                    # Process the tank
                    proc_table = ProcessPanel(zip_ref, filename, passed_tanks[tank_num]).process()
                    if proc_table.empty:
                        skipped_tanks.append(str(tank_num))
                        output_messages.append(f"Processed tank {tank_num} is empty.")
                        logger.warning("Processed tank %s is empty!", tank_num)
                        continue  
                    processed_tanks.append(str(tank_num))
                    process_table_li.append(proc_table)
                    output_messages.append(
                        f"Successfully processed Eve/Pi data for tank "
                        f"{passed_tanks[tank_num]}."
                    )
                    logger.info(
                        "Processed Eve/Pi data for tank %s.",
                        passed_tanks[tank_num],
                    )
                except Exception as e:
                    skipped_tanks.append(str(tank_num)) # type: ignore
                    output_messages.append(f"Processing failed for tank {tank_num}: {e}. Skipping this tank.") # type: ignore
                    logger.warning("Processing failed for tank %s: %s. Skipping this tank!", tank_num, e) # type: ignore

        logger.info("Skipped Eve/Pi tanks: %s.", skipped_tanks)
        logger.info("Processed Eve/Pi tanks: %s.", processed_tanks)

        if len(processed_tanks) == 0:
            logger.warning("No Eve/Pi tanks processed successfully. Returning an empty dataframe.")
            output_messages.append("No Eve/Pi tanks processed successfully. Returning an empty dataframe.") # type: ignore
            return pd.DataFrame(), output_messages

        result = pd.concat(process_table_li, axis='index', ignore_index=True)
        logger.info(
            "Consolidated %s Eve/Pi tables, %s samples.",
            len(process_table_li), result.shape[0],
        )
        # Clean up the memory
        del process_table_li
        gc.collect()
        return result, output_messages

    # ------------------------------------------------------------------
    # Plot-property filtering helpers
    # ------------------------------------------------------------------

    def get_selected_exp_tank(
        self, filter_keys: Dict[str, Tuple[str, str]]
    ) -> List[Any]:
        """Returns ``(Exp, Tank)`` index pairs matching *filter_keys*.

        Args:
            filter_keys: Mapping of column name → ``(operator, value)`` tuple
                used to build a pandas query string.  Pass an empty dict to
                return all pairs.

        Returns:
            List of ``(Exp, Tank)`` MultiIndex tuples.
        """
        if filter_keys:
            query_str = ' & '.join(
                [f'`{k}` {v[0]} {v[1]}' for k, v in filter_keys.items()]
            )
            return list(self.master_meta_table.query(query_str).index)  # type: ignore
        return list(self.master_meta_table.index)  # type: ignore

    @staticmethod
    def _filter_master_table_by_exp_tank(
        master_table: pd.DataFrame,
        selected_exp_tank: List[Any],
    ) -> pd.DataFrame:
        """Returns rows of *master_table* whose (Exp, Tank) pair is in *selected_exp_tank*."""
        if master_table.empty or not selected_exp_tank:
            return pd.DataFrame()
        exp_col = ('Exp', '')
        tank_col = ('Tank', '')
        keys = pd.MultiIndex.from_tuples(selected_exp_tank, names=['Exp', 'Tank'])
        row_keys = pd.MultiIndex.from_arrays([ # type: ignore
            master_table[exp_col].values, # type: ignore
            master_table[tank_col].values, # type: ignore
        ])
        return master_table.loc[row_keys.isin(keys)].dropna(axis='columns', how='all')  # type: ignore

    @staticmethod
    def _refresh_col_exist(
        plot_properties: Dict[str, Dict[str, Dict[str, Any]]],
        filtered_columns: pd.Index,
    ) -> None:
        """Updates ``col_exist`` flags from the set of columns present in a filtered table."""
        col_set = set(filtered_columns)
        for panel, kpis in plot_properties.items():
            for _, content in kpis.items():
                content['col_exist'] = [
                    1 if (panel, col) in col_set else 0 for col in content['cols']
                ]

    @helpers.profile_method
    def update_bench_plot_properties(
        self, filter_keys: Optional[Dict[str, Tuple[str, str]]] = None
    ) -> pd.DataFrame:
        """Filters ``master_bench_table`` and refreshes ``bench_plot_properties``.

        Args:
            filter_keys: Mapping of column → ``(operator, value)`` tuples.
                Pass ``None`` to select all experiments and tanks.

        Returns:
            Filtered benchling DataFrame with all-NaN columns dropped, or an
            empty DataFrame when the master table is empty or no tanks match.
        """
        if filter_keys is None:
            filter_keys = {}
        selected_exp_tank: List[Any] = self.get_selected_exp_tank(filter_keys)

        filtered_bench_table = pd.DataFrame()
        if (not self.master_bench_table.empty) and len(selected_exp_tank) > 0:
            filtered_bench_table = self._filter_master_table_by_exp_tank(
                self.master_bench_table, selected_exp_tank  # type: ignore
            )
            self._refresh_col_exist(self.bench_plot_properties, filtered_bench_table.columns)

        return filtered_bench_table

    @helpers.profile_method
    def update_process_plot_properties(
        self, filter_keys: Optional[Dict[str, Tuple[str, str]]] = None
    ) -> pd.DataFrame:
        """Filters ``master_process_table`` and refreshes ``process_plot_properties``.

        Args:
            filter_keys: Mapping of column → ``(operator, value)`` tuples.
                Pass ``None`` to select all experiments and tanks.

        Returns:
            Filtered process DataFrame with all-NaN columns dropped, or an
            empty DataFrame when the master table is empty or no tanks match.
        """
        if filter_keys is None:
            filter_keys = {}
        filtered_process_table = pd.DataFrame()

        selected_exp_tank: List[Any] = self.get_selected_exp_tank(filter_keys)

        if (not self.master_process_table.empty) and len(selected_exp_tank) > 0:
            filtered_process_table = self._filter_master_table_by_exp_tank(
                self.master_process_table, selected_exp_tank  # type: ignore
            )
            self._refresh_col_exist(self.process_plot_properties, filtered_process_table.columns)  # type: ignore

        return filtered_process_table


class AugmentTables:
    """Augments meta, bench, and process tables with derived columns and TRY KPIs.

    Stores deep copies of the three input tables on construction, then exposes an
    :meth:`augment` method that runs all derivation steps in order.  Results are
    stored in-place and read back via the public table attributes.  Status and
    error messages for each step are collected in :attr:`output_messages`.

    Args:
        meta: Pre-processed metadata table (one row per tank).
        bench: Pre-processed, consolidated Benchling result table.
        process: Pre-processed process (Eve/Pi) data table.

    Attributes:
        augmented_meta_table: Metadata table after augmentation (currently unchanged).
        augmented_bench_table: Benchling table with TRY KPI columns added and
            restricted to the caller-specified column list.
        augmented_process_table: Process table with derived feeding, volume, and
            mass-balance columns added, wrapped in a ``('Process', col)`` MultiIndex.
        output_messages: Human-readable status or error messages produced by each
            augmentation step, in order of execution.
    """
    def __init__(
        self,
        meta: pd.DataFrame,
        bench: pd.DataFrame,
        process: pd.DataFrame,
    ):
        self.augmented_meta_table: pd.DataFrame = meta.copy(deep=True)
        self.augmented_bench_table: pd.DataFrame = bench.copy(deep=False)
        self.augmented_process_table: pd.DataFrame = process.copy(deep=False)
        self._meta_by_tank: pd.DataFrame = meta.set_index('Tank') # type: ignore
        self.output_messages: List[str] = []

    @helpers.profile_method
    def augment(
        self,
        carbon_panels: Dict[str, List[str]],
        panels_for_try: Dict[str, List[str]],
        bench_cols_to_keep: List[str],
        process_cols_to_keep: List[str],
        panel_display_names: Dict[str, str],
    ) -> None:
        """Run all augmentation steps in order and restrict tables to the requested columns.

        Executes four steps:
        1. Meta augmentation (placeholder — no derived columns yet).
        2. Process-table augmentation: feeding volumes, total fed volume, combined feed
           weight, added carbon weight, removed sample volume/weight, and mass balance.
        3. Bench-table augmentation: TRY KPIs (Titer, Sp. Titer, Rate, Ins. Rate, Weight,
           Yield) and total broth / carbon balance columns.
        4. Column selection: both output tables are restricted to the caller-supplied
           keep lists.  Process columns are wrapped in a ``('Process', col)`` MultiIndex.

        Results are stored in :attr:`augmented_meta_table`, :attr:`augmented_bench_table`,
        and :attr:`augmented_process_table`.  Per-step status messages are appended to
        :attr:`output_messages`.

        Args:
            carbon_panels: Maps panel display names to the analyte names used for carbon
                accounting, e.g. ``{'Sugar': ['Glucose', 'Lactose']}``.
            panels_for_try: Maps panel display names to the product names for which TRY
                KPIs are calculated, e.g. ``{'Lcuv': ['Total Protein']}``.
            bench_cols_to_keep: Ordered list of Benchling columns to retain in the final
                bench table.  Columns absent from the augmented table are silently skipped.
            process_cols_to_keep: Ordered list of process columns to retain in the final
                process table.  Columns absent from the augmented table are silently skipped.
            panel_display_names: Maps raw Benchling class names to their human-readable
                display names, e.g. ``{'Ferm': 'Growth'}``.  Used to look up the Ferm panel
                columns (DCW, IS) needed for TRY KPI corrections and mass-balance.
        """
        self._augment_meta_table()
        self._augment_process_table(panel_display_names)
        self._augment_bench_table(carbon_panels, panels_for_try, panel_display_names)
        self._select_final_augmented_columns(process_cols_to_keep, bench_cols_to_keep)

    def _augment_meta_table(self) -> None:
        """Placeholder augmentation step for the metadata table.

        No derived columns are added at this time.  A success message is appended
        to :attr:`output_messages` so callers can confirm the step ran.
        """
        self.output_messages.append("Successfully augmented Metadata table.")

    def _augment_process_table(self, panel_display_names: Dict[str, str]) -> None:
        """Augments the process (Eve/Pi) table with derived feeding and mass-balance columns.

        If the table is empty on entry, a synthetic ``Tank`` / ``Time (h)`` scaffold is
        built from the metadata table (seed tanks whose name starts with ``'S'`` are
        excluded from the scaffold).  The ``'Exp'`` key column is then set for every row
        and :meth:`_add_key_cols_to_eve` is applied per-tank group.

        Errors are caught, logged, and recorded in :attr:`output_messages` without
        raising so that bench-table augmentation can still proceed.

        Args:
            panel_display_names: Maps raw Benchling class names to display names
                (e.g. ``{'Ferm': 'Growth'}``).  Used inside :meth:`_add_key_cols_to_eve`
                to look up the Ferm-panel Sample Density column for sample-weight
                estimation.
        """
        try:
            # If the process table is empty, create a synthetic Tank/Time scaffold from the metadata table
            if self.augmented_process_table.empty:
                ferm_meta = self.augmented_meta_table[ # type: ignore
                    ~self.augmented_meta_table['Tank'].apply(helpers.is_seed_tank)  # type: ignore
                ]
                scaffold_parts: List[pd.DataFrame] = []
                for tank, eft in zip(ferm_meta['Tank'].values, ferm_meta['EFT (h)'].values):  # type: ignore
                    n_pts = int(eft * 60 + 1)  # type: ignore
                    scaffold_parts.append(pd.DataFrame({
                        'Tank': [tank] * n_pts,
                        'Time (h)': np.linspace(0, eft, n_pts),  # type: ignore
                    }))
                if scaffold_parts:
                    self.augmented_process_table = pd.concat(scaffold_parts, ignore_index=True)
                logger.info("Successfully created synthetic Tank/Time scaffold from metadata table.")

            # Augment the process table with the 'Exp' key column and apply _add_key_cols_to_eve per-tank group
            self.augmented_process_table['Exp'] = self.augmented_meta_table.loc[0, 'Exp'] # type: ignore
            self.augmented_process_table = self.augmented_process_table.groupby('Tank', group_keys=False).apply( # type: ignore
                self._add_key_cols_to_eve, panel_display_names
            )
            self.output_messages.append("Successfully augmented Eve table.")
            logger.info("Successfully augmented Eve table.")
        except Exception as e:
            self.output_messages.append("Something went wrong when augmenting Eve table (see logs for details).")
            logger.exception(f"Failed to augment Eve table: {e}.")

    def _augment_bench_table(
        self,
        carbon_panels: Dict[str, List[str]],
        panels_for_try: Dict[str, List[str]],
        panel_display_names: Dict[str, str],
    ) -> None:
        """Augments the Benchling result table with broth-volume, carbon, and TRY KPI columns.

        Sets the ``'Exp'`` key column and applies :meth:`_add_key_cols_to_bench` per-tank
        group.  The step is skipped (with a message) when the bench table is empty.
        Errors are caught, logged, and recorded in :attr:`output_messages`.

        Args:
            carbon_panels: Maps panel display names to the analyte names used for carbon
                accounting, e.g. ``{'Sugar': ['Glucose', 'Lactose']}``.
            panels_for_try: Maps panel display names to the product names for which TRY
                KPIs are calculated, e.g. ``{'Lcuv': ['Total Protein']}``.
            panel_display_names: Maps raw Benchling class names to display names
                (e.g. ``{'Ferm': 'Growth'}``).  Used to look up the Ferm-panel DCW and
                Insoluble Solids columns required for TRY KPI corrections.
        """
        try:
            # If the bench table is not empty, augment it with the 'Exp' key column and apply _add_key_cols_to_bench per-tank group
            if not self.augmented_bench_table.empty:
                self.augmented_bench_table['Exp'] = self.augmented_meta_table.loc[0, 'Exp'] # type: ignore
                self.augmented_bench_table = self.augmented_bench_table.groupby('Tank', group_keys=False).apply( # type: ignore
                    self._add_key_cols_to_bench, panels_for_try, panel_display_names, carbon_panels
                )
                self.output_messages.append("Successfully augmented Benchling result table.")
                logger.info("Successfully augmented Benchling result table.")
            else:
                logger.info("Benchling result table is empty, skipping augmentation.")
                self.output_messages.append("Benchling result table is empty, skipping augmentation.")
        except Exception as e:
            self.output_messages.append("Something went wrong when augmenting Benchling result table (see logs for details).")
            logger.exception(f"Failed to augment Benchling result table: {e}.")

    def _select_final_augmented_columns(self, process_cols_to_keep: List[str], bench_cols_to_keep: List[str]) -> None:
        """Restrict both output tables to the requested columns and apply MultiIndex wrapping.

        Drops any column not present in the respective keep list.  Columns listed in
        ``process_cols_to_keep`` that are absent from the augmented table are silently
        skipped.  After filtering, non-key process columns are wrapped under the
        ``'Process'`` outer level of a two-level MultiIndex; the key columns
        ``Exp``, ``Tank``, ``Replicate``, and ``Time (h)`` keep an empty string as the
        inner level, consistent with the bench-table MultiIndex convention.

        Args:
            process_cols_to_keep: Ordered list of process column names to retain.
            bench_cols_to_keep: Ordered list of Benchling column names to retain.
        """
        # Select process columns to appear in the final augmented table
        all_process_cols = self.augmented_process_table.columns
        self.augmented_process_table = self.augmented_process_table[ # type: ignore
            [col for col in process_cols_to_keep if col in all_process_cols]
        ]
        # Group process columns under 'Process' outer level
        self.augmented_process_table.columns = pd.MultiIndex.from_tuples(
            [
                (col, '') if col in ['Exp', 'Tank', 'Replicate', 'Time (h)'] else ('Process', col) # type: ignore
                for col in self.augmented_process_table.columns # type: ignore
            ]
        )

        # Select bench columns to appear in the final augmented table
        all_bench_cols = self.augmented_bench_table.columns
        self.augmented_bench_table = self.augmented_bench_table[ # type: ignore
            [col for col in bench_cols_to_keep if col in all_bench_cols]
        ]

    def _add_key_cols_to_eve(self, grp: pd.DataFrame, panel_display_names: Dict[str, str]) -> pd.DataFrame:
        """Adds derived feeding, mass-balance, and replicate columns to one tank's process group.

        For seed tanks (name starts with ``'S'``) only ``Replicate`` is set; all other
        columns require the fermentor metadata and are skipped.  For fermentation tanks the
        following are computed per time-point:

        - ``Pumped <feed_type> Vol (ml)`` — integrated from Eve/Pi pump signals or from
          a manually specified time-profile and target rate, optionally corrected by
          the measured added volume.
        - ``Total Fed Vol (ml)`` — sum of all pumped volumes.
        - ``Combined Feeds Weight (g)`` — total mass of all feeds whose density is known.
        - ``Added Carbon Weight (g)`` — mass of carbon-element feeds.
        - ``Removed Sample Vol (ml)`` / ``Removed Sample Weight (g)`` — cumulative sample
          removed up to each time-point (requires a non-empty bench table).
        - ``Mass Balance (%)`` — gravimetric mass balance using feeds, removed samples,
          and off-gas weights.

        Args:
            grp: Process table slice for a single tank, produced by
                ``groupby('Tank').apply(...)``.
            panel_display_names: Maps raw Benchling class names to display names
                (e.g. ``{'Ferm': 'Growth'}``).  Used to look up the Ferm-panel Sample
                Density column when estimating sample weight from volume.

        Returns:
            Group with the derived columns added in-place.
        """
        # Set the 'Tank' and 'Replicate' columns for the group
        tank_meta = self._meta_by_tank.loc[grp.name, :]  # type: ignore
        grp['Tank'] = grp.name # type: ignore
        grp['Replicate'] = int(tank_meta['Replicate']) # type: ignore

        if helpers.is_seed_tank(grp.name):  # type: ignore
            return grp
        else:
            # If the tank is a fermentation tank, add the feeding volumes, mass balance, and other process metrics
            for feed_type in ['Feed', 'Co-feed', 'Bolus', 'Acid', 'Base']:
                if tank_meta[f'{feed_type} Source'] != 'NA':
                    if tank_meta[f'Eve/Pi Controlled {feed_type}'].lower() == 'yes': # type: ignore
                        
                        # --- AUTOMATICALLY CONTROLLED FEED TYPE ---
                        if tank_meta[f'Max Calib. {feed_type} Pump Rate (ml/s)'] == 'NA':
                            grp[f'Pumped {feed_type} Vol (ml)'] = grp.get(f'{feed_type} Pump.Total volume, ml', np.nan) # type: ignore
                        else:
                            pump_rate = tank_meta[f'Max Calib. {feed_type} Pump Rate (ml/s)'] # type: ignore
                            feed_pct = grp.get(f'{feed_type}, %', np.nan) # type: ignore
                            duration = grp.get(f'{feed_type}.Duration, s', np.nan) # type: ignore
                            grp[f'Pumped {feed_type} Vol (ml)'] = pump_rate * feed_pct * duration
                    else:
                        # --- MANUALLY CONTROLLED FEED TYPE USING TIME PROFILE AND TARGET RATE ---
                        
                        # Parse the time profile from the metadata
                        time_profile = (
                            str(tank_meta[f'Manual {feed_type} Time Profile (h)']).replace(' ', '').split(';') # type: ignore
                        )
                        # Parse the target rate from the metadata
                        target_rate = (
                            str(tank_meta[f'Manual Target {feed_type} Rate (ml/h)']).replace(' ', '').split(';') # type: ignore
                        )
                        # Integrate the time profile and target rate to get the pumped volume
                        grp['Pump Rate (ml/h)'] = 0.
                        for interval, rate_str in zip(time_profile, target_rate):
                            t_start, t_end = map(float, interval.split('-'))
                            grp['Pump Rate (ml/h)'] += (
                                (grp['Time (h)'] > t_start) & (grp['Time (h)'] <= t_end)
                            ) * float(rate_str)
                        grp[f'Pumped {feed_type} Vol (ml)'] = (
                            grp['Pump Rate (ml/h)'].rolling(window=2).mean() * grp['Time (h)'].diff() # type: ignore
                        ).cumsum().fillna(0) # type: ignore
                    
                    # If the measured added volume is not 'NA', correct the pumped volume using the measured added volume
                    if tank_meta[f'Measured Added {feed_type} (ml)'] != 'NA': # type: ignore
                        uncorrected_total_vol = grp[grp['Time (h)'] == tank_meta['EFT (h)'] # type: ignore
                                                    ][f'Pumped {feed_type} Vol (ml)']
                        if not uncorrected_total_vol.empty: # type: ignore
                            grp[f'Pumped {feed_type} Vol (ml)'] = grp[f'Pumped {feed_type} Vol (ml)'] * (
                                tank_meta[f'Measured Added {feed_type} (ml)'] / float(uncorrected_total_vol.iloc[0]) # type: ignore
                            )

            # Add the total fed volume, combined feeds weight, and added carbon weight
            grp['Total Fed Vol (ml)'] = 0
            grp['Combined Feeds Weight (g)'] = 0
            grp['Added Carbon Weight (g)'] = 0
            for feed_type in ['Feed', 'Co-feed', 'Bolus', 'Acid', 'Base']:
                grp['Total Fed Vol (ml)'] += grp.get(f'Pumped {feed_type} Vol (ml)', 0) # type: ignore
                if tank_meta[f'{feed_type} Density (g/ml)'] != 'NA':
                    grp['Combined Feeds Weight (g)'] += grp.get(f'Pumped {feed_type} Vol (ml)', 0) * tank_meta[f'{feed_type} Density (g/ml)'] # type: ignore
                if (feed_type in ['Feed', 'Co-feed', 'Bolus']) and (tank_meta[f'{feed_type} Element'].lower() == 'carbon'): # type: ignore
                    grp['Added Carbon Weight (g)'] += grp[f'Pumped {feed_type} Vol (ml)'] / 1000 * tank_meta[f'Target {feed_type} Conc. (g/l)'] # type: ignore

            if not self.augmented_bench_table.empty:
                bench_grp = self.augmented_bench_table[self.augmented_bench_table['Tank'] == grp.name] # type: ignore

                if (bench_grp.get('Sample Weight (g)') is not None) or (bench_grp.get('Sample Vol (ml)') is not None): # type: ignore
                    nan_col = [np.nan] * len(bench_grp) # type: ignore
                    sample_vol = bench_grp.get('Sample Vol (ml)', nan_col) # type: ignore
                    sample_weight = bench_grp.get('Sample Weight (g)', sample_vol * bench_grp.get((panel_display_names.get('Ferm', 'Ferm'), 'Sample Density (g/ml)'), nan_col)) # type: ignore
                    grp['Removed Sample Vol (ml)'] = 0.
                    grp['Removed Sample Weight (g)'] = 0.
                    for time, vol, weight in zip(bench_grp['Time (h)'], sample_vol, sample_weight): # type: ignore
                        grp['Removed Sample Vol (ml)'] += (grp['Time (h)'] > time) * vol
                        grp['Removed Sample Weight (g)'] += (grp['Time (h)'] > time) * weight
                    
                    mass_balance_num = ( # type: ignore
                        grp.get('Combined Feeds Weight (g)', np.nan) - grp.get('Removed Sample Weight (g)', np.nan) + # type: ignore
                        grp.get('OURT (g)', np.nan) - grp.get('CERT (g)', np.nan) # type: ignore
                    )
                    grp['Mass Balance (%)'] = mass_balance_num / 1000 / grp.get('Weight, kg', np.nan) * 100 # type: ignore
            return grp

    def _add_key_cols_to_bench(self, grp: pd.DataFrame, panels_for_try: Dict[str, List[str]], panel_display_names: Dict[str, str], carbon_panels: Dict[str, List[str]]) -> pd.DataFrame:
        """Adds broth-volume, carbon-balance, and TRY KPI columns to one tank's bench group.

        For seed tanks (name starts with ``'S'``) only ``Replicate`` and
        ``Total Broth Vol (ml)`` are set; TRY KPIs are not computed.  For fermentation
        tanks the following are also derived:

        - ``Total Broth Vol (ml)`` — initial volume plus fed volume minus cumulative
          sample volume removed.
        - ``Added Carbon Weight (g)`` — total carbon added via feeds (from the
          already-augmented process table).
        - ``Total Carbon in Broth (g)`` — instantaneous carbon mass in broth computed
          from the carbon-panel analyte concentrations and broth volume.
        - ``Total Carbon Consumed (g)`` — cumulative carbon consumed since t=0.
        - TRY KPIs via :meth:`_compute_try_kpis`.

        Args:
            grp: Benchling table slice for a single tank, produced by
                ``groupby('Tank').apply(...)``.
            panels_for_try: Maps panel display names to the product names for which TRY
                KPIs are calculated, e.g. ``{'Lcuv': ['Total Protein']}``.
            panel_display_names: Maps raw Benchling class names to display names
                (e.g. ``{'Ferm': 'Growth'}``).  Forwarded to :meth:`_compute_try_kpis`
                to resolve the Ferm-panel DCW and Insoluble Solids columns.
            carbon_panels: Maps panel display names to analyte names used for carbon
                accounting, e.g. ``{'Sugar': ['Glucose', 'Lactose']}``.

        Returns:
            Group with the derived columns added in-place.
        """
        tank_meta = self._meta_by_tank.loc[grp.name, :]  # type: ignore
        grp['Tank'] = grp.name # type: ignore
        tank_name = str(grp.name) # type: ignore

        if helpers.is_seed_tank(grp.name):  # type: ignore
            grp['Replicate'] = int(tank_meta['Replicate']) # type: ignore
            grp['Total Broth Vol (ml)'] = tank_meta['Initial Broth Vol (ml)']
            grp = self._compute_try_kpis(grp, panels_for_try, panel_display_names, include_weight_yield=False)
        else:
            # Align bench and process tables on the Time (h) index so that
            # fed-volume and carbon data can be interpolated at sampling timepoints.
            grp.reset_index(inplace=True) # type: ignore
            grp.set_index('Time (h)', inplace=True) # type: ignore
            grp['Replicate'] = int(tank_meta['Replicate']) # type: ignore
            common_eve_bench_table = self.augmented_process_table[ # type: ignore
                (self.augmented_process_table['Tank'] == grp.name) # type: ignore
                & (self.augmented_process_table['Time (h)'].isin(list(grp.index)))].set_index('Time (h)') # type: ignore

            grp['Total Broth Vol (ml)'] = (
                tank_meta['Initial Broth Vol (ml)'] + common_eve_bench_table['Total Fed Vol (ml)'] -
                grp.get('Sample Vol (ml)', len(grp) * [0]).cumsum() # type: ignore
            )
            grp['Added Carbon Weight (g)'] = common_eve_bench_table['Added Carbon Weight (g)']
            grp['Total Carbon in Broth (g)'] = grp['Total Broth Vol (ml)'] / 1000 * (
                pd.concat( # type: ignore
                    [
                        grp.get((panel, f'{analyte} (g/L)'), pd.Series([0] * len(grp), index=grp.index)) # type: ignore
                        for panel in carbon_panels.keys() for analyte in carbon_panels[panel]
                    ],
                    axis='columns',
                )
            ).sum(axis='columns')
            grp['Total Carbon Consumed (g)'] = (
                float(grp.loc[0., 'Total Carbon in Broth (g)']) + grp['Added Carbon Weight (g)'] - # type: ignore
                grp['Total Carbon in Broth (g)'] # type: ignore
            )
            grp = grp.reset_index().set_index('index') # type: ignore
            grp = self._compute_try_kpis(grp, panels_for_try, panel_display_names, include_weight_yield=True)
        return grp

    def _compute_try_kpis(self, grp: pd.DataFrame, panels_for_try: Dict[str, List[str]], panel_display_names: Dict[str, str], include_weight_yield: bool = False) -> pd.DataFrame:
        """Computes insoluble-solids-corrected TRY KPI columns for a tank group.

        For every ``(panel, product)`` pair in ``panels_for_try``, the raw
        ``"{product} (g/L)"`` column is replaced by the following derived columns:

        - ``"{product} Titer (g/L)"`` — raw titer corrected for insoluble solids
          fraction: ``titer × (1 − IS% / 100)``.
        - ``"{product} Sp. Titer (g/g)"`` — specific titer divided by DCW.
        - ``"{product} Rate (g/L/h)"`` — titer divided by elapsed time.
        - ``"{product} Ins. Rate (g/L/h)"`` — instantaneous rate from finite differences.
        - ``"{product} Weight (g)"`` — titer × broth volume (only when ``include_weight_yield=True``).
        - ``"{product} Yield (g/g)"`` — weight divided by total carbon consumed
          (only when ``include_weight_yield=True``).

        Products whose raw column is absent from ``grp`` are silently skipped.

        Args:
            grp: Benchling table slice for a single tank.
            panels_for_try: Maps panel display names to the product names for which TRY
                KPIs are calculated, e.g. ``{'Lcuv': ['Total Protein']}``.
            panel_display_names: Maps raw Benchling class names to display names
                (e.g. ``{'Ferm': 'Growth'}``).  Used to resolve the Ferm-panel
                ``'% Insoluble Solids (g/g)'`` and ``'DCW (g/L)'`` columns.
            include_weight_yield: When ``True``, also compute Product Weight and Product
                Yield columns.  Pass ``True`` for fermentation tanks and ``False`` for
                seed tanks.  Defaults to ``False``.

        Returns:
            Group with the corrected TRY KPI columns added and the raw titer column
            removed.
        """
        for panel, products in panels_for_try.items():
            for product in products:
                if (panel, f'{product} (g/L)') not in grp.columns:
                    continue
                # Calculate the corrected titer
                grp[(panel, f'{product} Titer (g/L)')] = (
                    grp[(panel, f'{product} (g/L)')] * (
                        1. -
                        grp.get((panel_display_names.get('Ferm', 'Ferm'), '% Insoluble Solids (g/g)'), 0) / 100. # type: ignore
                    )
                )
                # Drop the raw titer column
                grp.drop((panel, f'{product} (g/L)'), axis='columns', inplace=True)
                # Calculate the specific titer
                grp[(panel, f'{product} Sp. Titer (g/g)')] = (
                    grp[(panel, f'{product} Titer (g/L)')] /
                    grp.get((panel_display_names.get('Ferm', 'Ferm'), 'DCW (g/L)'), np.nan) # type: ignore
                )
                # Calculate the rate
                grp[(panel, f'{product} Rate (g/L/h)')] = (grp[(panel, f'{product} Titer (g/L)')] / grp['Time (h)'])
                # Calculate the instantaneous rate
                grp[(panel, f'{product} Ins. Rate (g/L/h)')
                    ] = (grp[(panel, f'{product} Titer (g/L)')].diff() / grp['Time (h)'].diff()) # type: ignore
                if include_weight_yield:
                    # Calculate the product weight
                    grp[(panel, f'{product} Weight (g)')
                        ] = (grp[(panel, f'{product} Titer (g/L)')] * grp['Total Broth Vol (ml)'] / 1000)
                    # Calculate the product yield
                    grp[(panel, f'{product} Yield (g/g)')
                        ] = (grp[(panel, f'{product} Weight (g)')] / grp['Total Carbon Consumed (g)'])
        return grp

    @classmethod
    def get_classname(cls) -> str:
        """Returns the class name as a string."""
        return cls.__name__
