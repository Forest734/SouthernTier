#!/usr/bin/env bash
# Census 2025 counties -> data/southern_tier.gpkg (counties), in EPSG:26918
# (NAD83 / UTM 18N, New York State's statewide projection).
set -euo pipefail
cd "$(dirname "$0")/data"
python3 -c "import urllib.request; urllib.request.urlretrieve('https://www2.census.gov/geo/tiger/GENZ2025/shp/cb_2025_us_county_500k.zip', 'cb_2025_us_county_500k.zip')"
unzip -o -q cb_2025_us_county_500k.zip -d cb_2025_us_county_500k
SHP=cb_2025_us_county_500k/cb_2025_us_county_500k.shp
# The five Southern Tier counties this map covers
ogr2ogr -f GPKG -overwrite southern_tier.gpkg $SHP \
  -nln counties -t_srs EPSG:26918 -nlt MULTIPOLYGON \
  -sql "SELECT GEOID AS geoid, NAME AS county FROM cb_2025_us_county_500k
        WHERE STATEFP = '36' AND NAME IN ('Broome','Chemung','Schuyler','Tioga','Tompkins')"
