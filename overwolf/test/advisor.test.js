import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { advise } from "../src/advisor.js";
import * as econ from "../src/econ.js";
import { setData } from "../src/store.js";

setData({ set: JSON.parse(readFileSync(new URL("../../data/set_data.json", import.meta.url))) });

const actions = (state) => advise(state).map((a) => a.action);

test("interest", () => {
  assert.deepEqual([9, 10, 49, 50, 80].map(econ.interest), [0, 1, 4, 5, 5]);
});

test("gold to next interest", () => {
  assert.equal(econ.goldToNextInterest(48), 2);
  assert.equal(econ.goldToNextInterest(60), 0);
});

test("cost to level", () => {
  assert.equal(econ.costToLevel(7, 20), 28); // 28 xp missing -> 7 buys
  assert.equal(econ.costToLevel(7, 46), 4);
  assert.equal(econ.costToLevel(10, 0), null);
});

test("levels on tempo", () => {
  assert.ok(actions({ stage: "2-1", level: 3, xp: 2, gold: 6 }).includes("LEVEL"));
});

test("saves before tempo", () => {
  const a = actions({ stage: "3-1", level: 5, xp: 0, gold: 30 });
  assert.ok(!a.includes("LEVEL"));
  assert.ok(a.includes("SAVE"));
});

test("levels early when rich", () => {
  assert.ok(actions({ stage: "3-5", level: 6, xp: 30, gold: 60 }).includes("LEVEL"));
});

test("roll at eight", () => {
  assert.ok(actions({ stage: "4-5", level: 8, xp: 0, gold: 50 }).includes("ROLL"));
});

test("slow roll holds level", () => {
  const a = actions({ stage: "3-3", level: 6, xp: 0, gold: 58, strategy: "reroll2" });
  assert.equal(a[0], "ROLL");
  assert.ok(!a.includes("LEVEL"));
});

test("danger rolls", () => {
  assert.ok(actions({ stage: "4-2", level: 7, xp: 0, gold: 40, hp: 25 }).includes("ROLL"));
});
