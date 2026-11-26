"""Trails and open space in the five counties -> data/trails_open_space.gpkg, in EPSG:26918.

open_space    public and protected land, with names. State, federal and land trust land is
              NYPAD's (the New York Protected Areas Database, NY Natural Heritage Program, as
              DEC serves it). The parks and preserves NYPAD lacks or leaves unnamed (city, town
              and county parks, Cornell's natural areas, nature centres, the Army Corps' land at
              Whitney Point) are OpenStreetMap's. NYPAD's city, town, county and district land
              with no OSM park over it stays, named for its owner, since NYPAD gives no other name.
trails        footpaths, bike paths, rail trails and bridle paths from OpenStreetMap, without
              the sidewalks and crossings, plus DEC's trails on state land where OSM has none.
trail_routes  named trail routes, from OSM's route relations: the Finger Lakes Trail and its
              branches and loops, the rail trails, the horse trails. Road walks included.

Downloads go to data/raw/ (gitignored): NYPAD and DEC's trails from DEC's ArcGIS Online, and
OpenStreetMap from Geofabrik's New York extract (about 500 MB; delete it to get a newer one).
Needs GDAL with its Python bindings (system python3 has them)."""
import json, os, re, subprocess, urllib.parse, urllib.request
from osgeo import gdal, ogr, osr

ogr.UseExceptions()
gdal.PushErrorHandler("CPLQuietErrorHandler")  # GEOS's notes on each invalid polygon it is asked to mend
ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = f"{ROOT}/data"
RAW = f"{DATA}/raw/open_space"
PBF = f"{DATA}/raw/osm/new-york-latest.osm.pbf"
OSM = f"{RAW}/osm.gpkg"
OUT = f"{DATA}/trails_open_space.gpkg"
AGOL = "https://services6.arcgis.com/DZHaqZm9cxOD4CWM/ArcGIS/rest/services"
UA = {"User-Agent": "southern-tier-map/1.0 (QGIS map build script)"}
UTM = osr.SpatialReference()
UTM.ImportFromEPSG(26918)

# The tags kept from OpenStreetMap (GDAL's OSM driver turns the colons into underscores)
OSMCONF = """[general]
closed_ways_are_polygons=aeroway,amenity,boundary,building,craft,geological,historic,landuse,leisure,military,natural,office,place,shop,sport,tourism,highway=platform,public_transport=platform
[points]
osm_id=yes
attributes=name
[lines]
osm_id=yes
attributes=name,highway,footway,path,cycleway,surface,access,bicycle,horse,mtb:scale,area
other_tags=no
[multipolygons]
osm_id=yes
attributes=name,type,leisure,boundary,protection_title,operator,access
other_tags=no
[multilinestrings]
osm_id=yes
attributes=name,type,route,network,ref,operator
other_tags=no
[other_relations]
osm_id=yes
attributes=name,type
other_tags=no
"""


def get(url, path):
    if not os.path.exists(path):
        urllib.request.urlretrieve(url, path + ".part")
        os.replace(path + ".part", path)


def arcgis(service, layer, path, env):
    """Every feature of an ArcGIS feature layer that meets env (WGS 84), as GeoJSON in UTM 18N"""
    feats, offset = [], 0
    while True:
        p = dict(where="1=1", geometry=",".join(map(str, env)), geometryType="esriGeometryEnvelope", inSR=4326,
                 spatialRel="esriSpatialRelIntersects", outFields="*", outSR=26918, f="geojson",
                 resultOffset=offset, resultRecordCount=1000, orderByFields="OBJECTID")
        r = json.load(urllib.request.urlopen(urllib.request.Request(
            f"{AGOL}/{service}/FeatureServer/{layer}/query", urllib.parse.urlencode(p).encode(), UA), timeout=300))
        if "error" in r:
            raise RuntimeError(r["error"])
        feats += r["features"]
        if not r.get("properties", {}).get("exceededTransferLimit") and len(r["features"]) < 1000:
            break
        offset += len(r["features"])
    json.dump({"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:26918"}},
               "features": feats}, open(path, "w"))
    return feats


def geom(feature):
    g = ogr.CreateGeometryFromJson(json.dumps(feature["geometry"])) if feature["geometry"] else None
    return g.MakeValid() if g is not None and not g.IsValid() else g


def multi(g, polygons):
    """g as a MultiPolygon or MultiLineString, dropping any points or lines a clip leaves"""
    want = ogr.wkbPolygon if polygons else ogr.wkbLineString
    out = ogr.Geometry(ogr.wkbMultiPolygon if polygons else ogr.wkbMultiLineString)
    if ogr.GT_Flatten(g.GetGeometryType()) == want:
        parts = [g]
    else:
        parts = [g.GetGeometryRef(i) for i in range(g.GetGeometryCount())]
    for p in parts:
        t = ogr.GT_Flatten(p.GetGeometryType())
        if t == want:
            out.AddGeometry(p)
        elif t in (ogr.wkbMultiPolygon, ogr.wkbMultiLineString, ogr.wkbGeometryCollection):
            sub = multi(p, polygons)
            for i in range(sub.GetGeometryCount()):
                out.AddGeometry(sub.GetGeometryRef(i))
    return out


def clip(g, county, polygons):
    if g is None or not g.Intersects(county):
        return None
    if not county.Contains(g):
        g = g.Intersection(county)
    g = multi(g, polygons)
    return g if g.GetGeometryCount() and (g.GetArea() if polygons else g.Length()) > 0 else None


def union(geoms):
    u = ogr.Geometry(ogr.wkbMultiPolygon)
    for g in geoms:
        u = u.Union(g)
    return u


def ends(line):
    """A way's identity, to find it among a route's member ways: its two ends and vertex count"""
    a, b = line.GetPoint_2D(0), line.GetPoint_2D(line.GetPointCount() - 1)
    return frozenset([(round(a[0], 2), round(a[1], 2)), (round(b[0], 2), round(b[1], 2))]), line.GetPointCount()


# ---------------------------------------------------------------- downloads
os.makedirs(RAW, exist_ok=True)
os.makedirs(os.path.dirname(PBF), exist_ok=True)
cds = ogr.Open(f"{DATA}/southern_tier.gpkg")
county = union(f.GetGeometryRef() for f in cds.GetLayer("counties"))
wgs = osr.SpatialReference()
wgs.ImportFromEPSG(4326)
wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
box = county.Clone()
box.AssignSpatialReference(UTM)
box.TransformTo(wgs)
w, e, s, n = box.GetEnvelope()
env = (round(w - 0.01, 4), round(s - 0.01, 4), round(e + 0.01, 4), round(n + 0.01, 4))

nypad = arcgis("NYPAD_view", 0, f"{RAW}/nypad.geojson", env)  # fee land only: the public view has no easements
dec = {}  # DEC's trail layers are one table seen by use (foot, ski, horse, bike, snowmobile): merged by id
for layer in range(1, 6):
    for f in arcgis("DEC_Trails", layer, f"{RAW}/dec_trails_{layer}.geojson", env):
        dec[f["properties"]["OBJECTID"]] = f
print(len(nypad), "NYPAD areas,", len(dec), "DEC trails")

get("https://download.geofabrik.de/north-america/us/new-york-latest.osm.pbf", PBF)
if not os.path.exists(OSM) or os.path.getmtime(OSM) < os.path.getmtime(PBF):
    open(f"{RAW}/osmconf.ini", "w").write(OSMCONF)
    if os.path.exists(OSM):
        os.remove(OSM)
    subprocess.run(["ogr2ogr", "-f", "GPKG", OSM, PBF, "-oo", f"CONFIG_FILE={RAW}/osmconf.ini",
                    "-spat", *map(str, env), "-t_srs", "EPSG:26918", "--config", "OSM_MAX_TMPFILE_SIZE", "2000",
                    "lines", "multipolygons", "multilinestrings"], check=True)
osm = ogr.Open(OSM)

# ---------------------------------------------------------------- open space
# NYPAD's designation types as kind codes, which build_map.py colours
KIND = {"NF": "national_forest", "SCA": "state_forest", "SRMA": "wma", "SP": "state_park", "SOTH": "state_other",
        "PCON": "preserve", "LP": "local_land", "LOTH": "local_land"}
MANAGER = {"SDC": "NYS DEC", "SPR": "NYS Parks", "USFS": "US Forest Service", "CITY": "city, town or village",
           "CNTY": "county", "RWD": "water district", "REG": "school district"}
ACCESS = {"OA": "open", "RA": "restricted", "XA": "closed", "UK": "unknown"}
OSM_ACCESS = {"yes": "open", "permissive": "open", "public": "open", "private": "private", "no": "private",
              "customers": "restricted", "destination": "restricted"}
TITLE = {"National Forest": "national_forest", "State Forest": "state_forest", "Wildlife Management Area": "wma",
         "State Park": "state_park"}


def owner_land(unit):
    """NYPAD's local land is named for its owner, in several word orders: "Cortland City of Land",
    "Groton The Village Of Land", "County Of Broome Land" -> "City of Cortland land", ..."""
    s = re.sub(r"\s+Land$", "", unit.strip())
    s = re.sub(r"^(.+?) (?:The )?(Town|City|Village|County) [Oo]f$", r"\2 of \1", s)
    s = re.sub(r"\bOf\b", "of", re.sub(r"\bCo$", "County", s))
    return s + " land"


def nypad_name(a):
    unit, loc = (a["Unit_Nm"] or "").strip(), (a["Loc_Nm"] or "").strip()
    if a["Des_Tp"] in ("LP", "LOTH"):
        return owner_land(unit)
    if a["Des_Tp"] == "PCON" and loc:  # the land trust's: Unit_Nm is "Finger Lakes Land Trust Land"
        return loc if " " in loc else f"{loc} (Finger Lakes Land Trust)"
    s = re.sub(r"\bWma$", "Wildlife Management Area", unit)  # DEC's names come title-cased from capitals
    s = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m[1].upper(), s)
    return re.sub(r"'S\b", "'s", s)


units = {}  # NYPAD's areas come in pieces: one feature per unit
for f in nypad:
    a, g = f["properties"], clip(geom(f), county, True)
    if g is None or g.GetArea() < 100:
        continue
    kind = KIND.get(a["Des_Tp"]) or ("state_park" if a["Mang_Name"] == "SPR" else "state_other")  # SREC
    manager = MANAGER.get(a["Mang_Name"])
    if a["Des_Tp"] == "PCON":
        fllt = (a["Unit_Nm"] or "").startswith("Finger Lakes Land Trust")
        manager = "Finger Lakes Land Trust" if fllt else "non-profit"
    key = (nypad_name(a), kind, manager)
    u = units.setdefault(key, {"geoms": [], "access": set()})
    u["geoms"].append(g)
    u["access"].add(ACCESS.get(a["Pub_Access"], "unknown"))
nypad_src = "NYPAD (NY Natural Heritage Program)"
areas, local = [], []
for (name, kind, manager), u in units.items():
    access = u["access"].pop() if len(u["access"]) == 1 else "partly open"
    g = multi(union(u["geoms"]), True)
    if kind != "local_land":
        areas.append(dict(name=name, kind=kind, manager=manager, access=access, geom=g, source=nypad_src))
    else:  # named only for its owner, so one name covers a county's parcels: each piece on its own
        local += [dict(name=name, kind=kind, manager=manager, access=access,
                       geom=multi(g.GetGeometryRef(i).Clone(), True), source=nypad_src)
                  for i in range(g.GetGeometryCount())]
state = union(a["geom"] for a in areas)

# OSM's parks and preserves, less those NYPAD has (half or more of the OSM area inside NYPAD's)
mp = osm.GetLayer("multipolygons")
mp.SetAttributeFilter("leisure IN ('park', 'nature_reserve') OR boundary IN ('protected_area', 'national_park')")
osm_areas = []
for f in mp:
    g = clip(f.GetGeometryRef().MakeValid(), county, True)
    if g is None or g.GetArea() < 100 or g.Intersection(state).GetArea() >= 0.5 * g.GetArea():
        continue
    kind = TITLE.get(f["protection_title"]) or ("park" if f["leisure"] == "park" else "preserve")
    osm_id = f"way {f['osm_way_id']}" if f["osm_way_id"] else f"relation {f['osm_id']}"
    osm_areas.append(dict(name=f["name"], kind=kind, manager=f["operator"], access=OSM_ACCESS.get(f["access"]),
                          geom=g, source=f"OpenStreetMap {osm_id}"))
# NYPAD's local land where OSM has a park (half or more of it under one) is that park
parks = union(a["geom"] for a in osm_areas)
local_kept = [a for a in local if a["geom"].Intersection(parks).GetArea() < 0.5 * a["geom"].GetArea()]
print(f"open space: {len(areas)} NYPAD state, federal and land trust areas, {len(osm_areas)} OSM parks and "
      f"preserves, {len(local_kept)} of NYPAD's {len(local)} pieces of local land")
areas += osm_areas + local_kept
open_space = union(a["geom"] for a in areas)

# ---------------------------------------------------------------- trail routes
ROUTES = ("hiking", "foot", "walking", "horse", "mtb", "ski", "running", "fitness_trail", "bicycle")
TRAILWAYS = ("path", "footway", "bridleway", "cycleway", "steps")
NOT_TRAIL = ("sidewalk", "crossing", "traffic_island", "access_aisle", "link", "alley")
lines = osm.GetLayer("lines")
lines.SetAttributeFilter(f"highway IN {TRAILWAYS}")
ways = {}
for f in lines:
    if f["footway"] in NOT_TRAIL or f["path"] in NOT_TRAIL or f["cycleway"] in NOT_TRAIL or f["area"] == "yes":
        continue
    ways[ends(f.GetGeometryRef())] = dict(
        osm_id=f["osm_id"], name=f["name"], highway=f["highway"], surface=f["surface"], access=f["access"],
        bicycle=f["bicycle"], horse=f["horse"], mtb=f["mtb_scale"], geom=f.GetGeometryRef().Clone(), routes=[],
        route_types=set())

rel = osm.GetLayer("multilinestrings")
rel.SetAttributeFilter(f"route IN {ROUTES}")
named = {}  # one trail is often a relation per use (hiking, horse, bike): one route per name
for f in rel:
    g = f.GetGeometryRef()
    members = [ways.get(ends(g.GetGeometryRef(i))) for i in range(g.GetGeometryCount())]
    c = clip(g, county, False)
    if c is None or c.Length() < 50:
        continue
    on_trails = sum(m["geom"].Length() for m in members if m)
    # Bike routes are mostly on roads (the state's bike routes, bike lanes): only those on trails
    # (the rail trails) are trail routes
    if f["route"] == "bicycle" and on_trails < 0.6 * g.Length():
        continue
    for m in members:
        if m:
            m["route_types"].add(f["route"])
            if f["name"] and f["name"] not in m["routes"]:
                m["routes"].append(f["name"])
    named.setdefault(f["name"] or f["osm_id"], []).append(dict(
        name=f["name"], route=f["route"], network=f["network"], ref=f["ref"], operator=f["operator"], geom=c,
        osm_id=f["osm_id"]))
routes = []
for rs in named.values():
    g = rs[0]["geom"]
    for r in rs[1:]:
        g = g.Union(r["geom"])
    g = multi(g, False)
    routes.append(dict(
        name=rs[0]["name"], route=", ".join(sorted({r["route"] for r in rs})),
        network=", ".join(sorted({r["network"] for r in rs if r["network"]})) or None,
        ref=next((r["ref"] for r in rs if r["ref"]), None),
        operator=next((r["operator"] for r in rs if r["operator"]), None),
        length_km=round(g.Length() / 1000, 1), geom=g,
        source="OpenStreetMap relation" + ("s " if len(rs) > 1 else " ") + ", ".join(r["osm_id"] for r in rs)))
print(len(routes), "trail routes")

# ---------------------------------------------------------------- trails
PAVED = ("asphalt", "concrete", "paved", "paving_stones", "concrete:plates", "concrete:lanes", "chipseal", "sett",
         "compacted", "fine_gravel")
UNPAVED = ("ground", "dirt", "earth", "unpaved", "gravel", "grass", "woodchips", "rock", "pebblestone", "mud", "sand",
           "wood")
near_open = open_space.Buffer(10)
trails = []
for wy in ways.values():
    g = clip(wy["geom"], county, False)
    if g is None:
        continue
    rt = wy["route_types"]
    # A footway or steps without a name, a route or a dirt surface, and outside the open space, is
    # a walk between buildings or across a lawn (campuses, parking lots, housing), not a trail
    if wy["highway"] in ("footway", "steps") and not (wy["name"] or rt or wy["surface"] in UNPAVED) \
            and not g.Intersects(near_open):
        continue
    if wy["access"] in ("private", "no"):
        kind = "private"
    elif wy["surface"] in PAVED or "bicycle" in rt or (wy["highway"] == "cycleway" and wy["surface"] not in UNPAVED):
        kind = "multiuse"
    elif wy["mtb"] or "mtb" in rt or wy["highway"] == "cycleway" or (wy["highway"] == "path" and
                                                                      wy["bicycle"] == "designated"):
        kind = "mtb"  # a cycleway of dirt is a mountain bike trail (Rowell Hill's, Hammond Hill's)
    elif wy["highway"] == "bridleway" or wy["horse"] == "designated" or "horse" in rt:
        kind = "horse"
    else:
        kind = "footpath"
    trails.append(dict(name=wy["name"], kind=kind, routes="; ".join(wy["routes"]) or None, highway=wy["highway"],
                       surface=wy["surface"], access=wy["access"], length_m=round(g.Length()), geom=g,
                       source=f"OpenStreetMap way {wy['osm_id']}"))
n_osm = len(trails)

# DEC's trails, where OSM has no trail within 20 m (its roads in the trail layers left out: they're roads)
osm_trails = ogr.GetDriverByName("MEM").CreateDataSource("")
tl = osm_trails.CreateLayer("t", UTM, ogr.wkbLineString)
for wy in ways.values():
    ft = ogr.Feature(tl.GetLayerDefn())
    ft.SetGeometry(wy["geom"])
    tl.CreateFeature(ft)


def dec_name(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    s = re.sub(r"\b(Flt|FLT)\b", "Finger Lakes Trail", s)
    return re.sub(r"\bMc([a-z])", lambda m: "Mc" + m[1].upper(), s) or None


for oid, f in sorted(dec.items()):
    a = f["properties"]
    if a["ASSET"] in ("UNPAVED ROAD", "PAVED ROAD", "CP3 ROUTE"):
        continue
    g = clip(geom(f), county, False)
    if g is None:
        continue
    tl.SetSpatialFilter(g.Buffer(25))
    near = ogr.Geometry(ogr.wkbMultiLineString)
    for ft in tl:
        near.AddGeometry(ft.GetGeometryRef())
    if near.GetGeometryCount():
        g = multi(g.Difference(near.Buffer(20)), False)
    pieces = ogr.Geometry(ogr.wkbMultiLineString)
    for i in range(g.GetGeometryCount()):
        if g.GetGeometryRef(i).Length() >= 50:  # not the stubs left at junctions and crossings
            pieces.AddGeometry(g.GetGeometryRef(i))
    if not pieces.GetGeometryCount():
        continue
    uses = {k for k in ("FOOT", "HORSE", "BIKE", "SNOWMB") if a[k] in ("Y", "M")}
    if a["ASSET"] == "SNOWMOBILE TRAIL" or uses == {"SNOWMB"}:
        kind = "snowmobile"
    elif "HORSE" in uses:
        kind = "horse"
    elif a["ASSET"] == "BIKE TRAIL" or "BIKE" in uses:
        kind = "mtb"
    else:
        kind = "footpath"
    trails.append(dict(name=dec_name(a["NAME"]), kind=kind, routes=None, highway=a["ASSET"].lower(), surface=None,
                       access=None, length_m=round(pieces.Length()), geom=pieces,
                       source=f"DEC trail {oid} ({a['FACILITY']})"))
print(f"trails: {n_osm} from OSM ({sum(t['length_m'] for t in trails[:n_osm]) / 1000:.0f} km), "
      f"{len(trails) - n_osm} from DEC ({sum(t['length_m'] for t in trails[n_osm:]) / 1000:.0f} km)")

# ---------------------------------------------------------------- write
for a in areas:
    a["area_ha"] = round(a["geom"].GetArea() / 1e4, 1)
NUMBERS = {"area_ha": ogr.OFTReal, "length_km": ogr.OFTReal, "length_m": ogr.OFTInteger}  # the rest are text
if os.path.exists(OUT):
    os.remove(OUT)
out = ogr.GetDriverByName("GPKG").CreateDataSource(OUT)
for name, gtype, fields, rows in (
        ("open_space", ogr.wkbMultiPolygon, "name kind manager access area_ha source",
         sorted(areas, key=lambda a: -a["area_ha"])),
        ("trails", ogr.wkbMultiLineString, "name kind routes highway surface access length_m source", trails),
        ("trail_routes", ogr.wkbMultiLineString, "name route network ref operator length_km source",
         sorted(routes, key=lambda r: -r["length_km"]))):
    lyr = out.CreateLayer(name, UTM, gtype, ["GEOMETRY_NAME=geom", "FID=fid"])
    for fname in fields.split():
        lyr.CreateField(ogr.FieldDefn(fname, NUMBERS.get(fname, ogr.OFTString)))
    lyr.StartTransaction()
    for r in rows:
        ft = ogr.Feature(lyr.GetLayerDefn())
        for fname in fields.split():
            if r.get(fname) is not None:
                ft.SetField(fname, r[fname])
        ft.SetGeometry(r["geom"])
        lyr.CreateFeature(ft)
    lyr.CommitTransaction()
out = None
print("wrote", OUT)
