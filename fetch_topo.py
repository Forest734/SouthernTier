"""USGS 3DEP 1 m lidar DEM for the five counties -> data/dem_1m.tif and data/hillshade_1m.tif.

    python3 fetch_topo.py [select|download|fill|mosaic|hillshade|all]   (default: all)

select:    ask The National Map which 1 m DEM tiles touch the counties, then keep the fewest
           that cover them, newest lidar first (reads each tile's small overview over HTTP)
           -> data/raw/dem/tiles.json
download:  fetch those tiles into data/raw/dem/ (resumable: rerun after an interruption)
fill:      where no 1 m tile has data (the Cayuga Lake water inside Tompkins County, which
           no lidar survey delivered), USGS's seamless 1/3 arc-second (~10 m) DEM in 1 km
           squares on the 1 m grid, which the mosaic puts under the 1 m tiles
mosaic:    newest-on-top mosaic clipped to the counties, EPSG:26918, metres above NAVD88,
           as a COG with LERC compression (every value within 1 cm of the source)
hillshade: multidirectional hillshade of the mosaic
"""
import glob, json, os, re, subprocess, sys, urllib.parse, urllib.request
import numpy as np
from osgeo import gdal, ogr
gdal.UseExceptions(); ogr.UseExceptions()

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = f"{ROOT}/data"
RAW = f"{DATA}/raw/dem"
GPKG = f"{DATA}/southern_tier.gpkg"
TILES = f"{RAW}/tiles.json"
DEM = f"{DATA}/dem_1m.tif"
HILLSHADE = f"{DATA}/hillshade_1m.tif"
FILL = f"{RAW}/fill"
SEAMLESS_13 = "/vsicurl/https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/USGS_Seamless_DEM_13.vrt"
GRID = 32  # metres: the coverage check's grid, about the size of each tile's small overview
TILE_NAME = re.compile(r"USGS_(?:1M_(\d+)|one_meter)_x(\d+)y(\d+)_(.+)\.tif$")


def counties():
    ds = ogr.Open(GPKG)
    u = None
    for f in ds.GetLayer("counties"):
        g = f.GetGeometryRef().Clone()
        u = g if u is None else u.Union(g)
    return u


def select():
    area = counties()
    wgs = area.Clone()
    srs = ogr.osr.SpatialReference(); srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(ogr.osr.OAMS_TRADITIONAL_GIS_ORDER)
    wgs.TransformTo(srs)
    minx, maxx, miny, maxy = wgs.GetEnvelope()
    q = urllib.parse.urlencode({"datasets": "Digital Elevation Model (DEM) 1 meter",
                                "bbox": f"{minx},{miny},{maxx},{maxy}", "max": 1000, "outputFormat": "JSON"})
    items = json.load(urllib.request.urlopen("https://tnmaccess.nationalmap.gov/api/v1/products?" + q, timeout=300))["items"]
    tiles = []
    for i in items:
        m = TILE_NAME.search(i["downloadURL"])
        if not m or int(m[1] or 18) != 18:
            print("skipping", i["downloadURL"]); continue
        x0, y1 = int(m[2]) * 10000, int(m[3]) * 10000
        ring = ogr.Geometry(ogr.wkbLinearRing)
        for px, py in [(x0, y1 - 10000), (x0 + 10000, y1 - 10000), (x0 + 10000, y1), (x0, y1), (x0, y1 - 10000)]:
            ring.AddPoint_2D(px, py)
        cell = ogr.Geometry(ogr.wkbPolygon); cell.AddGeometry(ring)
        if cell.Intersects(area):
            year = int(re.search(r"(20\d\d)", m[4])[1])
            tiles.append({"url": i["downloadURL"], "project": m[4], "year": year,
                          "cell": [x0, y1 - 10000, x0 + 10000, y1], "size": i.get("sizeInBytes") or 0})
    print(f"{len(tiles)} tiles touch the counties")

    # Coverage grid over the counties, snapped to the 10 km tile grid
    ax0, ax1, ay0, ay1 = area.GetEnvelope()
    gx0, gy0 = int(ax0 // 10000) * 10000, int(ay0 // 10000) * 10000
    gx1, gy1 = -int(-ax1 // 10000) * 10000, -int(-ay1 // 10000) * 10000
    w, h = (gx1 - gx0) // GRID + 1, (gy1 - gy0) // GRID + 1
    gt = (gx0, GRID, 0, gy0 + h * GRID, 0, -GRID)
    mask = gdal.GetDriverByName("MEM").Create("", w, h, 1, gdal.GDT_Byte)
    utm = ogr.osr.SpatialReference(); utm.ImportFromEPSG(26918)
    mask.SetGeoTransform(gt); mask.SetProjection(utm.ExportToWkt())
    gdal.Rasterize(mask, GPKG, layers=["counties"], burnValues=[1], allTouched=True)
    inside = mask.ReadAsArray().astype(bool)
    covered = np.zeros_like(inside)

    def grow(a, n=2):  # binary dilation by n grid cells
        for _ in range(n):
            b = a.copy()
            b[1:] |= a[:-1]; b[:-1] |= a[1:]; b[:, 1:] |= a[:, :-1]; b[:, :-1] |= a[:, 1:]
            a = b
        return a

    keep = []
    # New York's own surveys first, then the newest; a tile is kept if it has data where the
    # counties still need it. A 32 m overview cell can show data where its 1 m pixels are
    # partly empty, so the still-needed area is grown by two cells to keep the tiles that
    # fill the seams between surveys.
    for t in sorted(tiles, key=lambda t: (not t["project"].startswith("NY_"), -t["year"], t["project"], t["cell"])):
        x0, y0, x1, y1 = t["cell"]
        c0, r0 = (x0 - gx0) // GRID, (gy0 + h * GRID - y1) // GRID
        c1, r1 = min(w, c0 + 10000 // GRID + 1), min(h, r0 + 10000 // GRID + 1)
        # -ovr AUTO-1: one overview finer than the 32 m grid calls for; some older tiles'
        # smallest overview is empty although the tile has data
        sub = gdal.Warp("", "/vsicurl/" + t["url"], format="MEM", dstSRS="EPSG:26918", options=["-ovr", "AUTO-1"],
                        outputBounds=(gx0 + c0 * GRID, gy0 + h * GRID - r1 * GRID, gx0 + c1 * GRID, gy0 + h * GRID - r0 * GRID),
                        xRes=GRID, yRes=GRID, resampleAlg="near", dstNodata=np.nan, outputType=gdal.GDT_Float32)
        valid = ~np.isnan(sub.ReadAsArray())
        need = inside[r0:r1, c0:c1] & grow(~covered)[r0:r1, c0:c1]
        if (valid & need).any():
            keep.append(t)
            covered[r0:r1, c0:c1] |= valid
        print(f"{'keep' if keep and keep[-1] is t else 'drop'} {t['project']} {t['cell'][0]//10000},{t['cell'][3]//10000}")
    gaps = inside & ~covered
    print(f"kept {len(keep)} of {len(tiles)} tiles, {sum(t['size'] for t in keep)/1e9:.1f} GB; "
          f"county area with no 1 m data: {gaps.sum() * GRID * GRID / 1e6:.2f} km²")
    os.makedirs(RAW, exist_ok=True)
    json.dump(keep, open(TILES, "w"), indent=1)
    out = gdal.GetDriverByName("GTiff").CreateCopy(f"{RAW}/gaps_{GRID}m.tif", mask)
    out.GetRasterBand(1).WriteArray(gaps.astype(np.uint8))
    out = None


def path(t):
    return f"{RAW}/{t['url'].rsplit('/', 1)[1]}"


def download():
    tiles = json.load(open(TILES))
    for n, t in enumerate(tiles, 1):
        out = path(t)
        if os.path.exists(out):
            continue
        print(f"[{n}/{len(tiles)}] {os.path.basename(out)}", flush=True)
        subprocess.run(["wget", "-q", "-c", "-O", out + ".part", t["url"]], check=True)
        gdal.Info(out + ".part")  # raises if the file is not a readable GeoTIFF
        os.replace(out + ".part", out)
    print("downloaded", len(tiles), "tiles")


def fill():
    g = gdal.Open(f"{RAW}/gaps_{GRID}m.tif")
    gt = g.GetGeoTransform()
    rows, cols = np.nonzero(g.ReadAsArray())
    squares = set()
    for r, c in zip(rows, cols):  # every 1 km square a gap cell touches, by its corners
        for dx in (0, GRID):
            for dy in (0, GRID):
                squares.add((int((gt[0] + c * GRID + dx) // 1000), int((gt[3] - r * GRID - dy) // 1000)))
    os.makedirs(FILL, exist_ok=True)
    for x, y in sorted(squares):
        out = f"{FILL}/fill_{x}_{y}.tif"
        if not os.path.exists(out):
            gdal.Warp(out, SEAMLESS_13, dstSRS="EPSG:26918", outputBounds=(x * 1000, y * 1000, x * 1000 + 1000, y * 1000 + 1000),
                      xRes=1, yRes=1, resampleAlg="bilinear", dstNodata=-999999, outputType=gdal.GDT_Float32,
                      creationOptions=["TILED=YES", "COMPRESS=ZSTD", "PREDICTOR=3"])
    print(len(squares), "1 km fill squares from the 1/3 arc-second DEM")


def mosaic():
    """Warp on all cores into an uncompressed temp (about 40 GB), then compress: gdalwarp
    straight into a compressed GeoTIFF this size rewrites blocks over and over, and
    gdal_translate reading a warped VRT runs on one core; either takes hours. All the
    surveys here are delivered in EPSG:26918 on the same 1 m grid, so one VRT mosaics them."""
    tiles = json.load(open(TILES))
    # A VRT mosaic takes later sources over earlier ones, so the preferred tiles go last
    # (the reverse of select's order), and the 10 m fill goes first, under everything
    srcs = [path(t) for t in sorted(tiles, key=lambda t: (t["project"].startswith("NY_"), t["year"], t["project"]))]
    srcs = sorted(glob.glob(f"{FILL}/fill_*.tif")) + srcs
    gdal.BuildVRT(f"{RAW}/mosaic.vrt", srcs, srcNodata=-999999, VRTNodata=-999999)
    warped = f"{RAW}/dem_1m.warped.tif"
    subprocess.run(["gdalwarp", "-overwrite", "-t_srs", "EPSG:26918", "-tr", "1", "1", "-tap", "-r", "near",
                    "-dstnodata", "-999999", "-cutline", GPKG, "-cl", "counties", "-crop_to_cutline",
                    "-multi", "-wo", "NUM_THREADS=ALL_CPUS", "-wm", "1024", "--config", "GDAL_NUM_THREADS", "ALL_CPUS",
                    "-co", "TILED=YES", "-co", "BIGTIFF=YES", f"{RAW}/mosaic.vrt", warped], check=True)
    subprocess.run(["gdal_translate", "-of", "COG", "-co", "COMPRESS=LERC_ZSTD", "-co", "MAX_Z_ERROR=0.01",
                    "-co", "BIGTIFF=YES", "-co", "NUM_THREADS=ALL_CPUS", "-co", "OVERVIEW_RESAMPLING=AVERAGE",
                    "-mo", "VERTICAL_DATUM=NAVD88 (metres)", "-mo", "SOURCE=USGS 3DEP 1 m DEM: " +
                    ", ".join(sorted({t['project'] for t in tiles})) + "; USGS 1/3 arc-second DEM where none",
                    warped, DEM + ".tmp"], check=True)
    os.replace(DEM + ".tmp", DEM)  # only a finished file gets the name build_map.py looks for
    os.remove(warped)


def hillshade():
    tmp = HILLSHADE + ".tmp.tif"
    subprocess.run(["gdaldem", "hillshade", "-multidirectional", "-compute_edges", "--config", "GDAL_CACHEMAX", "1024",
                    "-co", "TILED=YES", "-co", "COMPRESS=ZSTD", "-co", "BIGTIFF=YES", DEM, tmp], check=True)
    subprocess.run(["gdal_translate", "-of", "COG", "-a_nodata", "0", "-co", "COMPRESS=ZSTD",
                    "-co", "BIGTIFF=YES", "-co", "NUM_THREADS=ALL_CPUS", "-co", "OVERVIEW_RESAMPLING=AVERAGE",
                    "--config", "GDAL_CACHEMAX", "1024", tmp, HILLSHADE + ".tmp"], check=True)
    os.replace(HILLSHADE + ".tmp", HILLSHADE)
    os.remove(tmp)


if __name__ == "__main__":
    steps = {"select": select, "download": download, "fill": fill, "mosaic": mosaic, "hillshade": hillshade}
    for s in (list(steps) if sys.argv[1:] in ([], ["all"]) else sys.argv[1:]):
        steps[s]()
