/* OneChoice service worker — cache shell + dish/poster images */
const CACHE = "onechoice-shell-v12";
const SHELL = [
  "/",
  "/result",
  "/execute",
  "/lista",
  "/history",
  "/profile",
  "/auth",
  "/static/app.css",
  "/static/app.js",
  "/manifest.webmanifest",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
  "/static/icons/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

function isAssetRequest(url) {
  return (
    url.pathname.startsWith("/assets/dishes/") ||
    url.pathname.startsWith("/assets/posters/") ||
    url.pathname.startsWith("/api/media/dish") ||
    url.pathname.startsWith("/api/media/poster") ||
    url.pathname.startsWith("/static/icons/")
  );
}

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Network-first for HTML navigations (fresh decisions), cache fallback
  if (req.mode === "navigate" || (req.headers.get("accept") || "").includes("text/html")) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          const copy = res.clone();
          caches.open(CACHE).then((c) => c.put(req, copy));
          return res;
        })
        .catch(() => caches.match(req).then((hit) => hit || caches.match("/")))
    );
    return;
  }

  // Cache-first for shell + media images
  if (
    url.pathname.startsWith("/static/") ||
    url.pathname === "/manifest.webmanifest" ||
    url.pathname === "/sw.js" ||
    isAssetRequest(url)
  ) {
    event.respondWith(
      caches.match(req).then((hit) => {
        if (hit) return hit;
        return fetch(req).then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(CACHE).then((c) => c.put(req, copy));
          }
          return res;
        });
      })
    );
  }
});
