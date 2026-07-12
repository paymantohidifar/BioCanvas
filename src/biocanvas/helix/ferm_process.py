# biocanvas/helix/ferm_process.py
"""Eve/Pi fermentation process zip loaders for Project Helix.

Each class loads a tank time-series CSV from an Eve or Pi zip export via
:meth:`_GeneralProcessTable.__init__` and returns a processed
:class:`pandas.DataFrame` from :meth:`process`.
"""
import numpy as np
import pandas as pd # type: ignore
import zipfile

# Physical constants for gas-exchange calculations
# Assumption: ideal gas law, P = 1 atm, T = 20 °C
AIR_O2 = 21        # O2 fraction in air (%)
AIR_N2 = 78        # N2 fraction in air (%)
AIR_CO2 = 0.04     # CO2 fraction in air (%)
VOL_TO_MOL = 24.06 # Molar volume at 20 °C, 1 atm (L/mol)
O2_MW = 32         # Oxygen molar mass (g/mol)
CO2_MW = 44        # CO2 molar mass (g/mol)


class _GeneralProcessTable:
    """Base class for fermentation process data tables.

    Subclasses must implement :meth:`_load_table` and :meth:`process`.
    Not intended to be instantiated directly.

    Args:
        zip_ref: Zipped file contents.
        file_name: Tank file name within the zip archive.
        tank: Tank identifier label applied during processing.

    Attributes:
        tank: Tank identifier label.
        table: Raw fermentation process table as read from the zip file.
    """

    def __init__(self, zip_ref: zipfile.ZipFile, file_name: str, tank: str):
        self.tank = tank
        self.table = self._load_table(zip_ref, file_name)  # type: ignore

    @classmethod
    def get_classname(cls) -> str:
        """Returns the class name.

        Returns:
            str: Name of the class.
        """
        return cls.__name__

    @staticmethod
    def _compute_gas_metrics(df: pd.DataFrame, outlet_n2_col: str, outlet_o2_col: str, outlet_co2_col: str) -> pd.DataFrame:
        """Computes gas exchange metrics and appends them to a fermentation DataFrame.

        Expects df to already contain 'Inlet Flow Rate (mmol/h)', 'GasMix', and
        'Time (h)' columns.

        Args:
            df (pd.DataFrame): Fermentation process table with standard intermediate columns.
            outlet_n2_col (str): Column name for the outlet N2 fraction (%).
            outlet_o2_col (str): Column name for the outlet O2 fraction (%).
            outlet_co2_col (str): Column name for the outlet CO2 fraction (%).

        Returns:
            pd.DataFrame: Same DataFrame with Exhaust Flow Rate, OUR, OURT, CER, CERT,
                and RQ columns added.
        """
        inlet_n2_frac: float = AIR_N2  / (100 - AIR_O2) * (100. - df['GasMix'])  # type: ignore
        inlet_co2_frac: float = AIR_CO2 / (100 - AIR_O2) * (100. - df['GasMix'])  # type: ignore

        # Exhaust molar flow rate via inert N2 balance
        df['Exhust Flow Rate (mmol/h)'] = (
            df['Inlet Flow Rate (mmol/h)'] * (inlet_n2_frac / df.get(outlet_n2_col, np.nan))  # type: ignore
        )
        # OUR — O2 uptake rate
        df['OUR (mmol/h)'] = (
            (df['Inlet Flow Rate (mmol/h)'] * df['GasMix'] / 100)  # type: ignore
            - (df['Exhust Flow Rate (mmol/h)'] * df.get(outlet_o2_col, np.nan) / 100)  # type: ignore
        ).clip(lower=0)
        # OURT — cumulative O2 consumed (g); integrate rate × Δt (trapezoid-free for speed)
        dt_h = df['Time (h)'].diff().fillna(0)  # type: ignore
        df['OURT (g)'] = (df['OUR (mmol/h)'] * dt_h).cumsum().fillna(0) * O2_MW / 1000.  # type: ignore
        # df['OURT (g)'] = (
        #     (df['OUR (mmol/h)'].rolling(window=2).mean() * df['Time (h)'].diff())  # type: ignore
        #     .cumsum().fillna(0) * O2_MW / 1000.  # type: ignore
        # )
        # CER — CO2 evolution rate
        df['CER (mmol/h)'] = (
            (df['Exhust Flow Rate (mmol/h)'] * df.get(outlet_co2_col, 0) / 100)  # type: ignore
            - (df['Inlet Flow Rate (mmol/h)'] * inlet_co2_frac / 100)  # type: ignore
        ).clip(lower=0)
        # CERT — cumulative CO2 produced (g)
        df['CERT (g)'] = (df['CER (mmol/h)'] * dt_h).cumsum().fillna(0) * CO2_MW / 1000.  # type: ignore
        # df['CERT (g)'] = (
        #     (df['CER (mmol/h)'].rolling(window=2).mean() * df['Time (h)'].diff())  # type: ignore
        #     .cumsum().fillna(0) * CO2_MW / 1000.  # type: ignore
        # )
        # RQ — Respiratory Quotient
        df['RQ'] = df['CER (mmol/h)'] / df['OUR (mmol/h)']
        return df


class EveTable(_GeneralProcessTable):
    """Eve software fermentation process table for a single tank.

    Args:
        zip_ref: Zipped file contents.
        file_name: Tank file name within the zip archive.
        tank: Tank identifier label.

    Attributes:
        tank: Tank identifier label.
        table: Raw Eve fermentation process table.
    """

    def _load_table(self, zip_ref: zipfile.ZipFile, file_name: str) -> pd.DataFrame:
        """Reads an Eve semicolon-delimited CSV result file into a DataFrame.

        Args:
            zip_ref (zipfile.ZipFile): Zipped file contents.
            file_name (str): Name of the file within the zipped content.

        Returns:
            pd.DataFrame: Original table content.
        """
        with zip_ref.open(file_name) as f:
            return pd.read_csv(f, sep=";", skiprows=1)  # type: ignore

    def process(self) -> pd.DataFrame:
        """Standardises column names, derives Time and flow columns, and computes gas metrics.

        Returns:
            pd.DataFrame: Processed fermentation table with gas exchange metrics.
        """
        
        if self.table.empty:  # type: ignore
            return pd.DataFrame()
        
        df: pd.DataFrame = self.table.copy().dropna(axis='columns', how='all').fillna(0)  # type: ignore
        df['Tank'] = self.tank
        df['Time (h)'] = np.round(  # type: ignore
            df['Batch Time (since inoc.), sec'].values / 3600., 3  # type: ignore
        )

        # Convert flow units from l/min to ml/min where needed
        df['GM Flow, ml/min']  = df.get('GM Flow, ml/min',  df.get('GM Flow, l/min',  np.nan) * 1000)  # type: ignore
        df['Air Flow, ml/min'] = df.get('Air Flow, ml/min', df.get('Air Flow, l/min', np.nan) * 1000)  # type: ignore
        df['O₂ Flow, ml/min']  = df.get('O₂ Flow, ml/min',  df.get('O₂ Flow, l/min',  np.nan) * 1000)  # type: ignore
        df['N₂ Flow, ml/min']  = df.get('N₂ Flow, ml/min',  df.get('N₂ Flow, l/min',  np.nan) * 1000)  # type: ignore
        df['CO₂ Flow, ml/min'] = df.get('CO₂ Flow, ml/min', df.get('CO₂ Flow, l/min', np.nan) * 1000)  # type: ignore

        df['Inlet Flow Rate (mmol/h)'] = df['GM Flow, ml/min'] * 60 / VOL_TO_MOL  # type: ignore

        # Alternative fixed inlet gas fractions (retained for reference):
        # df['Inlet N2, %']  = 62.2    # Tyler's N2 value
        # df['Inlet CO2, %'] = 0.0319  # Tyler's CO2 value
        df['GasMix'] = 36  # enriched-O2 gas mix (%)

        df = self._compute_gas_metrics(
            df, 'PrimaBT.N2, %', 'PrimaBT.O2, %', 'PrimaBT.CO2, %'
        )

        # Standardise final column names
        df.rename(columns={
            'Temperature, °C'                     : 'Temperature (°C)',
            'pH, -'                               : 'pH',
            'Stirrer, 1/min'                      : 'Stirrer (rpm)',
            'pO₂, %'                              : 'DO (%)',
            'O₂ Flow, ml/min'                     : 'Inlet O2 Flow (ml/min)',
            'GM Flow, ml/min'                     : 'Inlet GM Flow (ml/min)',
            'Air Flow, ml/min'                    : 'Inlet Air Flow (ml/min)',
            'PrimaBT.O2, %'                       : 'Oulet Flow O2 (%)',
            'PrimaBT.CO2, %'                      : 'Oulet Flow CO2 (%)',
            'PrimaBT.N2, %'                       : 'Outlet Flow N2 (%)',
            'Watson-Marlow pump, %'               : 'Feed Pump, %',
            'Watson-Marlow pump.Duration, s'      : 'Feed Pump.Duration, s',
            'Watson-Marlow pump.Total volume, ml' : 'Feed Pump.Total volume, ml',
            'Watson-Marlow pump.Pump factor, -'   : 'Feed Pump.Pump factor, -',
            'Watson-Marlow pump.Output, %'        : 'Feed Pump.Output, %',
            'Feed2Rate.Feed2Flowrate, ml/h'       : 'Feed2Rate.Feed2Flowrate, ml/h',
        }, inplace=True, errors='ignore')

        cols_to_drop = [
            'Date Time UTC', 'Date Local Time', 'Batch Time, sec',
            'Batch Time (since inoc.), sec', 'Phase', 'Phase Time, sec',
            'Turbidity', 'N₂ Flow, ml/min', 'CO₂ Flow, ml/min',
            'GasMix', 'PrimaBT.CDC, -', 'PrimaBT.OXC, -',
        ]
        return df.drop(columns=cols_to_drop, errors='ignore')


class PiTable(_GeneralProcessTable):
    """Pi software fermentation process table for a single tank.

    Args:
        zip_ref: Zipped file contents.
        file_name: Tank file name within the zip archive.
        tank: Tank identifier label.

    Attributes:
        tank: Tank identifier label.
        table: Raw Pi fermentation process table.
    """

    def _load_table(self, zip_ref: zipfile.ZipFile, file_name: str) -> pd.DataFrame:
        """Reads a Pi CSV result file into a DataFrame.

        Args:
            zip_ref (zipfile.ZipFile): Zipped file contents.
            file_name (str): Name of the file within the zipped content.

        Returns:
            pd.DataFrame: Original table content.
        """
        with zip_ref.open(file_name) as f:
            return pd.read_csv(f)  # type: ignore

    def process(self) -> pd.DataFrame:
        """Standardises column names, derives Time and flow columns, and computes gas metrics."""
        if self.table.empty:  # type: ignore
            return pd.DataFrame()
        
        df: pd.DataFrame = self.table.copy().dropna(axis='columns', how='all').fillna(0)  # type: ignore
        df['Tank'] = self.tank
        df['Time (h)'] = np.round(df['TFT'].values, 3)  # type: ignore

        df.rename(columns={  # type: ignore
                'Agitation (RPM)'     : 'Stirrer (rpm)',
                'Dissolved Oxygen (%)': 'DO (%)',
                'Airflow (LPM)'       : 'Inlet Air Flow (l/min)',
                'O2, mol%'            : 'Oulet Flow O2 (%)',
                'CO2, mol%'           : 'Oulet Flow CO2 (%)',
                'N2, mol%'            : 'Outlet Flow N2 (%)',
                'Tank Weight'         : 'Weight, kg',
                'Tank Weight (kg)'    : 'Weight, kg',
            }, inplace=True, errors='ignore')

        df['Inlet Air Flow (ml/min)'] = df.get('Inlet Air Flow (l/min)', np.nan) * 1000  # type: ignore
        df['Inlet Flow Rate (mmol/h)'] = df['Inlet Air Flow (ml/min)'] * 60 / VOL_TO_MOL  # type: ignore
        df['GasMix'] = AIR_O2  # house air
        
        # Compute gas metrics
        df = self._compute_gas_metrics(df, 'Outlet Flow N2 (%)', 'Oulet Flow O2 (%)', 'Oulet Flow CO2 (%)')  # type: ignore
        
        # Drop unnecessary columns
        cols_to_drop = [
            'TFT', 'Inlet Air Flow, l/min', 'CER, mol%', 'OUR, mol%',
            'Start Time&Date', 'Time, hr', 'Time&Date', 'Time Stamp',
        ]
        return df.drop(columns=cols_to_drop, errors='ignore')
