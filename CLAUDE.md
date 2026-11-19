# CLAUDE.md

Daily Tracker is a minimalist, offline-first habit tracker for a single user, used across several devices. A YAML file defines the habits. Each habit gets a daily level of missed, min or max, shown as circles like a paper tracker.

## Read first

- `docs/CONFIG.md` is the `habits.yaml` format: options, habit kinds, scoring and validation. It is the spec, and the code must match it.
- `docs/CONFIG-CHANGES.md` covers what each kind of `habits.yaml` edit does to stored data, past scores and devices that haven't updated, plus the spike #4 decisions: score with the current config, allow only safe kind changes in place (check ↔ avoid, max text, `count`), split the rest, and never rewrite stored data. Check it before changing an existing habit or adding a config option.
- `docs/DEPLOYMENT.md` covers the three supported deployments, the sync model and the PWA setup. Its code snippets are meant as starting points.

## Deployment status

- **Live:** Option 1, GitHub Pages + secret Gist, at https://rpatel23.github.io/dinacharya-utility/. Gist sync is set up on the owner's devices, so treat the stored data format and the Gist payload as production: changes need a migration, and must stay compatible with devices still running the previous version until they update.
- **Future migration paths:** Option 2 (Cloudflare) and Option 3 (Tailscale). Keep their code and tests working, but they are not deployed.
- **Work tracking:** GitHub Issues (`gh issue list`). Reference the issue in commits (`Fixes #N`).

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
  manifest.webmanifest, sw.js, icon-192.png, icon-512.png, apple-touch-icon.png   PWA (DEPLOYMENT.md §1.2)
functions/api/data.js   Option 2: Cloudflare Pages Function for /api/data (KV)
wrangler.toml           Option 2: Pages config (fill in the KV namespace id)
server/
  server.py       Option 3: stdlib server for public/ and /api/data (data in server/data/, gitignored)
  tracker.service Option 3: systemd unit
tools/
  make_icons.py   renders the three PNG icons from one SVG (Playwright)
  config_diff.py  Markdown report of risky habits.yaml changes (CI run summary; docs/CONFIG-CHANGES.md)
docs/
  CONFIG.md       habits.yaml reference
  CONFIG-CHANGES.md  what each habits.yaml change does to history and devices (spike #4)
  ROUTINE-BRIEF.md   brief for designing habits.yaml with another agent (used for #8)
  DEPLOYMENT.md   deployment options 1–3, sync model, PWA
tests/
  smoke_test.py   Playwright smoke test (runs on fixture_habits.yaml, not the live config)
  fixture_habits.yaml  the test routine the smoke test uses
```

## Current state (v3)

- **Storage:** the `localStorage` key `dailyTracker.v3` holds
  `{ days: { 'YYYY-MM-DD': { v: { <id>: { n, t } }, note, noteT }, … }, lastBackup }`.
  `n` is a level from 0 to 2 for checks, a unit count for counters, the entered value for number entries, or for avoid habits `1` = clean / `-1` = failed (`n > 0` reads as clean, so a check can switch to `avoid` and keep its history). `n` can be negative only for avoid habits; never clamp it to ≥ 0 in storage, merge or import. `val()` reads it clamped to the current kind (counter 0…`count`, number entry ≥ 0) for display, scoring and taps, so values left over from a config change never show out of range. `t` and `noteT` are `Date.now()` of the last change, used for last-write-wins merging. Clearing a value stores `{ n: 0, t }` (and an emptied note keeps `noteT`) so the clear wins against an older copy; never delete entries on clear.
- **Migration:** on first load, `dailyTracker.v2` (or else `dailyTracker.v1`, via `migrateV1`) is converted by `toV3`, with `t: 0`/`noteT: 0` so any later edit wins. The old keys are left in place as a safety copy. A `yaml` field in v2 data is not carried over; if it differs from the embedded default, it becomes the local override (see `load`).
- **Config:** `compile(yamlText)` parses with `jsyaml.CORE_SCHEMA`, validates against the CONFIG.md rules, and returns `{ weekStart, groups, all }`. Sources, in order:
  - `dailyTracker.override`: the per-device local override saved from **Habits…** or a `.yaml` import. Status bar: `Config: local`; **Use deployed** drops it.
  - `habits.yaml`, fetched with `cache: 'no-cache'` after the first render (`fetchConfig`), only on http(s). A valid file is cached (LF line endings) under `dailyTracker.deployed`; an invalid one keeps the cached copy and shows `Config error: …` in the status bar and the editor.
  - The embedded default in `<script type="text/yaml" id="defaultYaml">`, always used under `file://` (plus any override). Keep it identical to `public/habits.yaml`.
- **min / max:** min is done and is all Day %/Week % measure; max is optional extra credit that exists only when written (`hasMax(it)`: check `maxText`, count/value `it.max != null`). A check without max text toggles 0 ↔ 1 and reads any stored `n ≥ 1` as done (old 2s are never rewritten). A counter's `min` defaults to `count`; `max` never defaults.
- **Habit kinds:** `check`, `count`, `value` and `avoid` (`avoid: true`; blank → clean → failed → blank; clean scores as min and never max; colours `--ok` / `--fail`, and the legend's clean/failed entries show only when the config has an avoid habit).
- **Views:** Day (fieldsets of rows with circles) and Week (a table with a Wk totals column).
- **Backup:** Export writes a version 3 JSON file with the data only. Import replaces all local data and accepts a `.json` backup (v1, v2 or v3; a `yaml` field in older backups is ignored) or a `.yaml` config, which becomes the local override. With sync on, the next sync merges the imported data with the remote copy, so remote values with a newer `t` win.
- **Sync:** settings live in `dailyTracker.sync` (`{mode: 'off'|'gist'|'api', id, tok}`), per device and not synced. `ADAPTERS.gist` / `ADAPTERS.api` implement `pull()`/`push(data)`; the remote payload is `{app, version: 3, days}`. `sync()` always pulls, merges with `mergeDays` (per day and habit, newer `t` wins; ties go to the higher `n`; the note goes by `noteT`, ties to the longer text), saves and re-renders if local changed, and pushes only if the remote differs. It runs on open, on returning to the foreground, on `online`, 5 s after the last `save()` (`PUSH_DELAY`), when going to the background with a push pending, and when the status cell is clicked. One sync runs at a time. `/api/data` requests use `redirect: 'manual'`, so a Cloudflare Access login redirect is reported as `LOGIN` rather than a CORS failure. The status cell (`#s3`) shows `Syncing…`, `Synced HH:MM`, `Offline`, `Sync: sign in` (click reloads) or `Sync error` (detail in its tooltip). `/api/data` is not offered under `file://`; Gist works there.
- **PWA:** `sw.js` is registered only on http(s). It serves the app shell cache-first (`CACHE = 'tracker-vN'`: **bump it whenever an app file changes** when deploying with Options 2 or 3, or devices keep the old version (the Pages workflow stamps it automatically)), `habits.yaml` network-first, and never touches `/api/` or other origins. A navigation with `?signin` bypasses the cache so the `Sync: sign in` click can reach the Cloudflare Access login; the app then strips `?signin` from the address. Every file in `SHELL` must exist or the install fails (the smoke test checks this). Updates (#7): the shell is fetched with `cache: 'reload'` (Pages sends `max-age=600`); the new worker calls `skipWaiting()`/`clients.claim()`; the page checks `registration.update()` on foreground/`online` (at most once a minute) and on `controllerchange` reloads via `applyUpdate()`, deferred while a dialog is open, a field has focus or a sync runs (retried on focusout, dialog close, sync end and going hidden). The first install claiming the page doesn't reload. `BUILD` in index.html is stamped by the workflow and shown in Settings….

## Roadmap (MVP, complete)

Further work goes in GitHub Issues, not here.

1. ✅ **Load the config from `habits.yaml`** (DEPLOYMENT.md §1.4) — done
   - Fetch `habits.yaml`, network first. Fall back to the last valid cached copy, then to the embedded default. Under `file://`, use the embedded default.
   - If the fetched file is invalid, keep the last valid config and show `Config error: …` in the status bar.
   - The Habits… editor becomes a per-device **local override**. While one is active, the status bar shows `Config: local`, and a **Use deployed** button drops it.
   - Move the config out of the stored data shape (`yaml` is no longer saved with the data).
2. ✅ **Timestamps for merging** (DEPLOYMENT.md §1.1) — done
   - Store each value as `{n, t}` and give the note a `noteT`.
   - Add a v2 → v3 migration. Older backups must still import.
3. ✅ **Sync** (DEPLOYMENT.md §1.1, §2.5, §3.5, §4.5) — done
   - An adapter interface `pull()`/`push(data)`, merging per day and per habit with last-write-wins on `t`.
   - Pull when the app opens and when it returns to the foreground. Push 5 s after the last change, and when the app goes to the background.
   - A **Settings…** dialog to pick the adapter: off, Gist (ID and token), or same-origin `/api/data` (used by both Cloudflare and Tailscale).
   - A sync state cell in the status bar: `Synced 12:04`, `Offline`, `Sync: sign in` or `Sync error`.
4. ✅ **PWA** (DEPLOYMENT.md §1.2) — done
   - `manifest.webmanifest`, `sw.js` and icons (192, 512, and a 180 apple-touch icon) in the Win98 style.
   - Register the service worker only on http(s).
5. ✅ **Deployment targets** — done
   - ✅ Option 2: `functions/api/data.js` and `wrangler.toml` (§3.2). Future option, not deployed.
   - ✅ Option 3: `server/server.py` and `server/tracker.service` (§4.3–4.4). Future option, not deployed.
   - ✅ Option 1: `.github/workflows/pages.yml` runs all the tests on every push to `main` (and writes the habits.yaml change report to the run summary, without blocking), then publishes only `public/` to https://rpatel23.github.io/dinacharya-utility/ (Pages source: GitHub Actions). The deploy rewrites `CACHE` in the published `sw.js` to `tracker-<short sha>`, so Pages never needs a manual bump; Options 2 and 3 still do.

## Testing

```bash
pip install playwright     # Chromium may already be installed; otherwise: python -m playwright install chromium
python tests/smoke_test.py        # the app (file:// and http, config, data, sync, PWA)
python tests/server_test.py       # server/server.py, incl. two devices syncing through it
node tests/cf_function_test.mjs   # functions/api/data.js against an in-memory KV
python tests/config_diff_test.py  # tools/config_diff.py (needs pyyaml)
```

Extend the smoke test with each roadmap step. At minimum, cover config validation, every habit kind, migrations, and a merge of two diverging copies. Before finishing a UI change, take a screenshot at a width of 420px and check it.

## Owner context

`public/habits.yaml` is the owner's **live routine** (first version shipped in #8, first tracked day 2026-11-23, fresh start: the test data is wiped by hand per the reset procedure in #8, emptying the Gist and every device together). Groups: Morning (Ayurvedic and eye/voice/hair practice), Nutrition, Training (calisthenics Mon/Wed/Fri, runs Mon/Tue/Thu, track Sat, distance Sun), Work & study, Evening. The owner vetted every threshold; don't change it without being asked, and follow `docs/CONFIG-CHANGES.md` for any change to an existing habit. `protein` and `miles` are deliberately logged only (no min).

The tests don't use it: `tests/smoke_test.py` runs on `tests/fixture_habits.yaml` (the pre-#8 test routine) in a temp copy of `public/`, and only checks that the live file matches the embedded copy, loads with no Config error and fits 360px.
