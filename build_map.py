"""Build the map in the running QGIS (Python console, or qgis_call.py exec).

Layers whose data isn't fetched yet (fetch_landuse.sh, fetch_topo.py) are left out."""
from qgis.core import (
    Qgis, QgsColorRampShader, QgsCoordinateReferenceSystem, QgsDatumTransform, QgsFillSymbol,
    QgsInvertedPolygonRenderer, QgsPalettedRasterRenderer, QgsPalLayerSettings, QgsProject,
    QgsRasterLayer, QgsRasterShader, QgsReferencedRectangle, QgsSingleBandGrayRenderer,
    QgsSingleBandPseudoColorRenderer, QgsSingleSymbolRenderer, QgsTextBufferSettings, QgsTextFormat,
    QgsVectorLayer, QgsVectorLayerSimpleLabeling,
)
from qgis.utils import iface
import os
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtGui import QColor, QFont, QPainter

# Repo root: qgis_call.py passes it in; in the QGIS Python console set ROOT first
ROOT = globals().get("ROOT") or os.path.expanduser("~/dev/SouthernTier")
DATA = f"{ROOT}/data"
GPKG = f"{DATA}/southern_tier.gpkg"
project = QgsProject.instance()
project.clear()
project.setCrs(QgsCoordinateReferenceSystem("EPSG:26918"))
project.setTitle("Counties of the Southern Tier of New York")

# NYS orthoimagery, about 12 in (30 cm), streamed from NYS ITS Geospatial Services. The
# service's layers are flight years (0 = 2025 ... 3 = 2022); WMS draws the list left to
# right, so the newest goes last, on top.
# The imagery comes in Web Mercator (WGS 84); there are several ways from WGS 84 to NAD83,
# so QGIS stops to ask unless the project names one. Use the first PROJ can run here (the
# others need NOAA's New York and Pennsylvania HPGN grids, not installed).
merc = QgsCoordinateReferenceSystem("EPSG:3857")
op = next(o for o in QgsDatumTransform.operations(merc, project.crs()) if o.isAvailable)
ctx = project.transformContext()
ctx.addCoordinateOperation(merc, project.crs(), op.proj)
project.setTransformContext(ctx)

imagery = QgsRasterLayer(
    "contextualWMSLegend=0&crs=EPSG:3857&dpiMode=7&format=image/jpeg"
    "&layers=3&layers=2&layers=1&layers=0&styles=&styles=&styles=&styles="
    "&url=https://orthos.its.ny.gov/arcgis/services/wms/Latest/MapServer/WMSServer",
    "NYS orthoimagery 2022-2025", "wms")
assert imagery.isValid()

layers = [imagery]  # bottom to top

# Elevation: 1 m lidar DEM, tinted low green to high brown (fetch_topo.py)
if os.path.exists(f"{DATA}/dem_1m.tif"):
    dem = QgsRasterLayer(f"{DATA}/dem_1m.tif", "Elevation (1 m lidar)")
    stats = dem.dataProvider().bandStatistics(1, Qgis.RasterBandStatistic.Min | Qgis.RasterBandStatistic.Max,
                                              dem.extent(), 250000)
    lo, hi = stats.minimumValue, stats.maximumValue
    ramp = QgsColorRampShader(lo, hi)
    ramp.setColorRampType(QgsColorRampShader.Interpolated)
    stops = ["#5a8a50", "#a8c47a", "#e9e2a6", "#c9a36b", "#8a6a4a", "#f2efe9"]
    ramp.setColorRampItemList([QgsColorRampShader.ColorRampItem(lo + (hi - lo) * i / (len(stops) - 1), QColor(c),
                               f"{lo + (hi - lo) * i / (len(stops) - 1):.0f} m") for i, c in enumerate(stops)])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp)
    dem.setRenderer(QgsSingleBandPseudoColorRenderer(dem.dataProvider(), 1, shader))
    layers.append(dem)

# Land use/land cover 2021/22, 1 m, Chesapeake Bay Program classes (fetch_landuse.sh)
LANDUSE = [
    (10, "#1f5f9f", "Tidal Waters"), (11, "#2f6fb0", "Lakes and Reservoirs"),
    (12, "#4a88c4", "Riverine Ponds"), (13, "#5b95cc", "Terrene Ponds"),
    (14, "#3b7dc0", "Streams and Rivers"), (15, "#e8dcc0", "Bare Shore"),
    (20, "#3c3c3c", "Roads"), (21, "#c8312d", "Structures"), (22, "#8a8a8a", "Other Impervious"),
    (23, "#55704a", "Tree Canopy Over Roads"), (24, "#5f7d4f", "Tree Canopy Over Structures"),
    (25, "#677f55", "Tree Canopy Over Other Impervious"), (26, "#7fa35f", "Tree Canopy Over Turf Grass"),
    (27, "#b7d98f", "Turf Grass"), (28, "#d9c7a5", "Bare Developed"),
    (30, "#a87d55", "Extractive Barren"), (31, "#8c6744", "Extractive Impervious"),
    (32, "#6b4fa0", "Solar Field Panel Arrays"), (33, "#9b86c4", "Solar Field Barren"),
    (34, "#a996cf", "Solar Field Herbaceous"), (35, "#b7a6d8", "Solar Field Shrubland"),
    (36, "#d6c7a0", "Suspended Succession Barren"), (37, "#d9d39b", "Suspended Succession Herbaceous"),
    (38, "#c5c88a", "Suspended Succession Shrubland"),
    (40, "#2c6b2f", "Forest"), (41, "#3f7f3a", "Forested Other"),
    (42, "#cfc39a", "Natural Succession Barren"), (43, "#c8d98e", "Natural Succession Herbaceous"),
    (44, "#93b56a", "Natural Succession Shrubland"),
    (45, "#b8a273", "Harvested Forest Barren"), (46, "#bfb47c", "Harvested Forest Herbaceous"),
    (50, "#9fc9c0", "Riverine Wetlands Barren"), (51, "#6fbcae", "Riverine Wetlands Herbaceous"),
    (52, "#4fa898", "Riverine Wetlands Shrubland"), (53, "#3a9384", "Riverine Wetlands Forested Other"),
    (54, "#2e8072", "Riverine Wetlands Forest"), (55, "#7fb1a5", "Riverine Wetlands Harvested Forest"),
    (60, "#b3d9d4", "Terrene Wetlands Barren"), (61, "#86cfc6", "Terrene Wetlands Herbaceous"),
    (62, "#64bdb2", "Terrene Wetlands Shrubland"), (63, "#4aa99d", "Terrene Wetlands Forested Other"),
    (64, "#36958a", "Terrene Wetlands Forest"), (65, "#93c4bc", "Terrene Wetlands Harvested Forest"),
    (70, "#a6c8d8", "Tidal Wetlands Barren"), (71, "#7fb3cc", "Tidal Wetlands Herbaceous"),
    (72, "#5f9fbf", "Tidal Wetlands Shrubland"), (73, "#4a8db0", "Tidal Wetlands Forested Other"),
    (74, "#3b7ca0", "Tidal Wetlands Forest"), (75, "#8fb6c8", "Tidal Wetlands Harvested Forest"),
    (80, "#e3c58f", "Cropland Barren"), (81, "#f0cf5a", "Cropland Herbaceous"),
    (82, "#d7a9c9", "Orchards and Vineyards Barren"), (83, "#c98bb9", "Orchards and Vineyards Herbaceous"),
    (84, "#b46fa3", "Orchards and Vineyards Shrubland"),
    (85, "#ece3b0", "Pasture and Hay Barren"), (86, "#e6e08a", "Pasture and Hay Herbaceous"),
]
if os.path.exists(f"{DATA}/landuse_2022.tif"):
    landuse = QgsRasterLayer(f"{DATA}/landuse_2022.tif", "Land use 2021/22 (1 m)")
    landuse.setRenderer(QgsPalettedRasterRenderer(landuse.dataProvider(), 1, [
        QgsPalettedRasterRenderer.Class(v, QColor(c), name) for v, c, name in LANDUSE]))
    layers.append(landuse)

# Hillshade, multiplied over whatever is below it (fetch_topo.py)
if os.path.exists(f"{DATA}/hillshade_1m.tif"):
    hillshade = QgsRasterLayer(f"{DATA}/hillshade_1m.tif", "Hillshade (1 m lidar)")
    hillshade.setRenderer(QgsSingleBandGrayRenderer(hillshade.dataProvider(), 1))
    hillshade.setBlendMode(QPainter.CompositionMode_Multiply)
    hillshade.setOpacity(0.6)
    layers.append(hillshade)

# Everything outside the five counties painted white: the imagery is streamed unclipped
mask = QgsVectorLayer(f"{GPKG}|layername=counties", "Outside the counties (mask)", "ogr")
mask.setRenderer(QgsInvertedPolygonRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
    {"color": "#ffffff", "outline_style": "no"}))))
layers.append(mask)

# County lines and names on top
counties = QgsVectorLayer(f"{GPKG}|layername=counties", "Southern Tier counties", "ogr")
assert counties.isValid()
counties.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
    {"style": "no", "outline_color": "#2b2b2b", "outline_width": "0.6"})))
fmt = QgsTextFormat()
fmt.setFont(QFont("DejaVu Sans"))
fmt.setSize(9)
fmt.setColor(QColor("#2b2b2b"))
fmt.setCapitalization(Qgis.Capitalization.AllUppercase)
buf = QgsTextBufferSettings()
buf.setEnabled(True)
buf.setSize(0.8)
buf.setColor(QColor(255, 255, 255, 220))
fmt.setBuffer(buf)
lab = QgsPalLayerSettings()
lab.fieldName = "county"
lab.placement = Qgis.LabelPlacement.Horizontal
lab.setFormat(fmt)
counties.setLabeling(QgsVectorLayerSimpleLabeling(lab))
counties.setLabelsEnabled(True)
layers.append(counties)

# Layers panel top-down = drawing order top-down. Placed explicitly: addMapLayer's own
# placement follows whatever is selected in the panel.
root = project.layerTreeRoot()
for lyr in reversed(layers):
    project.addMapLayer(lyr, False)
    root.addLayer(lyr)
# Show the imagery; the other rasters are there to switch on
for lyr in layers:
    if lyr.name().startswith(("Elevation", "Land use", "Hillshade")):
        root.findLayer(lyr.id()).setItemVisibilityChecked(False)

ext = counties.extent()
ext.scale(1.05)
project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(ext, project.crs()))
project.write(f"{ROOT}/southern_tier.qgz")
if iface:  # not when run headless
    canvas = iface.mapCanvas()
    canvas.setExtent(ext)

    # The first layers added to an empty project can reset its CRS and zoom the canvas to
    # them (the whole state, for the imagery) once control returns to QGIS: put both back
    # after that
    def settle():
        if project.crs().authid() != "EPSG:26918":
            project.setCrs(QgsCoordinateReferenceSystem("EPSG:26918"))
        canvas.setExtent(ext)
        canvas.refresh()
        project.write()
    QTimer.singleShot(0, settle)
print("layers:", [l.name() for l in reversed(layers)], "saved:", project.fileName())
