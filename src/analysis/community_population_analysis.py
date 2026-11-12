"""Population/community proximity analysis for the data-center impact project.

This module:
1. validates site-level population estimates within 1/3/5 km;
2. computes unique population within at least one mapped site buffer using
   dissolved buffers so people are not double-counted across nearby sites;
3. optionally joins the 2030 moderate temporal-water results to population;
4. creates population figures for the final results package.

Important interpretation:
- Population values are area-weighted tract estimates.
- Nearby population is a proximity/context metric, not proof of health exposure.
- Do not sum site-level pop_1km/pop_3km/pop_5km nationally because site buffers overlap.
- Population source/vintage should be documented separately; this script does not assume it.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[2]

EXPOSURE_PATH = ROOT / "data/processed/community_exposure.csv"
TRACTS_PATH = ROOT / "data/processed/tracts_near_sites.gpkg"
MASTER_PATH = ROOT / "data/processed/master_sites.csv"
TEMPORAL_WATER_PATH = ROOT / "outputs/temporal_water_2023_2030.csv"

OUTPUT_DIR = ROOT / "outputs"
FIGURE_DIR = OUTPUT_DIR / "figures"


def _millions(value, _position=None):
    return f"{value / 1e6:.1f}M"


def load_exposure(path: Path = EXPOSURE_PATH) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        dtype={
            "site_id": "string",
            "source_site_id": "string",
            "tract_geoid": "string",
        },
    )

    required = {
        "site_id",
        "latitude",
        "longitude",
        "tract_population",
        "pop_1km",
        "pop_3km",
        "pop_5km",
        "incomplete_pop_1km",
        "incomplete_pop_3km",
        "incomplete_pop_5km",
    }

    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Exposure file missing required columns: {missing}")

    if df["site_id"].isna().any():
        raise ValueError("Exposure file contains missing site_id values.")

    if df["site_id"].duplicated().any():
        dupes = df.loc[df["site_id"].duplicated(), "site_id"].tolist()
        raise ValueError(f"Exposure file contains duplicate site IDs: {dupes[:10]}")

    return df


def load_tracts(path: Path = TRACTS_PATH) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)

    required = {"GEOID", "population", "tract_area_m2", "geometry"}
    missing = sorted(required - set(gdf.columns))
    if missing:
        raise ValueError(f"Tract GeoPackage missing required columns: {missing}")

    if gdf.crs is None:
        raise ValueError("Tract GeoPackage has no CRS.")

    if gdf.geometry.isna().any() or gdf.geometry.is_empty.any():
        raise ValueError("Tract GeoPackage contains missing/empty geometries.")

    return gdf


def compute_unique_population(
    exposure: pd.DataFrame,
    tracts: gpd.GeoDataFrame,
    radius_km: int,
) -> tuple[float, int]:
    """Area-weighted population within any site buffer, counting overlap once."""

    sites = gpd.GeoDataFrame(
        exposure[["site_id"]].copy(),
        geometry=gpd.points_from_xy(
            exposure["longitude"],
            exposure["latitude"],
        ),
        crs="EPSG:4326",
    ).to_crs(tracts.crs)

    buffers = sites.geometry.buffer(radius_km * 1000)
    dissolved = unary_union(list(buffers))

    candidates = tracts.loc[
        tracts.geometry.intersects(dissolved)
    ].copy()

    intersection_area = candidates.geometry.intersection(dissolved).area

    fraction = (
        intersection_area
        / pd.to_numeric(candidates["tract_area_m2"], errors="coerce")
    ).clip(lower=0, upper=1)

    population = pd.to_numeric(
        candidates["population"], errors="coerce"
    )

    unique_population = (population * fraction).sum(min_count=1)

    return float(unique_population), int(len(candidates))


def build_population_summary(
    exposure: pd.DataFrame,
    tracts: gpd.GeoDataFrame,
) -> pd.DataFrame:
    rows = []

    for radius in (1, 3, 5):
        col = f"pop_{radius}km"
        incomplete = f"incomplete_pop_{radius}km"

        unique_population, intersecting_tracts = compute_unique_population(
            exposure,
            tracts,
            radius,
        )

        values = pd.to_numeric(exposure[col], errors="coerce")

        rows.append(
            {
                "radius_km": radius,
                "unique_population_within_any_site_buffer": unique_population,
                "intersecting_tracts": intersecting_tracts,
                "site_records": int(len(exposure)),
                "sites_with_complete_population_buffer": int((~exposure[incomplete]).sum()),
                "sites_with_incomplete_population_buffer": int(exposure[incomplete].sum()),
                "site_level_population_median": float(values.median()),
                "site_level_population_q25": float(values.quantile(0.25)),
                "site_level_population_q75": float(values.quantile(0.75)),
                "site_level_population_p90": float(values.quantile(0.90)),
                "site_level_population_p95": float(values.quantile(0.95)),
                "site_level_population_max": float(values.max()),
            }
        )

    return pd.DataFrame(rows)


def join_population_to_water(
    exposure: pd.DataFrame,
    water_path: Path = TEMPORAL_WATER_PATH,
) -> pd.DataFrame | None:
    """Join population context to the 2030 moderate water model."""

    if not water_path.exists():
        print(
            f"Skipping water-population join because {water_path} does not exist."
        )
        return None

    water = pd.read_csv(
        water_path,
        dtype={"site_id": "string", "huc8": "string"},
    )

    required = {
        "site_id",
        "scenario",
        "year",
        "water_status",
        "projected_energy_mwh",
        "annual_water_footprint_m3",
        "annual_water_scarcity_footprint_m3_eq",
    }

    missing = sorted(required - set(water.columns))
    if missing:
        raise ValueError(
            f"Temporal water output missing required columns: {missing}"
        )

    water = water.loc[
        (water["scenario"] == "moderate")
        & (water["year"] == 2030)
    ].copy()

    if water["site_id"].duplicated().any():
        raise ValueError(
            "2030 moderate temporal-water subset contains duplicate site IDs."
        )

    out = water.merge(
        exposure,
        on="site_id",
        how="left",
        validate="one_to_one",
        suffixes=("", "_population"),
    )

    if MASTER_PATH.exists():
        master = pd.read_csv(
            MASTER_PATH,
            dtype={"site_id": "string"},
        )

        optional = [
            c
            for c in [
                "site_id",
                "site_name",
                "operator",
                "state_abbr",
                "county",
                "site_type",
            ]
            if c in master.columns
        ]

        if optional and "site_id" in optional:
            out = out.merge(
                master[optional],
                on="site_id",
                how="left",
                validate="one_to_one",
            )

    # Contextual intensity only. This is NOT a health-risk estimate.
    valid_5km = (
        (~out["incomplete_pop_5km"].fillna(True))
        & (pd.to_numeric(out["pop_5km"], errors="coerce") > 0)
    )

    out["wf_m3_per_10k_nearby_population"] = pd.NA
    out["wsf_m3_eq_per_10k_nearby_population"] = pd.NA

    out.loc[
        valid_5km, "wf_m3_per_10k_nearby_population"
    ] = (
        pd.to_numeric(
            out.loc[valid_5km, "annual_water_footprint_m3"],
            errors="coerce",
        )
        / pd.to_numeric(out.loc[valid_5km, "pop_5km"], errors="coerce")
        * 10_000
    )

    out.loc[
        valid_5km, "wsf_m3_eq_per_10k_nearby_population"
    ] = (
        pd.to_numeric(
            out.loc[
                valid_5km,
                "annual_water_scarcity_footprint_m3_eq",
            ],
            errors="coerce",
        )
        / pd.to_numeric(out.loc[valid_5km, "pop_5km"], errors="coerce")
        * 10_000
    )

    estimated = out.loc[
        (out["water_status"] == "estimated")
        & valid_5km
    ].copy()

    if not estimated.empty:
        population_q75 = estimated["pop_5km"].quantile(0.75)
        wsf_q75 = estimated[
            "annual_water_scarcity_footprint_m3_eq"
        ].quantile(0.75)

        out["high_population_high_wsf"] = False
        out.loc[
            (
                (out["water_status"] == "estimated")
                & valid_5km
                & (out["pop_5km"] >= population_q75)
                & (
                    out["annual_water_scarcity_footprint_m3_eq"]
                    >= wsf_q75
                )
            ),
            "high_population_high_wsf",
        ] = True

        out.attrs["population_q75"] = float(population_q75)
        out.attrs["wsf_q75"] = float(wsf_q75)

    return out


def save_population_reach_figure(summary: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5.2))

    labels = [
        f"{int(radius)} km"
        for radius in summary["radius_km"]
    ]

    values = summary[
        "unique_population_within_any_site_buffer"
    ]

    bars = ax.bar(labels, values)

    ax.set_title(
        "Estimated population within proximity of at least one mapped data-center site"
    )
    ax.set_xlabel("Distance from mapped IM3 site")
    ax.set_ylabel("Unique population estimate")
    ax.yaxis.set_major_formatter(FuncFormatter(_millions))
    ax.grid(axis="y", alpha=0.25)

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{value / 1e6:.2f}M",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    fig.text(
        0.5,
        -0.02,
        "Area-weighted tract estimate; overlapping site buffers are dissolved "
        "before population is counted.",
        ha="center",
        fontsize=9,
    )

    fig.tight_layout()

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    fig.savefig(
        FIGURE_DIR / "figure5a_population_proximity.png",
        dpi=300,
        bbox_inches="tight",
    )
    fig.savefig(
        FIGURE_DIR / "figure5a_population_proximity.pdf",
        bbox_inches="tight",
    )

    plt.close(fig)


def save_population_wsf_figure(joined: pd.DataFrame) -> None:
    x = joined.loc[
        (joined["water_status"] == "estimated")
        & (~joined["incomplete_pop_5km"].fillna(True))
        & (pd.to_numeric(joined["pop_5km"], errors="coerce") > 0)
        & (
            pd.to_numeric(
                joined["annual_water_scarcity_footprint_m3_eq"],
                errors="coerce",
            )
            > 0
        )
    ].copy()

    if x.empty:
        print("No rows available for population-vs-WSF figure.")
        return

    fig, ax = plt.subplots(figsize=(8, 6))

    ax.scatter(
        x["pop_5km"],
        x["annual_water_scarcity_footprint_m3_eq"],
        alpha=0.5,
        s=28,
    )

    ax.set_xscale("log")
    ax.set_yscale("log")

    ax.set_title(
        "Nearby population and modeled scarcity-weighted water impact"
    )
    ax.set_xlabel("Area-weighted population within 5 km")
    ax.set_ylabel("2030 moderate WSF (m³-eq/year)")
    ax.grid(alpha=0.25)

    fig.text(
        0.5,
        -0.02,
        "Proximity is community context, not evidence of direct health exposure "
        "or shared water-supply exposure.",
        ha="center",
        fontsize=9,
    )

    fig.tight_layout()

    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    fig.savefig(
        FIGURE_DIR / "figure5b_population_vs_wsf_2030.png",
        dpi=300,
        bbox_inches="tight",
    )
    fig.savefig(
        FIGURE_DIR / "figure5b_population_vs_wsf_2030.pdf",
        bbox_inches="tight",
    )

    plt.close(fig)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    exposure = load_exposure()
    tracts = load_tracts()

    summary = build_population_summary(exposure, tracts)

    summary_path = OUTPUT_DIR / "community_population_proximity_summary.csv"
    summary.to_csv(summary_path, index=False)

    print("=== POPULATION PROXIMITY SUMMARY ===")
    print(summary.to_string(index=False))
    print("\nWrote:", summary_path)

    incomplete = exposure.loc[
        exposure[
            [
                "incomplete_pop_1km",
                "incomplete_pop_3km",
                "incomplete_pop_5km",
            ]
        ].any(axis=1)
    ].copy()

    incomplete_path = OUTPUT_DIR / "community_population_incomplete_buffers.csv"
    incomplete.to_csv(incomplete_path, index=False)
    print("Wrote:", incomplete_path)

    save_population_reach_figure(summary)

    joined = join_population_to_water(exposure)

    if joined is not None:
        joined_path = OUTPUT_DIR / "community_exposure_2030_moderate.csv"
        joined.to_csv(joined_path, index=False)
        print("Wrote:", joined_path)

        high_high = joined.loc[
            joined.get(
                "high_population_high_wsf",
                pd.Series(False, index=joined.index),
            )
        ].copy()

        if not high_high.empty:
            high_high = high_high.sort_values(
                [
                    "annual_water_scarcity_footprint_m3_eq",
                    "pop_5km",
                ],
                ascending=False,
            )

            high_high_path = (
                OUTPUT_DIR
                / "community_high_population_high_wsf_2030.csv"
            )
            high_high.to_csv(high_high_path, index=False)
            print("Wrote:", high_high_path)

        save_population_wsf_figure(joined)

    print(
        "\nInterpretation note: nearby population is a proximity/context metric. "
        "Do not describe these residents as directly affected without an "
        "exposure pathway analysis."
    )


if __name__ == "__main__":
    main()
