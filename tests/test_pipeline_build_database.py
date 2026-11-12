import unittest

import pandas as pd
from pandas.testing import assert_frame_equal

from build_database import merge_dataset


class DatabaseMergeTests(unittest.TestCase):
    def setUp(self):
        self.sites = pd.DataFrame({
            'site_id': ['im3_00000000001', 'im3_00000000002', 'im3_00000000003'],
            'county_fips': pd.Series(['01001', '01001', None], dtype='string'),
        })

    def test_county_context_preserves_sites_and_reports_unmatched(self):
        dataset = pd.DataFrame({'county_fips': ['01001', '01003'], 'value': [12, 34]})
        result, report = merge_dataset(self.sites, dataset, 'water', 'county_fips', ['value'])
        assert_frame_equal(result[self.sites.columns], self.sites)
        self.assertEqual(result.water__value.iloc[:2].tolist(), [12, 12])
        self.assertTrue(pd.isna(result.water__value.iloc[2]))
        self.assertEqual(report['matched_sites'], 2)
        self.assertEqual(report['sites_missing_join_key'], 1)
        self.assertEqual(report['dataset_rows_without_site_match'], 1)

    def test_duplicate_and_missing_keys_rejected(self):
        for keys in [['01001', '01001'], ['01001', None], ['01001', '1001']]:
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                merge_dataset(self.sites, pd.DataFrame({'county_fips': keys, 'value': [1, 2]}),
                              'water', 'county_fips', ['value'])

    def test_site_merge_preserves_order_and_prefixes_fields(self):
        dataset = pd.DataFrame({'site_id': self.sites.site_id.iloc[::-1].tolist(), 'value': [3, 2, 1]})
        result, report = merge_dataset(self.sites, dataset, 'electricity', 'site_id', ['value'])
        self.assertEqual(result.electricity__value.tolist(), [1, 2, 3])
        self.assertEqual(report['matched_sites'], 3)
        with self.assertRaisesRegex(ValueError, 'already exist'):
            merge_dataset(result, dataset, 'electricity', 'site_id', ['value'])


if __name__ == '__main__':
    unittest.main()
