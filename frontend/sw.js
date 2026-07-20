// App-shell caching only — API/stream/webhook requests always go to the
// network so dashboard data is never served stale.
const CACHE_NAME = 'market-system-shell-v1';
const SHELL_FILES = [
    './',
    './index.html',
    './styles.css',
    './app.js',
    './vendor/lightweight-charts.standalone.production.js',
    './manifest.json',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES))
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    const isApiOrLive = ['/api/', '/stream/', '/webhook/'].some((p) => url.pathname.startsWith(p));
    if (isApiOrLive || event.request.method !== 'GET') return; // let these hit the network untouched

    event.respondWith(
        caches.match(event.request).then((cached) => {
            const network = fetch(event.request)
                .then((res) => {
                    if (res.ok) caches.open(CACHE_NAME).then((cache) => cache.put(event.request, res.clone()));
                    return res;
                })
                .catch(() => cached);
            return cached || network;
        })
    );
});
