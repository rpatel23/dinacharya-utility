# Daily Tracker

A minimalist, offline habit tracker in the style of a Windows 98 dev tool. It runs as a single HTML file, and a YAML file defines the habits. Each habit gets a daily level of **missed**, **min** or **max**. Habits can be daily checks, counters (for example water: 6 circles, min at 4) or number entries (miles), and each can have its own weekly schedule.

## Quick start

**Live app:** https://rpatel23.github.io/dinacharya-utility/. Install it to the home screen, then turn on Gist sync in **Settings…** (see `docs/DEPLOYMENT.md` §2.3–2.4).

**Locally:** open `public/index.html` in a browser. Your data is saved in the browser automatically. Use **Export…** now and then to keep a backup.

- **Day view:** tap a circle to cycle missed → min → max. On a counter, tap to set the count, or right-click to subtract.
- **Week view:** a table of the week with totals per habit. Click a day's header to open that day.
- **Habits…:** try out config changes. What you save there is a local override on that device only (the status bar shows **Config: local**). **Use deployed** drops it.
- **Config:** when served over http(s), the app loads `habits.yaml` from next to `index.html`, falls back to the last valid copy when offline, and keeps that copy if the file has an error (shown as **Config error** in the status bar). Opened from `file://`, it uses the copy embedded in `index.html`.
- **Settings…:** turn on sync, either to a secret GitHub Gist or to the server's own `/api/data` (Cloudflare or Tailscale). The status bar shows the sync state; click it to sync now. See `docs/DEPLOYMENT.md`.
- **Keys:** ← and → change the day, T jumps to today, W switches between Day and Week.

## Docs

- [`docs/CONFIG.md`](docs/CONFIG.md): the `habits.yaml` format
- [`docs/ROUTINE-BRIEF.md`](docs/ROUTINE-BRIEF.md): brief for designing your routine (`habits.yaml`) with an AI agent
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): running it on all your devices. In use: GitHub Pages + Gist. Future migration options: Cloudflare Pages + Access, or Tailscale + a home box
- [`CLAUDE.md`](CLAUDE.md): constraints and roadmap for development

## Status

**MVP complete** (Nov 2026). The app is deployed to GitHub Pages and syncs across devices through a secret Gist. It works as a standalone file, loads `habits.yaml` from the server, syncs with timestamped merging (data format v3), and installs as an app (PWA). Each push to `main` runs the tests and then deploys.

The repo also holds the code for the two future migration options: a Cloudflare Pages Function (`functions/`, `wrangler.toml`) and a Tailscale home-box server (`server/`). Both are tested in CI but not deployed.

Work is tracked in [GitHub Issues](https://github.com/rpatel23/dinacharya-utility/issues).

## License

App code: yours. Bundled js-yaml 4.1.0 is MIT-licensed (© Vitaly Puzrin); its license header is kept in `public/index.html`.
