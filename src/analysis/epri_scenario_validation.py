"""Compare all modeled energy scenarios with EPRI 2023 state benchmarks."""

from pathlib import Path

import pandas as pd

from src.model.temporal_projection import aggregate_state_baseline
from src.model.epri_projection import (
    load_epri_projections,
    compare_modeled_to_epri,
)


ROOT = Path(__file__).resolve().parents[2]

SCENARIO_DIR = (
    ROOT
    / "data/processed/energy_scenarios/floor_area_1.0"
)

OUTPUT_FILE = (
    ROOT
    / "outputs/epri_scenario_validation.csv"
)


def validate_energy_scenarios(
    scenario_dir=SCENARIO_DIR,
):
    scenario_dir = Path(scenario_dir)

    epri = load_epri_projections()

    records = []

    for path in sorted(
        scenario_dir.glob("*.csv")
    ):
        if path.name == "scenario_comparison.csv":
            continue

        sites = pd.read_csv(path)

        required = {
            "state_abbr",
            "estimated_annual_facility_energy_mwh",
        }

        if not required.issubset(
            sites.columns
        ):
            continue

        baseline = aggregate_state_baseline(
            sites
        )

        comparison = compare_modeled_to_epri(
            baseline,
            epri,
        )

        matched = comparison.dropna(
            subset=[
                "baseline_modeled_mwh",
                "epri_2023_load_mwh",
            ]
        )

        modeled_total = (
            matched[
                "baseline_modeled_mwh"
            ].sum()
        )

        epri_total = (
            matched[
                "epri_2023_load_mwh"
            ].sum()
        )

        ratio = (
            modeled_total
            / epri_total
        )

        records.append(
            {
                "scenario_file": path.name,
                "matched_states": len(
                    matched
                ),
                "modeled_total_mwh": (
                    modeled_total
                ),
                "epri_total_mwh": (
                    epri_total
                ),
                "modeled_to_epri_ratio": (
                    ratio
                ),
                "modeled_to_epri_pct": (
                    ratio * 100
                ),
                "absolute_difference_pct": (
                    abs(
                        ratio - 1
                    ) * 100
                ),
            }
        )

    result = pd.DataFrame(records)

    result = result.sort_values(
        "absolute_difference_pct"
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print(
        result.to_string(
            index=False
        )
    )

    print(
        "\nClosest scenario to EPRI:"
    )

    if not result.empty:
        best = result.iloc[0]

        print(
            f"{best['scenario_file']} "
            f"({best['modeled_to_epri_pct']:.1f}% "
            f"of EPRI)"
        )

    print(
        f"\nSaved {OUTPUT_FILE}"
    )

    return result


if __name__ == "__main__":
    validate_energy_scenarios()