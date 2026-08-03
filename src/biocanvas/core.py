# biocanvas/core.py
"""Thin view-orchestrator for the biocanvas GUI application."""
import os
import json
import re
from glob import glob
from typing import Any, Dict, List, Optional, Tuple

import ipywidgets as widgets 
from IPython.display import display, HTML
from tqdm.notebook import tqdm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import logging

from biocanvas.utils import auth, helpers, logging_config, visualization, stats as utils_stats, io as utils_io
import biocanvas.styles as styles
from biocanvas.data_service import DataService
from biocanvas.ui_components import (
    PDTabWidgets,
    QCTabWidgets,
    OLTabWidgets,
    CCTabWidgets,
    GCTabWidgets,
    PRTabWidgets,
)

logger = logging.getLogger(__name__)


class App:
    """GUI for biological experiment data I/O, processing, analysis, and visualization.

    Provides an ipywidgets-based notebook interface for transferring biological
    experiment data from a project's local SQLite database, processing raw
    data into master tables, and generating statistical plots.

    The App is a thin view layer: all data work is delegated to
    :class:`~biocanvas.data_service.DataService`.  Widget
    construction is delegated to the ``*TabWidgets`` classes in
    :mod:`biocanvas.ui_components`.
    """

    # PROJECT_LIST is defined on DataService; expose here for passcode verification.
    PROJECT_LIST: Dict[str, str] = DataService.PROJECT_LIST

    def __init__(self, initial_log_level: Optional[int] = None) -> None:
        """Initialises the application.

        Args:
            initial_log_level: Optional logging level (e.g. ``logging.DEBUG``)
                to pre-select in the log-level dropdown.  Defaults to INFO.
        """
        # ── Service layer ──────────────────────────────────────────────
        self.service = DataService()

        # ── Per-tab widget groups ──────────────────────────────────────
        self.pd = PDTabWidgets(
            project_list_keys=App.PROJECT_LIST.keys(),
            initial_log_level=initial_log_level,
        )
        self.qc = QCTabWidgets()  # Quality Control (qc) Plots tab
        self.ol = OLTabWidgets()  # KPI Overlap (ol) tab
        self.cc = CCTabWidgets()  # Condition Comparison (cc) tab
        self.gc = GCTabWidgets()  # Global Comparison (gc) tab
        self.pr = PRTabWidgets()  # Publish Results (pr) tab

        # ── Wire event handlers ────────────────────────────────────────
        self._wire_observers()

        # ── Assemble top-level Tab ─────────────────────────────────────
        self._build_tab()

    # ------------------------------------------------------------------
    # Initialisation helpers
    # ------------------------------------------------------------------

    def _wire_observers(self) -> None:
        """Attach all widget event handlers."""
        # Process Data tab
        self.pd.project_dropdown.observe(self._pd_project_dropdown_on_change, names='value')
        self.pd.passcode_box.observe(self._pd_passcode_on_change, names='value')
        self.pd.log_level_dropdown.observe(self._pd_log_level_dropdown_on_change, names='value')
        self.pd.connect_button.on_click(self._handle_pd_connect_button)
        self.pd.process_button.on_click(self._handle_pd_process_button)
        self.pd.select_all_radio_button.observe(self._pd_select_all_radio_button_on_change, names='value')

        # QC Plots tab
        self.qc.exp_dropdown.observe(self._qc_exp_dropdown_on_change, names='value')
        self.qc.plot_button.on_click(self._handle_qc_plot_button)

        # KPI Overlap tab
        self.ol.exp_dropdown.observe(self._ol_exp_dropdown_on_change, names='value')
        self.ol.condition_dropdown.observe(self._ol_condition_dropdown_on_change, names='value')
        self.ol.kpi1_group_dropdown.observe(self._ol_kpi1_group_dropdown_on_change, names='value')
        self.ol.kpi2_group_dropdown.observe(self._ol_kpi2_group_dropdown_on_change, names='value')
        self.ol.plot_button.on_click(self._handle_ol_plot_button)

        # Condition Comparison tab
        self.cc.exp_dropdown.observe(self._cc_exp_dropdown_on_change, names='value')
        self.cc.kpi_group_dropdown.observe(self._cc_kpi_group_dropdown_on_change, names='value')
        self.cc.plot_button.on_click(self._handle_cc_plot_button)

        # Global Comparison tab
        self.gc.kpi_group_dropdown.observe(self._gc_kpi_group_dropdown_on_change, names='value')
        self.gc.kpi_value_dropdown.observe(self._gc_kpi_value_dropdown_on_change, names='value')
        self.gc.first_grping_param_dropdown.observe(self._gc_first_grping_param_dropdown_on_change, names='value')
        self.gc.reset_filters_button.on_click(self._handle_gc_reset_filters_button)
        self.gc.plot_button.on_click(self._handle_gc_plot_button)
        self.gc.stacked_plot_checkbox.observe(self._gc_stacked_plot_checkbox_on_chnage, names='value')

        # Publish Results tab
        self.pr.publish_report_button.on_click(self._handle_pr_publish_report_button)
        self.pr.zip_results_button.on_click(self._handle_pr_zip_button)

    def _build_tab(self) -> None:
        """Assemble the top-level Tab widget from per-tab layouts."""
        self.tab = widgets.Tab(
            children=[
                self.pd.layout,
                self.qc.layout,
                self.ol.layout,
                self.cc.layout,
                self.gc.layout,
                self.pr.layout,
            ]
        )
        self.tab.add_class(styles.BIOCANVAS_APP_CLASS)
        self.tab.set_title(0, 'Process Data')
        self.tab.set_title(1, 'QC Plots')
        self.tab.set_title(2, 'KPI Overlap')
        self.tab.set_title(3, 'Condition Comparison')
        self.tab.set_title(4, 'Global Comparison')
        self.tab.set_title(5, 'Publish Results')

    # ------------------------------------------------------------------
    # Process Data tab — observers and handlers
    # ------------------------------------------------------------------

    def _pd_project_dropdown_on_change(self, change: Dict[str, Any]) -> None:
        """Resets the Process Data tab UI when the user selects a different project."""
        self.pd.output_label.clear_output()
        self.pd.passcode_box.value = ""
        self.pd.connect_button.disabled = True
        self.pd.select_all_radio_button.disabled = True
        self.pd.process_button.disabled = True
        self.pd.generate_tables_checkbox.disabled = True
        self.pd.exp_checkbox_container.children = tuple()

    def _pd_passcode_on_change(self, change: Dict[str, Any]) -> None:
        """Activates the Connect button when the correct passcode is entered.

        Verification uses PBKDF2-HMAC-SHA256 via :func:`utils.verify_passcode`
        so the stored hash is never compared in plaintext.
        """
        self.pd.output_label.clear_output()
        entered = change['new']
        if not entered:
            return
        stored_hash = App.PROJECT_LIST[self.pd.project_dropdown.value]
        if auth.verify_passcode(stored_hash, entered):
            self.pd.connect_button.disabled = False
            logger.debug("Passcode accepted for project '%s'", self.pd.project_dropdown.value)
        else:
            self.pd.connect_button.disabled = True
            logging_config.display_log_html(
                self.pd.output_label,
                [("Incorrect passcode. Please try again!", 'warning')],
            )
            logger.debug(
                "Incorrect passcode attempt for project '%s'",
                self.pd.project_dropdown.value,
            )

    def _pd_log_level_dropdown_on_change(self, change: Dict[str, Any]) -> None:
        """Applies the newly selected log level to the root logger and its handlers."""
        level = logging_config.LOG_LEVEL_MAP.get(change['new'], logging.INFO)
        logging_config.apply_root_log_level(level)
        logger.debug("Log level changed to '%s'", change['new'])

    def _pd_select_all_radio_button_on_change(self, change: Dict[str, Any]) -> None:
        """Checks or unchecks all experiment checkboxes based on the radio-button."""
        checked = change['new'] == 'All'
        for checkbox in self.pd.exp_checkbox_container.children:
            checkbox.value = checked

    def _handle_pd_connect_button(self, _: Any) -> None:
        """Creates result dirs, loads project modules, and lists local database experiments."""
        # Clear output labels and progress bar
        self.pd.progress_bar_output.clear_output()
        self.pd.output_label.clear_output()

        # Reset the generate tables checkbox
        self.pd.generate_tables_checkbox.value = False
        
        project_name = self.pd.project_dropdown.value
        logger.debug("Connect button invoked for project '%s'", project_name)
        log_entries: List[helpers.LogEntry] = [(f"Connecting to project: {project_name}", 'header')]

        log_level = logging_config.LOG_LEVEL_MAP.get(self.pd.log_level_dropdown.value, logging.INFO)
        self.service.setup_project_dirs(project_name, log_level)

        loaded, load_logs = self.service.load_project_modules(project_name)
        log_entries.extend(load_logs)
        if not loaded:
            logging_config.display_log_html(self.pd.output_label, log_entries)
            return

        exp_names, sp_logs = self.service.fetch_experiment_names()
        log_entries.extend(sp_logs)
        logging_config.display_log_html(self.pd.output_label, log_entries)

        if exp_names:
            self._pd_add_exp_checkbox_list(exp_names)
            self.pd.select_all_radio_button.disabled = False
            self.pd.process_button.disabled = False
            self.pd.generate_tables_checkbox.disabled = False
            self._gc_add_filter_accordian_keys()
            logger.info("UI activated for %d experiment(s)", len(exp_names))

    def _pd_add_exp_checkbox_list(self, names: List[str]) -> None:
        """Populates the experiment checkbox container with one checkbox per name.

        Args:
            names: Experiment directory names to display as checkboxes.
        """
        self.pd.exp_checkbox_container.children = tuple(
            widgets.Checkbox(
                value=False,
                description=name,
                indent=False,
                layout=widgets.Layout(width='auto', padding='10px 10px 10px 10px'),
            ) for name in names
        )

    def _handle_pd_process_button(self, _: Any) -> None:
        """Processes selected experiments and builds the master tables.

        Delegates the full pipeline to :meth:`DataService.build_master_tables`,
        displays a combined log, saves CSV tables if the checkbox is ticked, and
        activates all analysis tabs when at least one experiment succeeds.

        Notes:
            Parallel execution via ThreadPoolExecutor was attempted but abandoned.
            The legacy SharePoint backend enforced per-session connection limits
            that caused intermittent failures when multiple threads issued
            concurrent requests.  Sequential processing via DataService is
            reliable and still benefits from the modular per-experiment helper.
        """
        # Clear output labels and progress bar
        self.pd.progress_bar_output.clear_output()
        self.pd.output_label.clear_output()
        
        # Get selected experiment names
        exp_names = [cb.description for cb in self.pd.exp_checkbox_container.children if cb.value]

        # Process experiments showing progress bar
        try:
            self.pd.process_button.disabled = True
            with self.pd.progress_bar_output:
                log_entries = self.service.build_master_tables(
                    tqdm(exp_names, desc="Processing experiments", bar_format="{desc}: |{bar}| {percentage:3.0f}%")
                )
                logging_config.display_log_html(self.pd.output_label, log_entries)
        finally:
            self.pd.process_button.disabled = False
        
        # Save master tables if checkbox is ticked
        saved = self.service.save_master_tables(self.pd.generate_tables_checkbox.value)
        if saved:
            self.pr.zip_results_button.disabled = False
            logger.info("Master tables saved to CSV files.")

        # Activate analysis tabs if master tables are not empty
        if not self.service.master_meta_table.empty:
            self._activate_qc_tab()
            self._activate_ol_tab()
            self._activate_cc_tab()
            self._activate_gc_tab()
        else:
            logging_config.display_log_html(self.pd.output_label, [("Master meta table is empty. No experiments processed.", 'warning')])
            logger.warning("Master meta table is empty. No experiments processed.")

    # ------------------------------------------------------------------
    # Tab-activation helpers
    # ------------------------------------------------------------------

    def _activate_qc_tab(self) -> None:
        """Enables all QC Plots tab widgets and populates the experiment dropdown."""
        self.qc.exp_dropdown.disabled = False
        self.qc.exp_dropdown.options = list(
            self.service.master_meta_table.index.get_level_values('Exp').unique()  # type: ignore
        )
        self.qc.condition_dropdown.disabled = False
        self.qc.plot_button.disabled = False
        self.qc.savefig_checkbox.disabled = False

    def _activate_ol_tab(self) -> None:
        """Enables all KPI Overlap tab widgets and populates the experiment dropdown."""
        self.ol.exp_dropdown.disabled = False
        self.ol.exp_dropdown.options = list(
            self.service.master_meta_table.index.get_level_values('Exp').unique()  # type: ignore
        )
        self.ol.condition_dropdown.disabled = False
        self.ol.rep1_checkbox.disabled = False
        self.ol.rep2_checkbox.disabled = False
        self.ol.rep3_checkbox.disabled = False
        self.ol.kpi1_group_dropdown.disabled = False
        self.ol.kpi1_value_dropdown.disabled = False
        self.ol.kpi2_group_dropdown.disabled = False
        self.ol.kpi2_value_dropdown.disabled = False
        self.ol.plot_type_radio_buttons.disabled = False
        self.ol.plot_button.disabled = False
        self.ol.savefig_stats_checkbox.disabled = False
        self.ol.verbose_data_checkbox.disabled = False

    def _activate_cc_tab(self) -> None:
        """Enables all Condition Comparison tab widgets and populates dropdowns."""
        self.cc.exp_dropdown.disabled = False
        self.cc.exp_dropdown.options = list(
            self.service.master_meta_table.index.get_level_values('Exp').unique()  # type: ignore
        )
        self.cc.kpi_group_dropdown.disabled = False
        self.cc.kpi_value_dropdown.disabled = False
        self.cc.sample_time_dropdown.disabled = False
        self.cc.plot_type_radio_buttons.disabled = False
        self.cc.stacked_plot_checkbox.disabled = False
        self.cc.plot_button.disabled = False
        self.cc.verbose_data_checkbox.disabled = False
        self.cc.verbose_stats_checkbox.disabled = False
        self.cc.savefig_stats_checkbox.disabled = False

    def _activate_gc_tab(self) -> None:
        """Enables all Global Comparison tab widgets and populates their options."""
        self._gc_add_filters()
        _ = self.service.update_bench_plot_properties()
        _ = self.service.update_process_plot_properties()
        bench_kpi_li = [
            f'{panel} | {kpi}' for panel, kpis in self.service.bench_plot_properties.items()
            for kpi, content in kpis.items() if sum(content['col_exist'])
        ]
        process_kpi_li = [
            f'{panel} | {kpi}' for panel, kpis in self.service.process_plot_properties.items()
            for kpi, content in kpis.items() if sum(content['col_exist'])
        ]
        self.gc.kpi_group_dropdown.options = bench_kpi_li + process_kpi_li
        self.gc.first_grping_param_dropdown.options = (
            self.service.config_module.GLOBAL_GROUP_KEYS  # type: ignore
        )

    # ------------------------------------------------------------------
    # QC Plots tab — observers and handlers
    # ------------------------------------------------------------------

    def _qc_exp_dropdown_on_change(self, change: Dict[str, Any]) -> None:
        """Updates the Condition dropdown when the experiment selection changes."""
        conditions: List[str] = self.service.master_meta_table.loc[  # type: ignore
            self.qc.exp_dropdown.value, 'Condition'].unique()  # type: ignore
        self.qc.condition_dropdown.options = [
            c for c in conditions if not c.lower().startswith('seed')  # type: ignore
        ]

    def _handle_qc_plot_button(self, _: Any) -> None:
        """Generates QC plots for the selected experiment and condition."""
        self.qc.fig_placeholder.clear_output()

        try:
            exp: str = self.qc.exp_dropdown.value
            condition: str = self.qc.condition_dropdown.value
            logger.debug("QC plot requested exp=%s, condition=%s", exp, condition)

            filter_keys = {
                'Exp': ('in', f'{[exp]}'),
                'Condition': ('in', f'{[condition]}'),
            }
            bench_table = self.service.update_bench_plot_properties(filter_keys)
            process_table = self.service.update_process_plot_properties(filter_keys)
            logger.debug(
                "Updated tables: bench=%s, process=%s",
                bench_table.shape,
                process_table.shape,
            )

            bench_plotter = visualization.QCPlotter(
                bench_table,
                self.service.bench_plot_properties,
                plot_type='bench',
            )
            process_plotter = visualization.QCPlotter(
                process_table,
                self.service.process_plot_properties,
                plot_type='process',
            )
            bench_fig = bench_plotter.make_plots()
            process_fig = process_plotter.make_plots()
            logger.debug("QCPlotter returned bench_fig=%s, process_fig=%s", bench_fig, process_fig)

            if bench_fig:
                with self.qc.fig_placeholder:
                    display(bench_fig)
                plt.close(bench_fig)  # type: ignore
                logger.info("QC plot: Benchling figure displayed.")

            if process_fig:
                with self.qc.fig_placeholder:
                    display(process_fig)
                plt.close(process_fig)  # type: ignore
                logger.info("QC plot: Process figure displayed.")

            if self.qc.savefig_checkbox.value and bench_fig:
                self.service.save_fig_call_count += 1
                fig_description_file_path = os.path.join(self.service.figs_dir, 'plots_descriptions.json')
                visualization.generate_fig_description(
                    description={
                        'Tab': 'Quality Control',
                        'Experiment': exp,
                        'Condition': condition,
                        'Comment': 'Benchling data',
                    },
                    file_path=fig_description_file_path,
                    fig_count=self.service.save_fig_call_count,
                )
                fig_file_path = os.path.join(
                    self.service.figs_dir,
                    f"plot{self.service.save_fig_call_count}.png",
                )
                visualization.save_figure(fig=bench_fig, file_path=fig_file_path)
                logger.info("QC plot: Benchling figure saved to: %s", fig_file_path)
                self.pr.publish_report_button.disabled = False
                self.pr.zip_results_button.disabled = False

            if self.qc.savefig_checkbox.value and process_fig:
                self.service.save_fig_call_count += 1
                fig_description_file_path = os.path.join(self.service.figs_dir, 'plots_descriptions.json')
                visualization.generate_fig_description(
                    description={
                        'Tab': 'Quality Control',
                        'Experiment': exp,
                        'Condition': condition,
                        'Comment': 'Process data',
                    },
                    file_path=fig_description_file_path,
                    fig_count=self.service.save_fig_call_count,
                )
                fig_file_path = os.path.join(
                    self.service.figs_dir,
                    f"plot{self.service.save_fig_call_count}.png",
                )
                visualization.save_figure(fig=process_fig, file_path=fig_file_path)
                logger.info("QC plot: Process figure saved to: %s", fig_file_path)
                self.pr.publish_report_button.disabled = False
                self.pr.zip_results_button.disabled = False

        except Exception as e:
            logger.exception("Error generating QC plots: %s", e)
            logging_config.display_log_html(
                self.qc.fig_placeholder,
                [
                    (
                        "Error generating QC plots (see log for details). "
                        "Revise your selections and try again.",
                        'error',
                    )
                ],
            )

    # ------------------------------------------------------------------
    # KPI Overlap tab — observers and handlers
    # ------------------------------------------------------------------

    def _ol_exp_dropdown_on_change(self, change: Dict[str, Any]) -> None:
        """Updates the Condition dropdown when the experiment selection changes."""
        conditions: List[str] = self.service.master_meta_table.loc[  # type: ignore
            self.ol.exp_dropdown.value, 'Condition'].unique()
        self.ol.condition_dropdown.options = [
            c for c in conditions if not c.lower().startswith('seed')  # type: ignore
        ]

    def _ol_condition_dropdown_on_change(self, change: Dict[str, Any]) -> None:
        """Refreshes KPI dropdowns for the selected experiment and condition."""
        filter_keys = {
            'Exp': ('in', f'{[self.ol.exp_dropdown.value]}'),
            'Condition': ('in', f'{[self.ol.condition_dropdown.value]}'),
        }
        _ = self.service.update_bench_plot_properties(filter_keys)
        _ = self.service.update_process_plot_properties(filter_keys)

        bench_kpi_li = [
            f'{panel} | {kpi}' for panel, kpis in self.service.bench_plot_properties.items()
            for kpi, content in kpis.items() if sum(content['col_exist'])
        ]
        process_kpi_li = [
            f'{panel} | {kpi}' for panel, kpis in self.service.process_plot_properties.items()
            for kpi, content in kpis.items() if sum(content['col_exist'])
        ]
        kpi_li = bench_kpi_li + process_kpi_li
        self.ol.kpi1_group_dropdown.options = kpi_li
        self.ol.kpi2_group_dropdown.options = kpi_li

    def _ol_kpi1_group_dropdown_on_change(self, change: Dict[str, Any]) -> None:
        """Updates the KPI 1 value dropdown when the KPI 1 group selection changes."""
        panel, kpi = [s.strip() for s in self.ol.kpi1_group_dropdown.value.split('|')]
   
        if panel != 'Process':
            kpi_values: List[str] = [
                col for idx, col in enumerate(self.service.bench_plot_properties[panel][kpi]['cols'])
                if self.service.bench_plot_properties[panel][kpi]['col_exist'][idx]
            ]
        else:
            kpi_values = [
                col for idx, col in enumerate(self.service.process_plot_properties[panel][kpi]['cols'])
                if self.service.process_plot_properties[panel][kpi]['col_exist'][idx]
            ]

        self.ol.kpi1_value_dropdown.options = kpi_values

    def _ol_kpi2_group_dropdown_on_change(self, change: Dict[str, Any]) -> None:
        """Updates the KPI 2 value dropdown when the KPI 2 group selection changes."""
        panel, kpi = [s.strip() for s in self.ol.kpi2_group_dropdown.value.split('|')]
   
        if panel != 'Process':
            kpi_values: List[str] = [
                col for idx, col in enumerate(self.service.bench_plot_properties[panel][kpi]['cols'])
                if self.service.bench_plot_properties[panel][kpi]['col_exist'][idx]
            ]
        else:
            kpi_values = [
                col for idx, col in enumerate(self.service.process_plot_properties[panel][kpi]['cols'])
                if self.service.process_plot_properties[panel][kpi]['col_exist'][idx]
            ]

        self.ol.kpi2_value_dropdown.options = (kpi_values if len(kpi_values) <= 1 else kpi_values + ['All'])

    def _handle_ol_plot_button(self, _: Any) -> None:
        """Generates the overlapped-line KPI comparison plot."""
        self.ol.fig_placeholder.clear_output()
        self.ol.verbose_data_placeholder.clear_output()

        try:
            # --- Resolve user selections ---
            exp: str = self.ol.exp_dropdown.value
            condition: str = self.ol.condition_dropdown.value
            kpi1_panel, kpi1_group = [s.strip() for s in self.ol.kpi1_group_dropdown.value.split('|')]
            kpi2_panel, kpi2_group = [s.strip() for s in self.ol.kpi2_group_dropdown.value.split('|')]
            kpi1_value = self.ol.kpi1_value_dropdown.value
            kpi2_value = self.ol.kpi2_value_dropdown.value
            reps: List[int] = [i for i in range(1, 4) if getattr(self.ol, f"rep{i}_checkbox").value]
            plot_type: str = self.ol.plot_type_radio_buttons.value.lower()
            logger.debug(
                "OL plot requested exp=%s, condition=%s, kpi1_panel=%s, kpi1_group=%s, kpi1_value=%s, kpi2_panel=%s, kpi2_group=%s, kpi2_value=%s, reps=%s, plot_type=%s",
                exp,
                condition,
                kpi1_panel,
                kpi1_group,
                kpi1_value,
                kpi2_panel,
                kpi2_group,
                kpi2_value,
                reps,
                plot_type
            )

            # --- Resolve data tables and plot properties using filter keys ---
            filter_keys: Dict[str, Tuple[str, Any]] = {
                'Exp': ('in', f'{[exp]}'),
                'Condition': ('in', f'{[condition]}'),
                'Replicate': ('in', f'{reps}'),
            }
            bench_table: pd.DataFrame = self.service.update_bench_plot_properties(filter_keys)
            process_table: pd.DataFrame = self.service.update_process_plot_properties(filter_keys)

            # --- Collect plot properties and data tables for the selected KPI groups ---
            plot_properties: Dict[str, Any] = {}
            plot_tables: Dict[str, pd.DataFrame] = {} # type: ignore
            if kpi1_panel in self.service.bench_plot_properties and not bench_table.empty:
                plot_properties[kpi1_panel] = self.service.bench_plot_properties[kpi1_panel]
                plot_tables[kpi1_panel] = bench_table
            elif kpi1_panel in self.service.process_plot_properties and not process_table.empty:
                plot_properties[kpi1_panel] = self.service.process_plot_properties[kpi1_panel]
                plot_tables[kpi1_panel] = process_table
            else:
                raise ValueError(f"KPI1 panel {kpi1_panel} not found in bench or process plot properties")
            if kpi2_panel in self.service.bench_plot_properties and not bench_table.empty:
                plot_properties[kpi2_panel] = self.service.bench_plot_properties[kpi2_panel]
                plot_tables[kpi2_panel] = bench_table
            elif kpi2_panel in self.service.process_plot_properties and not process_table.empty:
                plot_properties[kpi2_panel] = self.service.process_plot_properties[kpi2_panel]
                plot_tables[kpi2_panel] = process_table
            else:
                raise ValueError(f"KPI2 panel {kpi2_panel} not found in bench or process plot properties")
            
            # --- Generate OL plot and results ---
            ol_plotter: visualization.OLPlotter = visualization.OLPlotter(plot_tables, plot_properties)
            ol_result: visualization.OLPlotterResults = ol_plotter.make_plots(
                panel1=kpi1_panel,
                group1=kpi1_group,
                value1=kpi1_value,
                panel2=kpi2_panel,
                group2=kpi2_group,
                value2=kpi2_value,
                plot_type=plot_type,
            )
            ol_fig = ol_result.fig
            ol_plot_data = ol_result.plot_data
            logger.debug("OL plot: fig=%s, plot_data=%s", ol_fig, ol_plot_data.shape)
            
            # --- Display OL plot ---
            with self.ol.fig_placeholder:
                display(ol_fig)
            plt.close(ol_fig)  # type: ignore
            logger.info("OL plot: figure displayed.")

            # --- Display verbose data table ---
            if self.ol.verbose_data_checkbox.value:
                data_for_display = helpers.flatten_multiindex_columns(ol_plot_data)
                with self.ol.verbose_data_placeholder:
                    pd.set_option('display.max_rows', None)
                    display(data_for_display)
                    pd.reset_option('display.max_rows')
                logger.info("OL plot: verbose data table displayed.")
            
            # --- Save OL plot and results ---
            if self.ol.savefig_stats_checkbox.value:
                self.service.save_fig_call_count += 1
                
                # Output figure description to JSON file
                fig_description_file_path = os.path.join(self.service.figs_dir, 'plots_descriptions.json')
                visualization.generate_fig_description(
                    description={
                        'Tab': 'KPI Overlap',
                        'Experiment': exp,
                        'Condition': condition,
                        'Replicate': ', '.join([str(i) for i in range(1, 4) if getattr(self.ol, f'rep{i}_checkbox').value]),
                        'KPI 1': f'{kpi1_panel} | {kpi1_group} | {kpi1_value}',
                        'KPI 2': f'{kpi2_panel} | {kpi2_group} | {kpi2_value}',
                        'Plot Type': plot_type,
                    },
                    file_path=fig_description_file_path,
                    fig_count=self.service.save_fig_call_count,
                )

                # Save OL plot figure
                fig_file_path = os.path.join(
                    self.service.figs_dir,
                    f"plot{self.service.save_fig_call_count}.png",
                )
                visualization.save_figure(fig=ol_fig, file_path=fig_file_path)
                
                # Save raw data table
                raw_data_file_path = os.path.join(
                    self.service.figs_dir,
                    f"raw_data_plot{self.service.save_fig_call_count}.csv",
                )
                helpers.flatten_multiindex_columns(ol_plot_data).to_csv(  # type: ignore
                    raw_data_file_path, index=False
                )

                # Allow publication and ZIP of results
                self.pr.publish_report_button.disabled = False
                self.pr.zip_results_button.disabled = False

        except Exception:
            logging_config.display_log_html(
                self.ol.fig_placeholder,
                [("Unexpected error occurred (see log for details). Revise your selections and try again!", 'warning')],
            )

    # ------------------------------------------------------------------
    # Condition Comparison tab — UI helpers, observers, and handlers
    # ------------------------------------------------------------------

    def _cc_add_conditions(self, conditions_info: List[Tuple[int, str]]) -> None:
        """Rebuilds the condition/replicate checkbox container for the CC tab.

        Args:
            conditions_info: List of ``(condition_number, condition_name)`` tuples
                (seed conditions excluded).
        """
        self.cc.condition_replicate_checkbox_container.children = tuple()
        for condition_info in conditions_info:
            new_condition_checkbox = widgets.Checkbox(
                value=False,
                description=f'Condition {condition_info[0]}: <i>{condition_info[1]}</i>',
                indent=False,
                layout=widgets.Layout(width='auto', padding='10px'),
            )
            cc_rep1_checkbox = widgets.Checkbox(
                value=False,
                description='<i>One</i>',
                disabled=False,
                indent=False,
                layout=widgets.Layout(width='auto', padding='1px'),
            )
            cc_rep2_checkbox = widgets.Checkbox(
                value=False,
                description='<i>Two</i>',
                disabled=False,
                indent=False,
                layout=widgets.Layout(width='auto', padding='1px'),
            )
            cc_rep3_checkbox = widgets.Checkbox(
                value=False,
                description='<i>Three</i>',
                disabled=False,
                indent=False,
                layout=widgets.Layout(width='auto', padding='1px'),
            )
            new_replicate_checkbox = widgets.HBox(
                children=[
                    widgets.HTML("Replicate/Tank: "),
                    cc_rep1_checkbox,
                    cc_rep2_checkbox,
                    cc_rep3_checkbox,
                ],
                layout=widgets.Layout(padding='10px 0 20px 0'),
            )
            self.cc.condition_replicate_checkbox_container.children += (  # type: ignore
                new_condition_checkbox,
            )
            self.cc.condition_replicate_checkbox_container.children += (  # type: ignore
                new_replicate_checkbox,
            )

    def _cc_exp_dropdown_on_change(self, change: Dict[str, Any]) -> None:
        """Refreshes CC tab controls when the user selects a different experiment."""
        conditions: List[str] = self.service.master_meta_table.loc[  # type: ignore  
            self.cc.exp_dropdown.value, 'Condition'].unique()
        conditions_info: List[Tuple[int, str]] = [
            (i + 1, c) for i, c in enumerate(conditions)  # type: ignore
            if not c.lower().startswith('seed')
        ]
        self._cc_add_conditions(conditions_info)

        filter_keys = {'Exp': ('in', f'{[self.cc.exp_dropdown.value]}')}
        bench_table = self.service.update_bench_plot_properties(filter_keys)
        process_table = self.service.update_process_plot_properties(filter_keys)

        bench_kpi_li = [
            f'{panel} | {kpi}' for panel, kpis in self.service.bench_plot_properties.items()
            for kpi, content in kpis.items() if sum(content['col_exist'])
        ]
        process_kpi_li = [
            f'{panel} | {kpi}' for panel, kpis in self.service.process_plot_properties.items()
            for kpi, content in kpis.items() if sum(content['col_exist'])
        ]
        self.cc.kpi_group_dropdown.options = bench_kpi_li + process_kpi_li

        if (bench_table is not None) and (not bench_table.empty):  # type: ignore
            self.cc.sample_time_dropdown.options = (
                list(bench_table[('Time (h)', '')].unique()) + ['All']  # type: ignore
            )
        else:
            if (process_table is not None) and (not process_table.empty):  # type: ignore
                max_process_time = int(max(process_table[('Time (h)', '')].values))  # type: ignore
                self.cc.sample_time_dropdown.options = (list(range(0, max_process_time + 1)) + ['All'])
            else:
                self.cc.sample_time_dropdown.options = []

    def _cc_kpi_group_dropdown_on_change(self, change: Dict[str, Any]) -> None:
        """Updates the KPI value dropdown when the KPI group selection changes."""
        panel, kpi = [s.strip() for s in self.cc.kpi_group_dropdown.value.split('|')]
        logger.debug("CC plot: kpi_group_dropdown changed to %s", self.cc.kpi_group_dropdown.value)
        logger.debug("CC plot: panel=%s, kpi=%s", panel, kpi)
   
        if panel != 'Process':
            kpi_values: List[str] = [
                col for idx, col in enumerate(self.service.bench_plot_properties[panel][kpi]['cols'])
                if self.service.bench_plot_properties[panel][kpi]['col_exist'][idx]
            ]
        else:
            kpi_values = [
                col for idx, col in enumerate(self.service.process_plot_properties[panel][kpi]['cols'])
                if self.service.process_plot_properties[panel][kpi]['col_exist'][idx]
            ]

        self.cc.kpi_value_dropdown.options = (kpi_values if len(kpi_values) <= 1 else kpi_values + ['All'])
        logger.debug("CC plot: kpi_value_dropdown options=%s", self.cc.kpi_value_dropdown.options)

    def _handle_cc_plot_button(self, _: Any) -> None:
        """Generates the condition-comparison plot."""
        self.cc.fig_placeholder.clear_output()
        self.cc.verbose_data_placeholder.clear_output()
        self.cc.verbose_stats_placeholder.clear_output()

        try:
            # Resolve user selections
            exp: str = self.cc.exp_dropdown.value
            kpi_panel: str = self.cc.kpi_group_dropdown.value.split('|')[0].strip()
            kpi_group: str = self.cc.kpi_group_dropdown.value.split('|')[1].strip()
            kpi_value: str = self.cc.kpi_value_dropdown.value
            timepoint: Any = self.cc.sample_time_dropdown.value
            plot_type: str = self.cc.plot_type_radio_buttons.value.lower()
            stacked: bool = self.cc.stacked_plot_checkbox.value

            # Resolve condition/replicate information
            condition_replicate_info: Dict[str, Any] = {}
            children = self.cc.condition_replicate_checkbox_container.children
            for n in range(0, len(children), 2):
                if children[n].value:
                    condition_desc = children[n].description.split(':')[1].strip(' <i>').strip('</i>')
                    condition_num = int(children[n].description.split(':')[0].strip('Condition '))
                    replicate_li = [i for i in range(1, 4) if children[n + 1].children[i].value]
                    condition_replicate_info[condition_desc] = (condition_num, replicate_li)

            logger.debug(
                "CC plot: exp=%s, kpi_panel=%s, kpi_group=%s, kpi_value=%s, "
                "timepoint=%s, condition_replicate_info=%r",
                exp,
                kpi_panel,
                kpi_group,
                kpi_value,
                timepoint,
                condition_replicate_info,
            )
            
            # Resolve plot properties
            is_bench = kpi_panel != 'Process'
            plot_properties = (self.service.bench_plot_properties if is_bench else self.service.process_plot_properties)
            # Resolve data update function
            update_data = (
                self.service.update_bench_plot_properties if is_bench else self.service.update_process_plot_properties
            )
            active_conditions = {
                cond: info for cond, info in condition_replicate_info.items() if info[1]
            }
            all_replicates = sorted({
                rep for _, (_, rep_li) in active_conditions.items() for rep in rep_li
            })
            filter_keys: Dict[str, Any] = {
                'Exp': ('in', f'{[exp]}'),
                'Condition': ('in', f'{list(active_conditions.keys())}'),
                'Replicate': ('in', f'{all_replicates}'),
            }
            data: pd.DataFrame = update_data(filter_keys)
            if timepoint != 'All':
                data = data[np.isclose(data[('Time (h)', '')], timepoint)]  # type: ignore

            if ('Condition', '') not in data.columns and not data.empty:
                row_index = pd.MultiIndex.from_arrays([ # type: ignore
                    data[('Exp', '')].values, # type: ignore
                    data[('Tank', '')].values, # type: ignore
                ], names=['Exp', 'Tank']) # type: ignore
                data[('Condition', '')] = self.service.master_meta_table.loc[row_index, 'Condition'].values  # type: ignore

            df_li: List[pd.DataFrame] = []
            for condition, (condition_num, replicate_li) in active_conditions.items():
                subset = data[ # type: ignore
                    (data[('Condition', '')] == condition)  # type: ignore
                    & (data[('Replicate', '')].isin(replicate_li))  # type: ignore
                ]
                if subset.empty: # type: ignore
                    continue
                subset = subset.copy() # type: ignore
                subset[('Condition_num', '')] = condition_num
                df_li.append(subset) # type: ignore
                logger.debug("CC plot: appended table for condition=%r", condition)

            if not df_li:
                logger.warning("CC plot: df_li is empty")
                raise helpers.EmptyTableError("Data table is empty.")
            concat_data: pd.DataFrame = pd.concat(df_li, axis='index', ignore_index=True)
            logger.debug("CC plot: concat_data shape=%s", concat_data.shape)

            # Generate CC plot
            cc_plotter = visualization.CCPlotter(
                data=concat_data,
                plot_properties=plot_properties,
            )
            result: visualization.CCPlotResult = cc_plotter.make_plots(
                kpi_panel=kpi_panel,
                kpi_group=kpi_group,
                kpi_value=kpi_value,
                timepoint=timepoint,
                plot_type=plot_type,
                stacked=stacked,
            )
            cc_fig = result.fig
            cc_plot_data = result.plot_data
            cc_kpi_y = result.kpi_y

            logger.debug(
                "CC plot: fig=%s, plot_data=%s, kpi_y=%s",
                cc_fig,
                cc_plot_data.shape,
                cc_kpi_y,
            )

            # Display CC plot
            with self.cc.fig_placeholder:
                display(cc_fig)
            plt.close(cc_fig)  # type: ignore
            logger.info("CC plot: figure displayed.")

            # Display verbose data
            if self.cc.verbose_data_checkbox.value:
                data_for_display = helpers.flatten_multiindex_columns(cc_plot_data)
                with self.cc.verbose_data_placeholder:
                    pd.set_option('display.max_rows', None)
                    display(data_for_display)
                    pd.reset_option('display.max_rows')
                    logger.info("CC plot: verbose data table displayed.")

            cc_summary_stats: Optional[pd.DataFrame] = None
            if self.cc.verbose_stats_checkbox.value or self.cc.savefig_stats_checkbox.value:
                cc_summary_stats, _ = utils_stats.calculate_stats(
                    data=cc_plot_data,
                    x='Condition_num',
                    y=cc_kpi_y,
                    hue='Time (h)' if timepoint == 'All' else None,
                )

            if self.cc.verbose_stats_checkbox.value and cc_summary_stats is not None:
                with self.cc.verbose_stats_placeholder:
                    pd.set_option('display.max_rows', None)
                    display(HTML('Table of summary statistics for each value of <b>Condition</b>:\n\n'))
                    display(cc_summary_stats)
                    pd.reset_option('display.max_rows')

            # Save CC plot
            if self.cc.savefig_stats_checkbox.value:
                self.service.save_fig_call_count += 1
                fig_description_file_path = os.path.join(self.service.figs_dir, 'plots_descriptions.json')
                visualization.generate_fig_description(
                    description={
                        'Tab': 'Condition Comparison',
                        'Exp': exp,
                        'Condition': ' | '.join(condition_replicate_info.keys()),
                        'Replicate': ' | '.join([', '.join([str(el) for el in item[1]]) for item in condition_replicate_info.values()]),
                        'KPI Group': kpi_group,
                        'KPI Value': kpi_value,
                        'Timepoint': str(timepoint) if timepoint != 'All' else 'All',
                    },
                    file_path=fig_description_file_path,
                    fig_count=self.service.save_fig_call_count,
                )
                fig_file_path = os.path.join(
                    self.service.figs_dir,
                    f"plot{self.service.save_fig_call_count}.png",
                )
                visualization.save_figure(fig=cc_fig, file_path=fig_file_path)
                
                raw_data_file_path = os.path.join(
                    self.service.figs_dir,
                    f"raw_data_plot{self.service.save_fig_call_count}.csv",
                )
                helpers.flatten_multiindex_columns(cc_plot_data).to_csv(  # type: ignore
                    raw_data_file_path, index=False
                )
                self.pr.publish_report_button.disabled = False
                self.pr.zip_results_button.disabled = False

                if cc_summary_stats is None:
                    cc_summary_stats, _ = utils_stats.calculate_stats(
                        data=cc_plot_data,
                        x='Condition_num',
                        y=cc_kpi_y,
                        hue='Time (h)' if timepoint == 'All' else None,
                    )
                cc_summary_stats.to_csv( # type: ignore
                    os.path.join(
                        self.service.figs_dir,
                        f"summary_stats_plot{self.service.save_fig_call_count}.csv",
                    ),
                    index=False,
                )

        except utils_stats.StatsCalculationError:
            logging_config.display_log_html(
                self.cc.verbose_stats_placeholder,
                [("Statistics calculation failed (see log for details).", 'warning')],
            )
        except Exception:
            logging_config.display_log_html(
                self.cc.fig_placeholder,
                [("Unexpected error occurred (see log for details). Revise your selections and try again!", 'warning')],
            )

    # ------------------------------------------------------------------
    # Global Comparison tab — UI helpers, observers, and handlers
    # ------------------------------------------------------------------

    def _gc_add_filter_accordian_keys(self) -> None:
        """Populates the GC filter accordion with one panel per filter key.

        No-op if the accordion already has children (prevents duplicate keys on
        repeated Connect calls).
        """
        if len(self.gc.filter_accordion.children) == 0:
            for filter_num, filter_key in enumerate( # type: ignore
                self.service.config_module.GLOBAL_FILTER_KEYS # type: ignore
            ):
                self.gc.filter_accordion.set_title(filter_num, filter_key)
                self.gc.filter_accordion.children += (
                    widgets.SelectMultiple(
                        options=[],
                        value=[],
                        rows=5,
                        layout={
                            'width': 'auto',
                            'padding': '0px 0px 0px 0px'
                        },
                    ),
                )

    def _gc_add_filters(self) -> None:
        """Populates each GC filter accordion panel with selectable options."""
        for idx, filter_key in enumerate( # type: ignore
            self.service.config_module.GLOBAL_FILTER_KEYS  # type: ignore
        ):
            if filter_key == 'Exp':
                self.gc.filter_accordion.children[idx].options = list(
                    self.service.master_meta_table.index.get_level_values(filter_key).unique()  # type: ignore
                )
            elif filter_key == 'Time (h)':
                if not self.service.master_bench_table.empty:
                    self.gc.filter_accordion.children[idx].options = sorted(
                        list(self.service.master_bench_table[(filter_key, '')].unique())  # type: ignore
                    )
                else:
                    self.gc.filter_accordion.children[idx].options = np.linspace(
                        0,
                        max(self.service.master_meta_table['EFT (h)']),  # type: ignore
                        int(max(self.service.master_meta_table['EFT (h)']) + 1),  # type: ignore 
                    )
            else:
                self.gc.filter_accordion.children[idx].options = list(
                    self.service.master_meta_table[filter_key].unique()  # type: ignore
                )

    def _gc_kpi_group_dropdown_on_change(self, change: Dict[str, Any]) -> None:
        """Activates GC controls and refreshes the KPI value dropdown."""
        self.gc.kpi_group_dropdown.disabled = False
        self.gc.kpi_value_dropdown.disabled = False
        self.gc.first_grping_param_dropdown.disabled = False
        self.gc.second_grping_param_dropdown.disabled = False
        self.gc.plot_type_radio_button.disabled = False
        self.gc.plot_button.disabled = False
        self.gc.reset_filters_button.disabled = False
        self.gc.verbose_data_checkbox.disabled = False
        self.gc.verbose_stats_checkbox.disabled = False
        self.gc.savefig_stats_checkbox.disabled = False

        panel: str = self.gc.kpi_group_dropdown.value.split('|')[0].strip()
        kpi_group: str = self.gc.kpi_group_dropdown.value.split('|')[1].strip()
        if panel != 'Process':
            kpi_values: List[str] = [
                col for idx, col in enumerate(self.service.bench_plot_properties[panel][kpi_group]['cols'])
                if self.service.bench_plot_properties[panel][kpi_group]['col_exist'][idx]
            ]
        else:
            kpi_values = [
                col for idx, col in enumerate(self.service.process_plot_properties[panel][kpi_group]['cols'])
                if self.service.process_plot_properties[panel][kpi_group]['col_exist'][idx]
            ]

        self.gc.kpi_value_dropdown.options = (kpi_values if len(kpi_values) <= 1 else kpi_values + ['All'])

    def _gc_first_grping_param_dropdown_on_change(self, change: Dict[str, str]) -> None:
        """Updates the second grouping dropdown and exposes Lineplot when Time is on X-axis."""
        local_group_keys: List[str] = list(self.service.config_module.GLOBAL_GROUP_KEYS  # type: ignore
                                           )
        local_group_keys.remove(change['new'])
        self.gc.second_grping_param_dropdown.options = ['---'] + local_group_keys

        if change['new'] == 'Time (h)':
            self.gc.plot_type_radio_button.options = ['Barplot', 'Boxplot', 'Lineplot']
        else:
            if self.gc.plot_type_radio_button.value == 'Lineplot':
                self.gc.plot_type_radio_button.value = 'Barplot'
            self.gc.plot_type_radio_button.options = ['Barplot', 'Boxplot']

    def _gc_kpi_value_dropdown_on_change(self, change: Dict[str, Any]) -> None:
        """Enables or disables the stacked-plot checkbox depending on the KPI value."""
        if change['new'] == 'All':
            self.gc.stacked_plot_checkbox.disabled = False
        else:
            self.gc.stacked_plot_checkbox.disabled = True
            self.gc.stacked_plot_checkbox.value = False

    def _gc_stacked_plot_checkbox_on_chnage(self, change: Dict[str, Any]) -> None:
        """Locks or unlocks secondary-grouping and plot-type controls for stacked mode."""
        if change['new']:
            self.gc.second_grping_param_dropdown.value = '---'
            self.gc.second_grping_param_dropdown.disabled = True
            self.gc.plot_type_radio_button.disabled = True
            self.gc.plot_type_radio_button.value = 'Barplot'
        else:
            self.gc.second_grping_param_dropdown.disabled = False
            self.gc.plot_type_radio_button.disabled = False

    def _handle_gc_plot_button(self, _: Any) -> None:
        """Generates the global-comparison plot."""
        self.gc.fig_placeholder.clear_output()
        self.gc.verbose_data_placeholder.clear_output()
        self.gc.verbose_stats_placeholder.clear_output()

        try:
            # --- Resolve user selections ---
            filter_keys: Dict[str, Any] = {
                filter_key: ('in', f'{list(self.gc.filter_accordion.children[panel_num].value)}')
                for panel_num, filter_key in # type: ignore
                enumerate(
                    self.service.config_module.GLOBAL_FILTER_KEYS[:-1]  # type: ignore
                ) if self.gc.filter_accordion.children[panel_num].value
            }
            last_child = self.gc.filter_accordion.children[-1]
            sample_time_li: List[Any] = list(last_child.value if last_child.value else last_child.options)
            kpi_panel, kpi_group = [s.strip() for s in self.gc.kpi_group_dropdown.value.split('|')]
            kpi_value: str = self.gc.kpi_value_dropdown.value
            first_grping_param: str = self.gc.first_grping_param_dropdown.value
            second_grping_param: str = self.gc.second_grping_param_dropdown.value
            plot_type: str = self.gc.plot_type_radio_button.value.lower()
            stacked: bool = self.gc.stacked_plot_checkbox.value

            logger.info(
                "GC plot: filter_keys=%s, sample_time_li=%s, kpi_panel=%s, kpi_group=%s, "
                "kpi_value=%s, first_grping_param=%s, second_grping_param=%s, "
                "plot_type=%s, stacked=%s",
                filter_keys,
                sample_time_li,
                kpi_panel,
                kpi_group,
                kpi_value,
                first_grping_param,
                second_grping_param,
                plot_type,
                stacked,
            )
            # --- Resolve plot properties ---
            is_bench = kpi_panel != 'Process'
            plot_properties = (self.service.bench_plot_properties if is_bench else self.service.process_plot_properties)
            update_table = (
                self.service.update_bench_plot_properties if is_bench else self.service.update_process_plot_properties
            )
            # --- Resolve data table ---
            table: pd.DataFrame = update_table(filter_keys)
            if table.empty:
                logger.warning("GC plot: Data table is empty after filtering.")
                raise helpers.EmptyTableError('Data table is empty.')
            
            # --- Resolve plotter ---
            gc_plotter = visualization.GCPlotter(
                data=table,
                plot_properties=plot_properties,
                master_meta_table=self.service.master_meta_table,
            )
            result: visualization.GCPlotResult = gc_plotter.make_plot(
                kpi_panel=kpi_panel,
                kpi_group=kpi_group,
                kpi_value=kpi_value,
                first_grping_param=first_grping_param,
                second_grping_param=second_grping_param,
                sample_time_li=sample_time_li,
                plot_type=plot_type,
                stacked=stacked,
            )
            gc_fig = result.fig
            gc_plot_data = result.plot_data
            gc_kpi_y = result.kpi_y

            with self.gc.fig_placeholder:
                display(gc_fig)
            plt.close(gc_fig)  # type: ignore

            logger.info(
                "GC plot: fig=%s, plot_data=%s, kpi_y=%s",
                gc_fig,
                gc_plot_data.shape,
                gc_kpi_y,
            )

            if self.gc.verbose_data_checkbox.value:
                data_for_display = helpers.flatten_multiindex_columns(gc_plot_data)
                with self.gc.verbose_data_placeholder:
                    pd.set_option('display.max_rows', None)
                    display(data_for_display)
                    pd.reset_option('display.max_rows')

            gc_summary_stats: Optional[pd.DataFrame] = None
            gc_sig_stats: Optional[pd.DataFrame] = None
            if self.gc.verbose_stats_checkbox.value or self.gc.savefig_stats_checkbox.value:
                gc_summary_stats, gc_sig_stats = utils_stats.calculate_stats(
                    data=gc_plot_data,
                    x=first_grping_param,
                    y=gc_kpi_y,
                    hue=second_grping_param if second_grping_param != '---' else None,
                    run_sig_test=True,
                )

            if self.gc.verbose_stats_checkbox.value and gc_summary_stats is not None:
                summary_stats, sig_stats = gc_summary_stats, gc_sig_stats
                with self.gc.verbose_stats_placeholder:
                    pd.set_option('display.max_rows', None)
                    display(
                        HTML(f'Table of summary statistics for each value of '
                             f'<b>{first_grping_param}</b>:\n\n')
                    )
                    display(summary_stats)
                    display(HTML('\n'))
                    display(
                        HTML(
                            f'Table of statistically significance differences between pair of '
                            f'values from <b>{first_grping_param}</b>:\n\n'
                        )
                    )
                    display(sig_stats)
                    pd.reset_option('display.max_rows')

            if self.gc.savefig_stats_checkbox.value:
                self.service.save_fig_call_count += 1
                filters_keys_for_figure: Dict[str, Any] = {
                    filter_key: self.gc.filter_accordion.children[panel_num].value
                    for panel_num, filter_key in # type: ignore
                    enumerate(
                        self.service.config_module.GLOBAL_FILTER_KEYS  # type: ignore
                    ) if self.gc.filter_accordion.children[panel_num].value
                }
                fig_description_file_path = os.path.join(self.service.figs_dir, 'plots_descriptions.json')
                visualization.generate_fig_description(
                    description={
                        'Tab': 'Global Comparison',
                        'Filter': ' | '.join([f"<{key}>={', '.join([str(el) for el in val])}" for key, val in filters_keys_for_figure.items()]),
                        'KPI Group': kpi_group,
                        'KPI Value': kpi_value,
                        'First Grouping Parameter': first_grping_param,
                        'Second Grouping Parameter': (second_grping_param if second_grping_param != '---' else None),
                    },
                    file_path=fig_description_file_path,
                    fig_count=self.service.save_fig_call_count,
                )
                fig_file_path = os.path.join(
                    self.service.figs_dir,
                    f"plot{self.service.save_fig_call_count}.png",
                )
                visualization.save_figure(fig=gc_fig, file_path=fig_file_path)
                raw_data_file_path = os.path.join(
                    self.service.figs_dir,
                    f"raw_data_plot{self.service.save_fig_call_count}.csv",
                )
                helpers.flatten_multiindex_columns(gc_plot_data).to_csv(  # type: ignore
                    raw_data_file_path, index=False
                )
                self.pr.publish_report_button.disabled = False
                self.pr.zip_results_button.disabled = False

                if gc_summary_stats is None or gc_sig_stats is None:
                    gc_summary_stats, gc_sig_stats = utils_stats.calculate_stats(
                        data=gc_plot_data,
                        x=first_grping_param,
                        y=gc_kpi_y,
                        hue=second_grping_param if second_grping_param != '---' else None,
                        run_sig_test=True,
                    )
                gc_summary_stats.to_csv( # type: ignore
                    os.path.join(
                        self.service.figs_dir,
                        f"summary_stats_plot{self.service.save_fig_call_count}.csv",
                    ),
                    index=False,
                )
                gc_sig_stats.to_csv( # type: ignore
                    os.path.join(
                        self.service.figs_dir,
                        f"significance_stats_plot{self.service.save_fig_call_count}.csv",
                    ),
                    index=True,
                )

        except utils_stats.StatsCalculationError:
            logging_config.display_log_html(
                self.gc.verbose_stats_placeholder,
                [("Statistics calculation failed (see log for details).", 'warning')],
            )
        except Exception:
            logging_config.display_log_html(
                self.gc.fig_placeholder,
                [("Unexpected error occurred (see log for details). Revise your selections and try again!", 'warning')],
            )

    def _handle_gc_reset_filters_button(self, _: Any) -> None:
        """Clears all active GC filter selections."""
        for i in range(len(self.gc.filter_accordion.children)):
            self.gc.filter_accordion.children[i].value = []

    # ------------------------------------------------------------------
    # Publish Results tab — handlers
    # ------------------------------------------------------------------

    def _handle_pr_publish_report_button(self, _: Any) -> None:
        """Discovers saved plots, loads descriptions, and generates Excel/HTML reports."""
        self.pr.output_label.clear_output()

        try:
            plots = sorted(
                [el.split('/')[-1].rstrip('.png') for el in glob(f'{self.service.figs_dir}/*.png')],
                key=lambda el: int(re.search(r'\d+$', el).group()) if re.search(r'\d+$', el) else 0,  # type: ignore
            )
            descriptions_path = os.path.join(self.service.figs_dir, 'plots_descriptions.json')
            with open(descriptions_path, 'r') as f:
                descriptions = json.load(f)
            plot_description = {
                name: pd.DataFrame({'values': list(meta.values())}, index=list(meta.keys()))
                for name, meta in descriptions.items()
            }
            utils_io.create_xlsx_report(
                plot_names=plots,
                plot_description=plot_description,
                source_dir=self.service.figs_dir,
                save_dir=self.service.results_dir,
            )
            utils_io.create_html_report(
                plot_names=plots,
                plot_description=plot_description,
                source_dir=self.service.figs_dir,
                save_dir=self.service.results_dir,
                project_version=self.service.config_module.PROJECT_VERSION  # type: ignore
            )
            with self.pr.output_label:
                display(
                    HTML(
                        f'Consolidated report published to '
                        f'<b>{self.service.results_dir}/report.xlsx</b> and '
                        f'<b>{self.service.results_dir}/report.html</b>.'
                    )
                )

        except Exception as e:
            logger.exception("Error publishing report: %s", e)
            logging_config.display_log_html(
                self.pr.output_label,
                [("Error publishing report (see log for details).", 'error')],
            )

    def _handle_pr_zip_button(self, _: Any) -> None:
        """Compresses the results directory into a zip archive."""
        self.pr.output_label.clear_output()

        try:
            if os.path.exists(self.service.results_dir):
                utils_io.zip_files(
                    source_dir=self.service.results_dir,
                    save_dir=self.service.root_dir,
                )
                with self.pr.output_label:
                    display(HTML(f'<b>{self.service.results_dir}</b> directory is zipped successfully.'))
            else:
                raise FileNotFoundError(f'No <{self.service.results_dir}> directory found!')

        except FileNotFoundError as e:
            logger.error("PR zip: file not found: %s", e)
            logging_config.display_log_html(
                self.pr.output_label,
                [("Error zipping files (see log for details).", 'error')],
            )
        except Exception as e:
            logger.exception("Error zipping files: %s", e)
            logging_config.display_log_html(
                self.pr.output_label,
                [("Error zipping files (see log for details).", 'error')],
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def display(self) -> None:
        """Displays the app and CSS styling in the Jupyter Notebook."""
        display(self.tab)
        display(HTML(styles.APP_CSS))
