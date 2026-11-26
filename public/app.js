// The page: the map, the panel (places, search, layers and legends) and what a click shows.
import * as maplibregl from "./vendor/maplibre-gl/maplibre-gl.mjs";
import { DASHES, MM, OLD_ROADS, OPEN_SPACE, ROADS, TRAILS, TRAIL_ROUTE, bbox, buildIndex, describe, search } from "./lib.js";
import { GROUPS, buildStyle } from "./style.js";

const BASE = new URL("./", location.href).href;
const VECTORS = ["counties", "mask", "labels", "open_space", "wma", "roads", "trail_routes", "trails", "old_roads"];
// What a click can pick, top layer first, as QGIS's map tips would
const CLICKABLE = ["old_roads", "trails", "trail_routes", "roads", "wma", "open_space"];
const $ = (sel) => document.querySelector(sel);

// localStorage under "southerntier:", shared with the other apps on this origin. Every access can
// throw (storage off, or full)
const store = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem(`southerntier:${key}`);
      return v == null ? fallback : JSON.parse(v);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(`southerntier:${key}`, JSON.stringify(value));
    } catch {}
  },
};

// The hillshade's multiply blend. Each grey pixel v becomes black at opacity 1 - v, so the layers
// below are darkened to v of themselves: a multiply. The layer's own 0.6 opacity then gives
// QGIS's multiply at 60%
maplibregl.addProtocol("multiply", async (params, abort) => {
  const response = await fetch(params.url.replace(/^multiply:/, "https:"), { signal: abort.signal });
  if (!response.ok) throw new Error(`${response.status} ${params.url}`);
  const image = await createImageBitmap(await response.blob());
  const canvas = new OffscreenCanvas(image.width, image.height);
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  ctx.drawImage(image, 0, 0);
  const pixels = ctx.getImageData(0, 0, image.width, image.height);
  const d = pixels.data;
  for (let i = 0; i < d.length; i += 4) {
    d[i + 3] = ((255 - d[i]) * d[i + 3]) / 255;
    d[i] = d[i + 1] = d[i + 2] = 0;
  }
  ctx.putImageData(pixels, 0, 0);
  return { data: await createImageBitmap(canvas) };
});

async function getJSON(path) {
  const response = await fetch(`${BASE}${path}`);
  if (!response.ok) throw new Error(`${response.status} ${path}`);
  return response.json();
}

function showError(message) {
  const el = $("#error");
  el.textContent = message;
  el.hidden = false;
}

let map;
let index = [];
const data = {};

async function start() {
  let meta;
  try {
    meta = await getJSON("data/meta.json");
  } catch (err) {
    showError("The map's data couldn't be loaded. Check the connection and reload.");
    throw err;
  }
  const layersOn = { ...Object.fromEntries(GROUPS.map((g) => [g.id, g.on])), ...store.get("layers", {}) };
  const style = buildStyle(BASE, meta, window.devicePixelRatio || 1);
  for (const l of style.layers) {
    const g = l.metadata?.group;
    if (g) l.layout = { ...l.layout, visibility: layersOn[g] ? "visible" : "none" };
  }

  const saved = store.get("view", null);
  try {
    map = new maplibregl.Map({
      container: "map",
      style,
      hash: true,
      minZoom: 7,
      maxZoom: 20,
      maxPitch: 0,
      dragRotate: false,
      ...(saved ? { center: saved.center, zoom: saved.zoom } : { bounds: meta.bookmarks[0].bounds }),
      attributionControl: { compact: true },
    });
  } catch (err) {
    showError("This browser can't draw the map (it needs WebGL).");
    throw err;
  }
  map.touchZoomRotate.disableRotation();
  map.keyboard.disableRotation();
  map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
  map.addControl(new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, trackUserLocation: true }), "top-right");
  map.addControl(new maplibregl.ScaleControl({ unit: "metric", maxWidth: 120 }), "bottom-left");
  map.addControl(new maplibregl.ScaleControl({ unit: "imperial", maxWidth: 120 }), "bottom-left");
  map.on("moveend", () => store.set("view", { center: map.getCenter().toArray(), zoom: map.getZoom() }));
  // A tile the map has no data for (the edges of the land use and elevation, a slow USGS
  // server) is only a gap in one layer: don't fill the console with them
  map.on("error", (e) => {
    if (e.sourceId || e.tile) return;
    console.error(e.error ?? e);
  });

  renderPlaces(meta.bookmarks);
  renderLayers(meta, layersOn);
  wirePanel();

  await new Promise((resolve) => (map.loaded() ? resolve() : map.once("load", resolve)));
  // The credits start folded (the ⓘ opens them): open, they cover the scale bar. The panel lists
  // the sources too
  document.querySelector(".maplibregl-ctrl-attrib")?.classList.remove("maplibregl-compact-show");
  await Promise.all(VECTORS.map(async (name) => {
    try {
      data[name] = await getJSON(`data/${name}.geojson`);
      map.getSource(name).setData(data[name]);
    } catch (err) {
      showError("Some of the map's layers couldn't be loaded. Check the connection and reload.");
      console.error(err);
    }
  }));
  index = buildIndex(data);
  renderOldRoads();
  wireClicks();
  const q = $("#search");
  if (q.value) q.dispatchEvent(new Event("input"));
}

// The places: the whole map, the counties, Connecticut Hill
function renderPlaces(bookmarks) {
  const list = $("#places");
  for (const b of bookmarks) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "chip";
    button.textContent = b.name.replace(/ County$/, "");
    button.title = b.name;
    button.addEventListener("click", () => {
      clearHighlight();
      map.fitBounds(b.bounds, { padding: 24, duration: reducedMotion() ? 0 : 800 });
      closePanel();
    });
    list.append(button);
  }
}

const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;

// The layer list, with each layer's legend under it
function renderLayers(meta, layersOn) {
  const list = $("#layers");
  for (const g of GROUPS) {
    const li = document.createElement("li");
    li.className = "layer";
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = !!layersOn[g.id];
    box.addEventListener("change", () => setGroup(g.id, box.checked));
    box.dataset.group = g.id;
    const name = document.createElement("span");
    name.textContent = g.name;
    label.append(box, name);
    li.append(label);
    const legend = legendFor(g.legend, meta);
    if (legend) li.append(legend);
    list.append(li);
  }
}

function setGroup(id, on) {
  for (const l of map.getStyle().layers)
    if (l.metadata?.group === id) map.setLayoutProperty(l.id, "visibility", on ? "visible" : "none");
  const box = document.querySelector(`#layers input[data-group="${id}"]`);
  if (box) box.checked = on;
  const saved = store.get("layers", {});
  saved[id] = on;
  store.set("layers", saved);
}

const SVG = "http://www.w3.org/2000/svg";
function svg(w, h, children) {
  const el = document.createElementNS(SVG, "svg");
  el.setAttribute("width", w);
  el.setAttribute("height", h);
  el.setAttribute("viewBox", `0 0 ${w} ${h}`);
  el.setAttribute("aria-hidden", "true");
  el.classList.add("swatch");
  for (const [tag, attrs] of children) {
    const c = document.createElementNS(SVG, tag);
    for (const [k, v] of Object.entries(attrs)) if (v != null) c.setAttribute(k, v);
    el.append(c);
  }
  return el;
}

// A line as the map draws it: its casing or halo, then the line with its dashes
function lineSwatch({ color, width, dash, under, underWidth }) {
  const w = width * MM;
  const parts = [];
  if (under) parts.push(["path", { d: "M5 7H27", stroke: under, "stroke-width": underWidth * MM, "stroke-linecap": "round" }]);
  parts.push(["path", { d: "M5 7H27", stroke: color, "stroke-width": w, "stroke-linecap": dash ? "butt" : "round",
    "stroke-dasharray": dash ? DASHES[dash].map((x) => x * w).join(" ") : null }]);
  return svg(32, 14, parts);
}

function fillSwatch({ fill, stroke, strokeWidth = 1.5, dash = false }) {
  return svg(32, 14, [["rect", { x: 1.5, y: 1.5, width: 29, height: 11, rx: 2, fill, stroke, "stroke-width": strokeWidth,
    "stroke-dasharray": dash ? "4 2" : null }]]);
}

function legendRow(swatch, text) {
  const li = document.createElement("li");
  const span = document.createElement("span");
  span.textContent = text;
  li.append(swatch, span);
  return li;
}

function legendList(rows) {
  const ul = document.createElement("ul");
  ul.className = "legend";
  ul.append(...rows);
  return ul;
}

const alpha = (hex, a) => `${hex}${Math.round(a).toString(16).padStart(2, "0")}`;

function legendFor(kind, meta) {
  switch (kind) {
    case "old_roads":
      return legendList(OLD_ROADS.map((c) => legendRow(lineSwatch({ ...c, under: "rgba(0,0,0,.63)", underWidth: c.width + 0.5 }), c.label)));
    case "trails":
      return legendList(TRAILS.map((c) => legendRow(lineSwatch({ ...c, under: c.halo ? "rgba(255,255,255,.47)" : null, underWidth: c.width + 0.35 }), c.label)));
    case "trail_routes":
      return legendList([legendRow(lineSwatch({ color: TRAIL_ROUTE.color, width: TRAIL_ROUTE.width }), TRAIL_ROUTE.label)]);
    case "roads":
      return legendList(ROADS.map((c) => legendRow(lineSwatch({ ...c, under: c.casing, underWidth: c.width + 0.4 }), c.label)));
    case "wma":
      return legendList([legendRow(fillSwatch({ fill: "rgba(60,170,60,.18)", stroke: "#1b6e2a" }), "Its boundary as OpenStreetMap has it")]);
    case "counties":
      return legendList([legendRow(fillSwatch({ fill: "none", stroke: "#2b2b2b", strokeWidth: 2 }), "Broome, Chemung, Schuyler, Tioga, Tompkins")]);
    case "open_space":
      return legendList(OPEN_SPACE.map((c) => legendRow(fillSwatch({ fill: alpha(c.color, c.alpha), stroke: c.color, dash: c.dash }), c.label)));
    case "mask":
      return null;
    case "hillshade": {
      const p = document.createElement("p");
      p.className = "note";
      p.textContent = "Streamed from USGS 3DEP; it shades whatever is under it.";
      return p;
    }
    case "elevation": {
      const ramp = meta.elevation?.ramp;
      if (!ramp) return null;
      const wrap = document.createElement("div");
      wrap.className = "ramp";
      const bar = document.createElement("div");
      bar.className = "ramp-bar";
      bar.style.background = `linear-gradient(90deg, ${ramp.map(([, c]) => c).join(", ")})`;
      const ends = document.createElement("div");
      ends.className = "ramp-ends";
      for (const [m] of [ramp[0], ramp[ramp.length - 1]]) {
        const s = document.createElement("span");
        s.textContent = `${Math.round(m)} m (${Math.round(m / 0.3048).toLocaleString("en-US")} ft)`;
        ends.append(s);
      }
      wrap.append(bar, ends);
      return wrap;
    }
    case "landuse": {
      const classes = meta.landuse?.classes;
      if (!classes) return null;
      const details = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = `${classes.length} classes, half transparent`;
      details.append(summary, legendList(classes.map(([, color, name]) => legendRow(fillSwatch({ fill: color, stroke: "none" }), name))));
      return details;
    }
    default:
      return null;
  }
}

// The nine old roads, under their layer: what the write-up says of each
function renderOldRoads() {
  const roads = data.old_roads?.features;
  const li = document.querySelector('#layers input[data-group="old_roads"]')?.closest("li");
  if (!roads || !li) return;
  const details = document.createElement("details");
  details.className = "old-roads";
  const summary = document.createElement("summary");
  summary.textContent = `The ${roads.length} roads`;
  const ol = document.createElement("ol");
  for (const f of [...roads].sort((a, b) => a.properties.id.localeCompare(b.properties.id))) {
    const d = describe("old_roads", f.properties);
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    const title = document.createElement("strong");
    title.textContent = f.properties.id;
    const color = OLD_ROADS.find((c) => c.value === f.properties.confidence)?.color;
    if (color) title.style.setProperty("--dot", color);
    const text = document.createElement("span");
    text.textContent = `${d.lines[0]}. ${f.properties.notes ?? ""}`;
    button.append(title, text);
    button.addEventListener("click", () => select({ layer: "old_roads", bounds: bbox(f.geometry), features: [f] }));
    item.append(button);
    ol.append(item);
  }
  details.append(summary, ol);
  li.append(details);
}

// Go to a search result or an old road, show its layer and mark it
function select(item) {
  if (!document.querySelector(`#layers input[data-group="${item.layer}"]`)?.checked) setGroup(item.layer, true);
  map.getSource("highlight").setData({ type: "FeatureCollection", features: item.features });
  map.fitBounds(item.bounds, { padding: 60, maxZoom: 15.5, duration: reducedMotion() ? 0 : 800 });
  closePanel();
}

function clearHighlight() {
  map?.getSource("highlight")?.setData({ type: "FeatureCollection", features: [] });
}

function wirePanel() {
  const input = $("#search");
  const results = $("#results");
  const show = () => {
    results.replaceChildren();
    const q = input.value.trim();
    if (!q) {
      results.hidden = true;
      return;
    }
    const found = search(index, q);
    results.hidden = false;
    if (!found.length) {
      const li = document.createElement("li");
      li.className = "none";
      li.textContent = index.length ? "Nothing by that name" : "Loading…";
      results.append(li);
      return;
    }
    for (const item of found) {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = item.name;
      const what = document.createElement("span");
      what.className = "what";
      what.textContent = [item.type, item.place, item.county].filter(Boolean).join(" · ");
      button.append(name, what);
      button.addEventListener("click", () => select(item));
      li.append(button);
      results.append(li);
    }
  };
  input.addEventListener("input", show);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") results.querySelector("button")?.click();
    if (e.key === "ArrowDown") {
      e.preventDefault();
      results.querySelector("button")?.focus();
    }
    if (e.key === "Escape") {
      input.value = "";
      show();
    }
  });
  results.addEventListener("keydown", (e) => {
    const buttons = [...results.querySelectorAll("button")];
    const i = buttons.indexOf(document.activeElement);
    if (e.key === "ArrowDown" && i < buttons.length - 1) { e.preventDefault(); buttons[i + 1].focus(); }
    if (e.key === "ArrowUp") { e.preventDefault(); (i > 0 ? buttons[i - 1] : input).focus(); }
  });

  const toggle = $("#panel-toggle");
  toggle.addEventListener("click", () => (document.body.classList.contains("panel-open") ? closePanel() : openPanel()));
  $(".scrim").addEventListener("click", () => closePanel());
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && document.body.classList.contains("panel-open") && narrow()) closePanel(true);
  });
}

const narrow = () => matchMedia("(max-width: 760px)").matches;
function openPanel() {
  document.body.classList.add("panel-open");
  $("#panel-toggle").setAttribute("aria-expanded", "true");
  $("#search").focus({ preventScroll: true });
}
function closePanel(focusToggle = false) {
  if (!narrow()) return;
  document.body.classList.remove("panel-open");
  $("#panel-toggle").setAttribute("aria-expanded", "false");
  if (focusToggle) $("#panel-toggle").focus();
}

// A click shows what's under it, the top layer first, as QGIS's map tips do; a trail on a route
// in a state forest shows all three
function wireClicks() {
  const clickable = map.getStyle().layers
    .filter((l) => CLICKABLE.includes(l.source) && (l.type === "line" || l.type === "fill"))
    .map((l) => l.id);
  const near = (point, r) => [[point.x - r, point.y - r], [point.x + r, point.y + r]];
  const hits = (point, r) => {
    const seen = new Set();
    const out = [];
    for (const f of map.queryRenderedFeatures(near(point, r), { layers: clickable })) {
      const key = `${f.source}:${f.id}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(f);
    }
    out.sort((a, b) => CLICKABLE.indexOf(a.source) - CLICKABLE.indexOf(b.source));
    return out;
  };
  const popup = new maplibregl.Popup({ maxWidth: "320px", focusAfterOpen: false });
  map.on("click", (e) => {
    // One entry per named thing: a trail is many OpenStreetMap ways, and a tap finds several
    const seen = new Set();
    const found = [];
    for (const f of hits(e.point, e.originalEvent?.pointerType === "touch" ? 10 : 5)) {
      const d = describe(f.source, f.properties);
      const key = `${f.source}\u0000${d.title}`;
      if (seen.has(key)) continue;
      seen.add(key);
      found.push(d);
      if (found.length === 4) break;
    }
    if (!found.length) {
      popup.remove();
      return;
    }
    const box = document.createElement("div");
    box.className = "tip";
    for (const d of found) {
      const section = document.createElement("section");
      const h = document.createElement("h3");
      h.textContent = d.title;
      section.append(h);
      for (const line of d.lines.filter(Boolean)) {
        const p = document.createElement("p");
        p.textContent = line;
        section.append(p);
      }
      if (d.source) {
        const p = document.createElement("p");
        p.className = "src";
        p.textContent = d.source;
        section.append(p);
      }
      box.append(section);
    }
    popup.setLngLat(e.lngLat).setDOMContent(box).addTo(map);
  });
  let last = false;
  map.on("mousemove", (e) => {
    const over = hits(e.point, 4).length > 0;
    if (over !== last) map.getCanvas().style.cursor = (last = over) ? "pointer" : "";
  });
}

if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});

start().catch((err) => console.error(err));
