// Daily Tracker service worker: serves the app from its cache so it opens offline.
// Bump CACHE on every deploy that changes an app file (habits.yaml doesn't need it).
const CACHE = 'tracker-v1';
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
      || url.pathname.includes('/api/')) return;            // sync goes straight to network
  if (e.request.mode === 'navigate' && url.searchParams.has('signin')) return;
                                                             // "Sync: sign in" reload: let it reach the login page
  if (url.pathname.endsWith('/habits.yaml')) {               // config: network first, cache as fallback
    e.respondWith(fetch(e.request, { cache: 'no-cache' })
      .then(r => { if (r.ok) { const c = r.clone(); caches.open(CACHE).then(k => k.put('./habits.yaml', c)); } return r; })
      .catch(() => caches.match('./habits.yaml').then(r => r || Response.error())));
    return;
  }
  e.respondWith(caches.match(e.request, { ignoreSearch: true })
    .then(hit => hit || fetch(e.request)));
});
