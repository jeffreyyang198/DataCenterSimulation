"""Temporal emissions projections for modeled data-center electricity demand.

Each site's 2023 modeled electricity demand is projected through time using
its state's EPRI growth trajectory. The site retains its assigned eGRID
subregion and 2023 eGRID emission factors.

Important:
    eGRID 2023 emission factors are held constant through the projection
    period. This is a scenario assumption, not a forecast of future grid
    carbon intensity.
"""

from __future__ import annotations

import pandas as pd


LB_TO_METRIC_TONNES = 0.00045359237

DEFAULT_ENERGY_COLUMN = "estimated_annual_facility_energy_mwh"


def _resolve_column(
    frame: pd.DataFrame,
    candidates: list[str],
    label: str,
) -> str:
    """Return the first matching column name."""
    for column in candidates:
        if column in frame.columns:
            return column

    raise ValueError(
        f"Could not find {label}. "
        f"Tried: {candidates}"
    )


def prepare_state_growth_factors(
    epri_annual: pd.DataFrame,
) -> pd.DataFrame:
    """Convert annual EPRI loads into state/scenario/year growth factors."""
    required = {
        "state_abbr",
        "scenario",
        "year",
        "projected_epri_load_mwh",
    }

    if missing := required - set(epri_annual.columns):
        raise ValueError(
            f"Missing EPRI annual columns: {sorted(missing)}"
        )

    growth = epri_annual[
        [
            "state_abbr",
            "scenario",
            "year",
            "projected_epri_load_mwh",
        ]
    ].copy()

    if growth.duplicated(
        subset=[
            "state_abbr",
            "scenario",
            "year",
        ]
    ).any():
        raise ValueError(
            "Duplicate EPRI state/scenario/year rows found"
        )

    growth = growth.sort_values(
        [
            "state_abbr",
            "scenario",
            "year",
        ]
    )

    baseline = growth.groupby(
        [
            "state_abbr",
            "scenario",
        ],
        dropna=False,
    )["projected_epri_load_mwh"].transform(
        "first"
    )

    growth["epri_growth_factor"] = (
        growth["projected_epri_load_mwh"]
        / baseline
    )

    return growth


def project_temporal_site_emissions(
    sites: pd.DataFrame,
    site_mapping: pd.DataFrame,
    egrid_factors: pd.DataFrame,
    state_growth: pd.DataFrame,
    energy_column: str = DEFAULT_ENERGY_COLUMN,
) -> pd.DataFrame:
    """Project annual site energy and emissions through time.

    Parameters
    ----------
    sites:
        Site-level modeled energy dataset.

    site_mapping:
        Site-to-eGRID-subregion mapping.

    egrid_factors:
        eGRID subregion emission factors in lb/MWh.

    state_growth:
        State/scenario/year EPRI growth factors.

    Returns
    -------
    pandas.DataFrame
        One row per site, EPRI scenario, and year where a state trajectory
        is available. Sites lacking EPRI coverage are retained with a
        no_epri_growth status.
    """
    required_sites = {
        "site_id",
        "state_abbr",
        energy_column,
    }

    if missing := required_sites - set(sites.columns):
        raise ValueError(
            f"Missing site columns: {sorted(missing)}"
        )

    if "site_id" not in site_mapping.columns:
        raise ValueError(
            "site_mapping must contain site_id"
        )

    if site_mapping["site_id"].duplicated().any():
        raise ValueError(
            "site_mapping contains duplicate site_id values"
        )

    growth_required = {
        "state_abbr",
        "scenario",
        "year",
        "epri_growth_factor",
    }

    if missing := growth_required - set(
        state_growth.columns
    ):
        raise ValueError(
            f"Missing growth columns: {sorted(missing)}"
        )

    if state_growth.duplicated(
        subset=[
            "state_abbr",
            "scenario",
            "year",
        ]
    ).any():
        raise ValueError(
            "state_growth contains duplicate state/scenario/year rows"
        )

    mapping_subregion = _resolve_column(
        site_mapping,
        [
            "egrid_subregion",
            "subregion",
            "SUBRGN",
        ],
        "site mapping subregion column",
    )

    factor_subregion = _resolve_column(
        egrid_factors,
        [
            "egrid_subregion",
            "subregion",
            "SUBRGN",
        ],
        "eGRID factor subregion column",
    )

    rate_columns = {
        "co2": _resolve_column(
            egrid_factors,
            [
                "co2_lb_per_mwh",
                "SRCO2RTA",
                "co2_rate_lb_mwh",
            ],
            "CO2 rate",
        ),
        "co2e": _resolve_column(
            egrid_factors,
            [
                "co2e_lb_per_mwh",
                "SRC2ERTA",
                "co2e_rate_lb_mwh",
            ],
            "CO2e rate",
        ),
        "nox": _resolve_column(
            egrid_factors,
            [
                "nox_lb_per_mwh",
                "SRNOXRTA",
                "nox_rate_lb_mwh",
            ],
            "NOx rate",
        ),
        "so2": _resolve_column(
            egrid_factors,
            [
                "so2_lb_per_mwh",
                "SRSO2RTA",
                "so2_rate_lb_mwh",
            ],
            "SO2 rate",
        ),
    }

    factors = egrid_factors[
        [
            factor_subregion,
            *rate_columns.values(),
        ]
    ].copy()

    factors = factors.rename(
        columns={
            factor_subregion: "egrid_subregion",
            rate_columns["co2"]: "co2_lb_per_mwh",
            rate_columns["co2e"]: "co2e_lb_per_mwh",
            rate_columns["nox"]: "nox_lb_per_mwh",
            rate_columns["so2"]: "so2_lb_per_mwh",
        }
    )

    if factors[
        "egrid_subregion"
    ].duplicated().any():
        raise ValueError(
            "eGRID factors contain duplicate subregions"
        )

    mapping = site_mapping[
        [
            "site_id",
            mapping_subregion,
        ]
    ].rename(
        columns={
            mapping_subregion: "egrid_subregion"
        }
    )

    frame = sites.copy()

    frame[energy_column] = pd.to_numeric(
        frame[energy_column],
        errors="coerce",
    )

    frame = frame.merge(
        mapping,
        on="site_id",
        how="left",
        validate="one_to_one",
    )

    frame = frame.merge(
        factors,
        on="egrid_subregion",
        how="left",
        validate="many_to_one",
    )

    # Expand every site across the EPRI scenarios and years
    # available for its state.
    result = frame.merge(
        state_growth[
            [
                "state_abbr",
                "scenario",
                "year",
                "epri_growth_factor",
            ]
        ],
        on="state_abbr",
        how="left",
        validate="many_to_many",
    )

    result[
        "projected_energy_mwh"
    ] = (
        result[energy_column]
        * result["epri_growth_factor"]
    )

    for pollutant in [
        "co2",
        "co2e",
        "nox",
        "so2",
    ]:
        rate = (
            f"{pollutant}_lb_per_mwh"
        )

        pounds = (
            f"{pollutant}_lb"
        )

        tonnes = (
            f"{pollutant}_metric_tonnes"
        )

        result[pounds] = (
            result["projected_energy_mwh"]
            * result[rate]
        )

        result[tonnes] = (
            result[pounds]
            * LB_TO_METRIC_TONNES
        )

    # Preserve individual QC reasons instead of relying only on one
    # mutually exclusive summary status.
    result["has_modeled_energy"] = (
        result[energy_column].notna()
    )

    result["has_epri_growth"] = (
        result["scenario"].notna()
    )

    result["has_egrid_mapping"] = (
        result["egrid_subregion"].notna()
    )

    result["has_complete_egrid_factors"] = (
        result[
            [
                "co2_lb_per_mwh",
                "co2e_lb_per_mwh",
                "nox_lb_per_mwh",
                "so2_lb_per_mwh",
            ]
        ]
        .notna()
        .all(axis=1)
    )

    # Convenient single summary status.
    #
    # Priority is intentional:
    # no EPRI trajectory prevents temporal projection entirely,
    # followed by no modeled energy, no spatial mapping, and
    # incomplete eGRID factors.
    result["temporal_emissions_status"] = "estimated"

    result.loc[
        ~result["has_complete_egrid_factors"],
        "temporal_emissions_status",
    ] = "missing_egrid_factor"

    result.loc[
        ~result["has_egrid_mapping"],
        "temporal_emissions_status",
    ] = "no_egrid_mapping"

    result.loc[
        ~result["has_modeled_energy"],
        "temporal_emissions_status",
    ] = "no_modeled_energy"

    result.loc[
        ~result["has_epri_growth"],
        "temporal_emissions_status",
    ] = "no_epri_growth"

    for pollutant in [
        "co2",
        "co2e",
        "nox",
        "so2",
    ]:
        annual_column = (
            f"{pollutant}_metric_tonnes"
        )

        cumulative_column = (
            f"cumulative_{pollutant}_metric_tonnes"
        )

        result[cumulative_column] = (
            result.groupby(
                [
                    "site_id",
                    "scenario",
                ],
                dropna=False,
            )[annual_column]
            .cumsum()
        )

    return result