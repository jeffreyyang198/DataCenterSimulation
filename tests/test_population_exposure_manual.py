"""
Author: Diya Patidar
Date: 2026-10-26

Tests for the by-hand community exposure functions in
population_exposure_manual.py.

Every case is one I can check on paper, so a failure points at the arithmetic
rather than at something odd in the census data. Nothing here touches the
network or needs a downloaded file, which keeps these Repeatable and Fast.

Kept separate from test_population_exposure.py so the two suites don't clash.
"""

import math
import unittest

import extra_functions.population_exposure_manual as manual


class ManualExposureTests(unittest.TestCase):
    """The by-hand equations, with no geometry library involved."""

    def test_buffer_area_matches_circle_formula(self):
        self.assertAlmostEqual(manual.buffer_area(1000.0), math.pi * 1000.0 ** 2)

    def test_buffer_area_rejects_zero_radius(self):
        # A zero-radius buffer would divide by zero in coverage_fraction, so
        # it gets stopped here rather than further down.
        with self.assertRaises(ValueError):
            manual.buffer_area(0.0)

    def test_tract_share_is_a_simple_fraction(self):
        self.assertAlmostEqual(manual.tract_share(250.0, 1000.0), 0.25)

    def test_overlap_bigger_than_tract_is_refused(self):
        # This only happens when the two areas were measured in different
        # units, which is a projection bug worth failing loudly on.
        with self.assertRaises(ValueError):
            manual.tract_share(1200.0, 1000.0)

    def test_exposure_adds_up_each_tracts_share(self):
        """Three tracts, worked out by hand.

        4200 * 0.72  = 3024
        1800 * 0.1375 = 247.5
        950  * 0.0403 = 38.25  (241592.65 / 6000000)
        """
        exposure = manual.calculate_population_exposure(
            [4200.0, 1800.0, 950.0],
            [2500000.0, 8000000.0, 6000000.0],
            [1800000.0, 1100000.0, 241592.65],
        )

        self.assertAlmostEqual(exposure, 3309.75, places=2)

    def test_mismatched_lists_are_refused(self):
        # Shorter lists would zip short and pair the wrong population with
        # the wrong tract, which is the kind of bug that produces plausible
        # numbers and never gets noticed.
        with self.assertRaises(ValueError):
            manual.calculate_population_exposure([100.0, 200.0],
                                                 [1000.0],
                                                 [500.0])

    def test_full_coverage_reports_one(self):
        radius = 1000.0
        overlaps = [manual.buffer_area(radius)]

        self.assertAlmostEqual(manual.coverage_fraction(overlaps, radius), 1.0)

    def test_partial_coverage_reports_the_shortfall(self):
        radius = 1000.0
        overlaps = [manual.buffer_area(radius) / 2.0]

        self.assertAlmostEqual(manual.coverage_fraction(overlaps, radius), 0.5)


class ManualTemperatureTests(unittest.TestCase):
    """Cooling degree days and the demand multiplier."""

    def test_cooling_degree_days_ignores_cool_days(self):
        # 78 is 13 above the base, 64 is below it and adds nothing, 91 is 26
        # above. So the total is 39, not 39 minus anything for the cool day.
        self.assertAlmostEqual(
            manual.cooling_degree_days([78.0, 64.0, 91.0]), 39.0
        )

    def test_a_cold_run_of_days_totals_zero(self):
        self.assertAlmostEqual(
            manual.cooling_degree_days([40.0, 55.0, 64.9]), 0.0
        )

    def test_empty_temperature_list_is_refused(self):
        with self.assertRaises(ValueError):
            manual.cooling_degree_days([])

    def test_reference_climate_gives_multiplier_of_one(self):
        # A site matching the reference should come back unchanged, whatever
        # the sensitivity is set to.
        self.assertAlmostEqual(
            manual.adjust_for_temperature(1200.0, 1200.0, 0.15), 1.0
        )

    def test_hotter_site_needs_more_cooling(self):
        # 1 + 0.15 * (1800 - 1200) / 1200 = 1.075
        self.assertAlmostEqual(
            manual.adjust_for_temperature(1800.0, 1200.0, 0.15), 1.075
        )

    def test_cooler_site_needs_less_cooling(self):
        # 1 + 0.15 * (600 - 1200) / 1200 = 0.925
        self.assertAlmostEqual(
            manual.adjust_for_temperature(600.0, 1200.0, 0.15), 0.925
        )

    def test_multiplier_never_goes_negative(self):
        # An extreme sensitivity on a cold site would otherwise return
        # negative cooling, which isn't a thing.
        self.assertGreaterEqual(
            manual.adjust_for_temperature(0.0, 1200.0, 5.0), 0.0
        )


if __name__ == "__main__":
    unittest.main()
