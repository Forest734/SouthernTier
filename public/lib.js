// Pure parts of the app: the map's categories (as build_map.py draws them), popup text, and
// search. No DOM and no MapLibre, so node:test can load it.

// QGIS sizes are millimetres; on screen, a millimetre at 96 dpi
export const MM = 96 / 25.4;

// The colours, widths and dashes below are build_map.py's. Change both together.

// Open space by kind. alpha is QGIS's 0-255 fill opacity; dashed outlines are for the land
// that's public but not a park
export const OPEN_SPACE = [
  { value: "national_forest", color: "#1b5e20", alpha: 60, dash: false, short: "National forest", label: "National forest" },
  { value: "state_forest", color: "#2e7d32", alpha: 45, dash: false, short: "State forest", label: "State forests" },
  { value: "wma", color: "#558b2f", alpha: 45, dash: false, short: "Wildlife management area", label: "Wildlife management and multiple use areas" },
  { value: "state_park", color: "#00796b", alpha: 55, dash: false, short: "State park", label: "State parks and rail trails" },
  { value: "park", color: "#26a69a", alpha: 60, dash: false, short: "Park", label: "City, town and county parks" },
  { value: "preserve", color: "#b8860b", alpha: 50, dash: false, short: "Nature preserve", label: "Nature preserves (land trusts, Cornell, others)" },
  { value: "state_other", color: "#00796b", alpha: 25, dash: true, short: "State land", label: "Other state land (boat launches, fishing access)" },
  { value: "local_land", color: "#757575", alpha: 30, dash: true, short: "Public land", label: "Other city, town, county and district land" },
];

// Today's roads and trails round Connecticut Hill, from OpenStreetMap. casing is a darker line
// 0.4 mm wider underneath
export const ROADS = [
  { value: "major", color: "#ffffff", width: 0.9, casing: "#3a3a3a", dash: null, short: "State or county road", label: "State and county roads" },
  { value: "local", color: "#f2f2f2", width: 0.6, casing: "#3a3a3a", dash: null, short: "Local road", label: "Local roads" },
  { value: "dirt", color: "#e3c99a", width: 0.55, casing: "#3a3a3a", dash: null, short: "Dirt road", label: "Dirt roads" },
  { value: "service", color: "#d0d0d0", width: 0.3, casing: null, dash: null, short: "Driveway or service road", label: "Driveways and service roads" },
  { value: "track", color: "#8a5a2b", width: 0.45, casing: null, dash: "dash", short: "Track", label: "Tracks" },
  { value: "trail", color: "#2b6fd6", width: 0.45, casing: null, dash: "dot", short: "Trail", label: "Trails" },
  { value: "abandoned", color: "#c51b8a", width: 0.45, casing: null, dash: "dash", short: "Abandoned road", label: "Abandoned (as mapped today)" },
];

// Every trail in the five counties. halo is a white line 0.35 mm wider underneath, to show on
// the imagery
export const TRAILS = [
  { value: "footpath", color: "#7b1e12", width: 0.45, dash: "dash", halo: true, short: "Footpath", label: "Footpaths and hiking trails" },
  { value: "multiuse", color: "#4a148c", width: 0.6, dash: null, halo: true, short: "Multi-use path", label: "Paved and stone-dust paths, rail trails" },
  { value: "mtb", color: "#e65100", width: 0.45, dash: "dash", halo: true, short: "Mountain bike trail", label: "Mountain bike trails" },
  { value: "horse", color: "#6d4c41", width: 0.45, dash: "dash dot", halo: true, short: "Horse trail", label: "Horse and multi-use trails" },
  { value: "snowmobile", color: "#37474f", width: 0.45, dash: "dot", halo: true, short: "Snowmobile trail", label: "Snowmobile trails" },
  { value: "private", color: "#9e9e9e", width: 0.35, dash: "dot", halo: false, short: "Private trail", label: "Private, no public access" },
];

// Old roads in the WMA, by how sure the tracing is. Each has a dark casing 0.5 mm wider
export const OLD_ROADS = [
  { value: "high", color: "#e8112d", width: 1.0, dash: null, short: "High confidence", label: "High: on the 1893 map, plain in the lidar" },
  { value: "medium", color: "#ff8c00", width: 0.8, dash: null, short: "Medium confidence", label: "Medium: on an old map, fainter in the lidar" },
  { value: "low", color: "#ffe14d", width: 0.6, dash: "dash", short: "Low confidence", label: "Low: in the lidar only (logging roads?)" },
];

export const TRAIL_ROUTE = { color: "rgba(255, 64, 129, 0.43)", width: 1.6, label: "Named routes (Finger Lakes Trail, rail trails)" };

// Qt's pen patterns, in line widths, as MapLibre's line-dasharray takes them
export const DASHES = { dash: [4, 2], dot: [1, 2], "dash dot": [4, 2, 1, 2] };

// The zoom at which the map shows a QGIS scale (1:scale) here: 96 dpi, at the counties' latitude
export const LATITUDE = 42.3;
export function zoomForScale(scale, latitude = LATITUDE) {
  const metresPerPixelAtZoom0 = (2 * Math.PI * 6378137) / 256;
  return Math.log2((metresPerPixelAtZoom0 * Math.cos((latitude * Math.PI) / 180) * 96) / 0.0254 / scale);
}

const byValue = (list) => Object.fromEntries(list.map((c) => [c.value, c]));
const SPACE = byValue(OPEN_SPACE);
const ROAD = byValue(ROADS);
const TRAIL = byValue(TRAILS);
const OLD = byValue(OLD_ROADS);

const whole = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const tenths = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });
export function hectares(ha) {
  if (ha == null) return "";
  return `${(ha < 10 ? tenths : whole).format(ha)} ha`;
}
export function metres(m) {
  if (m == null) return "";
  return m >= 1000 ? `${tenths.format(m / 1000)} km` : `${whole.format(m)} m`;
}

const joined = (parts, sep = ", ") => parts.filter((p) => p != null && p !== "").join(sep);
const words = (tag) => tag?.replaceAll("_", " "); // OpenStreetMap's values: "unhewn_cobblestone"
const capital = (s) => (s ? s[0].toUpperCase() + s.slice(1) : s);

// What a click on a feature shows: its title, a line or two, and where it's from. Plain text:
// the page sets it with textContent. layer is the feature's source in the map's style
export function describe(layer, p) {
  switch (layer) {
    case "open_space":
      return {
        title: p.name || "(no name)",
        lines: [
          joined([SPACE[p.kind]?.short, hectares(p.area_ha)], " · "),
          joined([p.manager && capital(p.manager), p.access && `access ${p.access}`]),
        ],
        source: p.source,
      };
    case "wma":
      return {
        title: p.name,
        lines: [`${hectares(p.area_ha)} (${joined([p.manager, p.source && `boundary from ${p.source}`], "; ")})`],
        source: null,
      };
    case "roads":
      return {
        title: p.name || capital(words(p.highway)) || "Road",
        lines: [joined([ROAD[p.kind]?.short, joined([words(p.highway), words(p.surface)])], " · ")],
        source: "OpenStreetMap",
      };
    case "trail_routes":
      return {
        title: p.name,
        lines: [
          joined([p.route && capital(p.route), p.length_km != null && `${tenths.format(p.length_km)} km in the counties`], " · "),
          joined([p.operator && p.operator.replaceAll(";", ", ")]),
        ],
        source: p.source,
      };
    case "trails":
      return {
        title: p.name || p.routes || "Trail",
        lines: [
          joined([TRAIL[p.kind]?.short, joined([words(p.highway), words(p.surface)]), metres(p.length_m)], " · "),
          p.routes && p.name && p.routes !== p.name ? `On ${p.routes}` : "",
        ],
        source: p.source,
      };
    case "old_roads":
      return {
        title: `Old road ${p.id}`,
        lines: [
          joined([OLD[p.confidence]?.short, metres(p.length_m),
            p.old_map && p.old_map !== "none" ? `on the ${p.old_map} map` : "on neither old map"], " · "),
          p.notes,
        ],
        source: "Traced from the 1 m lidar and USGS topographic maps; not checked on the ground",
      };
    default:
      return { title: p.name || "", lines: [], source: null };
  }
}

// [west, south, east, north] of a GeoJSON geometry
export function bbox(geometry) {
  const b = [Infinity, Infinity, -Infinity, -Infinity];
  const walk = (c) => {
    if (typeof c[0] === "number") {
      if (c[0] < b[0]) b[0] = c[0];
      if (c[1] < b[1]) b[1] = c[1];
      if (c[0] > b[2]) b[2] = c[0];
      if (c[1] > b[3]) b[3] = c[1];
    } else for (const x of c) walk(x);
  };
  walk(geometry.coordinates);
  return b;
}

const union = (a, b) => [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])];
const near = (a, b, gap) => a[0] - gap <= b[2] && b[0] - gap <= a[2] && a[1] - gap <= b[3] && b[1] - gap <= a[3];

// Features of the same name, in groups whose boxes come within gap degrees of each other: one
// search result for a trail of many pieces, but two for two "Blue Trail"s miles apart
export function groupByName(features, nameOf, gap) {
  const groups = [];
  const byName = new Map();
  for (const f of features) {
    const name = nameOf(f);
    if (!name) continue;
    const b = bbox(f.geometry);
    let list = byName.get(name);
    if (!list) byName.set(name, (list = []));
    const g = list.find((g) => near(g.bounds, b, gap));
    if (g) {
      g.bounds = union(g.bounds, b);
      g.features.push(f);
    } else {
      const ng = { name, bounds: b, features: [f] };
      list.push(ng);
      groups.push(ng);
    }
  }
  return groups;
}

const counties = (features) =>
  [...new Set(features.flatMap((f) => (f.properties.county ? f.properties.county.split(", ") : [])))].join(", ");

// The park or forest most of a trail's pieces are in (build_web.py's "in")
function place(features) {
  const n = new Map();
  for (const f of features) if (f.properties.in) n.set(f.properties.in, (n.get(f.properties.in) ?? 0) + 1);
  return [...n].sort((a, b) => b[1] - a[1])[0]?.[0] ?? "";
}

// When names match equally well: lower ranks first, then whatever reaches furthest across the map
// (a 150 km trail before its 2 km spur, a state forest before a pocket park)
const SPACE_RANK = { national_forest: 0, state_forest: 0, wma: 0, state_park: 0, park: 1, preserve: 1, state_other: 2, local_land: 4 };
export function reach([w, s, e, n]) {
  const km = 111.32;
  return Math.hypot((e - w) * km * Math.cos((((s + n) / 2) * Math.PI) / 180), (n - s) * km);
}

// The search's list: named open space, trail routes, trails, the old roads and the roads round
// Connecticut Hill. data has the GeoJSON FeatureCollections by source name
export function buildIndex(data) {
  const items = [];
  const add = (layer, groups, type, rank, byName = false) => {
    for (const g of groups) {
      const where = place(g.features);
      items.push({ layer, name: g.name, type: type(g.features[0]), county: counties(g.features), rank: rank(g.features[0]),
        ...(where && where !== g.name && { place: where }),
        reach: byName ? 0 : reach(g.bounds), bounds: g.bounds, features: g.features });
    }
  };
  const GAP = 0.01; // degrees: about a kilometre
  if (data.trail_routes)
    add("trail_routes", groupByName(data.trail_routes.features, (f) => f.properties.name, Infinity), () => "Trail route", () => 0);
  if (data.open_space)
    add("open_space", groupByName(data.open_space.features, (f) => f.properties.name && `${f.properties.name}\u0000${f.properties.kind}`, GAP),
      (f) => SPACE[f.properties.kind]?.short ?? "Open space", (f) => SPACE_RANK[f.properties.kind] ?? 3);
  if (data.old_roads)
    add("old_roads", groupByName(data.old_roads.features, (f) => `Old road ${f.properties.id}`, 0),
      (f) => `${OLD[f.properties.confidence]?.short ?? "Old road"}, Connecticut Hill`, () => 1, true);
  if (data.trails)
    add("trails", groupByName(data.trails.features, (f) => f.properties.name, GAP), (f) => TRAIL[f.properties.kind]?.short ?? "Trail", () => 2);
  if (data.roads)
    add("roads", groupByName(data.roads.features, (f) => f.properties.name, GAP), (f) => ROAD[f.properties.kind]?.short ?? "Road", () => 3);
  for (const item of items) item.name = item.name.split("\u0000")[0];
  return items;
}

const normal = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();

// Items whose names hold every word typed: names that start with it first, then names with a
// word that starts with it, then the rest; within those by rank, then by reach
export function search(items, query, limit = 8) {
  const q = normal(query);
  if (!q) return [];
  const words = q.split(" ");
  const scored = [];
  for (const item of items) {
    const n = item.norm ?? (item.norm = normal(item.name));
    if (!words.every((w) => n.includes(w))) continue;
    const score = n.startsWith(q) ? 0 : n.split(" ").some((w) => w.startsWith(words[0])) ? 1 : 2;
    scored.push([score, item]);
  }
  scored.sort((a, b) => a[0] - b[0] || a[1].rank - b[1].rank || b[1].reach - a[1].reach || a[1].name.localeCompare(b[1].name));
  return scored.slice(0, limit).map(([, item]) => item);
}
