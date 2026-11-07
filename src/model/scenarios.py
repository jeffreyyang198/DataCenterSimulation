"""Scenario objects used by the data-center simulation."""

from __future__ import annotations

from dataclasses import dataclass
import math
from numbers import Real


def _finite_number(
    value: float,
    name: str,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    """Validate and return a finite numeric value."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number")

    number = float(value)

    if not math.isfinite(number):
        raise ValueError(f"{name} must be a finite number")

    if minimum is not None and number < minimum:
        raise ValueError(f"{name} must be >= {minimum}")

    if maximum is not None and number > maximum:
        raise ValueError(f"{name} must be <= {maximum}")

    return number


@dataclass(frozen=True)
class SimulationScenario:
    """All assumptions defining one static data-center energy scenario."""

    name: str
    power_density_scenario: str
    workload: str
    floor_area_multiplier: float
    utilization: float
    idle_fraction: float
    pue: float

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Scenario name cannot be empty")

        if self.power_density_scenario not in {
            "low",
            "reference",
            "high",
        }:
            raise ValueError(
                "power_density_scenario must be low, reference, or high"
            )

        if not isinstance(self.workload, str) or not self.workload.strip():
            raise ValueError("workload cannot be empty")

        _finite_number(
            self.floor_area_multiplier,
            "floor_area_multiplier",
            minimum=0.000001,
        )

        _finite_number(
            self.utilization,
            "utilization",
            minimum=0.0,
            maximum=1.0,
        )

        _finite_number(
            self.idle_fraction,
            "idle_fraction",
            minimum=0.0,
            maximum=1.0,
        )

        _finite_number(
            self.pue,
            "pue",
            minimum=1.0,
        )

    @property
    def workload_parameters(self) -> dict[str, float]:
        """Return parameters expected by the existing energy model."""
        return {
            "utilization": float(self.utilization),
            "idle_fraction": float(self.idle_fraction),
            "pue": float(self.pue),
        }


@dataclass(frozen=True)
class TemporalScenario:
    """Growth assumptions for a year-by-year demand projection."""

    name: str
    start_year: int
    end_year: int
    annual_growth_rate: float

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("Temporal scenario name cannot be empty")

        if isinstance(self.start_year, bool) or not isinstance(
            self.start_year,
            int,
        ):
            raise ValueError("start_year must be an integer")

        if isinstance(self.end_year, bool) or not isinstance(
            self.end_year,
            int,
        ):
            raise ValueError("end_year must be an integer")

        if self.end_year < self.start_year:
            raise ValueError("end_year must be >= start_year")

        rate = _finite_number(
            self.annual_growth_rate,
            "annual_growth_rate",
        )

        if rate <= -1:
            raise ValueError(
                "annual_growth_rate must be greater than -1"
            )

    @property
    def years(self) -> range:
        """Inclusive simulation years."""
        return range(self.start_year, self.end_year + 1)

    def growth_factor(self, year: int) -> float:
        """Return compound growth relative to the starting year."""
        if year < self.start_year or year > self.end_year:
            raise ValueError(
                f"year must be between "
                f"{self.start_year} and {self.end_year}"
            )

        years_elapsed = year - self.start_year

        return (1 + self.annual_growth_rate) ** years_elapsed