/** Per-game state, fed by Overwolf's TFT game events, and the view the window shows. */
import { advise } from "./advisor.js";
import * as comps from "./comps.js";
import { parseStage, stageReached } from "./econ.js";
import { data, emblemTrait, unit } from "./store.js";

const SHOWN_COMPS = 3;
const COPIES = { 1: 1, 2: 3, 3: 9 }; // copies of a unit merged into each star level

/** Info values arrive as strings, objects among them as JSON. */
function parse(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

/** Playable units out of a board or bench payload ({cell_1: {name, level, item_1..3}, ...}). */
function pieces(cells) {
  return Object.values(cells ?? {}).flatMap((cell) => {
    const u = unit(cell?.name);
    if (!u) return [];
    const emblems = [cell.item_1, cell.item_2, cell.item_3].filter(Boolean).map(emblemTrait).filter(Boolean);
    return [{ name: u.name, traits: u.traits, star: Number(cell.level) || 1, emblems }];
  });
}

export class Session {
  constructor() {
    this.game = 0; // goes up each time a new game is detected
    this.me = null; // summoner name
    this.stage = null;
    this.roundType = null;
    this.level = null;
    this.xp = 0;
    this.gold = null;
    this.hp = 100;
    this.board = [];
    this.bench = [];
    this.shop = [];
    this.emblems = []; // traits of the emblems on your item bench
    this.over = false;
    this.reset();
  }

  /** Forgets what was remembered about the game. Gold, level, board and so on are overwritten by the next events. */
  reset() {
    this.game += 1;
    this.seenStage = [0, 0];
    this.streak = 0; // positive = win streak, negative = loss streak
    this.outcomeStage = null; // stage of the last result counted: the same result can be delivered twice
    this.opponent = null;
    this.unclaimed = null; // opponent board that arrived before the opponent's name
    this.scouted = {}; // player -> {stage seen, traits, units}
    this.locked = null;
  }

  /** Takes an info update or a getInfo result: {category: {key: value}}. */
  applyInfo(info) {
    for (const values of Object.values(info ?? {})) {
      if (!values || typeof values !== "object") continue;
      for (const [key, raw] of Object.entries(values)) this.set(key, parse(raw));
    }
  }

  set(key, value) {
    switch (key) {
      case "summoner_name":
        this.me = String(value);
        break;
      case "gold":
        this.gold = Number(value);
        break;
      case "health":
        this.hp = Number(value);
        break;
      case "xp":
        this.level = value.level;
        this.xp = value.current_xp;
        break;
      case "match_state":
        this.over = value.in_progress === false;
        break;
      case "round_type": {
        const stage = parseStage(value.stage);
        if (stage[0] === 1 && stageReached(this.seenStage, [2, 1])) this.reset(); // new game
        this.seenStage = stage;
        this.stage = value.stage;
        this.roundType = value.type;
        this.opponent = this.unclaimed = null;
        break;
      }
      case "board_pieces":
        this.board = pieces(value);
        break;
      case "bench_pieces":
        this.bench = pieces(value);
        break;
      case "shop_pieces":
        this.shop = [1, 2, 3, 4, 5].map((slot) => unit(value[`slot_${slot}`]?.name)?.name ?? null);
        break;
      case "item_bench": {
        const mine = Array.isArray(value) ? value.find((entry) => entry.summoner === this.me) : null;
        if (mine) {
          this.emblems = mine.bench_items.flatMap((item) => Array(item.count ?? 1).fill(emblemTrait(item.name)))
            .filter(Boolean);
        }
        break;
      }
      case "opponent":
        this.opponent = value.name;
        if (this.unclaimed) this.scout(this.unclaimed);
        break;
      case "opponent_board_pieces":
        this.scout(pieces(value));
        break;
      case "round_outcome": {
        const outcome = value?.[this.me]?.outcome;
        if (this.roundType !== "PVP" || this.outcomeStage === this.stage) break; // minion rounds don't touch streaks
        if (outcome === "victory" || outcome === "defeat") this.outcomeStage = this.stage;
        if (outcome === "victory") this.streak = Math.max(this.streak, 0) + 1;
        else if (outcome === "defeat") this.streak = Math.min(this.streak, 0) - 1;
        break;
      }
    }
  }

  /** Records the board you are fighting under its owner's name, once both are known. */
  scout(units) {
    if (!units.length) return;
    if (!this.opponent) {
      this.unclaimed = units;
      return;
    }
    this.unclaimed = null;
    this.scouted[this.opponent] = { stage: this.stage, traits: comps.traitsOf(units),
                                    units: [...new Set(units.map((u) => u.name))] };
  }

  /**
   * Everything the window shows, as an object of sections.
   *
   * `extraSlots` is board space beyond your level (Tactician's Cape/Crown, augments).
   */
  view({ strategy = "auto", hit = false, lock = false, extraSlots = 0 } = {}) {
    if (this.over || !this.stage || this.level === null || this.gold === null) {
      return { waiting: "Waiting for a TFT game..." };
    }
    const meta = data.meta;
    const taken = {}; // unit -> opponents fielding it
    for (const seen of Object.values(this.scouted)) {
      for (const name of seen.units) taken[name] = (taken[name] ?? 0) + 1;
    }
    let contenders = {};
    let ranked = [];
    if (meta) {
      const scouted = Object.fromEntries(Object.entries(this.scouted).map(([player, seen]) => [player, seen.traits]));
      contenders = comps.findContenders(meta, scouted);
      ranked = comps.rank(meta, comps.traitsOf(this.board), { contenders, emblems: this.emblems, taken });
    }
    if (lock && ranked.length) {
      this.locked ??= ranked[0].comp.name;
      ranked.sort((a, b) => (a.comp.name !== this.locked) - (b.comp.name !== this.locked)); // stable: locked comp first
    } else {
      this.locked = null;
    }
    if (strategy === "auto") strategy = ranked[0]?.comp.strategy ?? "standard";

    const size = Math.max(this.level + extraSlots, this.board.length);
    const copies = {}; // unit -> copies you hold, counting the ones merged into stars
    for (const u of [...this.board, ...this.bench]) copies[u.name] = (copies[u.name] ?? 0) + (COPIES[u.star] ?? 1);
    const view = {
      status: `Stage ${this.stage}   ·   Level ${this.level} (${this.xp} xp)   ·   ${this.gold} gold   ·   ` +
              `${this.hp} HP   ·   ${strategy}` + (size !== this.level ? `   ·   ${size} board slots` : ""),
      note: this.emblems.length ? `Spare emblems counted: ${this.emblems.join(", ")}.` : "",
      advice: advise({ stage: this.stage, level: this.level, xp: this.xp, gold: this.gold, hp: this.hp,
                       streak: this.streak, strategy, hit }),
      board: this.board.map(({ name, star }) => ({ name, star })),
      bench: this.bench.map(({ name, star }) => ({ name, star })),
      field: [], find: [], buy: [], items: [], components: [], comps: [],
      scouted: Object.entries(this.scouted).map(([player, seen]) => `${player} (${seen.stage})`),
      taken,
    };
    if (!ranked.length) {
      view.comps = ["No meta data: the download failed and there is no saved copy."];
      return view;
    }

    const target = ranked[0].comp;
    const owned = new Map(this.board.map((u) => [u.name, "board"]));
    for (const u of this.bench) if (!owned.has(u.name)) owned.set(u.name, "bench");
    this.shop.forEach((name, i) => {
      if (name && !owned.has(name)) owned.set(name, `shop ${i + 1}`);
    });
    [view.field, view.find] = comps.planBoard(target, this.level, owned, size);
    view.buy = comps.shopPicks(this.shop, target, this.level, size)
      .map(([slot, name]) => ({ name, slot, copies: copies[name.split("*")[0]] ?? 0 }));
    [view.items, view.components] = comps.itemPlan(target);
    view.target = target.name;
    const percent = (share) => `${Math.round(share * 100)}%`;
    view.comps = ranked.slice(0, SHOWN_COMPS).map(({ fit, comp }, i) => {
      const rivals = contenders[comp.name];
      const held = comps.unitContest(comp, taken);
      return `${i + 1}. ${comp.name}  ·  avg place ${comp.avg_place}  ·  top 4 ${percent(comp.top4)}  ·  ` +
             `fit ${percent(fit)}  ·  ${comp.strategy}, level ${comp.level}` +
             (rivals ? `  ·  CONTESTED by ${rivals.join(", ")}` : "") +
             (held ? `  ·  its units seen on opponents ${held}×` : "");
    });
    return view;
  }
}
