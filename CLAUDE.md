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

## Schema

Documented in `aiagentmatts-ai/Briefings`'s [PUBLISHING.md](https://github.com/aiagentmatts-ai/Briefings/blob/main/PUBLISHING.md) — canonical shapes for `morning.json`, `evening.json`, and `improvements.json`. The local [PUBLISHING.md](PUBLISHING.md) covers this repo's Cloudflare Workers + Access deployment.

## Commit cadence

One commit per briefing run, directly on `main` (no PR ceremony for routine data updates):

- Morning: `Morning briefing YYYY-MM-DD`
- Evening: `Evening briefing YYYY-MM-DD`

Match the existing history. Don't bundle multiple runs into one commit. Backfills/fixes get their own descriptive message (e.g., `Backfill 5/7 market prices from validated endpoints`) — don't reuse a daily-briefing message for a non-daily change.
