"""
Claude used for formatting the code style and comments
Author: Diya Patidar
Date: 2026-10-26

Manual implementation of the community exposure functions.

This file is the by-hand version: plain Python and math only, no pandas or
geopandas, so every equation is visible. The pipeline version in
population_exposure.py does the same arithmetic on real census geometry.
"""

import math


# calculate_population_exposure()

# E = estimated number of people living inside a buffer around a data center
# P_i = ACS population of census tract i
# A_i = total area of census tract i, in square metres
# O_i = area of the overlap between tract i and the buffer, in square metres
# O_i / A_i = the share of tract i that falls inside the buffer
# Census tracts do not line up with facility locations, so a buffer almost
# always cuts several tracts partway. Areal apportionment takes that share of
# each tract's population instead of counting the whole tract or none of it.
# This assumes people are spread evenly inside a tract, which they are not.
# It is a documented approximation, not a measurement.


def buffer_area(radius_m: float) -> float:
    """
    Compute the area of a circular buffer around a data center.

    Uses the area of a circle:
        A = pi * r^2

    Args:
        radius_m (float): Buffer radius in metres, must be positive.
    Returns:
        float: Buffer area in square metres.
    """
    if not math.isfinite(radius_m) or radius_m <= 0:
        raise ValueError("Buffer radius has to be a positive number")

    return math.pi * radius_m ** 2


def tract_share(overlap_area_m2: float, tract_area_m2: float) -> float:
    """
    Compute the fraction of one census tract that falls inside the buffer.

    Args:
        overlap_area_m2 (float): Area shared by the tract and the buffer.
        tract_area_m2 (float): Total area of the tract.
    Returns:
        float: A fraction between 0 and 1.
    """
    if not math.isfinite(tract_area_m2) or tract_area_m2 <= 0:
        raise ValueError("Tract area has to be a positive number")

    if not math.isfinite(overlap_area_m2) or overlap_area_m2 < 0:
        raise ValueError("Overlap area can't be negative")

    # An overlap bigger than the tract itself means the two areas were measured
    # differently, usually because one of them was computed in degrees instead
    # of metres. I raise here rather than clipping to 1, because clipping would
    # hide a projection mistake that affects every other site too.
    if overlap_area_m2 > tract_area_m2:
        raise ValueError("Overlap can't be larger than the tract it sits in")

    return overlap_area_m2 / tract_area_m2


def calculate_population_exposure(tract_populations: list[float],
                                  tract_areas_m2: list[float],
                                  overlap_areas_m2: list[float]) -> float:
    """
    Estimate how many people live inside a buffer, by areal apportionment.

    For every tract the buffer touches, take the share of that tract inside
    the buffer and count that share of its population:
        E = sum(P_i * O_i / A_i)

    Args:
        tract_populations (list[float]): ACS population of each tract touched.
        tract_areas_m2 (list[float]): Total area of each of those tracts.
        overlap_areas_m2 (list[float]): Area each tract shares with the buffer.
    Returns:
        float: Estimated population inside the buffer.
    """
    # The three lists are parallel, so position i has to describe the same
    # tract in all of them. Mismatched lengths would silently pair the wrong
    # population with the wrong area, so I stop instead of zipping them short.
    if not (len(tract_populations) == len(tract_areas_m2) == len(overlap_areas_m2)):
        raise ValueError("Population, area and overlap lists must be the same length")

    exposure = 0.0

    for population, tract_area, overlap_area in zip(tract_populations,
                                                    tract_areas_m2,
                                                    overlap_areas_m2):
        if not math.isfinite(population) or population < 0:
            raise ValueError("Tract population can't be negative")

        share = tract_share(overlap_area, tract_area)
        exposure += (population * share)

    return exposure


def coverage_fraction(overlap_areas_m2: list[float], radius_m: float) -> float:
    """
    Compute how much of the buffer actually had census tracts underneath it.

    A buffer can stick out past the edge of the data: over the ocean, across a
    state border whose tracts were never downloaded, or outside the country.
    Those gaps return zero people, which looks identical to a genuinely empty
    area unless the coverage is reported alongside it.

    Args:
        overlap_areas_m2 (list[float]): Overlap area for each tract touched.
        radius_m (float): Buffer radius in metres.
    Returns:
        float: Fraction of the buffer covered by tracts, between 0 and 1.
    """
    covered = sum(overlap_areas_m2)
    circle = buffer_area(radius_m)

    # Floating point can push the sum a hair over the circle area when the
    # tracts tile it completely, so I cap the reported fraction at 1.
    return min(covered / circle, 1.0)


# adjust_for_temperature()

# CDD = cooling degree days for one year at a site
# T_i = mean outdoor temperature on day i, in degrees Fahrenheit
# T_base = 65 F, the convention for when buildings start needing cooling
# M = multiplier applied to a site's baseline cooling demand
# CDD_ref = cooling degree days at a reference site
# k = sensitivity of cooling demand to climate
# The energy model uses one fixed PUE of 1.40 for every facility in the
# country. The same building needs more cooling in Phoenix than in Seattle,
# so this multiplier makes that fixed assumption depend on location.
# k is a scenario assumption we choose, not a value fitted from data.

COOLING_BASE_TEMPERATURE_F = 65.0


def cooling_degree_days(daily_mean_temps_f: list[float],
                        base_temp_f: float = COOLING_BASE_TEMPERATURE_F) -> float:
    """
    Sum the cooling degree days over a run of daily temperatures.

    Each day contributes however many degrees it sat above the base:
        CDD = sum(max(0, T_i - T_base))

    Args:
        daily_mean_temps_f (list[float]): Daily mean temperatures, in F.
        base_temp_f (float): Temperature above which cooling is needed.
    Returns:
        float: Total cooling degree days across the period.
    """
    if len(daily_mean_temps_f) == 0:
        raise ValueError("Need at least one day of temperature to total up")

    total = 0.0

    for temperature in daily_mean_temps_f:
        if not math.isfinite(temperature):
            raise ValueError("Daily temperature has to be a real number")

        # A day below the base needs no cooling, so it adds zero rather than a
        # negative. Without the max() a cold winter would cancel out summer and
        # a site with hot summers and cold winters would look mild.
        total += max(0.0, temperature - base_temp_f)

    return total


def adjust_for_temperature(site_cdd: float,
                           reference_cdd: float,
                           sensitivity: float) -> float:
    """
    Turn a site's cooling degree days into a cooling demand multiplier.

    Scales demand by how far the site sits from a reference climate:
        M = 1 + k * (CDD_site - CDD_ref) / CDD_ref

    A site hotter than the reference returns a multiplier above 1, a cooler
    site returns one below 1, and a site matching the reference returns
    exactly 1.

    Args:
        site_cdd (float): Cooling degree days at this site.
        reference_cdd (float): Cooling degree days at the reference site.
        sensitivity (float): How strongly demand responds, a scenario choice.
    Returns:
        float: Multiplier to apply to baseline cooling demand.
    """
    if not math.isfinite(site_cdd) or site_cdd < 0:
        raise ValueError("Cooling degree days can't be negative")

    if not math.isfinite(reference_cdd) or reference_cdd <= 0:
        raise ValueError("Reference cooling degree days has to be positive")

    if not math.isfinite(sensitivity) or sensitivity < 0:
        raise ValueError("Sensitivity can't be negative")

    relative_climate = (site_cdd - reference_cdd) / reference_cdd

    multiplier = 1 + (sensitivity * relative_climate)

    # A very cold site with a large sensitivity could drive this below zero,
    # which would mean negative cooling. I floor it at zero so the number stays
    # physically possible, and note that no US site gets anywhere near it.
    return max(0.0, multiplier)


# fit_slope() and the two helpers before it

# k used to be a number I picked. These functions estimate it from real data
# centers that publish their PUE, so it comes from evidence instead.
# For each facility i:
#   y_i = how far its PUE overhead sits above or below its operator's average
#       = (PUE_i - 1) / mean(PUE - 1) - 1
#   x_i = how far its climate sits above or below its operator's average
#       = (CDD_i - CDD_ref) / CDD_ref, with CDD_ref the operator's mean CDD
# adjust_for_temperature() says M = 1 + k * x. If an operator's average
# overhead is roughly its overhead at its average climate, y is roughly
# M - 1, so y is roughly k * x and the slope of y against x estimates k.
# That "roughly" is an assumption, not something the data proves.
# Comparing inside each operator keeps a company that is efficient
# everywhere, or one with most buildings in hot places, from looking like
# a climate effect.


def overhead_differences(pue_values: list[float]) -> list[float]:
    """
    Express each facility's overhead relative to the group's average overhead.

    Overhead is the part of PUE above 1, mostly cooling:
        y_i = (PUE_i - 1) / mean(PUE - 1) - 1

    A facility at the group average returns 0, one with 10% more overhead
    than average returns 0.1.

    Args:
        pue_values (list[float]): PUE of each facility from one operator.
    Returns:
        list[float]: Relative overhead of each facility.
    """
    if len(pue_values) < 2:
        raise ValueError("Need at least two facilities to compare overheads")

    overheads = []

    for pue in pue_values:
        # PUE is total power over IT power, so it can't be below 1.
        if not math.isfinite(pue) or pue < 1:
            raise ValueError("PUE has to be a number of at least 1")

        overheads.append(pue - 1)

    mean_overhead = sum(overheads) / len(overheads)

    # Every facility at exactly PUE 1.0 would leave nothing to compare against.
    if mean_overhead <= 0:
        raise ValueError("Average overhead is zero, so nothing to compare")

    return [(overhead / mean_overhead) - 1 for overhead in overheads]


def climate_differences(cdd_values: list[float],
                        reference_cdd: float) -> list[float]:
    """
    Express each facility's climate relative to the reference climate.

        x_i = (CDD_i - CDD_ref) / CDD_ref

    This is the same ratio adjust_for_temperature() multiplies by k.

    Args:
        cdd_values (list[float]): Cooling degree days at each facility.
        reference_cdd (float): Cooling degree days of the reference climate.
    Returns:
        list[float]: Relative climate of each facility.
    """
    if not math.isfinite(reference_cdd) or reference_cdd <= 0:
        raise ValueError("Reference cooling degree days has to be positive")

    differences = []

    for cdd in cdd_values:
        if not math.isfinite(cdd) or cdd < 0:
            raise ValueError("Cooling degree days can't be negative or missing")

        differences.append((cdd - reference_cdd) / reference_cdd)

    return differences


def fit_slope(x_values: list[float], y_values: list[float]) -> float:
    """
    Fit a straight line through the points and return its slope.

    Least squares slope:
        slope = sum((x - x_mean) * (y - y_mean)) / sum((x - x_mean)^2)

    With x from climate_differences() and y from overhead_differences(),
    the slope is k.

    Args:
        x_values (list[float]): Relative climate of each facility.
        y_values (list[float]): Relative overhead of each facility.
    Returns:
        float: The slope, which is the estimate of k.
    """
    if len(x_values) != len(y_values):
        raise ValueError("x and y lists must be the same length")

    # Two points always fit a line exactly, so they say nothing about scatter.
    if len(x_values) < 3:
        raise ValueError("Need at least three facilities to fit a slope")

    for value in x_values + y_values:
        if not math.isfinite(value):
            raise ValueError("Every x and y has to be a real number")

    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)

    top = 0.0
    bottom = 0.0

    for x, y in zip(x_values, y_values):
        top += (x - x_mean) * (y - y_mean)
        bottom += (x - x_mean) ** 2

    # If every facility had the same climate there is no slope to measure.
    # Rounding leaves a tiny leftover instead of exactly 0 (the mean of three
    # 0.1s is 0.10000000000000002), so I compare against a small tolerance.
    if bottom < 1e-12:
        raise ValueError("All facilities have the same climate; no slope")

    return top / bottom


# Worked example, printing the intermediate values so the arithmetic can be
# followed by hand. The numbers are made up, not a real site.

if __name__ == "__main__":

    print("Population exposure for one site, 1 km buffer")
    print("-" * 20)

    radius = 1000.0
    populations = [4200.0, 1800.0, 950.0]
    areas = [2500000.0, 8000000.0, 6000000.0]
    overlaps = [1800000.0, 1100000.0, 241592.65]

    print(f"Buffer area: {buffer_area(radius):,.2f} m2")

    for index in range(len(populations)):
        share = tract_share(overlaps[index], areas[index])
        print(f"  tract {index}: population {populations[index]:,.0f}"
              f" x share {share:.4f} = {populations[index] * share:,.2f} people")

    exposure = calculate_population_exposure(populations, areas, overlaps)
    coverage = coverage_fraction(overlaps, radius)

    print(f"People within 1 km: {exposure:,.2f}")
    print(f"Buffer covered by tracts: {coverage:.1%}")

    print()
    print("Cooling demand multiplier for one site")
    print("-" * 20)

    # Three days standing in for a year, so the total can be checked by hand.
    temperatures = [78.0, 64.0, 91.0]
    site_cdd = cooling_degree_days(temperatures)

    print(f"Daily temperatures: {temperatures}")
    print(f"Cooling degree days: {site_cdd:.1f}")

    reference = 1200.0
    k = 0.15
    multiplier = adjust_for_temperature(1800.0, reference, k)

    print(f"Site CDD 1800 against reference {reference:.0f}, sensitivity {k}")
    print(f"Cooling demand multiplier: {multiplier:.3f}")
