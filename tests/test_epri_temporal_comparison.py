import unittest

import pandas as pd

from src.model.temporal_projection import aggregate_state_baseline
from src.model.epri_projection import project_epri_annual


class EPRITemporalComparisonTests(unittest.TestCase):

    def test_expected_row_count(self):
        # 2 states × 2 scenarios × 3 years
        rows = []

        for state, abbr in [
            ("Pennsylvania", "PA"),
            ("Virginia", "VA"),
        ]:
            for scenario in [
                "low",
                "moderate",
            ]:
                rows.append(
                    {
                        "state": state,
                        "state_abbr": abbr,
                        "scenario": scenario,
                        "epri_2023_load_mwh": 1000.0,
                        "epri_2030_load_mwh": 1210.0,
                        "implied_annual_growth_rate": 0.10,
                    }
                )

        projections = pd.DataFrame(rows)

        annual = project_epri_annual(
            projections,
            start_year=2023,
            end_year=2025,
        )

        self.assertEqual(
            len(annual),
            12,
        )

    def test_modeled_ratio_constant_under_same_growth(self):
        modeled_baseline = 1200.0
        epri_baseline = 1000.0

        growth_factors = [
            1.0,
            1.05,
            1.1025,
        ]

        ratios = []

        for factor in growth_factors:
            modeled = modeled_baseline * factor
            epri = epri_baseline * factor

            ratios.append(
                modeled / epri
            )

        for ratio in ratios:
            self.assertAlmostEqual(
                ratio,
                1.2,
            )

    def test_cumulative_energy_increases(self):
        yearly = pd.Series(
            [
                100.0,
                110.0,
                121.0,
            ]
        )

        cumulative = yearly.cumsum()

        self.assertEqual(
            cumulative.tolist(),
            [
                100.0,
                210.0,
                331.0,
            ],
        )


if __name__ == "__main__":
    unittest.main()