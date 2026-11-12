# Community resource pressure rebuild

Run from the project root:

```sh
.venv/bin/python src/pipeline/fetch_acs2023.py
.venv/bin/python -m src.pipeline.community_resource_pressure
.venv/bin/python src/validation/validate_community_resource_pressure.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q
```

The first command normalizes the cached official Census summary file. If that
file is absent, it retrieves the official public table-based summary file.
The raw table downloaded for this run is
`data/raw/census/acs2023/acsdt5y2023-b01003.dat`.

## Source custody

The initial repository search found only `data/processed/tracts_near_sites.gpkg`.
The user subsequently identified two specific Downloads directories and
authorized their inspection. Files were copied from those directories, without
searching the rest of Downloads. No TIGER or Aqueduct download was necessary.
`data/raw/source_copy_manifest.json` lists every absolute original and target
path, SHA-256 hash, and copy/reuse action. Existing nonidentical targets stop the
copy instead of being replaced. Original files remain in place.

TIGER files are `tl_2023_<state>_tract` shapefiles, with their projection,
attribute, index, encoding, and metadata files. The pipeline checks tract GEOID
length and uniqueness, its state/county/tract components, polygon geometry and
CRS. Non-2023 or non-TRACT filenames are rejected. Source metadata and an
inventory accompany the processed result.

## Population

Source: [Census 2023 ACS table-based summary file](https://www2.census.gov/programs-surveys/acs/summary_file/2023/table-based-SF/data/5YRData/acsdt5y2023-b01003.dat).
The table-based `B01003_E001` is the total-population estimate represented by
API variable `B01003_001E`. Tract records have summary level `140`; only
`1400000US` identifiers with eleven trailing digits are retained. Negative
special values become missing population, never zero. These are 2019–2023
five-year estimates, not a point-in-time census count. Sampling uncertainty is
not propagated by this area-allocation calculation.

Every supplied tract file is searched, including neighboring states. The
processed GeoPackage contains full tract polygons intersecting the union of
5-km site buffers, not a nationwide tract layer. This scope supports the
1-, 3-, and 5-km analyses; moving/adding sites requires removing or archiving
the generated GeoPackage before rebuilding. The cached layer is not a raw
source. Original `tracts_near_sites.gpkg` and `community_exposure.csv` remain
unchanged.

Distances use local azimuthal equidistant projections centered on each site.
Intersections and tract-area fractions use EPSG:6933. Population is allocated
uniformly over total tract area, including water in the tract geometry; this is
an assumption, not a population raster. An uncovered buffer fraction greater
than 0.001 or any intersecting tract with missing population marks a buffer
incomplete. Coastal/territorial edges can cause incomplete coverage. A blank
population for a buffer with no positive-area intersections remains unknown.
Known partial sums remain flagged and must not be presented as complete totals.

Unique proximity summaries dissolve overlapping site buffers before allocation.
Per-site values must not be summed across facilities. Comparison outputs retain
the existing estimates, rebuilt estimates, signed differences and percentage
differences; percentage differences are blank for zero existing estimates.
Differences can reflect source vintage, geographic coverage and distance method.

In the November 11, 2026 rebuild, the processed layer contains 12,505 nearby
tracts with no missing ACS population. The previous tract layer contains no
Puerto Rico tracts. Its two Puerto Rico sites had zero estimates with incomplete
coverage flags at all three radii; the rebuild supplies those missing tracts.
Their rebuilt 5-km estimates are approximately 141,644 and 153,596 residents.
These are the two largest population differences, reflecting restored coverage
rather than a measured population increase.

## Aqueduct

Source: [WRI Aqueduct 4.0](https://www.wri.org/data/aqueduct-global-maps-40-data),
local release `Aqueduct40_waterrisk_download_Y2023M07D05`.
[WRI's data dictionary](https://github.com/wri/Aqueduct40/blob/master/data_dictionary_water-risk-atlas.md)
defines `pfaf_id` and scenario/indicator codes. The geodatabase layers are
inspected for polygon geometry and `pfaf_id`; future geometry is preferred,
then monthly basin geometry. Point/polygon intersections assign sites. Multiple
parts of one basin count as one match; multiple distinct basin IDs remain
ambiguous. There is no nearest-basin fallback and no HUC8-to-Pfafstetter join.

2030 pathways are optimistic (SSP1/RCP2.6), BAU (SSP3/RCP7.0) and pessimistic
(SSP5/RCP8.5), representing the 2015–2045 period. All supplied 2030 indicators
are retained. Negative special numeric values, including arid/low-use codes,
remain available in `_source_value` columns but are missing in usable numeric
columns. Labels remain intact. Missing/arid conditions must not be described as
zero stress. Scores and categories are distinct from physical water quantities.

## Combined context

The existing EPRI/Siddik temporal-water pipeline is rerun using its documented
low-density AI-inference energy scenario, floor-area multiplier 1.0 and fixed
Siddik coefficients. All four EPRI demand-growth scenarios are crossed with all
three independent Aqueduct pathways; their names are not equated. Site records
retain unsupported-model statuses and missing values. Sites without usable EPRI
growth factors are retained in all twelve scenario combinations with
`no_epri_growth` and blank modeled water quantities; their population and
Aqueduct context remain available. The final scenario-grid completion step
also has a standalone entry point:
`.venv/bin/python src/pipeline/complete_community_scenarios.py`.
EPRI projections are
scenario benchmarks; Siddik coefficients and the model energy scenario are not
site measurements. Existing overlap and duplicate-site caveats still apply.

The combined output reports water footprint, scarcity-weighted footprint,
nearby population and basin stress side by side. It does not multiply Siddik's
scarcity footprint by an Aqueduct score, or invent a calibrated composite index.
The per-10,000-nearby-residents quantity is a contextual ratio, not household
water demand, health risk, attributable exposure or a shared-water-supply claim.
The high-stress flag uses Aqueduct categories 3–4 and stays missing where no
usable category exists. Figures distinguish scenario and units.

Outputs are under `outputs/community_resource_pressure/`, with machine-readable
run metadata and raw source metadata. No GitHub push is part of this workflow.
