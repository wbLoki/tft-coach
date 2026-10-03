import unittest

from tft_coach import econ
from tft_coach.advisor import GameState, advise


def actions(**kw):
    return [a.action for a in advise(GameState(**kw))]


class EconTest(unittest.TestCase):
    def test_interest(self):
        self.assertEqual([econ.interest(g) for g in (9, 10, 49, 50, 80)], [0, 1, 4, 5, 5])

    def test_gold_to_next_interest(self):
        self.assertEqual(econ.gold_to_next_interest(48), 2)
        self.assertEqual(econ.gold_to_next_interest(60), 0)

    def test_cost_to_level(self):
        self.assertEqual(econ.cost_to_level(7, 20), 28)  # 28 xp missing -> 7 buys
        self.assertEqual(econ.cost_to_level(7, 46), 4)
        self.assertIsNone(econ.cost_to_level(10, 0))

    def test_hit_chance(self):
        self.assertEqual(econ.hit_chance(5, 5, 50), 0.0)
        low, high = econ.hit_chance(8, 4, 20), econ.hit_chance(8, 4, 50)
        self.assertTrue(0 < low < high < 1)
        self.assertEqual(econ.hit_chance(8, 4, 50, taken_by_others=10), 0.0)


class AdvisorTest(unittest.TestCase):
    def test_levels_on_tempo(self):
        self.assertIn("LEVEL", actions(stage="2-1", level=3, xp=2, gold=6))

    def test_saves_before_tempo(self):
        a = actions(stage="3-1", level=5, xp=0, gold=30)
        self.assertNotIn("LEVEL", a)
        self.assertIn("SAVE", a)

    def test_levels_early_when_rich(self):
        self.assertIn("LEVEL", actions(stage="3-5", level=6, xp=30, gold=60))

    def test_roll_at_eight(self):
        self.assertIn("ROLL", actions(stage="4-5", level=8, xp=0, gold=50))

    def test_slow_roll_holds_level(self):
        a = actions(stage="3-3", level=6, xp=0, gold=58, strategy="reroll2")
        self.assertEqual(a[0], "ROLL")
        self.assertNotIn("LEVEL", a)

    def test_danger_rolls(self):
        self.assertIn("ROLL", actions(stage="4-2", level=7, xp=0, gold=40, hp=25))


if __name__ == "__main__":
    unittest.main()
