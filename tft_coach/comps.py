"""Matches what is on screen (traits, shop) against the meta comps in data/meta.json."""
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from functools import lru_cache

from .meta import META_FILE, SET_DATA, STATIC_FILE

PLACEMENT_WEIGHT = 0.05  # how much a comp's average placement counts against trait fit
CONTEST_PENALTY = 0.1  # per opponent already on the comp
UNIT_CONTEST_PENALTY = 0.02  # per opponent board holding one of the comp's core units
UNIT_CONTEST_CAP = 0.2
EMBLEM_BONUS_MAIN = 0.25  # spare emblem for one of the comp's two defining traits
EMBLEM_BONUS_SIDE = 0.1  # spare emblem for another trait the comp uses
MAX_BOARD_GUESSES = 30  # stop looking for more unit sets that fit the trait panel
MAX_SEARCH_STEPS = 200_000  # keeps a late-game search from stalling the window
FIND_SHOWN = 5
BUY_MIN_FREQ = 0.4  # only flag shop units that the comp fields at least this often
CONTENDER_MIN_FIT = 0.4  # below this an opponent's board doesn't point at any comp yet


def load() -> dict | None:
    return json.loads(META_FILE.read_text()) if META_FILE.exists() else None


def emblem_traits() -> list[str]:
    """Traits that have an emblem in the current set."""
    if not STATIC_FILE.exists():
        return []
    static = json.loads(STATIC_FILE.read_text())
    marker = f"_{static['set']}_Emblem"
    return sorted({name.removesuffix(" Emblem") for api, name in static["items"].items() if marker in api})


def with_emblems(traits: dict[str, int], emblems: list[str]) -> dict[str, int]:
    """Your traits with +1 for each emblem you hold but haven't equipped yet."""
    out = dict(traits)
    for emblem in emblems:
        key = next((t for t in out if _same(t, emblem)), emblem)
        out[key] = out.get(key, 0) + 1
    return out


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def _same(a: str, b: str) -> bool:
    a, b = _norm(a), _norm(b)
    if a == b:
        return True
    if min(len(a), len(b)) < 4:
        return False
    return a.startswith(b) or b.startswith(a) or SequenceMatcher(None, a, b).ratio() >= 0.8


def fit(comp: dict, traits: dict[str, int]) -> float:
    """How well your traits and the comp's overlap (0..1).

    Average of: share of your trait units that the comp uses, and share of the comp you already fill.
    """
    need, mine = sum(comp["traits"].values()), sum(traits.values())
    have = sum(min(count, next((c for t, c in traits.items() if _same(t, name)), 0))
               for name, count in comp["traits"].items())
    return (have / need + have / mine) / 2 if need and mine else 0.0


def emblem_bonus(comp: dict, emblems: list[str]) -> float:
    """Ranking bonus for spare emblems: an emblem fits any unit, so it is worth more than one unit of the trait."""
    main = comp["name"].split(" + ")
    bonus = 0.0
    for emblem in emblems:
        if any(_same(emblem, t) for t in main):
            bonus += EMBLEM_BONUS_MAIN
        elif any(_same(emblem, t) for t in comp["traits"]):
            bonus += EMBLEM_BONUS_SIDE
    return bonus


def certain_units(traits: dict[str, int], max_units: int = 10) -> list[str]:
    """Units that must be on a board showing these traits (in every unit set that fits)."""
    guesses = infer_board(traits, max_units)
    return [n for n in guesses[0] if all(n in g for g in guesses)] if guesses else []


def unit_contest(comp: dict, taken: dict[str, int]) -> int:
    """How many opponent boards hold the comp's core units, added up over those units."""
    return sum(taken.get(u["name"], 0) for u in comp["units"] if u.get("freq", 1) >= BUY_MIN_FREQ)


def rank(meta: dict, traits: dict[str, int], contenders: dict[str, list[str]] | None = None,
         emblems: list[str] = (), taken: dict[str, int] | None = None) -> list[tuple[float, dict]]:
    """Comps sorted best first, as (fit, comp).

    `contenders` maps comp name -> opponents playing it. `emblems` are spare emblems
    you hold: they count as +1 of their trait and add a bonus to comps built on it.
    `taken` maps unit name -> how many opponents field it: comps whose core units
    are drained from the shared pool rank lower.
    """
    contenders, taken = contenders or {}, taken or {}
    traits = with_emblems(traits, emblems)
    scored = [(fit(c, traits), c) for c in meta["comps"]]
    return sorted(scored, key=lambda fc: -(fc[0] + (4.5 - fc[1]["avg_place"]) * PLACEMENT_WEIGHT
                                           + emblem_bonus(fc[1], emblems)
                                           - len(contenders.get(fc[1]["name"], [])) * CONTEST_PENALTY
                                           - min(unit_contest(fc[1], taken) * UNIT_CONTEST_PENALTY, UNIT_CONTEST_CAP)))


def find_contenders(meta: dict, scouted: dict[str, dict[str, int]]) -> dict[str, list[str]]:
    """Comp name -> opponents whose scouted traits point at that comp."""
    out: dict[str, list[str]] = {}
    for player, traits in scouted.items():
        best_fit, comp = rank(meta, traits)[0]
        if best_fit >= CONTENDER_MIN_FIT:
            out.setdefault(comp["name"], []).append(player)
    return out


def max_cost(level: int) -> int:
    """Highest unit cost you can realistically field at this level."""
    return 2 if level <= 4 else 3 if level <= 6 else 4 if level == 7 else 5


def board_units(comp: dict, level: int, size: int | None = None) -> tuple[list[dict], list[dict]]:
    """Estimated (final-board units, placeholders) to field at this level.

    `size` is how many units you can field: your level, plus any extra slots from
    Tactician's Cape/Crown or augments. Match data only has final boards, so below
    the comp's usual level this is the final units you can afford yet, topped up
    with cheap units sharing its traits.
    """
    size = size or level
    final = comp["units"][:max(size, comp["level"])]  # units are sorted most common first
    if level >= comp["level"]:
        return final[:size], []
    real = sorted((u for u in final if u["cost"] <= max_cost(level)), key=lambda u: (u["cost"], -u["freq"]))[:size]
    fill = [u for u in comp.get("early", []) if u["cost"] <= max_cost(level)][:size - len(real)]
    return real, fill


def board(comp: dict, level: int, size: int | None = None) -> tuple[list[str], list[str]]:
    """(front row, back row) names for this level; placeholders are marked with *."""
    real, fill = board_units(comp, level, size)
    named = [(u, u["name"]) for u in real] + [(u, u["name"] + "*") for u in fill]
    return [n for u, n in named if u["front"]], [n for u, n in named if not u["front"]]


@lru_cache
def playable_units() -> tuple[dict, ...]:
    """Units of the current set that have traits (name, cost, traits)."""
    if not STATIC_FILE.exists():
        return ()
    units = json.loads(STATIC_FILE.read_text())["units"].values()
    return tuple(u for u in units if u["traits"] and "(" not in u["name"])


def resolve_unit(text: str | None) -> dict | None:
    """The unit (name, cost, traits) a piece of shop text refers to, if any."""
    return next((u for u in playable_units() if _same(text, u["name"])), None) if text else None


def infer_board(panel: dict[str, int], max_units: int, units: tuple[dict, ...] | None = None) -> list[list[str]]:
    """Unit sets whose traits add up exactly to the trait panel's counts.

    The app can't see units, but every unit has known traits, so the panel usually
    pins down the board. Returns every possibility (often exactly one), or [] if
    nothing fits (misread panel, equipped emblem, traits scrolled off the panel).
    """
    units = playable_units() if units is None else units
    known = {t for u in units for t in u["traits"]}
    left = {}
    for name, count in panel.items():
        trait = next((t for t in known if _same(t, name)), None)
        if trait:
            left[trait] = count
    cands = [u for u in units if all(t in left for t in u["traits"])]
    out: list[list[str]] = []

    steps = 0

    def search(i: int, chosen: list[str]):
        nonlocal steps
        steps += 1
        if len(out) >= MAX_BOARD_GUESSES or steps > MAX_SEARCH_STEPS:
            return
        if not any(left.values()):
            out.append(chosen)
            return
        if i == len(cands) or len(chosen) == max_units:
            return
        u = cands[i]
        if all(left[t] > 0 for t in u["traits"]):
            for t in u["traits"]:
                left[t] -= 1
            search(i + 1, chosen + [u["name"]])
            for t in u["traits"]:
                left[t] += 1
        search(i + 1, chosen)

    if left:
        search(0, [])
    return out


def plan_board(comp: dict, level: int, owned: dict[str, str], size: int | None = None) -> tuple[list[dict], list[str]]:
    """(units to field, units to look for), choosing from the units you can get right now.

    `owned` maps unit name -> where it is ("board", "bench" or "shop 3"), in that order
    of preference. Each fielded unit is {name, where, front, kind}, where kind is
    "comp", "placeholder" (shares the comp's traits) or "off-comp" (replace when you can).
    """
    by_name = {u["name"]: u for u in playable_units()}
    final = {u["name"]: u for u in comp["units"]}
    picks = []
    for order, (name, where) in enumerate(owned.items()):
        traits = by_name.get(name, {}).get("traits", [])
        if name in final:
            rank, kind, front = 0, "comp", final[name]["front"]
        else:
            shares = any(t in comp["traits"] for t in traits)
            rank, kind = (1, "placeholder") if shares else (2, "off-comp")
            front = any(t in SET_DATA["frontline_traits"] for t in traits)
        if where.startswith("shop") and kind == "off-comp":
            continue  # never suggest buying an off-comp unit
        picks.append((rank, order, {"name": name, "where": where, "front": front, "kind": kind}))
    fielded = [p for _, _, p in sorted(picks, key=lambda p: p[:2])[:size or level]]
    real, fill = board_units(comp, level, size)
    find = [u["name"] for u in real + fill if u["name"] not in owned]
    return fielded, find[:FIND_SHOWN]


def item_plan(comp: dict) -> tuple[list[tuple[str, str, list[str]]], list[tuple[str, int]]]:
    """([(role, unit, items)], [(component, how many)]) for the comp's carry and main tank."""
    holders = [(label, u["name"], u["items"]) for label, u in item_holders(comp)]
    recipes = json.loads(STATIC_FILE.read_text()).get("recipes", {}) if STATIC_FILE.exists() else {}
    spelling: dict[str, str] = {}  # the data spells some components two ways ("of the" / "Of The")
    need = Counter(spelling.setdefault(c.lower(), c) for _, _, items in holders for i in items
                   for c in recipes.get(i, []))
    return holders, need.most_common()


def item_holders(comp: dict) -> list[tuple[str, dict]]:
    """[('Carry', unit), ('Tank', unit)]: the most itemised back-row and front-row unit."""
    out = []
    for label, front in (("Carry", False), ("Tank", True)):
        units = [u for u in comp["units"] if u["front"] == front and u["items"]]
        if units:
            out.append((label, max(units, key=lambda u: u["item_avg"])))
    return out


def shop_picks(shop: list[str | None], comp: dict, level: int = 10, size: int | None = None) -> list[tuple[int, str]]:
    """(slot number, label) for shop units worth buying: the comp's own units, plus
    the placeholders on this level's board (labelled as such)."""
    core = [u["name"] for u in comp["units"] if u.get("freq", 1) >= BUY_MIN_FREQ]
    fill = [u["name"] for u in board_units(comp, level, size)[1]]
    picks = []
    for i, name in enumerate(shop, 1):
        if name and any(_same(name, c) for c in core):
            picks.append((i, name))
        elif name and any(_same(name, f) for f in fill):
            picks.append((i, f"{name}* placeholder"))
    return picks
