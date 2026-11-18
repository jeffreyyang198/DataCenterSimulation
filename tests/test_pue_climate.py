"""
Author: Diya Patidar
AI-assisted: yes (to be reviewed by Diya Patidar)

Tests for the k estimate and the per-site PUE in pue_climate.py.

CDD values are written into the test tables directly, so nothing here needs
NOAA or the network.
"""

import math
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from extra_functions.pue_climate import estimate_k, load_observed_pue, site_pue


def facilities(rows):
    """Build an observed table from (site_id, operator, pue, cdd) tuples."""
    return pd.DataFrame(rows, columns=["site_id", "operator", "pue", "cdd_annual"])


class EstimateKTests(unittest.TestCase):

    def test_known_slope_is_recovered(self):
        # Built so y = 0.6 x for one operator, with reference CDD 1200.
        observed = facilities([
            ("a", "Op", 1.08, 800.0),
            ("b", "Op", 1.10, 1200.0),
            ("c", "Op", 1.12, 1600.0),
        ])

        k, points, per_operator = estimate_k(observed)

        self.assertAlmostEqual(k, 0.6)
        self.assertAlmostEqual(per_operator["Op"], 0.6)
        self.assertEqual(len(points), 3)

    def test_operators_in_different_climates_give_the_same_k(self):
        """A less efficient operator sitting in a hotter region.

        Both operators follow y = 0.6 x around their own averages, but
        "Heavy" has higher PUE everywhere and its buildings are twice as hot.
        Comparing each facility with its own operator gives 0.6 for both and
        for the pool. The earlier version measured climate against one shared
        median and returned a different, wrong k here.
        """
        observed = facilities([
            ("a1", "Lean", 1.08, 800.0),
            ("a2", "Lean", 1.10, 1200.0),
            ("a3", "Lean", 1.12, 1600.0),
            ("b1", "Heavy", 1.24, 1600.0),
            ("b2", "Heavy", 1.30, 2400.0),
            ("b3", "Heavy", 1.36, 3200.0),
        ])

        k, _, per_operator = estimate_k(observed)

        self.assertAlmostEqual(per_operator["Lean"], 0.6)
        self.assertAlmostEqual(per_operator["Heavy"], 0.6)
        self.assertAlmostEqual(k, 0.6)

    def test_facility_without_weather_is_left_out(self):
        observed = facilities([
            ("a", "Op", 1.08, 800.0),
            ("b", "Op", 1.10, 1200.0),
            ("c", "Op", 1.12, 1600.0),
            ("d", "Op", 1.50, float("nan")),
        ])

        k, points, _ = estimate_k(observed)

        self.assertNotIn("d", set(points["site_id"]))
        self.assertAlmostEqual(k, 0.6)


class SitePueTests(unittest.TestCase):

    def setUp(self):
        self.sites = pd.DataFrame({
            "site_id": ["cool", "typical", "hot", "no_station"],
            "cdd_annual": [600.0, 1200.0, 1800.0, float("nan")],
        })

    def test_k_zero_leaves_every_site_at_base(self):
        result = site_pue(self.sites, {"0": 0.0})

        for value in result["pue_k_0"].iloc[:3]:
            self.assertAlmostEqual(value, 1.40)

    def test_hot_and_cool_sites_by_hand(self):
        # Reference is the median, 1200. With k = 0.5:
        # hot  M = 1 + 0.5 * 0.5 = 1.25 -> PUE = 1 + 0.40 * 1.25 = 1.50
        # cool M = 1 - 0.5 * 0.5 = 0.75 -> PUE = 1 + 0.40 * 0.75 = 1.30
        result = site_pue(self.sites, {"0.5": 0.5}).set_index("site_id")

        self.assertAlmostEqual(result.loc["hot", "pue_k_0.5"], 1.50)
        self.assertAlmostEqual(result.loc["cool", "pue_k_0.5"], 1.30)
        self.assertAlmostEqual(result.loc["typical", "pue_k_0.5"], 1.40)

    def test_site_without_station_stays_blank(self):
        # Blank, not 1.40: we don't know its climate.
        result = site_pue(self.sites, {"1": 1.0}).set_index("site_id")

        self.assertTrue(math.isnan(result.loc["no_station", "pue_k_1"]))

    def test_negative_k_is_refused(self):
        with self.assertRaises(ValueError):
            site_pue(self.sites, {"fitted": -0.2})


class LoadObservedTests(unittest.TestCase):

    def test_rows_without_coordinates_are_skipped(self):
        table = pd.DataFrame({
            "operator": ["Op", "Op"],
            "location": ["Has coords", "No coords"],
            "pue": [1.1, 1.2],
            "latitude": [40.0, None],
            "longitude": [-80.0, None],
        })

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observed.csv"
            table.to_csv(path, index=False)
            loaded = load_observed_pue(path)

        self.assertEqual(loaded["site_id"].tolist(), ["Op: Has coords"])
        self.assertEqual(str(loaded.crs), "EPSG:5070")

    def test_pue_below_one_is_refused(self):
        table = pd.DataFrame({
            "operator": ["Op"], "location": ["Bad"], "pue": [0.9],
            "latitude": [40.0], "longitude": [-80.0],
        })

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observed.csv"
            table.to_csv(path, index=False)
            with self.assertRaises(ValueError):
                load_observed_pue(path)


if __name__ == "__main__":
    unittest.main()
