const CACHE_NAME = "etf-tracker-v1";
const SHELL = ["./", "./index.html", "./etf.html", "./app.js", "./style.css", "./manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  // Never cache data/API calls - ranking JSON and GitHub API must always be fresh
  if (url.hostname.includes("raw.githubusercontent.com") || url.hostname.includes("api.github.com")) {
    return;
  }
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
