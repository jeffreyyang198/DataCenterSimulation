# Interactive dashboard

Activate the existing environment and run from the repository root:

```bash
source /Users/yeritmaryrodriguezdelgado/.venvs/data-center-impact/bin/activate
python3 -m src.dashboard.app
```

Open <http://127.0.0.1:8050>. The app binds to loopback only. No hosted service, map token or external map tiles are required. The initial viewport emphasizes the contiguous United States; all 56 Census state/equivalent areas are clickable when in view and available through the state selector, including Alaska, Hawaii and territories. Areas without modeled sites remain navigable and show no modeled totals.

## Navigation and Option A

1. Start on the national map, colored by mapped site record count.
2. Click a state or use the state selector.
3. View complete HUC8 watersheds containing sites assigned to that state.
4. Click a watershed or use the HUC8 selector to inspect its metrics and trajectory.
5. Click a site marker or use the site selector for site-level estimates.
6. Move the year slider or change the paired scenario to update estimates. Back to state clears watershed/site selection; Reset to U.S. clears all geographic selections while preserving the controls.

State selection is a navigation/filtering device. Watersheds are displayed as complete hydrologic units and are **not clipped at state boundaries**. The state–HUC8 crosswalk counts assigned site records; it does not use polygon overlap or majority area. State views show sites assigned to the selected state. A watershed selection shows every site in that HUC8, including records assigned to neighboring states; their state is included in hover and site detail. The map fits the selected state together with the full associated watersheds so cross-state context remains visible. The selected state has a dark outline and selected HUC8 an orange outline.

## Data and preparation

`src/dashboard/data.py` loads validated tables once per process and builds keyed lookups for year/scenario, state/site, HUC8/site and state/year/scenario aggregates. Callbacks do not reload source CSVs. First startup reads the existing 132 MB simulation table and writes a compact 12 MB cache containing the three selected paired scenarios and needed columns. Later startups verify the compact dataset SHA-256 checksum and reuse it when the source size/mtime and cache schema match. A fresh clone can run from the committed, checksum-verified compact dataset when the excluded large simulation CSV is absent. If that artifact fails validation and the source is unavailable, startup stops with regeneration instructions. The Dash session store preserves geographic, year, scenario and metric selections. Pure selection helpers are shared with tests.

The authoritative annual HUC8 table is `outputs/huc8_dynamic_profiles_2023_2030.csv` (5,304 rows). The site source is `outputs/stateful_community_resource_simulation_2023_2030.csv`, selected by the validated EPRI/Aqueduct pairs. Identity fields come from `data/processed/master_sites_with_huc8.csv`. Saved 2030 profiles, trajectories and robustness labels come from `outputs/huc8_dashboard_data.csv`; paired 2030 CRPI scores come from `outputs/huc8_crpi_scenario_sensitivity_2030.csv`. No new scientific simulation, supervised target or annual CRPI is calculated by this dashboard.

The original national Census state boundary archive is preserved under `data/raw/census/state_boundaries_2023/`. It is the official 2023 State and Equivalent 1:500,000 file, EPSG:4269. `data/processed/us_states_2023.gpkg` contains the national layer in EPSG:4326. Its web GeoJSON is simplified at 1,200 m in EPSG:5070 with topology preservation, repaired if necessary, and reprojected to EPSG:4326. All 56 display geometries are valid and nonempty.

`data/processed/huc8_dashboard_geometry.geojson` reuses the 221 validated full watershed display geometries from `data/processed/huc8_analysis_boundaries.gpkg`. That existing layer was derived from `data/raw/siddik/SI_Shapefile.shp` with a 500 m display simplification. The dashboard adds no further simplification, clipping or intersection. All HUC8 geometries are valid. Subbasin names are joined by `HUC_8` from the original DBF's `SUBBASIN` field and preserved in `huc8_dashboard_names.csv`. Raw scientific geometries remain unchanged. Metadata and source hashes are in `data/processed/dashboard_geometry_metadata.json`.

Regenerate the display layers and crosswalk, if necessary:

```bash
python3 -m src.dashboard.data
```

## Metrics and interpretation

Annual numerical colors follow the selected year/scenario. Positive resource/population map colors use log10(1 + value) for legibility; hover always shows the raw quantity with units. Aqueduct colors use the documented WRI stress bands, including the open-ended extreme class, rather than treating the sentinel as a precise ratio. Intermediate saved ratios at or above 100 are treated as censored/open-ended context: gray on the numeric map and omitted from numeric trend lines. The underlying saved scientific data are preserved. Numeric details label these censored values explicitly. The maximum stress field may also be open-ended. Missing data remain missing rather than zero.

CRPI is available only for 2030, separately for each paired scenario. If an earlier year is selected while the CRPI option is active, the map explicitly switches to that year's saved WSF and explains the substitution. Cluster labels describe the saved central-2030 fit; hotspot labels describe the central 2023–2030 trajectory; scenario robustness means WSF top quartile in all three paired scenarios. These classifications remain static and are labeled accordingly when controls change. The lower-pressure filter uses the seven finalized central-2030 candidates, not a newly inferred annual classification. It filters displayed watersheds/sites after state selection; summary totals and trajectories retain the complete selected geography.

State/national annual quantities are summed from sites assigned to that geography with `min_count=1`: entirely unknown totals are unavailable. Coverage counts accompany the panels. Climate and Aqueduct state/national summaries are site medians, not area-weighted state climate measurements. HUC8 summaries retain the previously validated aggregation.

National and HUC8 proximity population comes from the validated dissolved-buffer population lookup. Buffers are dissolved for sites assigned to the group, not clipped to hydrologic borders. HUC8 populations are not additive. Unique state-level population is absent from that lookup; the UI explicitly shows it as unavailable and never sums overlapping site populations. Site population remains static at ACS 2023. Incomplete tract coverage is flagged. Proximity is not exposure.

Direct water is the modeled direct data-center water demand, using the Siddik supplementary notebook's 1.8 m³/MWh coefficient. It is distinct from total water footprint, which includes direct and indirect water. NASA SSP2-4.5 is external background climate context. Intermediate Aqueduct years are screening interpolations rather than official annual WRI forecasts. Paired scenarios are not formally coupled climate-economic pathways. CRPI is a screening index, not observed harm or a probability. Comparatively lower modeled resource pressure is not a development recommendation.

Site markers use uniform size within a navigation level and the same water-stress bands explained in the footer. Only selected-state or selected-watershed sites appear. No national cloud of 1,474 markers obscures the landing map. Temporal charts show one metric/unit at a time, omit unknowns and mark the selected year. Selecting a site keeps the temporal chart at watershed level.

## Validation and screenshots

Run the real-data programmatic checks and the complete test suite:

```bash
python3 -m src.dashboard.validate
python3 -m pytest tests -q
```

The validation command exercises the actual Dash HTTP layout and callback endpoints, including map click payloads for Arizona, Virginia, California, Texas, New York and an empty Alaska view; full polygon equality; a real cross-state watershed; HUC8/site selection; year/scenario changes; every map metric; temporal metrics; static population; and back/reset behavior. Results are recorded in `outputs/dashboard/validation.json`. The 15 focused dashboard tests cover pure navigation/data logic, including an explicit cross-state polygon-retention assertion, not framework internals.

Manual browser rendering/click verification and screenshots could not be performed because Computer Use access to Chrome was not approved. This remains a visual-validation limitation; programmatic checks are reported separately. No browser automation packages were installed. `outputs/dashboard/README.md` provides an exact manual checklist and instructions for saving `national_overview.png`, `state_example.png`, `huc8_example.png` and `hotspot_example.png`. These screenshots have not been fabricated or substituted with static map exports.
