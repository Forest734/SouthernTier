#!/usr/bin/env bash
# Chesapeake Bay Program 1 m land use/land cover for 2021/22, per county (Chesapeake Bay
# LULC Database 2024 Edition, USGS data release doi:10.5066/P14BEBRC) ->
# data/landuse_2022.tif: the five counties mosaicked, clipped and in EPSG:26918.
set -euo pipefail
cd "$(dirname "$0")/data"
mkdir -p raw/landuse
# ScienceBase item id per county; files are published on S3 under <item>/<name>
S3=https://prod-is-usgs-sb-prod-publish.s3.amazonaws.com
while read -r item name; do
  [ -s "raw/landuse/$name" ] || python3 -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" "$S3/$item/$name" "raw/landuse/$name"
done <<EOF
68011be4d4be0263cab0ff81 broo_36007_lulc_2022_2024-Edition.tif
68011be6d4be0263cab0ff88 chem_36015_lulc_2022_2024-Edition.tif
68011becd4be0263cab0ffac schu_36097_lulc_2022_2024-Edition.tif
68011bedd4be0263cab0ffb2 tiog_36107_lulc_2022_2024-Edition.tif
68011bedd4be0263cab0ffb5 tomp_36109_lulc_2022_2024-Edition.tif
EOF
# Metadata, with the class list (the same for every county); kept on ScienceBase, not S3
[ -s raw/landuse/lulc_2024-Edition.xml ] || python3 -c "import sys, urllib.request; urllib.request.urlretrieve(sys.argv[1], sys.argv[2])" \
  "https://www.sciencebase.gov/catalog/file/get/68011bedd4be0263cab0ffb5?f=__disk__71%2Fc5%2Ff0%2F71c5f0268ac136d7d9c606f86f695ff01f8cd9e6" \
  raw/landuse/lulc_2024-Edition.xml
# Mosaic, reproject from USGS Albers and clip to the counties. Classes stay as they are
# (codes 10-86, 0 = no data); build_map.py has their names and colours. Warp on all cores
# into an uncompressed temp (about 10 GB), then compress: gdalwarp straight into a
# compressed GeoTIFF this size rewrites blocks over and over, and gdal_translate reading a
# warped VRT runs on one core; either takes hours.
gdalbuildvrt -overwrite -srcnodata 0 -vrtnodata 0 landuse_2022.mosaic.vrt raw/landuse/*_lulc_2022_2024-Edition.tif
gdalwarp -overwrite -t_srs EPSG:26918 -tr 1 1 -tap -r near -dstnodata 0 \
  -cutline southern_tier.gpkg -cl counties -crop_to_cutline \
  -multi -wo NUM_THREADS=ALL_CPUS -wm 1024 --config GDAL_NUM_THREADS ALL_CPUS \
  -co TILED=YES -co BIGTIFF=YES landuse_2022.mosaic.vrt raw/landuse_2022.warped.tif
gdal_translate -of COG -co COMPRESS=ZSTD -co BIGTIFF=YES -co NUM_THREADS=ALL_CPUS \
  -co OVERVIEW_RESAMPLING=MODE raw/landuse_2022.warped.tif landuse_2022.tmp.tif
mv landuse_2022.tmp.tif landuse_2022.tif  # only a finished file gets the name build_map.py looks for
rm raw/landuse_2022.warped.tif landuse_2022.mosaic.vrt
