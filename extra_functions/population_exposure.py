"""
Community population exposure for data center sites.

Estimates how many people live near each data center, in two ways:

  1. Containing-tract exposure (simple): the population of the single census
     tract the facility's coordinate falls inside.
  2. Radius exposure (areal apportionment): for circles of a given radius
     around the facility, the share of each overlapping tract's population
     that falls inside the circle, summed.

The second method exists because census tract boundaries are drawn for
census-taking, not for anything to do with data centers. A facility near the
edge of a large rural tract can sit 500 m from a dense neighbourhood in the
next tract over; the containing-tract number misses those people entirely.
Areal apportionment assumes population is spread evenly within each tract,
which is not true, but it is a standard approximation and is documented as a
limitation rather than hidden.

Inputs are read from local files when present and downloaded otherwise, so
the script runs without any manual setup.

Usage:
    python population_exposure.py --sites data/processed/master_sites.csv
    python population_exposure.py --sites <IM3 atlas csv> --site-states 51 42

Author: Diya Patidar
AI-assisted: yes (reviewed by Diya Patidar)
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import requests

from extra_functions.temperature_adjustment import adjust_for_temperature

# Equal-area projection for the continental US. Distances are metres and
# polygon areas are correct, which is required before any buffering. Doing
# this work in raw latitude/longitude would silently produce wrong numbers,
# because a "radius of 5" in degrees is several hundred kilometres.
CONUS_ALBERS = "EPSG:5070"

# TIGER/Line ships in NAD83.
TIGER_CRS = "EPSG:4269"

# EPSG:5070 is defined for the continental US only. Sites in these states and
# territories are excluded rather than given distorted areas.
NON_CONUS_FIPS = {"02", "15", "60", "66", "69", "72", "78"}

TIGER_YEAR = "2024"
ACS_YEAR = "2023"
DEFAULT_RADII_KM = (1.0, 3.0, 5.0)

# Total population, ACS 5-year detailed table.
ACS_VARIABLE = "B01003_001E"


# --------------------------------------------------------------------------
# Column discovery
# --------------------------------------------------------------------------

def find_column(frame, candidates, label):
    """Return the first column in `frame` matching one of `candidates`.

    Matching ignores case and surrounding whitespace. Raises SystemExit with
    the available column names if nothing matches, so that an unexpected file
    layout fails loudly instead of being guessed at.
    """
    normalised = {str(col).strip().lower(): col for col in frame.columns}
    for candidate in candidates:
        if candidate in normalised:
            return normalised[candidate]
    sys.exit(
        f"Could not find a {label} column.\n"
        f"  Looked for any of: {', '.join(candidates)}\n"
        f"  File has: {', '.join(str(c) for c in frame.columns)}\n"
        f"Rename the column or edit the candidate list in find_column()."
    )


# --------------------------------------------------------------------------
# Site loading
# --------------------------------------------------------------------------

def load_sites(path):
    """Load data center sites as a GeoDataFrame of points in EPSG:5070.

    Accepts either the team's cleaned master_sites.csv or a raw IM3 Atlas
    export. Column names are discovered rather than assumed. Returns a
    GeoDataFrame with columns site_id, state_fips (may be blank) and geometry.
    """
    path = Path(path)
    if not path.exists():
        sys.exit(f"Sites file not found: {path}")

    frame = pd.read_csv(path, dtype=str)
    print(f"Loaded {len(frame)} rows from {path.name}")

    id_col = find_column(frame, ["site_id", "source_site_id", "id"], "site ID")
    lat_col = find_column(frame, ["latitude", "lat", "y"], "latitude")
    lon_col = find_column(frame, ["longitude", "lon", "lng", "long", "x"],
                          "longitude")

    # The team's master schema identifies sites as "im3_" plus the original
    # 11-digit IM3 ID, and keeps the bare ID as source_site_id. A raw IM3
    # export only has the bare ID, so the prefix is added here to make this
    # output join with everyone else's.
    raw_ids = frame[id_col].astype(str).str.strip()
    norm = {str(c).strip().lower(): c for c in frame.columns}
    if "source_site_id" in norm:
        source_ids = frame[norm["source_site_id"]].astype(str).str.strip()
    else:
        source_ids = raw_ids.str.removeprefix("im3_")
    site_ids = raw_ids.where(raw_ids.str.startswith("im3_"), "im3_" + raw_ids)

    sites = pd.DataFrame({
        "site_id": site_ids,
        "source_site_id": source_ids,
        "latitude": pd.to_numeric(frame[lat_col], errors="coerce"),
        "longitude": pd.to_numeric(frame[lon_col], errors="coerce"),
    })

    # state_fips is optional; it is used to decide which TIGER files to fetch
    # and which sites to keep. master_sites.csv calls it state_fips; the raw
    # IM3 Atlas calls the same two-digit FIPS code state_id.
    state_norm = {str(c).strip().lower(): c for c in frame.columns}
    state_col = next(
        (state_norm[c] for c in ["state_fips", "state_id"] if c in state_norm),
        None,
    )
    if state_col is not None:
        sites["state_fips"] = frame[state_col].astype(str).str.zfill(2)
    else:
        sites["state_fips"] = pd.NA

    # The IM3 Atlas lists a few facilities twice, once per county, when they
    # straddle a county line. Rows repeating an ID at identical coordinates
    # describe one facility, so one is kept. A repeated ID at different
    # coordinates is a data error and is refused rather than guessed at.
    repeated = sites.duplicated(subset="site_id", keep=False)
    if repeated.any():
        coords_per_id = (
            sites[repeated].groupby("site_id")[["latitude", "longitude"]]
            .nunique()
        )
        conflicting = coords_per_id[(coords_per_id > 1).any(axis=1)]
        if not conflicting.empty:
            sys.exit(
                f"{len(conflicting)} site IDs repeat with different "
                f"coordinates: {', '.join(conflicting.index[:10])}"
            )
        dropped = sites.duplicated(subset="site_id").sum()
        sites = sites.drop_duplicates(subset="site_id", keep="first")
        print(f"  Dropped {dropped} repeated rows (same ID, same coordinates)")

    bad_coords = sites[["latitude", "longitude"]].isna().any(axis=1).sum()
    if bad_coords:
        print(f"  Dropping {bad_coords} rows with unreadable coordinates")
        sites = sites.dropna(subset=["latitude", "longitude"])

    gdf = gpd.GeoDataFrame(
        sites,
        geometry=gpd.points_from_xy(sites["longitude"], sites["latitude"]),
        crs="EPSG:4326",
    )
    return gdf.to_crs(CONUS_ALBERS)


def find_double_listed(buildings, campuses, points):
    """Return the IDs of IM3 entries that repeat a facility already listed.

    The IM3 Atlas maps the same facility at several levels: a campus outline,
    the building outlines inside it, and sometimes a bare point. Names are
    not consistent between levels (a campus called "AWS" next to a building
    called "Amazon IAD91"), so matching is done on geometry instead:

      - a campus is a repeat if any building outline intersects it;
      - a point is a repeat if it lies inside a building outline, or inside
        a campus that is itself a repeat.

    Building entries are always kept. A campus with no mapped buildings, or
    a point outside every outline, is kept as the only record of that
    facility. All three inputs must share one projected CRS and carry an
    `id` column.
    """
    hits = gpd.sjoin(campuses[["id", "geometry"]], buildings[["geometry"]],
                     predicate="intersects")
    covered = campuses[campuses["id"].isin(hits["id"])]

    in_building = gpd.sjoin(points[["id", "geometry"]],
                            buildings[["geometry"]], predicate="within")
    in_campus = gpd.sjoin(points[["id", "geometry"]], covered[["geometry"]],
                          predicate="within")

    return set(covered["id"]) | set(in_building["id"]) | set(in_campus["id"])


def drop_double_listed(sites, gpkg_path):
    """Remove campus and point entries already represented by buildings.

    Reads the building, campus and point layers of the IM3 GeoPackage and
    drops every site whose ID find_double_listed() reports.
    """
    path = Path(gpkg_path)
    if not path.exists():
        sys.exit(f"IM3 GeoPackage not found: {path}")

    layers = {}
    for name in ["building", "campus", "point"]:
        layer = gpd.read_file(path, layer=name).to_crs(CONUS_ALBERS)
        layer["id"] = layer["id"].astype(str)
        layers[name] = layer

    # The GeoPackage carries bare IM3 IDs, so match on source_site_id.
    repeats = find_double_listed(layers["building"], layers["campus"],
                                 layers["point"])
    keep = ~sites["source_site_id"].isin(repeats)
    print(f"  Dropped {(~keep).sum()} campus/point entries already covered "
          f"by building outlines")
    return sites[keep]


# --------------------------------------------------------------------------
# Census data loading
# --------------------------------------------------------------------------

def resolve_state_list(sites, explicit_states):
    """Decide which states to pull census data for.

    Uses an explicit list when given, otherwise the state_fips column on the
    sites. Non-CONUS states are dropped because the projection does not cover
    them.
    """
    if explicit_states:
        states = {s.zfill(2) for s in explicit_states}
    elif sites["state_fips"].notna().any():
        states = set(sites["state_fips"].dropna().unique())
    else:
        sys.exit(
            "Sites file has no state_fips column, so the states to download "
            "cannot be determined. Pass them explicitly, e.g. --states 51 24 "
            "11, or add a state_fips column."
        )

    excluded = states & NON_CONUS_FIPS
    if excluded:
        print(f"  Skipping non-CONUS states (projection does not cover them): "
              f"{sorted(excluded)}")
    return sorted(states - NON_CONUS_FIPS)


def load_tracts(tiger_dir, state_fips_list):
    """Load census tract polygons, downloading any state files not on disk.

    Returns a single GeoDataFrame in EPSG:5070 with GEOID and geometry.
    """
    tiger_dir = Path(tiger_dir)
    tiger_dir.mkdir(parents=True, exist_ok=True)
    frames = []

    for fips in state_fips_list:
        stem = f"tl_{TIGER_YEAR}_{fips}_tract"
        shp = tiger_dir / f"{stem}.shp"

        if not shp.exists():
            url = (f"https://www2.census.gov/geo/tiger/TIGER{TIGER_YEAR}"
                   f"/TRACT/{stem}.zip")
            print(f"  Downloading tracts for state {fips}")
            response = requests.get(url, timeout=180)
            response.raise_for_status()
            with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
                archive.extractall(tiger_dir)

        frames.append(gpd.read_file(shp))

    tracts = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True))
    tracts = tracts.set_crs(TIGER_CRS, allow_override=True)
    print(f"Loaded {len(tracts)} census tracts across "
          f"{len(state_fips_list)} states")
    return tracts.to_crs(CONUS_ALBERS)


def load_acs(acs_path, state_fips_list, api_key=None):
    """Load tract population, from a local CSV if given or the API otherwise.

    Handles the data.census.gov download layout, which carries a second header
    row of human-readable labels and GEO_ID values such as
    '1400000US51107611300' where only the trailing 11 characters are the
    tract GEOID. The Census API requires a key (free, from
    https://api.census.gov/data/key_signup.html). Returns a DataFrame with
    GEOID and population.
    """
    if acs_path:
        path = Path(acs_path)
        if not path.exists():
            sys.exit(f"ACS file not found: {path}")

        # Row 0 holds the variable codes, row 1 the human-readable labels.
        frame = pd.read_csv(path, dtype=str, skiprows=[1])
        print(f"Loaded {len(frame)} ACS rows from {path.name}")

        geo_col = find_column(frame, ["geo_id", "geoid", "geography"],
                              "GEO_ID")
        pop_col = find_column(frame, [ACS_VARIABLE.lower(), "estimate!!total"],
                              "population estimate")

        # Keep only the trailing tract GEOID so it matches TIGER's GEOID.
        geoid = frame[geo_col].astype(str).str.strip().str[-11:]
        population = pd.to_numeric(frame[pop_col], errors="coerce")
        return pd.DataFrame({"GEOID": geoid, "population": population})

    # No local file: query the API, one state at a time.
    if not api_key:
        sys.exit(
            "The Census API needs a key. Pass --census-key, set the "
            "CENSUS_API_KEY environment variable, or pass --acs with a "
            "data.census.gov CSV export."
        )
    url = f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5"
    records = []
    for fips in state_fips_list:
        params = [("get", ACS_VARIABLE), ("for", "tract:*"),
                  ("in", f"state:{fips}"), ("in", "county:*"),
                  ("key", api_key)]
        print(f"  Requesting ACS population for state {fips}")
        response = requests.get(url, params=params, timeout=180)

        # Report failures without echoing the request URL, which contains
        # the key. An invalid key comes back as an HTML page, not JSON.
        try:
            if response.status_code != 200:
                raise ValueError(f"HTTP {response.status_code}")
            rows = response.json()
        except ValueError as error:
            sys.exit(f"Census API request for state {fips} failed ({error}). "
                     f"Response starts: {response.text[:200]!r}")
        frame = pd.DataFrame(rows[1:], columns=rows[0], dtype=str)
        frame["GEOID"] = frame["state"] + frame["county"] + frame["tract"]
        frame["population"] = pd.to_numeric(frame[ACS_VARIABLE],
                                            errors="coerce")
        records.append(frame[["GEOID", "population"]])

    acs = pd.concat(records, ignore_index=True)
    print(f"Loaded {len(acs)} ACS tract records from the API")
    return acs


def build_tract_layer(tracts, acs):
    """Attach population to tract polygons and precompute tract areas."""
    merged = tracts.merge(acs, on="GEOID", how="left")

    missing = merged["population"].isna().sum()
    if missing:
        print(f"  {missing} tracts have no population figure and contribute "
              f"zero; they are not imputed")

    merged["population"] = merged["population"].fillna(0.0)
    merged["tract_area_m2"] = merged.geometry.area
    return merged[["GEOID", "population", "tract_area_m2", "geometry"]]


# --------------------------------------------------------------------------
# The two exposure methods
# --------------------------------------------------------------------------

# Saved copy of the tract layer, so later runs never re-download Census data.
TRACT_CACHE = "data/processed/tracts_near_sites.gpkg"

# Shapes get simplified by this many metres before saving. It cuts the file
# down by a lot and moves tract areas by a tiny fraction of a percent.
SIMPLIFY_TOLERANCE_M = 5.0


def trim_tracts_to_sites(tracts, sites, radius_km=max(DEFAULT_RADII_KM)):
    """Keep only the tracts that touch some site's largest buffer.

    Only these tracts can ever add people to an exposure number, so the rest
    of the country doesn't need to be saved. Returns a GeoDataFrame in the
    same layout as build_tract_layer().
    """
    circles = sites[["geometry"]].copy()
    circles["geometry"] = circles.geometry.buffer(radius_km * 1000.0)

    near = gpd.sjoin(tracts[["GEOID", "geometry"]], circles,
                     how="inner", predicate="intersects")
    return tracts[tracts["GEOID"].isin(near["GEOID"].unique())].copy()


def save_tract_cache(tracts, path):
    """Simplify the trimmed tracts and save them as a GeoPackage.

    Tract area is recomputed from the simplified shape, so a circle that
    swallows a whole tract still takes exactly all of its population.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    saved = tracts.copy()
    saved["geometry"] = saved.geometry.simplify(SIMPLIFY_TOLERANCE_M,
                                                preserve_topology=True)
    saved["tract_area_m2"] = saved.geometry.area
    saved.to_file(path, driver="GPKG")

    size_mb = path.stat().st_size / 1e6
    print(f"Saved {len(saved)} tracts to {path} ({size_mb:.1f} MB)")
    if size_mb > 50:
        print("  Warning: over 50 MB, GitHub will warn on push; over 100 MB "
              "it will refuse the file")


def load_tract_cache(path):
    """Load the saved tract layer instead of downloading from Census."""
    tracts = gpd.read_file(path)
    tracts = tracts.to_crs(CONUS_ALBERS)
    tracts["GEOID"] = tracts["GEOID"].astype(str)
    print(f"Loaded {len(tracts)} tracts from saved file {path}")
    return tracts[["GEOID", "population", "tract_area_m2", "geometry"]]


def assign_containing_tract(sites, tracts):
    """Exposure as the population of the tract containing each site.

    This is the simple baseline. It is reported alongside the radius figures
    so the two can be compared, not because it is the better estimate.
    """
    joined = gpd.sjoin(
        sites[["site_id", "geometry"]],
        tracts[["GEOID", "population", "geometry"]],
        how="left",
        predicate="within",
    )

    # A site exactly on a shared boundary can match more than one tract.
    # Keep the first match and record that it happened.
    duplicated = joined.duplicated(subset="site_id", keep="first")
    if duplicated.any():
        print(f"  {duplicated.sum()} sites fell on a tract boundary; "
              f"first match kept")
    joined = joined[~duplicated]

    return pd.DataFrame({
        "site_id": joined["site_id"].values,
        "tract_geoid": joined["GEOID"].values,
        "tract_population": joined["population"].values,
    })


def calculate_population_exposure(sites, tracts, radii_km=DEFAULT_RADII_KM):
    """Population within each radius of each site, by areal apportionment.

    For every tract overlapping a site's circle, the fraction of that tract's
    area inside the circle is multiplied by its population, and the products
    are summed. Returns one row per site with a column per radius, plus a
    coverage flag.

    The coverage flag matters: if a circle extends past the edge of the loaded
    tracts, over a coastline, or across a border into a state whose tracts
    were not downloaded, the figure is an undercount rather than a zero.
    """
    results = pd.DataFrame({"site_id": sites["site_id"].values})

    for radius_km in radii_km:
        radius_m = radius_km * 1000.0
        column = f"pop_{radius_km:g}km"

        circles = sites[["site_id", "geometry"]].copy()
        circles["geometry"] = circles.geometry.buffer(radius_m)
        circles["circle_area_m2"] = circles.geometry.area

        pieces = gpd.overlay(
            circles[["site_id", "geometry"]],
            tracts[["GEOID", "population", "tract_area_m2", "geometry"]],
            how="intersection",
        )
        pieces["piece_area_m2"] = pieces.geometry.area
        pieces["share"] = pieces["piece_area_m2"] / pieces["tract_area_m2"]
        pieces["people"] = pieces["population"] * pieces["share"]

        per_site = pieces.groupby("site_id").agg(
            people=("people", "sum"),
            covered_area_m2=("piece_area_m2", "sum"),
            tracts_touched=("GEOID", "nunique"),
        )

        merged = circles[["site_id", "circle_area_m2"]].merge(
            per_site, on="site_id", how="left"
        )
        merged["people"] = merged["people"].fillna(0.0)
        merged["covered_area_m2"] = merged["covered_area_m2"].fillna(0.0)
        merged["tracts_touched"] = merged["tracts_touched"].fillna(0)

        # Under 99% coverage means part of the circle had no tract beneath it.
        coverage = merged["covered_area_m2"] / merged["circle_area_m2"]
        merged[f"incomplete_{column}"] = coverage < 0.99

        results = results.merge(
            merged[["site_id", "people", "tracts_touched",
                    f"incomplete_{column}"]].rename(columns={
                        "people": column,
                        "tracts_touched": f"tracts_within_{radius_km:g}km",
                    }),
            on="site_id",
            how="left",
        )

        incomplete = merged[f"incomplete_{column}"].sum()
        print(f"  {column}: computed for {len(merged)} sites, "
              f"{incomplete} with incomplete tract coverage")

    return results


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Population exposure around data center sites."
    )
    parser.add_argument("--sites", required=True,
                        help="master_sites.csv or a raw IM3 export")
    parser.add_argument("--tiger-dir", default="data/raw/census/tiger",
                        help="where tract shapefiles live or will be saved")
    parser.add_argument("--acs", default=None,
                        help="data.census.gov CSV; omit to use the API")
    parser.add_argument("--census-key",
                        default=os.environ.get("CENSUS_API_KEY"),
                        help="Census API key; defaults to $CENSUS_API_KEY")
    parser.add_argument("--site-states", nargs="*", default=None,
                        help="only report sites in these state FIPS codes, "
                             "e.g. 51 42")
    parser.add_argument("--outlines", default=None,
                        help="IM3 GeoPackage; drops campus/point entries "
                             "already covered by building outlines")
    parser.add_argument("--states", nargs="*", default=None,
                        help="state FIPS codes whose tracts to load, e.g. "
                             "51 24 11; defaults to the sites' own states")
    parser.add_argument("--noaa-dir", default="data/raw/noaa/ghcnd",
                        help="where GHCN-Daily files live or will be saved")
    parser.add_argument("--skip-temperature", action="store_true",
                        help="population only; no NOAA download")
    parser.add_argument("--tract-cache", default=TRACT_CACHE,
                        help="saved tract layer; loaded instead of "
                             "downloading when it exists")
    parser.add_argument("--refresh-tracts", action="store_true",
                        help="ignore the saved tract layer and rebuild it "
                             "from Census, e.g. after new sites are added")
    parser.add_argument("--out", default="data/processed/community_exposure.csv")
    args = parser.parse_args()

    sites = load_sites(args.sites)

    # Which sites to report on is a separate choice from which tracts to
    # load: a site near a state border needs the neighbour's tracts too.
    if args.site_states:
        keep = {s.zfill(2) for s in args.site_states}
        before = len(sites)
        sites = sites[sites["state_fips"].isin(keep)]
        print(f"Kept {len(sites)} of {before} sites in states "
              f"{', '.join(sorted(keep))}")
        if sites.empty:
            sys.exit("No sites left after --site-states filter.")

    if args.outlines:
        sites = drop_double_listed(sites, args.outlines)

    cache = Path(args.tract_cache)

    if cache.exists() and not args.refresh_tracts:
        # The saved file already has population joined on, so no TIGER or
        # ACS download and no API key are needed.
        tract_layer = load_tract_cache(cache)
    else:
        states = resolve_state_list(sites, args.states)
        print(f"Covering {len(states)} states: {', '.join(states)}")

        tracts = load_tracts(args.tiger_dir, states)
        acs = load_acs(args.acs, states, args.census_key)
        tract_layer = build_tract_layer(tracts, acs)

        # Only a full run saves the cache. A run filtered to a few states
        # would save a partial file and break every later full run.
        if not args.site_states and not args.states:
            trimmed = trim_tracts_to_sites(tract_layer, sites)
            save_tract_cache(trimmed, cache)
            # Use the saved version for this run too, so the first run and
            # every later one give identical numbers.
            tract_layer = load_tract_cache(cache)

    print("\nContaining-tract exposure:")
    containing = assign_containing_tract(sites, tract_layer)

    print("\nRadius exposure:")
    radius = calculate_population_exposure(sites, tract_layer)

    output = (
        sites[["site_id", "source_site_id", "latitude", "longitude"]]
        .merge(containing, on="site_id", how="left")
        .merge(radius, on="site_id", how="left")
    )

    if not args.skip_temperature:
        print("\nTemperature adjustment:")
        climate = adjust_for_temperature(sites, args.noaa_dir)
        output = output.merge(climate, on="site_id", how="left")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(out_path, index=False)

    print(f"\nWrote {len(output)} rows to {out_path}")
    print("\nSummary:")
    for column in ["tract_population", "pop_1km", "pop_3km", "pop_5km",
                   "station_distance_km", "cdd_annual", "pue_adjusted"]:
        if column in output:
            values = pd.to_numeric(output[column], errors="coerce")
            digits = 2 if column == "pue_adjusted" else 0
            print(f"  {column:19s} median {values.median():>12,.{digits}f}"
                  f"   max {values.max():>12,.{digits}f}")


if __name__ == "__main__":
    main()
