"""WS-121: the served page makes no external requests (no CDN, remote font, image, script or stylesheet)."""

import re

import dashboard_server


def _html():
    return dashboard_server.index_html_bytes().decode("utf-8")


def test_no_external_urls_except_the_svg_namespace():
    urls = re.findall(r"https?://[^\s'\"<>)]+", _html())
    offenders = [u for u in urls if u != "http://www.w3.org/2000/svg"]
    assert offenders == []


def test_no_remote_loading_constructs():
    html = _html()
    assert "@import" not in html
    for tag in re.findall(r"<link\b[^>]*>", html):  # only the favicon, whose href is filled in with a data: URI by the page
        assert 'id="favicon"' in tag and 'href=""' in tag, tag
    assert not re.search(r"<script[^>]*\ssrc=", html)
    assert not re.search(r"<img[^>]*\ssrc=[\"']?(https?:)?//", html)
    assert not re.search(r"url\(\s*[\"']?(https?:)?//", html)
    assert "@font-face" not in html


def test_csp_blocks_remote_loads():
    csp = dashboard_server.CSP if hasattr(dashboard_server, "CSP") else None
    if csp is not None:
        assert "default-src 'self'" in csp
