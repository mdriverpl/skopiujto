// Store only public fallback assets; never cache account pages, API data or documents.
const CACHE = 'edokumenty-public-v1';
const PUBLIC_ASSETS = ['/offline.html', '/icon-192.png', '/icon-512.png', '/icon-maskable-512.png'];
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(PUBLIC_ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(keys
    .filter(key => key.startsWith('edokumenty-public-') && key !== CACHE).map(key => caches.delete(key))))
    .then(() => self.clients.claim()));
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;
  if (event.request.mode === 'navigate') {
    event.respondWith(fetch(event.request).catch(() => caches.match('/offline.html')));
  } else if (PUBLIC_ASSETS.includes(url.pathname)) {
    event.respondWith(caches.match(url.pathname).then(cached => cached || fetch(event.request)));
  }
});
function notificationUrl(value) {
  try {
    const url = new URL(value || '/', self.location.origin);
    if (url.origin !== self.location.origin || url.pathname !== '/') return self.location.origin + '/';
    const section = url.searchParams.get('section');
    return self.location.origin + (['mail', 'tasks', 'calendar'].includes(section) ? '/?section=' + section : '/');
  } catch { return self.location.origin + '/'; }
}
self.addEventListener('push', event => {
  let payload = {};
  try { payload = event.data?.json() || {}; } catch {}
  event.waitUntil(self.registration.showNotification(payload.title || 'eDokumenty', {
    body: payload.body || 'Nowe zdarzenie w eDokumentach.',
    icon: '/icon-192.png', badge: '/icon-192.png',
    tag: payload.tag || 'edokumenty',
    data: { url: notificationUrl(payload.url) }
  }));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const target = notificationUrl(event.notification.data?.url);
  event.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async clients => {
    for (const client of clients) {
      if (new URL(client.url).origin !== self.location.origin) continue;
      if (client.navigate) await client.navigate(target);
      return client.focus();
    }
    return self.clients.openWindow(target);
  }));
});
