import unittest

from tft_coach import comps
from tft_coach.live import Session

COST = {u["name"]: u["cost"] for u in comps.playable_units()}


@unittest.skipUnless(COST, "needs data/static.json (run python -m tft_coach.meta)")
class PurchaseTrackingTest(unittest.TestCase):
    def setUp(self):
        self.s = Session(None)
        self.shop = ["Varus", "Shen", None, "Diana", "Rek'Sai"]
        self.s.track_purchases("2-1", 20, self.shop, [])

    def test_card_gone_and_gold_paid_is_a_purchase(self):
        self.s.track_purchases("2-1", 20 - COST["Shen"], ["Varus", None, None, "Diana", "Rek'Sai"], [])
        self.assertEqual(dict(self.s.bought), {"Shen": 1})

    def test_two_cards_bought_between_frames(self):
        self.s.track_purchases("2-1", 20 - COST["Varus"] - COST["Diana"], [None, "Shen", None, None, "Rek'Sai"], [])
        self.assertEqual(dict(self.s.bought), {"Varus": 1, "Diana": 1})

    def test_card_unreadable_without_gold_change_is_ignored(self):
        self.s.track_purchases("2-1", 20, ["Varus", None, None, "Diana", "Rek'Sai"], [])
        self.assertEqual(dict(self.s.bought), {})

    def test_reroll_is_not_a_purchase(self):
        self.s.track_purchases("2-1", 18, ["Leona", None, "Kayle", "Sejuani", None], [])
        self.assertEqual(dict(self.s.bought), {})

    def test_round_change_is_not_compared(self):
        self.s.track_purchases("2-2", 20 - COST["Shen"], ["Varus", None, None, "Diana", "Rek'Sai"], [])
        self.assertEqual(dict(self.s.bought), {})

    def test_unit_leaving_board_goes_to_bench(self):
        self.s.track_board(["Varus", "Shen", "Xayah"])
        self.s.track_board(["Varus", "Xayah"])
        self.assertEqual(self.s.bought["Shen"], 1)
        self.s.track_board(["Varus", "Xayah", "Shen"])  # back on the board: still owned, no longer bench
        self.assertEqual(self.s.bought["Shen"], 1)

    def test_unit_leaving_board_with_sale_gold_is_sold(self):
        self.s.track_board(["Varus", "Shen"])
        self.s.track_purchases("2-1", 20 + COST["Shen"], self.shop, ["Varus", "Shen"])  # gold up, shop unchanged
        self.s.track_board(["Varus"])
        self.assertEqual(self.s.bought["Shen"], 0)
        self.assertEqual(self.s.sales, [])

    def test_unambiguous_sale_removes_bench_unit(self):
        self.s.bought.update({"Diana": 1, "Varus": 1})
        self.s.track_purchases("2-1", 20 + COST["Diana"], self.shop, ["Varus"])
        self.assertEqual(self.s.bought["Diana"], 0)
        self.assertEqual(self.s.bought["Varus"], 1)


if __name__ == "__main__":
    unittest.main()
