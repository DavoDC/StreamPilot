"""WS-130: one app icon everywhere. Tray, favicon, header mark and the shortcut .ico all derive from the one source artwork."""

import io
import os
import re

import pytest

import app_icon
import dashboard_server
import health
import tray

PIL = pytest.importorskip("PIL")
from PIL import Image, ImageChops  # noqa: E402


def _same(a, b):
    return ImageChops.difference(a.convert("RGBA"), b.convert("RGBA")).getbbox(alpha_only=False) is None


def test_source_artwork_exists():
    assert os.path.exists(app_icon.SOURCE_PNG)


@pytest.mark.parametrize("state", app_icon.STATES)
def test_committed_state_png_is_derived_from_the_source(state):
    fresh = app_icon.render(state, app_icon.STATE_PNG_SIZE)
    assert _same(Image.open(app_icon.state_png_path(state)), fresh), "run scripts/dev/build-icons.py"


def test_ico_is_derived_from_the_source_and_multi_size():
    ico = Image.open(app_icon.ICO_PATH)
    assert {s[0] for s in ico.info["sizes"]} >= {16, 32, 48, 256}
    ico.size = (256, 256)
    assert _same(ico.copy(), app_icon.render(None, 256))


def test_tray_image_is_the_app_icon_with_a_state_badge():
    backend = tray._load_backend()
    for state in app_icon.STATES:
        assert _same(tray.render_icon(backend, state, 32), app_icon.render(state, 32))


def test_state_changes_only_the_corner_badge():
    ok, issue = app_icon.render("OK", 64), app_icon.render("ISSUE", 64)
    left, top, right, bottom = ImageChops.difference(ok.convert("RGBA"), issue.convert("RGBA")).getbbox(alpha_only=False)
    assert left >= 64 * 0.5 and top >= 64 * 0.5  # only the bottom-right quadrant differs; the glyph never changes


def test_page_favicon_and_header_mark_use_the_state_icons():
    html = dashboard_server.index_html_bytes().decode("utf-8")
    for state in app_icon.STATES:
        assert app_icon.data_uri(state) in html
    assert 'id="appmark"' in html
    assert "viewBox='0 0 32 32'" not in html  # the old generic disc favicon is gone


def test_every_state_has_a_colour_and_a_png():
    for state in app_icon.STATES:
        assert state in health.COLOURS and os.path.exists(app_icon.state_png_path(state))
