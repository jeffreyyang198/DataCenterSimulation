"""Generate 2023-2030 temporal emissions projections."""

import argparse

from pathlib import Path

import pandas as pd

from src.model.epri_projection import (
    load_epri_projections,
    project_epri_annual,
)
from src.impact.temporal_emissions import (
    prepare_state_growth_factors,
    project_temporal_site_emissions,
)


ROOT = Path(__file__).resolve().parents[2]

SITE_FILE = (
    ROOT
    / "data/processed/energy_scenarios/floor_area_1.0/"
      "low_ai_inference.csv"
)

MAPPING_FILE = (
    ROOT
    / "data/processed/emissions/site_egrid_mapping.csv"
)

FACTOR_FILE = (
    ROOT
    / "data/processed/emissions/egrid2023_factors.csv"
)

DETAIL_OUTPUT = (
    ROOT
    / "outputs/temporal_emissions_2023_2030.csv"
)

SUMMARY_OUTPUT = (
    ROOT
    / "outputs/temporal_emissions_summary_2023_2030.csv"
)


def build_temporal_emissions(
    site_file=SITE_FILE, detail_output=DETAIL_OUTPUT, summary_output=SUMMARY_OUTPUT,
):
    sites = pd.read_csv(
        site_file, dtype={"site_id": str},
    )

    mapping = pd.read_csv(
        MAPPING_FILE, dtype={"site_id": str},
    )

    factors = pd.read_csv(
        FACTOR_FILE
    )

    epri = load_epri_projections()

    epri_annual = project_epri_annual(
        epri
    )

    growth = prepare_state_growth_factors(
        epri_annual
    )

    result = project_temporal_site_emissions(
        sites=sites,
        site_mapping=mapping,
        egrid_factors=factors,
        state_growth=growth,
    )

    detail_output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_csv(
        detail_output,
        index=False,
    )

    estimated = result[
        result[
            "temporal_emissions_status"
        ] == "estimated"
    ].copy()

    summary = (
        estimated.groupby(
            [
                "scenario",
                "year",
            ],
            as_index=False,
        )
        .agg(
            projected_energy_mwh=(
                "projected_energy_mwh",
                "sum",
            ),
            co2_metric_tonnes=(
                "co2_metric_tonnes",
                "sum",
            ),
            co2e_metric_tonnes=(
                "co2e_metric_tonnes",
                "sum",
            ),
            nox_metric_tonnes=(
                "nox_metric_tonnes",
                "sum",
            ),
            so2_metric_tonnes=(
                "so2_metric_tonnes",
                "sum",
            ),
            modeled_sites=(
                "site_id",
                "nunique",
            ),
        )
    )

    for pollutant in [
        "co2",
        "co2e",
        "nox",
        "so2",
    ]:
        column = (
            f"{pollutant}_metric_tonnes"
        )

        summary[
            f"cumulative_{column}"
        ] = (
            summary.groupby(
                "scenario"
            )[column]
            .cumsum()
        )

    summary[
        "cumulative_energy_mwh"
    ] = (
        summary.groupby(
            "scenario"
        )[
            "projected_energy_mwh"
        ]
        .cumsum()
    )

    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(
        summary_output,
        index=False,
    )

    print(
        "Temporal emissions statuses:"
    )

    print(
        result[
            "temporal_emissions_status"
        ].value_counts(
            dropna=False
        )
    )

    print(
        "\n2030 national scenario totals:"
    )

    print(
        summary[
            summary["year"] == 2030
        ][
            [
                "scenario",
                "projected_energy_mwh",
                "co2_metric_tonnes",
                "co2e_metric_tonnes",
                "nox_metric_tonnes",
                "so2_metric_tonnes",
                "modeled_sites",
            ]
        ].to_string(
            index=False
        )
    )

    print(
        "\n2023-2030 cumulative CO2:"
    )

    last_year = summary[
        summary["year"] == 2030
    ]

    print(
        last_year[
            [
                "scenario",
                "cumulative_co2_metric_tonnes",
            ]
        ].to_string(
            index=False
        )
    )

    print(
        f"\nSaved detail: {detail_output}"
    )

    print(
        f"Saved summary: {summary_output}"
    )

    return result, summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", type=Path, help="Site-level energy model CSV")
    parser.add_argument("--output-dir", type=Path, help="Directory for detail and summary CSVs")
    args = parser.parse_args()
    output_dir = args.output_dir or (DETAIL_OUTPUT.parent / "climate_pue" if args.sites else DETAIL_OUTPUT.parent)
    build_temporal_emissions(
        args.sites or SITE_FILE,
        output_dir / DETAIL_OUTPUT.name,
        output_dir / SUMMARY_OUTPUT.name,
    )
