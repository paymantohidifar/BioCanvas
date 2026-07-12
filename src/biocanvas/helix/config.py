# biocanvas/helix/config.py
"""Configuration loader for Project Helix.

All user-editable values live in config.yaml (same directory).
This module loads that file and builds the derived structures expected by core.py.
To add a new substrate or change plot limits, edit config.yaml only.

Environment variables
---------------------
BIOCANVAS_PROFILE
    Set to any non-empty value to enable cProfile instrumentation on methods
    decorated with ``@helpers.profile_method``.  Output is emitted at DEBUG
    level via the module logger.  Unset (default) → zero-overhead passthrough.

Column-naming contract (read-only — do not edit here)
------------------------------------------------------
These patterns govern how raw Benchling column names are constructed from the
substrate, product, and enzyme-assay lists defined in config.yaml.  They are
used by ``bench_plot_properties`` to build column lists automatically — any
new entry added to a list in config.yaml propagates here with no changes to
core.py or utils/ required.

    Growth substrate : "{substrate} (g/L)"
    Inducer substrate: "{inducer} (g/L)"
    Product titer    : "{product} Titer (g/L)"
    Product sp. titer: "{product} Sp. Titer (g/g)"
    Product rate     : "{product} Rate (g/L/h)"
    Product ins. rate: "{product} Ins. Rate (g/L/h)"
    Product weight   : "{product} Weight (g)"
    Product yield    : "{product} Yield (g/g)"
    Enzyme assay     : "{assay} Activity (umoles/g/s)"
"""
import yaml
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

# ---------------------------------------------------------------------------
# Load raw config values from YAML
# ---------------------------------------------------------------------------
_cfg: Dict[str, Any] = yaml.safe_load((Path(__file__).parent / 'config.yaml').read_text())

# ---------------------------------------------------------------------------
# Project identity
# ---------------------------------------------------------------------------
PROJECT_NAME: str = _cfg['project_name']
PROJECT_VERSION: str = f"{PROJECT_NAME.split()[1].lower()}-v{_cfg['version']}"
SHAREPOINT_DATA_DIR: str = _cfg['sharepoint_data_dir']

# ---------------------------------------------------------------------------
# Panel display names
# Maps each benchling.py class name (= raw panel name from filename) to a
# human-readable label.  All exported dicts that are keyed by panel name
# (bench_plot_properties, CARBON_PANELS, PANELS_FOR_TRY, BENCHLING_PANELS)
# use display names so that callers never need to know the raw class names.
# bench_ylims lookups via _bench_ylim() are unaffected — they look up
# _cfg['bench_ylims'] directly using raw class names.
# ---------------------------------------------------------------------------
PANEL_DISPLAY_NAMES: Dict[str, str] = dict(_cfg['panel_display_names'])

# ---------------------------------------------------------------------------
# Benchling panels
# ---------------------------------------------------------------------------
BENCHLING_PANELS: Tuple[str, ...] = tuple( # type: ignore
    PANEL_DISPLAY_NAMES.get(p, p) for p in _cfg['benchling_panels'] 
) 

# ---------------------------------------------------------------------------
# Substrates
# ---------------------------------------------------------------------------
GROWTH_CARB_SUBST: Tuple[str, ...] = tuple(_cfg['growth_carb_subst'])
GROWTH_NITRO_SUBST: Tuple[str, ...] = tuple(_cfg['growth_nitro_subst'])
GROWTH_PHOSPH_SUBST: Tuple[str, ...] = tuple(_cfg['growth_phosph_subst'])
GROWTH_SULPH_SUBST: Tuple[str, ...] = tuple(_cfg['growth_sulph_subst'])
INDUCER_SUBST: Tuple[str, ...] = tuple(_cfg['inducer_subst'])

# ---------------------------------------------------------------------------
# Metabolites
# ---------------------------------------------------------------------------
BYPRODUCTS: Tuple[str, ...] = tuple(_cfg['byproducts'])
INTERMEDIATES: Tuple[str, ...] = tuple(_cfg['intermediates'])
PRODUCTS: Tuple[str, ...] = tuple(_cfg['products'])

# ---------------------------------------------------------------------------
# Enzyme activity assays
# ---------------------------------------------------------------------------
ENZYME_ASSAYS: Tuple[str, ...] = tuple(_cfg['enzyme_assays'])

# ---------------------------------------------------------------------------
# Derived structures — computed from the constants above so that a single
# change to a substrate list propagates everywhere automatically.
# ---------------------------------------------------------------------------
CARBON_PANELS: Dict[str, Tuple[str, ...]] = {
    PANEL_DISPLAY_NAMES.get('Sugar', 'Sugar'):    GROWTH_CARB_SUBST + INDUCER_SUBST,
    PANEL_DISPLAY_NAMES.get('Disacch', 'Disacch'): INDUCER_SUBST,
}

PANELS_FOR_TRY: Dict[str, Tuple[str, ...]] = {
    PANEL_DISPLAY_NAMES.get('Alpha', 'Alpha'): PRODUCTS,
    PANEL_DISPLAY_NAMES.get('Aaa', 'Aaa'):     PRODUCTS,
    PANEL_DISPLAY_NAMES.get('Lcuv', 'Lcuv'):   PRODUCTS,
    PANEL_DISPLAY_NAMES.get('Brad', 'Brad'):    PRODUCTS,
}

# Final processed table columns
FINAL_BENCHLING_COLS: Tuple[str, ...] = ('Exp', 'Tank', 'Replicate', 'Time (h)') + BENCHLING_PANELS[1:]
FINAL_PROCESS_COLS: Tuple[str, ...] = tuple(_cfg['final_process_cols'])

# ---------------------------------------------------------------------------
# Global comparison plot keys
# ---------------------------------------------------------------------------
GLOBAL_FILTER_KEYS: Tuple[str, ...] = tuple(_cfg['global_filter_keys'])
GLOBAL_GROUP_KEYS: Tuple[str, ...] = tuple(_cfg['global_group_keys'])

# ---------------------------------------------------------------------------
# Helpers for building plot properties
# ---------------------------------------------------------------------------

def _bench_ylim(panel: str, kpi: str) -> Tuple[Optional[float], Optional[float]]:
    """Returns the configured y-axis limit for a bench plot KPI group.

    Falls back to (0, None) if no override is specified in config.yaml.
    """
    raw = _cfg.get('bench_ylims', {}).get(panel, {}).get(kpi)
    if raw is None:
        return (0, None)
    return (raw[0], raw[1])


def _process_ylim(kpi: str) -> Tuple[Optional[float], Optional[float]]:
    """Returns the configured y-axis limit for a process plot KPI group.

    Falls back to (0, None) if no override is specified in config.yaml.
    """
    raw = _cfg.get('process_ylims', {}).get(kpi)
    if raw is None:
        return (0, None)
    return (raw[0], raw[1])


def _ylabel(items: Tuple[str, ...], suffix: str) -> str:
    """Returns '{item} {suffix}' when the list has exactly one element, else '{suffix}'.

    Produces a specific axis label when only one analyte or product is tracked
    (e.g. 'Glucose Titer (g/L)') and a generic label when there are several
    (e.g. 'Titer (g/L)').
    """
    return f"{items[0]} {suffix}" if len(items) == 1 else suffix


# ---------------------------------------------------------------------------
# Bench plot properties
# Derived column name lists are built from the substrate / product tuples so
# that adding a new entry to (e.g.) PRODUCTS propagates here automatically.
# ---------------------------------------------------------------------------
bench_plot_properties: Dict[str, Dict[str, Dict[str, Any]]] = {
    PANEL_DISPLAY_NAMES.get('Ferm', 'Ferm'): {
        'Biomass': {
            'cols': ['DCW (g/L)'],
            'ylabel': 'DCW (g/L)',
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0],
        },
        'IS (%)': {
            'cols': ['% Insoluble Solids (g/g)'],
            'ylabel': 'Insoluble Solids (%)',
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0],
        },
    },
    PANEL_DISPLAY_NAMES.get('Sugar', 'Sugar'): {
        'Growth Substrate': {
            'cols': [f'{el} (g/L)' for el in GROWTH_CARB_SUBST],
            'ylabel': _ylabel(GROWTH_CARB_SUBST, 'Titer (g/L)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(GROWTH_CARB_SUBST),
        },
        'Inducer Substrate': {
            'cols': [f'{el} (g/L)' for el in INDUCER_SUBST],
            'ylabel': _ylabel(INDUCER_SUBST, 'Titer (g/L)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(INDUCER_SUBST),
        },
    },
    PANEL_DISPLAY_NAMES.get('Disacch', 'Disacch'): {
        'Inducer Substrate': {
            'cols': [f'{el} (g/L)' for el in INDUCER_SUBST],
            'ylabel': _ylabel(INDUCER_SUBST, 'Titer (g/L)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(INDUCER_SUBST),
        },
    },
    PANEL_DISPLAY_NAMES.get('Acids', 'Acids'): {
        'Byproducts': {
            'cols': [f'{el} (g/L)' for el in BYPRODUCTS],
            'ylabel': _ylabel(BYPRODUCTS, 'Titer (g/L)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(BYPRODUCTS),
        },
    },
    PANEL_DISPLAY_NAMES.get('Ammonia', 'Ammonia'): {
        'Nitrogen Source': {
            'cols': [f'{el} (g/L)' for el in GROWTH_NITRO_SUBST],
            'ylabel': _ylabel(GROWTH_NITRO_SUBST, 'Titer (g/L)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(GROWTH_NITRO_SUBST),
        },
    },
    PANEL_DISPLAY_NAMES.get('Phs', 'Phs'): {
        'Phosphate Source': {
            'cols': [f'{el} (g/L)' for el in GROWTH_PHOSPH_SUBST],
            'ylabel': _ylabel(GROWTH_PHOSPH_SUBST, 'Titer (g/L)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(GROWTH_PHOSPH_SUBST),
        },
        'Sulfate Source': {
            'cols': [f'{el} (g/L)' for el in GROWTH_SULPH_SUBST],
            'ylabel': _ylabel(GROWTH_SULPH_SUBST, 'Titer (g/L)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(GROWTH_SULPH_SUBST),
        },
    },
    PANEL_DISPLAY_NAMES.get('Alpha', 'Alpha'): {
        'Growth Substrate': {
            'cols': [f'{el} (g/L)' for el in GROWTH_CARB_SUBST],
            'ylabel': _ylabel(GROWTH_CARB_SUBST, 'Titer (g/L)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(GROWTH_CARB_SUBST),
        },
        'Inducer Substrate': {
            'cols': [f'{el} (g/L)' for el in INDUCER_SUBST],
            'ylabel': _ylabel(INDUCER_SUBST, 'Titer (g/L)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(INDUCER_SUBST),
        },
        'Product Titer': {
            'cols': [f'{el} Titer (g/L)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Titer (g/L)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Sp. Titer': {
            'cols': [f'{el} Sp. Titer (g/g)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Sp. Titer (g/g)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Rate': {
            'cols': [f'{el} Rate (g/L/h)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Rate (g/L/h)'),
            'xlim': (0, None),
            'ylim': _bench_ylim('Alpha', 'Product Rate'),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Ins. Rate': {
            'cols': [f'{el} Ins. Rate (g/L/h)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Ins. Rate (g/L/h)'),
            'xlim': (0, None),
            'ylim': _bench_ylim('Alpha', 'Product Ins. Rate'),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Weight': {
            'cols': [f'{el} Weight (g)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Weight (g)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Yield': {
            'cols': [f'{el} Yield (g/g)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Yield (g/g)'),
            'xlim': (0, None),
            'ylim': _bench_ylim('Alpha', 'Product Yield'),
            'col_exist': [0] * len(PRODUCTS),
        },
    },
    PANEL_DISPLAY_NAMES.get('Aaa', 'Aaa'): {
        'Product Titer': {
            'cols': [f'{el} Titer (g/L)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Titer (g/L)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Sp. Titer': {
            'cols': [f'{el} Sp. Titer (g/g)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Sp. Titer (g/g)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Rate': {
            'cols': [f'{el} Rate (g/L/h)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Rate (g/L/h)'),
            'xlim': (0, None),
            'ylim': _bench_ylim('Aaa', 'Product Rate'),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Ins. Rate': {
            'cols': [f'{el} Ins. Rate (g/L/h)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Ins. Rate (g/L/h)'),
            'xlim': (0, None),
            'ylim': _bench_ylim('Aaa', 'Product Ins. Rate'),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Weight': {
            'cols': [f'{el} Weight (g)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Weight (g)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Yield': {
            'cols': [f'{el} Yield (g/g)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Yield (g/g)'),
            'xlim': (0, None),
            'ylim': _bench_ylim('Aaa', 'Product Yield'),
            'col_exist': [0] * len(PRODUCTS),
        },
    },
    PANEL_DISPLAY_NAMES.get('Lcuv', 'Lcuv'): {
        'Product Titer': {
            'cols': [f'{el} Titer (g/L)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Titer (g/L)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Sp. Titer': {
            'cols': [f'{el} Sp. Titer (g/g)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Sp. Titer (g/g)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Rate': {
            'cols': [f'{el} Rate (g/L/h)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Rate (g/L/h)'),
            'xlim': (0, None),
            'ylim': _bench_ylim('Lcuv', 'Product Rate'),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Ins. Rate': {
            'cols': [f'{el} Ins. Rate (g/L/h)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Ins. Rate (g/L/h)'),
            'xlim': (0, None),
            'ylim': _bench_ylim('Lcuv', 'Product Ins. Rate'),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Weight': {
            'cols': [f'{el} Weight (g)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Weight (g)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Yield': {
            'cols': [f'{el} Yield (g/g)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Yield (g/g)'),
            'xlim': (0, None),
            'ylim': _bench_ylim('Lcuv', 'Product Yield'),
            'col_exist': [0] * len(PRODUCTS),
        },
    },
    PANEL_DISPLAY_NAMES.get('Brad', 'Brad'): {
        'Product Titer': {
            'cols': [f'{el} Titer (g/L)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Titer (g/L)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Sp. Titer': {
            'cols': [f'{el} Sp. Titer (g/g)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Sp. Titer (g/g)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Rate': {
            'cols': [f'{el} Rate (g/L/h)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Rate (g/L/h)'),
            'xlim': (0, None),
            'ylim': _bench_ylim('Brad', 'Product Rate'),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Ins. Rate': {
            'cols': [f'{el} Ins. Rate (g/L/h)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Ins. Rate (g/L/h)'),
            'xlim': (0, None),
            'ylim': _bench_ylim('Brad', 'Product Ins. Rate'),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Weight': {
            'cols': [f'{el} Weight (g)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Weight (g)'),
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(PRODUCTS),
        },
        'Product Yield': {
            'cols': [f'{el} Yield (g/g)' for el in PRODUCTS],
            'ylabel': _ylabel(PRODUCTS, 'Yield (g/g)'),
            'xlim': (0, None),
            'ylim': _bench_ylim('Brad', 'Product Yield'),
            'col_exist': [0] * len(PRODUCTS),
        },
    },
    PANEL_DISPLAY_NAMES.get('Biochem', 'Biochem'): {
        'Product Activity': {
            'cols': [f'{el} Activity (umoles/g/s)' for el in ENZYME_ASSAYS],
            'ylabel': 'Enzyme Activity (umoles/g/s)',
            'xlim': (0, None),
            'ylim': (0, None),
            'col_exist': [0] * len(ENZYME_ASSAYS),
        },
    },
}

# ---------------------------------------------------------------------------
# Process plot properties (fully static — all values from YAML or literals)
# ---------------------------------------------------------------------------
process_plot_properties: Dict[str, Dict[str, Dict[str, Any]]] = {
    'Process': {
        'Temperature': {
            'cols': ['Temperature (°C)'],
            'ylabel': 'Temperature (°C)',
            'xlim': (0, None),
            'ylim': _process_ylim('Temperature'),
            'col_exist': [0],
        },
        'pH Profile': {
            'cols': ['pH'],
            'ylabel': 'pH',
            'xlim': (0, None),
            'ylim': _process_ylim('pH Profile'),
            'col_exist': [0],
        },
        'Tank Pressure': {
            'cols': ['Pressure (bar)'],
            'ylabel': 'Pressure (bar)',
            'xlim': (0, None),
            'ylim': _process_ylim('Tank Pressure'),
            'col_exist': [0],
        },
        'Dissolved Oxygen': {
            'cols': ['DO (%)'],
            'ylabel': 'DO (%)',
            'xlim': (0, None),
            'ylim': _process_ylim('Dissolved Oxygen'),
            'col_exist': [0],
        },
        'Stirrer Rate': {
            'cols': ['Stirrer (rpm)'],
            'ylabel': 'Stirrer (rpm)',
            'xlim': (0, None),
            'ylim': _process_ylim('Stirrer Rate'),
            'col_exist': [0],
        },
        'Oxygen Uptake Rate': {
            'cols': ['OUR (mmol/h)'],
            'ylabel': 'OUR (mmol/h)',
            'xlim': (0, None),
            'ylim': _process_ylim('Oxygen Uptake Rate'),
            'col_exist': [0],
        },
        'CO2 Evolution Rate': {
            'cols': ['CER (mmol/h)'],
            'ylabel': 'CER (mmol/h)',
            'xlim': (0, None),
            'ylim': _process_ylim('CO2 Evolution Rate'),
            'col_exist': [0],
        },
        'Respiratory Quotient': {
            'cols': ['RQ'],
            'ylabel': 'RQ',
            'xlim': (0, None),
            'ylim': _process_ylim('Respiratory Quotient'),
            'col_exist': [0],
        },
        'Added Carbon Weight': {
            'cols': ['Added Carbon Weight (g)'],
            'ylabel': 'Added Carbon Weight (g)',
            'xlim': (0, None),
            'ylim': _process_ylim('Added Carbon Weight'),
            'col_exist': [0],
        },
        'Added Feed Volume': {
            'cols': ['Pumped Feed Vol (ml)'],
            'ylabel': 'Pumped Feed Vol (ml)',
            'xlim': (0, None),
            'ylim': _process_ylim('Added Feed Volume'),
            'col_exist': [0],
        },
        'Added Co-feed Volume': {
            'cols': ['Pumped Co-feed Vol (ml)'],
            'ylabel': 'Pumped Co-feed Vol (ml)',
            'xlim': (0, None),
            'ylim': _process_ylim('Added Co-feed Volume'),
            'col_exist': [0],
        },
        'Added Bolus Volume': {
            'cols': ['Pumped Bolus Vol (ml)'],
            'ylabel': 'Pumped Bolus Vol (ml)',
            'xlim': (0, None),
            'ylim': _process_ylim('Added Bolus Volume'),
            'col_exist': [0],
        },
        'Added Acid Volume': {
            'cols': ['Pumped Acid Vol (ml)'],
            'ylabel': 'Pumped Acid Vol (ml)',
            'xlim': (0, None),
            'ylim': _process_ylim('Added Acid Volume'),
            'col_exist': [0],
        },
        'Added Base Volume': {
            'cols': ['Pumped Base Vol (ml)'],
            'ylabel': 'Pumped Base Vol (ml)',
            'xlim': (0, None),
            'ylim': _process_ylim('Added Base Volume'),
            'col_exist': [0],
        },
        'Removed Sample Volume': {
            'cols': ['Removed Sample Vol (ml)'],
            'ylabel': 'Removed Sample Vol (ml)',
            'xlim': (0, None),
            'ylim': _process_ylim('Removed Sample Volume'),
            'col_exist': [0],
        },
        'Combined Feeds Weight': {
            'cols': ['Combined Feeds Weight (g)'],
            'ylabel': 'Combined Feeds Weight (g)',
            'xlim': (0, None),
            'ylim': _process_ylim('Combined Feeds Weight'),
            'col_exist': [0],
        },
        'Removed Sample Weight': {
            'cols': ['Removed Sample Weight (g)'],
            'ylabel': 'Removed Sample Weight (g)',
            'xlim': (0, None),
            'ylim': _process_ylim('Removed Sample Weight'),
            'col_exist': [0],
        },
        'Consumed O2 Weight': {
            'cols': ['OURT (g)'],
            'ylabel': 'OURT (g)',
            'xlim': (0, None),
            'ylim': _process_ylim('Consumed O2 Weight'),
            'col_exist': [0],
        },
        'Produced CO2 Weight': {
            'cols': ['CERT (g)'],
            'ylabel': 'CERT (g)',
            'xlim': (0, None),
            'ylim': _process_ylim('Produced CO2 Weight'),
            'col_exist': [0],
        },
        'High-level Mass Balance': {
            'cols': ['Mass Balance (%)'],
            'ylabel': 'Mass Balance (%)',
            'xlim': (0, None),
            'ylim': _process_ylim('High-level Mass Balance'),
            'col_exist': [0],
        },
        'Oxygen Tank Flow Rate': {
            'cols': ['Inlet O2 Flow (ml/min)'],
            'ylabel': 'Inlet O2 Flow (ml/min)',
            'xlim': (0, None),
            'ylim': _process_ylim('Oxygen Tank Flow Rate'),
            'col_exist': [0],
        },
        'House Air Flow Rate': {
            'cols': ['Inlet Air Flow (ml/min)'],
            'ylabel': 'Inlet Air Flow (ml/min)',
            'xlim': (0, None),
            'ylim': _process_ylim('House Air Flow Rate'),
            'col_exist': [0],
        },
        'Gas Mix Flow Rate': {
            'cols': ['Inlet GM Flow (ml/min)'],
            'ylabel': 'Inlet GM Flow (ml/min)',
            'xlim': (0, None),
            'ylim': _process_ylim('Gas Mix Flow Rate'),
            'col_exist': [0],
        },
        'Offgas Oxygen Flow (%)': {
            'cols': ['Oulet Flow O2 (%)'],
            'ylabel': 'Oulet Flow O2 (%)',
            'xlim': (0, None),
            'ylim': _process_ylim('Offgas Oxygen Flow (%)'),
            'col_exist': [0],
        },
        'Offgas CO2 Flow (%)': {
            'cols': ['Oulet Flow CO2 (%)'],
            'ylabel': 'Oulet Flow CO2 (%)',
            'xlim': (0, None),
            'ylim': _process_ylim('Offgas CO2 Flow (%)'),
            'col_exist': [0],
        },
        'Offgas N2 Flow (%)': {
            'cols': ['Outlet Flow N2 (%)'],
            'ylabel': 'Outlet Flow N2 (%)',
            'xlim': (0, None),
            'ylim': _process_ylim('Offgas N2 Flow (%)'),
            'col_exist': [0],
        },
    },
}

# ---------------------------------------------------------------------------
# Significance test thresholds
# ---------------------------------------------------------------------------
SIGNIFICANCE_TEST_CONFIG: Dict[str, Any] = _cfg.get('significance_test_config', {})
