import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from src.model.apply_egrid_emissions import assign_subregions, emissions_tonnes


class EgridTests(unittest.TestCase):
    def test_pounds_to_metric_tonnes_and_missing_energy(self):
        values = emissions_tonnes(pd.Series([1000., 0., float('nan')]), 1000.)
        self.assertAlmostEqual(values[0], 453.59237)
        self.assertEqual(values[1], 0.)
        self.assertTrue(pd.isna(values[2]))

    def test_shared_and_unmatched_sites_not_assigned(self):
        sites = pd.DataFrame({'site_id': ['inside', 'shared', 'outside', 'boundary'], 'longitude': [1., 2., 10., 0.], 'latitude': [1., 2., 10., 1.]})
        primary = gpd.GeoDataFrame({'code': ['A', 'B']}, geometry=[box(0, 0, 3, 3), box(-2, 0, 0, 3)], crs=4326)
        shared = gpd.GeoDataFrame(geometry=[box(1.5, 1.5, 2.5, 2.5)], crs=4326)
        result = assign_subregions(sites, primary, shared, 'code').set_index('site_id')
        self.assertEqual(result.loc['inside', 'egrid_subregion'], 'A')
        self.assertEqual(result.loc['outside', 'egrid_mapping_status'], 'unmatched')
        for site in ['shared', 'boundary']:
            self.assertEqual(result.loc[site, 'egrid_mapping_status'], 'utility_verification_required')
            self.assertTrue(pd.isna(result.loc[site, 'egrid_subregion']))

    def test_duplicate_sites_rejected(self):
        sites = pd.DataFrame({'site_id': ['a', 'a'], 'longitude': [1., 1.], 'latitude': [1., 1.]})
        with self.assertRaises(ValueError):
            assign_subregions(sites, None, None, 'code')
