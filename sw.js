const CACHE_NAME = "etf-tracker-v4";
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

// Network-first for the app shell: always try to get the latest version first,
// only fall back to the cached copy when offline. This is an actively-edited app
// where freshness matters more than instant offline load, and a cache-first
// strategy here previously served stale CSS/JS for a long time after real edits.
self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.hostname.includes("raw.githubusercontent.com") || url.hostname.includes("api.github.com")) {
    return;
  }
  event.respondWith(
    fetch(event.request)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return res;
      })
      .catch(() => caches.match(event.request))
  );
});
