# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

A map of five Southern Tier counties of New York, two ways: a QGIS project (`build_map.py` →
`southern_tier.qgz`, run inside QGIS through `qgis_call.py`), and a static, no-build PWA of the
same map in `public/` (MapLibre GL JS 6.19, vendored), deployed to GitHub Pages. README.md covers
the data, the rebuild steps and the sources.

## Commands

```sh
npm run dev                          # http://localhost:8000 (scripts/serve.py: public/, Cache-Control: no-cache)
npm test                             # node:test, tests/ (lib.js only)
python3 build_web.py [vectors|landuse|elevation|all]   # data/ -> public/data, public/tiles (system GDAL)
python3 qgis_call.py exec build_map.py                 # rebuild the QGIS project (QGIS running, MCP plugin on)
```

`node --check public/*.js` catches syntax errors. UI changes need a browser: headless Chrome over
CDP from a throwaway Node script (Node's `WebSocket`), started with `--use-angle=swiftshader
--enable-unsafe-swiftshader` or MapLibre gets no WebGL. Set the view with the URL hash
(`#zoom/lat/lon`); `Emulation.setDeviceMetricsOverride` with `mobile: true` for the phone layout
(drawer under 760px). The imagery and hillshade need the network.

## Architecture

- `build_map.py` is the source of the map's look. `build_web.py` parses its `LANDUSE` and
  `stops` (ast; it imports QGIS so it can't be imported). `public/lib.js` copies its open space,
  roads, trails and old roads categories (colour, mm widths, Qt dash names), and
  `tests/lib.test.js` checks those against `build_map.py`'s text. Change both together.
- `build_web.py`: vectors to WGS 84 GeoJSON (5 decimals, 6 for Connecticut Hill), each feature's
  `county`, each trail's `in` (the named open space it runs through furthest, for search), polygon
  label points (`labels.geojson`; MapLibre would label every tile a polygon crosses), the mask (the
  world less the counties), `meta.json` (bookmarks, land use classes present, the elevation ramp).
  Rasters: each zoom level warped to the tile grid on its own (`-tap`), land use by mode on the
  class codes before colouring, elevation averaged before tinting, then `gdal raster tile` copies
  pixels with nearest. Zoom 8-13 (`MAX_ZOOM`).
- `public/style.js` builds the style: build_map.py's layers in its order, QGIS scales as zooms
  (`zoomForScale`: 96 dpi at 42.3° N), symbol layers last with the most important on top (MapLibre
  places the top layer's labels first). `GROUPS` is the panel's list; each style layer carries
  `metadata.group`. GeoJSON sources start empty; `app.js` fetches the data (it needs it for
  search) and `setData`s it.
- No `glyphs`: the style's `font-faces` points at `public/fonts/` (DejaVu Sans, subset to Latin).
  A name outside those codepoints would need the subset widened.
- The hillshade is USGS 3DEP's `exportImage` through the `multiply:` protocol in `app.js`, which
  makes grey into black at opacity 1 − grey: QGIS's multiply blend, under the layer's 0.6.
- Popup and search text is plain (`describe`, `search` in `lib.js`) and set with `textContent`.
  The only markup from strings is the attribution HTML MapLibre renders from `style.js`.
- localStorage under `southerntier:` (`layers`, `view`), every access in try/catch. `sw.js` caches
  as `southerntier-v1`, precaches the app and data, network-first for same-origin GETs (tiles get
  cached as they're shown); it deletes only `southerntier-*` caches, since the origin is shared.
- Relative paths throughout: Pages serves it from `/SouthernTier/`. MapLibre loads its worker
  from beside `maplibre-gl.mjs` with `?v=<version>`; `sw.js` matches it offline with `ignoreSearch`.

## Conventions

- Keep it build-free: vendored files are copied from the npm tarball (`npm pack maplibre-gl`),
  with the `sourceMappingURL` lines dropped.
- Keep the sources' credits (panel footer, and each source's `attribution`), OpenStreetMap's
  under the ODbL.
- CHANGELOG.md follows Keep a Changelog. Add user-facing changes under [Unreleased].
