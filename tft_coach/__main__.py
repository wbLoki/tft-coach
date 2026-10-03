"""Manual mode: type in your state, get advice. Example:

python -m tft_coach --stage 4-2 --level 7 --xp 20 --gold 54 --hp 62
"""
import argparse

from .advisor import HOLD_LEVEL, GameState, advise

p = argparse.ArgumentParser(prog="tft_coach")
p.add_argument("--stage", required=True)
p.add_argument("--level", type=int, required=True)
p.add_argument("--xp", type=int, default=0)
p.add_argument("--gold", type=int, required=True)
p.add_argument("--hp", type=int, default=100)
p.add_argument("--streak", type=int, default=0, help="positive = wins, negative = losses")
p.add_argument("--strategy", choices=list(HOLD_LEVEL), default="standard")
p.add_argument("--hit", action="store_true", help="reroll strategies: 3-stars done, level normally")

for a in advise(GameState(**vars(p.parse_args()))):
    print(f"[{a.action:5}] {a.text}")
