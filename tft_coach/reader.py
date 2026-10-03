"""Reads the game state from the screen (pixels only, never the game process).

Regions are measured on a 2560x1440 screenshot and scaled to the actual image size.
Debug: python -m tft_coach.reader screenshot.png
"""
import re
import statistics
import sys

import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

REF_W, REF_H = 2560, 1440

# (left, top, right, bottom) on the reference resolution
REGIONS = {
    "stage": (973, 6, 1158, 41),
    "level": (461, 1175, 563, 1213),
    "xp": (634, 1178, 698, 1211),
    "gold": (1364, 1182, 1420, 1214),
    "streak": (1523, 1172, 1568, 1206),
}
PLAYERS = (2240, 243, 2477, 1101)
TRAITS = (77, 340, 345, 1075)
AUGMENT_TITLE =(1120, 262, 1440, 325)
SHOP_X0, SHOP_STEP, SHOP_W, SHOP_Y = 741.5, 269.5, 190, (1393, 1426)
MIN_NAME_SCORE = 0.5
SCOUT_SHIFT = 15  # px the scouted player's row moves left, at reference resolution

_engine = RapidOCR()
# A lone zero is often read as one of these.
_ZERO_LOOKALIKES = str.maketrans({"。": "0", "O": "0", "o": "0", "D": "0", "Q": "0"})


def _crop(img: Image.Image, box) -> np.ndarray:
    sx, sy = img.width / REF_W, img.height / REF_H
    l, t, r, b = box
    crop = img.crop((round(l * sx), round(t * sy), round(r * sx), round(b * sy))).convert("RGB")
    return np.ascontiguousarray(np.array(crop)[:, :, ::-1])  # BGR for the OCR engine


def _read_line(img: Image.Image, box) -> tuple[str, float]:
    """Recognises a single line of text without running text detection (fast)."""
    text, score = _engine.text_recognizer([_crop(img, box)])[0][0]
    return text.strip(), float(score)


def _int(text: str) -> int | None:
    m = re.search(r"\d+", text.translate(_ZERO_LOOKALIKES))
    return int(m.group()) if m else None


def read_players(img: Image.Image) -> tuple[int | None, str | None]:
    """(your HP, name of the player whose board is on screen or None). Slow (~1s).

    Your own row in the player list is drawn larger than the others; the row of a
    player you are scouting slides out to the left.
    """
    result = _engine(_crop(img, PLAYERS))[0] or []
    hps, names = [], []
    for box, text, _ in result:
        y, height = (box[0][1] + box[2][1]) / 2, box[2][1] - box[0][1]
        if text.isdigit() and int(text) <= 100:
            hps.append((height, box[1][0], y, int(text)))
        elif len(text) >= 3:
            names.append((y, text))
    if not hps:
        return None, None
    own = max(hps)
    others = [h for h in hps if h is not own]
    viewed = None
    if len(others) >= 2:
        usual = statistics.median(h[1] for h in others)
        shifted = min(others, key=lambda h: h[1])
        if usual - shifted[1] >= SCOUT_SHIFT * img.width / REF_W and names:
            y, name = min(names, key=lambda n: abs(n[0] - shifted[2]))
            viewed = name if abs(y - shifted[2]) < shifted[0] else None
    return own[3], viewed


def read_traits(img: Image.Image) -> dict[str, int]:
    """Trait name -> unit count, from the panel on the left. Slow (~1s)."""
    panel = _crop(img, TRAITS)
    sy = img.height / REF_H
    traits = {}
    for box, text, _ in _engine(panel)[0] or []:
        if not re.fullmatch(r"[A-Za-z' ]{3,}", text):
            continue
        # The unit count sits just left of the name, slightly below its top.
        x, y = int(box[0][0]), int((box[0][1] + box[2][1]) / 2)
        digit = panel[max(y - round(12 * sy), 0):y + round(28 * sy), max(x - round(42 * sy), 0):max(x - round(6 * sy), 1)]
        count = _int(_engine.text_recognizer([digit])[0][0][0]) if digit.size else None
        traits[text.strip()] = count if count and count < 20 else 1
    return traits


def is_augment_choice(img: Image.Image) -> bool:
    """The augment picker hides the whole bottom HUD (gold, level, shop)."""
    return "choose" in _read_line(img, AUGMENT_TITLE)[0].lower()


def read_shop(img: Image.Image) -> list[str | None]:
    shop = []
    for i in range(5):
        x = SHOP_X0 + SHOP_STEP * i
        text, score = _read_line(img, (x, SHOP_Y[0], x + SHOP_W, SHOP_Y[1]))
        shop.append(text if score >= MIN_NAME_SCORE and text else None)
    return shop


def read_state(img: Image.Image) -> dict:
    """Fast fields only (stage, level, xp, gold, streak). Unreadable ones are None."""
    raw = {k: _read_line(img, box)[0] for k, box in REGIONS.items()}
    stage = re.search(r"(\d)\s*[-—–]\s*(\d)", raw["stage"])
    xp = re.search(r"(\d+)\s*/\s*(\d+)", raw["xp"].translate(_ZERO_LOOKALIKES))
    level = re.search(r"(\d+)\s*$", raw["level"])
    return {
        "stage": f"{stage.group(1)}-{stage.group(2)}" if stage else None,
        "level": int(level.group(1)) if level and "v" in raw["level"].lower() else None,
        "xp": int(xp.group(1)) if xp else None,
        "gold": _int(raw["gold"]),
        "streak": _int(raw["streak"]),
        "_raw": raw,
    }


if __name__ == "__main__":
    image = Image.open(sys.argv[1])
    hp, viewed = read_players(image)
    for k, v in {**read_state(image), "hp": hp, "scouting": viewed, "traits": read_traits(image),
                 "shop": read_shop(image)}.items():
        print(f"{k:8} {v}")
