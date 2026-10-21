"""Scenario-based IT power and annual facility energy; all power inputs are MW."""

import math
from numbers import Real


def _finite_number(value: float, name: str, minimum: float = 0.0,
                   maximum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f'{name} must be a finite number')
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise ValueError(f'{name} must be finite and >= {minimum}')
    if maximum is not None and number > maximum:
        raise ValueError(f'{name} must be between {minimum} and {maximum}')
    return number


def estimate_average_it_power(rated_power_mw: float, utilization: float,
                              idle_fraction: float) -> float:
    """Return average IT MW from a linear idle-to-rated power scenario.

    Utilization and idle fraction are dimensionless fractions in [0, 1].
    At zero utilization, power equals rated power × idle fraction; at full
    utilization it equals rated power. Rated power must be nonnegative.
    """
    rated = _finite_number(rated_power_mw, 'rated_power_mw')
    utilization = _finite_number(utilization, 'utilization', maximum=1.0)
    idle_fraction = _finite_number(idle_fraction, 'idle_fraction', maximum=1.0)
    idle_power = rated * idle_fraction
    return idle_power + utilization * (rated - idle_power)


def estimate_annual_facility_energy(average_it_power_mw: float, pue: float,
                                    hours_per_year: float = 8760) -> float:
    """Return annual facility MWh = average IT MW × PUE × operating hours.

    PUE (facility energy / IT energy) is dimensionless and at least 1. Power
    must be nonnegative and annual operating hours positive. The default is
    a full non-leap year; no additional utilization factor is applied here.
    """
    power = _finite_number(average_it_power_mw, 'average_it_power_mw')
    pue = _finite_number(pue, 'pue', minimum=1.0)
    hours = _finite_number(hours_per_year, 'hours_per_year')
    if hours == 0:
        raise ValueError('hours_per_year must be positive')
    facility_power_mw = power * pue
    return _finite_number(facility_power_mw * hours, 'annual facility energy')
