"""Temporal water-footprint projections for modeled data-center electricity demand."""

from __future__ import annotations

import pandas as pd


WATER_PARAMETERS = ["WF_1MW_DC", "WSF_1MW_DC"]


def _resolve_column(df: pd.DataFrame, candidates: list[str], label: str) -> str:
    """Return the first available column from a list of accepted aliases."""
    for column in candidates:
        if column in df.columns:
            return column
    raise ValueError(
        f"Could not find {label}. Expected one of: {candidates}. "
        f"Available columns: {list(df.columns)}"
    )


def project_temporal_site_water(
    sites: pd.DataFrame,
    water_mapping: pd.DataFrame,
    state_growth: pd.DataFrame,
    energy_column: str = "annual_energy_mwh",
) -> pd.DataFrame:
    """Project site electricity-related water impacts through time.

    Parameters
    ----------
    sites
        One row per modeled data-center site. Must contain a site identifier,
        state, and baseline annual electricity consumption.

    water_mapping
        HUC8 enrichment table containing site_id, huc8, WF_1MW_DC,
        and WSF_1MW_DC.

    state_growth
        State/year/scenario growth factors. A growth factor of 1.0 represents
        the baseline year.

    energy_column
        Baseline site electricity consumption in MWh/year.

    Notes
    -----
    Siddik WF_1MW_DC and WSF_1MW_DC are treated as fixed water-impact
    coefficients through the projection period. Temporal variation therefore
    represents electricity-demand growth only, not future changes in cooling,
    grid mix, watershed conditions, or water scarcity characterization.
    """
    if energy_column not in sites.columns:
        raise ValueError(f"Missing energy column: {energy_column}")

    site_id_sites = _resolve_column(
        sites,
        ["site_id", "id"],
        "site identifier in sites",
    )
    site_id_water = _resolve_column(
        water_mapping,
        ["site_id", "id"],
        "site identifier in water mapping",
    )

    state_sites = _resolve_column(
        sites,
        ["state_abbr", "state", "State"],
        "state column in sites",
    )
    state_growth_col = _resolve_column(
        state_growth,
        ["state_abbr", "state", "State"],
        "state column in growth factors",
    )

    scenario_col = _resolve_column(
        state_growth,
        ["scenario", "Scenario"],
        "scenario column in growth factors",
    )
    year_col = _resolve_column(
        state_growth,
        ["year", "Year"],
        "year column in growth factors",
    )
    growth_col = _resolve_column(
        state_growth,
        ["growth_factor", "epri_growth_factor", "Growth Factor"],
        "growth factor column",
    )

    required_water = {"huc8", "WF_1MW_DC", "WSF_1MW_DC"}
    missing_water_cols = required_water - set(water_mapping.columns)
    if missing_water_cols:
        raise ValueError(
            f"Water mapping missing required columns: {sorted(missing_water_cols)}"
        )

    base = sites.copy()

    if base[site_id_sites].duplicated().any():
        raise ValueError("Site energy input contains duplicate site identifiers.")

    water = water_mapping[
        [site_id_water, "huc8", "WF_1MW_DC", "WSF_1MW_DC"]
    ].copy()

    if water[site_id_water].duplicated().any():
        raise ValueError("Water mapping contains duplicate site identifiers.")

    water = water.rename(columns={site_id_water: site_id_sites})

    base = base.merge(
        water,
        on=site_id_sites,
        how="left",
        validate="one_to_one",
    )

    growth = state_growth[
        [state_growth_col, scenario_col, year_col, growth_col]
    ].copy()

    growth = growth.rename(
        columns={
            state_growth_col: state_sites,
            scenario_col: "scenario",
            year_col: "year",
            growth_col: "growth_factor",
        }
    )

    if growth.duplicated([state_sites, "scenario", "year"]).any():
        raise ValueError(
            "State growth table contains duplicate state/scenario/year rows."
        )

    # Cross each site against only the temporal records for its state.
    result = base.merge(
        growth,
        on=state_sites,
        how="left",
        validate="many_to_many",
    )

    result[energy_column] = pd.to_numeric(
        result[energy_column], errors="coerce"
    )
    result["growth_factor"] = pd.to_numeric(
        result["growth_factor"], errors="coerce"
    )

    result["WF_1MW_DC"] = pd.to_numeric(
        result["WF_1MW_DC"], errors="coerce"
    )
    result["WSF_1MW_DC"] = pd.to_numeric(
        result["WSF_1MW_DC"], errors="coerce"
    )

    result["has_modeled_energy"] = result[energy_column].notna()
    result["has_huc8_mapping"] = result["huc8"].notna()
    result["has_water_factors"] = (
        result["WF_1MW_DC"].notna()
        & result["WSF_1MW_DC"].notna()
    )
    result["has_epri_growth"] = result["growth_factor"].notna()

    result["projected_energy_mwh"] = (
        result[energy_column] * result["growth_factor"]
    )

    estimated = (
        result["has_modeled_energy"]
        & result["has_huc8_mapping"]
        & result["has_water_factors"]
        & result["has_epri_growth"]
    )

    result["annual_water_footprint_m3"] = pd.NA
    result["annual_water_scarcity_footprint_m3_eq"] = pd.NA

    result.loc[
        estimated, "annual_water_footprint_m3"
    ] = (
        result.loc[estimated, "projected_energy_mwh"]
        * result.loc[estimated, "WF_1MW_DC"]
    )

    result.loc[
        estimated, "annual_water_scarcity_footprint_m3_eq"
    ] = (
        result.loc[estimated, "projected_energy_mwh"]
        * result.loc[estimated, "WSF_1MW_DC"]
    )

    result["annual_water_footprint_m3"] = pd.to_numeric(
        result["annual_water_footprint_m3"], errors="coerce"
    )
    result["annual_water_scarcity_footprint_m3_eq"] = pd.to_numeric(
        result["annual_water_scarcity_footprint_m3_eq"],
        errors="coerce",
    )

    result["water_status"] = "estimated"

    result.loc[
        ~result["has_water_factors"],
        "water_status",
    ] = "missing_water_factor"

    result.loc[
        ~result["has_huc8_mapping"],
        "water_status",
    ] = "no_huc8_mapping"

    result.loc[
        ~result["has_modeled_energy"],
        "water_status",
    ] = "no_modeled_energy"

    result.loc[
        ~result["has_epri_growth"],
        "water_status",
    ] = "no_epri_growth"

    # Cumulative impacts are meaningful only for successfully estimated rows.
    result = result.sort_values(
        [site_id_sites, "scenario", "year"],
        kind="stable",
        na_position="last",
    )

    result["cumulative_water_footprint_m3"] = (
        result.groupby(
            [site_id_sites, "scenario"],
            dropna=False,
        )["annual_water_footprint_m3"]
        .cumsum()
    )

    result["cumulative_water_scarcity_footprint_m3_eq"] = (
        result.groupby(
            [site_id_sites, "scenario"],
            dropna=False,
        )["annual_water_scarcity_footprint_m3_eq"]
        .cumsum()
    )

    return result.reset_index(drop=True)
