"""
Estimate how strongly local climate changes a data center's PUE (the value k),
then give every IM3 site its own climate-adjusted PUE.

Why this exists: the energy model uses PUE 1.40 for every facility, and the
manual adjust_for_temperature() needed a value of k that was only a guess.
Here k is measured from operators that publish PUE for named sites or regions
(Google per campus, Microsoft and AWS per region; sources and periods are in
data/model_parameters/observed_pue.csv).

Steps:

  1. Load the observed PUE table and turn each row into a point.
  2. Give each point its cooling degree days (CDD) from the nearest complete
     NOAA GHCN-Daily station, reusing temperature_adjustment.py.
  3. Within each operator, compare every facility's overhead (PUE - 1) with
     that operator's average overhead, and its CDD with that operator's
     average CDD. Comparing inside each operator keeps one company's overall
     efficiency, or a fleet sitting mostly in hot places, from posing as a
     climate effect. The slope between the two is k (manual fit_slope()).
  4. For every site, PUE_site = 1 + 0.40 x adjust_for_temperature(CDD_site,
     CDD_ref, k), with CDD_ref the median site CDD, for the fitted k and for
     fixed comparison values of k.

The output is a separate table. The energy model still uses 1.40 until its
owner chooses to read the pue_k_* columns.

Limits worth stating: 29 facilities with coordinates from three operators;
Microsoft and AWS rows are regions, each placed at the average of that
company's IM3 buildings; PUE years (2022-2026) are later than the CDD years
(2014-2024); published PUEs run 1.04-1.31, below the unsourced 1.40 the energy
model assumes; k is a straight-line fit, and is applied to sites relative to a
different reference climate than the one it was fitted around.

Usage, from the repository root:
    python -m extra_functions.pue_climate --sites data/processed/master_sites.csv

Author: Diya Patidar
AI-assisted: yes (to be reviewed by Diya Patidar)
"""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

if __package__:
    from . import population_exposure_manual as manual
    from .population_exposure import load_sites
    from .temperature_adjustment import (BASE_PUE, CONUS_ALBERS,
                                         adjust_for_temperature)
else:
    import population_exposure_manual as manual
    from population_exposure import load_sites
    from temperature_adjustment import (BASE_PUE, CONUS_ALBERS,
                                        adjust_for_temperature)

OBSERVED_PUE_FILE = "data/model_parameters/observed_pue.csv"

# Fixed values of k reported next to the fitted one, so a reader can see how
# much the answer depends on k: 0 = weather has no effect, 1 = what the
# pipeline assumed before, 0.15 = the manual worked example.
COMPARISON_K = [0.0, 0.15, 0.5, 1.0]

# Only the columns temperature_adjustment returns that this file needs. Its
# own pue_adjusted column uses k = 1 and is deliberately dropped here.
CLIMATE_COLUMNS = ["site_id", "station_id", "station_distance_km",
                   "cdd_years_used", "cdd_annual"]


def load_observed_pue(path=OBSERVED_PUE_FILE):
    """Load published PUE values as points in EPSG:5070.

    Rows without coordinates are dropped and named, rather than guessed.

    Args:
        path: CSV with operator, location, pue, latitude, longitude.
    Returns:
        GeoDataFrame with site_id ("operator: location"), operator, pue and
        geometry.
    """
    table = pd.read_csv(path)

    required = {"operator", "location", "pue", "latitude", "longitude"}
    missing = required - set(table.columns)
    if missing:
        raise ValueError(f"Observed PUE file is missing columns: {sorted(missing)}")

    no_coords = table["latitude"].isna() | table["longitude"].isna()
    for name in table.loc[no_coords, "location"]:
        print(f"  Skipping {name}: no coordinates in the observed PUE file")
    table = table[~no_coords].copy()

    if (table["pue"] < 1).any():
        raise ValueError("A published PUE below 1 is impossible; check the file")

    table["site_id"] = table["operator"] + ": " + table["location"]
    if table["site_id"].duplicated().any():
        raise ValueError("Each operator and location pair must appear once")

    points = gpd.GeoDataFrame(
        table[["site_id", "operator", "pue"]],
        geometry=gpd.points_from_xy(table["longitude"], table["latitude"]),
        crs="EPSG:4326",
    )
    return points.to_crs(CONUS_ALBERS)


def estimate_k(observed):
    """Fit k from facilities with a published PUE and a CDD value.

    Each facility is compared with its own operator on both axes: overhead
    against the operator's average overhead, CDD against the operator's
    average CDD. An efficient company, or one whose buildings are mostly in
    hot places, then shifts nothing; only differences inside a company count.

    Args:
        observed: DataFrame with operator, pue and cdd_annual columns.
    Returns:
        (k, points, per_operator): the pooled k; a DataFrame of every facility
        used with its x and y; and a dict of k fitted for each operator alone
        (only operators with at least three facilities).
    """
    usable = observed.dropna(subset=["cdd_annual"]).copy()
    for name in observed.loc[observed["cdd_annual"].isna(), "site_id"]:
        print(f"  No complete weather station for {name}; left out of the fit")

    pieces = []
    for operator, group in usable.groupby("operator"):
        # One facility has nothing to be compared with inside its operator.
        if len(group) < 2:
            print(f"  {operator} has only one facility with CDD; left out")
            continue

        group = group.copy()
        operator_cdd = group["cdd_annual"].mean()
        group["y"] = manual.overhead_differences(group["pue"].tolist())
        group["x"] = manual.climate_differences(group["cdd_annual"].tolist(),
                                                operator_cdd)
        group["operator_mean_cdd"] = operator_cdd
        pieces.append(group)

    points = pd.concat(pieces, ignore_index=True)
    k = manual.fit_slope(points["x"].tolist(), points["y"].tolist())

    per_operator = {}
    for operator, group in points.groupby("operator"):
        if len(group) >= 3:
            per_operator[operator] = manual.fit_slope(group["x"].tolist(),
                                                      group["y"].tolist())

    return k, points, per_operator


def site_pue(site_climate, k_values, base_pue=BASE_PUE):
    """Climate-adjusted PUE for every site, one column per value of k.

    PUE_site = 1 + (base_pue - 1) x adjust_for_temperature(CDD, CDD_ref, k),
    with CDD_ref the median CDD of the sites, so the typical site keeps
    base_pue whatever k is. Sites with no weather station stay blank.

    Args:
        site_climate: DataFrame with site_id and cdd_annual.
        k_values: dict of column label -> k.
        base_pue: PUE before any climate adjustment.
    Returns:
        DataFrame with site_id, cdd_annual and a pue_k_<label> column per k.
    """
    result = site_climate[["site_id", "cdd_annual"]].copy()
    reference_cdd = statistics.median(result["cdd_annual"].dropna())

    for label, k in k_values.items():
        # adjust_for_temperature refuses a negative k. A negative fitted k
        # would mean hotter places run more efficiently, which needs looking
        # at before it is applied to anything.
        if k < 0:
            raise ValueError(f"k = {k:.3f} is negative; inspect the fit first")

        column = []
        for cdd in result["cdd_annual"]:
            if pd.isna(cdd):
                column.append(np.nan)
            else:
                multiplier = manual.adjust_for_temperature(cdd, reference_cdd, k)
                column.append(1.0 + (base_pue - 1.0) * multiplier)
        result[f"pue_k_{label}"] = column

    return result


def main():
    """Fit k from published PUE, then write a climate-adjusted PUE per site."""
    parser = argparse.ArgumentParser(
        description="Fit k from published PUE and adjust each site's PUE."
    )
    parser.add_argument("--sites", default="data/processed/master_sites.csv")
    parser.add_argument("--observed", default=OBSERVED_PUE_FILE)
    parser.add_argument("--noaa-dir", default="data/raw/noaa/ghcnd")
    parser.add_argument("--out", default="data/processed/site_pue_climate.csv")
    parser.add_argument("--report", default="data/processed/k_estimate.json")
    args = parser.parse_args()

    print("Facilities with published PUE:")
    observed = load_observed_pue(args.observed)
    observed_climate = adjust_for_temperature(observed[["site_id", "geometry"]],
                                              args.noaa_dir)
    observed = observed.drop(columns="geometry").merge(
        observed_climate[CLIMATE_COLUMNS], on="site_id", how="left")

    k, points, per_operator = estimate_k(observed)
    print(f"\nFitted k = {k:.3f} from {len(points)} facilities")
    for operator, value in per_operator.items():
        print(f"  {operator} alone: k = {value:.3f}")

    print("\nIM3 sites:")
    sites = load_sites(args.sites)
    site_climate = adjust_for_temperature(sites, args.noaa_dir)[CLIMATE_COLUMNS]

    k_values = {f"{value:g}": value for value in COMPARISON_K}
    k_values["fitted"] = k
    table = site_climate.merge(site_pue(site_climate, k_values),
                               on=["site_id", "cdd_annual"], how="left")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    table.to_csv(out_path, index=False)

    report = {
        "k_fitted": k,
        "k_by_operator": per_operator,
        "facilities_used": len(points),
        "reference_cdd_sites": statistics.median(site_climate["cdd_annual"].dropna()),
        "facilities": points[["site_id", "operator", "pue", "cdd_annual",
                              "operator_mean_cdd", "x", "y"]].to_dict(orient="records"),
    }
    Path(args.report).write_text(json.dumps(report, indent=2) + "\n")

    print(f"\nWrote {len(table)} sites to {out_path} and the fit to {args.report}")


if __name__ == "__main__":
    main()
