# Data sources

## HUC8 watershed analysis

The canonical dynamic HUC8 table is independently aggregated from the validated
site states and checked against `stateful_huc8_resource_simulation_2023_2030.csv`.
The selected source paths/columns are printed by
`src/analysis/huc8_environmental_profiles.py` and hashed in
`outputs/huc8_analysis_metadata.json`. Population uses the existing dissolved
within-HUC8 5-km cache; site population values are never summed. The actual
Siddik geometry source `data/raw/siddik/SI_Shapefile.shp`, key `HUC_8`, supports
the maps. HUC8 and PFAF remain separate identifiers.

The analysis is unsupervised; no observed environmental-harm target is invented.
Matched-cohort intensity features avoid dilution by missing coefficients.
Practically constant growth is retained as raw data but excluded from clustering;
central growth is neutral in the optional CRPI. Neither raw missing values nor
unassessable watersheds become zeros or lower-pressure recommendations.
PCA/cluster interpretations derive from actual loadings and profiles. CRPI is
an explicitly weighted relative screening index with four weight schemes, not
a supervised prediction or probability of harm. See
[methods, results and limitations](huc8_analysis.md) for full rules, weights,
coverage, figures and the exclusions from any siting interpretation.

## Stateful 2023–2030 simulation

The executable workflow is `src/analysis/stateful_community_simulation.py` and
the annual-state logic is `src/model/stateful_community.py`. Input file hashes,
the selected climate path and methodological limitations are saved in
`outputs/stateful_simulation_provenance.json`.

Electricity demand compounds through time using the existing EPRI state growth
workflow, unchanged. Annual emissions and water demand are recalculated from
each year's projected electricity use. Cumulative emissions and cumulative
direct water demand carry forward from prior years, starting with the annual
2023 amount. Unknown annual history makes subsequent cumulative amounts unknown;
missing amounts are never silently treated as zero.

Aqueduct and NASA provide external future environmental conditions. Population
is held constant using ACS 2023 context. No feedback is assumed from prior-year
data-center impacts into NASA climate projections. The model is a forward
stateful screening simulation rather than a fully coupled climate-hydrology
model. Cumulative modeled water demand is an accounting total, not a claim that
previously consumed water remains permanently unavailable in the watershed.

### Electricity and eGRID

The existing input energy scenario is
`data/processed/energy_scenarios/floor_area_1.0/low_ai_inference.csv`. It uses the
project's low power-density, AI-inference assumptions and an explicit assumed
floor-area multiplier of 1.0; energy is not measured site consumption.

EPRI's `data/raw/epri/EPRI_2024_Projections.xlsx` is processed by the existing
`load_epri_projections`, `project_epri_annual` and
`prepare_state_growth_factors` functions. For each state/scenario, its implied
annual geometric growth joins the 2023 and 2030 endpoints. Site electricity is
baseline electricity multiplied by the year's relative growth factor. This is
equivalent to multiplying the prior state by the ratio of successive growth
factors. The four EPRI scenarios remain low, moderate, high and higher.

`data/processed/emissions/site_egrid_mapping.csv` and
`data/processed/emissions/egrid2023_factors.csv` provide geographic eGRID
assignments and fixed 2023 rates in lb/MWh. Annual CO2, CO2e, NOx and SO2 equal
annual electricity times their respective rates times 0.00045359237 metric
tonnes/lb. No forecast grid decarbonization or additional grid-loss adjustment is
introduced. Missing trajectories, unsupported energy estimates and missing
factors remain NaN. Site records may overlap, so study-inventory totals are not
independently deduplicated national estimates.

### Verified direct data-center water demand

**Coefficient: 1.8 m³/MWh.** Provenance is the supplied Siddik supplementary
notebook/source workflow, **`Estimating_WF_CF_WSF_of_data_centers.html`**, section
**“Direct water footprint of data centers.”** This is not a coefficient inferred
from `Input data.xlsx` or `Results.xlsx`.

The user supplied this source passage and its implementation on November 11,
2026:

> Direct water consumption of a data center can be estimated from the heat
> generation capacity of a data center, which is related to the amount of
> electricity used. Estimates of data center specific electricity demand were
> multiplied by the typical water cooling requirement — 1.8 m3/MWh — to estimate
> the direct water footprint of each data center.

```python
DWF_at_HUC8["Direct water footprint (m3)"] = (
    HUC8_DWF["Scaled Power Consumption (MWh)"] * 1.8
)
```

The original HTML file was not located in this project during inspection; the
verification record is the supplied source transcription, not an independently
opened local HTML file. Code and machine-readable provenance preserve that
distinction.

`annual_direct_water_m3 = projected_energy_mwh × 1.8` is labeled **modeled direct
data-center water demand**. It is not total blue water footprint. The source
separately defines total blue water footprint as direct plus indirect water
consumption. The model does not add direct demand to the existing total WF,
which would risk double counting.

### Annual Siddik WF and WSF

`data/processed/master_sites_with_huc8.csv` supplies `WF_1MW_DC` and
`WSF_1MW_DC` from the existing Siddik enrichment. The local `Results.xlsx`
documentation labels these as m³/MWh and m³-eq/MWh for the hypothetical 1-MW
data-center comparison. The validated coefficients are unchanged. Each year's
electricity independently yields annual water footprint and annual
scarcity-weighted water footprint. WSF is already scarcity weighted and is never
multiplied by Aqueduct stress. m³ and m³-eq are not added.

### Aqueduct screening interpolation and unit limits

Source: WRI Aqueduct 4.0 release `Aqueduct40_waterrisk_download_Y2023M07D05`,
preserved in `data/raw/aqueduct/`. See the
[WRI data dictionary](https://github.com/wri/Aqueduct40/blob/master/data_dictionary_water-risk-atlas.md).
Sites use the previously validated spatial `pfaf_id` assignments. HUC8 and PFAF
are distinct hydrologic systems and are never equated.

The baseline CSV and geodatabase were inspected. They contain `bws_raw` and
`bwd_raw`, but no available-blue-water or gross-water-demand baseline fields.
Repeated baseline annual fragments have identical raw stress/depletion within
each PFAF basin; the pipeline checks this before selecting one basin value.
Negative sentinel/arid codes become NaN and are not interpreted as zero risk.

For raw stress/depletion, each pathway's 2030 `ws_x_r`/`wd_x_r` endpoint is
interpolated using `baseline + (year - 2023)/7 × (2030 - baseline)`. The historical
baseline is anchored at 2023 for screening; it is not a measurement of 2023.
Known endpoint values are retained even if the opposite endpoint is missing;
intermediate years require both endpoints.

**Aqueduct 2030 values are 2030-centered future projections rather than literal
annual forecasts. Annual interpolation is used only to create a smooth
screening trajectory for visualization. Interpolated 2024–2029 values are not
official WRI annual predictions.** The 2030 period is 2015–2045.

Future `ba_x_r` (available blue water) and `ww_x_r` (gross/background water demand)
are in **cm/year**. Their 2030 endpoints are retained with explicit unit columns;
2023–2029 are NaN because their baseline endpoints are unavailable. The model
does not back-solve or invent baseline supply/demand.

No `dc_adjusted_water_stress_ratio` is calculated. Adding direct demand in
m³/year to Aqueduct cm/year is dimensionally invalid. A polygon's geometric area
alone does not establish the hydrologic normalization-area basis of the source
variables; no unverified depth-to-volume conversion is applied. Instead the
simulation preserves parallel `aqueduct_water_stress` and
`annual_direct_water_m3` fields, plus an explicit adjusted-ratio status. At basin
aggregation, background supply/demand and stress are conditions, never sums over
the number of data-center records.

### NASA background projected climate conditions

Project inspection found no finalized site climate CSV, so the user-supplied
`/Users/yeritmaryrodriguezdelgado/Downloads/processed_data_2023_2030-1.csv` is
preserved under `data/raw/nasa/`, with source path and SHA-256 metadata. This
supplied processed table contains 11,792 site-year records, 1,474 sites, eight
years (2023–2030), `ssp245` (SSP2-4.5), and `n_models = 1`. The pipeline validates
the actual selected file's keys, years, site inventory and single-model metadata
before joining by site_id/year. It does not download or fabricate another
climate scenario. No precipitation field exists in the supplied table.

The output retains mean, warmest-day mean and coldest-day mean temperatures,
`n_models = 1`, and SSP2-4.5 metadata. These are **background projected climate
conditions**, not consequences of the simulated site emissions. The supplied
`temperature_anomaly_vs_2023_2030_c` is renamed
`temperature_deviation_from_2023_2030_mean_c`; it is not a historical-climate
anomaly.

### Static community proximity

Population is held constant at the ACS 2019–2023 5-Year estimate and provides
contemporary community context rather than a demographic forecast. The pipeline
uses `community_exposure_acs2023.csv` and `tracts_acs2023.gpkg`, retaining
1-, 3- and 5-km population and incomplete-coverage flags. No demographic growth
is invented. Nearby population is not a health-exposure estimate.

National 5-km population is computed from dissolved site buffers. HUC8 and PFAF
summaries separately dissolve buffers of the sites assigned to each group and
allocate full-tract population in EPSG:6933. These group buffers are not clipped
to watershed boundaries, and populations overlap between groups. Group
population values must not be summed to obtain a national population. The cache
`data/processed/stateful_unique_population_5km.csv` includes a hash-based input
manifest. Missing HUC8 assignments remain visible at site/national levels but
are excluded from named HUC8 group summaries. Incomplete coverage remains a
population limitation; no unknown resident count is imputed.

### Presentation and sensitivity scenarios

- `central_2030_screening`: EPRI moderate / Aqueduct business_as_usual / NASA SSP2-4.5.
- `lower_pressure`: EPRI low / Aqueduct optimistic / NASA SSP2-4.5.
- `higher_pressure`: EPRI higher / Aqueduct pessimistic / NASA SSP2-4.5.

All four EPRI × three Aqueduct combinations remain in the output for sensitivity
analysis. Presentation pairings are convenient screening combinations, not
formally coupled pathways. NASA remains fixed to the one available SSP. The
central label applies to its full annual trajectory, including the 2030 endpoint.

### Outputs and validation

`outputs/stateful_community_resource_simulation_2023_2030.csv` has one row per
site/year/EPRI/Aqueduct combination. Annual national, HUC8 and PFAF summaries are
separate files. `modeled_sites` counts sites with projected energy; water and CO2
coverage counts are separate because missing coefficients differ. National
totals are known modeled-site sums with NaN preserved for wholly missing groups.
They are not estimates for excluded facilities. The central animation-ready
frame table contains eight summary records; no animation is created.

`stateful_simulation_validation.json` records checks for row uniqueness, years,
annual compounding, strict cumulative transitions, annual factors, static
population, climate variation and independence, interpolation bounds,
identifier separation, dimensional compatibility and missingness. Test results
are retained in `outputs/stateful_simulation_tests.txt`.

Four static figures are supplied as PNG and PDF. Figure 9d uses separate axes for
electricity, water-stress ratio and temperature, avoiding mixed units on one
axis. Cumulative direct water is cumulative modeled resource demand, not a
depletion model. The existing `DataCenterSimulation/` directory is unchanged.

## Interactive dashboard display sources

The dashboard reuses validated site/year, HUC8/year, CRPI, cluster, trajectory and dissolved-buffer population artifacts; it does not introduce a new demographic dataset. See [dashboard provenance and interpretation](dashboard.md) for exact input paths and handling of missing, static and censored values.

The national state layer is the official [2023 Census Cartographic Boundary State and Equivalent, 1:500,000](https://www2.census.gov/geo/tiger/GENZ2023/shp/cb_2023_us_state_500k.zip), preserved in `data/raw/census/state_boundaries_2023/`. The source contains 56 state/equivalent areas in EPSG:4269; the GPKG is reprojected to EPSG:4326 and the web GeoJSON uses a 1,200 m topology-preserving display simplification. The previous tract-dissolved animation outline was inspected but lacked a complete national state/equivalent inventory.

HUC8 web geometry comes from the existing Siddik-source full HUC8 display layer, retaining its 500 m simplification and adding no clipping or further simplification. State associations are counted from assigned site records rather than polygon majority area. All 221 HUC8 display geometries and 56 state display geometries are valid. Source hashes and processing choices are recorded in `data/processed/dashboard_geometry_metadata.json`; the site-derived navigation crosswalk is `data/processed/state_huc8_dashboard_crosswalk.csv`.

The implementation follows the official [Dash callback documentation](https://dash.plotly.com/basic-callbacks) and [Plotly MapLibre choropleth reference](https://plotly.com/python/reference/choroplethmap/). Maps use local geometry with a tile-free background; no map token or third-party tile service is required.

