# CLAUDE.md

Daily Tracker is a minimalist, offline-first habit tracker for a single user, used across several devices. A YAML file defines the habits. Each habit gets a daily level of missed, min or max, shown as circles like a paper tracker.

## Read first

- `docs/CONFIG.md` is the `habits.yaml` format: options, habit kinds, scoring and validation. It is the spec, and the code must match it.
- `docs/DEPLOYMENT.md` covers the three supported deployments, the sync model and the PWA setup. Its code snippets are meant as starting points.

## Constraints (do not break)

- **The app is a single HTML file** (`public/index.html`) holding all its CSS and JS. There is no framework, no bundler and no build step. Opening the file directly from `file://` must still work, with sync turned off.
- **Third-party code is inlined.** The only one is js-yaml 4.1.0 (MIT, with its license header kept), inlined in index.html. Never load from a CDN, because the app must work offline.
- **Local-first.** `localStorage` is the live store. Sync is optional, and a sync failure must never block tracking.
- **UI style: Windows 98 dev tool.** Teal desktop, a grey beveled window, a navy title bar, group boxes and a status bar. Tahoma at 12px. Keep it minimal, with no new visual elements unless they serve a function. It must fit a 360px-wide phone with no horizontal page scroll (the week table may scroll inside its own box).
- **Habit ids key all stored data.** Never rename or re-key stored data automatically. Removing a habit from the config hides it but keeps its data.
- **Don't change the data format without a migration.** Keep the existing v1 → v2 migration working.

## Layout

```
public/
  index.html      the app (with js-yaml and a copy of habits.yaml as the fallback default)
  habits.yaml     the deployed habits config, which is the source of truth (see DEPLOYMENT.md §1.4)
docs/
  CONFIG.md       habits.yaml reference
  DEPLOYMENT.md   deployment options 1–3, sync model, PWA
tests/
  smoke_test.py   Playwright smoke test
```

## Current state (v2)

- **Storage:** the `localStorage` key `dailyTracker.v2` holds
  `{ yaml, days: { 'YYYY-MM-DD': { v: { <id>: number }, note }, … }, lastBackup }`.
  The number is a level from 0 to 2 for checks, a unit count for counters, or the entered value for number entries.
- **Migration:** on first load, data stored under `dailyTracker.v1` is converted automatically (see `migrateV1`).
- **Config:** `compile(yamlText)` parses with `jsyaml.CORE_SCHEMA`, validates against the CONFIG.md rules, and returns `{ weekStart, groups, all }`. The default config is embedded in `<script type="text/yaml" id="defaultYaml">`, and the **Habits…** dialog edits a copy stored in `localStorage`.
- **Views:** Day (fieldsets of rows with circles) and Week (a table with a Wk totals column).
- **Backup:** Export writes a JSON file with the data and the config. Import accepts a `.json` backup (v1 or v2) or a `.yaml` config.

## Roadmap (build in this order)

1. **Load the config from `habits.yaml`** (DEPLOYMENT.md §1.4)
   - Fetch `habits.yaml`, network first. Fall back to the last valid cached copy, then to the embedded default. Under `file://`, use the embedded default.
   - If the fetched file is invalid, keep the last valid config and show `Config error: …` in the status bar.
   - The Habits… editor becomes a per-device **local override**. While one is active, the status bar shows `Config: local`, and a **Use deployed** button drops it.
   - Move the config out of the stored data shape (`yaml` is no longer saved with the data).
2. **Timestamps for merging** (DEPLOYMENT.md §1.1)
   - Store each value as `{n, t}` and give the note a `noteT`.
   - Add a v2 → v3 migration. Older backups must still import.
3. **Sync** (DEPLOYMENT.md §1.1, §2.5, §3.5, §4.5)
   - An adapter interface `pull()`/`push(data)`, merging per day and per habit with last-write-wins on `t`.
   - Pull when the app opens and when it returns to the foreground. Push 5 s after the last change, and when the app goes to the background.
   - A **Settings…** dialog to pick the adapter: off, Gist (ID and token), or same-origin `/api/data` (used by both Cloudflare and Tailscale).
   - A sync state cell in the status bar: `Synced 12:04`, `Offline`, `Sync: sign in` or `Sync error`.
4. **PWA** (DEPLOYMENT.md §1.2)
   - `manifest.webmanifest`, `sw.js` and icons (192, 512, and a 180 apple-touch icon) in the Win98 style.
   - Register the service worker only on http(s).
5. **Deployment targets**
   - Option 2: `functions/api/data.js` and `wrangler.toml` (§3.2).
   - Option 3: `server/server.py` and `server/tracker.service` (§4.3–4.4).
   - Option 1 needs only GitHub Pages settings.

## Testing

```bash
pip install playwright     # Chromium may already be installed; otherwise: python -m playwright install chromium
python tests/smoke_test.py
```

Extend the smoke test with each roadmap step. At minimum, cover config validation, every habit kind, migrations, and a merge of two diverging copies. Before finishing a UI change, take a screenshot at a width of 420px and check it.

## Owner context

The routine in `habits.yaml` reflects the owner's Oct 2026 calendar: training on Mon–Sun, eye and voice practice in the mornings, an Ayurvedic evening routine, and work and study blocks. The thresholds for water (4 of 6), greens (3 of 4) and screen breaks (2 of 3), and the LinkedIn post start date, were guesses that the owner may adjust.
