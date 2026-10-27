"""
Local climate adjustment for data center cooling demand.

The energy module uses one power usage effectiveness (PUE) of 1.40 for every
facility, so a data center in a hot place and one in a cool place are given
the same cooling overhead. This module gives each site a local climate
figure, cooling degree days (CDD), and turns it into a site-specific PUE.

Steps:

  1. Find the nearest NOAA GHCN-Daily station that actually reported daily
     maximum and minimum temperature over the study years. The nearest
     station alone is not enough: many report only precipitation, or have
     long gaps.
  2. For each day, mean temperature in degrees F = (TMAX + TMIN) / 2, and
     CDD = max(0, mean - 65). Sum per year, then average across years.
  3. PUE_site = 1 + (BASE_PUE - 1) x (CDD_site / CDD_ref), where CDD_ref is
     the median CDD across the sites being processed.

Step 3 is an assumption, not a fitted relationship: it treats the whole
non-IT overhead (0.40 at PUE 1.40) as cooling that scales in proportion to
CDD. Real facilities have overhead that does not depend on weather
(lighting, power conversion losses), and free-air cooling makes the link
non-linear. The formula is used because it is transparent and keeps the
typical site at the energy module's existing PUE, not because it is
accurate for any particular facility.

Usage (normally called from population_exposure.py):
    from temperature_adjustment import adjust_for_temperature

Author: Diya Patidar
AI-assisted: yes (reviewed by Diya Patidar)
"""

from __future__ import annotations

import calendar
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import requests

GHCN_BASE = "https://www.ncei.noaa.gov/pub/data/ghcn/daily"

# Study period, matching the years the water module uses for streamflow.
FIRST_YEAR = 2014
LAST_YEAR = 2024

# Cooling degree days are conventionally measured against 65 degrees F.
CDD_BASE_F = 65.0

# The energy module's fixed PUE. The 0.40 above 1.0 is the overhead that
# this module lets vary with climate.
BASE_PUE = 1.40

# A year counts only if at least this share of its days have both TMAX and
# TMIN. A station is used only if at least MIN_YEARS years count.
MIN_DAY_SHARE = 0.90
MIN_YEARS = 8

# How many of the nearest candidate stations to try before giving up.
MAX_STATIONS_TRIED = 5

CONUS_ALBERS = "EPSG:5070"


# --------------------------------------------------------------------------
# Pure calculations (no network; covered by unit tests)
# --------------------------------------------------------------------------

def tenths_c_to_f(values):
    """Convert GHCN-Daily temperatures, stored as tenths of a degree C, to F.

    A raw value of 172 means 17.2 degrees C, which is 62.96 degrees F.
    """
    celsius = np.asarray(values, dtype=float) / 10.0
    return celsius * 9.0 / 5.0 + 32.0


def annual_cdd(daily, first_year=FIRST_YEAR, last_year=LAST_YEAR):
    """Cooling degree days per year from daily TMAX and TMIN in degrees F.

    `daily` has a DatetimeIndex and columns tmax_f and tmin_f. Days missing
    either value are ignored. A year with at least MIN_DAY_SHARE of its days
    observed is marked usable, and its total is the mean CDD per observed
    day times the number of days in the year, so a few missing days do not
    pull the total down. Years below that share are reported but not used.

    Returns a DataFrame indexed by year with columns days_observed, usable
    and cdd.
    """
    complete = daily.dropna(subset=["tmax_f", "tmin_f"])
    mean_f = (complete["tmax_f"] + complete["tmin_f"]) / 2.0
    day_cdd = (mean_f - CDD_BASE_F).clip(lower=0.0)

    rows = []
    for year in range(first_year, last_year + 1):
        in_year = day_cdd[day_cdd.index.year == year]
        days_in_year = 366 if calendar.isleap(year) else 365
        observed = len(in_year)
        usable = observed >= MIN_DAY_SHARE * days_in_year
        cdd = in_year.mean() * days_in_year if usable else np.nan
        rows.append({"year": year, "days_observed": observed,
                     "usable": usable, "cdd": cdd})

    return pd.DataFrame(rows).set_index("year")


def mean_annual_cdd(yearly):
    """Average CDD over usable years, or NaN if too few years are usable.

    Returns (mean CDD, number of usable years).
    """
    usable = yearly[yearly["usable"]]
    if len(usable) < MIN_YEARS:
        return np.nan, len(usable)
    return usable["cdd"].mean(), len(usable)


def cooling_adjustment(cdd, cdd_ref, base_pue=BASE_PUE):
    """Site-specific PUE from cooling degree days.

    PUE_site = 1 + (base_pue - 1) x (cdd / cdd_ref). A site at the reference
    climate keeps base_pue; a site with no cooling degree days gets 1.0
    (no overhead). This is a documented assumption, not a fitted value; see
    the module docstring.

    Returns (cdd_ratio, pue_adjusted).
    """
    ratio = np.asarray(cdd, dtype=float) / float(cdd_ref)
    return ratio, 1.0 + (base_pue - 1.0) * ratio


# --------------------------------------------------------------------------
# NOAA data loading
# --------------------------------------------------------------------------

def download(url, path):
    """Fetch `url` to `path` unless it is already on disk."""
    path = Path(path)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"  Downloading {url.rsplit('/', 1)[-1]}")
    response = requests.get(url, timeout=300)
    if response.status_code != 200:
        sys.exit(f"NOAA download failed (HTTP {response.status_code}): {url}")
    path.write_bytes(response.content)
    return path


def load_candidate_stations(cache_dir):
    """US stations whose inventory lists TMAX and TMIN across the study years.

    The inventory only gives first and last years, not gaps, so a station
    that passes here can still fail the completeness check in annual_cdd().
    Returns a GeoDataFrame in EPSG:5070 with station_id and geometry.
    """
    path = download(f"{GHCN_BASE}/ghcnd-inventory.txt",
                    Path(cache_dir) / "ghcnd-inventory.txt")

    # Fixed-width layout documented in NOAA's GHCN-Daily readme.
    inventory = pd.read_fwf(
        path,
        colspecs=[(0, 11), (12, 20), (21, 30), (31, 35), (36, 40), (41, 45)],
        names=["station_id", "lat", "lon", "element", "first", "last"],
        dtype={"station_id": str, "element": str},
    )
    inventory = inventory[
        inventory["station_id"].str.startswith("US")
        & inventory["element"].isin(["TMAX", "TMIN"])
        & (inventory["first"] <= FIRST_YEAR)
        & (inventory["last"] >= LAST_YEAR)
    ]

    # Keep stations that have both elements, not just one.
    both = inventory.groupby("station_id")["element"].nunique() == 2
    stations = (inventory[inventory["station_id"].isin(both[both].index)]
                .drop_duplicates("station_id"))

    return gpd.GeoDataFrame(
        stations[["station_id"]].reset_index(drop=True),
        geometry=gpd.points_from_xy(stations["lon"], stations["lat"]),
        crs="EPSG:4326",
    ).to_crs(CONUS_ALBERS)


def load_station_daily(station_id, cache_dir):
    """Daily TMAX and TMIN in degrees F for one station over the study years.

    Readings carrying a quality flag (QFLAG) failed one of NOAA's checks and
    are dropped. Returns a DataFrame with a DatetimeIndex and columns tmax_f
    and tmin_f.
    """
    path = download(f"{GHCN_BASE}/by_station/{station_id}.csv.gz",
                    Path(cache_dir) / "by_station" / f"{station_id}.csv.gz")

    raw = pd.read_csv(
        path, header=None, dtype=str,
        names=["station_id", "date", "element", "value", "mflag", "qflag",
               "sflag", "obs_time"],
    )
    raw = raw[raw["element"].isin(["TMAX", "TMIN"]) & raw["qflag"].isna()]
    raw["date"] = pd.to_datetime(raw["date"], format="%Y%m%d")
    raw = raw[raw["date"].dt.year.between(FIRST_YEAR, LAST_YEAR)]
    raw["value_f"] = tenths_c_to_f(raw["value"])

    if raw.empty:
        return pd.DataFrame(columns=["tmax_f", "tmin_f"],
                            index=pd.DatetimeIndex([], name="date"))

    daily = raw.pivot_table(index="date", columns="element",
                            values="value_f", aggfunc="first")
    daily = daily.reindex(columns=["TMAX", "TMIN"])
    return daily.rename(columns={"TMAX": "tmax_f", "TMIN": "tmin_f"})


# --------------------------------------------------------------------------
# Entry point for the pipeline
# --------------------------------------------------------------------------

def adjust_for_temperature(sites, cache_dir="data/raw/noaa/ghcnd"):
    """Attach a weather station, annual CDD and adjusted PUE to each site.

    `sites` is a GeoDataFrame in EPSG:5070 with a site_id column. For each
    site the nearest candidate stations are tried in order of distance, and
    the first one passing the completeness rules is used. Station results
    are cached, so a cluster of sites sharing one station costs a single
    download.

    The CDD reference is the median CDD across these sites, so the typical
    site keeps BASE_PUE. PUE_site = 1 + (BASE_PUE - 1) x (CDD / CDD_ref) is
    a documented assumption, not a fitted value.

    Returns a DataFrame with site_id, station_id, station_distance_km,
    cdd_years_used, cdd_annual, cdd_ratio and pue_adjusted.
    """
    stations = load_candidate_stations(cache_dir)
    print(f"  {len(stations)} candidate stations with TMAX and TMIN "
          f"{FIRST_YEAR}-{LAST_YEAR}")

    station_cache = {}  # station_id -> (mean CDD, usable years)
    rows = []

    for site_id, point in zip(sites["site_id"], sites.geometry):
        distances = stations.geometry.distance(point)
        nearest = distances.nsmallest(MAX_STATIONS_TRIED).index

        chosen = None
        for idx in nearest:
            station_id = stations.at[idx, "station_id"]
            if station_id not in station_cache:
                yearly = annual_cdd(load_station_daily(station_id, cache_dir))
                station_cache[station_id] = mean_annual_cdd(yearly)
            cdd, years = station_cache[station_id]
            if not np.isnan(cdd):
                chosen = (station_id, distances[idx] / 1000.0, years, cdd)
                break

        if chosen is None:
            print(f"  No complete station among the {MAX_STATIONS_TRIED} "
                  f"nearest to site {site_id}; left blank")
            chosen = (pd.NA, np.nan, 0, np.nan)

        rows.append(dict(zip(["site_id", "station_id", "station_distance_km",
                              "cdd_years_used", "cdd_annual"],
                             [site_id, *chosen])))

    result = pd.DataFrame(rows)
    cdd_ref = result["cdd_annual"].median()
    result["cdd_ratio"], result["pue_adjusted"] = cooling_adjustment(
        result["cdd_annual"], cdd_ref)

    print(f"  {result['station_id'].nunique()} stations used; "
          f"CDD reference (median of sites) = {cdd_ref:,.0f}")
    return result
