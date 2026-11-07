"""Temporal projections of modeled data-center electricity demand."""

from __future__ import annotations

import pandas as pd

try:
    from .scenarios import TemporalScenario
except ImportError:
    from scenarios import TemporalScenario


DEFAULT_ENERGY_COLUMN = (
    "estimated_annual_facility_energy_mwh"
)


def aggregate_state_baseline(
    sites: pd.DataFrame,
    state_column: str = "state_abbr",
    energy_column: str = DEFAULT_ENERGY_COLUMN,
) -> pd.DataFrame:
    """Aggregate modeled site electricity demand by state.

    Missing site energy estimates remain unknown rather than being
    interpreted as zero.

    Returns:
        DataFrame with:
            state
            baseline_modeled_mwh
            modeled_site_count
    """
    required = {
        state_column,
        energy_column,
    }

    if missing := required - set(sites.columns):
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    frame = sites[
        [
            state_column,
            energy_column,
        ]
    ].copy()

    frame[energy_column] = pd.to_numeric(
        frame[energy_column],
        errors="coerce",
    )

    grouped = (
        frame.groupby(
            state_column,
            dropna=False,
        )
        .agg(
            baseline_modeled_mwh=(
                energy_column,
                lambda values: values.sum(
                    min_count=1
                ),
            ),
            modeled_site_count=(
                energy_column,
                "count",
            ),
        )
        .reset_index()
    )

    return grouped.rename(
        columns={
            state_column: "state",
        }
    )


def project_state_energy(
    state_baseline: pd.DataFrame,
    scenario: TemporalScenario,
) -> pd.DataFrame:
    """Project state-level modeled demand through time.

    Projection equation:

        E_t = E_0 * (1 + g)^(t - start_year)

    where:
        E_0 = baseline modeled electricity demand
        g   = annual growth rate

    This models growth of aggregate represented demand. It does not
    predict where individual future data centers will be constructed.
    """
    if not isinstance(scenario, TemporalScenario):
        raise TypeError(
            "scenario must be a TemporalScenario"
        )

    

    # Support American spelling used elsewhere in the repo.
    if (
        "baseline_modeled_mwh"
        in state_baseline.columns
    ):
        baseline_column = "baseline_modeled_mwh"
    elif (
        "baseline_modelled_mwh"
        in state_baseline.columns
    ):
        baseline_column = "baseline_modelled_mwh"
    else:
        raise ValueError(
            "state_baseline must contain "
            "baseline_modeled_mwh"
        )

    if "state" not in state_baseline.columns:
        raise ValueError(
            "state_baseline must contain state"
        )

    rows = []

    for row in state_baseline.itertuples(
        index=False
    ):
        state = getattr(row, "state")
        baseline = getattr(
            row,
            baseline_column,
        )

        for year in scenario.years:
            factor = scenario.growth_factor(year)

            if pd.isna(baseline):
                projected = float("nan")
            else:
                projected = (
                    float(baseline)
                    * factor
                )

            rows.append(
                {
                    "state": state,
                    "year": year,
                    "temporal_scenario": scenario.name,
                    "annual_growth_rate": (
                        scenario.annual_growth_rate
                    ),
                    "growth_factor": factor,
                    "baseline_modeled_mwh": baseline,
                    "projected_energy_mwh": projected,
                }
            )

    result = pd.DataFrame(rows)

    result[
        "cumulative_projected_energy_mwh"
    ] = (
        result.groupby(
            [
                "state",
                "temporal_scenario",
            ],
            dropna=False,
        )["projected_energy_mwh"]
        .cumsum()
    )

    return result