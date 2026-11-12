import unittest

from src.model.scenarios import (
    SimulationScenario,
    TemporalScenario,
)


class SimulationScenarioTests(unittest.TestCase):

    def test_valid_simulation_scenario(self):
        scenario = SimulationScenario(
            name="reference_training",
            power_density_scenario="reference",
            workload="ai_training",
            floor_area_multiplier=1.0,
            utilization=0.8,
            idle_fraction=0.2,
            pue=1.4,
        )

        self.assertEqual(
            scenario.power_density_scenario,
            "reference",
        )

        self.assertEqual(
            scenario.workload_parameters,
            {
                "utilization": 0.8,
                "idle_fraction": 0.2,
                "pue": 1.4,
            },
        )

    def test_invalid_utilization_rejected(self):
        with self.assertRaises(ValueError):
            SimulationScenario(
                name="bad",
                power_density_scenario="reference",
                workload="ai_training",
                floor_area_multiplier=1.0,
                utilization=1.5,
                idle_fraction=0.2,
                pue=1.4,
            )

    def test_invalid_density_scenario_rejected(self):
        with self.assertRaises(ValueError):
            SimulationScenario(
                name="bad",
                power_density_scenario="extreme",
                workload="ai_training",
                floor_area_multiplier=1.0,
                utilization=0.8,
                idle_fraction=0.2,
                pue=1.4,
            )


class TemporalScenarioTests(unittest.TestCase):

    def test_year_range_is_inclusive(self):
        scenario = TemporalScenario(
            name="moderate",
            start_year=2023,
            end_year=2025,
            annual_growth_rate=0.05,
        )

        self.assertEqual(
            list(scenario.years),
            [2023, 2024, 2025],
        )

    def test_compound_growth_factor(self):
        scenario = TemporalScenario(
            name="moderate",
            start_year=2023,
            end_year=2030,
            annual_growth_rate=0.05,
        )

        self.assertAlmostEqual(
            scenario.growth_factor(2023),
            1.0,
        )

        self.assertAlmostEqual(
            scenario.growth_factor(2024),
            1.05,
        )

        self.assertAlmostEqual(
            scenario.growth_factor(2025),
            1.1025,
        )

    def test_invalid_year_range_rejected(self):
        with self.assertRaises(ValueError):
            TemporalScenario(
                name="bad",
                start_year=2030,
                end_year=2023,
                annual_growth_rate=0.05,
            )


if __name__ == "__main__":
    unittest.main()