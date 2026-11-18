"""Sensitivity analysis for one highly suspicious overlapping IM3 record.

Primary results retain all IM3 records.
This sensitivity excludes only im3_00567575425, the unnamed Arizona record
whose centroid is ~7.7 m from the named Apple Data Center and whose footprint
is ~94% as large.
"""

from pathlib import Path

import pandas as pd

from src.analysis.epri_temporal_water import (
    ENERGY_PATH,
    WATER_PATH,
    build_summary,
    load_epri,
)
from src.impact.temporal_emissions import prepare_state_growth_factors
from src.impact.temporal_water import project_temporal_site_water
from src.model.epri_projection import project_epri_annual


ROOT = Path(__file__).resolve().parents[2]

SUSPECTED_DUPLICATE = "im3_00567575425"

OUTPUT = ROOT / "outputs/apple_duplicate_sensitivity_water.csv"


def run_projection(energy: pd.DataFrame, water: pd.DataFrame) -> pd.DataFrame:
    epri = load_epri()
    epri_annual = project_epri_annual(epri)
    growth = prepare_state_growth_factors(epri_annual)

    result = project_temporal_site_water(
        sites=energy,
        water_mapping=water,
        state_growth=growth,
        energy_column="estimated_annual_facility_energy_mwh",
    )

    return build_summary(result)


def main() -> None:
    energy = pd.read_csv(ENERGY_PATH)

    water = pd.read_csv(
        WATER_PATH,
        dtype={"huc8": "string"},
    )

    primary = run_projection(energy, water)

    filtered_energy = energy.loc[
        energy["site_id"] != SUSPECTED_DUPLICATE
    ].copy()

    sensitivity = run_projection(filtered_energy, water)

    key = ["scenario", "year"]

    comparison = primary.merge(
        sensitivity,
        on=key,
        suffixes=("_primary", "_sensitivity"),
        validate="one_to_one",
    )

    metrics = [
        "projected_energy_mwh",
        "annual_water_footprint_m3",
        "annual_water_scarcity_footprint_m3_eq",
        "cumulative_energy_mwh",
        "cumulative_water_footprint_m3",
        "cumulative_water_scarcity_footprint_m3_eq",
    ]

    for metric in metrics:
        primary_col = f"{metric}_primary"
        sensitivity_col = f"{metric}_sensitivity"

        comparison[f"{metric}_difference"] = (
            comparison[primary_col]
            - comparison[sensitivity_col]
        )

        comparison[f"{metric}_percent_change"] = (
            100
            * comparison[f"{metric}_difference"]
            / comparison[primary_col]
        )

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    comparison.to_csv(OUTPUT, index=False)

    print("Excluded:", SUSPECTED_DUPLICATE)

    print("\n=== 2030 MODERATE SCENARIO ===")
    row = comparison.loc[
        (comparison["scenario"] == "moderate")
        & (comparison["year"] == 2030)
    ].iloc[0]

    for metric in [
        "projected_energy_mwh",
        "annual_water_footprint_m3",
        "annual_water_scarcity_footprint_m3_eq",
    ]:
        print(
            f"{metric}: "
            f"primary={row[f'{metric}_primary']:,.3f} | "
            f"sensitivity={row[f'{metric}_sensitivity']:,.3f} | "
            f"change={row[f'{metric}_percent_change']:.4f}%"
        )

    print("\n=== CUMULATIVE 2023-2030 MODERATE ===")

    for metric in [
        "cumulative_energy_mwh",
        "cumulative_water_footprint_m3",
        "cumulative_water_scarcity_footprint_m3_eq",
    ]:
        print(
            f"{metric}: "
            f"primary={row[f'{metric}_primary']:,.3f} | "
            f"sensitivity={row[f'{metric}_sensitivity']:,.3f} | "
            f"change={row[f'{metric}_percent_change']:.4f}%"
        )

    print("\nWrote:", OUTPUT)


if __name__ == "__main__":
    main()
