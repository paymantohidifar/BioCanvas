"""Tests for biocanvas.utils.visualization plotters."""

import copy
import pytest
import pandas as pd

from biocanvas.utils import visualization
from biocanvas.utils import helpers


########################################################
# OLPlotter tests
########################################################


class TestOLPlotterInit:
    """OLPlotter.__init__ stores deep copies of inputs."""

    def test_stores_deep_copies(
        self,
        bench_table_for_ol,
        process_table_for_ol,
        plot_properties_for_ol,
    ):
        # Arrange
        bench = copy.deepcopy(bench_table_for_ol)
        process = copy.deepcopy(process_table_for_ol)

        # Act
        plotter = visualization.OLPlotter(
            {"Ferm": bench, "Process": process},
            plot_properties_for_ol,
        )

        # Assert: mutating original tables does not affect plotter
        bench.loc[0, ("Ferm", "DCW (g/L)")] = 999.0
        process.loc[0, ("Process", "Temperature (°C)")] = 999.0
        assert plotter._plot_tables["Ferm"].loc[0, ("Ferm", "DCW (g/L)")] != 999.0
        assert (
            plotter._plot_tables["Process"].loc[0, ("Process", "Temperature (°C)")]
            != 999.0
        )


class TestOLPlotterExtractInformation:
    """OLPlotter._extract_information returns None or KPI info dict."""

    def test_returns_none_for_unknown_panel(
        self,
        bench_table_for_ol,
        process_table_for_ol,
        plot_properties_for_ol,
    ):
        # Arrange
        plotter = visualization.OLPlotter(
            {"Ferm": bench_table_for_ol, "Process": process_table_for_ol},
            plot_properties_for_ol,
        )

        # Act / Assert
        with pytest.raises(ValueError, match="Panel 'UnknownPanel' not found"):
            plotter._extract_information("UnknownPanel", "Biomass", "DCW (g/L)")

    def test_returns_none_when_no_kpi_columns_exist(
        self,
        bench_table_for_ol,
        process_table_for_ol,
        plot_properties_for_ol,
    ):
        # Arrange: bench plot_properties with col_exist all False
        plot_properties_copy = copy.deepcopy(plot_properties_for_ol)
        plot_properties_copy["Ferm"]["Biomass"]["col_exist"] = [0]
        plotter = visualization.OLPlotter(
            {"Ferm": bench_table_for_ol, "Process": process_table_for_ol},
            plot_properties_copy,
        )

        # Act / Assert: col_exist=0 excludes the column, returning empty y list
        result = plotter._extract_information("Ferm", "Biomass", "DCW (g/L)")
        assert result["y"] == []

    def test_returns_info_dict_when_panel_and_kpi_valid(
        self,
        bench_table_for_ol,
        process_table_for_ol,
        plot_properties_for_ol,
        mocker,
    ):
        # Arrange
        plotter = visualization.OLPlotter(
            {"Ferm": bench_table_for_ol, "Process": process_table_for_ol},
            plot_properties_for_ol,
        )

        # Act
        result = plotter._extract_information("Ferm", "Biomass", "DCW (g/L)")

        # Assert
        assert result is not None
        assert "data" in result
        assert "y" in result
        assert "xlim" in result
        assert "ylim" in result
        assert "ylabel" in result
        assert isinstance(result["data"], pd.DataFrame)
        assert result["y"] == [("Ferm", "DCW (g/L)")]


class TestOLPlotterMakePlots:
    """OLPlotter.make_plots returns None or (fig, kpi1_data, kpi2_data)."""

    def test_returns_none_when_first_kpi_missing(
        self,
        bench_table_for_ol,
        process_table_for_ol,
        plot_properties_for_ol,
    ):

        # Arrange: no bench plot_properties so first KPI cannot be resolved
        plot_properties_copy = copy.deepcopy(plot_properties_for_ol)
        plot_properties_copy["Ferm"] = {}
        plotter = visualization.OLPlotter(
            {"Ferm": bench_table_for_ol, "Process": process_table_for_ol},
            plot_properties_copy,
        )

        # Act / Assert: make_plots wraps ValueError in PlottingError
        with pytest.raises(
            visualization.PlottingError, match="KPI group 'Biomass' not found"
        ):
            plotter.make_plots(
                "Ferm",
                "Biomass",
                "DCW (g/L)",
                "Process",
                "Temperature",
                "Temperature (°C)",
                "Aggregate",
            )

    def test_returns_fig_and_data_when_both_kpis_valid(
        self,
        bench_table_for_ol,
        process_table_for_ol,
        plot_properties_for_ol,
        mocker,
    ):
        # Real Figure/Axes — seaborn.lineplot attaches axis converters and
        # breaks on MagicMock axes. Agg backend keeps this headless.
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        # OLPlotter calls plt.subplots(1, 2, ...) and unpacks into two axes
        fig, axes = plt.subplots(1, 2, figsize=(4.0, 3.0))
        mocker.patch(
            "biocanvas.utils.visualization.plt.subplots", return_value=(fig, axes)
        )
        mocker.patch("biocanvas.utils.visualization.plt.tight_layout")
        mocker.patch("biocanvas.utils.visualization.plt.show")
        plotter = visualization.OLPlotter(
            {"Ferm": bench_table_for_ol, "Process": process_table_for_ol},
            plot_properties_for_ol,
        )

        # Act
        result = plotter.make_plots(
            "Ferm",
            "Biomass",
            "DCW (g/L)",
            "Process",
            "Temperature",
            "Temperature (°C)",
            "Aggregate",
        )

        # Assert: result is an OLPlotterResults NamedTuple with fig and plot_data
        assert result is not None
        assert result.fig is not None
        assert isinstance(result.plot_data, pd.DataFrame)
        assert not result.plot_data.empty
        plt.close(result.fig)


########################################################
# CCPlotter tests
########################################################


class TestCCPlotterInit:
    """CCPlotter.__init__ deep-copies plot_properties so callers cannot mutate the plotter's state."""

    def test_stores_deep_copy_of_plot_properties(
        self,
        plot_properties_for_cc,
    ):
        # Arrange
        props = copy.deepcopy(plot_properties_for_cc)
        original_col_exist = copy.deepcopy(props["Ferm"]["Biomass"]["col_exist"])
        # Act
        plotter = visualization.CCPlotter(
            data=pd.DataFrame(),
            plot_properties=props,
        )

        # Assert: mutating the passed-in dict does not alter the plotter's internal copy
        props["Ferm"]["Biomass"]["col_exist"] = [0]
        assert (
            plotter._plot_properties["Ferm"]["Biomass"]["col_exist"]
            == original_col_exist
        )


class TestCCPlotterExtractInformation:
    """CCPlotter._extract_information validates inputs and assembles multi-condition plot data."""

    def _make_plotter(self, plot_properties, data) -> visualization.CCPlotter:
        return visualization.CCPlotter(
            data=data,
            plot_properties=copy.deepcopy(plot_properties),
        )

    def test_raises_value_error_for_unknown_panel(self, plot_properties_for_cc):
        plotter = self._make_plotter(plot_properties_for_cc, pd.DataFrame())

        with pytest.raises(ValueError, match="Panel 'UnknownPanel' not found"):
            plotter._extract_information(
                kpi_panel="UnknownPanel", kpi_group="Biomass", kpi_value="DCW (g/L)"
            )

    def test_raises_value_error_for_unknown_kpi_group(self, plot_properties_for_cc):
        plotter = self._make_plotter(plot_properties_for_cc, pd.DataFrame())

        with pytest.raises(ValueError, match="KPI group 'UnknownGroup' not found"):
            plotter._extract_information(
                kpi_panel="Ferm", kpi_group="UnknownGroup", kpi_value="DCW (g/L)"
            )

    def test_col_exist_is_not_used_in_column_resolution(
        self, plot_properties_for_cc, update_table_for_cc
    ):
        # col_exist is ignored in the new API; column presence in self._data is the only check
        plot_properties_copy = copy.deepcopy(plot_properties_for_cc)
        plot_properties_copy["Ferm"]["Biomass"]["col_exist"] = [0]
        plotter = self._make_plotter(plot_properties_copy, update_table_for_cc.copy())

        result = plotter._extract_information(
            kpi_panel="Ferm", kpi_group="Biomass", kpi_value="DCW (g/L)"
        )
        assert result["y"] == [("Ferm", "DCW (g/L)")]

    def test_returns_empty_y_when_kpi_value_not_in_data_columns(
        self, plot_properties_for_cc, update_table_for_cc
    ):
        plotter = self._make_plotter(plot_properties_for_cc, update_table_for_cc.copy())

        result = plotter._extract_information(
            kpi_panel="Ferm", kpi_group="Biomass", kpi_value="UnknownMetric"
        )
        assert result["y"] == []

    def test_raises_empty_table_exception_when_data_is_empty(
        self, plot_properties_for_cc, update_table_for_cc
    ):
        # Pass a table with correct columns but zero rows to trigger EmptyTableError
        plotter = self._make_plotter(
            plot_properties_for_cc, update_table_for_cc.head(0)
        )

        with pytest.raises(helpers.EmptyTableError, match="Data table is empty"):
            plotter._extract_information(
                kpi_panel="Ferm", kpi_group="Biomass", kpi_value="DCW (g/L)"
            )

    def test_assembles_plot_data_for_single_kpi_value(
        self, plot_properties_for_cc, update_table_for_cc
    ):
        plotter = self._make_plotter(plot_properties_for_cc, update_table_for_cc.copy())

        result = plotter._extract_information(
            kpi_panel="Ferm", kpi_group="Biomass", kpi_value="DCW (g/L)"
        )

        assert not result["data"].empty
        assert result["y"] == [("Ferm", "DCW (g/L)")]
        assert ("Condition_num", "") in result["data"].columns

    def test_assembles_kpi_y_list_for_all_value(
        self, plot_properties_for_cc, update_table_for_cc
    ):
        plotter = self._make_plotter(plot_properties_for_cc, update_table_for_cc.copy())

        result = plotter._extract_information(
            kpi_panel="Sugar", kpi_group="Growth Substrate", kpi_value="All"
        )

        assert result["y"] == [
            ("Sugar", "Glucose (g/L)"),
            ("Sugar", "Fructose (g/L)"),
            ("Sugar", "Sucrose (g/L)"),
        ]
        assert not result["data"].empty

    def test_returns_all_timepoints_in_data(
        self, plot_properties_for_cc, update_table_for_cc
    ):
        # _extract_information no longer filters by timepoint; all rows are returned
        plotter = self._make_plotter(plot_properties_for_cc, update_table_for_cc.copy())

        result = plotter._extract_information(
            kpi_panel="Ferm", kpi_group="Biomass", kpi_value="DCW (g/L)"
        )
        assert len(result["data"]) == len(update_table_for_cc)


class TestCCPlotterMakePlots:
    """CCPlotter.make_plots returns a CCPlotResult with correct fig/data/kpi_y shape."""

    def _make_plotter(self, plot_properties, data) -> visualization.CCPlotter:
        return visualization.CCPlotter(
            data=data,
            plot_properties=copy.deepcopy(plot_properties),
        )

    def test_returns_none_when_assembled_data_is_empty(
        self, plot_properties_for_cc, update_table_for_cc
    ):
        # Table with correct columns but no rows triggers EmptyTableError → PlottingError
        plotter = self._make_plotter(
            plot_properties_for_cc, update_table_for_cc.head(0)
        )
        with pytest.raises(visualization.PlottingError, match="Data table is empty"):
            plotter.make_plots(
                kpi_panel="Ferm",
                kpi_group="Biomass",
                kpi_value="DCW (g/L)",
                timepoint="All",
                plot_type="aggregate",
            )

    def test_returns_fig_for_line_plot_all_timepoints(
        self, plot_properties_for_cc, update_table_for_cc, mocker
    ):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(1, 1, figsize=(4.0, 3.0))
        mocker.patch(
            "biocanvas.utils.visualization.plt.subplots", return_value=(fig, ax)
        )
        mocker.patch("biocanvas.utils.visualization.plt.show")

        plotter = self._make_plotter(plot_properties_for_cc, update_table_for_cc.copy())

        result = plotter.make_plots(
            kpi_panel="Ferm",
            kpi_group="Biomass",
            kpi_value="DCW (g/L)",
            timepoint="All",
            plot_type="aggregate",
        )

        assert isinstance(result, visualization.CCPlotResult)
        assert result.fig is not None
        assert not result.plot_data.empty
        assert result.kpi_y == [("Ferm", "DCW (g/L)")]
        plt.close(result.fig)

    def test_returns_fig_for_bar_plot_single_timepoint(
        self, plot_properties_for_cc, update_table_for_cc, mocker
    ):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(1, 1, figsize=(4.0, 3.0))
        mocker.patch(
            "biocanvas.utils.visualization.plt.subplots", return_value=(fig, ax)
        )
        mocker.patch("biocanvas.utils.visualization.plt.show")

        plotter = self._make_plotter(plot_properties_for_cc, update_table_for_cc.copy())

        # timepoint=1.0 triggers the bar-plot branch; update_table_for_cc has rows at Time=1.0
        result = plotter.make_plots(
            kpi_panel="Ferm",
            kpi_group="Biomass",
            kpi_value="DCW (g/L)",
            timepoint=1.0,
            plot_type="aggregate",
        )

        assert isinstance(result, visualization.CCPlotResult)
        assert result.fig is not None
        assert not result.plot_data.empty
        plt.close(result.fig)


class TestCCPlotterDrawLines:
    """CCPlotter._draw_lines raises ValueError when multiple y components are requested for time-series."""

    def test_raises_value_error_when_data_x_y_are_none(self):
        with pytest.raises(
            ValueError, match="Missing required information to plot lines."
        ):
            visualization.CCPlotter._plot_lines(
                ax=None,
                data=None,
                x=None,
                y=None,
                title="Test",
                ylabel="g/L",
                x_lim=(None, None),
                y_lim=(None, None),
                marker=True,
                plot_type="aggregate",
            )


########################################################
# GCPlotter tests
########################################################


class TestGCPlotterInit:
    """GCPlotter.__init__ deep-copies plot_properties so callers cannot mutate the plotter's state."""

    def test_stores_deep_copy_of_plot_properties(
        self,
        plot_properties_for_gc,
        master_meta_table_for_gc,
    ):
        # Arrange
        props = copy.deepcopy(plot_properties_for_gc)
        original_col_exist = copy.deepcopy(props["Ferm"]["Biomass"]["col_exist"])

        # Act
        plotter = visualization.GCPlotter(
            data=pd.DataFrame(),
            plot_properties=props,
            master_meta_table=master_meta_table_for_gc,
        )

        # Assert: mutating the passed-in dict does not alter the plotter's internal copy
        props["Ferm"]["Biomass"]["col_exist"] = [0]
        assert (
            plotter._plot_properties["Ferm"]["Biomass"]["col_exist"]
            == original_col_exist
        )


class TestGCPlotterExtractInformation:
    """GCPlotter._extract_information validates inputs and assembles GC plot data."""

    def _make_plotter(
        self, plot_properties, data, master_meta_table
    ) -> visualization.GCPlotter:
        return visualization.GCPlotter(
            data=data,
            plot_properties=copy.deepcopy(plot_properties),
            master_meta_table=master_meta_table,
        )

    def test_raises_value_error_for_unknown_panel(
        self, plot_properties_for_gc, master_meta_table_for_gc
    ):
        plotter = self._make_plotter(
            plot_properties_for_gc, pd.DataFrame(), master_meta_table_for_gc
        )

        with pytest.raises(
            ValueError, match="Panel 'Unknown' not found in plot properties."
        ):
            plotter._extract_information(
                kpi_panel="Unknown",
                kpi_group="Biomass",
                kpi_value="DCW (g/L)",
                first_grping_param="Condition",
                second_grping_param="---",
                sample_time_li=[24.0],
            )

    def test_raises_value_error_for_unknown_kpi_group(
        self, plot_properties_for_gc, master_meta_table_for_gc
    ):
        plotter = self._make_plotter(
            plot_properties_for_gc, pd.DataFrame(), master_meta_table_for_gc
        )

        with pytest.raises(
            ValueError, match="KPI group 'Unknown' not found in panel 'Ferm'."
        ):
            plotter._extract_information(
                kpi_panel="Ferm",
                kpi_group="Unknown",
                kpi_value="DCW (g/L)",
                first_grping_param="Condition",
                second_grping_param="---",
                sample_time_li=[24.0],
            )

    def test_raises_empty_table_exception_when_update_table_returns_empty(
        self,
        plot_properties_for_gc,
        update_table_for_gc,
        master_meta_table_for_gc,
    ):
        # Table with correct columns but zero rows triggers EmptyTableError
        plotter = self._make_plotter(
            plot_properties_for_gc,
            update_table_for_gc.head(0),
            master_meta_table_for_gc,
        )

        with pytest.raises(helpers.EmptyTableError):
            plotter._extract_information(
                kpi_panel="Ferm",
                kpi_group="Biomass",
                kpi_value="DCW (g/L)",
                first_grping_param="Condition",
                second_grping_param="---",
                sample_time_li=[24.0],
            )

    def test_raises_empty_table_exception_when_sample_time_filter_empties_table(
        self,
        plot_properties_for_gc,
        update_table_for_gc,
        master_meta_table_for_gc,
    ):
        plotter = self._make_plotter(
            plot_properties_for_gc, update_table_for_gc.copy(), master_meta_table_for_gc
        )

        with pytest.raises(helpers.EmptyTableError):
            plotter._extract_information(
                kpi_panel="Ferm",
                kpi_group="Biomass",
                kpi_value="DCW (g/L)",
                first_grping_param="Condition",
                second_grping_param="---",
                sample_time_li=[999.0],
            )

    def test_returns_correct_dict_keys_for_bench_selection(
        self,
        plot_properties_for_gc,
        update_table_for_gc,
        master_meta_table_for_gc,
    ):
        plotter = self._make_plotter(
            plot_properties_for_gc, update_table_for_gc.copy(), master_meta_table_for_gc
        )

        result = plotter._extract_information(
            kpi_panel="Ferm",
            kpi_group="Biomass",
            kpi_value="DCW (g/L)",
            first_grping_param="Condition",
            second_grping_param="---",
            sample_time_li=[24.0],
        )

        for key in (
            "data",
            "data_full_resolution",
            "y",
            "title",
            "ylabel",
            "xlim",
            "ylim",
            "hue",
        ):
            assert key in result
        assert result["y"] == [("Ferm", "DCW (g/L)")]
        assert result["title"] == "Ferm | Biomass"
        assert result["ylabel"] == "DCW (g/L)"
        assert not result["data"].empty

    def test_data_full_resolution_is_empty_for_bench_panel(
        self,
        plot_properties_for_gc,
        update_table_for_gc,
        master_meta_table_for_gc,
    ):
        plotter = self._make_plotter(
            plot_properties_for_gc, update_table_for_gc.copy(), master_meta_table_for_gc
        )

        result = plotter._extract_information(
            kpi_panel="Ferm",
            kpi_group="Biomass",
            kpi_value="DCW (g/L)",
            first_grping_param="Time (h)",
            second_grping_param="---",
            sample_time_li=[24.0],
        )

        # Bench panel never produces a full-resolution table
        assert result["data_full_resolution"].empty

    def test_data_full_resolution_is_non_empty_for_process_time_selection(
        self,
        plot_properties_for_gc,
        update_table_for_gc,
        master_meta_table_for_gc,
    ):
        plotter = self._make_plotter(
            plot_properties_for_gc, update_table_for_gc.copy(), master_meta_table_for_gc
        )

        result = plotter._extract_information(
            kpi_panel="Process",
            kpi_group="pH Profile",
            kpi_value="pH",
            first_grping_param="Time (h)",
            second_grping_param="---",
            sample_time_li=[24.0],
        )

        # Full-resolution table contains all time points (8 rows);
        # filtered table contains only the t=24 h rows (4 rows).
        assert not result["data_full_resolution"].empty
        assert len(result["data_full_resolution"]) > len(result["data"])


class TestGCPlotterMakePlot:
    """GCPlotter.make_plot renders a figure and returns a GCPlotResult for all three plot types."""

    def _make_plotter(
        self, plot_properties, data, master_meta_table
    ) -> visualization.GCPlotter:
        return visualization.GCPlotter(
            data=data,
            plot_properties=copy.deepcopy(plot_properties),
            master_meta_table=master_meta_table,
        )

    def test_returns_gc_plot_result_for_boxplot(
        self,
        plot_properties_for_gc,
        update_table_for_gc,
        master_meta_table_for_gc,
        mocker,
    ):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(1, 1, figsize=(4.0, 3.0))
        mocker.patch(
            "biocanvas.utils.visualization.plt.subplots", return_value=(fig, ax)
        )
        mocker.patch("biocanvas.utils.visualization.plt.show")

        plotter = self._make_plotter(
            plot_properties_for_gc, update_table_for_gc.copy(), master_meta_table_for_gc
        )

        result = plotter.make_plot(
            kpi_panel="Ferm",
            kpi_group="Biomass",
            kpi_value="DCW (g/L)",
            first_grping_param="Condition",
            second_grping_param="---",
            sample_time_li=[24.0],
            plot_type="boxplot",
        )

        assert isinstance(result, visualization.GCPlotResult)
        assert result.fig is fig
        assert isinstance(result.plot_data, pd.DataFrame)
        assert result.kpi_y == [("Ferm", "DCW (g/L)")]
        plt.close(fig)

    def test_returns_gc_plot_result_for_barplot(
        self,
        plot_properties_for_gc,
        update_table_for_gc,
        master_meta_table_for_gc,
        mocker,
    ):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(1, 1, figsize=(4.0, 3.0))
        mocker.patch(
            "biocanvas.utils.visualization.plt.subplots", return_value=(fig, ax)
        )
        mocker.patch("biocanvas.utils.visualization.plt.show")

        plotter = self._make_plotter(
            plot_properties_for_gc, update_table_for_gc.copy(), master_meta_table_for_gc
        )

        result = plotter.make_plot(
            kpi_panel="Ferm",
            kpi_group="Biomass",
            kpi_value="DCW (g/L)",
            first_grping_param="Condition",
            second_grping_param="---",
            sample_time_li=[24.0],
            plot_type="barplot",
        )

        assert isinstance(result, visualization.GCPlotResult)
        assert result.fig is fig
        assert not result.plot_data.empty
        plt.close(fig)

    def test_returns_gc_plot_result_for_lineplot_process(
        self,
        plot_properties_for_gc,
        update_table_for_gc,
        master_meta_table_for_gc,
        mocker,
    ):
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(1, 1, figsize=(4.0, 3.0))
        mocker.patch(
            "biocanvas.utils.visualization.plt.subplots", return_value=(fig, ax)
        )
        mocker.patch("biocanvas.utils.visualization.plt.show")

        plotter = self._make_plotter(
            plot_properties_for_gc, update_table_for_gc.copy(), master_meta_table_for_gc
        )

        result = plotter.make_plot(
            kpi_panel="Process",
            kpi_group="pH Profile",
            kpi_value="pH",
            first_grping_param="Time (h)",
            second_grping_param="---",
            sample_time_li=[24.0],
            plot_type="lineplot",
        )

        assert isinstance(result, visualization.GCPlotResult)
        assert result.fig is fig
        # For Process + Time (h) lineplot, result.plot_data is the full-resolution table (8 rows)
        assert len(result.plot_data) == 8
        plt.close(fig)
