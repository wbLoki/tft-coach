"""Live coach: watches the primary monitor and shows advice in an always-on-top window.

Run: .venv\\Scripts\\python -m tft_coach.live
"""
import threading
import time
import tkinter as tk
from collections import Counter
from dataclasses import replace

import mss
from PIL import Image

from . import comps, meta
from .advisor import HOLD_LEVEL, GameState, advise
from .econ import parse_stage
from .reader import is_augment_choice, read_players, read_shop, read_state, read_traits

POLL_SECONDS = 1.0
SLOW_EVERY = 8  # HP and traits are slow to read and only change now and then
SHOWN_COMPS = 3

BG, PANEL, FG, MUTED = "#101a17", "#1b2925", "#e8dfc4", "#8fa097"
COLORS = {"LEVEL": "#7bd389", "ROLL": "#f0a04b", "SAVE": "#6fb3e0", "INFO": MUTED,
          "bench": "#6fb3e0", "shop": "#7bd389", "off-comp": "#e36d6d", "muted": MUTED, "warn": "#f0a04b"}


class Session:
    """Everything remembered between frames of one game."""

    def __init__(self, meta: dict | None):
        self.meta = meta
        self.n = 0
        self.game = 0  # goes up each time a new game is detected
        self.reset()

    def reset(self):
        self.game += 1
        self.n = 0  # so the next frame re-reads HP and traits straight away
        self.hp = 100
        self.seen_stage = (0, 0)
        self.last: GameState | None = None  # last state read with the HUD visible
        self.traits: dict[str, int] = {}
        self.scouted: dict[str, dict] = {}  # player -> {stage seen, traits, units worked out from traits}
        self.locked: str | None = None
        self.bought: Counter[str] = Counter()  # unit -> copies seen bought from the shop (minus detected sells)
        self.prev: tuple[str, int, list[str | None]] | None = None  # (stage, gold, shop) of the last HUD frame
        self.shop: list[str | None] = []
        self.board_prev: list[str] = []  # last board worked out unambiguously
        self.sales: list[int] = []  # unexplained mid-round gold gains since then

    def track_purchases(self, stage: str, gold: int, shop: list[str | None], on_board: list[str]):
        """Bench units have no text to read, so follow them through the shop instead:
        a card that disappears while gold drops by exactly its cost was bought."""
        units = [comps.resolve_unit(name) for name in shop]
        names = [u["name"] if u else None for u in units]
        if self.prev and self.prev[0] == stage:
            _, prev_gold, prev_names = self.prev
            gone = [i for i in range(len(names)) if prev_names[i] and not names[i]]
            rest_same = all(prev_names[i] == names[i] for i in range(len(names)) if i not in gone)
            costs = {u["name"]: u["cost"] for u in comps.playable_units()}
            if gone and rest_same and prev_gold - gold == sum(costs[prev_names[i]] for i in gone):
                self.bought.update(prev_names[i] for i in gone)
            elif names == prev_names and gold > prev_gold:
                # Gold went up mid-round with the shop untouched: a sale. Only act if it's unambiguous.
                sold = [n for n, k in self.bought.items() if k > 0 and n not in on_board and costs[n] == gold - prev_gold]
                if len(sold) == 1:
                    self.bought[sold[0]] -= 1
                else:
                    self.sales.append(gold - prev_gold)  # maybe a board unit: settled in track_board
        self.prev = (stage, gold, names)
        self.shop = names

    def track_board(self, board: list[str]):
        """A unit that left the board was either sold (gold went up by its sale price) or
        moved to the bench. Call only with boards that were worked out unambiguously."""
        costs = {u["name"]: u["cost"] for u in comps.playable_units()}
        for name in self.board_prev:
            if name in board:
                continue
            cost = costs.get(name, 0)
            prices = {cost, 3 if cost == 1 else 3 * cost - 1}  # one-star and two-star sale price
            paid = next((g for g in self.sales if g in prices), None)
            if paid is not None:
                self.sales.remove(paid)
                self.bought[name] = 0
            else:
                self.bought[name] = max(self.bought[name], 1)  # benched
        self.board_prev = board
        self.sales.clear()

    def step(self, img: Image.Image, strategy: str = "auto", hit: bool = False, lock: bool = False,
             emblems: list[str] = (), extra_slots: int = 0) -> dict:
        """Reads one frame and returns everything the window shows, as a dict of sections.

        `extra_slots` is board space beyond your level (Tactician's Cape/Crown, augments).
        """
        s = read_state(img)
        stage = s["stage"]
        hud = None not in (stage, s["level"], s["gold"])
        if stage and stage.startswith("1-") and self.seen_stage >= (2, 1):
            self.reset()  # new game
        if stage:
            self.seen_stage = parse_stage(stage)
        note = ""
        fresh_traits = False
        if hud:
            # Own board: the trait panel shows your traits.
            if self.n % SLOW_EVERY == 0:
                self.hp = read_players(img)[0] or self.hp
                self.traits = read_traits(img) or self.traits
                fresh_traits = True
        elif stage and is_augment_choice(img):
            note = "Augment selection: gold and level can't be read, showing the last values seen."
        elif stage:
            # Bottom HUD gone: when scouting, the trait panel is the opponent's.
            own_hp, viewed = read_players(img)
            self.hp = own_hp or self.hp
            if viewed:
                traits = read_traits(img)
                self.scouted[viewed] = {"stage": stage, "traits": traits, "units": comps.certain_units(traits)}
                note = f"Scouting {viewed}: recorded. Showing your last values."
            else:
                note = "HUD hidden: showing the last values seen."
        self.n += 1

        contenders, ranked = {}, []
        taken = Counter(u for seen in self.scouted.values() for u in seen["units"])  # unit -> opponents fielding it
        if self.meta:
            contenders = comps.find_contenders(self.meta, {p: seen["traits"] for p, seen in self.scouted.items()})
            ranked = comps.rank(self.meta, self.traits, contenders, emblems, taken)
            if lock:
                self.locked = self.locked or ranked[0][1]["name"]
                ranked.sort(key=lambda fc: fc[1]["name"] != self.locked)  # stable: locked comp first
            else:
                self.locked = None
        if strategy == "auto":
            strategy = ranked[0][1]["strategy"] if ranked else "standard"

        if hud:
            self.last = GameState(stage=stage, level=s["level"], xp=s["xp"] or 0, gold=s["gold"], hp=self.hp,
                                  streak=s["streak"] or 0)
        if self.last is None:
            return {"waiting": "Waiting for a game...  (gold / level bar not visible)"}
        state = replace(self.last, stage=stage or self.last.stage, hp=self.hp, strategy=strategy, hit=hit)

        # One spare slot in the search, so an extra slot you haven't told the app about still shows up.
        guesses = comps.infer_board(self.traits, state.level + extra_slots + 1)
        board = [n for n in guesses[0] if all(n in g for g in guesses)] if guesses else []
        size = max(state.level + extra_slots, len(board))
        if hud:
            self.track_purchases(stage, s["gold"], read_shop(img), board)
        if fresh_traits and len(guesses) == 1:
            self.track_board(board)
        shop = self.shop if hud else [None] * 5
        bench = {n: k for n, k in self.bought.items() if k > 0 and n not in board}

        view = {
            "status": f"Stage {state.stage}   ·   Level {state.level} ({state.xp} xp)   ·   {state.gold} gold   ·   "
                      f"{state.hp} HP   ·   {strategy}" + (f"   ·   {size} board slots" if size != state.level else ""),
            "note": note + (f"  Spare emblems counted: {', '.join(emblems)}." if emblems else ""),
            "advice": [(a.action, a.text) for a in advise(state)],
            "board": board, "board_guesses": len(guesses), "bench": bench,
            "field": [], "find": [], "buy": [], "items": [], "components": [], "comps": [],
            "scouted": [f"{p} ({seen['stage']}" + ("" if seen["units"] else ", units unclear") + ")"
                        for p, seen in self.scouted.items()],
            "taken": dict(taken),
        }
        if not ranked:
            view["comps"] = ["No meta data yet: run  python -m tft_coach.meta"]
            return view
        target = ranked[0][1]
        owned = {n: "board" for n in board} | {n: "bench" for n in bench}
        for slot, name in enumerate(shop, 1):
            if name and name not in owned:
                owned[name] = f"shop {slot}"
        view["field"], view["find"] = comps.plan_board(target, state.level, owned, size)
        view["buy"] = [(name, slot, self.bought[name.split("*")[0]]) for slot, name in
                       comps.shop_picks(shop, target, state.level, size)]
        view["items"], view["components"] = comps.item_plan(target)
        view["target"] = target["name"]
        for i, (fit, c) in enumerate(ranked[:SHOWN_COMPS], 1):
            rivals = contenders.get(c["name"])
            held = comps.unit_contest(c, taken)
            view["comps"].append(
                f"{i}. {c['name']}  ·  avg place {c['avg_place']}  ·  top 4 {c['top4']:.0%}  ·  fit {fit:.0%}  ·  "
                f"{c['strategy']}, level {c['level']}" + (f"  ·  CONTESTED by {', '.join(rivals)}" if rivals else "")
                + (f"  ·  its units seen on opponents {held}×" if held else ""))
        return view


def to_text(view: dict) -> str:
    """Plain-text version of the window, for debugging."""
    if "waiting" in view:
        return view["waiting"]
    unit = lambda u: u["name"] + {"comp": "", "placeholder": "*", "off-comp": "~"}[u["kind"]] + \
        ("" if u["where"] == "board" else f" [{u['where']}]")
    lines = [view["status"], view["note"], *(f"{a:5} {t}" for a, t in view["advice"]),
             f"ON BOARD: {', '.join(view['board']) or 'unclear'} ({view['board_guesses']} fit)",
             f"ON BENCH: {', '.join(f'{n} x{k}' for n, k in view['bench'].items()) or '-'}",
             f"PUT ON BOARD ({view.get('target')}):",
             "  front: " + ", ".join(unit(u) for u in view["field"] if u["front"]),
             "  back:  " + ", ".join(unit(u) for u in view["field"] if not u["front"]),
             "LOOK FOR: " + (", ".join(f"{n} ({view['taken'][n]} opp.)" if n in view["taken"] else n
                                       for n in view["find"]) or "-"),
             "BUY: " + (", ".join(f"{n} (slot {s}, {k} bought)" for n, s, k in view["buy"]) or "-"),
             *(f"ITEMS {role} {name}: {', '.join(items)}" for role, name, items in view["items"]),
             "COMPONENTS: " + ", ".join(f"{k}x {c}" for c, k in view["components"]),
             *view["comps"], "SCOUTED: " + (", ".join(view["scouted"]) or "nobody")]
    return "\n".join(l for l in lines if l)


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("TFT Coach")
        self.root.attributes("-topmost", True)
        self.root.configure(bg=BG, padx=10, pady=8)
        self.root.columnconfigure((0, 1), weight=1, uniform="half")
        self.strategy = tk.StringVar(value="auto")
        self.hit = tk.BooleanVar(value=False)
        self.lock = tk.BooleanVar(value=False)
        self.session: Session | None = None  # created by the worker thread
        self.view: dict = {}
        self.shown: dict[str, list] = {}  # what each section currently displays

        bar =tk.Frame(self.root, bg=BG)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        style = dict(bg=BG, fg=MUTED, selectcolor=PANEL, activebackground=BG, activeforeground=FG,
                     font=("Segoe UI", 9))
        for name in ("auto", *HOLD_LEVEL):
            tk.Radiobutton(bar, text=name, value=name, variable=self.strategy, **style).pack(side="left")
        tk.Checkbutton(bar, text="3-stars hit", variable=self.hit, **style).pack(side="left", padx=(14, 0))
        tk.Checkbutton(bar, text="lock comp", variable=self.lock, **style).pack(side="left")
        # Spare emblems (on your item bench): each ticked trait counts extra when matching comps.
        self.emblems = {t: tk.BooleanVar(value=False) for t in comps.emblem_traits()}
        picker = tk.Menubutton(bar, text="spare emblems ▾", bg=PANEL, fg=FG, activebackground=PANEL,
                               activeforeground=FG, relief="flat", font=("Segoe UI", 9), padx=8)
        picker.menu = tk.Menu(picker, tearoff=False)
        picker["menu"] = picker.menu
        for trait, var in self.emblems.items():
            picker.menu.add_checkbutton(label=trait, variable=var)
        picker.pack(side="right")
        # Extra board slots beyond your level: Tactician's Cape / Crown, or augments that add team size.
        self.extra_slots = tk.IntVar(value=0)
        slots = tk.Menubutton(bar, text="extra slots ▾", bg=PANEL, fg=FG, activebackground=PANEL,
                              activeforeground=FG, relief="flat", font=("Segoe UI", 9), padx=8)
        slots.menu = tk.Menu(slots, tearoff=False)
        slots["menu"] = slots.menu
        for n, label in enumerate(("none", "+1  (Tactician's Cape / Crown)", "+2", "+3")):
            slots.menu.add_radiobutton(label=label, value=n, variable=self.extra_slots)
        slots.pack(side="right", padx=(0, 6))

        self.status = tk.Label(self.root, text="Starting...", font=("Segoe UI Semibold", 14), bg=BG, fg=FG, anchor="w")
        self.status.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.note = tk.Label(self.root, text="", font=("Segoe UI", 10), bg=BG, fg=COLORS["warn"], anchor="w",
                             justify="left", wraplength=840)
        self.note.grid(row=2, column=0, columnspan=2, sticky="ew")

        self.sections = {
            "advice": self.section("What to do now", 3, 0, 2, 3),
            "board": self.section("On your board", 4, 0, 1, 3),
            "bench": self.section("On your bench", 4, 1, 1, 3),
            "field": self.section("Put on board", 5, 0, 2, 4),
            "find": self.section("Look for", 6, 0, 1, 8),
            "items": self.section("Items to prioritise", 6, 1, 1, 8),
            "comps": self.section("Comps", 7, 0, 2, 5, size=10),
        }
        threading.Thread(target=self.worker, daemon=True).start()

    def section(self, title: str, row: int, column: int, span: int, height: int, size: int = 11) -> tk.Text:
        frame = tk.Frame(self.root, bg=PANEL, padx=10, pady=6)
        frame.grid(row=row, column=column, columnspan=span, sticky="nsew", padx=3, pady=3)
        tk.Label(frame, text=title.upper(), font=("Segoe UI", 8, "bold"), bg=PANEL, fg=MUTED, anchor="w").pack(fill="x")
        text = tk.Text(frame, height=height, width=44 * span, wrap="word", bg=PANEL, fg=FG, relief="flat",
                       font=("Segoe UI", size), highlightthickness=0, cursor="arrow", state="disabled")
        text.pack(fill="both", expand=True)
        for tag, color in COLORS.items():
            text.tag_configure(tag, foreground=color)
        text.tag_configure("bold", font=("Segoe UI Semibold", size))
        text.tag_configure("minus", foreground=FG, background="#2f4a5c", font=("Segoe UI Semibold", size))
        text.tag_configure("delete", foreground=FG, background="#7a3030", font=("Segoe UI Semibold", size))
        return text

    def fill(self, name: str, parts: list[tuple[str, str]]):
        """Replaces a section's content with (text, tag) pieces."""
        text = self.sections[name]
        if self.shown.get(name) == parts:
            return  # unchanged: leave it alone so hovering and clicking aren't interrupted
        self.shown[name] = parts
        text.configure(state="normal")
        text.delete("1.0", "end")
        for chunk, tag in parts:
            text.insert("end", chunk, tag)
        text.configure(state="disabled")

    def show(self, view: dict):
        self.view = view
        if "waiting" in view:
            self.status.configure(text=view["waiting"])
            self.note.configure(text="")
            for name in self.sections:
                self.fill(name, [])
            return
        self.status.configure(text=view["status"])
        self.note.configure(text=view["note"])
        self.fill("advice", [p for action, t in view["advice"] for p in ((f"{action}  ", action), (t + "\n", ""))])

        if view["board"]:
            unsure = f"\n+ others unclear ({view['board_guesses']} possibilities)" if view["board_guesses"] > 1 else ""
            self.fill("board", [(", ".join(view["board"]), ""), (unsure, "muted")])
        else:
            self.fill("board", [("Couldn't work it out from your traits.", "muted")])
        if view["bench"]:
            parts = []
            for i, (name, copies) in enumerate(view["bench"].items()):
                # The tracking can be wrong, so each unit gets a button: − takes one copy off,
                # ✕ (shown when one copy is left) deletes the unit.
                button = (" ✕ ", (f"bench:{name}", "delete")) if copies == 1 else (" − ", (f"bench:{name}", "minus"))
                parts += [((name if copies == 1 else f"{name} ×{copies}") + " ", ""), button,
                          ("    " if i < len(view["bench"]) - 1 else "", "")]
            self.fill("bench", parts + [("\n−  remove one copy      ✕  delete the unit", "muted")])
            text = self.sections["bench"]
            for name in view["bench"]:
                tag = f"bench:{name}"
                text.tag_bind(tag, "<Button-1>", lambda e, n=name: self.remove_from_bench(n))
                text.tag_bind(tag, "<Enter>", lambda e: text.configure(cursor="hand2"))
                text.tag_bind(tag, "<Leave>", lambda e: text.configure(cursor="arrow"))
        else:
            self.fill("bench", [("Nothing tracked yet (only purchases the app has seen).", "muted")])
            self.sections["bench"].configure(cursor="arrow")

        parts = [(f"For {view['target']}\n", "muted")] if view.get("target") else []
        for label, front in (("Front   ", True), ("Back    ", False)):
            parts.append((label, "muted"))
            row = [u for u in view["field"] if u["front"] == front]
            for i, u in enumerate(row):
                where = {"board": "", "bench": " (from bench)"}.get(u["where"], f" (buy, {u['where']})")
                kind = {"comp": "", "placeholder": " placeholder", "off-comp": " off-comp, replace later"}[u["kind"]]
                tag = "shop" if u["where"].startswith("shop") else "bench" if u["where"] == "bench" else \
                    "off-comp" if u["kind"] == "off-comp" else ""
                parts.append((u["name"], tag or "bold"))
                parts.append((where + ("," if kind and where else "") + kind + (",  " if i < len(row) - 1 else ""), "muted"))
            parts.append(("\n" if row else "-\n", "muted"))
        self.fill("field", parts if view["field"] else [("Nothing to suggest yet.", "muted")])

        held = lambda name: view["taken"].get(name.split("*")[0], 0)
        parts = [("Missing   ", "muted")]
        for i, name in enumerate(view["find"]):
            parts.append((name, ""))
            if held(name):
                parts.append((f" ({held(name)} opp.)", "warn" if held(name) >= 2 else "muted"))
            parts.append((", " if i < len(view["find"]) - 1 else "", ""))
        parts.append(("\n" if view["find"] else "nothing for this level\n", ""))
        parts.append(("In shop   ", "muted"))
        if view["buy"]:
            for name, slot, copies in view["buy"]:
                extra = [f"slot {slot}"] + ([f"{copies} bought"] if copies else []) + \
                        ([f"{held(name)} opp. have it"] if held(name) else [])
                parts += [(name, "shop"), (f" ({', '.join(extra)})\n          ", "muted")]
        else:
            parts.append(("nothing worth buying", "muted"))
        self.fill("find", parts)

        parts = []
        for role, name, items in view["items"]:
            parts += [(f"{role} {name}\n", "bold"), ("  " + ", ".join(items) + "\n", "")]
        if view["components"]:
            parts += [("Components to collect\n", "bold"), ("  " + ", ".join(c if k == 1 else f"{k}× {c}" for c, k in view["components"]), "")]
        self.fill("items", parts)

        parts = [(line + "\n", "" if i == 0 else "muted") for i, line in enumerate(view["comps"])]
        parts.append(("Scouted: " + (", ".join(view["scouted"]) or "nobody yet (view a board for 2-3 seconds)"), "muted"))
        self.fill("comps", parts)

    def remove_from_bench(self, name: str):
        """Takes one copy of the unit off the bench; the last copy removes the unit."""
        if self.session and self.session.bought[name] > 0:
            self.session.bought[name] -= 1
        bench = self.view.get("bench", {})
        if name in bench:  # update now rather than on the next read
            bench[name] -= 1
            if bench[name] <= 0:
                del bench[name]
            self.show(self.view)

    def clear_game_options(self):
        for var in (self.hit, self.lock, *self.emblems.values()):
            var.set(False)
        self.extra_slots.set(0)

    def worker(self):
        meta.update()  # in the worker so the window opens without waiting on the download
        session = self.session = Session(comps.load())
        with mss.mss() as sct:
            primary = next(m for m in sct.monitors[1:] if m["left"] == 0 and m["top"] == 0)
            other = next((m for m in sct.monitors[1:] if m is not primary), None)
            if other:
                self.root.after(0, lambda: self.root.geometry(f"+{other['left'] + 20}+{max(other['top'], 0) + 40}"))
            while True:
                try:
                    shot = sct.grab(primary)
                    img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                    game = session.game
                    emblems = [t for t, var in self.emblems.items() if var.get()]
                    view = session.step(img, self.strategy.get(), self.hit.get(), self.lock.get(), emblems,
                                        self.extra_slots.get())
                    if session.game != game:  # new game: clear per-game ticks
                        self.root.after(0, self.clear_game_options)
                except Exception as e:  # keep the window alive on a bad frame
                    view = {"waiting": f"Read error: {e}"}
                self.root.after(0, lambda v=view: self.show(v))
                time.sleep(POLL_SECONDS)


def main():
    App().root.mainloop()


if __name__ == "__main__":
    main()
