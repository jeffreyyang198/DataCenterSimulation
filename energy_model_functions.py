import math
import pandas as pd
            
HOURS_PER_YEAR = 8760
LB_PER_METRIC_TON = 2204.62
LB_PER_SHORT_TON = 2000.0

# calculates distance based on latitude and longitude.
def haversine_km(lat1, lon1, lat2, lon2):
    
    r = 6371.0
    lat1, lon1 = math.radians(lat1), math.radians(lon1)

    lat2 = lat2.apply(math.radians) if hasattr(lat2, "apply") else math.radians(lat2)
    lon2 = lon2.apply(math.radians) if hasattr(lon2, "apply") else math.radians(lon2)
    
    dlat, dlon = lat2 - lat1, lon2 - lon1

    a = ((dlat / 2).apply(math.sin) ** 2 + math.cos(lat1) * lat2.apply(math.cos) * (dlon / 2).apply(math.sin) ** 2)

    return 2 * r * a.apply(lambda x: math.asin(math.sqrt(x)))

# emissions estimatinon function.
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