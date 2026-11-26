import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { OLD_ROADS, OPEN_SPACE, ROADS, TRAILS, bbox, buildIndex, describe, groupByName, hectares, metres, search, zoomForScale } from "../public/lib.js";

const line = (coords, properties) => ({ type: "Feature", properties, geometry: { type: "LineString", coordinates: coords } });

test("zoomForScale puts QGIS's scales where the web map shows them", () => {
  // At 42.3° N and 96 dpi, zoom 12 is about 1:104,000
  assert.ok(Math.abs(zoomForScale(104000) - 12) < 0.05);
  // Each halving of the scale is one zoom level in
  assert.ok(Math.abs(zoomForScale(30000) - zoomForScale(60000) - 1) < 1e-9);
  assert.ok(zoomForScale(500000) < zoomForScale(200000));
});

test("the categories are build_map.py's", () => {
  const src = readFileSync(new URL("../build_map.py", import.meta.url), "utf8");
  for (const c of OPEN_SPACE) assert.match(src, new RegExp(`\\("${c.value}", "${c.color}", ${c.alpha}, ${c.dash ? "True" : "False"}`));
  for (const c of ROADS) assert.match(src, new RegExp(`\\("${c.value}", "${c.color}", ${c.width}, `));
  for (const c of TRAILS) assert.match(src, new RegExp(`\\("${c.value}", "${c.color}", ${c.width}, "${c.dash ?? "solid"}", ${c.halo ? "True" : "False"}`));
  for (const c of OLD_ROADS) assert.match(src, new RegExp(`\\("${c.value}", "${c.color}", ${c.width.toFixed(1)}, ${c.dash ? "True" : "False"}`));
});

test("hectares and metres", () => {
  assert.equal(hectares(4521), "4,521 ha");
  assert.equal(hectares(2.35), "2.4 ha");
  assert.equal(hectares(null), "");
  assert.equal(metres(535), "535 m");
  assert.equal(metres(2528), "2.5 km");
});

test("describe: open space with and without a name", () => {
  const d = describe("open_space", { name: "Danby State Forest", kind: "state_forest", area_ha: 2939.4, manager: "NYS DEC",
    access: "open", source: "NYPAD (NY Natural Heritage Program)" });
  assert.deepEqual(d, { title: "Danby State Forest", lines: ["State forest · 2,939 ha", "NYS DEC, access open"],
    source: "NYPAD (NY Natural Heritage Program)" });
  assert.equal(describe("open_space", { kind: "park" }).title, "(no name)");
});

test("describe: a trail with no name takes its route's", () => {
  const d = describe("trails", { kind: "footpath", routes: "Finger Lakes Trail", highway: "path", surface: "ground", length_m: 1234, source: "OpenStreetMap way 1" });
  assert.equal(d.title, "Finger Lakes Trail");
  assert.deepEqual(d.lines, ["Footpath · path, ground · 1.2 km", ""]);
  const named = describe("trails", { name: "Gorge Trail", routes: "Finger Lakes Trail", kind: "footpath", surface: "unhewn_cobblestone" });
  assert.deepEqual(named.lines, ["Footpath · unhewn cobblestone", "On Finger Lakes Trail"]);
  assert.equal(describe("trails", { kind: "mtb" }).title, "Trail");
});

test("describe: an old road", () => {
  const d = describe("old_roads", { id: "G", confidence: "low", old_map: "none", length_m: 535, notes: "A bench." });
  assert.equal(d.title, "Old road G");
  assert.deepEqual(d.lines, ["Low confidence · 535 m · on neither old map", "A bench."]);
  assert.equal(describe("old_roads", { id: "A", confidence: "high", old_map: "1893", length_m: 2528 }).lines[0],
    "High confidence · 2.5 km · on the 1893 map");
});

test("describe: roads and routes", () => {
  assert.deepEqual(describe("roads", { highway: "track", kind: "track" }), { title: "Track", lines: ["Track · track"], source: "OpenStreetMap" });
  const r = describe("trail_routes", { name: "Catharine Valley Trail", route: "bicycle", length_km: 21.2, operator: "A;B" });
  assert.deepEqual(r.lines, ["Bicycle · 21.2 km in the counties", "A, B"]);
});

test("bbox of lines and multipolygons", () => {
  assert.deepEqual(bbox({ type: "LineString", coordinates: [[-76.5, 42.4], [-76.4, 42.3]] }), [-76.5, 42.3, -76.4, 42.4]);
  assert.deepEqual(bbox({ type: "MultiPolygon", coordinates: [[[[0, 0], [2, 0], [2, 1], [0, 0]]], [[[-1, 5], [0, 5], [0, 6], [-1, 5]]]] }), [-1, 0, 2, 6]);
});

test("groupByName joins pieces that touch and keeps far ones apart", () => {
  const fs = [
    line([[0, 0], [0.005, 0]], { name: "Blue Trail" }),
    line([[0.006, 0], [0.01, 0]], { name: "Blue Trail" }),
    line([[1, 1], [1.01, 1]], { name: "Blue Trail" }),
    line([[0, 0], [0.01, 0]], {}),
  ];
  const groups = groupByName(fs, (f) => f.properties.name, 0.01);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].features.length, 2);
  assert.deepEqual(groups[0].bounds, [0, 0, 0.01, 0]);
});

test("search ranks names that start with the query first, then by kind", () => {
  const data = {
    trail_routes: { type: "FeatureCollection", features: [line([[0, 0], [1, 0]], { name: "Finger Lakes Trail", county: "Tompkins" })] },
    open_space: { type: "FeatureCollection", features: [
      line([[0, 0], [0.1, 0]], { name: "Danby State Forest", kind: "state_forest", county: "Tompkins" }),
      line([[0, 0], [0.1, 0]], { name: "Town of Danby land", kind: "local_land", county: "Tompkins" }),
    ] },
    trails: { type: "FeatureCollection", features: [
      line([[0, 0], [0.001, 0]], { name: "Abbott Loop", kind: "footpath", county: "Tompkins" }),
      line([[0.002, 0], [0.003, 0]], { name: "Abbott Loop", kind: "footpath", county: "Tompkins, Tioga" }),
    ] },
  };
  const index = buildIndex(data);
  assert.deepEqual(search(index, "danby").map((i) => i.name), ["Danby State Forest", "Town of Danby land"]);
  assert.deepEqual(search(index, "lakes finger").map((i) => i.name), ["Finger Lakes Trail"]);
  const loop = search(index, "abbott");
  assert.equal(loop.length, 1);
  assert.equal(loop[0].county, "Tompkins, Tioga");
  assert.equal(loop[0].type, "Footpath");
  assert.deepEqual(search(index, "  "), []);
});

test("search puts what reaches further first: the long trail before its spur, the forest beside it", () => {
  const routes = [
    line([[-76.5, 42.3], [-76.48, 42.3]], { name: "Finger Lakes Trail Spur" }),
    line([[-77, 42.3], [-76, 42.5]], { name: "Finger Lakes Trail" }),
  ];
  const space = [line([[-76.9, 42.4], [-76.8, 42.5]], { name: "Finger Lakes National Forest", kind: "national_forest" }),
    line([[-76.5, 42.4], [-76.49, 42.41]], { name: "Finger Lakes Park", kind: "park" })];
  const index = buildIndex({ trail_routes: { features: routes }, open_space: { features: space } });
  assert.deepEqual(search(index, "finger lakes").map((i) => i.name),
    ["Finger Lakes Trail", "Finger Lakes National Forest", "Finger Lakes Trail Spur", "Finger Lakes Park"]);
});
