"""Calibrate critical IT W/ft² of gross floor area and model building footprints."""

import math
from numbers import Real
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CALIBRATION_FILE = ROOT / 'data/model_parameters/power_density_calibration.csv'
# Stored densities have two decimal places; allow up to 0.01 W/ft² rounding error.
DENSITY_TOLERANCE = 0.01


def _positive_number(value: float, name: str) -> float:
    """Reject missing, nonnumeric, infinite, boolean, zero, or negative values."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f'{name} must be a positive finite number')
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f'{name} must be a positive finite number')
    return number


def calculate_observed_power_density(capacity_mw: float, gross_sqft: float) -> float:
    """Return critical IT W/ft² of reported gross floor area (not IT-space area).

    Both capacity in MW and gross area in ft² must be finite and positive.
    """
    capacity = _positive_number(capacity_mw, 'capacity_mw')
    area = _positive_number(gross_sqft, 'gross_sqft')
    return _positive_number(capacity * 1_000_000 / area, 'calculated density')


def load_power_density_calibration(path: str | Path = CALIBRATION_FILE) -> pd.DataFrame:
    """Load and check the supplied facility calibration table.

    Reject stored densities differing by more than 0.01 W/ft² from MW / gross
    area. Return full-precision recalculated ``w_per_sqft`` for statistics and
    retain the input values as ``stored_w_per_sqft``. Source notes are placeholders,
    so this arithmetic check does not verify the facility reports themselves.
    """
    df = pd.read_csv(path)
    required = {'facility', 'gross_sqft', 'critical_it_mw', 'w_per_sqft', 'source_note'}
    if missing := required - set(df.columns):
        raise ValueError(f'Missing calibration columns: {sorted(missing)}')
    if df.empty:
        raise ValueError('Calibration must contain at least one facility')
    calculated = []
    for row in df.itertuples(index=False):
        density = calculate_observed_power_density(row.critical_it_mw, row.gross_sqft)
        stored = _positive_number(row.w_per_sqft, 'stored w_per_sqft')
        if abs(density - stored) > DENSITY_TOLERANCE:
            raise ValueError(
                f'{row.facility}: stored density {stored} differs from calculated '
                f'{density:.6f} W/ft² by more than {DENSITY_TOLERANCE}'
            )
        calculated.append(density)
    df['stored_w_per_sqft'] = df['w_per_sqft']
    df['w_per_sqft'] = calculated
    return df


def summarize_power_density(df: pd.DataFrame) -> dict[str, float | int]:
    """Return unweighted facility density statistics in W/ft² of gross area.

    Each facility counts once; quartiles use pandas' linear interpolation.
    No density is inferred for missing or invalid calibration observations.
    """
    if 'w_per_sqft' not in df or df.empty:
        raise ValueError('A nonempty calibration with w_per_sqft is required')
    values = pd.Series([_positive_number(v, 'w_per_sqft') for v in df.w_per_sqft])
    return {
        'count': len(values),
        'minimum': float(values.min()),
        'q25': float(values.quantile(0.25)),
        'median': float(values.median()),
        'q75': float(values.quantile(0.75)),
        'maximum': float(values.max()),
        'mean': float(values.mean()),
    }


def estimate_rated_power_from_im3(
    footprint_sqft: float,
    floor_area_multiplier: float,
    power_density_w_sqft: float,
    site_type: str,
) -> float | None:
    """Estimate building rated IT MW, never observed site power.

    Gross area (ft²) = IM3 polygon footprint (ft²) × explicit area multiplier.
    Multiply by critical IT W/ft² of gross area and divide by 1e6 for MW.
    Campus and point records return None before validating their unused inputs.
    Unknown site types raise ValueError. No multiplier default is assumed here.
    """
    if site_type in ('campus', 'point'):
        return None
    if site_type != 'building':
        raise ValueError(f'Unknown site_type: {site_type!r}')
    footprint = _positive_number(footprint_sqft, 'footprint_sqft')
    multiplier = _positive_number(floor_area_multiplier, 'floor_area_multiplier')
    density = _positive_number(power_density_w_sqft, 'power_density_w_sqft')
    estimated_gross_area = footprint * multiplier
    return _positive_number(estimated_gross_area * density / 1_000_000, 'rated IT power')


def assign_power_density_scenario(summary: dict[str, float | int], scenario: str) -> float:
    """Select low=q25, reference=median, or high=q75 density in W/ft²."""
    keys = {'low': 'q25', 'reference': 'median', 'high': 'q75'}
    if scenario not in keys:
        raise ValueError(f'Unknown density scenario {scenario!r}; choose low, reference, or high')
    key = keys[scenario]
    if key not in summary:
        raise ValueError(f'Calibration summary is missing {key}')
    return _positive_number(summary[key], key)
