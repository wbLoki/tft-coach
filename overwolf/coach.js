/** The coach window: feeds the game updates sent by main.js to the session and draws its view. */
import { loadData } from "./src/remote.js";
import { Session } from "./src/session.js";
import { data, setData } from "./src/store.js";

setData(await loadData()); // before any event can ask for a view
const session = new Session();
const controls = document.getElementById("controls");
let problem = ""; // why the game can't be read, if main.js reported one

const esc = (text) => String(text).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const span = (text, cls = "") => (cls ? `<span class="${cls}">${esc(text)}</span>` : esc(text));
const stars = (unit) => unit.name + (unit.star > 1 ? " " + "★".repeat(unit.star) : "");

function options() {
  const form = new FormData(controls);
  return { strategy: form.get("strategy"), hit: form.has("hit"), lock: form.has("lock"),
           extraSlots: Number(form.get("extraSlots")) };
}

function render() {
  const view = data.set ? session.view(options())
    : { waiting: "Couldn't download the game data. Check your connection, then reopen the app." };
  const fill = (id, html) => {
    const element = document.getElementById(id);
    if (element.innerHTML !== html) element.innerHTML = html;
  };
  if (view.waiting) {
    fill("status", esc(view.waiting));
    fill("note", esc(problem));
    for (const id of ["advice", "board", "bench", "field", "find", "items", "comps"]) fill(id, "");
    return;
  }
  fill("status", esc(view.status));
  fill("note", esc(view.note));
  fill("advice", view.advice.map((a) => span(a.action + "  ", a.action) + esc(a.text)).join("\n"));
  fill("board", view.board.length ? esc(view.board.map(stars).join(", ")) : span("Empty.", "muted"));
  fill("bench", view.bench.length ? esc(view.bench.map(stars).join(", ")) : span("Empty.", "muted"));

  let html = view.target ? span(`For ${view.target}\n`, "muted") : "";
  for (const [label, front] of [["Front   ", true], ["Back    ", false]]) {
    const row = view.field.filter((u) => u.front === front);
    html += span(label, "muted") + row.map((u) => {
      const where = { board: "", bench: " (from bench)" }[u.where] ?? ` (buy, ${u.where})`;
      const kind = { comp: "", placeholder: " placeholder", "off-comp": " off-comp, replace later" }[u.kind];
      const cls = u.where.startsWith("shop") ? "shop" : u.where === "bench" ? "bench"
        : u.kind === "off-comp" ? "off-comp" : "bold";
      return span(u.name, cls) + span(where + (kind && where ? "," : "") + kind, "muted");
    }).join(span(",  ", "muted")) + (row.length ? "\n" : span("-\n", "muted"));
  }
  fill("field", view.field.length ? html : span("Nothing to suggest yet.", "muted"));

  const held = (name) => view.taken[name.split("*")[0]] ?? 0;
  html = span("Missing   ", "muted") + (view.find.map((name) =>
    esc(name) + (held(name) ? span(` (${held(name)} opp.)`, held(name) >= 2 ? "warn" : "muted") : "")).join(", ")
    || "nothing for this level") + "\n" + span("In shop   ", "muted");
  html += view.buy.map(({ name, slot, copies }) => {
    const extra = [`slot ${slot}`, ...(copies ? [`${copies} owned`] : []),
                   ...(held(name) ? [`${held(name)} opp. have it`] : [])];
    return span(name, "shop") + span(` (${extra.join(", ")})`, "muted");
  }).join("\n          ") || span("nothing worth buying", "muted");
  fill("find", html);

  html = view.items.map(([role, name, items]) => span(`${role} ${name}\n`, "bold") + esc("  " + items.join(", "))).join("\n");
  if (view.components.length) {
    html += "\n" + span("Components to collect\n", "bold") +
            esc("  " + view.components.map(([c, k]) => (k === 1 ? c : `${k}× ${c}`)).join(", "));
  }
  fill("items", html);

  fill("comps", view.comps.map((line, i) => span(line, i ? "muted" : "")).join("\n") + "\n" +
       span("Scouted: " + (view.scouted.join(", ") || "nobody yet (recorded as you fight them)"), "muted"));
}

function resetControls() {
  for (const name of ["hit", "lock"]) controls.elements[name].checked = false;
  controls.elements.extraSlots.value = "0";
}

window.game.onInfo((info) => {
  const game = session.game;
  session.applyInfo(info); // a value can arrive twice: as an update, and in the state sent on "ready"
  if (session.game !== game) resetControls(); // new game: clear per-game ticks
  render();
});
window.game.onEvent((name) => {
  if (name !== "match_start") return;
  session.reset();
  resetControls();
  render();
});
window.game.onProblem((text) => {
  problem = text;
  render();
});
controls.addEventListener("change", render);

render();
window.game.ready();
