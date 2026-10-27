"""
Unit tests for population_exposure.

Each test builds a synthetic tract whose correct answer can be worked out by
hand, so a failure points at the apportionment logic rather than at the real
census data. No network access and no downloaded files are required.

Run with:
    python -m unittest test_population_exposure -v

Author: Diya Patidar
AI-assisted: yes (reviewed by Diya Patidar)
"""

import math
import unittest

import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon

from population_exposure import (
    CONUS_ALBERS,
    assign_containing_tract,
    calculate_population_exposure,
    find_double_listed,
)

# A square tract 2 km on a side, centred on the origin, holding 1,000 people.
TRACT_SIDE_M = 2000.0
TRACT_AREA_M2 = TRACT_SIDE_M ** 2
TRACT_POPULATION = 1000.0

# geopandas approximates a circle with a polygon, so buffer areas come out a
# fraction under the true value. One percent is comfortably outside that
# approximation error but tight enough to catch a real mistake.
TOLERANCE = 0.01


def square_tract(geoid="99999999999", population=TRACT_POPULATION):
    """One square tract centred on the origin, in the working projection."""
    half = TRACT_SIDE_M / 2.0
    polygon = Polygon([
        (-half, -half), (half, -half), (half, half), (-half, half),
    ])
    tracts = gpd.GeoDataFrame(
        {
            "GEOID": [geoid],
            "population": [population],
            "tract_area_m2": [polygon.area],
        },
        geometry=[polygon],
        crs=CONUS_ALBERS,
    )
    return tracts


def site_at(x, y, site_id="test_site"):
    """A single site point at the given projected coordinates."""
    return gpd.GeoDataFrame(
        {"site_id": [site_id]},
        geometry=[Point(x, y)],
        crs=CONUS_ALBERS,
    )


class TestRadiusExposure(unittest.TestCase):

    def test_circle_fully_inside_tract(self):
        """A 500 m circle at the centre lies wholly inside the tract.

        Expected people = population x (circle area / tract area)
                        = 1000 x (pi x 500^2) / 4,000,000
                        ~ 196.3
        """
        tracts = square_tract()
        sites = site_at(0.0, 0.0)

        result = calculate_population_exposure(sites, tracts, radii_km=[0.5])

        expected = TRACT_POPULATION * (math.pi * 500.0 ** 2) / TRACT_AREA_M2
        self.assertAlmostEqual(
            result["pop_0.5km"].iloc[0], expected,
            delta=expected * TOLERANCE,
        )

    def test_circle_swallows_whole_tract(self):
        """A circle far larger than the tract captures everyone in it."""
        tracts = square_tract()
        sites = site_at(0.0, 0.0)

        result = calculate_population_exposure(sites, tracts, radii_km=[10.0])

        self.assertAlmostEqual(
            result["pop_10km"].iloc[0], TRACT_POPULATION,
            delta=TRACT_POPULATION * TOLERANCE,
        )

    def test_site_on_corner_gets_a_quarter(self):
        """A circle centred on a tract corner has a quarter of its area inside.

        This is the case the containing-tract method handles badly, so it is
        worth pinning down.
        """
        half = TRACT_SIDE_M / 2.0
        tracts = square_tract()
        sites = site_at(half, half)

        result = calculate_population_exposure(sites, tracts, radii_km=[0.5])

        quarter_circle_area = (math.pi * 500.0 ** 2) / 4.0
        expected = TRACT_POPULATION * quarter_circle_area / TRACT_AREA_M2
        self.assertAlmostEqual(
            result["pop_0.5km"].iloc[0], expected,
            delta=expected * TOLERANCE,
        )

    def test_site_far_away_sees_nobody(self):
        """A site with no tract nearby returns zero, not an error or a gap."""
        tracts = square_tract()
        sites = site_at(500_000.0, 500_000.0)

        result = calculate_population_exposure(sites, tracts, radii_km=[1.0])

        self.assertEqual(result["pop_1km"].iloc[0], 0.0)

    def test_incomplete_coverage_is_flagged(self):
        """A circle extending past the tract edge is flagged as an undercount.

        Without this flag a coastal or border site would silently report a
        number that looks precise but is missing whoever lives outside the
        loaded tracts.
        """
        tracts = square_tract()
        sites = site_at(0.0, 0.0)

        result = calculate_population_exposure(sites, tracts, radii_km=[5.0])

        self.assertTrue(bool(result["incomplete_pop_5km"].iloc[0]))

    def test_population_splits_across_two_tracts(self):
        """Two tracts side by side each contribute their own share."""
        half = TRACT_SIDE_M / 2.0
        left = Polygon([(-half, -half), (0, -half), (0, half), (-half, half)])
        right = Polygon([(0, -half), (half, -half), (half, half), (0, half)])

        tracts = gpd.GeoDataFrame(
            {
                "GEOID": ["11111111111", "22222222222"],
                "population": [800.0, 200.0],
                "tract_area_m2": [left.area, right.area],
            },
            geometry=[left, right],
            crs=CONUS_ALBERS,
        )
        sites = site_at(0.0, 0.0)

        result = calculate_population_exposure(sites, tracts, radii_km=[0.5])

        # The circle straddles the shared edge, taking half its area from each
        # tract. Each half-circle is (pi x 500^2)/2 out of a 2,000,000 m2 tract.
        half_circle = (math.pi * 500.0 ** 2) / 2.0
        expected = (800.0 * half_circle / left.area
                    + 200.0 * half_circle / right.area)
        self.assertAlmostEqual(
            result["pop_0.5km"].iloc[0], expected,
            delta=expected * TOLERANCE,
        )
        self.assertEqual(result["tracts_within_0.5km"].iloc[0], 2)


class TestContainingTract(unittest.TestCase):

    def test_site_inside_tract_gets_full_population(self):
        """The simple method reports the whole tract, however near the edge."""
        tracts = square_tract()
        sites = site_at(0.0, 0.0)

        result = assign_containing_tract(sites, tracts)

        self.assertEqual(result["tract_population"].iloc[0], TRACT_POPULATION)
        self.assertEqual(result["tract_geoid"].iloc[0], "99999999999")

    def test_site_outside_every_tract_is_blank(self):
        """A site with no containing tract yields a missing value, not zero."""
        tracts = square_tract()
        sites = site_at(500_000.0, 500_000.0)

        result = assign_containing_tract(sites, tracts)

        self.assertTrue(pd.isna(result["tract_geoid"].iloc[0]))


def layer(ids, shapes):
    """A minimal IM3-style layer: an id column and geometry."""
    return gpd.GeoDataFrame({"id": ids}, geometry=shapes, crs=CONUS_ALBERS)


def box(x0, y0, x1, y1):
    """An axis-aligned rectangle."""
    return Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


class TestDoubleListing(unittest.TestCase):

    def test_campuses_and_points_resolve_to_buildings(self):
        """One campus holding a building, one empty campus, three points.

        Campus A contains building B, so A is the repeat. Campus C has no
        building inside and is the only record of its facility. Point P1
        sits inside B, P2 inside A but outside B, and P3 out on its own.
        """
        buildings = layer(["B"], [box(10, 10, 20, 20)])
        campuses = layer(["A", "C"], [box(0, 0, 100, 100),
                                      box(500, 500, 600, 600)])
        points = layer(["P1", "P2", "P3"], [Point(15, 15), Point(80, 80),
                                            Point(1000, 1000)])

        repeats = find_double_listed(buildings, campuses, points)

        self.assertEqual(repeats, {"A", "P1", "P2"})


if __name__ == "__main__":
    unittest.main()
