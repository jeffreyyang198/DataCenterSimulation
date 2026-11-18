# Python implementation highlights

## GeoPandas spatial foundation

The spatial code uses library primitives to implement a project-specific assignment policy. In [HUC8 enrichment](../src/geo/enrich_huc8.py), `gpd.points_from_xy` and `gpd.GeoDataFrame` construct site points. `to_crs` aligns points with watershed boundaries, `gpd.sjoin` identifies intersections, and `make_valid` repairs invalid source geometry. `assign_huc8_to_sites` validates coordinates and records ambiguous matches.

[Community resource pressure](../src/pipeline/community_resource_pressure.py) implements independent PFAF assignments and 1, 3 and 5 km buffers. The geometry operations are `point.buffer`, tract `intersection`, and `union_all` for dissolved buffers. Project logic converts geodesic scale to local projected meters, computes intersected shares and tracks incomplete tract coverage. The [stateful proximity cache](../src/analysis/stateful_community_simulation.py) repeats the dissolve by distinct national/HUC8/PFAF groups.

GeoPackage layers preserve analysis geometry and CRS metadata. The [dashboard geometry builder](../src/dashboard/data.py) exports local GeoJSON and keeps full watershed boundaries for cross-state navigation.

## Energy modeling and yearly growth

[Power density](../src/model/power_density.py) implements calibrated quantiles and footprint-to-rated-IT-MW conversion. [Energy model functions](../src/model/energy_model.py) apply workload utilization, idle fraction, PUE and annual hours:

```text
rated_mw = footprint_ft² × gross_area_multiplier × density_w_per_ft² / 1,000,000
average_mw = idle_mw + utilization × (rated_mw − idle_mw)
facility_mwh = average_mw × pue × 8,760
```

[EPRI projections](../src/model/epri_projection.py) infer each state/scenario compound rate from its endpoints. [Stateful accounting](../src/model/stateful_community.py) multiplies the site's baseline by each annual growth factor. Each cumulative series is keyed by site and scenario and propagates missing history.

## Water, emissions and environmental integration

[The stateful model](../src/model/stateful_community.py) converts eGRID lb/MWh to metric tonnes, calculates direct water as `projected_energy_mwh × 1.8 m³/MWh`, and separately applies the Siddik WF and WSF coefficients. It guards join cardinality across site, year, eGRID, HUC8 and PFAF identifiers. Aqueduct depth and facility volume remain separate, and the NASA join supplies external climate context. [Equations and provenance](methodology.md)

## Watershed analytics and display

[HUC8 profiles](../src/model/huc8_profiles.py) implement coverage-aware aggregation and intensity denominators, feature selection and transforms, ML-only imputation, standardized PCA/KMeans inputs, cluster eligibility, hotspot trajectories and scenario rank robustness. The [dashboard data layer](../src/dashboard/data.py) indexes saved tables by site or HUC8, year and scenario. [The navigation reducer](../src/dashboard/callbacks.py) clears descendants when their parent changes, preserves cross-state sites in the selected watershed, and selects the correct summaries and maps.

The [animation renderer](../src/visualization/animate_resource_pressure.py) reads validated annual state and basin tables, checks provenance, and generates frames and a presentation MP4.

## What we implemented beyond library calls

> GeoPandas supplies core geometric operations; the project's substantive contribution is the domain-specific scientific modeling, temporal simulation, cross-dataset integration, watershed analytics, validation logic, and interactive application built on top of those operations.

The project code defines scientific equations, scenario logic, unit conversions, temporal growth, cumulative accounting, missing-data behavior, watershed aggregation, screening thresholds, feature preparation, scenario sensitivity and dashboard interaction. GeoPandas supplies primitive spatial operations. scikit-learn and Plotly supply model and rendering primitives used by the project's analysis and interface.
