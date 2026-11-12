import unittest

import pandas as pd

from src.impact.temporal_emissions import (
    LB_TO_METRIC_TONNES,
    prepare_state_growth_factors,
    project_temporal_site_emissions,
)


class TemporalEmissionsTests(unittest.TestCase):

    def sample_epri(self):
        return pd.DataFrame(
            {
                "state_abbr": [
                    "PA",
                    "PA",
                ],
                "scenario": [
                    "moderate",
                    "moderate",
                ],
                "year": [
                    2023,
                    2024,
                ],
                "projected_epri_load_mwh": [
                    1000.0,
                    1100.0,
                ],
            }
        )

    def sample_sites(self):
        return pd.DataFrame(
            {
                "site_id": [
                    "A",
                ],
                "state_abbr": [
                    "PA",
                ],
                "estimated_annual_facility_energy_mwh": [
                    100.0,
                ],
            }
        )

    def sample_mapping(self):
        return pd.DataFrame(
            {
                "site_id": [
                    "A",
                ],
                "egrid_subregion": [
                    "RFCW",
                ],
            }
        )

    def sample_factors(self):
        return pd.DataFrame(
            {
                "egrid_subregion": [
                    "RFCW",
                ],
                "co2_lb_per_mwh": [
                    1000.0,
                ],
                "co2e_lb_per_mwh": [
                    1010.0,
                ],
                "nox_lb_per_mwh": [
                    0.5,
                ],
                "so2_lb_per_mwh": [
                    0.2,
                ],
            }
        )

    def test_growth_factor(self):
        growth = prepare_state_growth_factors(
            self.sample_epri()
        )

        self.assertAlmostEqual(
            growth.loc[
                growth["year"] == 2023,
                "epri_growth_factor",
            ].iloc[0],
            1.0,
        )

        self.assertAlmostEqual(
            growth.loc[
                growth["year"] == 2024,
                "epri_growth_factor",
            ].iloc[0],
            1.1,
        )

    def test_energy_projection(self):
        growth = prepare_state_growth_factors(
            self.sample_epri()
        )

        result = project_temporal_site_emissions(
            self.sample_sites(),
            self.sample_mapping(),
            self.sample_factors(),
            growth,
        )

        projected_2024 = result.loc[
            result["year"] == 2024,
            "projected_energy_mwh",
        ].iloc[0]

        self.assertAlmostEqual(
            projected_2024,
            110.0,
        )

    def test_emissions_conversion(self):
        growth = prepare_state_growth_factors(
            self.sample_epri()
        )

        result = project_temporal_site_emissions(
            self.sample_sites(),
            self.sample_mapping(),
            self.sample_factors(),
            growth,
        )

        co2_2023 = result.loc[
            result["year"] == 2023,
            "co2_metric_tonnes",
        ].iloc[0]

        expected = (
            100.0
            * 1000.0
            * LB_TO_METRIC_TONNES
        )

        self.assertAlmostEqual(
            co2_2023,
            expected,
        )

    def test_missing_epri_state_retained(self):
        sites = pd.DataFrame(
            {
                "site_id": ["A"],
                "state_abbr": ["PR"],
                "estimated_annual_facility_energy_mwh": [
                    100.0
                ],
            }
        )

        growth = prepare_state_growth_factors(
            self.sample_epri()
        )

        result = project_temporal_site_emissions(
            sites,
            self.sample_mapping(),
            self.sample_factors(),
            growth,
        )

        self.assertEqual(
            len(result),
            1,
        )

        self.assertEqual(
            result.loc[
                0,
                "temporal_emissions_status",
            ],
            "no_epri_growth",
        )

        self.assertTrue(
            pd.isna(
                result.loc[
                    0,
                    "projected_energy_mwh",
                ]
            )
        )


if __name__ == "__main__":
    unittest.main()