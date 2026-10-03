"""Gold, XP and shop-odds maths. All set-specific numbers come from data/set_data.json."""
import json
import math
from pathlib import Path

DATA = json.loads((Path(__file__).parent.parent / "data" / "set_data.json").read_text())


def parse_stage(stage: str) -> tuple[int, int]:
    a, b = stage.split("-")
    return int(a), int(b)


def interest(gold: int) -> int:
    return min(gold // DATA["interest_per"], DATA["interest_cap"])


def streak_gold(streak: int) -> int:
    """streak is the length of the current win OR loss streak."""
    for length, bonus in DATA["streak_gold"]:
        if abs(streak) >= length:
            return bonus
    return 0


def income(gold: int, streak: int = 0) -> int:
    """Gold gained at the start of next round, excluding the +1 for a win."""
    return DATA["base_income"] + interest(gold) + streak_gold(streak)


def gold_to_next_interest(gold: int) -> int:
    """Gold missing to reach the next interest breakpoint (0 if already capped)."""
    if interest(gold) >= DATA["interest_cap"]:
        return 0
    return DATA["interest_per"] - gold % DATA["interest_per"]


def cost_to_level(level: int, xp: int) -> int | None:
    """Gold needed to reach the next level, or None at max level."""
    if level >= DATA["max_level"]:
        return None
    missing = DATA["xp_to_next_level"][str(level)] - xp
    buys = math.ceil(max(missing, 0) / DATA["xp_per_buy"])
    return buys * DATA["xp_buy_cost"]


def shop_odds(level: int) -> list[float]:
    return [p / 100 for p in DATA["shop_odds"][str(level)]]


def hit_chance(level: int, cost: int, gold: int, owned: int = 0, taken_by_others: int = 0,
               other_units_taken: int = 0) -> float:
    """Chance to see at least one copy of a specific unit when spending `gold` on rerolls.

    Approximation: ignores the pool shrinking as you roll.
    """
    copies = DATA["copies_per_unit"][cost - 1]
    left = max(copies - owned - taken_by_others, 0)
    pool = copies * DATA["units_per_cost"][cost - 1] - owned - taken_by_others - other_units_taken
    if left == 0 or pool <= 0:
        return 0.0
    per_slot = shop_odds(level)[cost - 1] * left / pool
    slots = (gold // DATA["reroll_cost"]) * DATA["shop_slots"]
    return 1 - (1 - per_slot) ** slots
