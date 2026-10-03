/** Gold and XP maths. All set-specific numbers come from data/set_data.json. */
import { data } from "./store.js";

export function parseStage(stage) {
  const [a, b] = stage.split("-").map(Number);
  return [a, b];
}

/** True once `stage` is at or past `target`, both as [stage, round]. */
export function stageReached(stage, target) {
  return stage[0] > target[0] || (stage[0] === target[0] && stage[1] >= target[1]);
}

export function interest(gold) {
  return Math.min(Math.floor(gold / data.set.interest_per), data.set.interest_cap);
}

/** `streak` is the length of the current win OR loss streak. */
export function streakGold(streak) {
  for (const [length, bonus] of data.set.streak_gold) {
    if (Math.abs(streak) >= length) return bonus;
  }
  return 0;
}

/** Gold gained at the start of next round, excluding the +1 for a win. */
export function income(gold, streak = 0) {
  return data.set.base_income + interest(gold) + streakGold(streak);
}

/** Gold missing to reach the next interest breakpoint (0 if already capped). */
export function goldToNextInterest(gold) {
  if (interest(gold) >= data.set.interest_cap) return 0;
  return data.set.interest_per - (gold % data.set.interest_per);
}

/** Gold needed to reach the next level, or null at max level. */
export function costToLevel(level, xp) {
  if (level >= data.set.max_level) return null;
  const missing = data.set.xp_to_next_level[level] - xp;
  const buys = Math.ceil(Math.max(missing, 0) / data.set.xp_per_buy);
  return buys * data.set.xp_buy_cost;
}
