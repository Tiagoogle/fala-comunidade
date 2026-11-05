// Service worker: guarda SÓ o shell do app (lista explícita), para abrir sem rede.
// Respostas da API nunca passam por aqui: contêm dados de manifestações e não podem ir para cache.
const CACHE = "escuta-shell-v2";
const SHELL = ["index.html", "app.js", "config.js", "styles.css", "manifest.webmanifest", "icone.svg"];
const base = new URL(self.registration.scope).pathname;
const caminhosShell = new Set([base, ...SHELL.map((f) => base + f)]);

self.addEventListener("install", (e) => e.waitUntil(caches.open(CACHE).then((c) => c.addAll(["./", ...SHELL])).then(() => self.skipWaiting())));
self.addEventListener("activate", (e) => e.waitUntil(
  caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())));
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin || !caminhosShell.has(url.pathname)) return;
  e.respondWith(fetch(e.request).then((r) => { if (r.ok) { const copia = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copia)); } return r; })
    .catch(() => caches.match(e.request).then((r) => r || caches.match("./"))));
});
