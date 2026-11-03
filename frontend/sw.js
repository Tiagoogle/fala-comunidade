// Service worker: shell do app em cache (abre sem rede). Chamadas de API nunca são cacheadas.
const CACHE = "escuta-shell-v1";
const SHELL = ["./", "./index.html", "./app.js", "./styles.css", "./manifest.webmanifest", "./icone.svg"];

self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting())));
self.addEventListener("activate", (e) => e.waitUntil(
  caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || !url.pathname.startsWith(new URL(self.registration.scope).pathname)) return; // API: sempre rede
  e.respondWith(fetch(e.request).then((r) => { const copia = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copia)); return r; })
    .catch(() => caches.match(e.request).then((r) => r || caches.match("./index.html"))));
});
