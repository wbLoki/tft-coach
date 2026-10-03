"""Builds data/meta.json (current meta comps) from recent Challenger matches.

Run: .venv\\Scripts\\python -m tft_coach.meta            (fetch new matches, then rebuild)
     .venv\\Scripts\\python -m tft_coach.meta --no-fetch (rebuild from cached matches only)

Needs RIOT_API_KEY in .env or the environment. Optional: RIOT_PLATFORM (default euw1), RIOT_REGION (default europe).

.github/workflows/meta.yml runs this on a schedule and publishes the result; the coach picks it up with update().
"""
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).parent.parent
MATCH_DIR = ROOT / "data" / "matches"
META_FILE = ROOT / "data" / "meta.json"
STATIC_FILE = ROOT / "data" / "static.json"
SET_DATA = json.loads((ROOT / "data" / "set_data.json").read_text())
CDRAGON_URL = "https://raw.communitydragon.org/latest/cdragon/tft/en_us.json"
PUBLISHED_URL = "https://raw.githubusercontent.com/wbLoki/tft-coach/meta/"  # branch written by the meta workflow
UPDATE_TIMEOUT = 10
MIN_ITEM_SAMPLES = 10
PLACEHOLDER_MAX_COST = 3
PLACEHOLDERS_KEPT = 8

PLAYERS = 40
MATCHES_PER_PLAYER = 8
REQUEST_GAP = 1.25  # personal keys allow 100 requests per 2 minutes
RANKED_QUEUE = 1100
MIN_GAMES = 15
CORE_UNIT_FREQ = 0.25  # units kept per comp; the less common ones only fill out the board
RARITY_TO_COST = {0: 1, 1: 2, 2: 3, 4: 4, 6: 5}

ENV_FILE = ROOT / ".env"  # absent in the packaged exe, which only reads the data files
ENV = dict(os.environ)
if ENV_FILE.exists():
    ENV.update(l.strip().split("=", 1) for l in ENV_FILE.read_text().splitlines() if "=" in l)
PLATFORM = ENV.get("RIOT_PLATFORM", "euw1")
REGION = ENV.get("RIOT_REGION", "europe")


def _get(url: str):
    while True:
        time.sleep(REQUEST_GAP)
        req = urllib.request.Request(url, headers={"X-Riot-Token": ENV["RIOT_API_KEY"], "User-Agent": "tft-coach/0.1"})
        try:
            return json.load(urllib.request.urlopen(req, timeout=30))
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(int(e.headers.get("Retry-After", 10)))
            elif e.code in (401, 403):
                sys.exit(f"Riot API refused the key ({e.code}). Dev keys expire after 24h: renew it in .env.")
            elif e.code == 404:
                return None
            else:
                raise


def fetch():
    MATCH_DIR.mkdir(parents=True, exist_ok=True)
    league = _get(f"https://{PLATFORM}.api.riotgames.com/tft/league/v1/challenger?queue=RANKED_TFT")
    players = sorted(league["entries"], key=lambda e: -e["leaguePoints"])[:PLAYERS]
    ids = set()
    for i, p in enumerate(players, 1):
        url = f"https://{REGION}.api.riotgames.com/tft/match/v1/matches/by-puuid/{p['puuid']}/ids?count={MATCHES_PER_PLAYER}"
        ids.update(_get(url) or [])
        print(f"\rmatch lists {i}/{len(players)}", end="", flush=True)
    todo = [m for m in sorted(ids) if not (MATCH_DIR / f"{m}.json").exists()]
    print(f"\n{len(ids)} matches found, {len(todo)} to download (~{len(todo) * REQUEST_GAP / 60:.0f} min)")
    for i, m in enumerate(todo, 1):
        match = _get(f"https://{REGION}.api.riotgames.com/tft/match/v1/matches/{m}")
        if match:
            (MATCH_DIR / f"{m}.json").write_text(json.dumps(match))
        print(f"\rmatches {i}/{len(todo)}", end="", flush=True)
    print()


def update() -> bool:
    """Swaps in the published meta if it is newer than the local one. Offline or unpublished: keeps the local files."""
    try:
        files = {f: urllib.request.urlopen(PUBLISHED_URL + f.name, timeout=UPDATE_TIMEOUT).read()
                 for f in (META_FILE, STATIC_FILE)}
        local = json.loads(META_FILE.read_text())["built"] if META_FILE.exists() else ""
        published = json.loads(files[META_FILE])
        if published["platform"] != PLATFORM or published["built"] <= local:  # another server's meta: keep your own
            return False
        json.loads(files[STATIC_FILE])  # don't replace good files with a broken download
    except (OSError, ValueError, KeyError):
        return False
    for f, content in files.items():
        f.write_bytes(content)
    return True


def display(api_name: str) -> str:
    """'DA_18_KhaZix' -> 'Kha Zix', 'DA_18_KogMaw18_AD' -> 'Kog Maw', 'DA_HandOfJustice' -> 'Hand Of Justice'."""
    name = re.sub(r"^[A-Za-z]+_(\d+_)?", "", api_name)
    name = re.sub(r"\d+(_\w+)?$", "", name)
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)


def _strategy(units: list[dict]) -> str:
    rerolled = [u["cost"] for u in units if u["three_star_rate"] >= 0.5 and u["cost"] <= 3 and u["freq"] >= 0.4]
    return f"reroll{max(rerolled)}" if rerolled else "standard"


def load_static(set_number: int) -> dict:
    """Real names, costs and unit traits from CommunityDragon, cached in data/static.json."""
    if STATIC_FILE.exists():
        static = json.loads(STATIC_FILE.read_text())
        if static["set"] == set_number and "recipes" in static:
            return static
    req = urllib.request.Request(CDRAGON_URL, headers={"User-Agent": "tft-coach/0.1"})
    data = json.load(urllib.request.urlopen(req, timeout=180))
    tft_set = data["sets"][str(set_number)]
    static = {
        "set": set_number,
        "units": {c["apiName"]: {"name": c["name"], "cost": c["cost"], "traits": c["traits"]}
                  for c in tft_set["champions"]},
        "traits": {t["apiName"]: t["name"] for t in tft_set["traits"]},
        "items": {i["apiName"]: i["name"] for i in data["items"] if i.get("name")},
    }
    # Completed item name -> the two components it is built from.
    static["recipes"] = {i["name"]: [static["items"].get(c, c) for c in i["composition"]]
                         for i in data["items"] if i.get("name") and len(i.get("composition") or []) == 2}
    STATIC_FILE.write_text(json.dumps(static))
    return static


def _placeholders(static: dict, comp_traits: dict[str, int], core_names: set[str]) -> list[dict]:
    """Cheap units outside the final board that share the comp's traits: early stand-ins."""
    out = []
    for u in static["units"].values():
        shared = [t for t in u["traits"] if t in comp_traits]
        if shared and u["cost"] <= PLACEHOLDER_MAX_COST and u["name"] not in core_names:
            out.append({"name": u["name"], "cost": u["cost"], "shares": shared,
                        "front": any(t in SET_DATA["frontline_traits"] for t in u["traits"]),
                        "score": sum(comp_traits[t] for t in shared)})
    out.sort(key=lambda u: (-u["score"], u["cost"], u["name"]))
    return out[:PLACEHOLDERS_KEPT]


def _is_front(unit_traits: list[str], item_counts: Counter) -> bool:
    """Front row if the unit is mostly given tank items, else if it has a frontline trait."""
    full = {i: k for i, k in item_counts.items() if "Component" not in i and "Emblem" not in i}
    if sum(full.values()) >= MIN_ITEM_SAMPLES:
        tank = sum(k for i, k in full.items() if any(t in i for t in SET_DATA["tank_items"]))
        return tank / sum(full.values()) >= 0.5
    return any(t in SET_DATA["frontline_traits"] for t in unit_traits)


def build():
    matches = [json.loads(f.read_text())["info"] for f in MATCH_DIR.glob("*.json")]
    current_set = max(m["tft_set_number"] for m in matches)
    matches = [m for m in matches if m["tft_set_number"] == current_set and m["queue_id"] == RANKED_QUEUE]
    static = load_static(current_set)
    unit_info = lambda cid: static["units"].get(cid, {})
    trait_name = lambda t: static["traits"].get(t) or display(t)
    boards = defaultdict(list)
    for m in matches:
        for p in m["participants"]:
            active = [t for t in p["traits"] if t["tier_current"] > 0 and t["tier_total"] > 1]
            active.sort(key=lambda t: (-t["style"], -t["num_units"], t["name"]))
            if len(active) >= 2:
                boards[tuple(sorted(t["name"] for t in active[:2]))].append(p)

    total = sum(len(b) for b in boards.values())
    comps = []
    for key, plays in boards.items():
        n = len(plays)
        if n < MIN_GAMES:
            continue
        seen, stars, three, costs, items = Counter(), Counter(), Counter(), {}, defaultdict(Counter)
        trait_counts = defaultdict(list)
        for p in plays:
            for cid in {u["character_id"] for u in p["units"]}:
                seen[cid] += 1
            for u in p["units"]:
                cid = u["character_id"]
                stars[cid] += u["tier"]
                three[cid] += u["tier"] >= 3
                costs[cid] = RARITY_TO_COST.get(u["rarity"], u["rarity"] + 1)
                items[cid].update(u.get("itemNames", []))
            for t in p["traits"]:
                if t["tier_current"] > 0 and "Unique" not in t["name"]:
                    trait_counts[t["name"]].append(t["num_units"])
        units = [{
            "name": unit_info(cid).get("name") or display(cid),
            "cost": unit_info(cid).get("cost") or costs[cid],
            "freq": round(c / n, 2),
            "three_star_rate": round(three[cid] / c, 2),
            "front": _is_front(unit_info(cid).get("traits", []), items[cid]),
            "item_avg": round(sum(items[cid].values()) / c, 1),
            "items": [static["items"].get(i) or display(i) for i, k in items[cid].most_common(3) if k >= c * 0.25],
        } for cid, c in seen.most_common() if c / n >= CORE_UNIT_FREQ]
        comp_traits = {trait_name(t): round(statistics.median(v)) for t, v in trait_counts.items() if len(v) >= n * 0.5}
        comps.append({
            "name": " + ".join(trait_name(t) for t in key),
            "games": n,
            "play_rate": round(n / total, 3),
            "avg_place": round(statistics.mean(p["placement"] for p in plays), 2),
            "top4": round(sum(p["placement"] <= 4 for p in plays) / n, 2),
            "level": round(statistics.median(p["level"] for p in plays)),
            "strategy": _strategy(units),
            "traits": comp_traits,
            "units": units,
            "early": _placeholders(static, comp_traits, {u["name"] for u in units if u["freq"] >= 0.4}),
        })
    comps.sort(key=lambda c: c["avg_place"])
    META_FILE.write_text(json.dumps({
        "set": current_set, "platform": PLATFORM, "matches": len(matches), "boards": total,
        "built": time.strftime("%Y-%m-%d %H:%M"), "comps": comps,
    }, indent=1))
    print(f"set {current_set}: {len(matches)} matches, {total} boards, {len(comps)} comps -> {META_FILE}")


if __name__ == "__main__":
    if "--no-fetch" not in sys.argv:
        fetch()
    build()
