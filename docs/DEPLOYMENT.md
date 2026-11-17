# Deployment: single-user, multi-device

How to run Daily Tracker on every device you own without running a server for it or making your data public.

All three options use the same app. Only where the files are hosted and where your data is synced changes.

| | Option 1: GitHub Pages + Gist | Option 2: Cloudflare Pages + Access | Option 3: Tailscale + home box |
|---|---|---|---|
| App hosted on | GitHub Pages (public URL) | Cloudflare Pages (login required) | A Raspberry Pi or NAS on your tailnet |
| Data synced to | A secret GitHub Gist | Cloudflare KV | A JSON file on the box |
| Always-on hardware | None | None | Yes (about 3 W) |
| Who can reach it | The app: anyone. The data: anyone who has the Gist URL | Only your email, after login | Only devices on your tailnet |
| Cost | Free | Free tier | About $50 one-time for the box |
| Setup time | About 15 min | About 1 hr | About 1 hr |
| Offline use | Yes | Yes | Yes |
| Sync away from home | Yes | Yes | Only with Tailscale connected |

**Recommendation:** start with Option 1. Move to Option 2 if you want the page and the data to need a login. Option 3 suits you if you already have an always-on box, or want everything to stay on your own network.

---

## 1. Shared foundation

### 1.1 Local-first model

The app always reads and writes its own `localStorage` first. That keeps it instant and lets it work offline. A sync adapter copies your data to and from one remote copy:

```
device A ─┐                     ┌─ device B
 localStorage ⇄ sync adapter ⇄ remote copy ⇄ sync adapter ⇄ localStorage
```

- **When it pulls:** when the app opens, and when it comes back to the foreground.
- **When it pushes:** 5 seconds after your last change, and when the app goes to the background. Waiting for a pause keeps Gist revisions and KV writes low.
- **How it merges:** every habit value for every day stores `t`, the time it was last changed. When two copies disagree on the same day and habit, the newer `t` wins. With one person using the app, conflicts are rare and never lose more than a single tap.
- **Config:** `habits.yaml` is not part of sync. It's a file deployed with the app (see 1.4). Sync carries only your entries.

Each adapter has the same two methods:

```js
pull(): Promise<Data | null>   // Data = { days: { 'YYYY-MM-DD': { v:{id:{n,t}}, note, noteT } } }
push(data: Data): Promise<void>
```

Changing deployment later means swapping the adapter. The app and your data format stay the same.

### 1.2 Making it a PWA

A PWA (progressive web app) is a normal website that a phone can install like an app. It gets a home-screen icon, opens full-screen without browser bars, and works offline. A browser offers to install a site only if it meets three requirements:

1. **It's served over HTTPS.** All three options here provide HTTPS. That's also why opening the file from `file://` can't be installed.
2. **It has a web app manifest.** This is a small JSON file with the app's name, icons and display mode.
3. **It has a service worker.** This is a script that caches the app so it opens with no network.

The tracker is still one HTML file. The PWA adds a few small files around it:

```
public/
  index.html             ← daily-tracker.html, renamed
  habits.yaml            ← your habits config (see 1.4)
  manifest.webmanifest
  sw.js
  icon-192.png
  icon-512.png
  apple-touch-icon.png   ← 180×180, used by iOS
```

**manifest.webmanifest**

```json
{
  "name": "Daily Tracker",
  "short_name": "Tracker",
  "start_url": "./",
  "scope": "./",
  "display": "standalone",
  "background_color": "#008080",
  "theme_color": "#000080",
  "icons": [
    { "src": "icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

**sw.js** serves the app from its cache first and never caches sync calls:

```js
const CACHE = 'tracker-v1';            // bump on every deploy
const SHELL = ['./', './index.html', './habits.yaml', './manifest.webmanifest',
               './icon-192.png', './icon-512.png', './apple-touch-icon.png'];

self.addEventListener('install', e =>
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL))));

self.addEventListener('activate', e =>
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))));

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin
      || url.pathname.includes('/api/')) return;          // sync goes straight to network
  if (url.pathname.endsWith('/habits.yaml')) {             // config: network first, cache as fallback
    e.respondWith(fetch(e.request, { cache: 'no-cache' })
      .then(r => { if (r.ok) caches.open(CACHE).then(c => c.put('./habits.yaml', r.clone())); return r; })
      .catch(() => caches.match('./habits.yaml')));
    return;
  }
  e.respondWith(caches.match(e.request, { ignoreSearch: true })
    .then(hit => hit || fetch(e.request)));
});
```

`habits.yaml` is fetched from the network first, so a config change appears the next time the app opens, without bumping `CACHE`. When the device is offline, the app uses the last copy it downloaded.

**Add to `<head>` in index.html:**

```html
<link rel="manifest" href="manifest.webmanifest" crossorigin="use-credentials">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<meta name="theme-color" content="#000080">
<script>
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js');
</script>
```

The shipped app registers the worker from its main script, and only when served over http(s). Its `public/sw.js` also adds two things to the snippet above. A navigation to `./?signin=…` skips the cache, so the **Sync: sign in** click (see 3.5) reaches the Cloudflare Access login instead of the cached page. And the `habits.yaml` response is cloned before the body is read.

`crossorigin="use-credentials"` matters only for Option 2. Behind Cloudflare Access, the browser has to send your login cookie when it fetches the manifest, or the install fails. It does no harm in the other options.

**Updating the app:** change the `CACHE` name (`tracker-v2`, and so on) and deploy. Devices download the new version in the background and switch to it the next time the app opens. Close it fully and reopen it if you want the update right away.

### 1.3 Installing it on your devices

**iPhone / iPad**

1. Open the site's URL in Safari. On iOS 16.4 and later, Chrome and Edge also work.
2. Tap **Share** (the square with an arrow), then **Add to Home Screen**.
3. Keep **Open as Web App** turned on if it's shown, and tap **Add**.

On iPhone, the home-screen app keeps its storage separate from Safari. Data you entered in a Safari tab won't appear in the installed app, so install the app first and let sync pull your data. Installed apps are also exempt from Safari's rule that deletes data for sites you haven't used in 7 days.

**Android**

1. Open the URL in Chrome.
2. Tap **Install** on the banner, or open **⋮** and choose **Add to Home screen**, then **Install**.

**Desktop (Chrome / Edge)**

Click the install icon at the right end of the address bar, or open **⋮** and choose **Cast, save and share**, then **Install page as app**. The app then opens in its own window.

### 1.4 The habits config (habits.yaml)

The file format is documented in `CONFIG.md`. This section covers where the file lives and how a change reaches your devices.

**One source of truth.** `public/habits.yaml` is deployed along with the app, and every device reads that same file. Configs never drift apart between devices, and Git keeps the history (who changed what and when, and how to revert).

**Editing it**

| Option | How to edit | When it reaches your devices |
|---|---|---|
| 1. GitHub Pages | Open the file on github.com, tap the pencil, then **Commit**. This works from your phone. | About 1 min (Pages rebuild), then the next time the app opens |
| 2. Cloudflare Pages | The same as Option 1 if the repo is connected to Pages. Otherwise edit it locally and run `wrangler pages deploy`. | About 1 min, then the next time the app opens |
| 3. Tailscale box | Edit `public/habits.yaml` on the box, or `git pull` there | The next time the app opens |

**Trying out a change.** The app's **Habits…** editor still works, but what you save there is a **local override** on that device only. While an override is active, the status bar shows **Config: local**. Once the change works, click **Save .yaml** and commit the file, then choose **Use deployed** to drop the override.

**Safety rules the app follows**

- **Invalid file:** the app validates `habits.yaml` every time it loads it. If the deployed file has an error, the app keeps using the last valid version and shows **Config error** with the problem (YAML syntax errors include the line number), so a typo never stops you tracking.
- **History follows ids, not names:** your entries are stored by habit **id**.
  - Renaming a habit (`name:`) keeps its history.
  - Removing a habit hides it but keeps its data. Adding the same id back brings its history back.
  - Changing an id starts a new, empty habit.
- **Changing thresholds:** a new `min`/`max` or `count` applies to past days too, because levels are calculated from the stored values whenever they're shown. To keep old days scored the old way, give the habit an `end:` date and add a new id with a `start:` date.

**First run on each device:** open **Settings…** in the app, paste the sync details (a Gist ID and token for Option 1; nothing for Options 2 and 3), and the app pulls your data.

---

## 2. Option 1: GitHub Pages + secret Gist

GitHub hosts both the app files and the data. Nothing runs on your side.

### 2.1 How it fits together

```
phone/laptop ──HTTPS──▶ <you>.github.io/daily-tracker      (app files, public)
       └──────HTTPS──▶ api.github.com/gists/<id>          (data, token required to write)
```

### 2.2 Host the app on GitHub Pages

1. Create a repo, for example `daily-tracker`. It must be **public** for Pages on a free plan. The repo holds only the app code, never your data.
2. Commit the `public/` files to the root of the repo, or to a `/docs` folder.
3. Go to **Settings → Pages → Build and deployment**. Choose **Deploy from a branch**, branch `main`, folder `/ (root)` or `/docs`, then click **Save**.
4. About a minute later the site is live at `https://<you>.github.io/daily-tracker/`, with HTTPS included.

To update it, push a commit. Remember to bump `CACHE` in `sw.js`.

### 2.3 Create the data Gist

1. Go to gist.github.com and create a **secret** gist with one file, `tracker.json`, containing `{}`.
2. Copy the Gist ID, which is the long hex string at the end of its URL.

> **"Secret" means unlisted, not private.** The Gist won't show up in search or on your profile, but anyone who has its URL can read it. If that's not acceptable for your health and habit data, either encrypt it before upload (see 2.6) or use Option 2.

### 2.4 Create a token that can only touch Gists

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token**.
2. Tick **only** the `gist` scope and set an expiry (for example, 1 year).
3. Paste the token into the app's Settings once on each device. It's stored in that device's `localStorage`.

If a device is lost, revoke the token in GitHub and make a new one. A token with only the `gist` scope can't touch your repos or your account.

### 2.5 The adapter

```js
const api = id => `https://api.github.com/gists/${id}`;
const hdr = tok => ({ Authorization: `Bearer ${tok}`, Accept: 'application/vnd.github+json' });

async function pull({ id, tok }) {
  const g = await (await fetch(api(id), { headers: hdr(tok), cache: 'no-store' })).json();
  const f = g.files['tracker.json'];
  const text = f.truncated ? await (await fetch(f.raw_url)).text() : f.content;  // files >1 MB come back truncated
  return JSON.parse(text || '{}');
}

async function push({ id, tok }, data) {
  await fetch(api(id), {
    method: 'PATCH', headers: hdr(tok),
    body: JSON.stringify({ files: { 'tracker.json': { content: JSON.stringify(data) } } })
  });
}
```

### 2.6 Notes

- **History:** every push is a Gist revision. On the Gist page you can open **Revisions** to see or restore any earlier state.
- **Limits:** authenticated API calls are capped at 5,000 an hour, which the pause before each push keeps far out of reach.
- **Optional encryption:** derive a key from a passphrase (WebCrypto PBKDF2, then AES-GCM) and upload only the ciphertext. Someone with the URL then sees only unreadable data. The cost is entering the passphrase on each device, and if you lose it, the data can't be recovered.

---

## 3. Option 2: Cloudflare Pages + KV, behind Cloudflare Access

Cloudflare hosts the app and a small sync API. Access sits in front of both, so nothing loads until you've logged in with your email. Cloudflare runs it all, so you don't maintain a server.

### 3.1 How it fits together

```
phone/laptop ──HTTPS──▶ Cloudflare Access (email one-time code)
                              │ allowed
                              ▼
                     daily-tracker.pages.dev
                       ├── /            static app (public/)
                       └── /api/data    Pages Function ⇄ KV namespace
```

- **Pages** serves the static files.
- **Pages Functions** are small scripts under `functions/` that run on request. They give you an API without a server.
- **KV** is a key-value store. Your whole data set is one value.
- **Access** (part of Cloudflare Zero Trust, free for up to 50 users) puts a login in front of the site. You log in with a one-time code sent to your email.

### 3.2 Project layout

```
daily-tracker/
  public/               ← app files from 1.2
  functions/api/data.js
  wrangler.toml
```

**wrangler.toml**

```toml
name = "daily-tracker"
pages_build_output_dir = "./public"
compatibility_date = "2026-11-01"

[[kv_namespaces]]
binding = "KV"
id = "<namespace id from step 2>"
```

**functions/api/data.js**

```js
export async function onRequestGet({ env }) {
  return new Response(await env.KV.get('data') ?? '{}',
    { headers: { 'content-type': 'application/json', 'cache-control': 'no-store' } });
}

export async function onRequestPut({ request, env }) {
  const text = await request.text();
  JSON.parse(text);                                   // reject anything that isn't JSON
  await env.KV.put('data', text);
  await env.KV.put(`backup:${new Date().toISOString().slice(0, 10)}`, text,
                   { expirationTtl: 60 * 60 * 24 * 90 });   // daily snapshot, kept 90 days
  return new Response(null, { status: 204 });
}
```

### 3.3 Deploy

```bash
npm i -g wrangler
wrangler login                                   # 1. opens a browser to sign in to Cloudflare
wrangler kv namespace create TRACKER             # 2. copy the id it prints into wrangler.toml
wrangler pages deploy                            # 3. first run creates the project, then uploads
```

The site is now at `https://daily-tracker.pages.dev`. Run `wrangler pages deploy` again for each update, after bumping `CACHE`. You can also connect the repo in the dashboard so every push deploys automatically.

### 3.4 Lock it down with Access

1. In the Cloudflare dashboard, open **Zero Trust**. The first time, it asks you to choose a team name and the Free plan.
2. Go to **Access → Applications → Add an application → Self-hosted**.
3. Add both domains:
   - `daily-tracker.pages.dev`
   - `*.daily-tracker.pages.dev` (this covers preview URLs, which would otherwise be open)
4. Set the session duration, for example **1 month**, so you aren't asked to log in often.
5. Add a policy: **Action Allow**, **Include → Emails →** your email address.
6. Under login methods, keep **One-time PIN**.

From then on, any visit, including to `/api/data`, needs your email login first.

### 3.5 The adapter

```js
async function pull() {
  const r = await fetch('api/data', { credentials: 'include', cache: 'no-store' });
  if (r.redirected || !r.headers.get('content-type')?.includes('json')) throw new Error('LOGIN');
  return r.json();
}

async function push(data) {
  const r = await fetch('api/data', { method: 'PUT', credentials: 'include', body: JSON.stringify(data) });
  if (r.redirected || !r.ok) throw new Error('LOGIN');
}
```

When the Access session expires, sync requests get redirected to the login page instead of returning data. The app catches the `LOGIN` error and shows **Sync: sign in** in the status bar. Click it to reload the page and log in. The app doesn't reload by itself, so nothing you're typing is lost. Tracking keeps working offline the whole time.

The app's adapter also passes `redirect: 'manual'`. Without it, the browser would follow the redirect to the Access login domain, fail the cross-origin check, and report it as a network error ("Offline") instead of a sign-in.

### 3.6 Notes

- **Free-tier limits:** KV allows 100,000 reads and 1,000 writes a day. With the pause before each push and one snapshot a day, you'll use a few dozen.
- **Backups:** your daily snapshots are `backup:YYYY-MM-DD` keys. List them with `wrangler kv key list --binding KV`.
- **Custom domain (optional):** attach a domain you own in **Pages → Custom domains**, then add it to the Access application too.

---

## 4. Option 3: Tailscale + a low-power home box

This is the same setup as running it on your desktop, except a Raspberry Pi, NAS or old laptop stays on instead. Nothing is exposed to the internet, and your data never leaves hardware you own.

### 4.1 How it fits together

```
phone/laptop (Tailscale on) ──WireGuard──▶ tracker.<tailnet>.ts.net (HTTPS via tailscale serve)
                                                 │
                                           127.0.0.1:8080  tiny server
                                                 ├── /          public/ files
                                                 └── /api/data  data.json (+ daily copies)
```

### 4.2 The box

Any always-on Linux machine that can run Python 3 works. A Raspberry Pi 4 or 5, or a Pi Zero 2 W, draws a few watts.

1. Install Tailscale: `curl -fsSL https://tailscale.com/install.sh | sh`, then run `sudo tailscale up`.
2. In the Tailscale admin console, under **DNS**, turn on **MagicDNS** and **HTTPS Certificates**.
3. Rename the machine to `tracker` in the console, so its address is `tracker.<tailnet>.ts.net`.

### 4.3 Tiny server: server.py

```python
import json, shutil, datetime, pathlib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).parent
DATA = ROOT / "data" / "data.json"
DATA.parent.mkdir(exist_ok=True)

class H(SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=str(ROOT / "public"), **k)
    def do_GET(s):
        if s.path != "/api/data": return super().do_GET()
        body = DATA.read_bytes() if DATA.exists() else b"{}"
        s.send_response(200); s.send_header("Content-Type", "application/json")
        s.send_header("Cache-Control", "no-store"); s.end_headers(); s.wfile.write(body)
    def do_PUT(s):
        if s.path != "/api/data": return s.send_error(404)
        body = s.rfile.read(int(s.headers["Content-Length"])); json.loads(body)
        tmp = DATA.with_suffix(".tmp"); tmp.write_bytes(body); tmp.replace(DATA)   # atomic write
        snap = DATA.parent / f"{datetime.date.today()}.json"
        if not snap.exists(): shutil.copy(DATA, snap)                          # daily copy
        s.send_response(204); s.end_headers()

ThreadingHTTPServer(("127.0.0.1", 8080), H).serve_forever()
```

It listens only on `127.0.0.1`. Tailscale is the only way in.

### 4.4 Run it on boot, and expose it to the tailnet

`/etc/systemd/system/tracker.service`

```ini
[Unit]
Description=Daily Tracker
After=network-online.target

[Service]
WorkingDirectory=/home/pi/daily-tracker
ExecStart=/usr/bin/python3 server.py
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now tracker
sudo tailscale serve --bg 8080        # HTTPS on https://tracker.<tailnet>.ts.net → localhost:8080
```

Use `tailscale serve`, not `tailscale funnel`. Funnel publishes to the public internet.

### 4.5 The adapter

This is the same as Option 2's adapter, without the login handling. `fetch('api/data')` for GET and PUT.

### 4.6 Notes

- **Phones:** sync works only while the Tailscale app is connected. You can still track while it's off, and the app syncs the next time it connects. To make this automatic, turn on Tailscale's **Always-on VPN** (Android) or **On Demand** (iOS).
- **Backups:** the box is a single point of failure. Copy `data/` somewhere else nightly, for example with a cron job that runs `rclone` to your Google Drive. You can also use the app's **Export** button from time to time.
- **Updates:** `git pull` (or copy the files over) into `public/`, then bump `CACHE`. You don't need to restart the server.

---

## 5. Moving between options

1. In the old deployment, click **Export…** to save a JSON backup.
2. Deploy the new option and install it on one device.
3. **Import…** the backup there. Sync pushes it up.
4. Install the app on your other devices and let them pull.

Copy `public/habits.yaml` along with the other app files. The data format is the same in every option, so you only re-enter sync settings and nothing else changes.
