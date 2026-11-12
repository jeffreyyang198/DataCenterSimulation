"""Compare modeled state-level data-center demand with EPRI 2023 benchmarks."""

from pathlib import Path

import pandas as pd

from src.model.temporal_projection import aggregate_state_baseline
from src.model.epri_projection import (
    load_epri_projections,
    compare_modeled_to_epri,
)


ROOT = Path(__file__).resolve().parents[2]

ENERGY_FILE = (
    ROOT / "data/processed/data_centers_with_energy.csv"
)

OUTPUT_FILE = (
    ROOT / "outputs/epri_modeled_vs_2023.csv"
)


def build_epri_baseline_comparison(
    energy_file: str | Path = ENERGY_FILE,
    output_file: str | Path = OUTPUT_FILE,
) -> pd.DataFrame:
    """Compare modeled site energy totals by state with EPRI 2023 load.

    The site's modeled electricity values remain scenario-based estimates.
    EPRI values are used as state-level external benchmarks, not as
    facility-level measurements.
    """
    energy_file = Path(energy_file)
    output_file = Path(output_file)

    if not energy_file.exists():
        raise FileNotFoundError(
            f"Energy dataset not found: {energy_file}"
        )

    sites = pd.read_csv(
        energy_file,
        dtype={
            "site_id": "string",
            "state_abbr": "string",
        },
    )

    required = {
        "state_abbr",
        "estimated_annual_facility_energy_mwh",
    }

    if missing := required - set(sites.columns):
        raise ValueError(
            f"Missing energy columns: {sorted(missing)}"
        )

    baseline = aggregate_state_baseline(
        sites,
        state_column="state_abbr",
        energy_column="estimated_annual_facility_energy_mwh",
    )

    epri = load_epri_projections()

    comparison = compare_modeled_to_epri(
        baseline,
        epri,
    )

    comparison["modeled_share_of_epri_pct"] = (
        comparison["modeled_to_epri_ratio"]
        * 100
    )

    comparison["epri_match_status"] = (
        comparison["epri_2023_load_mwh"]
        .notna()
        .map(
            {
                True: "matched",
                False: "no_epri_benchmark",
            }
        )
    )

    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    comparison.to_csv(
        output_file,
        index=False,
    )

    matched = comparison[
        comparison["epri_match_status"] == "matched"
    ]

    print(
        f"Modeled states: {len(comparison)}"
    )

    print(
        f"EPRI-matched states: {len(matched)}"
    )

    print(
        "States without EPRI benchmark:",
        comparison.loc[
            comparison["epri_match_status"]
            != "matched",
            "state",
        ].tolist(),
    )

    print("\nModeled vs EPRI 2023:")
    print(
        matched[
            [
                "state",
                "modeled_site_count",
                "baseline_modeled_mwh",
                "epri_2023_load_mwh",
                "modeled_share_of_epri_pct",
            ]
        ]
        .sort_values(
            "modeled_share_of_epri_pct",
            ascending=False,
        )
        .to_string(
            index=False,
        )
    )

    print(
        f"\nSaved {output_file}"
    )

    return comparison


if __name__ == "__main__":
    build_epri_baseline_comparison()