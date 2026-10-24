import os
import pandas as pd
import sys

# build_water_impact_df() return a new dataframe

def estimate_total_water_use(csv_file_path: str) -> pd.DataFrame:
    """
    Input: File path string of the CSV file containing Table 3
    - includes the Water footprint, carbon footprint, and water scarcity footprint
    - each value is for a hypothetical 1 MW data center placed within each US subbasin
    - subbasin is identified by the HUC8 code

    Output: Pandas dataframe containing the subbasin_code, water_footprint, water_impact columns
    """
    initial_df = pd.read_csv(csv_file_path)

    # create final dataframe
    final_df = pd.DataFrame({
        "subbasin_code" : df["HUC8"],
        "water_use" : df["WF_1MW_DC"],
        "water_scarcity" : df["WSF_1MW_DC"]
    })

    return final_df


water_df = estimate_total_water_use(INPUT_DATA)
print(water_df[:10])

# calculate stats for water use
avg_water_use = water_df["water_use"].mean()

# calculate stats for water impact
avg_water_scarcity = water_df["water_scarcity"].mean()

# report stats
print("Water Usage and Impact Summary")
print("The following are for a hypothetical 1 MW data center installed across the subbasins in the US")
print("-" * 20)
print(f"Average Water Use: {avg_water_use:.2f} m3/MWh")
print(f"Average Water Scarcity: {avg_water_scarcity:.2f} m3-eq/MWh")