"""Regenerate assets/icons/*.png and assets/StreamPilotIconICO.ico from the one source artwork (WS-130).

Run: python scripts/dev/build-icons.py   (needs Pillow). A test fails when the committed files drift from the source.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "src"))
import app_icon  # noqa: E402

if __name__ == "__main__":
    for p in app_icon.build_all():
        print("wrote", os.path.relpath(p, app_icon.ROOT))
