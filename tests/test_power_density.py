import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.model.power_density import (
    CALIBRATION_FILE, assign_power_density_scenario, calculate_observed_power_density,
    estimate_rated_power_from_im3, load_power_density_calibration, summarize_power_density,
)


class PowerDensityTests(unittest.TestCase):
    def test_observed_density(self):
        self.assertAlmostEqual(calculate_observed_power_density(72, 540000), 133.3333333333)

    def test_summary_and_scenario_mapping(self):
        summary = summarize_power_density(pd.DataFrame({'w_per_sqft': [100, 200, 300, 400]}))
        self.assertEqual(summary, {'count': 4, 'minimum': 100, 'q25': 175, 'median': 250,
                                   'q75': 325, 'maximum': 400, 'mean': 250})
        for scenario, expected in [('low', 175), ('reference', 250), ('high', 325)]:
            self.assertEqual(assign_power_density_scenario(summary, scenario), expected)
        with self.assertRaisesRegex(ValueError, 'Unknown density scenario'):
            assign_power_density_scenario(summary, 'extreme')

    def test_invalid_inputs(self):
        for bad in [-1, 0, float('nan'), float('inf'), None, '100', True]:
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    calculate_observed_power_density(bad, 100)
                with self.assertRaises(ValueError):
                    calculate_observed_power_density(100, bad)
                for index in range(3):
                    inputs = [1000, 1, 200]
                    inputs[index] = bad
                    with self.assertRaises(ValueError):
                        estimate_rated_power_from_im3(*inputs, 'building')

    def test_supported_site_types(self):
        self.assertAlmostEqual(estimate_rated_power_from_im3(100000, 2, 200, 'building'), 40)
        for site_type in ['campus', 'point']:
            self.assertIsNone(estimate_rated_power_from_im3(float('nan'), 1, 200, site_type))
        with self.assertRaises(ValueError):
            estimate_rated_power_from_im3(1000, 1, 200, 'unknown')

    def test_calibration_recalculation_and_tolerance(self):
        df = load_power_density_calibration()
        self.assertEqual(len(df), 9)
        self.assertAlmostEqual(df.iloc[0].w_per_sqft, 72_000_000 / 540000)
        self.assertNotEqual(df.iloc[0].w_per_sqft, df.iloc[0].stored_w_per_sqft)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.csv'
            raw = pd.read_csv(CALIBRATION_FILE)
            raw.loc[0, 'w_per_sqft'] += 1
            raw.to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'EdgeCore Silicon Valley'):
                load_power_density_calibration(path)

    def test_empty_or_invalid_summary_rejected(self):
        for values in [[], [100, float('nan')], [100, -1]]:
            with self.assertRaises(ValueError):
                summarize_power_density(pd.DataFrame({'w_per_sqft': values}))


if __name__ == '__main__':
    unittest.main()
