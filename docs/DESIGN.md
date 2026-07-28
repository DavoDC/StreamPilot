# Dashboard Design Consistency

Rules for keeping `src/dashboard_server.py`'s single-page dashboard visually
consistent as features get added. Read this before touching `INDEX_HTML`.

## Design principles (read before adding or changing a card/row)

The dashboard groups its fields into one card per API source - OBS, Twitch, SABnzbd - rather than one flat list of label-value rows, because the source of a fact is part of the fact. A window-capture problem and a Twitch category problem are different failure modes with different fixes, and putting them in separate cards lets David's eye go straight to the source that needs attention instead of scanning an undifferentiated list to work out which service a row even belongs to.

Each card has a muted accent colour (a thin left border and a matching icon tint, see the palette below) that exists purely to help the eye group a card's rows together at a glance - these accents must never compete with the big OK/ISSUE badge above the cards, which is the dashboard's primary signal. The accents are deliberately dark-filled and low-contrast for exactly this reason: if a card's own colour were as loud as the top-level badge, David would have to compare colours instead of just checking the one badge that actually says whether something is wrong.

White means normal, colour means attention - this is the governing rule for every row on the dashboard, not just a stylistic default. A green "safe" label used to sit on the OBS card's Audio row in the healthy state, and it was removed (2026-07-28) precisely because decorative colour in the healthy state trains the eye to ignore colour: once green becomes the everyday appearance of a row, the same eye stops reacting when that row turns red, because colour on that row no longer reliably means something changed. Reserving colour for the case that needs attention keeps every colour on the page meaningful the moment it appears.

The OBS card's Video and Audio rows are a deliberately symmetric pair - identical labels-width, identical value formatting, identical values when everything is correct - so a mismatch between what is being seen and what is being heard is visible instantly, without reading either word. That alignment is the feature, not a side effect of tidy layout. Any decoration that breaks it - brackets around one value, a colour applied to only one row, an adjective like "safe" prefixed to one but not the other - destroys the comparison, because the eye can no longer treat the two rows as directly comparable strings.

Where a stable identifier and a human-friendly one conflict, the dashboard shows the stable one. The Video row shows the exe name rather than the OBS window title because window titles truncate, change at runtime (loading screens, level names, match state), and are localised, while the exe is the one thing that does not move - and critically, it is the exact identifier the audio guard matches on. Showing the same identifier the guard uses is what makes the dashboard a verification surface rather than a decoration: David is not being told a name, he is being shown the actual value a safety check compares against.

The dashboard is entirely self-contained: no external requests, no CDN, no remote fonts or images, inline SVG only for the card-header icons. It has to work with no internet, since it is a local status page served from `http.server` on `localhost` and is meant to be glanced at mid-stream - a dependency on any external resource would mean the one page that is supposed to prove everything is working could itself fail silently for a reason unrelated to StreamPilot.

## Why this doc exists

The Quit button once rendered in a different font than the rest of the page.
Root cause: browsers' default user-agent stylesheets do NOT make `<button>`
or `<input>` inherit `font-family` from the page - only text elements do.
The fix is a single global rule (see below); anything that adds a new
interactive element gets it for free and never needs to repeat it.

## Color palette

| Role | Value | Used for |
|---|---|---|
| Page background | `#12151a` | `body` |
| Panel background | `#1a1e26` | `#panel`, `#quitDialog` |
| Chip/control background | `#262b34` | `.tag`, `.switch .slider` (off) |
| Muted text / labels | `#6b7280` | `.row .label`, `#footer` |
| OK | `#3fd67a` | status badge/dot |
| ISSUE | `#ff5d5d` | status badge/dot |
| IDLE | `#6b7280` | status badge/dot |
| OFFLINE | `#4b5563` | status badge/dot |
| Twitch accent (purple) | `#a970ff` | `#twitchLink` |
| Keep-streaming accent (blue) | `#3fa1ff` | `#quitKeepStream`, toggle "on" |
| End-stream accent (red) | `#ff5d5d` / `#ff8787` | `#quitEndStream` |

New status colors or accents should reuse one of these rather than
introducing a new hue - the palette is deliberately small.

## Typography

- One font stack for everything: `"Segoe UI", system-ui, sans-serif`, set once
  on `body`.
- **Rule: any new `<button>` or `<input>` must inherit that font.** This is
  handled globally by:
  ```css
  button, input { font-family: inherit; }
  ```
  Do not add a new interactive element without checking this rule still
  covers it (it does, for both tags, by default) - never re-set
  `font-family` per-element instead.

## Buttons

- Border-radius `6px`.
- Rest state: transparent or dark background, muted border/text color.
- Hover/`:focus-visible`: border and text brighten to the accent color for
  that action (see `#quitBtn`, `.quitActions button` for examples).
- Destructive actions (End stream) use the red accent; safe/default actions
  use neutral or blue.

## Toggle switches

Use the `.switch` pattern (checkbox styled as a pill) for any on/off control
the dashboard exposes - e.g. `#sabToggle`. Structure:
```html
<label class="switch"><input type="checkbox" id="...""><span class="slider"></span></label>
```
The CSS lives in one block (search `.switch` in `INDEX_HTML`). Reuse it
rather than writing new toggle CSS per feature. Disable (`input.disabled`)
whenever the dashboard is offline/stale, matching how the rest of the panel
blanks out to `-`.

## Adding a new dashboard control checklist

1. Does it need a color? Reuse a palette entry above.
2. Is it a button or input? Confirm `font-family: inherit` still applies (it
   does automatically via the global rule).
3. Is it a toggle? Reuse `.switch`, don't invent new markup.
4. Does the value need to reflect daemon state? Read it from `status.json`
   in `tick()`, and blank/disable it in the `stale` branch like every other
   field.
