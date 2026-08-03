"""Styles of widgets and plots."""

from typing import Dict, Any
import seaborn as sns


# Unique CSS class applied to the root tab widget to namespace all app styles
BIOCANVAS_APP_CLASS = "biocanvas-app"

# Application styling CSS — all selectors scoped under BIOCANVAS_APP_CLASS
APP_CSS = f"""
        <style>
            .jupyter-widgets.widget-tab.{BIOCANVAS_APP_CLASS} > .p-TabBar .p-TabBar-tab {{
                font-size: 12px;
                width: 150px;
                text-align: center;
            }}

            .jupyter-widgets.widget-tab.{BIOCANVAS_APP_CLASS} > .p-TabBar .p-TabBar-tab.p-mod-current {{
                font-size: 12px;
                font-weight: bold;
            }}

            .{BIOCANVAS_APP_CLASS} .widget-accordion .p-accordion-header {{
                font-size: 12px;
                font-weight: normal;
            }}

            .{BIOCANVAS_APP_CLASS} .widget-radio-box {{
                flex-direction: row;
            }}
            .{BIOCANVAS_APP_CLASS} .widget-radio-box label {{
                margin-right: 10px;
            }}
        </style>
        """

# A dictionary for Process Data tab dimensions
PD_TAB_DIM: Dict[str, Any] = {
    "pane_widths": ["350px", "0px", "750px"],
    "pane_heights": ["30px", "800px", "0px"],
    "width": "auto",
    "height": "auto",
    "grid_gap": "30px",
}

# A dictionary for QC Plots tab dimensions
QC_TAB_DIM: Dict[str, Any] = {
    "pane_widths": [1, 0, 0],
    "pane_heights": ["30px", "290px", "600px"],
    "width": "auto",
    "height": "980px",
    "grid_gap": "30px",
}

# A dictionary for KPI Overlap tab dimensions
OL_TAB_DIM: Dict[str, Any] = {
    "pane_widths": ["300px", "1050px", "0px"],
    "pane_heights": ["30px", "650px", "0px"],
    "width": "auto",
    "height": "auto",
    "grid_gap": "30px",
}

# A dictionary for Condition Comparison tab dimensions
CC_TAB_DIM: Dict[str, Any] = {
    "pane_widths": ["300px", "300px", "850px"],
    "pane_heights": ["30px", "600px", "0px"],
    "width": "auto",
    "height": "auto",
    "grid_gap": "30px",
}

# A dictionary for Global Comparison tab dimensions
GC_TAB_DIM: Dict[str, Any] = {
    "pane_widths": ["300px", "300px", "850px"],
    "pane_heights": ["30px", "640px", "0px"],
    "width": "auto",
    "height": "auto",
    "grid_gap": "30px",
}

# A dictionary for Publish Results tab dimensions
PR_TAB_DIM: Dict[str, Any] = {
    "pane_widths": ["280px", "0px", "700px"],
    "pane_heights": ["30px", "200px", "0px"],
    "width": "auto",
    "height": "auto",
    "grid_gap": "30px",
}

# A dictionary for Seaborn styles
SEABORN_STYLES: Dict[str, Dict[str, Any]] = {
    "qc": {  # QC Plot tab
        "style": "whitegrid",
        "rc": {"axes.facecolor": "#FFFAFA", "grid.color": "#C9C9D1"},
    },
    "ol": {  # Overlap KPI
        "style": "white",
        "rc": {"axes.facecolor": "#FFFAFA", "grid.color": "#C9C9D1"},
    },
    "cc": {  # Condition Comparison
        "style": "whitegrid",
        "rc": {"axes.facecolor": "#FFFAFA", "grid.color": "#C9C9D1"},
    },
    "gc": {  # Global Comparison
        "style": "whitegrid",
        "rc": {"axes.facecolor": "#FFFAFA", "grid.color": "#C9C9D1"},
    },
}

# Severity → inline CSS mapping for the Process Data log output widget
LOG_STYLES: Dict[str, str] = {
    "header": "font-weight:bold; font-size:1.05em; border-bottom:1px solid #aaa; padding-bottom:2px; margin-bottom:4px;",
    "success": "color:#2e7d32;",
    "warning": "color:#e65100;",
    "error": "color:#c62828; font-weight:bold;",
    "separator": "border-top:2px solid #555; margin:6px 0;",
}

# A dictionary for plot configurations
PLOT_CONFIG: Dict[str, Dict[str, Any]] = {
    "qc": {  # Configuration for QC Plots
        "fig_size": {  # Figure size
            "one_row": (6, 5),  # One row plots
            "multiple_rows": (6, 6),  # Multiple row plots
        },
        "num_subplot_col": 3,  # Number of subplot columns
        "subplot_wspace": 0.4,  # Width of space between subplots
        "subplot_hspace": 0.4,  # Height of space between subplots
        "colors": sns.color_palette(
            palette="bright", as_cmap=True
        ),  # matplotlib.colors.ListedColormap # type: ignore
        "markers": [
            "o",
            "s",
            "D",
            "^",
            "v",
            ">",
            "<",
            "+",
            "p",
            "*",
            "x",
            "",
        ],  # Acceptable markers
        "marker_size": 9,  # Marker size
    },
    "ol": {  # Configuration for KPI Overlap Plots
        "fig_size": (15, 6),
        "color_palette": sns.color_palette(
            palette="bright", as_cmap=True
        ),  # matplotlib.colors.ListedColormap # type: ignore
        "marker_symbols": [
            "o",
            "s",
            "D",
            "^",
            "v",
            ">",
            "<",
            "+",
            "p",
            "*",
            "x",
            "",
        ],  # Acceptable markers
        "marker_size": 9,  # Marker size
        "line_styles": ["-", "--", ".-"],  # Per-replicate line dash styles
    },
    "cc": {  # Configuration for Condition Comparison plots
        "fig_size": (6, 6),  # Figure size for a single panel
        "color_palette": sns.color_palette(
            palette="bright", n_colors=12
        ),  # Per-condition line colors; multi-KPI bar colors
        "gray_palette": sns.color_palette(
            palette="gray", n_colors=3
        ),  # Single-KPI aggregated bar colors (per replicate)
        "marker_symbols": [
            "o",
            "s",
            "D",
            "^",
            "v",
            ">",
            "<",
            "+",
            "p",
            "*",
            "x",
        ],  # Per-condition marker symbols
        "marker_size": 9,  # Marker size
        "line_styles": ["-", "--", ".-"],  # Per-replicate line dash styles
    },
    "gc": {  # Configuration for Global Comparison plots
        "fig_size": (9, 6),  # Figure size
        "color_palette_name": "bright",  # Palette name used for dynamic extension when hue cardinality > 12
        "color_palette": sns.color_palette(
            palette="bright", n_colors=12
        ),  # Default hue / multi-component bar colors (up to 12 categories)
        "gray_palette": sns.color_palette(
            palette="gray", n_colors=1
        ),  # Single-component bar/box colors
        "line_markers": [
            "o",
            "s",
            "D",
            "^",
            "v",
            ">",
            "<",
            "+",
            "p",
            "*",
        ],  # Per-hue marker symbols for line plots
        "line_styles": [
            "-",
            "--",
            "-.",
            ":",
        ],  # Per-hue line dash styles for line plots
    },
}
