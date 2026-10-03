import assert from "node:assert/strict";
import { test } from "node:test";

import * as comps from "../src/comps.js";

const INFERNO = { name: "Adaptor + Inferno", avg_place: 4.8, level: 8, traits: { Inferno: 2, Rapidfire: 2, Lunar: 2 },
                  units: [{ name: "Varus" }, { name: "Kog Maw" }, { name: "Rek Sai" }] };
const STRONG = { name: "Executioner + Summoner", avg_place: 3.1, traits: { Executioner: 4, Summoner: 3 },
                 units: [{ name: "Zyra" }] };
const META = { comps: [STRONG, INFERNO] };

const top = (...args) => comps.rank(META, ...args)[0].comp.name;

test("fitting comp beats stronger comp", () => {
  assert.equal(top({ Inferno: 2, Rapidfire: 2, Fae: 1 }), "Adaptor + Inferno");
});

test("no traits falls back to placement", () => {
  assert.equal(top({}), "Executioner + Summoner");
});

test("contested comp drops", () => {
  const scouted = { a: { Inferno: 2, Rapidfire: 2, Lunar: 2 }, b: { Inferno: 2, Lunar: 2 }, c: { Fae: 1 } };
  const contenders = comps.findContenders(META, scouted);
  assert.deepEqual(contenders, { "Adaptor + Inferno": ["a", "b"] });
  const mine = { Inferno: 2, Rapidfire: 1, Executioner: 2 };
  assert.equal(top(mine), "Adaptor + Inferno");
  assert.equal(top(mine, { contenders }), "Executioner + Summoner");
});

test("units held by opponents lower a comp", () => {
  const mine = { Inferno: 2, Rapidfire: 1, Executioner: 2 };
  const taken = { Varus: 4, "Kog Maw": 3, Zyra: 0 };
  assert.equal(comps.unitContest(INFERNO, taken), 7);
  assert.equal(top(mine, { taken }), "Executioner + Summoner");
});

test("spare emblem shifts ranking", () => {
  const mine = { Inferno: 1, Executioner: 2 };
  assert.equal(top(mine), "Executioner + Summoner");
  const boosted = comps.withEmblems(mine, ["Inferno", "Lunar"]);
  assert.deepEqual(boosted, { Inferno: 2, Executioner: 2, Lunar: 1 });
  assert.equal(top(boosted), "Adaptor + Inferno");
  assert.deepEqual(mine, { Inferno: 1, Executioner: 2 });
});

test("emblem outweighs a plain unit", () => {
  const mine = { Executioner: 1, Fae: 2 };
  // One more Inferno unit is not enough to pivot, an Inferno emblem is.
  assert.equal(top({ ...mine, Inferno: 1 }), "Executioner + Summoner");
  assert.equal(top(mine, { emblems: ["Inferno"] }), "Adaptor + Inferno");
  assert.equal(comps.emblemBonus(INFERNO, ["Inferno", "Lunar", "Fae"]), comps.EMBLEM_BONUS_MAIN + comps.EMBLEM_BONUS_SIDE);
});

test("traits count copies once and equipped emblems on top", () => {
  const varus = { name: "Varus", traits: ["Inferno", "Rapidfire"], emblems: [] };
  assert.deepEqual(comps.traitsOf([varus, varus, { name: "Zyra", traits: ["Inferno"], emblems: ["Lunar"] }]),
                   { Inferno: 2, Rapidfire: 1, Lunar: 1 });
});

test("board by level", () => {
  const unit = (name, cost, freq, front, avg) => ({ name, cost, freq, front, item_avg: avg, items: ["x"] });
  const comp = { level: 4, units: [unit("Carry", 4, 1.0, false, 2.8), unit("Tank", 4, 0.9, true, 2.5),
                                   unit("Cheap", 1, 0.8, true, 0.1), unit("Mid", 2, 0.7, false, 0.5),
                                   unit("Flex", 1, 0.5, false, 0.0)] };
  assert.deepEqual(comps.board(comp, 2), [["Cheap"], ["Mid"]]);
  assert.deepEqual(comps.board(comp, 4), [["Tank", "Cheap"], ["Carry", "Mid"]]);
  assert.deepEqual(comps.board(comp, 5), [["Tank", "Cheap"], ["Carry", "Mid", "Flex"]]);
  assert.deepEqual(comps.itemHolders(comp).map(([label, u]) => [label, u.name]), [["Carry", "Carry"], ["Tank", "Tank"]]);
});

test("extra slot adds a unit", () => {
  const unit = (name, cost, freq) => ({ name, cost, freq, front: false });
  const comp = { level: 3, traits: {}, early: [unit("Standin", 1, 0)],
                 units: [unit("A", 1, 1.0), unit("B", 1, 0.9), unit("C", 2, 0.8), unit("D", 2, 0.7)] };
  assert.deepEqual(comps.board(comp, 3), [[], ["A", "B", "C"]]);
  assert.deepEqual(comps.board(comp, 3, 4), [[], ["A", "B", "C", "D"]]); // final level: next comp unit
  assert.deepEqual(comps.board(comp, 2, 3), [[], ["A", "B", "C"]]); // early: 3 slots at level 2
  const owned = new Map([["A", "board"], ["B", "board"], ["C", "board"], ["D", "bench"]]);
  assert.deepEqual(comps.planBoard(comp, 3, owned)[0].map((u) => u.name), ["A", "B", "C"]);
  assert.deepEqual(comps.planBoard(comp, 3, owned, 4)[0].map((u) => u.name), ["A", "B", "C", "D"]);
});

test("placeholders fill early board", () => {
  const unit = (name, cost, freq, front) => ({ name, cost, freq, front });
  const comp = { level: 8, units: [unit("Carry", 4, 1.0, false), unit("Tank", 4, 0.9, true), unit("Cheap", 1, 0.8, true)],
                 early: [unit("Standin", 1, 0, false), unit("Pricey", 3, 0, true)] };
  assert.deepEqual(comps.board(comp, 3), [["Cheap"], ["Standin*"]]); // 3-cost and 4-costs not fieldable at level 3
  assert.deepEqual(comps.shopPicks(["Standin", "Carry", "Pricey", null, "Other"], comp, 3),
                   [[1, "Standin* placeholder"], [2, "Carry"]]);
  assert.deepEqual(comps.shopPicks(["Standin", "Carry"], comp, 8), [[2, "Carry"]]);
});
