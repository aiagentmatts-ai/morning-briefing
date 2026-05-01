# Publishing the Morning Briefing app

This is a personal Progressive Web App (PWA) deployed to **Cloudflare Workers** with **Cloudflare Access (Zero Trust)** in front so only the owner's email can load it. No public access.

Same shape as the PA GA Guide deployment.

## Architecture

- **Source**: this repo. Static files only — `index.html`, `app.js`, `sw.js`, `styles.css`, `manifest.json`, `icons/`, `data/`.
- **Hosting**: Cloudflare Workers using the Static Assets feature (`wrangler.jsonc` → `assets.directory: "."`).
- **CI/CD**: Cloudflare's GitHub integration auto-deploys every push to `main`.
- **Access**: Cloudflare Access self-hosted application — Allow policy keyed to the owner's email. Anyone else gets the Access login wall.

## One-time setup

### 1. GitHub

Push this repo to GitHub (private is fine).

```bash
git remote add origin https://github.com/<your-username>/morning-briefing.git
git push -u origin main
```

### 2. Connect to Cloudflare Workers

1. Cloudflare dashboard → **Workers & Pages** → **Create** → **Connect to Git**.
2. Pick the `morning-briefing` repo, branch `main`, root directory `/`.
3. Cloudflare detects `wrangler.jsonc` and runs `wrangler deploy`. The first deploy lands at `https://morning-briefing.<account>.workers.dev`.

### 3. Put Cloudflare Access in front

1. Cloudflare dashboard → **Zero Trust** → **Access** → **Applications** → **Add an application** → **Self-hosted**.
2. Application domain: the `*.workers.dev` URL from step 2 (or a custom subdomain if used).
3. Identity provider: same one used for the PA GA Guide app (One-time PIN to email at minimum, or your SSO).
4. Policy: **Allow**, rule = `Emails` includes your email. Save.
5. Verify in a private window — should redirect to Cloudflare Access login and reject any other email.

### 4. Add to iPhone home screen

1. Open the app URL in **Safari** on iPhone.
2. Complete the Cloudflare Access login (one-time PIN to your email, or SSO).
3. Share icon → **Add to Home Screen** → name "Briefing" → Add.
4. Delete any old GitHub Pages icon pointing at the previous host.

The Access session persists for the duration configured in the Access policy (e.g., 1 month), so you won't have to log in on every launch.

## Daily content updates

The app reads two files at the same base URL:

- `data/morning.json`
- `data/improvements.json`

Tell Claude (or your automation) to write these files in the repo, commit, and push to `main`. Cloudflare auto-deploys within a minute. The app fetches network-first and falls back to the service worker cache.

### `morning.json` shape

```json
{
  "date": "2026-04-25",
  "type": "morning",
  "generated_at": "2026-04-25T07:00:00-04:00",
  "sections": [
    {
      "id": "national-politics",
      "label": "National Politics",
      "count": 6,
      "stories": [
        {
          "headline": "...",
          "summary": "...",
          "source": "Punchbowl News",
          "time": "3h ago",
          "flagged": true
        }
      ]
    }
  ]
}
```

The first section's first story is the "Top Story." `count` is the badge number on category cells (falls back to `stories.length`). `flagged: true` shows a ⚡ marker.

### `improvements.json` shape

The Settings page has a "Report a bug or idea" inbox. Copy the inbox to clipboard, paste to Claude. Claude writes/updates this file:

```json
{
  "generated_at": "2026-04-26T08:00:00-04:00",
  "items": [
    {
      "id": "imp_2026-04-26_001",
      "title": "Responsive top-story headline",
      "description": "Cap headline at 3 lines on screens <380px with ellipsis + tap-to-expand.",
      "source_feedback": ["Top story headline wraps awkwardly on small screens"],
      "estimated_effort": "S"
    }
  ]
}
```

Approved items move into a local queue inside the app (`localStorage["db_improvement_decisions"]`).

## Pointing the app at a different briefings URL

By default the app fetches from `./data` (relative to the host). To override, open the app → **⚙ Settings** → **Briefings URL** and paste a base URL. Cached locally.

## Local development

```bash
npm install
npm run dev
```

Wrangler serves the app at `http://localhost:8787` using the same Static Assets runtime as production.
