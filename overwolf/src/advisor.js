/** Turns a game state into econ / level / reroll advice. */
import * as econ from "./econ.js";
import { parseStage, stageReached } from "./econ.js";
import { data } from "./store.js";

// Strategy -> level you sit on while slow-rolling for 3-stars (null = level normally).
export const HOLD_LEVEL = { standard: null, reroll1: 5, reroll2: 6, reroll3: 7 };

function inDanger(s) {
  const stage = parseStage(s.stage);
  return (stageReached(stage, [3, 5]) && s.hp <= 30) || (stageReached(stage, [4, 1]) && s.hp <= 40);
}

/**
 * `s` is {stage: "3-2", level, xp, gold, hp, streak, strategy, hit}. streak is positive for wins and
 * negative for losses; hit is true once a reroll strategy's 3-stars are done.
 * Returns [{action: LEVEL | ROLL | SAVE | INFO, text}].
 */
export function advise({ stage: stageText, level, xp, gold, hp = 100, streak = 0, strategy = "standard", hit = false }) {
  const out = [];
  const say = (action, text) => out.push({ action, text });
  const set = data.set;
  const econCap = set.interest_per * set.interest_cap;
  const stage = parseStage(stageText);
  const hold = hit ? null : HOLD_LEVEL[strategy];
  const danger = inDanger({ stage: stageText, hp });

  // --- levelling ---
  const cost = econ.costToLevel(level, xp);
  if (cost !== null && (hold === null || level < hold)) {
    const nxt = level + 1;
    const tempo = set.level_tempo[nxt];
    const onTempo = tempo !== undefined && stageReached(stage, parseStage(tempo));
    if (cost <= gold && onTempo) {
      say("LEVEL", `Level to ${nxt} (${cost}g). Standard timing for ${nxt} is ${tempo}.`);
      gold -= cost;
    } else if (gold - cost >= econCap) {
      say("LEVEL", `Level to ${nxt} (${cost}g): you stay at ${econCap}+ gold, so it costs no interest.`);
      gold -= cost;
    } else if (onTempo) {
      say("INFO", `Behind tempo for level ${nxt} (${tempo}); need ${cost}g, have ${gold}g.`);
    }
  }

  // --- rolling ---
  if (danger) {
    say("ROLL", `HP ${hp}: roll down now to stabilise your board. Surviving beats interest.`);
  } else if (hold !== null && level === hold) {
    const spare = Math.floor((gold - econCap) / set.reroll_cost);
    if (spare > 0) say("ROLL", `Slow-roll: ${spare} reroll(s), stay at ${econCap}g.`);
    else say("SAVE", `Slow-roll level ${hold}: econ to ${econCap}g before rolling.`);
  } else if (hold === null && level === 8 && stageReached(stage, [4, 2])) {
    if (gold >= 30) say("ROLL", "Level 8: roll for your 4-cost carries. Stop around 10-20g or once the board is upgraded.");
    else say("SAVE", "Level 8 but low gold: rebuild econ unless you are losing hard.");
  } else if (hold === null && level >= 9) {
    const spare = Math.floor((gold - 30) / set.reroll_cost);
    if (spare > 0) say("ROLL", `Level ${level}: ${spare} reroll(s) for 5-costs, keep ~30g.`);
  } else {
    say("SAVE", "Don't roll: your level's shop odds aren't worth it yet.");
  }

  // --- interest ---
  if (!danger) {
    const missing = econ.goldToNextInterest(gold);
    if (missing > 0 && missing <= 3) {
      say("INFO", `${missing}g short of ${gold + missing}g interest: sell a bench unit or skip a buy.`);
    }
    say("INFO", `Next round income: +${econ.income(gold, streak)}g (interest ${econ.interest(gold)}, ` +
                `streak ${econ.streakGold(streak)}).`);
  }
  return out;
}
