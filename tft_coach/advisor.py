"""Turns a game state into econ / level / reroll advice."""
from dataclasses import dataclass

from . import econ
from .econ import DATA, parse_stage

# Strategy -> level you sit on while slow-rolling for 3-stars (None = level normally).
HOLD_LEVEL = {"standard": None, "reroll1": 5, "reroll2": 6, "reroll3": 7}
ECON_CAP = DATA["interest_per"] * DATA["interest_cap"]


@dataclass
class GameState:
    stage: str  # e.g. "3-2"
    level: int
    xp: int
    gold: int
    hp: int = 100
    streak: int = 0  # positive = win streak, negative = loss streak
    strategy: str = "standard"
    hit: bool = False  # reroll strategies: True once your 3-stars are done


@dataclass
class Advice:
    action: str  # LEVEL | ROLL | SAVE | INFO
    text: str


def _in_danger(s: GameState) -> bool:
    stage = parse_stage(s.stage)
    return (stage >= (3, 5) and s.hp <= 30) or (stage >= (4, 1) and s.hp <= 40)


def advise(s: GameState) -> list[Advice]:
    out: list[Advice] = []
    stage = parse_stage(s.stage)
    gold = s.gold
    hold = None if s.hit else HOLD_LEVEL[s.strategy]
    danger = _in_danger(s)

    # --- levelling ---
    cost = econ.cost_to_level(s.level, s.xp)
    if cost is not None and (hold is None or s.level < hold):
        nxt = s.level + 1
        tempo = DATA["level_tempo"].get(str(nxt))
        on_tempo = tempo is not None and stage >= parse_stage(tempo)
        if cost <= gold and on_tempo:
            out.append(Advice("LEVEL", f"Level to {nxt} ({cost}g). Standard timing for {nxt} is {tempo}."))
            gold -= cost
        elif gold - cost >= ECON_CAP:
            out.append(Advice("LEVEL", f"Level to {nxt} ({cost}g): you stay at {ECON_CAP}+ gold, so it costs no interest."))
            gold -= cost
        elif on_tempo:
            out.append(Advice("INFO", f"Behind tempo for level {nxt} ({tempo}); need {cost}g, have {gold}g."))

    # --- rolling ---
    if danger:
        out.append(Advice("ROLL", f"HP {s.hp}: roll down now to stabilise your board. Surviving beats interest."))
    elif hold is not None and s.level == hold:
        spare = (gold - ECON_CAP) // DATA["reroll_cost"]
        if spare > 0:
            out.append(Advice("ROLL", f"Slow-roll: {spare} reroll(s), stay at {ECON_CAP}g."))
        else:
            out.append(Advice("SAVE", f"Slow-roll level {hold}: econ to {ECON_CAP}g before rolling."))
    elif hold is None and s.level == 8 and stage >= (4, 2):
        if gold >= 30:
            out.append(Advice("ROLL", "Level 8: roll for your 4-cost carries. Stop around 10-20g or once the board is upgraded."))
        else:
            out.append(Advice("SAVE", "Level 8 but low gold: rebuild econ unless you are losing hard."))
    elif hold is None and s.level >= 9:
        spare = (gold - 30) // DATA["reroll_cost"]
        if spare > 0:
            out.append(Advice("ROLL", f"Level {s.level}: {spare} reroll(s) for 5-costs, keep ~30g."))
    else:
        out.append(Advice("SAVE", "Don't roll: your level's shop odds aren't worth it yet."))

    # --- interest ---
    if not danger:
        missing = econ.gold_to_next_interest(gold)
        if 0 < missing <= 3:
            out.append(Advice("INFO", f"{missing}g short of {gold + missing}g interest: sell a bench unit or skip a buy."))
        out.append(Advice("INFO", f"Next round income: +{econ.income(gold, s.streak)}g (interest {econ.interest(gold)}, "
                                  f"streak {econ.streak_gold(s.streak)})."))
    return out
