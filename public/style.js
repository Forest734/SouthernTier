// The map's MapLibre style: build_map.py's layers, in its order, with its colours (lib.js).
import { DASHES, MM, OLD_ROADS, OPEN_SPACE, ROADS, TRAILS, TRAIL_ROUTE, zoomForScale } from "./lib.js";

const EMPTY = { type: "FeatureCollection", features: [] };
const HALO = "rgba(255, 255, 255, 0.86)";
const px = (mm) => Math.round(mm * MM * 100) / 100;
const rgba = (hex, alpha) =>
  `rgba(${parseInt(hex.slice(1, 3), 16)}, ${parseInt(hex.slice(3, 5), 16)}, ${parseInt(hex.slice(5, 7), 16)}, ${(alpha / 255).toFixed(3)})`;
const match = (field, list, pick, fallback) => ["match", ["get", field], ...list.flatMap((c) => [c.value, pick(c)]), fallback];
const values = (list) => list.map((c) => c.value);
const kindIn = (field, list) => ["in", ["get", field], ["literal", values(list)]];

// NYS orthoimagery 2022-2025 (about 30 cm), as WMS: the service's layers are flight years,
// 0 = 2025 ... 3 = 2022, and it draws the list in order, so the newest goes last, on top
const IMAGERY = "https://orthos.its.ny.gov/arcgis/services/wms/Latest/MapServer/WMSServer?SERVICE=WMS&VERSION=1.1.1"
  + "&REQUEST=GetMap&LAYERS=3,2,1,0&STYLES=,,,&SRS=EPSG:3857&BBOX={bbox-epsg-3857}&FORMAT=image/jpeg";
// USGS 3DEP's multidirectional hillshade, made from the same 1 m lidar as data/hillshade_1m.tif.
// The multiply: scheme is app.js's: it turns the grey into black of matching opacity, which drawn
// over the layers below is the same as QGIS's multiply blend
const HILLSHADE = "multiply://elevation.nationalmap.gov/arcgis/rest/services/3DEPElevation/ImageServer/exportImage"
  + "?bbox={bbox-epsg-3857}&bboxSR=3857&imageSR=3857&format=png&f=image&renderingRule="
  + encodeURIComponent(JSON.stringify({ rasterFunction: "Hillshade Multidirectional" }));

const OSM = '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

// The panel's list, top to bottom as in QGIS's Layers panel: each group is one checkbox over the
// style layers named here (labels included). on is how it starts, as build_map.py leaves it
export const GROUPS = [
  { id: "old_roads", name: "Old roads, Connecticut Hill", on: true, legend: "old_roads" },
  { id: "trails", name: "Trails", on: true, legend: "trails" },
  { id: "trail_routes", name: "Trail routes", on: true, legend: "trail_routes" },
  { id: "roads", name: "Roads and trails, Connecticut Hill", on: true, legend: "roads" },
  { id: "wma", name: "Connecticut Hill WMA (OpenStreetMap outline)", on: false, legend: "wma" },
  { id: "counties", name: "Southern Tier counties", on: true, legend: "counties" },
  { id: "open_space", name: "Open space", on: true, legend: "open_space" },
  { id: "mask", name: "White outside the counties", on: true, legend: "mask" },
  { id: "hillshade", name: "Hillshade (1 m lidar)", on: false, legend: "hillshade" },
  { id: "landuse", name: "Land use 2021/22", on: false, legend: "landuse" },
  { id: "elevation", name: "Elevation (1 m lidar)", on: false, legend: "elevation" },
  { id: "imagery", name: "NYS orthoimagery 2022–2025", on: true, legend: null },
];

// base: the app's URL, for its own files. meta: data/meta.json. ratio: device pixels a CSS pixel
// (the streamed layers are asked for at twice the size on sharp screens)
export function buildStyle(base, meta, ratio = 1) {
  const size = ratio > 1 ? 512 : 256;
  const counties = meta.bookmarks[0].bounds;
  const geojson = (attribution) => ({ type: "geojson", data: EMPTY, generateId: true, ...(attribution && { attribution }) });

  const sources = {
    imagery: { type: "raster", tiles: [`${IMAGERY}&WIDTH=${size}&HEIGHT=${size}`], tileSize: 256, maxzoom: 20,
      attribution: 'Imagery: <a href="https://orthos.ny.gov/">NYS ITS Geospatial Services</a>' },
    elevation: { type: "raster", tiles: [`${base}tiles/elevation/{z}/{x}/{y}.webp`], tileSize: 256, minzoom: 8,
      maxzoom: meta.elevation?.maxzoom ?? 13, bounds: counties, attribution: "Elevation: USGS 3DEP 1 m lidar" },
    landuse: { type: "raster", tiles: [`${base}tiles/landuse/{z}/{x}/{y}.webp`], tileSize: 256, minzoom: 8,
      maxzoom: meta.landuse?.maxzoom ?? 13, bounds: counties,
      attribution: 'Land use: <a href="https://doi.org/10.5066/P14BEBRC">Chesapeake Bay Program LULC 2024 Edition</a>' },
    hillshade: { type: "raster", tiles: [`${HILLSHADE}&size=${size},${size}`], tileSize: 256, maxzoom: 17, bounds: counties,
      attribution: "Hillshade: USGS 3DEP" },
    mask: geojson(),
    counties: geojson("Counties: U.S. Census Bureau"),
    open_space: geojson(`Open space: NYPAD (NY Natural Heritage Program), ${OSM}`),
    wma: geojson(OSM),
    roads: geojson(OSM),
    trail_routes: geojson(OSM),
    trails: geojson(`${OSM}; NYS DEC trails`),
    old_roads: geojson(),
    labels: geojson(),
    highlight: geojson(),
  };

  const layers = [];
  const add = (group, layer) => layers.push({ ...layer, metadata: { group } });
  const raster = (id, paint = {}) => add(id, { id, type: "raster", source: id, paint: { "raster-fade-duration": 150, ...paint } });

  // Bottom to top, as build_map.py stacks them
  raster("imagery");
  raster("elevation", { "raster-resampling": "linear" });
  // Classes stay square past the last zoom level: blending them would make colours of no class
  raster("landuse", { "raster-opacity": meta.landuse?.opacity ?? 0.5, "raster-resampling": "nearest" });
  raster("hillshade", { "raster-opacity": 0.6 });
  add("mask", { id: "mask", type: "fill", source: "mask", paint: { "fill-color": "#ffffff", "fill-antialias": false } });

  // Open space: translucent fills, solid outlines for parks and forests, dashed for other land
  add("open_space", { id: "open_space-fill", type: "fill", source: "open_space",
    paint: { "fill-color": match("kind", OPEN_SPACE, (c) => rgba(c.color, c.alpha), "rgba(0,0,0,0)") } });
  for (const dashed of [false, true]) {
    const list = OPEN_SPACE.filter((c) => c.dash === dashed);
    add("open_space", { id: `open_space-line${dashed ? "-dash" : ""}`, type: "line", source: "open_space",
      filter: kindIn("kind", list), layout: { "line-join": "round" },
      paint: { "line-color": match("kind", list, (c) => c.color, "#000"), "line-width": px(0.5),
        ...(dashed && { "line-dasharray": DASHES.dash }) } });
  }

  add("counties", { id: "counties-line", type: "line", source: "counties", layout: { "line-join": "round" },
    paint: { "line-color": "#2b2b2b", "line-width": px(0.6) } });

  add("wma", { id: "wma-fill", type: "fill", source: "wma", paint: { "fill-color": "rgba(60, 170, 60, 0.176)" } });
  add("wma", { id: "wma-line", type: "line", source: "wma", layout: { "line-join": "round" },
    paint: { "line-color": "#1b6e2a", "line-width": px(0.7) } });

  // Lines of one category list: casings or halos first, then one layer per dash pattern
  const lines = (group, source, field, list, under) => {
    const cased = list.filter(under.has);
    if (cased.length)
      add(group, { id: `${source}-${under.name}`, type: "line", source, filter: kindIn(field, cased),
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": match(field, cased, under.color, "#000"), "line-width": match(field, cased, (c) => px(c.width + under.extra), 1) } });
    for (const dash of [null, ...Object.keys(DASHES)]) {
      const these = list.filter((c) => c.dash === dash);
      if (!these.length) continue;
      add(group, { id: `${source}-line${dash ? `-${dash.replace(" ", "-")}` : ""}`, type: "line", source,
        filter: kindIn(field, these), layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": match(field, these, (c) => c.color, "#000"), "line-width": match(field, these, (c) => px(c.width), 1),
          ...(dash && { "line-dasharray": DASHES[dash] }) } });
    }
  };
  lines("roads", "roads", "kind", ROADS, { name: "casing", has: (c) => !!c.casing, color: (c) => c.casing, extra: 0.4 });
  add("trail_routes", { id: "trail_routes-line", type: "line", source: "trail_routes",
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": TRAIL_ROUTE.color, "line-width": px(TRAIL_ROUTE.width) } });
  lines("trails", "trails", "kind", TRAILS, { name: "halo", has: (c) => c.halo, color: () => "rgba(255, 255, 255, 0.47)", extra: 0.35 });
  lines("old_roads", "old_roads", "confidence", OLD_ROADS, { name: "casing", has: () => true, color: () => "rgba(0, 0, 0, 0.63)", extra: 0.5 });

  // A search result or a picked old road, drawn over everything but the names
  layers.push({ id: "highlight-fill", type: "fill", source: "highlight", filter: ["==", ["geometry-type"], "Polygon"],
    paint: { "fill-color": "rgba(255, 214, 0, 0.25)" } });
  layers.push({ id: "highlight-line", type: "line", source: "highlight", layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": "#ffd600", "line-width": 6, "line-opacity": 0.85, "line-blur": 1 } });

  // Names. MapLibre places the top layer's first, so the most important go last
  const text = (font, size, color, extra = {}) => ({
    layout: { "text-font": [font], "text-size": size, ...extra.layout },
    paint: { "text-color": color, "text-halo-color": HALO, "text-halo-width": 1.6, "text-halo-blur": 0.4, ...extra.paint },
  });
  const label = (group, id, source, minzoom, filter, field, style, layout = {}) => {
    add(group, { id, type: "symbol", source, minzoom, ...(filter && { filter }),
      layout: { "text-field": field, ...style.layout, ...layout }, paint: style.paint });
  };
  const along = { "symbol-placement": "line", "text-max-angle": 30, "text-padding": 4 };
  const at = { "text-max-width": 9, "text-padding": 3, "text-line-height": 1.15 };
  const area = ["get", "area_ha"];
  const notLocal = ["!=", ["get", "kind"], "local_land"];
  const isSpace = ["==", ["get", "layer"], "open_space"];

  label("trails", "trails-label", "trails", zoomForScale(25000), null, ["coalesce", ["get", "name"], ["get", "routes"], ""],
    text("DejaVu Sans", 11, "#4a1208"), along);
  label("roads", "roads-label", "roads", zoomForScale(30000), null, ["coalesce", ["get", "name"], ""],
    text("DejaVu Sans", 11, "#222222"), along);
  label("open_space", "open_space-label-local", "labels", zoomForScale(20000), ["all", isSpace, ["==", ["get", "kind"], "local_land"]],
    ["get", "name"], text("DejaVu Sans Oblique", 11, "#555555"), at);
  label("open_space", "open_space-label-small", "labels", zoomForScale(30000), ["all", isSpace, notLocal, ["<", area, 50]],
    ["get", "name"], text("DejaVu Sans Oblique", 11, "#14501f"), at);
  label("open_space", "open_space-label-mid", "labels", zoomForScale(100000), ["all", isSpace, notLocal, [">=", area, 50], ["<", area, 500]],
    ["get", "name"], text("DejaVu Sans Oblique", 11.5, "#14501f"), at);
  label("trail_routes", "trail_routes-label", "trail_routes", zoomForScale(200000), null, ["get", "name"],
    text("DejaVu Sans Bold", 11.5, "#9c0d4f"), { ...along, "symbol-spacing": Math.round(120 * MM) });
  label("old_roads", "old_roads-label", "old_roads", zoomForScale(60000), null, ["get", "id"],
    text("DejaVu Sans Bold", 13, "#1a1a1a", { paint: { "text-halo-width": 2 } }), { ...along, "text-max-angle": 45 });
  label("open_space", "open_space-label-big", "labels", zoomForScale(500000), ["all", isSpace, notLocal, [">=", area, 500]],
    ["get", "name"], text("DejaVu Sans Oblique", 12, "#14501f"), at);
  label("wma", "wma-label", "labels", zoomForScale(150000), ["==", ["get", "layer"], "wma"], ["get", "name"],
    text("DejaVu Sans", 12, "#14501f"), at);
  label("counties", "counties-label", "labels", 0, ["==", ["get", "layer"], "county"], ["upcase", ["get", "name"]],
    text("DejaVu Sans", 13, "#2b2b2b", { layout: { "text-letter-spacing": 0.08 } }), at);

  for (const l of layers) {
    const g = GROUPS.find((g) => g.id === l.metadata?.group);
    if (g && !g.on) l.layout = { ...l.layout, visibility: "none" };
    // Connecticut Hill's roads cover a patch 10 km across: from further out they're a white blot
    if (l.metadata?.group === "roads" && !(l.minzoom > 10.5)) l.minzoom = 10.5;
  }

  return {
    version: 8,
    name: "Counties of the Southern Tier of New York",
    // Names are drawn from DejaVu Sans, as in QGIS, by the browser: no glyph server
    "font-faces": {
      "DejaVu Sans": `${base}fonts/DejaVuSans.woff2`,
      "DejaVu Sans Oblique": `${base}fonts/DejaVuSans-Oblique.woff2`,
      "DejaVu Sans Bold": `${base}fonts/DejaVuSans-Bold.woff2`,
    },
    sources,
    layers,
  };
}
