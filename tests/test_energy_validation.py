import unittest

import pandas as pd

from src.validation.validate_energy_outputs import (
    ANNUAL, AREA, AVERAGE, RATED, add_plausibility_flags, describe_numeric,
    structural_counts, top_outliers, validate_structure,
)


class EnergyValidationTests(unittest.TestCase):
    def sites(self, count: int = 101) -> pd.DataFrame:
        return pd.DataFrame({
            'site_id': [f'im3_{number:011d}' for number in range(count)],
            'site_type': 'building', 'energy_estimate_status': 'estimated_building',
            'latitude': 40, 'longitude': -75, 'square_feet': range(1, count + 1),
            AREA: range(1, count + 1), RATED: range(1, count + 1),
            AVERAGE: 1, ANNUAL: range(1, count + 1), 'floor_area_multiplier': 1,
            'power_density_w_sqft': 100, 'utilization': .8, 'idle_fraction': .2, 'pue': 1.4,
        })

    def test_statistics(self):
        summary = describe_numeric(pd.Series([1, 2, 3, 4, 5, None, 'bad', float('inf')]))
        self.assertEqual(summary['count'], 5)
        self.assertEqual(summary['min'], 1)
        self.assertEqual(summary['q25'], 2)
        self.assertEqual(summary['median'], 3)
        self.assertEqual(summary['q75'], 4)
        self.assertEqual(summary['max'], 5)
        self.assertEqual(summary['mean'], 3)
        self.assertAlmostEqual(summary['q05'], 1.2)
        self.assertAlmostEqual(summary['q95'], 4.8)
        self.assertAlmostEqual(summary['standard_deviation'], 2.5 ** .5)

    def test_duplicate_detection(self):
        sites = self.sites(2)
        sites.loc[1, 'site_id'] = sites.loc[0, 'site_id']
        self.assertEqual(structural_counts(sites)['duplicated_site_id_values'], 1)
        with self.assertRaisesRegex(ValueError, 'duplicate site_id'):
            validate_structure(sites)

    def test_invalid_ranges(self):
        for column, value in [('utilization', 1.1), ('utilization', -.1),
                              ('idle_fraction', 1.1), ('pue', .9),
                              ('square_feet', -1), (AREA, -1), (RATED, -1),
                              (AVERAGE, -1), (ANNUAL, -1)]:
            with self.subTest(column=column, value=value):
                sites = self.sites(1)
                sites[column] = value
                with self.assertRaisesRegex(ValueError, column):
                    validate_structure(sites)

    def test_missing_coordinates_and_bad_numeric(self):
        for column, value in [('latitude', None), ('longitude', None),
                              (RATED, 'bad'), (ANNUAL, float('inf'))]:
            sites = self.sites(1)
            sites[column] = value
            with self.assertRaises(ValueError):
                validate_structure(sites)

    def test_unsupported_null_estimates_allowed(self):
        sites = self.sites(2)
        sites['site_type'] = ['campus', 'point']
        sites['energy_estimate_status'] = ['campus_not_supported', 'point_not_supported']
        sites[[AREA, RATED, AVERAGE, ANNUAL]] = float('nan')
        sites['square_feet'] = [100, float('nan')]
        validated = validate_structure(sites)
        flagged, thresholds = add_plausibility_flags(validated)
        self.assertEqual(flagged.energy_validation_flag.tolist(), ['unsupported_site_type'] * 2)
        self.assertTrue(pd.isna(thresholds['q99_rated_it_power_mw']))
        sites[RATED] = 10
        with self.assertRaisesRegex(ValueError, 'unsupported site type'):
            validate_structure(sites)

    def test_q99_flags_and_multiple_conditions(self):
        sites = validate_structure(self.sites())
        flagged, thresholds = add_plausibility_flags(sites)
        self.assertEqual(thresholds['q99_rated_it_power_mw'], 100)
        self.assertEqual(thresholds['q99_building_square_feet'], 100)
        self.assertEqual(flagged.iloc[-2].energy_validation_flag, 'ok')
        self.assertEqual(flagged.iloc[-1].energy_validation_flag,
                         'very_large_power_estimate;very_large_footprint')
        self.assertEqual(len(flagged), len(sites))

    def test_missing_building_inputs_and_outputs(self):
        sites = self.sites(2)
        sites['square_feet'] = [None, 10]
        sites[ANNUAL] = [10, None]
        flagged, _ = add_plausibility_flags(validate_structure(sites))
        self.assertTrue(flagged.energy_validation_flag.str.contains('missing_required_input').all())
        self.assertEqual(structural_counts(sites)['missing_building_estimates'], 1)
        sites = self.sites(1).drop(columns='floor_area_multiplier')
        flagged, _ = add_plausibility_flags(validate_structure(sites))
        self.assertEqual(flagged.iloc[0].energy_validation_flag, 'missing_required_input')

    def test_top_lists(self):
        sites = validate_structure(self.sites(12))
        report = top_outliers(sites)
        self.assertEqual(len(report), 30)
        for _, group in report.groupby('ranking_metric'):
            self.assertEqual(group.iloc[0].site_id, 'im3_00000000011')
            self.assertEqual(group['rank'].tolist(), list(range(1, 11)))

    def test_empty_statistics(self):
        stats = describe_numeric(pd.Series([], dtype=float))
        self.assertEqual(stats['count'], 0)
        self.assertTrue(pd.isna(stats['median']))


if __name__ == '__main__':
    unittest.main()
