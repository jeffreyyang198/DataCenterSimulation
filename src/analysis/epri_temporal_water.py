"""Run 2023-2030 EPRI demand-growth water-impact projections."""

from __future__ import annotations

import inspect
from pathlib import Path

import pandas as pd

from src.impact.temporal_emissions import prepare_state_growth_factors
from src.impact.temporal_water import project_temporal_site_water
from src.model.epri_projection import load_epri_projections, project_epri_annual


ROOT = Path(__file__).resolve().parents[2]

ENERGY_PATH = (
    ROOT
    / "data/processed/energy_scenarios/floor_area_1.0/low_ai_inference.csv"
)
WATER_PATH = ROOT / "data/processed/master_sites_with_huc8.csv"
EPRI_PATH = ROOT / "data/raw/epri/EPRI_2024_Projections.xlsx"

SITE_OUTPUT = ROOT / "outputs/temporal_water_2023_2030.csv"
SUMMARY_OUTPUT = ROOT / "outputs/temporal_water_summary_2023_2030.csv"


def load_epri() -> pd.DataFrame:
    """Load EPRI projections while supporting the project's existing loader signature."""
    parameters = inspect.signature(load_epri_projections).parameters

    if len(parameters) == 0:
        return load_epri_projections()

    return load_epri_projections(EPRI_PATH)


def build_summary(result: pd.DataFrame) -> pd.DataFrame:
    """Aggregate successfully estimated annual water impacts."""
    estimated = result.loc[result["water_status"] == "estimated"].copy()

    summary = (
        estimated.groupby(
            ["scenario", "year"],
            as_index=False,
            dropna=False,
        )
        .agg(
            estimated_sites=("site_id", "nunique"),
            projected_energy_mwh=("projected_energy_mwh", "sum"),
            annual_water_footprint_m3=(
                "annual_water_footprint_m3",
                "sum",
            ),
            annual_water_scarcity_footprint_m3_eq=(
                "annual_water_scarcity_footprint_m3_eq",
                "sum",
            ),
        )
        .sort_values(["scenario", "year"])
        .reset_index(drop=True)
    )

    summary["cumulative_energy_mwh"] = (
        summary.groupby("scenario")["projected_energy_mwh"].cumsum()
    )

    summary["cumulative_water_footprint_m3"] = (
        summary.groupby("scenario")[
            "annual_water_footprint_m3"
        ].cumsum()
    )

    summary["cumulative_water_scarcity_footprint_m3_eq"] = (
        summary.groupby("scenario")[
            "annual_water_scarcity_footprint_m3_eq"
        ].cumsum()
    )

    return summary


def main() -> None:
    energy = pd.read_csv(ENERGY_PATH)

    water = pd.read_csv(
        WATER_PATH,
        dtype={"huc8": "string"},
    )

    epri = load_epri()
    epri_annual = project_epri_annual(epri)
    growth = prepare_state_growth_factors(epri_annual)

    result = project_temporal_site_water(
        sites=energy,
        water_mapping=water,
        state_growth=growth,
        energy_column="estimated_annual_facility_energy_mwh",
    )

    summary = build_summary(result)

    SITE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    result.to_csv(SITE_OUTPUT, index=False)
    summary.to_csv(SUMMARY_OUTPUT, index=False)

    print("\n=== WATER STATUS COUNTS ===")
    print(result["water_status"].value_counts(dropna=False).to_string())

    print("\n=== UNIQUE SITES BY QC FLAG ===")
    for flag in [
        "has_modeled_energy",
        "has_huc8_mapping",
        "has_water_factors",
        "has_epri_growth",
    ]:
        counts = (
            result.groupby("site_id")[flag]
            .max()
            .value_counts(dropna=False)
        )
        print(f"\n{flag}")
        print(counts.to_string())

    print("\n=== 2030 WATER SUMMARY ===")
    print(
        summary.loc[
            summary["year"] == 2030,
            [
                "scenario",
                "estimated_sites",
                "projected_energy_mwh",
                "annual_water_footprint_m3",
                "annual_water_scarcity_footprint_m3_eq",
            ],
        ].to_string(index=False)
    )

    print("\n=== 2023-2030 CUMULATIVE WATER SUMMARY ===")
    final = summary.loc[
        summary.groupby("scenario")["year"].idxmax()
    ]

    print(
        final[
            [
                "scenario",
                "cumulative_energy_mwh",
                "cumulative_water_footprint_m3",
                "cumulative_water_scarcity_footprint_m3_eq",
            ]
        ].to_string(index=False)
    )

    print(f"\nWrote: {SITE_OUTPUT}")
    print(f"Wrote: {SUMMARY_OUTPUT}")


if __name__ == "__main__":
    main()
