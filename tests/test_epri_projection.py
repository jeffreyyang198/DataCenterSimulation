import unittest

import pandas as pd

from src.model.epri_projection import (
    project_epri_annual,
    compare_modeled_to_epri,
)


class EPRIProjectionTests(unittest.TestCase):

    def sample_projection(self):
        return pd.DataFrame(
            {
                "state": ["Pennsylvania"],
                "state_abbr": ["PA"],
                "scenario": ["moderate"],
                "scenario_label_growth_rate": [0.05],
                "epri_2023_load_mwh": [1000.0],
                "epri_2023_state_share": [0.10],
                "epri_2030_load_mwh": [1400.0],
                "epri_2030_state_share": [0.15],
                "implied_annual_growth_rate": [
                    (1400 / 1000) ** (1 / 7) - 1
                ],
            }
        )

    def test_projection_preserves_endpoints(self):
        projection = project_epri_annual(
            self.sample_projection()
        )

        first = projection.loc[
            projection["year"] == 2023,
            "projected_epri_load_mwh",
        ].iloc[0]

        last = projection.loc[
            projection["year"] == 2030,
            "projected_epri_load_mwh",
        ].iloc[0]

        self.assertEqual(
            first,
            1000.0,
        )

        self.assertEqual(
            last,
            1400.0,
        )

    def test_projection_contains_all_years(self):
        projection = project_epri_annual(
            self.sample_projection()
        )

        self.assertEqual(
            projection["year"].tolist(),
            list(range(2023, 2031)),
        )

    def test_projection_grows_monotonically(self):
        projection = project_epri_annual(
            self.sample_projection()
        )

        values = projection[
            "projected_epri_load_mwh"
        ]

        self.assertTrue(
            values.is_monotonic_increasing
        )

    def test_compare_modeled_to_epri(self):
        modeled = pd.DataFrame(
            {
                "state": ["PA"],
                "baseline_modeled_mwh": [800.0],
                "modeled_site_count": [5],
            }
        )

        result = compare_modeled_to_epri(
            modeled,
            self.sample_projection(),
        )

        self.assertEqual(
            result.loc[
                0,
                "epri_2023_load_mwh",
            ],
            1000.0,
        )

        self.assertAlmostEqual(
            result.loc[
                0,
                "modeled_to_epri_ratio",
            ],
            0.8,
        )

        self.assertAlmostEqual(
            result.loc[
                0,
                "modeled_minus_epri_mwh",
            ],
            -200.0,
        )


if __name__ == "__main__":
    unittest.main()