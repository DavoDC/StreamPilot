"""The one StreamPilot app icon (WS-130, WS-124).

Every surface derives from the single source artwork assets/StreamPilotIconPNG.png: the tray image, the browser favicon and header
mark, and the multi-size desktop shortcut .ico. State (OK / ISSUE / IDLE / OFFLINE) is only a small coloured badge in the bottom-right
corner of that same artwork, never a different glyph. Dark only: the artwork sits on the dark rounded badge.
Pillow is needed to RENDER (tray, scripts/dev/build-icons.py); the running server only reads the pre-rendered assets/icons/*.png.
"""
import base64
import os

import health

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SOURCE_PNG = os.path.join(ROOT, "assets", "StreamPilotIconPNG.png")
ICO_PATH = os.path.join(ROOT, "assets", "StreamPilotIconICO.ico")
ICONS_DIR = os.path.join(ROOT, "assets", "icons")
BADGE = "#1f2937"
STATES = ("OK", "ISSUE", "IDLE", "OFFLINE")
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)
STATE_PNG_SIZE = 64


def render(state=None, size=64, source=SOURCE_PNG):
    """The app icon at size px. state None = plain app icon (shortcut, header base); a state adds only the corner badge."""
    from PIL import Image, ImageDraw
    big = max(size * 4, 256)
    img = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, big - 1, big - 1), radius=big * 0.19, fill=BADGE)
    art = Image.open(source).convert("RGBA")
    inset = int(big * 0.10)
    art = art.resize((big - 2 * inset, big - 2 * inset), Image.LANCZOS)
    img.alpha_composite(art, (inset, inset))
    if state is not None:
        r = big * 0.15
        cx, cy = big - r - big * 0.02, big - r - big * 0.02
        d = ImageDraw.Draw(img)
        d.ellipse((cx - r * 1.28, cy - r * 1.28, cx + r * 1.28, cy + r * 1.28), fill=BADGE)
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=health.COLOURS[state])
    return img.resize((size, size), Image.LANCZOS)


def state_png_path(state):
    return os.path.join(ICONS_DIR, f"{state.lower()}.png")


def data_uri(state):
    """data: URI of the pre-rendered state icon, for the page favicon and header mark (no Pillow, no extra request)."""
    with open(state_png_path(state), "rb") as fh:
        return "data:image/png;base64," + base64.b64encode(fh.read()).decode("ascii")


def build_all(icons_dir=ICONS_DIR, ico_path=ICO_PATH, source=SOURCE_PNG):
    """Regenerate every derived file from the source. Returns the written paths."""
    os.makedirs(icons_dir, exist_ok=True)
    written = []
    for st in STATES:
        p = os.path.join(icons_dir, f"{st.lower()}.png")
        render(st, STATE_PNG_SIZE, source).save(p, optimize=True)
        written.append(p)
    render(None, 256, source).save(ico_path, sizes=[(s, s) for s in ICO_SIZES])
    written.append(ico_path)
    return written
