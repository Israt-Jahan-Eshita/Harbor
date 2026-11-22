const CACHE_NAME = "harbor-shell-v1";
const PRECACHE_URLS = [
  "/",
  "/dashboard",
  "/manifest.json",
  "/icons/icon-192.svg",
  "/icons/icon-512.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(PRECACHE_URLS).catch(() => undefined)),
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))),
      ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  if (req.cache === "only-if-cached" && req.mode !== "same-origin") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Network-first with retry and exact-route cache fallback (never serve '/' HTML for another route)
  event.respondWith(
    fetch(req)
      .catch(() => fetch(req.url))
      .then((resp) => {
        if (resp && resp.ok && (req.mode === "navigate" || url.pathname.startsWith("/_next/static") || url.pathname.startsWith("/icons"))) {
          const copy = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(req, copy)).catch(() => undefined);
        }
        return resp;
      })
      .catch(async () => {
        const cached = await caches.match(req);
        if (cached) return cached;
        return new Response("Offline", { status: 503, statusText: "Offline" });
      }),
  );
});

self.addEventListener("push", (event) => {
  let title = "Harbor";
  let body = "ওষুধের সময় হয়েছে";
  if (event.data) {
    try {
      const payload = event.data.json();
      if (payload && typeof payload.title === "string") title = payload.title;
      if (payload && typeof payload.body === "string") body = payload.body;
    } catch {
      /* keep generic disease-free text */
    }
  }
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: "/icons/icon-192.svg",
      badge: "/icons/icon-192.svg",
      tag: "harbor-reminder",
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ("focus" in client) return client.focus();
      }
      if (self.clients.openWindow) return self.clients.openWindow("/dashboard");
      return undefined;
    }),
  );
});

