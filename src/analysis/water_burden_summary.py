"""Summarize temporal data-center water impacts by watershed, state, and site."""

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]

INPUT = ROOT / "outputs/temporal_water_2023_2030.csv"

HUC8_2030_OUTPUT = ROOT / "outputs/water_burden_huc8_2030.csv"
STATE_2030_OUTPUT = ROOT / "outputs/water_burden_state_2030.csv"
SITE_2030_OUTPUT = ROOT / "outputs/water_burden_site_2030.csv"
HUC8_CUM_OUTPUT = ROOT / "outputs/water_burden_huc8_cumulative_2023_2030.csv"


def main() -> None:
    df = pd.read_csv(INPUT, dtype={"huc8": "string"})

    estimated = df.loc[df["water_status"] == "estimated"].copy()

    # ---------------------------------------------------------
    # 2030 watershed burden
    # ---------------------------------------------------------
    y2030 = estimated.loc[estimated["year"] == 2030].copy()

    huc8_2030 = (
        y2030.groupby(
            ["scenario", "huc8"],
            as_index=False,
        )
        .agg(
            sites=("site_id", "nunique"),
            projected_energy_mwh=("projected_energy_mwh", "sum"),
            water_footprint_m3=("annual_water_footprint_m3", "sum"),
            water_scarcity_footprint_m3_eq=(
                "annual_water_scarcity_footprint_m3_eq",
                "sum",
            ),
        )
    )

    huc8_2030["wf_rank_within_scenario"] = (
        huc8_2030.groupby("scenario")["water_footprint_m3"]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    huc8_2030["wsf_rank_within_scenario"] = (
        huc8_2030.groupby("scenario")[
            "water_scarcity_footprint_m3_eq"
        ]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    # ---------------------------------------------------------
    # 2030 state burden
    # ---------------------------------------------------------
    state_2030 = (
        y2030.groupby(
            ["scenario", "state_abbr"],
            as_index=False,
        )
        .agg(
            sites=("site_id", "nunique"),
            projected_energy_mwh=("projected_energy_mwh", "sum"),
            water_footprint_m3=("annual_water_footprint_m3", "sum"),
            water_scarcity_footprint_m3_eq=(
                "annual_water_scarcity_footprint_m3_eq",
                "sum",
            ),
        )
    )

    state_2030["wf_rank_within_scenario"] = (
        state_2030.groupby("scenario")["water_footprint_m3"]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    state_2030["wsf_rank_within_scenario"] = (
        state_2030.groupby("scenario")[
            "water_scarcity_footprint_m3_eq"
        ]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    # ---------------------------------------------------------
    # 2030 individual-site burden
    # ---------------------------------------------------------
    site_columns = [
        c for c in [
            "scenario",
            "year",
            "site_id",
            "site_name",
            "operator",
            "state_abbr",
            "huc8",
            "projected_energy_mwh",
            "WF_1MW_DC",
            "WSF_1MW_DC",
            "annual_water_footprint_m3",
            "annual_water_scarcity_footprint_m3_eq",
        ]
        if c in y2030.columns
    ]

    site_2030 = y2030[site_columns].copy()

    site_2030["wf_rank_within_scenario"] = (
        site_2030.groupby("scenario")[
            "annual_water_footprint_m3"
        ]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    site_2030["wsf_rank_within_scenario"] = (
        site_2030.groupby("scenario")[
            "annual_water_scarcity_footprint_m3_eq"
        ]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    # ---------------------------------------------------------
    # Cumulative 2023-2030 burden by HUC8
    # ---------------------------------------------------------
    huc8_cumulative = (
        estimated.groupby(
            ["scenario", "huc8"],
            as_index=False,
        )
        .agg(
            sites=("site_id", "nunique"),
            cumulative_energy_mwh=("projected_energy_mwh", "sum"),
            cumulative_water_footprint_m3=(
                "annual_water_footprint_m3",
                "sum",
            ),
            cumulative_water_scarcity_footprint_m3_eq=(
                "annual_water_scarcity_footprint_m3_eq",
                "sum",
            ),
        )
    )

    huc8_cumulative["wf_rank_within_scenario"] = (
        huc8_cumulative.groupby("scenario")[
            "cumulative_water_footprint_m3"
        ]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    huc8_cumulative["wsf_rank_within_scenario"] = (
        huc8_cumulative.groupby("scenario")[
            "cumulative_water_scarcity_footprint_m3_eq"
        ]
        .rank(method="min", ascending=False)
        .astype(int)
    )

    HUC8_2030_OUTPUT.parent.mkdir(parents=True, exist_ok=True)

    huc8_2030.to_csv(HUC8_2030_OUTPUT, index=False)
    state_2030.to_csv(STATE_2030_OUTPUT, index=False)
    site_2030.to_csv(SITE_2030_OUTPUT, index=False)
    huc8_cumulative.to_csv(HUC8_CUM_OUTPUT, index=False)

    # Central scenario for quick inspection.
    moderate_huc8 = huc8_2030.loc[
        huc8_2030["scenario"] == "moderate"
    ]

    moderate_sites = site_2030.loc[
        site_2030["scenario"] == "moderate"
    ]

    moderate_states = state_2030.loc[
        state_2030["scenario"] == "moderate"
    ]

    print("\n=== TOP 10 HUC8 BY 2030 MODERATE WATER FOOTPRINT ===")
    print(
        moderate_huc8.nlargest(10, "water_footprint_m3")[
            [
                "huc8",
                "sites",
                "projected_energy_mwh",
                "water_footprint_m3",
                "water_scarcity_footprint_m3_eq",
            ]
        ].to_string(index=False)
    )

    print("\n=== TOP 10 HUC8 BY 2030 MODERATE WATER SCARCITY FOOTPRINT ===")
    print(
        moderate_huc8.nlargest(
            10,
            "water_scarcity_footprint_m3_eq",
        )[
            [
                "huc8",
                "sites",
                "projected_energy_mwh",
                "water_footprint_m3",
                "water_scarcity_footprint_m3_eq",
            ]
        ].to_string(index=False)
    )

    print("\n=== TOP 10 STATES BY 2030 MODERATE WSF ===")
    print(
        moderate_states.nlargest(
            10,
            "water_scarcity_footprint_m3_eq",
        )[
            [
                "state_abbr",
                "sites",
                "projected_energy_mwh",
                "water_footprint_m3",
                "water_scarcity_footprint_m3_eq",
            ]
        ].to_string(index=False)
    )

    print("\n=== TOP 10 SITES BY 2030 MODERATE WSF ===")
    display = [
        c for c in [
            "site_id",
            "site_name",
            "operator",
            "state_abbr",
            "huc8",
            "projected_energy_mwh",
            "annual_water_footprint_m3",
            "annual_water_scarcity_footprint_m3_eq",
        ]
        if c in moderate_sites.columns
    ]

    print(
        moderate_sites.nlargest(
            10,
            "annual_water_scarcity_footprint_m3_eq",
        )[display].to_string(index=False)
    )

    print("\nWrote:")
    print(HUC8_2030_OUTPUT)
    print(STATE_2030_OUTPUT)
    print(SITE_2030_OUTPUT)
    print(HUC8_CUM_OUTPUT)


if __name__ == "__main__":
    main()
