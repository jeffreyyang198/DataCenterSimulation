# eGRID electricity emissions

Run from the project root with the dependencies in requirements.txt installed:

```sh
python src/model/apply_egrid_emissions.py
```

The raw inputs go in `data/raw/egrid/` (ignored by Git):

| Local name | EPA download |
| --- | --- |
| subregions.zip | https://www.epa.gov/system/files/other-files/2025-01/egrid2023_subregions.zip |
| multiple.zip | https://www.epa.gov/system/files/other-files/2025-01/egrid2023_multiple_subregions.zip |
| egrid2023.xlsx | https://www.epa.gov/system/files/documents/2025-06/egrid2023_data_rev2.xlsx |

Sources: [EPA detailed data](https://www.epa.gov/egrid/detailed-data) and [EPA mapping files](https://www.epa.gov/egrid/egrid-mapping-files). Factors use eGRID2023 revision 2, SRL23 annual total-output rates. Downloaded October 21, 2026. File hashes are recorded in emissions_report.json.

Site coordinates are intersected with primary boundaries and the separate multiple-subregion layer. These are geographic screening assignments, not verified electricity-supplier assignments. Sites in shared areas or touching multiple primary subregions receive no assigned factor or emissions until utility verification. EPA recommends Power Profiler and the supplying utility to resolve shared areas. Candidates list primary polygon hits only; it is not a complete list of possible suppliers in shared areas.

The energy input is the existing hypothetical 8,760-hour scenario, not measured 2023 consumption. Its assumptions and all original site fields are retained. CO2, CO2e, annual NOx, and SO2 are calculated separately as energy MWh × rate lb/MWh × 0.45359237 / 1,000, yielding metric tonnes. CO2e already includes greenhouse gases; do not add CO2 to it. There is no grid-loss uplift, marginal-emissions model, or contractual renewable adjustment. Air pollutant estimates do not locate emissions at the data center or estimate nearby exposure.

Outputs:

- `site_egrid_mapping.csv`: every site, geographic candidates, assigned subregion, and mapping status.
- `egrid2023_factors.csv`: annual emission factors in lb/MWh.
- `data_centers_with_emissions.csv`: all input records plus factors, statuses, and four annual emissions estimates. Missing estimates stay missing.
- `emissions_review.csv`: sites without an emissions estimate. Use the mapping status as well as emissions status; missing energy takes precedence in emissions status.
- `emissions_report.json`: counts, source URLs, hashes, and assumptions.
- `same_facility_comparison.csv` and `.png`: the same hypothetical 911,040 MWh/year facility across all 27 eGRID subregions, using 2023 rates. The dashed line is the unweighted median across subregions. These updated factors can differ from the supplied chart, whose factor year was unspecified.

No site emissions totals are produced because source facility overlaps remain unresolved. Keep these outputs separate from the original energy table. Balancing-authority monthly files are a separate framework and are not joined here.
