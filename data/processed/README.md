# Processed datasets

## Essential dashboard snapshot

| Dataset | Role |
| --- | --- |
| `dashboard_site_states.csv` and `.json` | Compact annual site states for the three presentation scenarios and SHA-256 manifest |
| `master_sites_with_huc8.csv` | Site identity, coordinates, HUC8 and Siddik coefficients |
| `huc8_dashboard_geometry.geojson` | Full local HUC8 polygons and watershed names |
| `us_states_dashboard.geojson` | Simplified local state and equivalent polygons |
| `state_huc8_dashboard_crosswalk.csv` | State-to-watershed navigation based on mapped sites |
| `stateful_unique_population_5km.csv` | Dissolved ACS proximity estimates for national, HUC8 and PFAF groups |

The dashboard also reads four canonical `outputs/` CSVs for dynamic HUC8 profiles, HUC8 dashboard data, the lower-pressure shortlist and scenario CRPI scores. See [dashboard documentation](../../docs/dashboard.md).

## Reproducible analysis inputs and final results

- **Site inventory.** `data_centers.csv` and `master_sites.csv` hold cleaned and merged IM3 records. Associated review and report files record quality and merge outcomes.
- **Electricity.** `data_centers_with_energy.csv` and `energy_scenarios/` hold the fixed-PUE site estimates and scenario comparison. `data_centers_with_energy_climate.csv`, `site_pue_climate.csv` and `k_estimate.json` hold the adjusted energy, site PUE and fitted coefficient diagnostics.
- **Emissions.** `emissions/` holds 2023 regional factors, site mappings, comparison figures, estimates and review tables. [Emissions data guide](emissions/README.md)
- **Water and community.** `table3.csv` stores source water factors. `site_aqueduct_basins.csv`, `aqueduct2030_normalized.csv` and `aqueduct_annual_screening_2023_2030.csv` hold spatial and annual basin context. `community_exposure.csv` and `community_exposure_acs2023.csv` preserve both the companion and current buffer results. The dissolved proximity JSON records input provenance.
- **Map preparation.** `huc8_analysis_boundaries.gpkg`, `us_states_2023.gpkg` and `animation_state_outlines.gpkg` support analysis or figure preparation. Their companion metadata, `huc8_dashboard_names.csv`, and the geometry metadata describe display inputs.

## Larger or redundant local intermediates

`tracts_acs2023.gpkg` and `tracts_near_sites.gpkg` are existing tracked tract geometry caches. Neither is needed at dashboard startup. This review leaves the tracked history and retention of both caches to the team. The existing `EPRI_2024_Projections.xlsx` mirror is likewise preserved. The oversized all-scenario site simulation remains local under `outputs/`. The compact dashboard snapshot covers presentation use. See the [GitHub manifest](../../docs/github_manifest.md).

## Classification register

Each retained file is assigned its primary role. Patterns below apply to all matching files, and this README and the emissions README document the inventory.

| Primary role | File or group |
| --- | --- |
| Required by dashboard | The seven files listed in Essential dashboard snapshot, counting CSV and JSON separately |
| Required by reproducible example | `data_centers.csv`, `master_sites.csv`, `table3.csv`, `site_aqueduct_basins.csv`, `community_exposure_acs2023.csv`, `emissions/egrid2023_factors.csv`, `emissions/site_egrid_mapping.csv`, the `energy_scenarios/floor_area_1.0/low_ai_inference.csv` baseline, `huc8_analysis_boundaries.gpkg`, `animation_state_outlines.gpkg` |
| Final scientific result | `data_centers_with_energy.csv`, `data_centers_with_energy_climate.csv`, `site_pue_climate.csv`, `k_estimate.json`, the other `energy_scenarios/` CSVs, `emissions/data_centers_with_emissions.csv`, `emissions/same_facility_comparison.csv`, `emissions/same_facility_co2_by_subregion.png`, `aqueduct_annual_screening_2023_2030.csv`, `community_exposure.csv` |
| Intermediate or supporting QA | `EPRI_2024_Projections.xlsx` mirror, `aqueduct2030_normalized.csv`, `us_states_2023.gpkg`, `huc8_dashboard_names.csv`, both `tracts_*.gpkg` caches, `im3_county_review.csv`, `master_sites_with_huc8_review.csv`, `emissions/emissions_review.csv`, and the provenance/report JSON files other than the dashboard snapshot manifest and PUE fit report |
