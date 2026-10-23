# Data Center Community Impact

A Python-based simulation and geospatial analysis project for estimating the downstream resource and community impacts of U.S. data centers.

The project combines publicly available information on data-center locations, electricity infrastructure, regional emissions, population, weather, and water stress to compare how the burden of data-center development may vary across communities and geographic regions.

## Scientific Question

As data centers expand across the United States, their electricity and water requirements may place additional pressure on local infrastructure and surrounding communities.

This project asks:

**How can publicly available geographic, infrastructure, and environmental data be combined to estimate and compare the downstream community impacts of data centers across the United States?**

Rather than attempting to predict exact economic or social outcomes, the project focuses on measurable resource-based effects, including:

- Electricity demand
- Electricity-related emissions
- Regional generation capacity
- Population exposure
- Weather and temperature
- Cooling-related water demand
- Water stress

## Current Progress

The project currently includes:

- A cleaned master dataset of **1,474 IM3 data-center records**
- Separation of IM3 records into:
  - 1,237 buildings
  - 132 campuses
  - 105 point locations
- A calibrated footprint-to-power estimation model
- Low, reference, and high power-density scenarios
- Workload scenarios for AI training and AI inference
- Utilization, idle-power, and PUE modeling
- Estimates of:
  - Rated IT power
  - Average IT power
  - Annual facility electricity consumption
- Validation and outlier detection for modeled power estimates
- EPA eGRID subregion assignment
- Electricity-related estimates for:
  - CO₂
  - CO₂-equivalent
  - NOₓ
  - SO₂
- Automated tests for cleaning and modeling functions
- Manual implementations of core modeling equations for transparency and reproducibility

Current emissions estimates are available for more than 1,200 sites with both usable energy estimates and resolved eGRID assignments.

## Modeling Workflow

```text
IM3 data-center locations
        ↓
Clean and standardize site records
        ↓
Classify geometry
(building / campus / point)
        ↓
Estimate rated IT power
        ↓
Apply utilization + idle-power assumptions
        ↓
Estimate average IT power
        ↓
Apply PUE
        ↓
Estimate annual facility electricity consumption
        ↓
Assign eGRID subregion
        ↓
Estimate electricity-related emissions
        ↓
Integrate:
population + weather + water + power infrastructure
        ↓
Compare community burden across locations
```

## Energy Model

For supported building records, rated IT power is estimated using:

\[
P_{rated}
=
\frac{
A_{IM3}
\times
F_A
\times
D
}{
10^6
}
\]

where:

- \(A_{IM3}\) = IM3 building footprint area in ft²
- \(F_A\) = explicit effective-area multiplier
- \(D\) = calibrated power density in W/ft²

The current power-density calibration is derived from publicly reported U.S. data-center facilities with both gross area and IT capacity information.

Current scenarios are based on the calibration distribution:

- Low: 25th percentile
- Reference: median
- High: 75th percentile

Average IT power incorporates idle power:

\[
P_{avg}
=
P_{idle}
+
U(P_{rated}-P_{idle})
\]

where \(U\) represents workload utilization.

Annual facility electricity is then estimated as:

\[
E_{annual}
=
P_{avg}
\times
PUE
\times
8760
\]

These values are **scenario-based estimates and should not be interpreted as observed facility consumption**.

## Data Sources

### IM3 Open Source Data Center Atlas

Pacific Northwest National Laboratory

Used for:

- Data-center coordinates
- State and county
- Operator
- Facility name
- Polygon footprint
- Site geometry type

https://im3.pnnl.gov/datacenter-atlas

### Lawrence Berkeley National Laboratory

United States Data Center Energy Usage Report

Used to support assumptions related to:

- Power Usage Effectiveness (PUE)
- Utilization
- AI workload characteristics
- Data-center electricity demand

### EPA eGRID

Used for:

- eGRID subregions
- Regional CO₂ emission factors
- CO₂-equivalent emission factors
- NOₓ emission factors
- SO₂ emission factors

https://www.epa.gov/egrid

### EIA-860

Used for planned analysis of:

- Power plant locations
- Generator capacities
- Generator technologies
- Primary energy sources
- Generator operating status
- Balancing authorities
- NERC regions

https://www.eia.gov/electricity/data/eia860/

### U.S. Census

American Community Survey and TIGER/Line data will be used to estimate population surrounding data centers.

Planned analysis includes population within:

- 1 km
- 3 km
- 5 km

of each facility.

### NOAA Climate Data Online

Planned use includes:

- Daily temperature records
- Seasonal conditions
- Temperature-related changes in cooling and electricity demand

### Water Data

Planned sources include:

- USGS Water Data
- EIA thermoelectric cooling-water data
- WRI Aqueduct Water Risk Atlas
- Published data-center water-footprint literature

## Important Assumptions

### IM3 Area

IM3 `sqft` represents polygon surface area rather than verified total usable or IT floor area.

For this reason:

- Building records may be used for footprint-based scenario estimation
- Campus polygons are not treated as equivalent to building floor area
- Point records do not contain usable footprint area
- Campus and building polygons may overlap

### Power Estimates

Estimated MW values are modeled rather than observed.

Results depend on assumptions including:

- Power density
- Effective-area multiplier
- Workload
- Utilization
- Idle-power fraction
- PUE

Sensitivity analysis is therefore an important part of the project.

### Electricity Emissions

eGRID emissions estimates represent emissions associated with regional electricity generation.

They do **not** imply that those pollutants are physically emitted next to the data center.

### Power Plants

Nearby or regional EIA-860 power plants are interpreted as electricity infrastructure.

Spatial proximity alone does **not** establish that a specific power plant supplies electricity to a particular data center.

## Current Limitations

- IM3 is not assumed to represent a complete census of every U.S. data center.
- Data-center footprints do not directly provide IT floor area.
- Campus and building polygons may overlap.
- IM3 does not directly provide facility workload or service model.
- Some eGRID assignments require additional utility verification.
- Population, weather, and water datasets may differ in spatial and temporal resolution.
- Modeled facility demand must be distinguished from measured electricity consumption.
- Regional generation capacity in MW should not be directly interpreted as annual electricity generation in MWh.
- Electricity-related emissions do not directly establish local pollution exposure around a data center.

## Next Steps

- Integrate Census population data
- Create 1 km, 3 km, and 5 km population-exposure buffers
- Integrate NOAA temperature data
- Clean and integrate EIA-860 plant and generator information
- Compare modeled data-center demand with regional electricity capacity
- Add water-use and water-stress metrics
- Investigate defensible classifications of data-center service models, including:
  - Hyperscale cloud
  - Colocation
  - Private enterprise
  - AI/HPC
  - Unknown
- Expand uncertainty and sensitivity analysis
- Develop a combined community-impact comparison framework
- Produce final geographic and comparative visualizations

## Reproducibility

The project separates raw data, processed data, modeling assumptions, simulation calculations, and validation results so that assumptions can be changed without modifying the original source datasets.

Core scientific equations are also implemented manually and documented to make the modeling process transparent and reproducible.

## Disclaimer

This project is intended as a scientific screening and simulation framework.

Results should be interpreted as **scenario-based estimates**, not direct measurements of individual data-center resource consumption, local pollution exposure, or utility-system behavior.
