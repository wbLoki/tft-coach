import unittest

from tft_coach import comps
from tft_coach.meta import display

INFERNO = {"name": "Adaptor + Inferno", "avg_place": 4.8, "level": 8,"traits": {"Inferno": 2, "Rapidfire": 2, "Lunar": 2},
           "units": [{"name": "Varus"}, {"name": "Kog Maw"}, {"name": "Rek Sai"}]}
STRONG = {"name": "Executioner + Summoner", "avg_place": 3.1, "traits": {"Executioner": 4, "Summoner": 3},
          "units": [{"name": "Zyra"}]}
META = {"comps": [STRONG, INFERNO]}


class CompsTest(unittest.TestCase):
    def test_display_names(self):
        self.assertEqual(display("DA_18_KhaZix"), "Kha Zix")
        self.assertEqual(display("DA_18_KogMaw18_AD"), "Kog Maw")
        self.assertEqual(display("DA_HandOfJustice"), "Hand Of Justice")

    def test_fitting_comp_beats_stronger_comp(self):
        ranked = comps.rank(META, {"Inferno": 2, "Rapidfire": 2, "Fae": 1})
        self.assertEqual(ranked[0][1]["name"], "Adaptor + Inferno")

    def test_no_traits_falls_back_to_placement(self):
        self.assertEqual(comps.rank(META, {})[0][1]["name"], "Executioner + Summoner")

    def test_contested_comp_drops(self):
        scouted = {"a": {"Inferno": 2, "Rapidfire": 2, "Lunar": 2}, "b": {"Inferno": 2, "Lunar": 2}, "c": {"Fae": 1}}
        contenders = comps.find_contenders(META, scouted)
        self.assertEqual(contenders, {"Adaptor + Inferno": ["a", "b"]})
        mine = {"Inferno": 2, "Rapidfire": 1, "Executioner": 2}
        self.assertEqual(comps.rank(META, mine)[0][1]["name"], "Adaptor + Inferno")
        self.assertEqual(comps.rank(META, mine, contenders)[0][1]["name"], "Executioner + Summoner")

    def test_units_held_by_opponents_lower_a_comp(self):
        mine = {"Inferno": 2, "Rapidfire": 1, "Executioner": 2}
        self.assertEqual(comps.rank(META, mine)[0][1]["name"], "Adaptor + Inferno")
        taken = {"Varus": 4, "Kog Maw": 3, "Zyra": 0}
        self.assertEqual(comps.unit_contest(INFERNO, taken), 7)
        self.assertEqual(comps.rank(META, mine, taken=taken)[0][1]["name"], "Executioner + Summoner")

    def test_spare_emblem_shifts_ranking(self):
        mine = {"Inferno": 1, "Executioner": 2}
        self.assertEqual(comps.rank(META, mine)[0][1]["name"], "Executioner + Summoner")
        boosted = comps.with_emblems(mine, ["Inferno", "Lunar"])
        self.assertEqual(boosted, {"Inferno": 2, "Executioner": 2, "Lunar": 1})
        self.assertEqual(comps.rank(META, boosted)[0][1]["name"], "Adaptor + Inferno")
        self.assertEqual(mine, {"Inferno": 1, "Executioner": 2})

    def test_emblem_outweighs_a_plain_unit(self):
        mine = {"Executioner": 1, "Fae": 2}
        # One more Inferno unit is not enough to pivot, an Inferno emblem is.
        self.assertEqual(comps.rank(META, {**mine, "Inferno": 1})[0][1]["name"], "Executioner + Summoner")
        self.assertEqual(comps.rank(META, mine, emblems=["Inferno"])[0][1]["name"], "Adaptor + Inferno")
        self.assertEqual(comps.emblem_bonus(INFERNO, ["Inferno", "Lunar", "Fae"]),
                         comps.EMBLEM_BONUS_MAIN + comps.EMBLEM_BONUS_SIDE)

    def test_infer_board_from_traits(self):
        units = ({"name": "A", "traits": ["Inferno", "Rapidfire"]}, {"name": "B", "traits": ["Inferno", "Fae"]},
                 {"name": "C", "traits": ["Rapidfire", "Defender"]}, {"name": "D", "traits": ["Fae", "Defender"]},
                 {"name": "E", "traits": ["Lunar"]})
        panel = {"Inferno": 2, "Rapidfire": 2, "Fae": 1, "Defender": 1}
        self.assertEqual(comps.infer_board(panel, 4, units), [["A", "B", "C"]])
        self.assertEqual(comps.infer_board(panel, 2, units), [])  # needs three units
        self.assertEqual(len(comps.infer_board({"Fae": 1, "Defender": 1, "Inferno": 1, "Rapidfire": 1}, 4, units)), 2)
        self.assertEqual(comps.infer_board({"lnferno": 1, "Fae": 1}, 4, units), [["B"]])  # OCR misspelling

    def test_board_by_level(self):
        unit = lambda name, cost, freq, front, avg: {"name": name, "cost": cost, "freq": freq, "front": front,
                                                     "item_avg": avg, "items": ["x"]}
        comp = {"level": 4, "units": [unit("Carry", 4, 1.0, False, 2.8), unit("Tank", 4, 0.9, True, 2.5),
                                      unit("Cheap", 1, 0.8, True, 0.1), unit("Mid", 2, 0.7, False, 0.5),
                                      unit("Flex", 1, 0.5, False, 0.0)]}
        self.assertEqual(comps.board(comp, 2), (["Cheap"], ["Mid"]))
        self.assertEqual(comps.board(comp, 4), (["Tank", "Cheap"], ["Carry", "Mid"]))
        self.assertEqual(comps.board(comp, 5), (["Tank", "Cheap"], ["Carry", "Mid", "Flex"]))
        self.assertEqual([(l, u["name"]) for l, u in comps.item_holders(comp)], [("Carry", "Carry"), ("Tank", "Tank")])

    def test_extra_slot_adds_a_unit(self):
        unit = lambda name, cost, freq: {"name": name, "cost": cost, "freq": freq, "front": False}
        comp = {"level": 3, "traits": {}, "early": [unit("Standin", 1, 0)],
                "units": [unit("A", 1, 1.0), unit("B", 1, 0.9), unit("C", 2, 0.8), unit("D", 2, 0.7)]}
        self.assertEqual(comps.board(comp, 3), ([], ["A", "B", "C"]))
        self.assertEqual(comps.board(comp, 3, size=4), ([], ["A", "B", "C", "D"]))  # final level: next comp unit
        self.assertEqual(comps.board(comp, 2, size=3), ([], ["A", "B", "C"]))  # early: 3 slots at level 2
        owned = {"A": "board", "B": "board", "C": "board", "D": "bench"}
        self.assertEqual([u["name"] for u in comps.plan_board(comp, 3, owned)[0]], ["A", "B", "C"])
        self.assertEqual([u["name"] for u in comps.plan_board(comp, 3, owned, size=4)[0]], ["A", "B", "C", "D"])

    def test_placeholders_fill_early_board(self):
        unit = lambda name, cost, freq, front: {"name": name, "cost": cost, "freq": freq, "front": front}
        comp = {"level": 8, "units": [unit("Carry", 4, 1.0, False), unit("Tank", 4, 0.9, True), unit("Cheap", 1, 0.8, True)],
                "early": [unit("Standin", 1, 0, False), unit("Pricey", 3, 0, True)]}
        self.assertEqual(comps.board(comp, 3), (["Cheap"], ["Standin*"]))  # 3-cost and 4-costs not fieldable at level 3
        self.assertEqual(comps.shop_picks(["Standin", "Carry", "Pricey", None, "Other"], comp, 3),
                         [(1, "Standin* placeholder"), (2, "Carry")])
        self.assertEqual(comps.shop_picks(["Standin", "Carry"], comp, 8), [(2, "Carry")])

    def test_shop_picks_match_ocr_spelling(self):
        shop = [None, "Murkwolf", "Rek'Sai", "Kog'Maw", "Varus"]
        self.assertEqual(comps.shop_picks(shop, INFERNO), [(3, "Rek'Sai"), (4, "Kog'Maw"), (5, "Varus")])


if __name__ == "__main__":
    unittest.main()
