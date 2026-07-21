"""Pure helpers for building a per-game Twitch title and tag list.

No I/O here - these are plain functions over config dicts so they are
trivially unit testable. twitch_client.py sends whatever they produce.
"""

import re

TWITCH_TITLE_MAX_LEN = 140
TWITCH_TAG_MAX_LEN = 25
TWITCH_TAG_MAX_COUNT = 10

DEFAULT_TITLE_TEMPLATE = "Davo plays {game}!"

_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")


def build_title(name: str, game_cfg: dict, twitch_cfg: dict) -> str:
    """Build the stream title for a game.

    Uses the per-game 'title' override if set (non-empty); otherwise formats
    twitch_cfg's 'title_template' (default "Davo plays {game}!") with the
    game name. Truncated to Twitch's 140-char limit.

    If the game has an 'emoji' entry, it's appended as " <emoji>" - but only
    if it fits within the 140-char limit alongside the (already truncated)
    base title. The emoji is dropped rather than truncating the base title,
    since a half-cut emoji or a chopped word reads worse than no emoji.
    """
    title = game_cfg.get("title")
    if not title:
        template = twitch_cfg.get("title_template", DEFAULT_TITLE_TEMPLATE)
        title = template.format(game=name)
    title = title[:TWITCH_TITLE_MAX_LEN]

    emoji = game_cfg.get("emoji")
    if emoji:
        with_emoji = f"{title} {emoji}"
        if len(with_emoji) <= TWITCH_TITLE_MAX_LEN:
            title = with_emoji

    return title


def _sanitize_tag(tag: str) -> str:
    """Strip to alphanumeric-only and cap length. May return an empty string."""
    return _NON_ALNUM.sub("", tag)[:TWITCH_TAG_MAX_LEN]


def build_tags(game_cfg: dict, twitch_cfg: dict) -> list:
    """Build the sanitized tag list for a game.

    Combines twitch_cfg's 'base_tags' (always applied) with the game's
    'tags', sanitizes each (alphanumeric only, max 25 chars, empties
    dropped), dedupes case-insensitively (keeping the first-seen casing),
    and caps the result at 10 tags - matching Twitch's channel tag rules.
    """
    raw = list(twitch_cfg.get("base_tags", [])) + list(game_cfg.get("tags", []))
    seen = set()
    result = []
    for tag in raw:
        cleaned = _sanitize_tag(tag)
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned)
        if len(result) >= TWITCH_TAG_MAX_COUNT:
            break
    return result
