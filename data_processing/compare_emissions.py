import pandas as pd
import matplotlib.pyplot as plt

import emissions as EM

# parameters
FACILITY = dict(mw=100, pue=1.3, load_factor=0.8)
GRID_LOSS_PCT = 0.0
EXCLUDE = ["AKMS", "HIMS"]
LOCAL_RADIUS_KM = 50

# creates a dataframe specific to the subregions.
def compare_subregions(demand, egrid_sr, exclude=(), grid_loss_pct=0.0):

    rows = []
    for sub in egrid_sr.index:
        if sub in exclude or pd.isna(egrid_sr.loc[sub, "co2_lb_mwh"]):
            continue
        
        em = EM.estimate_emissions(demand["annual_mwh"], sub, egrid_sr, grid_loss_pct)
        sr = egrid_sr.loc[sub]
        rows.append({**em, "pct_of_subregion_generation": 100 * demand["annual_mwh"] / sr["net_gen_mwh"], "pct_of_subregion_capacity": 100 * demand["peak_mw"] / sr["capacity_mw"],})
    
    df = pd.DataFrame(rows).sort_values("co2_metric_tons").reset_index(drop=True)
    
    cleanest = df["co2_metric_tons"].iloc[0]
    
    df["times_cleanest"] = df["co2_metric_tons"] / cleanest
    df["vs_median_pct"] = 100 * (df["co2_metric_tons"] / df["co2_metric_tons"].median() - 1)
    
    return df


# plots CO2 emissions according to subregions.
def plot_subregions(df, demand, path="co2_by_subregion.png"):
    
    fig, ax = plt.subplots(figsize=(9, 0.32 * len(df) + 1.5))
    ax.barh(df["subregion"], df["co2_metric_tons"] / 1000, color="#4a7ab5")
    ax.axvline(df["co2_metric_tons"].median() / 1000, color="gray", ls="--", lw=1,
               label="median")
    ax.invert_yaxis()
    ax.set_xlabel("Annual CO2 (thousand metric tons)")
    ax.set_title(f"Same facility ({demand['annual_mwh']:,.0f} MWh/yr) "
                 f"in each eGRID subregion")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)


# outputs an emissions comparison csv for both subregions and sites.
egrid_sr = EM.load_egrid_subregions()
demand = EM.estimate_demand(**FACILITY)

print(f"Facility: {demand['demand_method']}")
print(f"Peak {demand['peak_mw']:,.1f} MW, {demand['annual_mwh']:,.0f} MWh/yr\n")

# every eGRID subregion.
by_sub = compare_subregions(demand, egrid_sr, EXCLUDE, GRID_LOSS_PCT)

cols = ["subregion", "subregion_name", "co2_rate_lb_per_mwh", "co2_metric_tons", "times_cleanest", "vs_median_pct", "pct_of_subregion_capacity"]

lo, hi = by_sub.iloc[0], by_sub.iloc[-1]

by_sub.to_csv("compare_subregions.csv", index=False)

plot_subregions(by_sub, demand)