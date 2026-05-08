# Morning Briefing — repo guide for Claude

## What this repo is

The Cloudflare Workers PWA **and** the daily briefing data it serves. Static assets (`index.html`, `app.js`, `sw.js`, `styles.css`) auto-deploy on every push to `main` via Cloudflare's GitHub integration; Cloudflare Access keeps it owner-only. The same `data/*.json` files are also consumed by the sibling GitHub Pages app at `aiagentmatts-ai/Briefings` (it accepts a configurable Briefings URL).

The design/dev workspace at `C:\Users\Matt\Desktop\Matt's Claude Vault\Daily Briefing App\` is the source-of-truth for cross-cutting workflows (its CLAUDE.md covers `/deploy-cf` verification, etc.). This repo's CLAUDE.md only documents what's specific to the briefing-data side.

## When the scheduler didn't fire

Run `/diagnose-briefing`. The full runbook (stuck-counter signature in `main.log`, Claude Desktop restart fix) lives in the user-level skill — don't re-document it here.

## Data integrity (highest-leverage rule)

The briefing files are read aloud on iPhone. Fabricated stories, sources, dates, or numbers are silent failures the user only catches after relying on them.

- **Never invent.** If a feed is empty or unreachable, write an empty `stories` array (or omit the section) and add a `note` field saying so. Do not pad with plausible-looking entries.
- **Cross-reference outlet attribution.** Confirm at least one identifying detail (URL, byline, dateline) before asserting a story came from a specific outlet. The Apple News+ / NYT-duplicate-charge incident is the cautionary tale — a single signal looked authoritative and wasn't.
- **Numeric facts come from a real endpoint or they don't appear.** Weather, market prices, dates: no placeholders, no "approximately."
- **PA/NJ co-op + PJM angle is the lens** (see user memory `user_role.md`), but the lens applies to selection, not invention.

## PJM market snapshot — read before composing the energy section

**Before composing the morning briefing's energy-industry section, run the PJM scraper and read its output.** This is what gives the section real numbers (RTO LMP, Western Hub, current load, fuel mix) instead of just headlines.

```
python scripts/scrape-pjm-markets.py
```

The scraper writes (or refreshes) `data/energy-markets.json`. It hits one URL — `www.pjm.com/markets-and-operations` — server-rendered widget data, no API key, no JS runtime. Typical run is under 5 seconds. The scraper itself is fixture-tested at `tests/test_pjm.py` (33 assertions on output shape, exact ground-truth values, count, absence, cross-checks).

If the scraper errors (network blip, PJM site restructured), **don't fabricate prices.** Write the energy section without market numbers and add a `note: "PJM market snapshot unavailable today"` to the section. Drift detection (`.github/workflows/drift-check-pjm.yml`) opens a `fixture-drift` issue when PJM's HTML changes structurally — when you see one of those, check the parser before assuming the source is just down.

What to incorporate into the energy-industry section's prose summaries:
- **`todaysOutlook.rtoLmpDollars`** — headline real-time LMP for PJM-RTO. Cite as "$X.XX/MWh" with the `asOf` timestamp.
- **`hubLmps`** entries flagged `isPaNjHub: true` (WESTERN HUB, EASTERN HUB, NEW JERSEY HUB, DOMINION HUB) — Western Hub is the canonical PA wholesale benchmark. Useful when a story is about wholesale prices, hedging, or supply contracts.
- **`zoneLmps`** entries flagged `isPaZone: true` (METED, PECO, PENELEC, PPL) — when a story is about a specific PA utility's load or pricing.
- **`fuelMix.byFuel`** — share-of-generation context. Especially relevant when stories mention queue results, capacity auction outcomes, or fuel-specific policy.
- **`todaysOutlook.currentLoadMw`** and **`forecastedPeakMw`** — useful framing when stories mention demand, peak load, or grid stress.

The section should still be story-driven (headlines + summaries from real reporting), but the numbers from `energy-markets.json` can sharpen a summary, e.g. "FirstEnergy CEO Tierney's earnings-call complaint about PJM auction design landed with Western Hub at $44.78/MWh and load forecast at 84.9 GW." The numbers come from the snapshot, the framing comes from the source reporting.

`data/energy-markets.json` is also refreshed independently by `.github/workflows/refresh-energy-markets.yml` at 11:00 UTC daily as a safety net, but the briefing routine should run the scraper itself at compose time so the snapshot matches the briefing's `generated_at` timestamp.

## Schema

Documented in `aiagentmatts-ai/Briefings`'s [PUBLISHING.md](https://github.com/aiagentmatts-ai/Briefings/blob/main/PUBLISHING.md) — canonical shapes for `morning.json`, `evening.json`, and `improvements.json`. The local [PUBLISHING.md](PUBLISHING.md) covers this repo's Cloudflare Workers + Access deployment.

## Commit cadence

One commit per briefing run, directly on `main` (no PR ceremony for routine data updates):

- Morning: `Morning briefing YYYY-MM-DD`
- Evening: `Evening briefing YYYY-MM-DD`

Match the existing history. Don't bundle multiple runs into one commit. Backfills/fixes get their own descriptive message (e.g., `Backfill 5/7 market prices from validated endpoints`) — don't reuse a daily-briefing message for a non-daily change.
