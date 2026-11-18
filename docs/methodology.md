# Methodology

## Facility electricity

For building footprint \(A\) in ft², assumed gross-area multiplier \(m\), calibrated IT power density \(d\) in W/ft², workload utilization \(u\), and idle fraction \(f\):

```text
Rated IT power (MW)   = A × m × d / 1,000,000
Average IT power (MW) = Rated IT power × [f + u × (1 − f)]
Annual facility MWh   = Average IT power × PUE × 8,760
PUE                   = facility electricity / IT electricity
```

Low, reference and high density use the calibration's 25th, 50th and 75th percentiles. The current screening run uses low density, the AI-inference scenario and \(m=1.0\). Campus and point records carry no footprint-based estimate. See [power density](../src/model/power_density.py), [energy equations](../src/model/energy_model.py) and [scenario parameters](../data/model_parameters/energy_scenarios.csv).

The NOAA model derives cooling-degree-day (CDD) climatology from historical daily records and fits a slope \(k\) from within-operator differences in relative overhead and CDD. The site PUE is anchored at 1.40 at the median site CDD:

```text
PUEᵢ = 1 + 0.40 × max(0, 1 + k × (CDDᵢ − CDDref) / CDDref)
```

The annual simulation carries that same site PUE across years. The energy model uses the workload PUE when fitted site data are unavailable. [PUE fit and inputs](../extra_functions/pue_climate.py)

## 2023–2030 growth and impact accounting

The EPRI endpoint ratio yields a state/scenario annual growth rate \(r=(L_{2030}/L_{2023})^{1/7}-1\). For each site, \(E_y=E_{2023}(1+r)^{y-2023}\). Each annual electricity estimate drives the following quantities:

```text
Emissions (metric tonnes) = E_y × eGRID factor (lb/MWh) × 0.00045359237
Direct water (m³)          = E_y × 1.8 m³/MWh
Water footprint (m³)       = E_y × Siddik WF_1MW_DC (m³/MWh)
Scarcity footprint (m³-eq) = E_y × Siddik WSF_1MW_DC (m³-eq/MWh)
```

Use fixed 2023 eGRID rates for CO₂, CO₂e, NOₓ and SO₂. Siddik WF already includes direct and indirect water. WSF already incorporates scarcity weighting. Cumulative emissions and direct water start at the 2023 annual amount, then add each subsequent year. A missing annual value makes cumulative history unknown from that year onward. Aggregates sum known sites and publish coverage. [Stateful implementation](../src/model/stateful_community.py) · [Water coefficient provenance](data_sources.md#verified-direct-data-center-water-demand)

## Geographic and environmental context

- **Population.** Construct site circles at 1, 3 and 5 km using local azimuthal equidistant projections. Measure intersections with ACS/TIGER tracts in equal-area EPSG:6933. Each tract contributes its population multiplied by the fraction of its area in the buffer. Group totals intersect dissolved 5 km buffers, so an overlap is counted once within that group. ACS 2019–2023 population stays static.
- **Aqueduct.** Join each site to its PFAF region, independently of HUC8. For stress and depletion, intermediate years use `baseline + ((year − 2023)/7) × (2030 − baseline)` where both endpoints exist. The 2030 figure is a period-centered endpoint, and the anchored historical baseline is screening context. Supply and background demand remain in cm/year. The model keeps facility demand in m³/year separate.
- **NASA.** Join the supplied single-model CMIP6 SSP2-4.5 temperature values by site and year as projected background conditions. NOAA PUE calibration and NASA projections enter different parts of the analysis.
- **Watersheds.** Aggregate site quantity and coverage by HUC8. Use PCA and KMeans on screened, standardized features with separately documented ML-only imputation. Rank robustness and hotspot rules operate on the saved burden and scenario results. [HUC8 rules](huc8_analysis.md)

The presentation uses lower (EPRI low / Aqueduct optimistic), Central (moderate / business as usual) and higher (higher / pessimistic). The underlying simulation retains all 12 EPRI/Aqueduct combinations. [Data provenance](data_sources.md) · [Interpretation limits](limitations.md)
