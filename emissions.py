import math
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

# dataset variables.
EGRID_FILE = "egrid2023_data_rev2.xlsx"
EGRID_YEAR_SUFFIX = "23"
EIA860_PLANT_FILE = "2___Plant_Y2024.xlsx"
EIA860_GEN_FILE = "3_1_Generator_Y2024.xlsx"

# eGRID columns.
EG_SR = {"subregion": "SUBRGN", "name": "SRNAME",
         "net_gen_mwh": "SRNGENAN", "capacity_mw": "SRNAMEPCAP",
         "co2_lb_mwh": "SRCO2RTA", "co2e_lb_mwh": "SRC2ERTA",
         "nox_lb_mwh": "SRNOXRTA", "so2_lb_mwh": "SRSO2RTA"}

EG_PL = {"plant_id": "ORISPL", "name": "PNAME", "lat": "LAT", "lon": "LON", "subregion": "SUBRGN"}

# EIA860 column names.
E860_PLANT = {"plant_id": "Plant Code", "name": "Plant Name", "state": "State",
              "lat": "Latitude", "lon": "Longitude",
              "ba": "Balancing Authority Code"}

E860_GEN = {"plant_id": "Plant Code", "capacity_mw": "Nameplate Capacity (MW)", "technology": "Technology", "fuel": "Energy Source 1"}

# Electricity in kWh per square foot per year.
EUI_KWH_PER_SQFT = {"commercial_average": 12.6,}

HOURS_PER_YEAR = 8760
LB_PER_METRIC_TON = 2204.62
LB_PER_SHORT_TON = 2000.0


# load the data.
def load_egrid_subregions(path=EGRID_FILE, suffix=EGRID_YEAR_SUFFIX):

    df = pd.read_excel(path, sheet_name=f"SRL{suffix}", header=1)
    df = df[list(EG_SR.values())].rename(columns={v: k for k, v in EG_SR.items()})
    
    return df.set_index("subregion")


def load_egrid_plants(path=EGRID_FILE, suffix=EGRID_YEAR_SUFFIX):
    
    df = pd.read_excel(path, sheet_name=f"PLNT{suffix}", header=1)
    df = df[list(EG_PL.values())].rename(columns={v: k for k, v in EG_PL.items()})
    
    return df.dropna(subset=["lat", "lon", "subregion"])


# read EIA860 data.
def load_eia860(plant_path=EIA860_PLANT_FILE, gen_path=EIA860_GEN_FILE):
    
    plants = pd.read_excel(plant_path, sheet_name="Plant", header=1)
    plants = plants[list(E860_PLANT.values())].rename(
        columns={v: k for k, v in E860_PLANT.items()})

    gens = pd.read_excel(gen_path, sheet_name="Operable", header=1)
    gens = gens[list(E860_GEN.values())].rename(
        columns={v: k for k, v in E860_GEN.items()})
    
    gens["capacity_mw"] = pd.to_numeric(gens["capacity_mw"], errors="coerce")

    cap = (gens.groupby(["plant_id", "technology", "fuel"], dropna=False)
               ["capacity_mw"].sum().reset_index())
    
    out = cap.merge(plants, on="plant_id", how="left", validate="many_to_one")
    
    out["lat"] = pd.to_numeric(out["lat"], errors="coerce")
    out["lon"] = pd.to_numeric(out["lon"], errors="coerce")
    
    return out.dropna(subset=["lat", "lon"])


# helper function to calculate latitude and longitude values.
def haversine_km(lat1, lon1, lat2, lon2):
    
    r = 6371.0
    lat1, lon1 = math.radians(lat1), math.radians(lon1)
    lat2 = lat2.apply(math.radians) if hasattr(lat2, "apply") else math.radians(lat2)
    lon2 = lon2.apply(math.radians) if hasattr(lon2, "apply") else math.radians(lon2)
    
    dlat, dlon = lat2 - lat1, lon2 - lon1
    
    a = ((dlat / 2).apply(math.sin) ** 2
         + math.cos(lat1) * lat2.apply(math.cos) * (dlon / 2).apply(math.sin) ** 2)
    
    return 2 * r * a.apply(lambda x: math.asin(math.sqrt(x)))


# define the eGRID subregions.
def find_subregion(lat, lon, egrid_plants=None, shapefile=None):
    
    if shapefile:
        
        regions = gpd.read_file(shapefile).to_crs("EPSG:4326")
        hit = regions[regions.contains(Point(lon, lat))]
        
        if len(hit):
            col = "SUBRGN" if "SUBRGN" in hit.columns else hit.columns[0]
            
            return hit.iloc[0][col], "shapefile"
    
    d = haversine_km(lat, lon, egrid_plants["lat"], egrid_plants["lon"])
    
    return egrid_plants.loc[d.idxmin(), "subregion"], "nearest_plant (approximate)"


# estimation of the energy demand.
def estimate_demand(mw=None, sqft=None, building_type="commercial_average",
                    eui_kwh_per_sqft=None, w_per_sqft=None,
                    load_factor=1.0, pue=1.0):
    
    if mw is not None:
        peak_mw = mw * pue
        annual_mwh = peak_mw * HOURS_PER_YEAR * load_factor
        method = f"known MW ({mw} MW, PUE {pue}, load factor {load_factor})"
    
    elif sqft is not None and w_per_sqft is not None:
        peak_mw = sqft * w_per_sqft / 1e6 * pue
        annual_mwh = peak_mw * HOURS_PER_YEAR * load_factor
        method = (f"square footage x power density ({w_per_sqft} W/sqft, "
                  f"PUE {pue}, load factor {load_factor})")
    
    elif sqft is not None:
        
        eui = eui_kwh_per_sqft or EUI_KWH_PER_SQFT.get(building_type)
        
        annual_mwh = sqft * eui / 1000
        peak_mw = annual_mwh / HOURS_PER_YEAR / load_factor
        method = f"square footage x EUI ({eui} kWh/sqft/yr, load factor {load_factor})"
    
    return {"peak_mw": peak_mw, "annual_mwh": annual_mwh, "demand_method": method}


# emissions estimation function.
def estimate_emissions(annual_mwh, subregion, egrid_sr, grid_loss_pct=0.0):
    
    sr = egrid_sr.loc[subregion]
    mwh_generated = annual_mwh / (1 - grid_loss_pct / 100)
    co2_lb = mwh_generated * sr["co2_lb_mwh"]
    co2e_lb = mwh_generated * sr["co2e_lb_mwh"]
    
    return {
        "subregion": subregion,
        "subregion_name": sr["name"],
        "co2_rate_lb_per_mwh": sr["co2_lb_mwh"],
        "mwh_incl_losses": mwh_generated,
        "co2_metric_tons": co2_lb / LB_PER_METRIC_TON,
        "co2_short_tons": co2_lb / LB_PER_SHORT_TON,
        "co2e_metric_tons": co2e_lb / LB_PER_METRIC_TON,
        "nox_lb": mwh_generated * sr["nox_lb_mwh"],
        "so2_lb": mwh_generated * sr["so2_lb_mwh"],
    }


# energy burden of the grid.
def calculate_grid_burden(peak_mw, annual_mwh, lat, lon, subregion, egrid_sr, eia860, radius_km=50):
    
    sr = egrid_sr.loc[subregion]

    d = haversine_km(lat, lon, eia860["lat"], eia860["lon"])
    
    nearby = eia860.loc[d <= radius_km].copy()
    
    local_cap = nearby["capacity_mw"].sum()
    local_mix = (nearby.groupby("technology")["capacity_mw"].sum().sort_values(ascending=False))

    return {
        "pct_of_subregion_generation": 100 * annual_mwh / sr["net_gen_mwh"],
        "pct_of_subregion_capacity": 100 * peak_mw / sr["capacity_mw"],
        "local_radius_km": radius_km,
        "local_plants": nearby["plant_id"].nunique(),
        "local_capacity_mw": local_cap,
        "pct_of_local_capacity": (100 * peak_mw / local_cap) if local_cap else float("nan"),
        "local_capacity_mix_mw": local_mix.round(1).to_dict(),
    }


# determines the emissions based on facility.
def analyze_facility(name, lat, lon, egrid_sr, egrid_plants, eia860, shapefile=None, grid_loss_pct=0.0, radius_km=50, **demand_kwargs):
    
    demand = estimate_demand(**demand_kwargs)
    subregion, lookup = find_subregion(lat, lon, egrid_plants, shapefile)
    emissions = estimate_emissions(demand["annual_mwh"], subregion, egrid_sr, grid_loss_pct)
    burden = calculate_grid_burden(demand["peak_mw"], demand["annual_mwh"], lat, lon, subregion, egrid_sr, eia860, radius_km)
    
    return {"facility": name, "lat": lat, "lon": lon, "subregion_lookup": lookup, **demand, **emissions, **burden}