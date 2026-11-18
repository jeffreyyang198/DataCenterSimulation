"""Focused watershed enrichment tests, compatible with pytest and unittest."""

import unittest
from pathlib import Path

import geopandas as gpd
import pandas as pd
from pandas.testing import assert_frame_equal
from shapely.geometry import box

from src.geo.enrich_huc8 import (assign_huc8_to_sites, load_huc8_boundaries,
                                 merge_table3, normalize_huc8, validate_huc8_merge)


class HUC8Tests(unittest.TestCase):
    def boundaries(self):
        return gpd.GeoDataFrame({'HUC8': ['1010001']}, geometry=[box(0, 0, 2, 2)],
                                crs='EPSG:4326')

    def sites(self):
        return pd.DataFrame({'site_id': ['a', 'b', 'c', 'd'],
                             'longitude': ['1', '3', None, 'inf'],
                             'latitude': ['1', '3', '0', '0']}, index=[9, 9, 5, 2])

    def table(self):
        return pd.DataFrame({'HUC8': ['01010001'], 'WF_1MW_DC': [8.091],
                             'WSF_1MW_DC': [1.594], 'CF_1MW_DC': [0.254]})

    def test_normalization(self):
        result = normalize_huc8(pd.Series([1010001, '05030101', None, '', float('nan'), ' 1010001.0 ']))
        self.assertEqual(result.iloc[:2].tolist(), ['01010001', '05030101'])
        self.assertTrue(result.iloc[2:5].isna().all())
        self.assertEqual(result.iloc[5], '01010001')
        for value in ['123456789', 'abc', '12.3']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_huc8(pd.Series([value]))

    def test_spatial_merge_preservation_and_crs(self):
        sites = self.sites()
        assigned = assign_huc8_to_sites(sites, self.boundaries().to_crs(3857))
        self.assertEqual(assigned.huc8.iloc[0], '01010001')
        self.assertEqual(assigned.huc8_status.tolist(),
                         ['assigned', 'no_polygon_match', 'invalid_coordinates', 'invalid_coordinates'])
        enriched = merge_table3(assigned, self.table())
        assert_frame_equal(sites, enriched[sites.columns])
        self.assertEqual(enriched.iloc[0][['WF_1MW_DC', 'WSF_1MW_DC', 'CF_1MW_DC']].tolist(),
                         [8.091, 1.594, 0.254])
        self.assertTrue(enriched.iloc[1:][['WF_1MW_DC', 'WSF_1MW_DC', 'CF_1MW_DC']].isna().all().all())
        report = validate_huc8_merge(sites, enriched, self.table())
        self.assertEqual(report['rows_matched_table3'], 1)
        self.assertEqual(report['rows_without_huc8'], 3)

    def test_unmatched_and_missing_keys(self):
        sites = pd.DataFrame({'huc8': ['05030101', None, '01010001']})
        table = pd.concat([self.table(), self.table().assign(HUC8=None)])
        result = merge_table3(sites, table)
        self.assertEqual(len(result), 3)
        self.assertEqual(result.table3_match.tolist(), [False, False, True])
        self.assertTrue(result.WF_1MW_DC.iloc[:2].isna().all())

    def test_duplicate_table3_keys_rejected_after_normalization(self):
        table = pd.concat([self.table(), self.table().assign(HUC8='1010001.0')])
        with self.assertRaisesRegex(ValueError, 'Duplicate HUC8'):
            merge_table3(pd.DataFrame({'huc8': ['01010001']}), table)

    def test_ambiguous_boundary_and_same_code_parts(self):
        sites = pd.DataFrame({'longitude': [2], 'latitude': [1]})
        boundaries = gpd.GeoDataFrame({'HUC8': ['01010001', '01010002']},
                                      geometry=[box(0, 0, 2, 2), box(2, 0, 4, 2)], crs=4326)
        result = assign_huc8_to_sites(sites, boundaries)
        self.assertTrue(result.huc8.isna().all())
        self.assertEqual(result.huc8_status.iloc[0], 'ambiguous_watershed')
        self.assertEqual(result.huc8_candidates.iloc[0], '01010001;01010002')
        boundaries['HUC8'] = '01010001'
        self.assertEqual(assign_huc8_to_sites(sites, boundaries).huc8.iloc[0], '01010001')

    def test_empty_and_invalid_sites(self):
        for sites in [self.sites().iloc[:0], self.sites().iloc[2:]]:
            result = merge_table3(assign_huc8_to_sites(sites, self.boundaries()), self.table())
            assert_frame_equal(sites, result[sites.columns])

    def test_missing_dataset_and_crs(self):
        with self.assertRaisesRegex(FileNotFoundError, 'USGS WBD HUC8'):
            load_huc8_boundaries(Path('/nonexistent/wbd.shp'))
        boundaries = self.boundaries().set_crs(None, allow_override=True)
        with self.assertRaisesRegex(ValueError, 'declared CRS'):
            assign_huc8_to_sites(self.sites(), boundaries)


if __name__ == '__main__':
    unittest.main()
