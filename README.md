# Daily Tracker

A minimalist, offline habit tracker in the style of a Windows 98 dev tool. It runs as a single HTML file, and a YAML file defines the habits. Each habit gets a daily level of **missed**, **min** or **max**. Habits can be daily checks, counters (for example water: 6 circles, min at 4) or number entries (miles), and each can have its own weekly schedule.

## Quick start

Open `public/index.html` in a browser. Your data is saved in the browser automatically. Use **Export…** now and then to keep a backup.

- **Day view:** tap a circle to cycle missed → min → max. On a counter, tap to set the count, or right-click to subtract.
- **Week view:** a table of the week with totals per habit. Click a day's header to open that day.
- **Habits…:** edit the habit config in the app.
- **Keys:** ← and → change the day, T jumps to today, W switches between Day and Week.

## Docs

- [`docs/CONFIG.md`](docs/CONFIG.md): the `habits.yaml` format
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md): running it on all your devices (GitHub Pages + Gist, Cloudflare Pages + Access, or Tailscale + a home box)
- [`CLAUDE.md`](CLAUDE.md): constraints and roadmap for development

## Status

v2 works as a standalone file. Sync, installing as a PWA and loading `habits.yaml` from the server are planned; see the roadmap in CLAUDE.md.

## License

App code: yours. Bundled js-yaml 4.1.0 is MIT-licensed (© Vitaly Puzrin); its license header is kept in `public/index.html`.
