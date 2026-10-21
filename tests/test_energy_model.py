import unittest

import pandas as pd
from pandas.testing import assert_frame_equal

from src.model.energy_model import estimate_average_it_power, estimate_annual_facility_energy
from src.model.apply_im3_energy_model import ESTIMATE_COLUMNS, apply_energy_model, load_energy_scenario


class EnergyModelTests(unittest.TestCase):
    def test_utilization_formula(self):
        self.assertAlmostEqual(estimate_average_it_power(100, 0.8, 0.2), 84)
        self.assertEqual(estimate_average_it_power(100, 0, 0.2), 20)
        self.assertEqual(estimate_average_it_power(100, 1, 0.2), 100)
        self.assertEqual(estimate_average_it_power(0, 0.8, 0.2), 0)

    def test_annual_energy_formula(self):
        self.assertAlmostEqual(estimate_annual_facility_energy(84, 1.4), 1030176)
        self.assertEqual(estimate_annual_facility_energy(10, 1, 100), 1000)
        self.assertEqual(estimate_annual_facility_energy(0, 1.4), 0)

    def test_invalid_power_and_fractions(self):
        for bad in [-1, float('nan'), float('inf'), None, True, '100']:
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    estimate_average_it_power(bad, 0.8, 0.2)
                with self.assertRaises(ValueError):
                    estimate_annual_facility_energy(bad, 1.4)
        for bad in [-0.1, 1.1, float('nan'), float('inf')]:
            with self.assertRaises(ValueError):
                estimate_average_it_power(100, bad, 0.2)
            with self.assertRaises(ValueError):
                estimate_average_it_power(100, 0.8, bad)

    def test_pue_and_hours_validation(self):
        for bad in [0.99, -1, float('nan'), float('inf'), None, True]:
            with self.assertRaises(ValueError):
                estimate_annual_facility_energy(100, bad)
        for bad in [0, -1, float('inf'), float('nan')]:
            with self.assertRaises(ValueError):
                estimate_annual_facility_energy(100, 1.4, bad)

    def test_application_preserves_sites_and_excludes_unsupported(self):
        sites = pd.DataFrame({
            'source_site_id': ['00000000001', '00000000002', '00000000003', '00000000004'],
            'state_fips': ['01'] * 4,
            'site_type': ['building', 'building', 'campus', 'point'],
            'square_feet': [100000, float('nan'), 500000, float('nan')],
        }, index=[10, 20, 30, 40])
        before = sites.copy(deep=True)
        result = apply_energy_model(sites, {'median': 200}, 2, load_energy_scenario('ai_training'))
        assert_frame_equal(sites, before)
        assert_frame_equal(result[sites.columns], sites)
        self.assertEqual(result.energy_estimate_status.tolist(), [
            'estimated_building', 'missing_footprint', 'campus_not_supported', 'point_not_supported'])
        self.assertTrue(result.loc[[20, 30, 40], ESTIMATE_COLUMNS].isna().all().all())
        self.assertEqual(result.loc[10, 'estimated_gross_area_sqft'], 200000)
        self.assertEqual(result.loc[10, 'estimated_rated_it_power_mw'], 40)
        self.assertAlmostEqual(result.loc[10, 'estimated_average_it_power_mw'], 33.6)
        self.assertAlmostEqual(result.loc[10, 'estimated_annual_facility_energy_mwh'], 412070.4)

    def test_workloads_and_invalid_scenarios(self):
        self.assertEqual(load_energy_scenario('ai_inference')['utilization'], 0.4)
        with self.assertRaisesRegex(ValueError, 'Unknown workload scenario'):
            load_energy_scenario('unknown')
        sites = pd.DataFrame({'site_type': ['campus'], 'square_feet': [100]})
        with self.assertRaises(ValueError):
            apply_energy_model(sites, {'median': 200}, -1, load_energy_scenario('ai_training'))
        sites['site_type'] = 'building'
        sites['square_feet'] = -100
        with self.assertRaises(ValueError):
            apply_energy_model(sites, {'median': 200}, 1, load_energy_scenario('ai_training'))


if __name__ == '__main__':
    unittest.main()
