# Included

[Review list](../github_files_to_commit.txt) contains the proposed changed and new paths for the integration commit. This manifest also describes the relevant files already tracked on the branch.

## Source

`src/clean/`, `src/geo/`, `src/model/`, `src/impact/`, `src/pipeline/`, `src/analysis/`, `src/validation/`, `src/visualization/` and `extra_functions/` support the scientific workflow. Existing imports and entry points retain their paths. `build_database.py` is the compatibility entry point. `requirements.txt` identifies the tested dependencies.

## Tests

The `tests/` suite covers scientific calculations, data integration, watershed grouping and navigation logic. `pytest.ini` and `scripts/smoke_test_dashboard.py` provide runnable validation.

## Documentation

The root README and [documentation index](index.md) link the architecture, methodology, results, limitations, implementation examples, provenance and demo instructions. `manual/` contains existing methodological provenance. The [data inventory](../data/README.md) and [processed dataset guide](../data/processed/README.md) document acquisition and reuse.

## Processed data

The compact snapshot and its hash manifest, display GeoJSON, site inventory, crosswalk and dissolved proximity estimates support offline startup. Climate PUE and energy outputs support the current analysis. Existing processed inputs and validation assets remain at their canonical paths.

## Final tables

[Final tables](../outputs/final_tables/README.md) contains six publication copies. The original tables remain the paths that the dashboard and scripts read. The validation compares each copy with its original.

## Figures

[Figures](../outputs/figures/README.md) indexes the existing figure series and diagnostics. Earlier fixed-PUE figures are labeled in the results page. Current climate-adjusted values are available in the final tables.

## Dashboard

`src/dashboard/`, the two presentation scripts and the local dashboard outputs support offline U.S. → state → full HUC8 → site selection. `outputs/dashboard/PRESENTATION_BACKUP.txt` records the fallback paths.

## Animation

The existing presentation MP4 is approximately 3.6 MiB, and the poster is approximately 0.3 MiB. Both remain tracked. They depict the earlier simulation and can be regenerated from local inputs with the animation module when needed.

# Excluded

## Raw public data

Git ignores `data/raw/`, including the raw Aqueduct geodatabase and annual CSV, Siddik shapefile, Census, eGRID, NOAA, IM3, EPRI and NASA inputs. The existing workbook mirror under `data/processed/` is already tracked. Verify its redistribution terms with the team before a public release.

## Large local artifacts

The complete site simulation CSV and the redundant climate-scenario emissions detail CSV remain local. The compact site snapshot and selected summaries are tracked. The size review found no tracked file over 90 MiB. See the [processed dataset guide](../data/processed/README.md) for the larger existing tract caches.

## Cache / temporary files

Keep the nested `DataCenterSimulation/` directory outside the review list. Ignore environments, caches, editor workspace files, logs, backup scripts and credential files. Empty, untracked scaffolds stay local. The current branch also contains previously tracked outputs unrelated to this dashboard. They are outside the proposed changes. Any decision to remove legacy tracked artifacts belongs to the team.

## Audit and handoff

The release review checks the named paths, file sizes, ignore rules and credential patterns. Only filenames and pattern names are reported for potential matches. The review list describes the final submission follow-up, while the history contains the earlier integration package.
