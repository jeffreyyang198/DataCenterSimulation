import unittest

import pandas as pd

from src.model.scenarios import TemporalScenario
from src.model.temporal_projection import (
    aggregate_state_baseline,
    project_state_energy,
)


class TemporalProjectionTests(unittest.TestCase):

    def test_state_aggregation(self):
        sites = pd.DataFrame(
            {
                "state_abbr": [
                    "PA",
                    "PA",
                    "VA",
                ],
                "estimated_annual_facility_energy_mwh": [
                    100.0,
                    200.0,
                    500.0,
                ],
            }
        )

        result = aggregate_state_baseline(
            sites
        )

        pa = result.loc[
            result["state"] == "PA"
        ].iloc[0]

        self.assertEqual(
            pa["baseline_modeled_mwh"],
            300.0,
        )

        self.assertEqual(
            pa["modeled_site_count"],
            2,
        )

    def test_missing_energy_not_treated_as_zero_site(self):
        sites = pd.DataFrame(
            {
                "state_abbr": [
                    "PA",
                    "PA",
                ],
                "estimated_annual_facility_energy_mwh": [
                    100.0,
                    float("nan"),
                ],
            }
        )

        result = aggregate_state_baseline(
            sites
        )

        self.assertEqual(
            result.loc[
                0,
                "baseline_modeled_mwh",
            ],
            100.0,
        )

        self.assertEqual(
            result.loc[
                0,
                "modeled_site_count",
            ],
            1,
        )

    def test_projection_compounds_over_time(self):
        baseline = pd.DataFrame(
            {
                "state": ["PA"],
                "baseline_modeled_mwh": [
                    1000.0
                ],
            }
        )

        scenario = TemporalScenario(
            name="moderate",
            start_year=2023,
            end_year=2025,
            annual_growth_rate=0.05,
        )

        result = project_state_energy(
            baseline,
            scenario,
        )

        self.assertEqual(
            result["year"].tolist(),
            [
                2023,
                2024,
                2025,
            ],
        )

        self.assertAlmostEqual(
            result.loc[
                result["year"] == 2023,
                "projected_energy_mwh",
            ].iloc[0],
            1000.0,
        )

        self.assertAlmostEqual(
            result.loc[
                result["year"] == 2024,
                "projected_energy_mwh",
            ].iloc[0],
            1050.0,
        )

        self.assertAlmostEqual(
            result.loc[
                result["year"] == 2025,
                "projected_energy_mwh",
            ].iloc[0],
            1102.5,
        )

    def test_cumulative_energy(self):
        baseline = pd.DataFrame(
            {
                "state": ["PA"],
                "baseline_modeled_mwh": [
                    100.0
                ],
            }
        )

        scenario = TemporalScenario(
            name="no_growth",
            start_year=2023,
            end_year=2025,
            annual_growth_rate=0.0,
        )

        result = project_state_energy(
            baseline,
            scenario,
        )

        self.assertEqual(
            result[
                "cumulative_projected_energy_mwh"
            ].tolist(),
            [
                100.0,
                200.0,
                300.0,
            ],
        )


if __name__ == "__main__":
    unittest.main()