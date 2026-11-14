"""tests/test_lab_sim.py - Unit tests for tools/lab_sim.py Monte Carlo simulation engine."""
import unittest
from tools import lab_sim
from utils import lab as lab_catalog


class TestLabSimulation(unittest.TestCase):
    def test_simulate_single_compound_isolated(self):
        """Verify single compound simulation converges and returns a positive float."""
        methane = lab_catalog.COMPOUND_BY_NAME.get("methane")
        self.assertIsNotNone(methane)
        avg_time = lab_sim.simulate_single_compound_isolated(methane, trials=30)
        self.assertIsInstance(avg_time, float)
        self.assertGreater(avg_time, 0)
        # Methane requires 1 C and 4 H; should be craftable quickly (~1-3 minutes)
        self.assertLess(avg_time, 10)

    def test_simulate_user_progression_subset(self):
        """Verify simulate_user progression logic on a small subset of compounds."""
        # Test with first 3 alkanes
        subset = [c for c in lab_catalog.COMPOUNDS if c["category"] == "Alkanes"][:3]
        res = lab_sim.simulate_user(subset)
        self.assertIn("first_compound_time", res)
        self.assertIsNotNone(res["first_compound_time"])
        self.assertGreater(res["first_compound_time"], 0)
        self.assertIn("category_times", res)
        self.assertIn("all_completed_time", res)
        self.assertGreaterEqual(res["all_completed_time"], res["first_compound_time"])


if __name__ == "__main__":
    unittest.main()
