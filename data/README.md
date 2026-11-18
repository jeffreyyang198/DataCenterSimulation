# Data inventory

Keep raw inputs under `data/raw/`, which Git ignores. Source acquisition and regeneration require those files. The dashboard loads the smaller checked snapshot from [processed data](processed/README.md). See [data provenance](../docs/data_sources.md) for transformation rules and source coverage.

| Source | Version or period | Purpose | Expected local raw path | Raw in repository |
| --- | --- | --- | --- | --- |
| [IM3 Atlas](https://im3.pnnl.gov/datacenter-atlas) | 2026.02.09 | Site coordinates, footprint, operator and site type | `im3/p147s-4h760/im3_open_source_data_center_atlas_v2026.02.09/` | No |
| [EPA eGRID](https://www.epa.gov/egrid) | 2023 | Subregion geometry, CO₂, CO₂e, NOₓ and SO₂ factors | `egrid/egrid2023.xlsx`, `egrid/subregions.zip` | No |
| EPRI | 2024 workbook, 2023 and 2030 endpoints | State-specific growth scenarios | `epri/EPRI_2024_Projections.xlsx` | Raw directory excluded. A previously tracked workbook mirror exists in `data/processed/` |
| Siddik supplemental tables and geometry | Supplied study supplement | HUC8 geometry, WF and WSF coefficients, direct-water method | `siddik/SI_Shapefile.*`, `siddik/Results.xlsx`, `siddik/Input data.xlsx` | No |
| Census ACS | 2019–2023 five-year, B01003 | Tract total population | `census/acs2023/acsdt5y2023-b01003.dat` | No |
| Census TIGER/Line and cartographic boundaries | 2023 | Tracts and state display geometry | `census/tiger2023/`, `census/state_boundaries_2023/cb_2023_us_state_500k.zip` | No |
| [WRI Aqueduct](https://github.com/wri/Aqueduct40) | 4.0, July 2023 and 2030-centered future endpoint | PFAF joins and external stress/depletion | `aqueduct/` baseline/future annual CSVs and `aqueduct/GDB/` | No |
| NASA CMIP6 | Supplied SSP2-4.5, 2023–2030, one model | Site-year background temperature | `nasa/processed_data_2023_2030-1.csv` | No |
| NOAA GHCN-Daily and operator PUE | NOAA 2014–2024 climate window, operator reporting periods in the input CSV | Cooling-degree-day model calibrated against reported PUE | `noaa/ghcnd/`; operator inputs in [model parameters](model_parameters/observed_pue.csv) | NOAA raw excluded. Curated PUE inputs proposed |

Paths in the inventory are relative to `data/raw/` unless explicitly linked elsewhere. Large source datasets are kept locally and are excluded from the GitHub review list. Review terms for the existing EPRI mirror before broad redistribution. The dashboard runtime does not require that workbook.
