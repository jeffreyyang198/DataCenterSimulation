"""Combine unique nearby population with HUC8-level water impacts.

For each HUC8:
- select 2030 moderate-scenario modeled sites;
- dissolve all 5-km site buffers within the HUC8;
- estimate unique nearby population using area-weighted census tracts;
- aggregate energy, WF, and WSF across site records.

Population represents people near mapped data-center sites assigned to the
watershed. It is a proximity/context metric, not a direct exposure estimate.
"""

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[2]

EXPOSURE = ROOT / "data/processed/community_exposure.csv"
TRACTS = ROOT / "data/processed/tracts_near_sites.gpkg"
WATER = ROOT / "outputs/temporal_water_2023_2030.csv"

OUTPUT = ROOT / "outputs/huc8_population_water_2030.csv"

FIG_PNG = (
    ROOT
    / "outputs/figures/figure5c_huc8_population_vs_wsf.png"
)

FIG_PDF = (
    ROOT
    / "outputs/figures/figure5c_huc8_population_vs_wsf.pdf"
)


def unique_population_for_geometry(
    tracts,
    geometry,
):
    candidates = tracts[
        tracts.geometry.intersects(geometry)
    ].copy()

    if candidates.empty:
        return float("nan"), 0

    intersection_area = (
        candidates.geometry
        .intersection(geometry)
        .area
    )

    tract_area = pd.to_numeric(
        candidates["tract_area_m2"],
        errors="coerce",
    )

    fraction = (
        intersection_area / tract_area
    ).clip(
        lower=0,
        upper=1,
    )

    population = pd.to_numeric(
        candidates["population"],
        errors="coerce",
    )

    estimate = (
        population * fraction
    ).sum(min_count=1)

    return (
        float(estimate),
        int(len(candidates)),
    )


def main():

    exposure = pd.read_csv(
        EXPOSURE,
        dtype={
            "site_id": "string",
            "tract_geoid": "string",
        },
    )

    water = pd.read_csv(
        WATER,
        dtype={
            "site_id": "string",
            "huc8": "string",
        },
    )

    tracts = gpd.read_file(
        TRACTS
    )

    water = water[
        (water["scenario"] == "moderate")
        & (water["year"] == 2030)
        & (water["water_status"] == "estimated")
        & water["huc8"].notna()
    ].copy()

    population_context = exposure[
        [
            "site_id",
            "latitude",
            "longitude",
            "pop_5km",
            "incomplete_pop_5km",
        ]
    ].rename(
        columns={
            "latitude": "population_latitude",
            "longitude": "population_longitude",
        }
    )

    data = water.merge(
        population_context,
        on="site_id",
        how="left",
        validate="one_to_one",
    )

    sites = gpd.GeoDataFrame(
        data,
        geometry=gpd.points_from_xy(
            data["population_longitude"],
            data["population_latitude"],
        ),
        crs="EPSG:4326",
    ).to_crs(tracts.crs)

    sites["buffer_5km"] = (
        sites.geometry.buffer(5000)
    )

    rows = []

    print(
        "Calculating unique 5-km population by HUC8..."
    )

    for huc8, group in sites.groupby("huc8"):

        dissolved = unary_union(
            list(group["buffer_5km"])
        )

        nearby_population, tract_count = (
            unique_population_for_geometry(
                tracts,
                dissolved,
            )
        )

        rows.append(
            {
                "huc8": huc8,
                "sites": group["site_id"].nunique(),
                "unique_population_within_5km": (
                    nearby_population
                ),
                "tracts_intersecting_5km_union": tract_count,
                "projected_energy_mwh": (
                    group[
                        "projected_energy_mwh"
                    ].sum()
                ),
                "water_footprint_m3": (
                    group[
                        "annual_water_footprint_m3"
                    ].sum()
                ),
                "water_scarcity_footprint_m3_eq": (
                    group[
                        "annual_water_scarcity_footprint_m3_eq"
                    ].sum()
                ),
                "has_incomplete_population_site": bool(
                    group[
                        "incomplete_pop_5km"
                    ].fillna(True).any()
                ),
            }
        )

    out = pd.DataFrame(rows)

    out["wf_rank"] = (
        out["water_footprint_m3"]
        .rank(
            ascending=False,
            method="min",
        )
        .astype(int)
    )

    out["wsf_rank"] = (
        out[
            "water_scarcity_footprint_m3_eq"
        ]
        .rank(
            ascending=False,
            method="min",
        )
        .astype(int)
    )

    # Screening/context variable only.
    out[
        "wsf_per_10k_unique_nearby_population"
    ] = (
        out[
            "water_scarcity_footprint_m3_eq"
        ]
        /
        out[
            "unique_population_within_5km"
        ]
        * 10_000
    )

    out = out.sort_values(
        "water_scarcity_footprint_m3_eq",
        ascending=False,
    )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.parent.joinpath(
        "figures"
    ).mkdir(
        parents=True,
        exist_ok=True,
    )

    out.to_csv(
        OUTPUT,
        index=False,
    )

    print("\n=== TOP HUC8 BY WSF ===")

    print(
        out[
            [
                "huc8",
                "sites",
                "unique_population_within_5km",
                "water_footprint_m3",
                "water_scarcity_footprint_m3_eq",
                "wf_rank",
                "wsf_rank",
            ]
        ]
        .head(15)
        .to_string(index=False)
    )

    # ----------------------------------------------------
    # Figure
    # ----------------------------------------------------

    valid = out[
        (out["unique_population_within_5km"] > 0)
        &
        (
            out[
                "water_scarcity_footprint_m3_eq"
            ] > 0
        )
        &
        (
            ~out[
                "has_incomplete_population_site"
            ]
        )
    ].copy()

    fig, ax = plt.subplots(
        figsize=(8.5, 6.5)
    )

    sizes = (
        35
        +
        valid["sites"].clip(
            upper=50
        )
        * 5
    )

    ax.scatter(
        valid[
            "unique_population_within_5km"
        ],
        valid[
            "water_scarcity_footprint_m3_eq"
        ],
        s=sizes,
        alpha=0.55,
    )

    ax.set_xscale("log")
    ax.set_yscale("log")

    ax.set_xlabel(
        "Unique nearby population within 5 km"
    )

    ax.set_ylabel(
        "2030 moderate WSF (m³-eq/year)"
    )

    ax.set_title(
        "Community proximity and scarcity-weighted water burden by watershed"
    )

    ax.grid(
        alpha=0.25
    )

    top = valid.nlargest(
        8,
        "water_scarcity_footprint_m3_eq",
    )

    for _, row in top.iterrows():

        ax.annotate(
            row["huc8"],
            (
                row[
                    "unique_population_within_5km"
                ],
                row[
                    "water_scarcity_footprint_m3_eq"
                ],
            ),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=8,
        )

    fig.text(
        0.5,
        -0.02,
        "Population is area-weighted and counted once within each watershed's "
        "dissolved 5-km site buffers; proximity does not imply direct exposure.",
        ha="center",
        fontsize=9,
    )

    fig.tight_layout()

    fig.savefig(
        FIG_PNG,
        dpi=300,
        bbox_inches="tight",
    )

    fig.savefig(
        FIG_PDF,
        bbox_inches="tight",
    )

    plt.close(fig)

    print(
        "\nWrote:",
        OUTPUT,
    )

    print(
        "Wrote:",
        FIG_PNG,
    )

    print(
        "Wrote:",
        FIG_PDF,
    )


if __name__ == "__main__":
    main()
