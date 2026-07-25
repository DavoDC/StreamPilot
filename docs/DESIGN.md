# Dashboard Design Consistency

Rules for keeping `src/dashboard_server.py`'s single-page dashboard visually
consistent as features get added. Read this before touching `INDEX_HTML`.

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
