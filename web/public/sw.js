/* Minimal OneChoice service worker — shell + static assets. */
const CACHE = "oc-shell-v1";
const PRECACHE = ["/", "/index.html", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png", "/apple-touch-icon.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  // Never cache API auth/data.
  if (url.pathname.startsWith("/v1/") || url.pathname === "/health") return;
  // Cache-first for static shell and dish/poster images.
  const staticish =
    url.origin === self.location.origin &&
    (PRECACHE.includes(url.pathname) ||
      url.pathname.startsWith("/assets/") ||
      url.pathname.startsWith("/dishes/") ||
      url.pathname.startsWith("/posters/") ||
      url.pathname.endsWith(".js") ||
      url.pathname.endsWith(".css") ||
      url.pathname.endsWith(".svg") ||
      url.pathname.endsWith(".png") ||
      url.pathname.endsWith(".jpg"));
  if (!staticish) return;
  event.respondWith(
    caches.open(CACHE).then(async (cache) => {
      const hit = await cache.match(req);
      if (hit) return hit;
      const res = await fetch(req);
      if (res.ok) cache.put(req, res.clone());
      return res;
    })
  );
});
