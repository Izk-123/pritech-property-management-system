/**
 * Pritech PMS Service Worker
 *
 * Caching strategies:
 *   - App shell (HTML pages): NetworkFirst with 3-second timeout
 *   - Static assets (CSS, JS, icons): CacheFirst with 30-day expiry
 *   - API GET requests: NetworkFirst with 5-second timeout
 *   - API POST/PATCH/DELETE: queued offline, synced on reconnect
 *   - Media/images: StaleWhileRevalidate
 *
 * Works across all tenant subdomains. The tenant hostname is used
 * as a cache key prefix so tenants never see each other's data.
 */

importScripts('https://storage.googleapis.com/workbox-cdn/releases/7.1.0/workbox-sw.js');

workbox.setConfig({ debug: false });

const { registerRoute } = workbox.routing;
const { NetworkFirst, CacheFirst, StaleWhileRevalidate } = workbox.strategies;
const { ExpirationPlugin } = workbox.expiration;
const { CacheableResponsePlugin } = workbox.cacheableResponse;
const { BackgroundSyncPlugin } = workbox.backgroundSync;

// ── Tenant-aware cache names ──────────────────────────────────────
// Each tenant subdomain gets its own cache bucket, so
// lakeview.pms.pritechmw.com can never leak data into
// sunbird.pms.pritechmw.com's cache.
const tenantScope = self.location.hostname
    .replace(/\./g, '_')
    .toLowerCase();

const CACHE_VERSION = 'v1';
const SHELL_CACHE = `pritech-shell-${tenantScope}-${CACHE_VERSION}`;
const STATIC_CACHE = `pritech-static-${tenantScope}-${CACHE_VERSION}`;
const API_CACHE = `pritech-api-${tenantScope}-${CACHE_VERSION}`;
const MEDIA_CACHE = `pritech-media-${tenantScope}-${CACHE_VERSION}`;

const OFFLINE_URL = '/offline/';

// ── 1. App shell (HTML pages) ─────────────────────────────────────
// NetworkFirst with a 3-second timeout: online users get fresh HTML,
// offline users get the cached shell.
registerRoute(
    ({ request }) => request.mode === 'navigate',
    new NetworkFirst({
        cacheName: SHELL_CACHE,
        networkTimeoutSeconds: 3,
        plugins: [
            new CacheableResponsePlugin({ statuses: [0, 200] }),
        ],
    })
);

// ── 2. Static assets (CSS, JS, fonts) ────────────────────────────
registerRoute(
    ({ request }) =>
        ['style', 'script', 'font', 'worker'].includes(request.destination),
    new CacheFirst({
        cacheName: STATIC_CACHE,
        plugins: [
            new CacheableResponsePlugin({ statuses: [0, 200] }),
            new ExpirationPlugin({
                maxEntries: 100,
                maxAgeSeconds: 30 * 24 * 60 * 60,  // 30 days
            }),
        ],
    })
);

// ── 3. API GET requests ──────────────────────────────────────────
// NetworkFirst with a 5-second timeout: fresh data when possible,
// cached data during outages.
registerRoute(
    ({ url, request }) =>
        url.pathname.startsWith('/api/') && request.method === 'GET',
    new NetworkFirst({
        cacheName: API_CACHE,
        networkTimeoutSeconds: 5,
        plugins: [
            new CacheableResponsePlugin({ statuses: [0, 200] }),
            new ExpirationPlugin({
                maxEntries: 100,
                maxAgeSeconds: 60 * 60,  // 1 hour
            }),
        ],
    })
);

// ── 4. API mutations — Background Sync queue ─────────────────────
// POST/PATCH/DELETE requests are queued in IndexedDB and replayed
// when connectivity returns. This is what keeps check-ins,
// housekeeping updates, and payment recording working offline.
const bgSyncPlugin = new BackgroundSyncPlugin('pritech-sync-queue', {
    maxRetentionTime: 72 * 60,  // 72 hours (in minutes)
    onSync: async ({ queue }) => {
        let entry;
        while ((entry = await queue.shiftRequest())) {
            try {
                await fetch(entry.request.clone());
                // Notify all open tabs that a sync completed
                const clients = await self.clients.matchAll();
                clients.forEach((client) => {
                    client.postMessage({
                        type: 'SYNC_COMPLETE',
                        url: entry.request.url,
                    });
                });
            } catch (error) {
                await queue.unshiftRequest(entry);
                throw error;
            }
        }
    },
});

registerRoute(
    ({ url, request }) =>
        url.pathname.startsWith('/api/') &&
        ['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method),
    new NetworkFirst({
        cacheName: `${API_CACHE}-mutations`,
        plugins: [bgSyncPlugin],
    }),
    'POST'  // Workbox needs the method explicitly for BackgroundSync
);

// ── 5. Media (property photos, documents) ────────────────────────
registerRoute(
    ({ request, url }) =>
        request.destination === 'image' ||
        url.pathname.startsWith('/media/'),
    new StaleWhileRevalidate({
        cacheName: MEDIA_CACHE,
        plugins: [
            new CacheableResponsePlugin({ statuses: [0, 200] }),
            new ExpirationPlugin({
                maxEntries: 200,
                maxAgeSeconds: 7 * 24 * 60 * 60,  // 7 days
            }),
        ],
    })
);

// ── 6. Offline fallback ──────────────────────────────────────────
// When a navigation request fails completely, show the offline page.
self.addEventListener('fetch', (event) => {
    if (event.request.mode !== 'navigate') return;

    event.respondWith(
        fetch(event.request).catch(async () => {
            const cache = await caches.open(SHELL_CACHE);
            const cachedPage = await cache.match(event.request);
            if (cachedPage) return cachedPage;
            const offlinePage = await cache.match(OFFLINE_URL);
            return offlinePage || new Response(
                '<h1>Offline</h1><p>Pritech PMS is offline. Please reconnect.</p>',
                { headers: { 'Content-Type': 'text/html' } }
            );
        })
    );
});

// ── 7. Precache the app shell ────────────────────────────────────
self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(SHELL_CACHE).then((cache) => {
            return cache.addAll([
                '/',
                '/offline/',
                '/static/icons/icon-192.png',
                '/static/icons/icon-512.png',
            ]);
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys
                    .filter((key) => !key.includes(CACHE_VERSION) || 
                                     !key.includes(tenantScope))
                    .map((key) => caches.delete(key))
            );
        })
    );
    self.clients.claim();
});