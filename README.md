# Southern Tier

A map of five counties of New York's Southern Tier (Broome, Chemung, Schuyler, Tioga and
Tompkins): open space, trails and trail routes, and the old roads of Connecticut Hill Wildlife
Management Area, over NYS aerial imagery, 1 m lidar elevation and hillshade, and 1 m land use.

It comes two ways: a QGIS project (`southern_tier.qgz`, built by `build_map.py`), and a web app
of the same map (`public/`, built from the same data by `build_web.py`).

## The web app

`public/` is a static, no-build PWA. It's [MapLibre GL JS](https://maplibre.org/) 6.19 (vendored
in `public/vendor/maplibre-gl/`) drawing the map in QGIS's colours, with:

- **Layers** as in QGIS, with their legends, switched on and off as there (the choice is kept).
- **Click** (or tap) for what's there: every layer under the point, as QGIS's map tips show it.
  A trail on a route in a state forest shows all three.
- **Search** for a park, forest, trail, route or old road by name.
- **Go to** the whole map, a county, or Connecticut Hill (the QGIS project's bookmark).
- **The nine old roads** listed under their layer, with what the write-up says of each.
- My location, metric and imperial scale bars, and a URL that follows the view.
- Installable to a phone's home screen. Once opened, the app, its vector data and the tiles it
  has shown work offline; the imagery and hillshade, streamed from NYS and USGS, need a signal.

```sh
npm run dev       # http://localhost:8000 (scripts/serve.py: public/, Cache-Control: no-cache)
npm test          # node:test: tests/ (lib.js: popups, search, the categories against build_map.py)
```

### Its data

`build_web.py` makes `public/data/` and `public/tiles/` from `data/`. It runs with the system's
python3 and GDAL, not in QGIS:

```sh
python3 build_web.py              # everything (about a minute)
python3 build_web.py vectors      # the GeoPackages' layers as GeoJSON, and meta.json
python3 build_web.py landuse      # land use as WebP tiles, zoom 8-13 (5 MB)
python3 build_web.py elevation    # the tinted elevation as WebP tiles, zoom 8-13 (2 MB)
```

The land use and elevation tiles stop at zoom 13 (about 14 m a pixel; the map draws them bigger
beyond). Each level more would take about three times the tiles. The colours and classes come
from `build_map.py` itself, parsed rather than imported (it needs QGIS), and the tests check the
web map's line and fill styles against it. Change the two together.

Two layers aren't built, but streamed, as the QGIS project streams the imagery:

- **Imagery**: NYS ITS Geospatial Services' orthoimagery WMS, 2022-2025, the newest on top.
- **Hillshade**: USGS 3DEP's ImageServer, its multidirectional hillshade, from the same 1 m lidar
  as `data/hillshade_1m.tif`. QGIS multiplies it over the layers below at 60%; the app does the
  same by turning each tile's grey into black of matching opacity (`app.js`, `multiply:`).

Labels are drawn from DejaVu Sans, the QGIS project's font, by the browser (MapLibre's
`font-faces`), so there's no glyph server. `public/fonts/` has it cut down to Latin with fontTools
(`pyftsubset`, `--unicodes=U+0020-007E,U+00A0-00FF,U+2010-2027,U+2032-2033 --flavor=woff2`); the
oblique came from Ubuntu's `fonts-dejavu-extra`. Its licence is `public/fonts/LICENSE.txt`.

### Deploying

`.github/workflows/pages.yml` runs the tests and publishes `public/` to GitHub Pages on every push
to main (Settings → Pages → Source: GitHub Actions). The data in `public/` is committed: it's built
here, from rasters too big for git.

## The QGIS map

```sh
./fetch_boundaries.sh                 # Census counties -> data/southern_tier.gpkg
./fetch_landuse.sh                    # Chesapeake Bay Program land use -> data/landuse_2022.tif
python3 fetch_topo.py                 # USGS 1 m lidar -> data/dem_1m.tif, data/hillshade_1m.tif
python3 fetch_trails_open_space.py    # NYPAD, DEC and OSM -> data/trails_open_space.gpkg
python3 qgis_call.py exec build_map.py   # in the running QGIS (the QGIS MCP plugin's socket)
```

`data/connecticut_hill.gpkg` (the WMA, its roads today and the traced old roads) is committed as
it is. The rasters are gigabytes each and gitignored; the fetch scripts rebuild them.

## Sources

- Imagery: NYS ITS Geospatial Services orthoimagery (orthos.ny.gov).
- Elevation and hillshade: USGS 3D Elevation Program, 1 m lidar.
- Land use: Chesapeake Bay Program land use/land cover, 2024 Edition (USGS data release
  doi:10.5066/P14BEBRC).
- Open space: NYPAD, the New York Protected Areas Database (NY Natural Heritage Program), and
  OpenStreetMap.
- Trails and routes: OpenStreetMap, and NYS DEC's trails.
- Counties: U.S. Census Bureau 2025 cartographic boundaries.

OpenStreetMap data © OpenStreetMap contributors, under the ODbL. The old roads were traced from
the lidar and the 1893 and 1950 USGS topographic maps and haven't been checked on the ground.
