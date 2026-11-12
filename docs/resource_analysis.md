# Data center community impact

## HUC8 watershed profiles, clustering and robustness

In the existing `data-center-impact` environment:

```sh
python3 -m src.analysis.huc8_environmental_profiles
python3 -m pytest tests -q
```

This produces the dynamic HUC8 dataset, 2030 features, preprocessing/correlation
audit, PCA, diagnostic-selected KMeans profiles, persistent/emerging hotspot
trajectories, scenario rank robustness, four-weight CRPI sensitivity and
`outputs/huc8_dashboard_data.csv`. No supervised environmental-risk target is
created. Original simulation equations and the nested project stay unchanged.
Unsupported watersheds remain unclassified rather than becoming zero pressure.
Population is static, uniquely counted proximity context, not exposure. CRPI is
an analyst-defined screening index, not observed harm or development advice.

[Methods and results](huc8_analysis.md) ·
[Main watershed map](../outputs/figures/figure12_huc8_environmental_profiles.png) ·
[Observed cluster profiles](../outputs/figures/figure10f_cluster_profiles.png)

## Animated 2023–2030 screening simulation

Using the existing `data-center-impact` Python environment, run:

```sh
python3 -m src.visualization.animate_resource_pressure
```

The 36-second central presentation uses EPRI moderate, Aqueduct
business_as_usual, NASA SSP2-4.5 (one model), and static ACS 2019–2023 population.
It reads the validated stateful outputs; numerical values step to actual annual
results. Only the playback progress indicator moves between annual snapshots.
The MP4 is `outputs/animations/data_center_resource_pressure_2023_2030.mp4`
(1920×1080, H.264 Main, 24 fps), with a smaller GIF, preview PNGs and a PowerPoint
poster. `animation_manifest.json` records source hashes, encodings, stages,
metrics, codec/decode validation and caveats. No new software is installed:
the exporter uses installed FFmpeg, or installed macOS AVFoundation and Swift
when FFmpeg is unavailable. On macOS it selects a compatible existing SDK.
If no installed H.264 encoder is accessible, it still produces the GIF and
previews and records the MP4 limitation explicitly instead of installing software.

Population within 5 km is unique within dissolved buffers and held constant;
it is community proximity, not exposure. HUC8 population values overlap across
groups and must not be summed. NASA is external background climate, never
data-center-caused warming. Aqueduct intermediate years are screening
interpolations, not official annual WRI forecasts. Modeled direct water uses the
verified Siddik supplementary coefficient of 1.8 m³/MWh, separately from WF and
WSF. Cumulative direct-water accounting is not permanent watershed depletion.

Map coordinates are actual sites, with state outlines derived from the existing
TIGER 2023 tract geometry and a separate Puerto Rico inset. Marker size shows
direct water demand on an explicitly labeled logarithmic scale; color shows
Aqueduct stress categories. HUC8 hotspots meet top-quartile WF and dissolved
nearby-population thresholds plus median stress ≥0.4, at least 80% known risk,
and complete population-buffer coverage. Qualifiers are ranked by WF, not a
composite score. Contrasts select the highest WSF within the bottom and top
population quartiles; source IDs are not hard-coded. Selection thresholds and
all group metrics are exported with the animation.

For a quick layout review, use `--previews-only`; `--no-gif` skips the optional
GIF. The nested `DataCenterSimulation/` and core model equations are unchanged.

## Stateful 2023–2030 simulation

Use the existing `/Users/yeritmaryrodriguezdelgado/.venvs/data-center-impact`
environment and run from this project root:

```sh
MPLCONFIGDIR=/tmp/stateful-mpl /Users/yeritmaryrodriguezdelgado/.venvs/data-center-impact/bin/python -m src.analysis.stateful_community_simulation
MPLCONFIGDIR=/tmp/stateful-mpl /Users/yeritmaryrodriguezdelgado/.venvs/data-center-impact/bin/python -m src.analysis.plot_stateful_community
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 /Users/yeritmaryrodriguezdelgado/.venvs/data-center-impact/bin/python -m pytest tests -q
```

On first preparation, if no project climate input exists, supply the user's
climate CSV using `--nasa-source /path/to/processed_data_2023_2030-1.csv`; the
pipeline preserves a raw project copy and records its provenance.

Electricity demand compounds through time using the unchanged EPRI trajectory.
Annual emissions and water demand are recalculated from each year's projected
electricity use. Cumulative emissions and cumulative direct water demand carry
forward from prior years. Aqueduct and NASA provide external future environmental
conditions. Population is held constant using ACS 2023 context. No feedback is
assumed from prior-year data-center impacts into NASA climate projections. This
is a forward stateful screening simulation rather than a fully coupled
climate-hydrology model.

The central presentation uses EPRI moderate, Aqueduct business_as_usual and NASA
SSP2-4.5; all four EPRI × three Aqueduct combinations are retained. Direct demand
uses the verified **Siddik supplementary notebook** coefficient of 1.8 m³/MWh,
separately from annual total WF and scarcity-weighted WSF. No adjusted stress
ratio is calculated because Aqueduct depth units and their normalization basis
do not support adding site water volumes directly. Supply/demand baseline
fields are unavailable; only their actual 2030 depth endpoints are retained.

Outputs include the master annual states, national/HUC8/PFAF summaries, eight
central animation-ready frame rows, four static figures (PNG/PDF), validation,
test and source-hash records. Population summaries dissolve overlapping buffers.
No MP4/GIF is produced. See [source and method documentation](data_sources.md).

The ACS 2023 / TIGER 2023 / Aqueduct 4.0 rebuild is documented in
[community resource pressure provenance](manual/community_resource_pressure_provenance.md).
Run `.venv/bin/python src/pipeline/fetch_acs2023.py` to normalize the cached
Census population table, then
`.venv/bin/python -m src.pipeline.community_resource_pressure` to rebuild
population and combine the independent EPRI demand and Aqueduct pathways.
Outputs are separate from the original community-population dataset.

The IM3 cleaning pipeline creates a master site table for geographic joins and community impact analysis. The source CSV is kept unchanged.

Run from the project root using the existing environment:

```sh
.venv/bin/python src/clean/clean_im3.py
.venv/bin/python -m unittest discover -s tests -v
```

The cleaner resolves its paths relative to the repository, so it also works from other directories. The input is the bundled IM3 Atlas version `2026.02.09` under `data/raw/im3/`.

## Outputs

- `data/processed/master_sites.csv`: final site master, built by `build_database.py`; currently IM3-only until teammate datasets are supplied.
- `data/processed/master_sites_merge_report.json`: configured sources, selected fields, and join coverage; explicitly reports an IM3-only build.
- `data/processed/data_centers.csv`: one row per IM3 source site.
- `data/processed/im3_county_review.csv`: all county alternatives for sites with multiple county assignments.
- `data/processed/im3_quality_report.json`: input/output counts, missing values, and site type counts.
- `data/processed/data_centers_with_energy.csv`: separate scenario-based energy output, produced by the model below; the cleaned dataset is preserved.

## Master site schema

### Build the deliverable and merge processed datasets

```sh
.venv/bin/python build_database.py
```

This rebuilds the cleaned IM3 table and its review/quality files from the bundled
source, then writes `data/processed/master_sites.csv` with one row per site.
It leaves the manual implementation and energy outputs untouched. The base schema
below is already implemented; teammate fields extend it using `dataset__column`
names so they cannot overwrite IM3 fields.

Once teammate file formats are agreed, supply an explicit JSON configuration:

```json
{
  "datasets": [
    {
      "name": "water",
      "path": "data/processed/water_by_county.csv",
      "key": "county_fips",
      "columns": ["reporting_year", "water_value", "unit", "source"]
    }
  ]
}
```

These file and column names are illustrative, not an agreed water-data contract.
Save this configuration at the project root as `merge_config.json`, then run:

```sh
.venv/bin/python build_database.py --config data/merge_config.json
```

CSV paths resolve relative to the configuration file. Only explicitly selected
columns are merged. Supported keys are `site_id` (`im3_` plus eleven digits),
`county_fips` (five digits), and `state_fips` (two digits); preserve leading zeros.
Each incoming dataset must contain one nonmissing row per join key. Select an
agreed year/scenario or reshape repeated observations before joining. Utility IDs
require a separate, agreed site-to-utility mapping before integration.

Left joins preserve every master site and its order. Missing county assignments
stay unmatched, and unmatched incoming rows are counted in the merge report.
County/state values are geographic context repeated across sites, not individual
site measurements, and must not be summed across master rows. Incoming values are
loaded as strings to preserve supplied text; each provider remains responsible for
units, numeric validation, and provenance. No missing values are imputed. Rebuilding
replaces the master with exactly the datasets in that run's configuration; omitting
`--config` produces the base IM3 master again.

The executable column order and pandas types are defined in `src/clean/site_schema.py`. CSV blanks represent missing values. Load with this schema to preserve leading zeros:

```python
import pandas as pd
from src.clean.site_schema import MASTER_SITE_SCHEMA
sites = pd.read_csv('data/processed/data_centers.csv', dtype=MASTER_SITE_SCHEMA)
```

| Column | Type | Meaning / rule |
| --- | --- | --- |
| `site_id` | string | Unique source-qualified ID: `im3_` plus the original 11-digit ID. |
| `source` | string | `im3`. |
| `source_version` | string | `2026.02.09`. |
| `source_site_id` | string | Original IM3 identifier, retaining leading zeros. |
| `site_name` | nullable string | Source name with whitespace normalized. |
| `state`, `state_abbr` | string | Source state name and uppercase two-letter abbreviation. |
| `state_fips` | string | Two-digit state code. |
| `county` | nullable string | Source county name; blank when county assignment is ambiguous. |
| `county_fips` | nullable string | Five-digit state + county code, suitable for county joins. |
| `longitude`, `latitude` | float | Source centroid coordinates in WGS84 (EPSG:4326), required, within ±180 / ±90. |
| `square_feet` | nullable float | Source `sqft`: surface area of the facility polygon in ft², available for building/campus types. This is mapped footprint, not verified usable floor area. Finite and positive when present. |
| `operator` | nullable string | Whitespace normalized and conservative explicit aliases applied. |
| `operator_raw` | nullable string | Source operator label before alias mapping, with whitespace normalized. |
| `site_type` | string | `building`, `campus`, or `point`. |
| `reference` | nullable string | Source `ref` identifier; not assumed to be a URL or citation. |
| `quality_flags` | nullable string | Semicolon-separated `ambiguous_county`, `missing_operator`, `missing_square_feet`. |

## Watershed HUC8 and Table 3 enrichment

HUC8 is the eight-digit identifier for a USGS hydrologic subbasin. Run this
separate step with a USGS Watershed Boundary Dataset (WBD) HUC8 polygon layer:

```sh
.venv/bin/python src/geo/enrich_huc8.py --boundaries /path/to/WBD.gpkg --layer WBDHU8
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest tests/test_enrich_huc8.py -q
```

Use `--master`, `--table3`, or `--output` to override the repository defaults.
The test command disables unrelated installed pytest plugins.
The WBD dataset must be supplied separately; the bundled IM3 GeoPackage contains
site data and is not a replacement for watershed boundaries. Coordinates use the
master's `longitude` and `latitude` columns, start in EPSG:4326, and are reprojected
to the polygon CRS before spatial assignment. HUC8 codes remain strings with
leading zeros. Malformed codes and duplicate normalized Table 3 keys stop the run.

The output is `data/processed/master_sites_with_huc8.csv`, with a matching
`master_sites_with_huc8_report.json` coverage summary and
`master_sites_with_huc8_review.csv` containing sites without a watershed or Table 3
match. Original rows, columns, identifiers, coordinates, and ordering are retained.
`huc8_status` distinguishes assigned, invalid coordinates, no polygon match, and
ambiguous watershed cases. Points on polygon edges are included; multiple distinct
HUC8 matches remain unassigned and their codes appear in `huc8_candidates` for
review. Multiple polygon parts with the same HUC8 count as one assignment.
`table3_match` records key coverage independently of missing parameter values.

Siddik et al. Table 3 values are watershed-level environmental-footprint
parameters. `WF_1MW_DC` and `WSF_1MW_DC` support later water and water-scarcity
analysis; this step does not calculate site water consumption. `CF_1MW_DC` is
retained only for comparison/validation and is **not added to eGRID carbon
emissions**. Existing energy/eGRID calculations and the original master are
unchanged. Missing matches remain in the output with blank parameters and flags.

## Cleaning rules and review process

1. Preserve source identifiers as strings. IDs distinguish source records; they do not establish that sites from different datasets are the same facility.
2. Build county FIPS by concatenating state FIPS and IM3's three-digit county code. Already complete five-digit codes must match the state prefix. Formatting and prefix checks do not independently verify geographic boundaries or official code validity.
3. Reject missing/invalid coordinates, malformed IDs/FIPS, nonpositive or nonfinite footprint, and unknown site types before saving. Optional missing footprints and operators remain blank and receive flags.
4. Normalize whitespace and site-type case. Operator aliases are explicit in `OPERATOR_ALIASES`; preserve the source label for audit. No ownership changes or operator inference from site names are applied.
5. Remove identical records. County-only duplicates become one master row with blank county fields and an `ambiguous_county` flag; export every county alternative for review. Other conflicting attributes stop the run for investigation.
6. Inspect the quality report and county review file before county-level analysis. The source README explains that repeated IDs with different counties represent buildings/campuses straddling county boundaries, with both mappings intentionally retained. The `ambiguous_county` flag means a single master county cannot be assigned; it does not imply an erroneous source mapping. Use an explicit spatial or allocation method downstream, retaining both mappings where appropriate.

## Verified area definition and power equation constraint

The bundled [IM3 README.pdf](data/raw/im3/p147s-4h760/im3_open_source_data_center_atlas_v2026.02.09/README.pdf), page 2, defines `sqft` as “surface area of facility polygon, measured in square feet.” It is available only for building and campus types. The same page describes polygon geometry as area footprint. Thus `square_feet` records building footprint or campus polygon area according to `site_type`; the README does not establish total floor area, usable floor area, or IT/white-space area. It supplies no conversion to those quantities. Page 1 explicitly warns that campus and individual building polygons can overlap and that both are retained.

For a density `D` measured in W/ft², `P_MW = A_basis_ft2 × D_W_per_ft2 / 1,000,000` is usable only when `A_basis` matches the area definition used to derive `D`. Do not substitute IM3 `square_feet` for usable floor area or IT area. First document the density's area basis and whether its power numerator is IT load or total facility load. Any conversion from footprint to the required area needs separately supported assumptions or data; IM3 alone does not supply them. Campus area requires its own treatment, point records have no polygon area, and overlapping campuses/buildings must not be summed without resolving double counting. This is an equation constraint, not a finalized capacity estimate.

The supplied snapshot has 1,479 source rows and 1,474 unique sites. Five sites have two county assignments each. All 105 point records lack footprint. Campus and building areas describe different geographic units; do not interpret their combined area as total usable building floor space or assume campuses and buildings never overlap. Coordinates and footprint are carried from the source without reprojection or geometric recomputation. County joins and spatial verification remain separate analysis steps.

This updates the previous output contract: `site_id` now has an `im3_` prefix, county codes are corrected, and provenance/quality columns are added. Update downstream joins to use the new IDs or `source_site_id` as appropriate.

## Power-density calibration and energy scenarios

Run the separate model after cleaning:

```sh
.venv/bin/python src/model/apply_im3_energy_model.py --floor-area-multiplier 1.0 --power-density-scenario reference --workload-scenario ai_training
```

The script also supports `python -m src.model.apply_im3_energy_model`. Its paths resolve from the repository location. Defaults are `reference` density, `ai_training` workload, and an **explicit single-story floor-area scenario of 1.0**, printed on each run and recorded in every output row. This multiplier is an assumption, not a measured number of stories. The underlying estimator requires the multiplier as an argument with no default. Change it with `--floor-area-multiplier`, select `low`/`reference`/`high` with `--power-density-scenario`, and select `ai_training` or `ai_inference` with `--workload-scenario`. Each run replaces only `data_centers_with_energy.csv`.

IM3 `sqft` is polygon surface area, not confirmed total floor area. Only `building` records with positive footprints receive this estimate:

```text
estimated_gross_area_sqft = square_feet × floor_area_multiplier
estimated_rated_it_power_mw = estimated_gross_area_sqft × power_density_w_sqft / 1,000,000
idle_power_mw = estimated_rated_it_power_mw × idle_fraction
estimated_average_it_power_mw = idle_power_mw + utilization × (estimated_rated_it_power_mw - idle_power_mw)
estimated_annual_facility_energy_mwh = estimated_average_it_power_mw × pue × 8760
```

The calibration CSV at `data/model_parameters/power_density_calibration.csv` contains the nine supplied real-facility examples with reported gross area and critical IT MW. Density is **critical IT watts per ft² of gross area**, not watts per ft² of IT equipment space. The loader recalculates each density from MW and area, rejects discrepancies exceeding 0.01 W/ft² against the rounded stored value, and uses full precision for statistics. Its returned table retains the rounded input as `stored_w_per_sqft`. This verifies arithmetic only: provider/facility `source_note` entries are citation placeholders, and the supplied facility reports have not been independently verified here. No source URLs are invented.

The low/reference/high density scenarios use the unweighted q25/median/q75 of these recalculated facility observations. Quartiles use pandas' linear interpolation; they are empirical scenario choices, not confidence bounds or a representative national sample.

`data/model_parameters/energy_scenarios.csv` holds the supplied literature-derived scenario assumptions: training utilization 0.80, inference utilization 0.40, idle fraction 0.20, and PUE 1.40 for both workloads. These are model parameters, not IM3 fields; literature citations remain to be documented. Utilization interpolates between idle and rated IT power. PUE converts IT power into facility power, and 8,760 hours assumes a full non-leap year. These are scenario estimates and must not be interpreted as observed site power or measured annual energy.

The output preserves all cleaned columns and adds `power_density_scenario`, `power_density_w_sqft`, `floor_area_multiplier`, `estimated_gross_area_sqft`, `estimated_rated_it_power_mw`, `workload_scenario`, `utilization`, `idle_fraction`, `pue`, `estimated_average_it_power_mw`, `estimated_annual_facility_energy_mwh`, and `energy_estimate_status`. Scenario parameters are recorded even on excluded rows, but all four area/power/energy estimates remain blank there.

| Status | Interpretation |
| --- | --- |
| `estimated_building` | Building estimate under the recorded scenario assumptions. |
| `missing_footprint` | Building without footprint; no area is imputed. |
| `campus_not_supported` | Campus polygon is not converted to gross floor area by this method. |
| `point_not_supported` | Point location has no usable polygon area. |

Campus/point statuses take precedence over missing footprint. Invalid building inputs (including nonpositive area), invalid parameters, or unknown site types stop the model instead of silently filling values. Excluded rows are unknown estimates, not zero consumption. The script prints calibration quantiles and status counts. Validate the functions and existing cleaner with `.venv/bin/python -m unittest discover -s tests -v`.

## Compare energy scenarios

Generate all six combinations of low/reference/high density and training/inference workload:

```sh
.venv/bin/python src/model/compare_energy_scenarios.py --floor-area-multiplier 1.0
```

Module execution (`python -m src.model.compare_energy_scenarios`) is also supported.
The runner reuses the existing model and saves six site-level CSVs plus
`scenario_comparison.csv` under `data/processed/energy_scenarios/floor_area_1.0/`.
The default folder reflects the supplied multiplier, which remains an assumed
gross-area/footprint conversion. Use `--output-dir PATH` to choose another folder.
Rerunning in the same folder replaces those seven files; the existing
`data_centers_with_energy.csv` and cleaned input are preserved.

The comparison records scenario parameters, site/status counts, and building-only
median, q95, and maximum rated IT power and annual facility energy. Quantiles use
pandas linear interpolation. Each workload is applied uniformly as a hypothetical
scenario, not as a classification of actual facilities. Unsupported records retain
blank estimates; statistics are blank when no buildings are estimated. No geographic
totals are produced because overlap and county allocation remain unresolved.

## Energy Estimate Validation

Run the checks and plots after generating the energy output:

```sh
.venv/bin/python src/validation/validate_energy_outputs.py
.venv/bin/python src/validation/plot_energy_distributions.py
.venv/bin/python -m unittest discover -s tests -v
```

These are scenario-based estimates, not observed site loads. Building estimates combine IM3 footprint with model assumptions; campus and point records remain unsupported with blank estimates. Validation is a separate layer that catches geometric or modeling anomalies before downstream water/emissions calculations. It does not alter the cleaner, equations, parameter CSVs, processed model output, or scenario defaults.

The validator checks unique site IDs, coordinates, numeric values, nonnegative areas/power/energy, utilization and idle fraction within [0, 1], and PUE ≥ 1. Nonnumeric/nonfinite values, inconsistent site-type statuses, and estimates attached to unsupported sites raise errors. Missing building inputs or outputs receive `missing_required_input`; unsupported campus/point rows receive `unsupported_site_type`. Missing coordinate values raise errors. All optional numeric columns are checked when present.

For manual inspection only, rated IT power strictly above the estimated-building q99 receives `very_large_power_estimate`; footprint strictly above the all-building q99 receives `very_large_footprint`. Multiple flags are preserved with semicolons. These are dataset-relative thresholds, not physical capacity limits or evidence of an error. No outliers are deleted, capped, or winsorized. Under identical assumptions, footprint and power rankings coincide by construction.

Reports under `data/validation/`:

- `energy_validation_results.csv`: all original rows/columns plus `energy_validation_flag`.
- `top_energy_outliers.csv`: three separate building-only top-ten lists, distinguished by `ranking_metric` and `rank`; a site can appear in all three lists.
- `energy_summary.csv`: two-column structural counts, selected statistics, and the exact q99 thresholds used. `missing_building_estimates` counts building rows missing any of the four area/power/energy outputs; `missing_footprint_records` counts the corresponding model status.
- `energy_descriptive_statistics.csv`: count, minimum, q05, q25, median, q75, q95, maximum, mean, and sample standard deviation for the four requested variables. Statistics use finite non-null values, pandas linear quantiles, and sample SD (`ddof=1`). Footprint statistics include both buildings and campuses; the footprint flag threshold uses buildings only. Empty populations have blank statistics, and SD is blank for fewer than two observations.

The plotting script uses matplotlib and writes three separate PNGs under `outputs/validation/`: `rated_it_power_distribution.png`, `annual_energy_distribution.png`, and `footprint_vs_power.png`. Plots include estimated buildings only and exclude null values. Log scales are used only when all values are positive and span at least two orders of magnitude, to keep small sites visible alongside large sites. The footprint-versus-power relationship reflects the model equation and is not independent evidence of accuracy.

## Repository organization

The project separates reusable scientific logic from analysis scripts,
raw and processed data, validation code, and generated outputs.

```text
data-center-community-impact/
├── data/
│   ├── raw/
│   │   └── epri/
│   │       └── EPRI_2024_Projections.xlsx
│   ├── processed/
│   │   ├── data_centers.csv
│   │   ├── data_centers_with_energy.csv
│   │   ├── energy_scenarios/
│   │   ├── emissions/
│   │   └── table3.csv
│   ├── model_parameters/
│   └── validation/
│
├── src/
│   ├── clean/
│   │   └── IM3 cleaning and site-schema logic
│   ├── geo/
│   │   └── geospatial enrichment, including HUC8 assignment
│   ├── model/
│   │   ├── energy_model.py
│   │   ├── power_density.py
│   │   ├── apply_im3_energy_model.py
│   │   ├── scenarios.py
│   │   ├── temporal_projection.py
│   │   └── epri_projection.py
│   ├── impact/
│   │   ├── eGRID emissions calculations
│   │   └── temporal_emissions.py
│   ├── analysis/
│   │   ├── EPRI baseline comparison
│   │   ├── EPRI energy-scenario validation
│   │   ├── EPRI temporal comparison
│   │   └── temporal emissions analysis
│   ├── pipeline/
│   │   └── database-building workflows
│   └── validation/
│       └── model QC and diagnostic analysis
│
├── tests/
│   └── unit and integration tests
├── manual/
│   └── independent/manual implementations used for verification
├── outputs/
│   └── generated model results and validation summaries
├── pytest.ini
├── requirements.txt
└── README.md
```

### Design philosophy

Reusable scientific calculations are kept in `src/model/`,
`src/impact/`, and `src/geo/`. Analysis scripts in `src/analysis/`
orchestrate those reusable components to generate specific results.

The project intentionally retains functional implementations for core
scientific equations because they are simple, testable transformations.
Object-oriented structure is introduced where it improves organization,
particularly for simulation assumptions and temporal scenarios through
`SimulationScenario` and `TemporalScenario`.

Generated results are written to `outputs/` and are not treated as source
code.

## Temporal simulation

The initial model estimates annual electricity demand for individual IM3
data-center records under alternative power-density and workload
assumptions.

Temporal simulations extend 2023 baseline estimates through 2030 using
state-level growth trajectories derived from EPRI projections.

Four EPRI demand-growth scenarios are represented:

- Low growth
- Moderate growth
- High growth
- Higher growth

For temporal environmental-impact simulations, each site's projected
electricity demand retains its assigned eGRID subregion. EPA eGRID 2023
CO2, CO2e, NOx, and SO2 output rates are then applied to annual projected
electricity demand.

The current temporal emissions analysis holds 2023 eGRID emission factors
constant through 2030. Therefore, projected emissions isolate the effect
of electricity-demand growth and should not be interpreted as a forecast
of future U.S. grid carbon intensity.

EPRI estimates are used as an external state-level benchmark and growth
scenario source. They are not treated as measured electricity consumption
for individual IM3 facilities.

## Interactive Dashboard

Use the existing environment, then launch the local Plotly Dash explorer:

```bash
source /Users/yeritmaryrodriguezdelgado/.venvs/data-center-impact/bin/activate
python3 -m src.dashboard.app
```

Open <http://127.0.0.1:8050>. Start on the national map, click a state, view the full HUC8 watersheds represented by modeled sites, click a watershed for details, then click a data-center site for its estimates. The year slider and paired scenario selector update results through 2030.

**Option A:** state selection is a navigation/filtering device. Watersheds remain complete hydrologic units and are not clipped at state boundaries. [Dashboard methods and limitations](dashboard.md) document the saved 2030 classifications, annual metric behavior and population handling. [Screenshot instructions and manual checklist](../outputs/dashboard/README.md) accompany the automated validation results.

