import unittest

import pandas as pd

from src.impact.temporal_water import project_temporal_site_water


class TemporalWaterTests(unittest.TestCase):

    def setUp(self):
        self.sites = pd.DataFrame(
            {
                "site_id": ["A", "B", "C"],
                "state_abbr": ["VA", "VA", "PR"],
                "annual_energy_mwh": [100.0, 200.0, 50.0],
            }
        )

        self.water = pd.DataFrame(
            {
                "site_id": ["A", "B", "C"],
                "huc8": ["02070010", "02070010", pd.NA],
                "WF_1MW_DC": [2.0, pd.NA, pd.NA],
                "WSF_1MW_DC": [5.0, pd.NA, pd.NA],
            }
        )

        self.growth = pd.DataFrame(
            {
                "state_abbr": ["VA", "VA"],
                "scenario": ["moderate", "moderate"],
                "year": [2023, 2024],
                "growth_factor": [1.0, 1.1],
            }
        )

    def test_water_projection(self):
        result = project_temporal_site_water(
            self.sites,
            self.water,
            self.growth,
        )

        row = result[
            (result["site_id"] == "A")
            & (result["year"] == 2024)
        ].iloc[0]

        self.assertAlmostEqual(row["projected_energy_mwh"], 110.0)
        self.assertAlmostEqual(row["annual_water_footprint_m3"], 220.0)
        self.assertAlmostEqual(
            row["annual_water_scarcity_footprint_m3_eq"],
            550.0,
        )

    def test_cumulative_water(self):
        result = project_temporal_site_water(
            self.sites,
            self.water,
            self.growth,
        )

        row = result[
            (result["site_id"] == "A")
            & (result["year"] == 2024)
        ].iloc[0]

        self.assertAlmostEqual(
            row["cumulative_water_footprint_m3"],
            420.0,
        )
        self.assertAlmostEqual(
            row["cumulative_water_scarcity_footprint_m3_eq"],
            1050.0,
        )

    def test_missing_water_factor_not_zero(self):
        result = project_temporal_site_water(
            self.sites,
            self.water,
            self.growth,
        )

        rows = result[result["site_id"] == "B"]

        self.assertTrue(
            rows["annual_water_footprint_m3"].isna().all()
        )
        self.assertTrue(
            rows["annual_water_scarcity_footprint_m3_eq"].isna().all()
        )
        self.assertTrue(
            (rows["water_status"] == "missing_water_factor").all()
        )

    def test_missing_huc8_retained(self):
        result = project_temporal_site_water(
            self.sites,
            self.water,
            self.growth,
        )

        row = result[result["site_id"] == "C"].iloc[0]

        self.assertEqual(row["water_status"], "no_epri_growth")
        self.assertFalse(row["has_huc8_mapping"])
        self.assertTrue(pd.isna(row["annual_water_footprint_m3"]))

    def test_duplicate_water_mapping_rejected(self):
        water = pd.concat(
            [self.water, self.water.iloc[[0]]],
            ignore_index=True,
        )

        with self.assertRaises(ValueError):
            project_temporal_site_water(
                self.sites,
                water,
                self.growth,
            )


if __name__ == "__main__":
    unittest.main()
