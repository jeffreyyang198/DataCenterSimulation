import tempfile
import unittest
from pathlib import Path

import pandas as pd
from pandas.testing import assert_frame_equal
from src.clean.clean_im3 import clean_im3, load_im3, save_im3
from src.clean.site_schema import MASTER_SITE_SCHEMA


class CleanIM3Tests(unittest.TestCase):
    def row(self, **changes):
        row = dict(id='00002744301', state='New Jersey', state_abb=' nj ',
                   state_id='34', county='Middlesex County', county_id='023',
                   operator='  Google   LLC ', ref='001', name=' Test ',
                   sqft='100.5', lon='-74.4', lat='40.5', type=' Building ')
        return row | changes

    def clean(self, *rows):
        return clean_im3(pd.DataFrame(rows))

    def test_identifiers_and_normalization(self):
        df = self.clean(self.row())
        self.assertEqual(df.loc[0, 'site_id'], 'im3_00002744301')
        self.assertEqual(df.loc[0, 'county_fips'], '34023')
        self.assertEqual(df.loc[0, 'operator'], 'Google')
        self.assertEqual(df.loc[0, 'operator_raw'], 'Google LLC')
        self.assertEqual(df.loc[0, 'site_type'], 'building')
        self.assertEqual(df.loc[0, 'reference'], '001')
        self.assertEqual(df.loc[0, 'square_feet'], 100.5)

    def test_numeric_input_and_full_fips(self):
        df = self.clean(self.row(id=2744301.0, state_id=34.0, county_id=34023.0))
        self.assertEqual(df.loc[0, 'source_site_id'], '00002744301')
        self.assertEqual(df.loc[0, 'county_fips'], '34023')

    def test_missing_optional_fields(self):
        df = self.clean(self.row(operator='', sqft='', type='point'))
        self.assertTrue(pd.isna(df.loc[0, 'operator']))
        self.assertTrue(pd.isna(df.loc[0, 'square_feet']))
        self.assertIn('missing_square_feet', df.loc[0, 'quality_flags'])

    def test_invalid_values_fail(self):
        for changes in [dict(id=''), dict(id='1.2'), dict(lat='91'), dict(lon='inf'),
                        dict(lat=''), dict(sqft='-1'), dict(sqft='inf'), dict(sqft='bad'),
                        dict(county_id='06023'), dict(type='unknown')]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.clean(self.row(**changes))

    def test_duplicate_counties_preserved_for_review(self):
        a, b = self.row(), self.row(county='Other County', county_id='025')
        df = self.clean(a, b)
        self.assertEqual(len(df), 1)
        self.assertTrue(pd.isna(df.loc[0, 'county_fips']))
        self.assertEqual(len(df.attrs['county_review']), 2)
        self.assertEqual(df.loc[0, 'quality_flags'], 'ambiguous_county')
        assert_frame_equal(df, self.clean(b, a))

    def test_exact_duplicates_and_conflicts(self):
        self.assertEqual(len(self.clean(self.row(), self.row())), 1)
        with self.assertRaises(ValueError):
            self.clean(self.row(), self.row(lon='-75'))

    def test_csv_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / 'raw.csv'
            pd.DataFrame([self.row()]).to_csv(raw, index=False)
            df = clean_im3(load_im3(raw))
            target = Path(tmp) / 'master.csv'
            save_im3(df, target)
            assert_frame_equal(df, pd.read_csv(target, dtype=MASTER_SITE_SCHEMA))
            self.assertTrue(target.with_name('im3_county_review.csv').exists())

    def test_atlas_integration(self):
        raw = load_im3()
        df = clean_im3(raw)
        self.assertEqual(len(df), raw.id.nunique())
        self.assertEqual(int(df.county_fips.isna().sum()), 5)
        self.assertEqual(len(df.attrs['county_review']), 10)
        self.assertEqual(int(df.square_feet.isna().sum()), 105)


if __name__ == '__main__':
    unittest.main()
