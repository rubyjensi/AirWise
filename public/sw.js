// Development cache-busting Service Worker: always fetches fresh from network and clears all old caches
self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(keys.map((k) => caches.delete(k)));
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  // Always go network-first directly
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
