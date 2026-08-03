# biocanvas/utils/visualization.py
"""Plotting classes and figure utilities for QC, OL, CC, and GC tabs."""
import os
import json
import copy
from math import ceil
import numpy as np
import pandas as pd 
import matplotlib.pyplot as plt
import matplotlib.axes
import matplotlib.figure
import seaborn as sns
from IPython.display import display  # type: ignore
from ipywidgets import widgets  # type: ignore
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Set, Tuple, Union, Iterable
import logging

import biocanvas.styles as styles
from biocanvas.utils.helpers import (
    EmptyTableError,
    PlottingError,
    join_kpi_data_on_index,
    profile_method,
)

logger = logging.getLogger(__name__)


def generate_fig_description(description: dict[str, Any], file_path: str, fig_count: int) -> None:
    """Writes plot metadata to a JSON file.

    Reads the existing JSON file (if present), adds or overwrites the entry for
    this figure, then writes the full dict back. The file maps plot keys such as
    'plot1' to their metadata dicts.

    Args:
        description: Dictionary containing plot metadata and descriptions.
        file_path: File path to save the description file.
        fig_count: Figure number for identification.
    """
    existing: dict[str, Any] = {}
    if os.path.isfile(file_path):
        with open(file_path, 'r') as f:
            existing = json.load(f)
    existing[f'plot{fig_count}'] = description
    with open(file_path, 'w') as f:
        json.dump(existing, f, indent=4)


def save_figure(fig: matplotlib.figure.Figure, file_path: str) -> None:
    """Saves a Matplotlib figure to a specified file path.

    Saves the figure as a PNG file. Creates parent directories if they do not
    already exist.

    Args:
        fig: Matplotlib figure object to save.
        file_path: File path to save the figure.
    """
    parent_dir: str = os.path.dirname(file_path)
    if not os.path.exists(parent_dir):
        os.makedirs(parent_dir)
    fig.savefig(file_path, bbox_inches='tight')  # type: ignore


class QCPlotter:
    """A utility class for generating Quality Control (QC) plots.

    Each instance is responsible for a single data source (either bench or
    process). Instantiate one ``QCPlotter`` per data type and call
    :meth:`make_plots` without arguments.

    Attributes:
        _table: Deep copy of the data table for this plotter.
        _plot_properties: Plot properties configuration for this plotter.
        _marker_num: Marker style index (``0`` for bench, ``-1`` for process).

    Args:
        table: Data table for plotting.
        plot_properties: Plot properties configuration for this data type.
        plot_type: Either ``'bench'`` or ``'process'``; controls the marker
            style used in the generated figure.
    """
    def __init__(
        self,
        table: pd.DataFrame,
        plot_properties: Dict[str, Dict[str, Dict[str, Any]]],
        plot_type: str,
    ):
        self._table = table.copy()
        self._plot_properties = copy.deepcopy(plot_properties)
        self._marker_num: int = 0 if plot_type == 'bench' else -1

    @profile_method
    def make_plots(self) -> Optional[matplotlib.figure.Figure]:
        """Generates QC plots for this plotter's data table.

        Returns:
            A Matplotlib figure object if plots are generated, otherwise None.
        """
        table = self._table
        plot_properties = self._plot_properties
        plot_marker_num = self._marker_num

        # Check if the data table is empty.
        if table.empty:
            return None

        # Calculate the total number of plots required.
        num_plots = sum(sum(content['col_exist']) for kpis in plot_properties.values() for content in kpis.values())

        # Determine subplot grid dimensions.
        subplots_nrows = ceil(num_plots / styles.PLOT_CONFIG['qc']['num_subplot_col'])
        subplots_ncols = styles.PLOT_CONFIG['qc']['num_subplot_col']

        # Set figure size based on the number of subplot rows.
        if subplots_nrows <= 1:
            fig_size = (
                subplots_ncols * styles.PLOT_CONFIG['qc']['fig_size']['one_row'][0],
                subplots_nrows * styles.PLOT_CONFIG['qc']['fig_size']['one_row'][1]
            )
        else:
            fig_size = (
                subplots_ncols * styles.PLOT_CONFIG['qc']['fig_size']['multiple_rows'][0],
                subplots_nrows * styles.PLOT_CONFIG['qc']['fig_size']['multiple_rows'][1]
            )

        # Set White background without gridlines for plots.
        sns.set_theme(**styles.SEABORN_STYLES['qc'])

        # Create subplots.
        fig, ax_handle = plt.subplots(subplots_nrows, subplots_ncols, figsize=fig_size)  # type: ignore

        # Ensure ax_handle is a 2D array even for a single row subplots.
        ax_handle = ax_handle.reshape(subplots_nrows, subplots_ncols)  # type: ignore

        # Set space between subplots.
        fig.subplots_adjust(  # type: ignore
            wspace=styles.PLOT_CONFIG['qc']['subplot_wspace'],
            hspace=styles.PLOT_CONFIG['qc']['subplot_hspace']
        )

        # Generate individual subplots.
        ax_row, ax_col = 0, 0
        for panel, kpis in plot_properties.items():
            for kpi, content in kpis.items():
                for col, col_exists in zip(content['cols'], content['col_exist']):
                    if col_exists:
                        data = table[[('Time (h)', ''), ('Replicate', ''), (panel, col)]]
                        if not data.empty:
                            self.__plot_lines(
                                ax=ax_handle[ax_row][ax_col],  # type: ignore
                                data=data,
                                x=('Time (h)', ''),
                                y=[(panel, col)],
                                title=f'{panel} panel | {kpi}',
                                ylabel=content['ylabel'],
                                x_lim=content['xlim'],
                                y_lim=content['ylim'],
                                marker_num=plot_marker_num
                            )
                            ax_col += 1
                            if ax_col == subplots_ncols:
                                ax_col = 0
                                ax_row += 1

        return fig

    def __plot_lines(
        self, ax: matplotlib.axes.Axes, data: pd.DataFrame, x: Tuple[str, str], y: List[Tuple[str, str]], title: str,
        ylabel: str, x_lim: Tuple[Optional[float], Optional[float]], y_lim: Tuple[Optional[float],
                                                                                  Optional[float]], marker_num: int
    ) -> None:
        """Plots quality control lines for time-series data with specific styling.

        Creates line plots for quality control data with customizable styling,
        supporting both single and multiple KPI components.

        Args:
            ax: Matplotlib axes object to plot on.
            data: DataFrame containing the data to plot.
            x: Column tuple for x-axis data (e.g., ('Time (h)', '')).
            y: List of tuples containing (group_column_name, sub_column_name) for y-axis.
            title: Title for the plot.
            ylabel: Label for the y-axis.
            x_lim: Tuple of (min, max) for x-axis limits.
            y_lim: Tuple of (min, max) for y-axis limits.
            marker_num: Index for marker style selection.
        """
        # Get Unique replicates.
        replicates: Set[str] = set(data[('Replicate', '')].values)  # type: ignore

        if len(y) == 1:
            sns.lineplot(
                ax=ax,
                data=data,
                x=x,
                y=y[0],
                hue=('Replicate', ''),
                marker=styles.PLOT_CONFIG['qc']['markers'][marker_num],
                markersize=styles.PLOT_CONFIG['qc']['marker_size'],
                palette=styles.PLOT_CONFIG['qc']['colors'][0:len(replicates)]
            )
            # Set plot tile, axes labels, legend.
            ax.set(title=title)
            ax.set(xlim=x_lim)
            ax.set(ylim=y_lim)
            ax.set_xlabel('Time (h)', fontsize=12)
            ax.set_ylabel(y[0][1], fontsize=12)
            ax.legend(title='Replicate', fontsize=10, loc='best')
        else:
            # Iterate through y-axes columns and plot lines for respective replicates.
            for idx, y_col in enumerate(y):
                for rep_idx, rep in enumerate(replicates):
                    data_rep = data[data[('Replicate', '')] == rep]
                    if not data_rep.empty:
                        sns.lineplot(
                            ax=ax,
                            data=data_rep,
                            x=x,
                            y=y_col,
                            marker=styles.PLOT_CONFIG['qc']['markers'][idx],
                            markersize=styles.PLOT_CONFIG['qc']['marker_size'],
                            color=styles.PLOT_CONFIG['qc']['colors'][rep_idx],
                            label=y_col[1].split(' ')[0] if rep_idx == 0 else None,
                            legend=True if rep_idx == 0 else False
                        )

            # Set plot tile, axes labels, legend.
            ax.set(title=title)
            ax.set(xlim=x_lim)
            ax.set(ylim=y_lim)
            ax.set_xlabel(x[0], fontsize=12)
            ax.set_ylabel(y[0][1], fontsize=12)
            handles, labels = ax.get_legend_handles_labels()
            ax.legend(labels=labels, handles=handles, fontsize=10)


class OLPlotterResults(NamedTuple):
    """Result returned by OLPlotter.make_plots.

    Attributes:
        fig: The generated matplotlib figure, used for save/verbose display.
        kpi_data: The data for the KPI.
    """
    fig: matplotlib.figure.Figure
    plot_data: pd.DataFrame


class OLPlotter:
    """
    Overlapped Line Plotter for Time-Series KPIs.

    This class provides methods to generate overlapped line plots for comparing specified KPIs from two different
    panels (e.g., 'Benchling', 'Process') using time-series data. The resulting figure displays each KPI as a 
    line on a shared x-axis (typically time), with the option to plot each KPI on twin y-axes for clarity. 
    The class is designed for flexible comparative visualization of KPIs across multiple data sources and
    supports both 'Aggregate' and 'Individual' plot types.

    Attributes:
        _plot_tables (Dict[str, pd.DataFrame]): 
            A deep copy of the panel data tables to be used for plotting, keyed by panel name.
        _plot_properties (Dict[str, Dict[str, Dict[str, Any]]]): 
            Plot configuration properties (e.g., y-limits, x-limits, labels) available for all panels.

    Raises:
        ValueError: If a specified panel or KPI group is not found in the provided properties.
        EmptyTableError: If the data table for a requested KPI is empty.
    """
    def __init__(
        self,
        plot_tables: Dict[str, pd.DataFrame],
        plot_properties: Dict[str, Dict[str, Dict[str, Any]]],
    ) -> None:
        self._plot_tables: Dict[str, pd.DataFrame] = {k: v.copy() for k, v in plot_tables.items()}
        self._plot_properties: Dict[str, Dict[str, Dict[str, Any]]] = copy.deepcopy(plot_properties)
    
    def make_plots(self, panel1: str, group1: str, value1: str, panel2: str, group2: str, value2: str, plot_type: str) -> OLPlotterResults:
        """Generates overlapped line plots for specified panels and KPIs using time-series data.

        Args:
            panel1: Name of the first panel (e.g., 'Benchling', 'Process').
            group1: Name of KPI group from panel1 to plot.
            value1: Name of KPI value from panel1 to plot.
            panel2: Name of the second panel (e.g., 'Benchling', 'Process').
            group2: Name of KPI group from panel2 to plot.
            value2: Name of KPI value from panel2 to plot.
            plot_type: Type of plot to generate ('Aggregate' or 'Individual').

        Returns:
            OLPlotterResults containing the generated figure and the assembled DataFrame ready for plotting.

        Raises:
            ValueError: If the panel or KPI group is not found in plot properties.
            PlottingError: If the OL plot generation fails.
        """

        try:
            # --- Extract OL plot information using the _extract_information method ---
            kpi1_info: Dict[str, Any] = self._extract_information(panel1, group1, value1)
            kpi2_info: Dict[str, Any] = self._extract_information(panel2, group2, value2)
            kpi1_data: pd.DataFrame = kpi1_info['data']
            kpi2_data: pd.DataFrame = kpi2_info['data']
            kpi1_y: List[Tuple[str, str]] = kpi1_info['y']
            kpi2_y: List[Tuple[str, str]] = kpi2_info['y']
            kpi1_xlim: Tuple[Optional[float], Optional[float]] = kpi1_info['xlim']
            kpi2_xlim: Tuple[Optional[float], Optional[float]] = kpi2_info['xlim']
            kpi1_ylim: Tuple[Optional[float], Optional[float]] = kpi1_info['ylim']
            kpi2_ylim: Tuple[Optional[float], Optional[float]] = kpi2_info['ylim']
            kpi1_ylabel: str = kpi1_info['ylabel']
            kpi2_ylabel: str = kpi2_info['ylabel']
            use_marker1: bool = kpi1_info['use_marker']
            use_marker2: bool = kpi2_info['use_marker']
            logger.debug("OL plot: kpi1_data=%r, kpi2_data=%r, kpi1_y=%r, kpi2_y=%r, kpi1_xlim=%r, kpi2_xlim=%r, kpi1_ylim=%r, kpi2_ylim=%r, kpi1_ylabel=%s, kpi2_ylabel=%s, use_marker1=%r, use_marker2=%r", kpi1_data, kpi2_data, kpi1_y, kpi2_y, kpi1_xlim, kpi2_xlim, kpi1_ylim, kpi2_ylim, kpi1_ylabel, kpi2_ylabel, use_marker1, use_marker2)

            # Join the two KPI dataframes on the index.
            if kpi1_y == kpi2_y:
                both_kpi_data = kpi1_data
            else:
                both_kpi_data = join_kpi_data_on_index(kpi1_data, kpi2_data)
            logger.debug("both_kpi_data shape=%s", both_kpi_data.shape)

            # --- Make OL plot ---
            # Set OL plot theme and configuration
            sns.set_theme(**styles.SEABORN_STYLES['ol'])
            ol_style_properties: Dict[str, Any] = styles.PLOT_CONFIG['ol']

            # Plot the OL plot on left axis of the left subplot
            fig, ax_handles = plt.subplots(1, 2, figsize=ol_style_properties['fig_size'])  # type: ignore
            time_course_ax, kpi_comparison_ax = ax_handles
            self._plot_line(
                ax=time_course_ax,
                data=both_kpi_data,
                x=('Time (h)', ''),
                y=kpi1_y,
                ylabel=kpi1_ylabel,
                x_lim=kpi1_xlim,
                y_lim=kpi1_ylim,
                marker=use_marker1,
                plot_type=plot_type,
                style_properties=ol_style_properties,
                which_kpi='one',
            )
            logger.debug("OL plot: lines plotted on left axis of left subplot")
            # Plot the OL plot on right axis of the left subplot
            self._plot_line(
                ax=time_course_ax.twinx(),  # type: ignore
                data=both_kpi_data,
                x=('Time (h)', ''),
                y=kpi2_y,
                ylabel=kpi2_ylabel,
                x_lim=kpi2_xlim,
                y_lim=kpi2_ylim,
                marker=use_marker2,
                plot_type=plot_type,
                style_properties=ol_style_properties,
                which_kpi='two',
            )
            logger.debug("OL plot: lines plotted on right axis of left subplot")
            # Plot the scatter plot on the right subplot
            self._plot_scatter(
                ax=kpi_comparison_ax,
                data=both_kpi_data,
                x=kpi1_y,
                y=kpi2_y,
                xlabel=kpi1_ylabel,
                ylabel=kpi2_ylabel,
                x_lim=kpi1_xlim,
                y_lim=kpi2_ylim,
                plot_type=plot_type,
                style_properties=ol_style_properties,
            )
            logger.debug("OL plot: scatter plot plotted on right subplot")
            plt.tight_layout()
            return OLPlotterResults(fig=fig, plot_data=both_kpi_data)
        except Exception as e:
            logger.error("OLPlotter.make_plots: error plotting OL plot: %s", e, exc_info=True)
            raise PlottingError(f"OL Plotting failed.\n{e}") from e

    def _extract_information(self, kpi_panel: str, kpi_group: str, kpi_value: str) -> Dict[str, Any]:
        """
        Retrieve table slice and plotting configuration for the specified KPI panel, group, and value.

        Assembles the relevant slice of input data and plotting parameters needed to create a time-course
        or comparison plot for a given KPI value within a selected panel and group. This function is intended
        for use by the OLPlotter to abstract away the lookup logic for each panel/group and to centralize
        the error handling for missing or empty data.

        Args:
            kpi_panel (str): Name of the panel (e.g., 'Benchling', 'Process').
            kpi_group (str): Name of the KPI group within the selected panel.
            kpi_value (str): The KPI value to plot (should match an entry in the panel/group's columns).

        Returns:
            Dict[str, Any]: Dictionary containing:
                - 'data' (pd.DataFrame): Table with relevant columns for the plot.
                - 'y' (List[Tuple[str, str]]): List of resolved y-axis columns with (panel, col) format.
                - 'xlim' (Tuple[float, float] or Tuple[None, None]): x-axis plot limits.
                - 'ylim' (Tuple[float, float] or Tuple[None, None]): y-axis plot limits.
                - 'ylabel' (str): y-axis label for the plot.
                - 'use_marker' (bool): Whether to use markers when plotting this panel's data.

        Raises:
            ValueError: If the panel or KPI group is not present in current plot properties, or the specified
                        KPI value does not map to any existing group column.
            EmptyTableError: If the resolved data table contains no rows.

        """
   
        # Sanity check
        plot_properties: Dict[str, Dict[str, Dict[str, Any]]] = self._plot_properties
        if kpi_panel not in plot_properties:
            logger.warning("OLPlotter._extract_information: Panel '%s' not found in plot properties.", kpi_panel)
            raise ValueError(f"Panel '{kpi_panel}' not found.")
        if kpi_group not in plot_properties[kpi_panel]:
            logger.warning("OLPlotter._extract_information: KPI group '%s' not found in panel '%s'.", kpi_group, kpi_panel)
            raise ValueError(f"KPI group '{kpi_group}' not found.")

        # Extract the plot properties for the given panel and group
        kpi_props: Dict[str, Any] = plot_properties[kpi_panel][kpi_group]
        # Resolve the y-axis columns
        cols: List[str] = kpi_props['cols']
        col_exist: List[bool] = kpi_props['col_exist']
        y = [col for idx, col in enumerate(cols) if col == kpi_value and col_exist[idx]]
        resolved_y = [(kpi_panel, col) for col in y]
        logger.debug("OLPlotter._extract_information: resolved y=%r", resolved_y)

        # Extract the data for plotting
        data: pd.DataFrame = self._plot_tables[kpi_panel][[('Tank', ''), ('Replicate', ''), ('Time (h)', '')] + resolved_y]  # type: ignore
        logger.debug("OLPlotter._extract_information: data found: %r", data.shape)
        if data.empty:
            raise EmptyTableError("Data table is empty.")

        return {
            'data': data,
            'y': resolved_y,
            'xlim': kpi_props['xlim'],
            'ylim': kpi_props['ylim'],
            'ylabel': kpi_props['ylabel'],
            'use_marker': False if kpi_panel == 'Process' else True,
        }

    @staticmethod
    def _plot_line(
        ax: Optional[matplotlib.axes.Axes] = None,
        data: Optional[pd.DataFrame] = None,
        x: Optional[Tuple[str, str]] = None,
        y: Optional[List[Tuple[str, str]]] = None,
        ylabel: Optional[str] = None,
        x_lim: Tuple[Optional[float], Optional[float]] = (None, None),
        y_lim: Tuple[Optional[float], Optional[float]] = (None, None),
        marker: Optional[bool] = None,
        plot_type: str = 'aggregate',
        style_properties: Optional[Dict[str, Any]] = None,
        which_kpi: str = 'one',
    ) -> None:
        """Plots line(s) for time-series KPI data on one axis.

        Args:
            ax: The axes to draw the lines on.
            data: DataFrame containing the data to plot.
            x: Name of the column for x-axis.
            y: List of (panel, column) tuples for y-axis.
            ylabel: Label for the y-axis.
            x_lim: (min, max) x-axis limits.
            y_lim: (min, max) y-axis limits.
            marker: Whether to use markers for the line plots.
            plot_type: Type of plot to generate ('aggregate' or 'individual').
            style_properties: Style properties dictionary.
            which_kpi: Which KPI to plot
                - 'one' for the first KPI
                - 'two' for the second KPI
        """

        # Sanity check
        if data is None or x is None or y is None or ax is None or style_properties is None:
            logger.warning("OLPlotter._plot_line: Data, x, y, ax, and style_properties are required to plot lines.")
            raise ValueError("Missing required information to plot lines.")

        # Set plot style properties
        marker_symbols: List[str] = style_properties['marker_symbols'] if marker else [''] * len(style_properties['marker_symbols'])
        marker_size: int = style_properties['marker_size']
        line_styles: List[str] = style_properties['line_styles']
        line_colors: List[str] = style_properties['color_palette']
        kpi_number: int = 1 if which_kpi == 'one' else 2

        # Get unique replicates from the data
        replicates: Set[int] = set(data[('Replicate', '')].values)  # type: ignore

        # Plot lines when there is only one y-axis column
        if plot_type == 'aggregate':
            sns.lineplot(
                ax=ax,
                data=data,
                x=x,
                y=y[0],
                errorbar=("sd", 1),
                color=line_colors[kpi_number - 1],
                marker=marker_symbols[kpi_number - 1],
                markersize=marker_size,
                legend=False,
            )
        elif plot_type == 'individual':
            for rep in replicates:
                grp_rep: pd.DataFrame = data[data[('Replicate', '')] == rep]  # type: ignore
                if grp_rep.empty:
                    continue
                sns.lineplot(
                    ax=ax,
                    data=grp_rep,
                    x=x,
                    y=y[0],
                    color=line_colors[kpi_number - 1],
                    linestyle=line_styles[rep - 1],
                    marker=marker_symbols[kpi_number - 1],
                    markersize=marker_size,
                    label=f'Rep {rep}',
                    legend=False,
                )
            ax.legend(fontsize=12, loc='best')  # type: ignore
        
        # Set plot title, axes labels, legend, and grid
        ax.set_xlabel('Time (h)', fontsize=14)  # type: ignore
        ax.set_ylabel(ylabel, fontsize=14, color=line_colors[kpi_number - 1])  # type: ignore
        ax.tick_params(axis='x', labelsize=12)  # type: ignore
        ax.tick_params(axis='y', labelsize=12, colors=line_colors[kpi_number - 1])  # type: ignore
        ax.set(xlim=x_lim, ylim=y_lim)  # type: ignore
        ax.xaxis.grid(True)  # type: ignore
        ax.yaxis.grid(False)  # type: ignore

    @staticmethod
    def _plot_scatter(
        ax: Optional[matplotlib.axes.Axes] = None,
        data: Optional[pd.DataFrame] = None,
        x: Optional[List[Tuple[str, str]]] = None,
        y: Optional[List[Tuple[str, str]]] = None,
        xlabel: Optional[str] = None,
        ylabel: Optional[str] = None,
        x_lim: Tuple[Optional[float], Optional[float]] = (None, None),
        y_lim: Tuple[Optional[float], Optional[float]] = (None, None),
        style_properties: Optional[Dict[str, Any]] = None,
        plot_type: str = 'aggregate',
    ) -> None:
        """Plots a scatter plot for two KPIs on one axis.

        Args:
            ax: The axes to draw the scatter plot on.
            data: DataFrame containing the data to plot.
            x: List of (panel, column) tuples for x-axis.
            y: List of (panel, column) tuples for y-axis.
            xlabel: Label for the x-axis.
            ylabel: Label for the y-axis.
            x_lim: (min, max) x-axis limits.
            y_lim: (min, max) y-axis limits.
            plot_type: Type of plot to generate ('Aggregate' or 'Individual').
        """
        # Sanity check
        if data is None or x is None or y is None or style_properties is None:
            logger.warning("OLPlotter._plot_scatter: Data, x, y, and style_properties are required to plot scatter plot.")
            raise ValueError("Missing required information to plot scatter plot.")

        # Set plot style properties
        marker_symbols: List[str] = style_properties['marker_symbols']
        marker_colors: List[str] = style_properties['color_palette']

        # Get unique replicates from the data
        replicates: Set[int] = set(data[('Replicate', '')].values)  # type: ignore
       
        # Plot scatter plot for aggregate data
        if plot_type == 'aggregate':
            sns.scatterplot(
                ax=ax,
                data=data,
                x=x[0],
                y=y[0],
                marker=marker_symbols[0],
                s=100,
                color=marker_colors[0],
                legend=False,
            )
        # Plot scatter plot for individual data
        elif plot_type == 'individual':
            sns.scatterplot(
                ax=ax,
                data=data,
                x=x[0],
                y=y[0],
                hue=('Replicate', ''),
                marker=marker_symbols[0],
                s=100,
                palette=marker_colors[:len(replicates)],
            )
        ax.set_xlabel(xlabel, fontsize=14)  # type: ignore
        ax.set_ylabel(ylabel, fontsize=14)  # type: ignore
        ax.tick_params(axis='both', labelsize=12)  # type: ignore
        ax.set(xlim=x_lim, ylim=y_lim)  # type: ignore
        ax.xaxis.grid(True)  # type: ignore
        ax.yaxis.grid(True)  # type: ignore
        # Only the 'individual' branch above creates a hue-based legend
        # ('aggregate' explicitly passes legend=False to scatterplot); calling
        # ax.legend() unconditionally would warn about a labelless legend.
        if plot_type == 'individual':
            ax.legend(fontsize=12, loc='best')  # type: ignore


class CCPlotResult(NamedTuple):
    """NamedTuple containing the figure, plot data, and y-axis columns for a CC plot.

    Attributes:
        fig: The generated matplotlib figure, used for save/verbose display.
        plot_data: The assembled multi-condition DataFrame, used for verbose data table
            and calculating statistics.
        kpi_y: Resolved (panel, column) tuples for the y-axis, used by calculate_stats.
    """
    fig: matplotlib.figure.Figure
    plot_data: pd.DataFrame
    kpi_y: List[Tuple[str, str]]


class CCPlotter:
    """Generates condition comparison plots for the CC tab.

    Enables comparative visualization of KPIs across multiple conditions by overlaying
    time-series line plots or bar plots for single/multiple KPI components.

    Attributes:
        _data: Deep copy of the input panel data table to plot.
        _plot_properties: Plot properties configuration for all panels available.
    """
    def __init__(
        self,
        data: pd.DataFrame,
        plot_properties: Dict[str, Dict[str, Dict[str, Any]]],
    ) -> None:
        self._data: pd.DataFrame = data.copy()
        self._plot_properties: Dict[str, Dict[str, Dict[str, Any]]] = copy.deepcopy(plot_properties)

    def make_plots(
        self,
        kpi_panel: str,
        kpi_group: str,
        kpi_value: str,
        timepoint: str,
        plot_type: str,
        stacked: bool = False,
    ) -> CCPlotResult:
        """
        Generates a Condition Comparison (CC) plot and returns the figure, underlying data, and y-column mapping.

        This method produces comparative visualizations of key performance indicators (KPIs) across multiple
        experimental conditions and/or replicates. Depending on inputs, it supports:
            - aggregate or individual (per replicate) representations.
            - Plots across all timepoints (typically as a line plot) or at a specific timepoint (bar plot).
            - Optional stacked bar plots for multi-component KPIs.

        Args:
            kpi_panel (str): 
                The panel or data source name (e.g., 'Benchling', 'Process').
            kpi_group (str):
                The KPI metric or group to visualize, as defined within the panel.
            kpi_value (str):
                The specific KPI component (e.g., gene, metabolite) to plot.
            timepoint (str):
                Time selection for comparison: "All" for time series, or a single timepoint for snapshot/bar plots.
            plot_type (str):
                Plotting mode; 'aggregate' for summary/combined data or 'individual' for each replicate.
            stacked (bool, optional):
                If True, generates stacked bar plots (applies only to bar plot mode with multiple components).

        Returns:
            CCPlotResult:
                A named tuple with:
                    - fig (matplotlib.figure.Figure): The generated matplotlib figure.
                    - plot_data (pd.DataFrame): The DataFrame actually plotted and used for stats/verbose display.
                    - kpi_y (List[Tuple[str, str]]): Column labels (panel, col) used for the plot's y-axis.

        Raises:
            PlottingError: If the plotting operation fails.

        """
   
        try:
            # --- Extract CC plot information ---
            info: Dict[str, Any] = self._extract_information(
                kpi_panel=kpi_panel,
                kpi_group=kpi_group,
                kpi_value=kpi_value,
            )
            plot_data: pd.DataFrame = info['data']
            kpi_y: List[Tuple[str, str]] = info['y']
            kpi_title: str = info['title']
            kpi_ylabel: str = info['ylabel']
            kpi_xlim: Tuple[Optional[float], Optional[float]] = info['xlim']
            kpi_ylim: Tuple[Optional[float], Optional[float]] = info['ylim']
            use_marker: bool = info['use_marker']
            logger.debug("Extracted CC plot information: data=%s, y=%s, title=%s, ylabel=%s, xlim=%s, ylim=%s", plot_data.shape, kpi_y, kpi_title, kpi_ylabel, kpi_xlim, kpi_ylim)
            
            # --- Make CC plots ---
            # Set CC plot theme and configuration
            sns.set_theme(**styles.SEABORN_STYLES['cc'])
            cc_style_properties: Dict[str, Any] = styles.PLOT_CONFIG['cc']

            # Plot line plot for all timepoints if timepoint is 'All' or bar plot for a specific timepoint
            if timepoint == 'All':
                fig, ax = plt.subplots(1, 1, figsize=cc_style_properties['fig_size'])  # type: ignore
                self._plot_lines(
                    ax=ax,
                    data=plot_data,
                    x=('Time (h)', ''),
                    y=kpi_y,
                    title=kpi_title,
                    ylabel=kpi_ylabel,
                    x_lim=kpi_xlim,
                    y_lim=kpi_ylim,
                    marker=use_marker,
                    plot_type=plot_type,
                    style_properties=cc_style_properties,
                )
                logger.debug("CC plot: line plot plotted successfully")
            else:
                # Plot bar plot for a specific timepoint
                num_fig_panels: int = (
                    len(set(plot_data[('Replicate', '')].values))  # type: ignore
                    if plot_type == 'individual' and len(kpi_y) > 1 else 1
                )
                fig_width: float = cc_style_properties['fig_size'][0] * num_fig_panels
                fig_height: float = cc_style_properties['fig_size'][1]
                fig, ax = plt.subplots(1, num_fig_panels, figsize=(fig_width, fig_height), sharey=True)  # type: ignore
                fig.subplots_adjust(wspace=0.1, hspace=0.1)
                self._plot_bars(
                    ax=ax,
                    data=plot_data,
                    x=('Condition_num', ''),
                    y=kpi_y,
                    title=kpi_title,
                    ylabel=kpi_ylabel,
                    plot_type=plot_type,
                    stacked=stacked,
                    style_properties=cc_style_properties,
                )
                logger.debug("CC plot: bar plot plotted successfully")

            return CCPlotResult(fig=fig, plot_data=plot_data, kpi_y=kpi_y)
        except Exception as e:
            logger.error("CCPlotter.make_plots: error plotting CC plot: %s", e)
            raise PlottingError(f"CC Plotting failed.\n{e}")

    def _extract_information(
        self,
        kpi_panel: str,
        kpi_group: str,
        kpi_value: str,
    ) -> Dict[str, Any]:
        """
        Extract plot-relevant data and metadata for a Condition Comparison (CC) plot.

        This method retrieves filtered DataFrame columns and associated plot properties based on the provided
        panel ('kpi_panel'), KPI group ('kpi_group'), and specific metric or component ('kpi_value'). It is
        used internally to assemble all information needed to generate a CC plot in the UI.

        Args:
            kpi_panel (str): 
                The data panel or source for KPIs (e.g., 'Benchling', 'Process'). Must exist in plot properties.
            kpi_group (str): 
                The KPI group/metric cluster selected within the panel.
            kpi_value (str): 
                The specific KPI/component name to plot, or 'All' for every available KPI in the group.

        Returns:
            Dict[str, Any]: 
                A dictionary including:
                  - 'data': (pd.DataFrame) Subsetted data including all columns for plotting.
                  - 'y': (List[Tuple[str, str]]) List of column keys (tuples) corresponding to y variables.
                  - 'title': (str) Title for the output CC plot.
                  - 'ylabel': (str) y-axis label for the plot.
                  - 'xlim': (Tuple[Optional[float], Optional[float]]) Tuple setting x-axis range (may be (None, None)).
                  - 'ylim': (Tuple[Optional[float], Optional[float]]) Tuple setting y-axis range (may be (None, None)).
                  - 'use_marker': (bool) Whether to use marker symbols for series (panel-dependent).

        Raises:
            ValueError: 
                If either 'kpi_panel' or 'kpi_group' is not present in the plot properties configuration.
            EmptyTableError: 
                If the resulting filtered data for plotting is empty.
        """
   
        # Sanity check
        plot_properties: Dict[str, Dict[str, Dict[str, Any]]] = self._plot_properties
        if kpi_panel not in plot_properties:
            logger.warning("CCPlotter._extract_information: Panel '%s' not found in plot properties.", kpi_panel)
            raise ValueError(f"Panel '{kpi_panel}' not found.")
        if kpi_group not in plot_properties[kpi_panel]:
            logger.warning("CCPlotter._extract_information: KPI group '%s' not found in panel '%s'.", kpi_group, kpi_panel)
            raise ValueError(f"KPI group '{kpi_group}' not found.")

        # Extract the plot properties for the given panel and group
        kpi_props: Dict[str, Any] = plot_properties[kpi_panel][kpi_group]
        
        # Resolve the y-axis columns
        cols: List[str] = kpi_props['cols']
        if kpi_value == 'All':
            y = [col for col in cols if (kpi_panel, col) in self._data.columns]
        else:
            y = [col for col in cols if col == kpi_value and (kpi_panel, col) in self._data.columns]
        resolved_y = [(kpi_panel, col) for col in y]
        logger.debug("CCPlotter._extract_information: resolved y=%r", resolved_y)        

        # Extract the data for plotting
        data: pd.DataFrame = self._data[[('Tank', ''), ('Time (h)', ''), ('Condition_num', ''), ('Replicate', '')] + resolved_y]  # type: ignore
        logger.debug("CCPlotter._extract_information: data=%r", data.shape)
        if data.empty:
            logger.warning("CCPlotter._extract_information: Data table is empty.")
            raise EmptyTableError("Data table is empty.")

        return {
            'data': data,
            'y': resolved_y,
            'title': f'{kpi_panel} | {kpi_group}',
            'ylabel': kpi_props['ylabel'],
            'xlim': kpi_props['xlim'],
            'ylim': kpi_props['ylim'],
            'use_marker': False if kpi_panel == 'Process' else True,
        }

    @staticmethod
    def _plot_lines(
        ax: Optional[matplotlib.axes.Axes] = None,
        data: Optional[pd.DataFrame] = None,
        x: Optional[Union[str, Tuple[str, str]]] = None,
        y: Optional[Union[str, List[Tuple[str, str]]]] = None,
        title: Optional[str] = None,
        ylabel: Optional[str] = None,
        x_lim: Optional[Tuple[Optional[float], Optional[float]]] = None,
        y_lim: Optional[Tuple[Optional[float], Optional[float]]] = None,
        marker: bool = True,
        plot_type: str = 'aggregate',
        style_properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Plot condition-comparison lines for the Condition Comparison (CC) tab.

        This method renders either aggregated or individual replicate line plots for experimental conditions
        using the provided axes. The function expects data grouped by conditions (and optionally, replicates).
        Aggregated view summarizes replicates per condition (with statistic/error), while individual view shows
        each replicate as a separate line.

        Args:
            ax (matplotlib.axes.Axes): Axes object to plot lines on.
            data (pd.DataFrame): DataFrame containing at minimum columns ['Condition_num', 'Replicate', x, y].
            x (str or Tuple[str, str]): Column name or (panel, column) tuple for X (e.g., ('Time (h)', '')).
            y (str or List[Tuple[str, str]]): Single or list of (panel, column) tuples used as Y.
            title (str, optional): Plot title.
            ylabel (str, optional): Y-axis label.
            x_lim (tuple[float|None, float|None], optional): X-axis limits as (min, max).
            y_lim (tuple[float|None, float|None], optional): Y-axis limits as (min, max).
            marker (bool, optional): If True, show point markers on line plots. Default: True.
            plot_type (str): 'aggregate' for mean/error by condition or 'individual' for all replicates.
            style_properties (dict, optional): Parameters for colors, markers, line styles; see styles.CC_PLOT_STYLES.

        Raises:
            ValueError: If any of ax, data, x, y, or style_properties are None or invalid.

        Notes:
            - 'aggregate': Plots mean (±SD) over replicates, grouped by condition.
            - 'individual': Plots all replicates as separate lines per condition.
            - Y can be a list of output variables (for multi-series plots).
            - Uses seaborn.lineplot internally.
            - Styling (colors, markers, lines) is driven by style_properties, with sensible defaults from styles.py.
            - Legend and axis labeling must be completed by the caller after plotting if customized.
        """
   
   
        # Sanity check
        if data is None or x is None or y is None or ax is None or style_properties is None:
            logger.warning("CCPlotter._plot_lines: Data, x, y, ax, and style_properties are required to plot lines.")
            raise ValueError("Missing required information to plot lines.")

        # Set plot style properties
        marker_symbols: List[str] = style_properties['marker_symbols'] if marker else [''] * len(style_properties['marker_symbols'])
        marker_size: int = style_properties['marker_size']
        line_styles: List[str] = style_properties['line_styles']
        line_colors: List[str] = style_properties['color_palette']
            
        # Get unique replicates from the data
        replicates: Set[int] = set(data[('Replicate', '')].values)  # type: ignore

        # Plot lines when there is only one y-axis column
        if len(y) == 1:
            data_grouped_by_condition: Iterable[tuple[int, pd.DataFrame]] = data.groupby(('Condition_num', ''))  # type: ignore
            if plot_type == 'aggregate':
                for condition_num, grp in data_grouped_by_condition:
                    sns.lineplot(
                        ax=ax,
                        data=grp,
                        x=x,
                        y=y[0],
                        errorbar=("sd", 1),
                        color=line_colors[condition_num - 1],
                        marker=marker_symbols[condition_num - 1],
                        markersize=marker_size,
                        label=f'Condition {condition_num}',
                    )
            elif plot_type == 'individual':
                for condition_num, grp in data_grouped_by_condition:
                    for rep in replicates:
                        grp_rep: pd.DataFrame = grp[grp[('Replicate', '')] == rep]  # type: ignore
                        if grp_rep.empty:
                            continue
                        sns.lineplot(
                            ax=ax,
                            data=grp_rep,
                            x=x,
                            y=y[0],
                            color=line_colors[condition_num - 1],
                            linestyle=line_styles[rep - 1],
                            marker=marker_symbols[condition_num - 1],
                            markersize=marker_size,
                            label=f'Condition {condition_num}-Rep{rep}',
                        )

            # Set plot tile, axes labels, legend.
            ax.set(title=title)
            ax.set(xlim=x_lim)
            ax.set(ylim=y_lim)
            ax.set_xlabel('Time (h)', fontsize=14)  # type: ignore
            ax.set_ylabel(ylabel, fontsize=14)  # type: ignore
            ax.legend(fontsize=12, loc='best')  # type: ignore

        else:
            logger.warning("CCPlotter._plot_lines: Multiple KPI components for line plots are not supported. y=%r", y)
            raise ValueError("Multiple KPI components for line plots are not supported.")

    @staticmethod
    def _plot_bars(
        ax: Optional[matplotlib.axes.Axes] = None,
        data: Optional[pd.DataFrame] = None,
        x: Optional[Union[str, Tuple[str, str]]] = None,
        y: Optional[Union[str, List[Tuple[str, str]]]] = None,
        title: Optional[str] = None,
        ylabel: Optional[str] = None,
        plot_type: str = 'aggregate',
        stacked: bool = False,
        style_properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Plots condition comparison bar plots onto the given Matplotlib axes.

        This method supports both 'Aggregated' (mean ± standard deviation per group)
        and 'Individual' (per replicate) bar representations, accommodating both single
        and multiple y-axis columns. Appropriate styling and legends are applied based
        on plot type and grouping.

        Args:
            ax (Optional[matplotlib.axes.Axes]): The Matplotlib axes to plot on. In
                'Individual' mode, can be one axes per panel.
            data (Optional[pd.DataFrame]): Multi-condition DataFrame containing data
                to plot. Must contain required columns for grouping and y-values.
            x (Optional[Union[str, Tuple[str, str]]]): Column (or multi-index tuple)
                used for x-axis grouping (typically Condition).
            y (Optional[Union[str, List[Tuple[str, str]]]]): Single column or list
                of columns (panel, column tuples) to plot on y-axis.
            title (Optional[str]): Plot title displayed above the axes.
            ylabel (Optional[str]): Y-axis label.
            plot_type (Optional[str]): Either 'Aggregated' (mean/sd by group) or
                'Individual' (by replicate).
            stacked (bool): If True, display bars stacked (only applicable for
                multiple y-columns).
            style_properties (Optional[Dict[str, Any]]): Dictionary of style properties,
                such as color palettes and marker symbols, from the CC plot config.

        Raises:
            ValueError: If required arguments are missing or input is invalid.
        """
   
        
        # Sanity check
        if data is None or x is None or y is None or style_properties is None:
            logger.warning("CCPlotter._plot_bars: Data, x, y, and style_properties are required to plot bars.")
            raise ValueError("Missing required information to plot bars.")

        # Set plot style properties
        gray_palette: List[str] = style_properties['gray_palette']

        # Get unique conditions and replicates from the data
        condition_nums: Set[int] = set(data[('Condition_num', '')].values)  # type: ignore
        replicates: Set[int] = set(data[('Replicate', '')].values)  # type: ignore

        # Plot bars when there is only one y-axis column
        if len(y) == 1:
            if plot_type == 'aggregate':
                grps: Iterable[tuple[int, pd.DataFrame]] = data.groupby(('Condition_num', ''))  # type: ignore
                means: pd.Series = grps[y].mean(numeric_only=True)  # type: ignore
                errors: pd.Series = grps[y].std(ddof=0)  # type: ignore
                means.plot.bar( # type: ignore
                    ax=ax, stacked=False, yerr=errors, color=gray_palette[0], rot=0, capsize=2, linewidth=1,
                    edgecolor="k", legend=False
                )
            elif plot_type == 'individual':
                sns.barplot(
                    ax=ax,
                    data=data,
                    x=x,
                    y=y[0],
                    hue=('Replicate', ''),
                    palette=gray_palette[:len(replicates)],
                    linewidth=1,
                    edgecolor="k",
                )
                ax.legend(title='Replicate', fontsize=9, loc='upper left', bbox_to_anchor=(1.05, 1))  # type: ignore
            ax.set(title=title)  # type: ignore
            ax.set_xlabel('Condition', fontsize=12)  # type: ignore
            ax.set_ylabel(ylabel, fontsize=12)  # type: ignore
        else:
            # Plot bars when there are multiple y-axis columns
            if plot_type == 'aggregate':
                grps: Iterable[tuple[int, pd.DataFrame]] = data.groupby(('Condition_num', ''))  # type: ignore
                means: pd.Series = grps[y].mean(numeric_only=True)  # type: ignore
                errors: pd.Series = grps[y].std(ddof=0)  # type: ignore
                means.plot.bar( # type: ignore
                    ax=ax, stacked=stacked, yerr=errors, capsize=2, rot=0, linewidth=1, edgecolor='k'
                )
                ax.set_title(title)  # type: ignore
                ax.set_xticks(list(range(len(condition_nums))))  # type: ignore
                ax.set_xticklabels(condition_nums)  # type: ignore
                ax.set_xlabel('Condition', fontsize=14)  # type: ignore
                ax.set_ylabel(ylabel, fontsize=14)  # type: ignore
                ax.legend( # type: ignore
                    labels=[' '.join(el[1].split(' ')[:-1]) for el in y],
                    loc='upper left',
                    bbox_to_anchor=(1.05, 1),
                    fontsize=12
                )  # type: ignore
            elif plot_type == 'Individual':
                for idx, rep in enumerate(replicates):
                    grp_rep: pd.DataFrame = data[data[('Replicate', '')] == rep]  # type: ignore
                    if not grp_rep.empty:
                        working_ax: matplotlib.axes.Axes = ax[idx] if len(replicates) > 1 else ax  # type: ignore
                        condition_nums_rep: Set[int] = set(grp_rep[('Condition_num', '')].values)  # type: ignore
                        grp_rep.plot.bar( # type: ignore
                            ax=working_ax, y=y, stacked=stacked, yerr=None, capsize=2, rot=0, linewidth=1,
                            edgecolor='k'
                        )
                        working_ax.set_title(f'Replicate {rep}')  # type: ignore
                        working_ax.set_xticks(list(range(len(condition_nums_rep))))  # type: ignore
                        working_ax.set_xticklabels(list(condition_nums_rep))  # type: ignore
                        working_ax.set_xlabel('Condition', fontsize=14)  # type: ignore
                        working_ax.set_ylabel(ylabel, fontsize=14)  # type: ignore
                        working_ax.legend( # type: ignore
                            labels=[' '.join(el[1].split(' ')[:-1]) for el in y], loc='best', fontsize=9
                        )


class GCPlotResult(NamedTuple):
    """Result returned by GCPlotter.make_plot.

    Attributes:
        fig: The generated matplotlib figure, used for save/verbose display.
        plot_data: The assembled DataFrame ready for plotting.
        kpi_y: Resolved (panel, column) tuples for the y-axis, used by calculate_stats.
    """
    fig: matplotlib.figure.Figure
    plot_data: pd.DataFrame
    kpi_y: List[Tuple[str, str]]


class GCPlotter:
    """Generates Global Comparison (GC) plots for the biocanvas analysis UI.

    This class provides methods to create visualizations – including boxplots, bar plots (optionally stacked), 
    and line plots – to compare groups of data across one or two categorical parameters, such as experiment conditions 
    or batch identifiers. It is designed for use in the biocanvas analysis interface for high-level summary comparisons.

    Grouping and coloring for plots are automatically resolved based on the primary and secondary grouping parameters, 
    optionally using metadata from the master metadata table to provide context for non-time groupings.

    Attributes:
        _data (pd.DataFrame): The input DataFrame to be plotted.
        _plot_properties (Dict[str, Any]): Dictionary of properties and settings for the plot, based on the selected KPI panel.
        _master_meta_table (pd.DataFrame): DataFrame containing experiment and tank metadata, used to aid grouping or annotation.
    """
    def __init__(
        self,
        data: pd.DataFrame,
        plot_properties: Dict[str, Any],
        master_meta_table: pd.DataFrame,
    ) -> None:
        self._data: pd.DataFrame = data
        self._plot_properties: Dict[str, Any] = copy.deepcopy(plot_properties)
        self._master_meta_table: pd.DataFrame = master_meta_table

    def make_plot(
        self,
        kpi_panel: str,
        kpi_group: str,
        kpi_value: str,
        first_grping_param: str,
        second_grping_param: str,
        sample_time_li: List[Any],
        plot_type: str = 'boxplot',
        stacked: bool = False,
    ) -> GCPlotResult:
        """
        Generates a Global Comparison (GC) figure and returns the result including figure, plotted data, and KPI y-axis columns.

        This method provides a high-level interface to produce summary comparison plots across one or two categorical groups.
        The plot type can be a boxplot, barplot (optionally stacked), or lineplot, as selected by the user. Data is grouped as
        specified by the x-axis (first_grping_param) and an optional hue (second_grping_param). Data used for plotting is
        automatically filtered based on the provided list of sample_time_li, and KPI value(s) to show are determined by the 
        specified KPI group and value names.

        Args:
            kpi_panel (str): Name of the KPI panel, e.g., 'Benchling' or 'Process'.
            kpi_group (str): Name of the KPI group within the specified panel.
            kpi_value (str): Name of the KPI value (feature/metric) within the group to plot.
            first_grping_param (str): Column to use for the primary x-axis (grouping) of the plot.
            second_grping_param (str): Column for group coloring ("hue"), or '---' to disable.
            sample_time_li (List[Any]): List of sample time points (e.g., [24, 48, 72]) to subset the data for plotting.
            plot_type (str): The plot type to render. One of {'boxplot', 'lineplot', 'barplot'} (default: 'boxplot').
            stacked (bool, optional): If True and plot_type is 'barplot', renders bars as stacked. Defaults to False.

        Returns:
            GCPlotResult: Named tuple containing:
                - fig (matplotlib.figure.Figure): Matplotlib figure object for the GC plot.
                - plot_data (pd.DataFrame): DataFrame with the plotted data in summary/grouped format.
                - kpi_y (List[Tuple[str, str]]): List of (panel, value) column tuples used as the plot y-axis (for stats).

        Raises:
            ValueError: If any required arguments are missing or invalid.
            RuntimeError: If plot creation or data processing fails.

        """
   

        try:
            # --- Extract plot information ---
            info = self._extract_information(
                kpi_panel=kpi_panel,
                kpi_group=kpi_group,
                kpi_value=kpi_value,
                first_grping_param=first_grping_param,
                second_grping_param=second_grping_param,
                sample_time_li=sample_time_li,
            )
            plot_data: pd.DataFrame = info['data']
            plot_data_full_resolution: pd.DataFrame = info['data_full_resolution']
            kpi_y: List[Tuple[str, str]] = info['y']
            kpi_title: str = info['title']
            kpi_ylabel: str = info['ylabel']
            kpi_ylim: Tuple[Optional[float], Optional[float]] = info['ylim']
            kpi_hue: Optional[str] = info['hue']
            logger.debug(
                "GCPlotter.make_plot: extracted information, plot_data shape=%s, kpi_y=%s",
                info['data'].shape, info['y']
            )

            # --- Make GC plot ---
            # Set GC plot theme and configuration
            sns.set_theme(**styles.SEABORN_STYLES['gc'])
            gc_style_properties: Dict[str, Any] = styles.PLOT_CONFIG['gc']
            
            # Plot boxplot if selected
            fig, ax = plt.subplots(1, 1, figsize=gc_style_properties['fig_size'])  # type: ignore
            if plot_type == 'boxplot':
                self._box_plot(
                    ax=ax, data=plot_data, x=(first_grping_param, ''), y=kpi_y, hue=kpi_hue, title=kpi_title,
                    ylabel=kpi_ylabel, y_lim=kpi_ylim, style_properties=gc_style_properties,
                )
            # Plot lineplot if selected
            elif plot_type == 'lineplot':
                line_data = (plot_data_full_resolution if not plot_data_full_resolution.empty else plot_data)
                self._line_plot(
                    ax=ax, data=line_data, x=(first_grping_param, ''), y=kpi_y, hue=kpi_hue, title=kpi_title,
                    ylabel=kpi_ylabel, y_lim=kpi_ylim, use_markers=plot_data_full_resolution.empty, style_properties=gc_style_properties,
                )
            # Plot barplot if selected
            elif plot_type == 'barplot':
                self._bar_plot(
                    ax=ax, data=plot_data, x=(first_grping_param, ''), y=kpi_y, hue=kpi_hue, title=kpi_title,
                    ylabel=kpi_ylabel, y_lim=kpi_ylim, stacked=stacked, style_properties=gc_style_properties,
                )
            result_data: pd.DataFrame = line_data if plot_type == 'lineplot' else plot_data  # type: ignore
            logger.debug("GCPlotter.make_plot: figure rendered successfully.")
            return GCPlotResult(fig=fig, plot_data=result_data, kpi_y=kpi_y)
        except Exception:
            logger.error("GCPlotter.make_plot: error making plot", exc_info=True)
            raise PlottingError("GC Plotting failed. Revise your selections and try again!") from None

    def _extract_information(
        self,
        kpi_panel: str,
        kpi_group: str,
        kpi_value: str,
        first_grping_param: str,
        second_grping_param: str,
        sample_time_li: List[Any],
    ) -> Dict[str, Any]:
        """
        Extracts and assembles all necessary data and metadata for generating a GC (Growth Curve) plot.

        This method prepares the filtered data and collects plot parameters, including the y-axis columns,
        axis labels, limits, and grouping information. It supports both 'Benchling' and 'Process' panels and
        handles optional secondary grouping (hue) and time point filtering.

        Args:
            kpi_panel (str): The panel source for KPIs, either 'Benchling' or 'Process'.
            kpi_group (str): The KPI group name (e.g., 'Yield', 'OD600').
            kpi_value (str): Specific KPI value to plot or 'All' for all available.
            first_grping_param (str): The variable to use on the x-axis (e.g., 'Time (h)').
            second_grping_param (str): Secondary grouping/hue parameter, or '---' if none.
            sample_time_li (List[Any]): List of selected time points to filter the data.

        Returns:
            Dict[str, Any]: Dictionary containing:
                - 'data': The filtered data table for selected time points (pd.DataFrame).
                - 'data_full_resolution': The unfiltered, full time-course table (for line plots, pd.DataFrame).
                - 'y': List[Tuple[str, str]] of fully resolved y-axis columns.
                - 'title': Plot title (str).
                - 'ylabel': Y-axis label (str).
                - 'xlim': x-axis limits as a tuple (min, max), optional (Tuple[Optional[float], Optional[float]]).
                - 'ylim': y-axis limits as a tuple (min, max), optional (Tuple[Optional[float], Optional[float]]).
                - 'hue': Name of the secondary grouping variable if specified, else None.

        Raises:
            ValueError: If the specified kpi_panel or kpi_group is not present in the plot properties.
            EmptyTableError: If filtering results in an empty data table (no rows match the time points).
        """
   
        
        # Sanity check
        if kpi_panel not in self._plot_properties:
            logger.warning("GCPlotter._extract_information: panel %r not found in plot_properties.", kpi_panel)
            raise ValueError(f"Panel '{kpi_panel}' not found in plot properties.")
        if kpi_group not in self._plot_properties[kpi_panel]:
            logger.warning(
                "GCPlotter._extract_information: kpi_value %r not found in panel %r.", kpi_value, kpi_panel
            )
            raise ValueError(f"KPI group '{kpi_group}' not found in panel '{kpi_panel}'.")

        # Extract plot properties for the given panel and group
        kpi_props: Dict[str, Any] = self._plot_properties[kpi_panel][kpi_group]

        # Resolve plot metadata
        kpi_ylabel: str = kpi_props['ylabel']
        kpi_xlim: Tuple[Optional[float], Optional[float]] = kpi_props['xlim']
        kpi_ylim: Tuple[Optional[float], Optional[float]] = kpi_props['ylim']
        kpi_title: str = f'{kpi_panel} | {kpi_group}'
        kpi_hue: Optional[str] = second_grping_param if second_grping_param != '---' else None

        # Resolve y-axis columns
        cols: List[str] = kpi_props['cols']
        col_exist: List[bool] = kpi_props['col_exist']
        if kpi_value == 'All':
            y = [col for idx, col in enumerate(cols) if col_exist[idx]]
        else:
            y = [col for idx, col in enumerate(cols) if col == kpi_value and col_exist[idx]]
        resolved_y = [(kpi_panel, col) for col in y]
        logger.debug("GCPlotter._extract_information: resolved y=%r", resolved_y)

        # Resolve data table for all time points of process panel
        if kpi_panel == 'Process' and first_grping_param == 'Time (h)':
            data_full_resolution: pd.DataFrame = self._data.copy()
        else:
            data_full_resolution = pd.DataFrame()

        # Resolve data table for selected time points
        data: pd.DataFrame = self._data[self._data[('Time (h)', '')].isin(sample_time_li)]  # type: ignore
        if data.empty:
            logger.warning("GCPlotter._extract_information: Data table is empty after time point filtering.")
            raise EmptyTableError('Data table is empty.')

        base_cols = [('Exp', ''), ('Tank', ''), (first_grping_param, '')]
        if second_grping_param != '---':
            base_cols.append((second_grping_param, ''))

        def _enrich_and_select(t: pd.DataFrame, add_first_grp: bool = True) -> pd.DataFrame:
            """Enriches table with grouping parameters and selects necessary columns."""
            t = t.copy()
            row_index = pd.MultiIndex.from_arrays([
                t[('Exp', '')].values,
                t[('Tank', '')].values,
            ], names=['Exp', 'Tank'])
            if add_first_grp and first_grping_param != 'Time (h)':
                t[first_grping_param] = self._master_meta_table.loc[row_index, first_grping_param].values  # type: ignore
            if second_grping_param not in ('---', 'Time (h)'):
                t[second_grping_param] = self._master_meta_table.loc[row_index, second_grping_param].values  # type: ignore
            return t[base_cols + resolved_y]  # type: ignore

        plot_data: pd.DataFrame = _enrich_and_select(data)
        if plot_data.empty:
            logger.warning("GCPlotter._extract_information: Plot data is empty.")
            raise EmptyTableError('Plot data is empty.')

        # Resolve plot data for all time points of process panel
        plot_data_full_resolution = _enrich_and_select(data_full_resolution, add_first_grp=False) \
            if not data_full_resolution.empty else pd.DataFrame()

        return {
            'data': plot_data,
            'data_full_resolution': plot_data_full_resolution,
            'y': resolved_y,
            'title': kpi_title,
            'ylabel': kpi_ylabel,
            'xlim': kpi_xlim,
            'ylim': kpi_ylim,
            'hue': kpi_hue,
        }

    @staticmethod
    def _box_plot(
        ax: Optional[matplotlib.axes.Axes] = None,
        data: Optional[pd.DataFrame] = None,
        x: Optional[Tuple[str, str]] = None,
        y: Optional[List[Tuple[str, str]]] = None,
        hue: Optional[str] = None,
        title: Optional[str] = None,
        ylabel: Optional[str] = None,
        y_lim: Optional[Tuple[Optional[float], Optional[float]]] = None,
        style_properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Render a box plot for the Global Comparison tab.

        Plots data grouped by the provided x-axis grouping parameter, for one or more y-axis columns.
        If a 'hue' parameter is provided, data is colored/grouped accordingly.
        Supports both single-column and multi-column y variables; in the multi-column case, values are stacked by sum.

        Args:
            ax (Optional[matplotlib.axes.Axes]): Matplotlib axes object to plot on. Must not be None.
            data (Optional[pd.DataFrame]): DataFrame containing the data to plot. Must not be None.
            x (Optional[Tuple[str, str]]): Column tuple specifying the x-axis grouping parameter. Must not be None.
            y (Optional[List[Tuple[str, str]]]): List of (panel, column) tuples for the y-axis variables. Must not be None.
            hue (Optional[str]): Optional column name for coloring/grouping boxes (will use unique values for palette).
            title (Optional[str]): Plot title (may be displayed by the caller, not this function).
            ylabel (Optional[str]): Y-axis label.
            y_lim (Optional[Tuple[Optional[float], Optional[float]]]): Tuple specifying (min, max) for y-axis limits.
            style_properties (Optional[Dict[str, Any]]): Dictionary containing plot style properties,
                expects keys 'gray_palette' and 'color_palette'.

        Raises:
            ValueError: If required arguments are missing or if the data is empty.

        """
   

        # Sanity check
        if data is None or x is None or y is None or ax is None or style_properties is None:
            logger.warning("GCPlotter._box_plot: Missing required arguments.")
            raise ValueError("GCPlotter._box_plot: Missing required arguments.")

        # Set plot style properties
        gray_palette = style_properties['gray_palette']
        color_palette = style_properties['color_palette']
        
        # Plot boxplot when there is only one y-axis column
        if len(y) == 1:
            ylabel = y[0][1]
            if hue:
                num_hue: int = data[hue].nunique() # type: ignore
                palette = color_palette[:num_hue]
                sns.boxplot(
                    ax=ax, data=data, x=x, y=y[0], hue=hue, dodge='auto', width=0.5, notch=False,
                    showcaps=False, palette=palette, flierprops={"marker": "o", "alpha": 0.5},
                    boxprops={"alpha": 0.5}, medianprops={"linewidth": 2},
                )
            else:
                num_x: int = data[x].nunique() # type: ignore
                palette = [gray_palette[0]] * num_x
                sns.boxplot(
                    ax=ax, data=data, x=x, y=y[0], hue=x, dodge=False, legend=False, width=0.5, notch=False,
                    showcaps=False, palette=palette, flierprops={"marker": "o", "alpha": 0.5},
                    boxprops={"alpha": 0.5}, medianprops={"linewidth": 2},
                )
        # Plot boxplot when there are multiple y-axis columns
        else:
            # Stack the data by summing values of the y-axis columns and call it the 'Total' column
            data_stacked = data.copy()
            data_stacked['Total'] = data[y].sum(axis=1).values # type: ignore
            ylabel = f'Total {ylabel}'
            if hue:
                num_hue: int = data_stacked[hue].nunique() # type: ignore
                palette = color_palette[:num_hue]
                sns.boxplot(
                    ax=ax, data=data_stacked, x=x, y='Total', hue=hue, dodge='auto', width=0.5, notch=False,
                    showcaps=False, palette=palette, flierprops={"marker": "o", "alpha": 0.5},
                    boxprops={"alpha": 0.5}, medianprops={"linewidth": 2},
                )
            else:
                num_x: int = data_stacked[x].nunique() # type: ignore
                palette = [gray_palette[0]] * num_x
                sns.boxplot(
                    ax=ax, data=data_stacked, x=x, y=y[0], hue=x, dodge=False, legend=False, width=0.5,
                    notch=False, showcaps=False, palette=palette, flierprops={"marker": "o", "alpha": 0.5},
                    boxprops={"alpha": 0.5}, medianprops={"linewidth": 2},
                )
        # Set plot title, axes labels, and legend
        ax.set(ylim=y_lim)
        ax.set(title=title)
        ax.set_xlabel(x[0], fontsize=14) # type: ignore
        ax.set_ylabel(ylabel, fontsize=14) # type: ignore
        xticklabels = ax.get_xticklabels()
        num_xticklabels = len(xticklabels)
        max_label_length = max([len(label.get_text()) for label in xticklabels])
        if max_label_length < 5:
            label_rot = 0
        elif max_label_length >= 5 and num_xticklabels < 6:
            label_rot = 45
        else:
            label_rot = 90
        ax.tick_params(axis='x', labelsize=9, labelrotation=label_rot) # type: ignore
        ax.tick_params(axis='y', labelsize=9) # type: ignore
        if hue:
            ax.legend(title=hue, fontsize=9, loc='upper left', bbox_to_anchor=(1.05, 1)) # type: ignore

    @staticmethod
    def _bar_plot(
        ax: Optional[matplotlib.axes.Axes] = None,
        data: Optional[pd.DataFrame] = None,
        x: Optional[Tuple[str, str]] = None,
        y: Optional[List[Tuple[str, str]]] = None,
        hue: Optional[str] = None,
        title: Optional[str] = None,
        ylabel: Optional[str] = None,
        y_lim: Optional[Tuple[Optional[float], Optional[float]]] = None,
        stacked: bool = False,
        style_properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Renders a bar plot for the Global Comparison (GC) panel, supporting standard and stacked bar plots.

        This method plots bar charts to compare groups defined by an x-axis grouping parameter, optionally split and coloured by a secondary "hue" grouping.
        For multi-KPI (multi-y) cases, bars can be stacked (to visualize component totals) or grouped (to show each metric as a separate bar).
        Handles error bars and legend generation automatically according to the provided parameters.

        Args:
            ax (matplotlib.axes.Axes): Matplotlib axes object to plot on.
            data (pd.DataFrame): DataFrame containing pre-aggregated or grouped data for plotting.
            x (Tuple[str, str]): Column tuple for the x-axis grouping parameter (e.g., group/category).
            y (List[Tuple[str, str]]): List of (panel, column) tuples specifying the y-axis metric(s) to plot.
            hue (Optional[str]): Column name for secondary grouping used for colored bars, or None for no hue grouping.
            title (Optional[str]): Title to display above the plot.
            ylabel (Optional[str]): Label for the y-axis.
            y_lim (Optional[Tuple[Optional[float], Optional[float]]]): Tuple for specifying y-axis (min, max) limits.
            stacked (bool): If True, renders stacked bars for multi-component metrics; if False, shows grouped bars or totals.
            style_properties (Dict[str, Any]): Dictionary of plotting style properties (e.g., color palettes).

        Raises:
            ValueError: If required arguments are missing.
        """
   
        # Sanity check
        if data is None or x is None or y is None or ax is None or style_properties is None:
            logger.warning("GCPlotter._bar_plot: Missing required arguments.")
            raise ValueError("GCPlotter._bar_plot: Missing required arguments.")

        # Set plot style properties
        gray_palette = style_properties['gray_palette']
        color_palette = style_properties['color_palette']

        # Plot barplot when there is only one y-axis column
        if len(y) == 1:
            if hue:
                num_hue: int = data[hue].nunique() # type: ignore
                palette = color_palette[:num_hue]
                sns.barplot(
                    ax=ax, data=data.sort_values(x), x=x, y=y[0], hue=hue, dodge='auto', errorbar=('sd', 1),
                    palette=palette, linewidth=1, edgecolor='k',
                )
            else:
                num_x: int = data[x].nunique() # type: ignore
                palette = [gray_palette[0]] * num_x
                sns.barplot(
                    ax=ax, data=data.sort_values(x), x=x, y=y[0], hue=x, dodge='auto', errorbar=('sd', 1),
                    palette=palette, linewidth=1, edgecolor='k', legend=False,
                )
        
        # Plot barplot when there are multiple y-axis columns
        else:
            if stacked:
                grps: Iterable[tuple[Any, pd.DataFrame]] = data.groupby(x) # type: ignore
                means: pd.Series = grps[y].mean(numeric_only=True) # type: ignore
                errors: pd.Series = grps[y].std(ddof=0) # type: ignore
                means.plot.bar(ax=ax, stacked=stacked, yerr=errors, capsize=2, rot=0, linewidth=1, edgecolor='k') # type: ignore
                ax.legend( # type: ignore
                    labels=[' '.join(el[1].split(' ')[:-1]) for el in y],
                    loc='upper left', bbox_to_anchor=(1.05, 1), fontsize=9
                )
                ax.grid(axis='x', linestyle='') # type: ignore
            else:
                data_stacked = data.copy()
                data_stacked['Total'] = data[y].sum(axis=1).values # type: ignore
                ylabel = f'Total {ylabel}'
                num_hue: int = data_stacked[hue].nunique() # type: ignore
                palette = color_palette[:num_hue] if hue else gray_palette
                sns.barplot(
                    ax=ax, data=data_stacked, x=x, y='Total', hue=hue, dodge='auto', errorbar=('sd', 1),
                    palette=palette, linewidth=1, edgecolor='k',
                )
        # Set plot title, axes labels, and legend
        ax.set(ylim=y_lim)
        ax.set(title=title)
        ax.set_xlabel(x[0], fontsize=14) # type: ignore
        ax.set_ylabel(ylabel, fontsize=14) # type: ignore
        xticklabels = ax.get_xticklabels()
        num_xticklabels = len(xticklabels)
        max_label_length = max([len(label.get_text()) for label in xticklabels])
        if max_label_length < 5:
            label_rot = 0
        elif max_label_length >= 5 and num_xticklabels < 6:
            label_rot = 45
        else:
            label_rot = 90
        ax.tick_params(axis='x', labelsize=9, labelrotation=label_rot) # type: ignore
        ax.tick_params(axis='y', labelsize=9) # type: ignore
        if hue:
            ax.legend(title=hue, fontsize=9, loc='upper left', bbox_to_anchor=(1.05, 1)) # type: ignore

    @staticmethod
    def _line_plot(
        ax: Optional[matplotlib.axes.Axes] = None,
        data: Optional[pd.DataFrame] = None,
        x: Optional[Tuple[str, str]] = None,
        y: Optional[List[Tuple[str, str]]] = None,
        hue: Optional[str] = None,
        title: Optional[str] = None,
        ylabel: Optional[str] = None,
        y_lim: Optional[Tuple[Optional[float], Optional[float]]] = None,
        use_markers: bool = True,
        style_properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Plots a lineplot for Global Comparison (GC) analysis, comparing groups or time series.

        This function creates a line plot using the specified x-axis column, one or more y-axis columns,
        and optionally colors/groups the data using a 'hue' category. It supports plotting either a single metric
        or a summed 'Total' line if multiple y-axis columns are specified. Markers can be toggled via the
        `use_markers` argument. Styling and palette options are provided via the `style_properties` dictionary.

        Args:
            ax (Optional[matplotlib.axes.Axes]): The Matplotlib axes object to draw on.
            data (Optional[pd.DataFrame]): Data to plot (columns must match x, y, and optional hue).
            x (Optional[Tuple[str, str]]): Column tuple for the x-axis (e.g., ('Time (h)', '')).
            y (Optional[List[Tuple[str, str]]]): List of y-axis (panel, column) tuples to plot.
            hue (Optional[str]): Column name for coloring/legend grouping; if None, all data plotted as one series.
            title (Optional[str]): The plot title.
            ylabel (Optional[str]): The label for the y-axis.
            y_lim (Optional[Tuple[Optional[float], Optional[float]]]): Tuple for y-axis min/max limits.
            use_markers (bool): Whether to add markers for each data point (default True).
            style_properties (Optional[Dict[str, Any]]): Style/palette/marker settings used for plotting.

        Raises:
            ValueError: If any required argument is missing or if the data is empty.
        """
   
        # Sanity check
        if data is None or x is None or y is None or ax is None or style_properties is None:
            logger.warning("GCPlotter._line_plot: Missing required arguments.")
            raise ValueError("GCPlotter._line_plot: Missing required arguments.")

        # Set plot style properties
        color_palette = style_properties['color_palette']
        gray_palette = style_properties['gray_palette']
        marker: str = style_properties['line_markers'][0] if use_markers else ''

        # Plot lineplot when there is only one y-axis column
        if len(y) == 1:
            plot_y = y[0]
            plot_data = data
        else:
            plot_data = data.copy()
            plot_data['Total'] = data[y].sum(axis=1).values # type: ignore
            plot_y = 'Total'
            ylabel = f'Total {ylabel}'

        if hue:
            n_hues: int = plot_data[hue].nunique() # type: ignore
            if n_hues > len(color_palette):
                logger.warning(
                    "GCPlotter._line_plot: hue cardinality (%d) exceeds configured palette size (%d). "
                    "Generating extended palette.",
                    n_hues, len(color_palette),
                )
                palette = sns.color_palette(palette=style_properties['color_palette_name'], n_colors=n_hues)
            else:
                palette = color_palette[:n_hues]
            sns.lineplot(
                ax=ax, data=plot_data, x=x, y=plot_y, hue=hue, errorbar=('sd', 1), palette=palette,
                marker=marker, dashes=False,
            )
        else:
            sns.lineplot(
                ax=ax, data=plot_data, x=x, y=plot_y, errorbar=('sd', 1), color=gray_palette[0], marker=marker,
            )
        
        # Set plot title, axes labels, and legend
        ax.set(ylim=y_lim)
        ax.set(title=title)
        ax.set_xlabel(x[0], fontsize=14) # type: ignore
        ax.set_ylabel(ylabel, fontsize=14) # type: ignore
        xticklabels = ax.get_xticklabels()
        num_xticklabels = len(xticklabels)
        max_label_length = max([len(label.get_text()) for label in xticklabels])
        if max_label_length < 5:
            label_rot = 0
        elif max_label_length >= 5 and num_xticklabels < 6:
            label_rot = 45
        else:
            label_rot = 90
        ax.tick_params(axis='x', labelsize=9, labelrotation=label_rot) # type: ignore
        ax.tick_params(axis='y', labelsize=9) # type: ignore
        if hue:
            ax.legend(title=hue, fontsize=9, loc='upper left', bbox_to_anchor=(1.05, 1)) # type: ignore
