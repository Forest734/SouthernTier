// Service worker: keeps the app's own files, its data and the tiles it has shown, so the map opens
// with no signal (the imagery and hillshade, streamed from NYS and USGS, need one). Always asks the
// network first, so a new version of the app or its data shows up at once.
//
// Only this site's own files go through here.

const CACHE = "southerntier-v1";
const DATA = ["counties", "mask", "labels", "open_space", "wma", "roads", "trail_routes", "trails", "old_roads"];
const FILES = [
  "./", "index.html", "styles.css", "app.js", "style.js", "lib.js", "manifest.webmanifest", "icons/icon.svg",
  "vendor/maplibre-gl/maplibre-gl.mjs", "vendor/maplibre-gl/maplibre-gl-worker.mjs", "vendor/maplibre-gl/maplibre-gl.css",
  "fonts/DejaVuSans.woff2", "fonts/DejaVuSans-Oblique.woff2", "fonts/DejaVuSans-Bold.woff2",
  "data/meta.json", ...DATA.map((d) => `data/${d}.geojson`),
];

self.addEventListener("install", (event) => {
  self.skipWaiting();
  // Best effort: a missing file mustn't stop the worker installing.
  event.waitUntil(caches.open(CACHE).then((cache) => Promise.allSettled(FILES.map((f) => cache.add(f)))));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      // Other apps share this origin (forest734.github.io, and localhost:8000 in development) and
      // its caches: drop only this app's old ones.
      for (const key of await caches.keys()) if (key.startsWith("southerntier-") && key !== CACHE) await caches.delete(key);
      await self.clients.claim();
    })(),
  );
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || event.request.method !== "GET") return;
  event.respondWith(networkFirst(event.request));
});

// "no-cache" makes the browser check with the server every time, instead of reusing a copy it
// guesses is still fresh (GitHub Pages allows that guess for ten minutes, which would hide a new
// version). ignoreSearch: MapLibre asks for its worker with its version on the end.
async function networkFirst(request) {
  const cache = await caches.open(CACHE);
  try {
    const response = await fetch(request, { cache: "no-cache" });
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch (err) {
    const cached = await cache.match(request, { ignoreSearch: true });
    if (cached) return cached;
    throw err;
  }
}
