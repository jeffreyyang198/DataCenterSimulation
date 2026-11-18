import tempfile
import unittest
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal

from src.model.compare_energy_scenarios import compare_energy_scenarios
from src.model.apply_im3_energy_model import ESTIMATE_COLUMNS, apply_energy_model


class ScenarioComparisonTests(unittest.TestCase):
    def test_climate_pue_changes_facility_energy_once_and_flags_fallback(self):
        sites = pd.DataFrame({
            'site_id': ['001', '002', '003'],
            'site_type': ['building', 'building', 'building'],
            'square_feet': [100000, 100000, 100000],
        }, index=[3, 7, 9])
        climate = pd.DataFrame({
            'site_id': ['002', '001'],
            'pue_k_fitted': [float('nan'), 1.5],
        })
        args = (sites, {'q25': 100, 'median': 200, 'q75': 300}, 1,
                {'utilization': 0.4, 'idle_fraction': 0.2, 'pue': 1.4})
        baseline = apply_energy_model(*args)
        adjusted = apply_energy_model(*args, climate_pue=climate)
        self.assertEqual(adjusted.index.tolist(), [3, 7, 9])
        self.assertEqual(adjusted.pue.tolist(), [1.5, 1.4, 1.4])
        self.assertEqual(adjusted.pue_source.tolist(),
                         ['climate_fitted', 'scenario_fallback', 'scenario_fallback'])
        self.assertEqual(adjusted.estimated_average_it_power_mw.tolist(),
                         baseline.estimated_average_it_power_mw.tolist())
        energy = 'estimated_annual_facility_energy_mwh'
        self.assertAlmostEqual(adjusted.loc[3, energy], baseline.loc[3, energy] * 1.5 / 1.4)
        self.assertEqual(adjusted.loc[[7, 9], energy].tolist(), baseline.loc[[7, 9], energy].tolist())

    def test_saved_scenarios_preserve_ids_exclusions_and_expected_energy(self):
        sites = pd.DataFrame({
            'site_id': ['001', '002', '003', '004'],
            'site_type': ['building', 'building', 'campus', 'point'],
            'square_feet': [100000, float('nan'), 900000, float('nan')],
        })
        before = sites.copy(deep=True)
        with tempfile.TemporaryDirectory() as directory:
            comparison = compare_energy_scenarios(
                sites, {'q25': 100, 'median': 200, 'q75': 300}, 2, directory,
            )
            self.assertEqual(len(list(Path(directory).glob('*.csv'))), 7)
            self.assertEqual(len(comparison), 6)
            self.assertTrue((comparison.estimated_building_count == 1).all())
            for row in comparison.itertuples(index=False):
                saved = pd.read_csv(Path(directory) / row.output_file, dtype={'site_id': 'string'})
                self.assertEqual(saved.site_id.tolist(), ['001', '002', '003', '004'])
                self.assertTrue(saved.loc[1:, ESTIMATE_COLUMNS].isna().all().all())
                expected_rated = 200000 * row.power_density_w_sqft / 1e6
                expected_energy = expected_rated * (0.2 + row.utilization * 0.8) * 1.4 * 8760
                self.assertAlmostEqual(saved.loc[0, 'estimated_annual_facility_energy_mwh'], expected_energy)
                self.assertAlmostEqual(row.median_estimated_annual_facility_energy_mwh, expected_energy)
            assert_frame_equal(sites, before)

    def test_unsupported_only_summary_is_unknown_not_zero(self):
        sites = pd.DataFrame({'site_type': ['point'], 'square_feet': [float('nan')]})
        with tempfile.TemporaryDirectory() as directory:
            comparison = compare_energy_scenarios(sites, {'q25': 100, 'median': 200, 'q75': 300}, 1, directory)
            self.assertTrue(comparison.median_estimated_annual_facility_energy_mwh.isna().all())
            self.assertTrue((comparison.point_not_supported_count == 1).all())

    def test_invalid_scenario_does_not_write_partial_outputs(self):
        sites = pd.DataFrame({'site_type': ['building'], 'square_feet': [100000]})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                compare_energy_scenarios(sites, {'q25': 100, 'median': 200, 'q75': -1}, 1, directory)
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
