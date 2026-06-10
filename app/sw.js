/* Fala Comunidade — service worker (offline-first)
 * Pré-cacheia o shell do app; navegação e estáticos saem do cache primeiro,
 * com atualização em segundo plano. Os dados ficam no localStorage.
 */
const VERSAO = 'fala-comunidade-v1.0.0';

const SHELL = [
  './',
  './index.html',
  './manifest.webmanifest',
  './css/app.css',
  './js/util.js',
  './js/ia.js',
  './js/db.js',
  './js/stats.js',
  './js/views.js',
  './js/app.js',
  './icons/icon.svg',
  './icons/maskable.svg',
  './icons/icon-180.png',
  './icons/icon-192.png',
  './icons/icon-512.png',
];

self.addEventListener('install', (e) => {
  e.waitUntil(
    caches.open(VERSAO).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((chaves) => Promise.all(chaves.filter((k) => k !== VERSAO).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (e) => {
  const url = new URL(e.request.url);
  // Nunca interceptar chamadas externas (ex.: API do Claude no modo online).
  if (url.origin !== self.location.origin || e.request.method !== 'GET') return;

  e.respondWith(
    caches.match(e.request, { ignoreSearch: true }).then((emCache) => {
      const rede = fetch(e.request)
        .then((resp) => {
          if (resp && resp.ok) {
            const copia = resp.clone();
            caches.open(VERSAO).then((cache) => cache.put(e.request, copia));
          }
          return resp;
        })
        .catch(() => emCache);
      return emCache || rede;
    })
  );
});
