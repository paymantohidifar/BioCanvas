# biocanvas/ui_components.py
"""Per-tab widget containers for the biocanvas App.

Each class builds and owns the ipywidgets for one notebook tab and exposes a
``layout`` attribute (a ``widgets.AppLayout``) that the App assembles into the
top-level Tab.  These classes contain no data or business logic.
"""
import logging
from typing import Iterable, Optional

import ipywidgets as widgets

import biocanvas.styles as styles
from biocanvas.utils import logging_config

logger = logging.getLogger(__name__)


class PDTabWidgets:
    """Widgets for the *Process Data* tab.

    Args:
        project_list_keys: Iterable of project names to populate the dropdown.
        initial_log_level: Optional logging-level integer used to pre-select
            the log-level dropdown value.
    """

    def __init__(
        self,
        project_list_keys: Iterable[str],
        initial_log_level: Optional[int] = None,
    ) -> None:
        keys = list(project_list_keys)

        self.project_dropdown = widgets.Dropdown(
            options=keys,
            value=keys[0],
            description='Project:',
            disabled=False,
            indent=False,
            layout=widgets.Layout(width='85%'),
        )
        self.passcode_box = widgets.Password(
            description='Passcode:',
            placeholder='Enter passcode',
            layout=widgets.Layout(width='85%'),
        )
        _default_log_label = next(
            (k for k, v in logging_config.LOG_LEVEL_MAP.items() if v == initial_log_level),
            "INFO",
        )
        self.log_level_dropdown = widgets.Dropdown(
            options=list(logging_config.LOG_LEVEL_MAP.keys()),
            value=_default_log_label,
            description='Log level:',
            disabled=False,
            layout=widgets.Layout(width='85%'),
        )
        self.connect_button = widgets.Button(
            description="Connect",
            disabled=True,
            button_style='success',
            layout=widgets.Layout(width='170px', height='35px'),
        )
        self.select_all_radio_button = widgets.RadioButtons(
            value='None',
            options=['None', 'All'],
            description='Select:',
            disabled=True,
            layout=widgets.Layout(width='auto'),
        )
        self.exp_checkbox_container = widgets.VBox(
            layout=widgets.Layout(width='90%', height='50%', border='0.1px solid gray')
        )
        self.generate_tables_checkbox = widgets.Checkbox(
            value=False,
            description='<span style="color: #666;">Save processed data tables</span>',
            indent=False,
            layout=widgets.Layout(width='auto'),
        )
        self.process_button = widgets.Button(
            description="Process Data",
            disabled=True,
            button_style='primary',
            layout=widgets.Layout(width='170px', height='35px'),
        )
        self.progress_bar_output = widgets.Output(
            layout=widgets.Layout(width='auto', height='auto', border='0.1px solid gray')
        )
        self.output_label = widgets.Output(
            layout={'width': 'auto', 'height': 'auto', 'border': '0.1px solid gray'}
        )
        self.layout = self._build_layout()

    def _build_layout(self) -> widgets.AppLayout:
        return widgets.AppLayout(
            header=widgets.HTML(
                "<h3>Pull raw data from SharePoint and process it into master tables.</h3>"
            ),
            center=None,
            left_sidebar=widgets.VBox([
                widgets.HTML("<b>Step 1:</b> Select a project and enter the passcode:"),
                self.project_dropdown,
                self.passcode_box,
                self.log_level_dropdown,
                widgets.HTML("<br><b>Step 2:</b> Connect to SharePoint:"),
                self.connect_button,
                widgets.HTML("<br><b>Step 3:</b> Select experiment(s) to process:"),
                self.select_all_radio_button,
                self.exp_checkbox_container,
                widgets.HTML("<br><b>Step 4:</b> Process selected experiments:"),
                self.generate_tables_checkbox,
                self.process_button,
            ]),
            right_sidebar=widgets.VBox([
                self.progress_bar_output,
                self.output_label,
            ]),
            pane_widths=styles.PD_TAB_DIM['pane_widths'],
            pane_heights=styles.PD_TAB_DIM['pane_heights'],
            width=styles.PD_TAB_DIM['width'],
            height=styles.PD_TAB_DIM['height'],
            grid_gap=styles.PD_TAB_DIM['grid_gap'],
        )


class QCTabWidgets:
    """Widgets for the *QC Plots* tab."""

    def __init__(self) -> None:
        self.exp_dropdown = widgets.Dropdown(
            options=[], value=None, description='Experiment:',
            disabled=True, layout={'width': '15%'},
        )
        self.condition_dropdown = widgets.Dropdown(
            options=[], value=None, description='Condition:',
            disabled=True, layout={'width': '15%'},
        )
        self.savefig_checkbox = widgets.Checkbox(
            value=False,
            description='<span style="color: #666;">Save plots</span>',
            disabled=True, indent=False,
            layout=widgets.Layout(width='auto'),
        )
        self.plot_button = widgets.Button(
            description="Plot", disabled=True, button_style='success',
            layout=widgets.Layout(width='170px', height='35px'),
        )
        self.fig_placeholder = widgets.Output(
            layout=widgets.Layout(width='auto', height='auto', border='0.1px solid gray')
        )

        self.layout = self._build_layout()

    def _build_layout(self) -> widgets.AppLayout:
        return widgets.AppLayout(
            header=widgets.HTML(
                "<h3>Generate QC plots for a selected experiment and condition.</h3>"
            ),
            left_sidebar=widgets.VBox(children=[
                widgets.HTML("<b>Step 1: </b> Pick an experiment:"),
                self.exp_dropdown,
                widgets.HTML("<br><b>Step 2: </b> Pick a condition:"),
                self.condition_dropdown,
                widgets.HTML("<br><b>Step 3: </b> Display all plots:"),
                self.savefig_checkbox,
                self.plot_button
            ]),
            footer=widgets.VBox([self.fig_placeholder]),
            pane_widths=styles.QC_TAB_DIM['pane_widths'],
            pane_heights=styles.QC_TAB_DIM['pane_heights'],
            width=styles.QC_TAB_DIM['width'],
            height=styles.QC_TAB_DIM['height'],
            grid_gap=styles.QC_TAB_DIM['grid_gap'],
        )


class OLTabWidgets:
    """Widgets for the *KPI Overlap* tab."""

    def __init__(self) -> None:
        self.exp_dropdown = widgets.Dropdown(
            options=[], value=None, description='Experiment:',
            disabled=True, layout={'width': 'auto'},
        )
        self.condition_dropdown = widgets.Dropdown(
            options=[], value=None, description='Condition:',
            disabled=True, layout={'width': 'auto'},
        )
        self.rep1_checkbox = widgets.Checkbox(
            value=False, description='One', disabled=True, indent=False,
            layout=widgets.Layout(width='auto', padding='1px'),
        )
        self.rep2_checkbox = widgets.Checkbox(
            value=False, description='Two', disabled=True, indent=False,
            layout=widgets.Layout(width='auto', padding='1px'),
        )
        self.rep3_checkbox = widgets.Checkbox(
            value=False, description='Three', disabled=True, indent=False,
            layout=widgets.Layout(width='auto', padding='1px'),
        )
        self.kpi1_group_dropdown = widgets.Dropdown(
            options=[], value=None, description='KPI 1 Group:',
            disabled=True, layout={'width': 'auto'},
        )
        self.kpi1_value_dropdown = widgets.Dropdown(
            options=[], value=None, description='KPI 1 Value:',
            disabled=True, layout={'width': 'auto'},
        )
        self.kpi2_group_dropdown = widgets.Dropdown(
            options=[], value=None, description='KPI 2 Group:',
            disabled=True, layout={'width': 'auto'},
        )
        self.kpi2_value_dropdown = widgets.Dropdown(
            options=[], value=None, description='KPI 2 Value:',
            disabled=True, layout={'width': 'auto'},
        )
        self.plot_type_radio_buttons = widgets.RadioButtons(
            options=['Aggregate', 'Individual'], description='Plot type:',
            disabled=True, layout=widgets.Layout(width='auto'),
        )
        self.verbose_data_checkbox = widgets.Checkbox(
            value=False,
            description='<span style="color: #666;">Show raw data table</span>',
            disabled=True, indent=False, layout=widgets.Layout(width='auto'),
        )
        self.verbose_stats_checkbox = widgets.Checkbox(
            value=False,
            description='<span style="color: #666;">Show statistics tables</span>',
            disabled=True, indent=False, layout=widgets.Layout(width='auto'),
        )
        self.savefig_stats_checkbox = widgets.Checkbox(
            value=False,
            description='<span style="color: #666;">Save plot and raw data table</span>',
            disabled=True, indent=False, layout=widgets.Layout(width='auto'),
        )
        self.plot_button = widgets.Button(
            description='Plot', disabled=True, button_style='success',
            layout=widgets.Layout(width='170px', height='35px'),
        )
        self.fig_placeholder = widgets.Output(
            layout=widgets.Layout(width='auto', height='auto', border='0.1px solid gray')
        )
        self.verbose_data_placeholder = widgets.Output(
            layout=widgets.Layout(width='auto', height='auto', border='0.1px solid gray')
        )

        self.layout = self._build_layout()

    def _build_layout(self) -> widgets.AppLayout:
        return widgets.AppLayout(
            header=widgets.HTML(
                "<h3>Overlay two KPIs over time for a selected experiment and condition.</h3>"
            ),
            left_sidebar=widgets.VBox(children=[
                widgets.HTML("<b>Step 1: </b> Pick an experiment:"),
                self.exp_dropdown,
                widgets.HTML("<br><b>Step 2: </b> Pick a condition:"),
                self.condition_dropdown,
                widgets.HTML(
                    "<br><b>Step 3: </b> Pick replicates/tanks for selected condition:"
                ),
                widgets.HBox(
                    children=[
                        widgets.HTML('Replicate/Tank:'),
                        self.rep1_checkbox,
                        self.rep2_checkbox,
                        self.rep3_checkbox,
                    ],
                    layout=widgets.Layout(width='auto'),
                ),
                widgets.HTML("<br><b>Step 4: </b> Pick two KPIs:"),
                self.kpi1_group_dropdown,
                self.kpi1_value_dropdown,
                self.kpi2_group_dropdown,
                self.kpi2_value_dropdown,
                widgets.HTML("<br><b>Step 5: </b> Display plot:"),
                self.plot_type_radio_buttons,
                self.verbose_data_checkbox,
                self.savefig_stats_checkbox,
                self.plot_button,
            ]),
            center=widgets.VBox([
                self.fig_placeholder,
                self.verbose_data_placeholder,
            ]),
            pane_widths=styles.OL_TAB_DIM['pane_widths'],
            pane_heights=styles.OL_TAB_DIM['pane_heights'],
            width=styles.OL_TAB_DIM['width'],
            height=styles.OL_TAB_DIM['height'],
            grid_gap=styles.OL_TAB_DIM['grid_gap'],
        )


class CCTabWidgets:
    """Widgets for the *Condition Comparison* tab."""

    def __init__(self) -> None:
        self.exp_dropdown = widgets.Dropdown(
            options=[], value=None, description='Experiment:',
            disabled=True, layout={'width': 'auto'},
        )
        self.condition_replicate_checkbox_container = widgets.VBox(
            layout=widgets.Layout(width='100%', height='70%', border='0.1px solid gray')
        )
        self.kpi_group_dropdown = widgets.Dropdown(
            options=[], value=None, description='KPI Group:',
            disabled=True, layout={'width': 'auto'},
        )
        self.kpi_value_dropdown = widgets.Dropdown(
            options=[], value=None, description='KPI Value:',
            disabled=True, layout={'width': 'auto'},
        )
        self.sample_time_dropdown = widgets.Dropdown(
            options=[], value=None, description='Timepoint (h):',
            disabled=True, layout={'width': 'auto'},
        )
        self.plot_type_radio_buttons = widgets.RadioButtons(
            options=['Aggregate', 'Individual'], description='Plot type:',
            disabled=True, layout=widgets.Layout(width='auto'),
        )
        self.stacked_plot_checkbox = widgets.Checkbox(
            value=False,
            description='<span style="color: #666;">Stack Y-axis on barplot</span>',
            disabled=True, indent=False, layout=widgets.Layout(width='auto'),
        )
        self.verbose_data_checkbox = widgets.Checkbox(
            value=False,
            description='<span style="color: #666;">Show raw data table</span>',
            disabled=True, indent=False, layout=widgets.Layout(width='auto'),
        )
        self.verbose_stats_checkbox = widgets.Checkbox(
            value=False,
            description='<span style="color: #666;">Show statistics tables</span>',
            disabled=True, indent=False, layout=widgets.Layout(width='auto'),
        )
        self.savefig_stats_checkbox = widgets.Checkbox(
            value=False,
            description=(
                '<span style="color: #666;">'
                'Save plot, raw data, and statistics tables</span>'
            ),
            disabled=True, indent=False, layout=widgets.Layout(width='auto'),
        )
        self.plot_button = widgets.Button(
            description="Plot", disabled=True, button_style='success',
            layout=widgets.Layout(width='170px', height='35px'),
        )
        self.fig_placeholder = widgets.Output(
            layout=widgets.Layout(width='auto', height='auto', border='0.1px solid gray')
        )
        self.verbose_data_placeholder = widgets.Output(
            layout=widgets.Layout(width='auto', height='auto', border='0.1px solid gray')
        )
        self.verbose_stats_placeholder = widgets.Output(
            layout=widgets.Layout(width='auto', height='auto', border='0.1px solid gray')
        )

        self.layout = self._build_layout()

    def _build_layout(self) -> widgets.AppLayout:
        return widgets.AppLayout(
            header=widgets.HTML(
                "<h3>Compare a KPI across conditions and replicates.</h3>"
            ),
            left_sidebar=widgets.VBox([
                widgets.HTML("<b>Step 1: </b> Pick an experiment:"),
                self.exp_dropdown,
                widgets.HTML(
                    "<br><b>Step 2:</b> Pick condition(s) & replicate(s)/tank(s):"
                ),
                self.condition_replicate_checkbox_container,
            ]),
            center=widgets.VBox([
                widgets.HTML("<b>Step 3:</b> Pick a KPI:"),
                self.kpi_group_dropdown,
                self.kpi_value_dropdown,
                widgets.HTML("<br><b>Step 4:</b> Pick a timepoint:"),
                self.sample_time_dropdown,
                widgets.HTML("<br><b>Step 5:</b> Display plot:"),
                self.plot_type_radio_buttons,
                self.stacked_plot_checkbox,
                widgets.HTML("<br>"),
                self.verbose_data_checkbox,
                self.verbose_stats_checkbox,
                self.savefig_stats_checkbox,
                self.plot_button,
            ]),
            right_sidebar=widgets.VBox([
                self.fig_placeholder,
                self.verbose_data_placeholder,
                self.verbose_stats_placeholder,
            ]),
            pane_widths=styles.CC_TAB_DIM['pane_widths'],
            pane_heights=styles.CC_TAB_DIM['pane_heights'],
            width=styles.CC_TAB_DIM['width'],
            height=styles.CC_TAB_DIM['height'],
            grid_gap=styles.CC_TAB_DIM['grid_gap'],
        )


class GCTabWidgets:
    """Widgets for the *Global Comparison* tab."""

    def __init__(self) -> None:
        self.filter_accordion = widgets.Accordion(
            layout=widgets.Layout(
                width='auto', height='auto',
                padding='10px 10px 10px 10px', align_items='initial',
            )
        )
        self.kpi_group_dropdown = widgets.Dropdown(
            options=[], value=None, description='KPI Group:',
            disabled=True, layout={'width': 'auto'},
        )
        self.kpi_value_dropdown = widgets.Dropdown(
            options=[], value=None, description='KPI Value:',
            disabled=True, layout={'width': 'auto'},
        )
        self.first_grping_param_dropdown = widgets.Dropdown(
            options=[], value=None, description='X-axis Param:',
            disabled=True, layout={'width': 'auto'},
        )
        self.second_grping_param_dropdown = widgets.Dropdown(
            options=[], value=None, description='Hue Param:',
            disabled=True, layout={'width': 'auto'},
        )
        self.plot_type_radio_button = widgets.RadioButtons(
            options=['Barplot', 'Boxplot'], description='Plot type:',
            disabled=True, layout=widgets.Layout(width='auto'),
        )
        self.plot_button = widgets.Button(
            description="Plot", disabled=True, button_style='success',
            layout=widgets.Layout(width='170px', height='35px'),
        )
        self.reset_filters_button = widgets.Button(
            description="Reset Filters", disabled=True, button_style='primary',
            layout=widgets.Layout(width='170px', height='35px'),
        )
        self.stacked_plot_checkbox = widgets.Checkbox(
            value=False,
            description='<span style="color: #666;">Stack Y-axis on barplot</span>',
            disabled=True, indent=False, layout=widgets.Layout(width='auto'),
        )
        self.verbose_data_checkbox = widgets.Checkbox(
            value=False,
            description='<span style="color: #666;">Show raw data table</span>',
            disabled=True, indent=False, layout=widgets.Layout(width='auto'),
        )
        self.verbose_stats_checkbox = widgets.Checkbox(
            value=False,
            description='<span style="color: #666;">Show statistics tables</span>',
            disabled=True, indent=False, layout=widgets.Layout(width='auto'),
        )
        self.savefig_stats_checkbox = widgets.Checkbox(
            value=False,
            description=(
                '<span style="color: #666;">'
                'Save plot, raw data, and statistics tables</span>'
            ),
            disabled=True, indent=False, layout=widgets.Layout(width='auto'),
        )
        self.fig_placeholder = widgets.Output(
            layout=widgets.Layout(width='auto', height='auto', border='0.1px solid gray')
        )
        self.verbose_data_placeholder = widgets.Output(
            layout=widgets.Layout(width='auto', height='auto', border='0.1px solid gray')
        )
        self.verbose_stats_placeholder = widgets.Output(
            layout=widgets.Layout(width='auto', height='auto', border='0.1px solid gray')
        )

        self.layout = self._build_layout()

    def _build_layout(self) -> widgets.AppLayout:
        return widgets.AppLayout(
            header=widgets.HTML(
                "<h3>Compare a KPI across experiments with optional grouping and filters.</h3>"
            ),
            left_sidebar=widgets.VBox([
                widgets.HTML("<b>Step 1: </b> Select filters:"),
                widgets.HTML(
                    '<span style="color:gray; font-size: 12px; text-align: center;">'
                    'Hold Ctrl to select/deselect multiple values</span>'
                ),
                self.filter_accordion,
            ]),
            center=widgets.VBox([
                widgets.HTML("<b>Step 2:</b> Pick a KPI:"),
                self.kpi_group_dropdown,
                self.kpi_value_dropdown,
                widgets.HTML("<br><b>Step 3:</b> Pick first grouping parameter on X-axis:"),
                self.first_grping_param_dropdown,
                widgets.HTML("<br><b>Step 4:</b> Pick second grouping parameter (optional):"),
                self.second_grping_param_dropdown,
                widgets.HTML("<br><b>Step 5:</b> Display plot:"),
                self.plot_type_radio_button,
                self.stacked_plot_checkbox,
                widgets.HTML("<br>"),
                self.verbose_data_checkbox,
                self.verbose_stats_checkbox,
                self.savefig_stats_checkbox,
                widgets.HBox([self.plot_button, self.reset_filters_button]),
            ]),
            right_sidebar=widgets.VBox([
                self.fig_placeholder,
                self.verbose_data_placeholder,
                self.verbose_stats_placeholder,
            ]),
            pane_widths=styles.GC_TAB_DIM['pane_widths'],
            pane_heights=styles.GC_TAB_DIM['pane_heights'],
            width=styles.GC_TAB_DIM['width'],
            height=styles.GC_TAB_DIM['height'],
            grid_gap=styles.GC_TAB_DIM['grid_gap'],
        )


class PRTabWidgets:
    """Widgets for the *Publish Results* tab."""

    def __init__(self) -> None:
        self.publish_report_button = widgets.Button(
            description="Publish Report", disabled=True, button_style='success',
            layout=widgets.Layout(width='170px', height='35px'),
        )
        self.zip_results_button = widgets.Button(
            description="Zip Results", disabled=True, button_style='primary',
            layout=widgets.Layout(width='170px', height='35px'),
        )
        self.output_label = widgets.Output(
            layout={'width': 'auto', 'height': '100%', 'border': '0.1px solid gray'}
        )

        self.layout = self._build_layout()

    def _build_layout(self) -> widgets.AppLayout:
        return widgets.AppLayout(
            header=widgets.HTML(
                "<h3>Consolidate saved figures and data into a shareable report.</h3>"
            ),
            left_sidebar=widgets.VBox([
                widgets.HTML("<b>Step 1: </b> Publish results as a consolidated report:"),
                self.publish_report_button,
                widgets.HTML("<br><b>Step 2: </b> Zip results files:"),
                self.zip_results_button,
            ]),
            right_sidebar=widgets.VBox([
                widgets.HTML("Status:"),
                self.output_label,
            ]),
            pane_widths=styles.PR_TAB_DIM['pane_widths'],
            pane_heights=styles.PR_TAB_DIM['pane_heights'],
            height=styles.PR_TAB_DIM['height'],
            width=styles.PR_TAB_DIM['width'],
            grid_gap=styles.PR_TAB_DIM['grid_gap'],
        )
