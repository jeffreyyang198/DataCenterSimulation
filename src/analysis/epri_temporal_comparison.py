"""Project modeled state demand through 2030 using EPRI growth trajectories."""

from pathlib import Path

import pandas as pd

from src.model.temporal_projection import aggregate_state_baseline
from src.model.epri_projection import (
    load_epri_projections,
    project_epri_annual,
)


ROOT = Path(__file__).resolve().parents[2]

MODELED_FILE = (
    ROOT
    / "data/processed/energy_scenarios/floor_area_1.0/low_ai_inference.csv"
)

OUTPUT_FILE = (
    ROOT
    / "outputs/epri_temporal_comparison.csv"
)


def build_temporal_comparison(
    modeled_file: str | Path = MODELED_FILE,
) -> pd.DataFrame:
    """Compare modeled and EPRI state trajectories from 2023 through 2030.

    The modeled 2023 baseline comes from the selected IM3 energy scenario.

    EPRI supplies state-specific growth trajectories. Those growth factors
    are applied to the modeled 2023 baseline without replacing the modeled
    baseline itself.

    Therefore:
        modeled trajectory = modeled 2023 load × EPRI growth factor

    The EPRI trajectory remains an independent external benchmark.
    """
    modeled_file = Path(modeled_file)

    if not modeled_file.exists():
        raise FileNotFoundError(
            f"Modeled scenario file not found: {modeled_file}"
        )

    sites = pd.read_csv(modeled_file)

    modeled_baseline = aggregate_state_baseline(
        sites,
        state_column="state_abbr",
        energy_column="estimated_annual_facility_energy_mwh",
    )

    epri = load_epri_projections()

    epri_annual = project_epri_annual(
        epri
    )

    # EPRI's annual projections already contain one state/scenario/year row.
    comparison = epri_annual.merge(
        modeled_baseline,
        left_on="state_abbr",
        right_on="state",
        how="left",
        validate="many_to_one",
        suffixes=("", "_modeled"),
    )

    comparison = comparison.drop(
        columns=["state_modeled"]
    )

    # Growth factor relative to EPRI's 2023 value.
    comparison["epri_growth_factor"] = (
        comparison["projected_epri_load_mwh"]
        / comparison.groupby(
            ["state_abbr", "scenario"]
        )["projected_epri_load_mwh"]
        .transform("first")
    )

    # Apply the same trajectory to our independently modeled baseline.
    comparison["projected_modeled_load_mwh"] = (
        comparison["baseline_modeled_mwh"]
        * comparison["epri_growth_factor"]
    )

    comparison["modeled_minus_epri_mwh"] = (
        comparison["projected_modeled_load_mwh"]
        - comparison["projected_epri_load_mwh"]
    )

    comparison["modeled_to_epri_ratio"] = (
        comparison["projected_modeled_load_mwh"]
        / comparison["projected_epri_load_mwh"]
    )

    comparison["modeled_to_epri_pct"] = (
        comparison["modeled_to_epri_ratio"]
        * 100
    )

    comparison[
        "cumulative_modeled_load_mwh"
    ] = (
        comparison.groupby(
            ["state_abbr", "scenario"],
            dropna=False,
        )["projected_modeled_load_mwh"]
        .cumsum()
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    comparison.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    matched = comparison.dropna(
        subset=[
            "baseline_modeled_mwh",
            "projected_epri_load_mwh",
        ]
    )

    print(
        f"States with modeled and EPRI data: "
        f"{matched['state_abbr'].nunique()}"
    )

    print(
        f"Temporal rows: {len(matched)}"
    )

    print(
        "\nVirginia moderate-growth example:"
    )

    print(
        matched[
            (matched["state_abbr"] == "VA")
            & (matched["scenario"] == "moderate")
        ][
            [
                "year",
                "projected_modeled_load_mwh",
                "projected_epri_load_mwh",
                "modeled_to_epri_pct",
                "cumulative_modeled_load_mwh",
            ]
        ].to_string(index=False)
    )

    print(
        f"\nSaved {OUTPUT_FILE}"
    )

    return comparison


if __name__ == "__main__":
    build_temporal_comparison()