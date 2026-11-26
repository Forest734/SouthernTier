"""Build the web app's data from the map's: public/data and public/tiles.

    python3 build_web.py [vectors|landuse|elevation|all]   (default: all)

vectors:   every vector layer of build_map.py as GeoJSON in WGS 84 (public/data/*.geojson), with
           label points for the polygons, the white mask outside the counties, and meta.json
           (bookmarks, and the land use and elevation legends)
landuse:   data/landuse_2022.tif in build_map.py's colours, lossless WebP tiles, zoom 8 to 13
           (public/tiles/landuse)
elevation: data/dem_1m.tif tinted with build_map.py's ramp, WebP tiles, zoom 8 to 13
           (public/tiles/elevation)

Runs outside QGIS, with the system's GDAL. The imagery and the hillshade aren't built: the app
streams them, the imagery from NYS as the QGIS project does, and the hillshade from USGS 3DEP,
which made it from the same 1 m lidar.
"""
import ast, json, math, os, shutil, subprocess, sys
import numpy as np
from osgeo import gdal, ogr, osr
gdal.UseExceptions(); ogr.UseExceptions()

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = f"{ROOT}/data"
OUT = f"{ROOT}/public/data"
TILES = f"{ROOT}/public/tiles"
GPKG = f"{DATA}/southern_tier.gpkg"
CH = f"{DATA}/connecticut_hill.gpkg"
TOS = f"{DATA}/trails_open_space.gpkg"
# Zoom 13 is about 14 m a pixel here. Each level more is about three times the tiles; the app
# draws the last level bigger past it
MIN_ZOOM, MAX_ZOOM = 8, 13
RES0 = 2 * math.pi * 6378137 / 256  # Web Mercator metres a pixel at zoom 0

UTM = osr.SpatialReference(); UTM.ImportFromEPSG(26918)
WGS = osr.SpatialReference(); WGS.ImportFromEPSG(4326)
WGS.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)  # lon, lat
TO_WGS = osr.CoordinateTransformation(UTM, WGS)


def from_build_map(name):
    """A constant from build_map.py (the land use classes, the elevation ramp), so the two maps
    can't disagree. build_map.py itself needs QGIS, so it's parsed, not imported"""
    for node in ast.walk(ast.parse(open(f"{ROOT}/build_map.py").read())):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise KeyError(name)


def wgs_bounds(env, grow=0):
    """An (minx, maxx, miny, maxy) envelope in UTM as [west, south, east, north] in WGS 84"""
    x0, x1, y0, y1 = env[0] - grow, env[1] + grow, env[2] - grow, env[3] + grow
    ring = ogr.Geometry(ogr.wkbLinearRing)
    for x, y in [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]:
        ring.AddPoint_2D(x, y)
    box = ogr.Geometry(ogr.wkbPolygon); box.AddGeometry(ring)
    box.Segmentize(500)  # the box's edges curve in WGS 84
    box.Transform(TO_WGS)
    w, e, s, n = box.GetEnvelope()
    return [round(w, 5), round(s, 5), round(e, 5), round(n, 5)]


def features(gpkg, layer):
    """A layer's features. The dataset is held open while they're read: GDAL frees a layer whose
    dataset Python has dropped"""
    ds = ogr.Open(gpkg)
    return [f for f in ds.GetLayer(layer)]


def geometry_json(g, precision):
    g = g.Clone()
    g.Transform(TO_WGS)
    return json.loads(g.ExportToJson([f"COORDINATE_PRECISION={precision}"]))


def write(name, features):
    path = f"{OUT}/{name}.geojson"
    with open(path + ".tmp", "w") as f:
        json.dump({"type": "FeatureCollection", "features": features}, f, separators=(",", ":"))
    os.replace(path + ".tmp", path)
    print(f"  {name}.geojson: {len(features)} features, {os.path.getsize(path) // 1024} KB")


def vectors():
    os.makedirs(OUT, exist_ok=True)
    counties = [(f["county"], f.GetGeometryRef().Clone()) for f in features(GPKG, "counties")]
    counties.sort()

    def county_of(g):
        """The counties a feature is in, for telling apart search results of the same name"""
        env = g.GetEnvelope()
        names = []
        for name, cg in counties:
            ce = cg.GetEnvelope()
            if env[0] <= ce[1] and env[1] >= ce[0] and env[2] <= ce[3] and env[3] >= ce[2] and g.Intersects(cg):
                names.append(name)
        return ", ".join(names)

    def export(gpkg, layer, fields, precision, with_county=False, rounding=None):
        feats = []
        for f in features(gpkg, layer):
            g = f.GetGeometryRef()
            props = {k: f[k] for k in fields if f[k] not in (None, "")}
            for k, nd in (rounding or {}).items():
                if k in props:
                    props[k] = round(props[k], nd) if nd else int(round(props[k]))
            if with_county:
                props["county"] = county_of(g)
            feats.append({"type": "Feature", "properties": props, "geometry": geometry_json(g, precision),
                          "_g": g.Clone()})
        return feats

    def strip(feats):
        return [{k: v for k, v in f.items() if k != "_g"} for f in feats]

    print("vectors:")
    write("counties", strip(export(GPKG, "counties", ["county", "geoid"], 5)))
    space = export(TOS, "open_space", ["name", "kind", "manager", "access", "area_ha", "source"], 5,
                   with_county=True, rounding={"area_ha": 1})
    write("open_space", strip(space))
    wma = export(CH, "wma", ["name", "manager", "source", "area_ha"], 6)
    write("wma", strip(wma))
    write("roads", strip(export(CH, "roads", ["name", "highway", "kind", "surface"], 6)))
    old = export(CH, "old_roads", ["id", "old_map", "confidence", "length_m", "notes"], 6)
    write("old_roads", strip(old))
    write("trail_routes", strip(export(TOS, "trail_routes", ["name", "route", "network", "ref", "operator",
                                                              "length_km", "source"], 5, with_county=True,
                                       rounding={"length_km": 1})))
    trails = export(TOS, "trails", ["name", "kind", "routes", "highway", "surface", "access", "length_m", "source"], 5,
                    with_county=True)
    # The park or forest each trail is in, to tell apart the many Gorge Trails and Blue Trails:
    # the named open space it runs through furthest, local land only when there's nothing else
    named = [(f["properties"]["name"], f["properties"]["kind"] == "local_land", f["_g"], f["_g"].GetEnvelope())
             for f in space if f["properties"].get("name")]
    for t in trails:
        g = t["_g"]
        e = g.GetEnvelope()
        best = None
        for name, local, sg, se in named:
            if e[0] > se[1] or e[1] < se[0] or e[2] > se[3] or e[3] < se[2] or not g.Intersects(sg):
                continue
            inside = g.Intersection(sg)  # a point where a trail only touches the edge
            key = (not local, 0 if ogr.GT_Flatten(inside.GetGeometryType()) in (ogr.wkbPoint, ogr.wkbMultiPoint)
                   else inside.Length())
            if best is None or key > best[0]:
                best = (key, name)
        if best:
            t["properties"]["in"] = best[1]
    write("trails", strip(trails))

    # Polygon names at one point each, inside the polygon: the map would otherwise label every
    # tile a polygon crosses
    labels = []
    for layer, feats, key in [("county", None, "county"), ("open_space", space, "name"), ("wma", wma, "name")]:
        items = ([{"properties": {"county": n}, "_g": g} for n, g in counties] if feats is None else feats)
        for f in items:
            p = f["properties"]
            if not p.get(key):
                continue
            pt = f["_g"].PointOnSurface()
            props = {"layer": layer, "name": p[key]}
            props.update({k: p[k] for k in ("kind", "area_ha") if k in p})
            labels.append({"type": "Feature", "properties": props, "geometry": geometry_json(pt, 5)})
    write("labels", labels)

    # White outside the counties: the world, less the five of them
    union = None
    for _, g in counties:
        union = g.Clone() if union is None else union.Union(g)
    union.Transform(TO_WGS)
    world = ogr.CreateGeometryFromWkt("POLYGON((-180 -85,180 -85,180 85,-180 85,-180 -85))")
    mask = world.Difference(union)
    write("mask", [{"type": "Feature", "properties": {},
                    "geometry": json.loads(mask.ExportToJson(["COORDINATE_PRECISION=5"]))}])

    # Bookmarks: the whole map as build_map.py frames it (its extent scaled by 1.05), each county,
    # and the Connecticut Hill bookmark (the WMA and its old roads, grown 600 m)
    union_env = None
    for _, g in counties:
        e = g.GetEnvelope()
        union_env = e if union_env is None else (min(union_env[0], e[0]), max(union_env[1], e[1]),
                                                 min(union_env[2], e[2]), max(union_env[3], e[3]))
    grow = max(union_env[1] - union_env[0], union_env[3] - union_env[2]) * 0.025
    bookmarks = [{"name": "All five counties", "bounds": wgs_bounds(union_env, grow)}]
    bookmarks += [{"name": f"{n} County", "bounds": wgs_bounds(g.GetEnvelope(), 1500)} for n, g in counties]
    env = wma[0]["_g"].GetEnvelope()
    for f in old:
        e = f["_g"].GetEnvelope()
        env = (min(env[0], e[0]), max(env[1], e[1]), min(env[2], e[2]), max(env[3], e[3]))
    bookmarks.append({"name": "Connecticut Hill WMA", "bounds": wgs_bounds(env, 600)})

    update_meta("bookmarks", bookmarks)


def update_meta(key, value):
    """meta.json holds a key from each step, so one step can be rerun alone"""
    path = f"{OUT}/meta.json"
    meta = json.load(open(path)) if os.path.exists(path) else {}
    meta[key] = value
    with open(path, "w") as f:
        json.dump(meta, f, indent=1)
        f.write("\n")


def tile(src, out, zoom, fmt_opts):
    """One zoom level of tiles from a raster already warped to that level's grid, so each tile is
    a straight copy of its pixels"""
    cmd = ["gdal", "raster", "tile", "-q", "--format", "WEBP", *fmt_opts, "--min-zoom", str(zoom),
           "--max-zoom", str(zoom), "-r", "nearest", "--skip-blank", "--webviewer", "none", src, out]
    subprocess.run(cmd, check=True)


def warp(src, dst, zoom, resampling, src_nodata, dst_nodata, dtype=None):
    res = RES0 / 2 ** zoom
    # -tap lines the pixels up with the tile grid: its origin is a whole number of pixels from 0
    gdal.Warp(dst, src, dstSRS="EPSG:3857", xRes=res, yRes=res, targetAlignedPixels=True,
              resampleAlg=resampling, srcNodata=src_nodata, dstNodata=dst_nodata, outputType=dtype or gdal.GDT_Unknown,
              multithread=True, warpOptions=["NUM_THREADS=ALL_CPUS"], creationOptions=["COMPRESS=ZSTD", "TILED=YES"])


def tile_dir(name):
    out = f"{TILES}/{name}"
    if os.path.isdir(out):
        shutil.rmtree(out)  # a tile left from an older build would show where it shouldn't
    tmp = f"{TILES}/.{name}.tmp"
    os.makedirs(tmp, exist_ok=True)
    return out, tmp


def report(name, out):
    files = [os.path.join(r, f) for r, _, fs in os.walk(out) for f in fs]
    print(f"  {name}: {len(files)} tiles, {sum(map(os.path.getsize, files)) // 1024} KB")


def landuse():
    src = f"{DATA}/landuse_2022.tif"
    if not os.path.exists(src):
        print("landuse: no", src, "(fetch_landuse.sh)"); return
    print("landuse:")
    classes = from_build_map("LANDUSE")
    ct = gdal.ColorTable()
    ct.SetColorEntry(0, (0, 0, 0, 0))
    for v, c, _ in classes:
        ct.SetColorEntry(v, (int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16), 255))
    out, tmp = tile_dir("landuse")
    for z in range(MIN_ZOOM, MAX_ZOOM + 1):
        # Each level straight from the 1 m classes (GDAL reads the file's overviews), by mode:
        # averaging colours would make classes that aren't there
        warp(src, f"{tmp}/{z}.tif", z, "mode", 0, 0)
        ds = gdal.Open(f"{tmp}/{z}.tif", gdal.GA_Update)
        ds.GetRasterBand(1).SetRasterColorTable(ct)
        ds = None
        gdal.Translate(f"{tmp}/{z}.vrt", f"{tmp}/{z}.tif", format="VRT", rgbExpand="rgba")
        tile(f"{tmp}/{z}.vrt", out, z, ["--co", "LOSSLESS=TRUE"])
    shutil.rmtree(tmp)
    report("landuse", out)
    # The legend lists the classes there are, from the 16 m overview (a class too small to show
    # there doesn't show in the tiles either)
    ds = gdal.Open(src)
    band = ds.GetRasterBand(1)
    ov = band.GetOverview(min(2, band.GetOverviewCount() - 1)).ReadAsArray()
    present = set(np.unique(ov).tolist()) - {0}
    update_meta("landuse", {"maxzoom": MAX_ZOOM, "opacity": 0.5,
                            "classes": [[v, c, n] for v, c, n in classes if v in present]})


def elevation():
    src = f"{DATA}/dem_1m.tif"
    if not os.path.exists(src):
        print("elevation: no", src, "(fetch_topo.py)"); return
    print("elevation:")
    # The ramp as build_map.py stretches it: its stops spread evenly from the lowest to the
    # highest value in GDAL's approximate statistics, which is what QGIS's sample finds
    ds = gdal.Open(src)
    stats = ds.GetRasterBand(1).ComputeStatistics(True)
    ds = None
    lo, hi = stats[0], stats[1]
    stops = from_build_map("stops")
    ramp = [[round(lo + (hi - lo) * i / (len(stops) - 1), 1), c] for i, c in enumerate(stops)]
    out, tmp = tile_dir("elevation")
    with open(f"{tmp}/ramp.txt", "w") as f:
        f.write("nv 0 0 0 0\n")
        for v, c in ramp:
            f.write(f"{v} {int(c[1:3], 16)} {int(c[3:5], 16)} {int(c[5:7], 16)} 255\n")
    for z in range(MIN_ZOOM, MAX_ZOOM + 1):
        # Tint after averaging the heights, not average the tints
        warp(src, f"{tmp}/{z}.tif", z, "average", -999999, -999999, gdal.GDT_Float32)
        gdal.DEMProcessing(f"{tmp}/{z}_rgba.tif", f"{tmp}/{z}.tif", "color-relief", colorFilename=f"{tmp}/ramp.txt",
                           addAlpha=True, creationOptions=["COMPRESS=ZSTD", "TILED=YES"])
        tile(f"{tmp}/{z}_rgba.tif", out, z, ["--co", "QUALITY=88"])
    shutil.rmtree(tmp)
    report("elevation", out)
    update_meta("elevation", {"maxzoom": MAX_ZOOM, "ramp": ramp})


if __name__ == "__main__":
    steps = {"vectors": vectors, "landuse": landuse, "elevation": elevation}
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    for name, fn in steps.items():
        if which in (name, "all"):
            fn()
