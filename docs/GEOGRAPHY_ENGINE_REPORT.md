# Geographic map engine — October 30, 2026

> Presentation update: [full-frame composition](FULL_FRAME_VIDEO_REPORT.md) now uses
> one edge-to-edge map with a terrain-detail transition, replacing the initial stacked
> overview/inset layout described in the original build below.

## Result

The Falklands preview now uses real coastline geometry and elevation-derived relief,
replacing the generic island rectangle, rocky-ground box and unlocated road line.
It shows East and West Falkland and nearby islands, plus a closer view of Stanley
and the surrounding hills. Gazetteer labels, north-up orientation and distance
scale bars provide geographic context.

This is a data-processing stage with no model calls. Qwen remains the visual
designer/reviewer; reviewed unit designs are reused. Research/writing defaults are
unchanged. Coastlines and mountains are not invented by a language model.

## Sources

| Layer | Source | Use |
|---|---|---|
| Coastlines | Natural Earth admin-0 GeoJSON, pinned v5.1.2 | Falklands land geometry at 1:10 million scale; no political boundary styling |
| Heights | Public Mapzen Terrain Tiles on AWS | Measured elevation used for relief shading |
| Places | GeoNames Falklands gazetteer | Explicit place IDs and coordinates, including Stanley and nearby hills |

Natural Earth is public domain. GeoNames requires CC BY attribution. Terrain Tiles
combine elevation sources; credits include Mapzen, USGS SRTM/GMTED2010 and NOAA
ETOPO1 for the global product. Credits appear on the map and in its generated report.
Source URLs, retrieval times and SHA-256 hashes are saved alongside the scene.

- [Natural Earth terms](https://www.naturalearthdata.com/about/terms-of-use/)
- [Pinned coastline source](https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_10m_admin_0_countries.geojson)
- [AWS Terrain Tiles registry](https://registry.opendata.aws/terrain-tiles/)
- [Terrain encoding](https://github.com/tilezen/joerd/blob/master/docs/formats.md)
- [Terrain attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)
- [GeoNames data and terms](https://www.geonames.org/export/)

These are generalized modern geographic datasets. They do not reconstruct the 1982
road network, fortifications or every historical shoreline.

## Implementation and contracts

`war_content.geodata` defines geographic bounds, polygon rings/holes, places, layers
and force/place callouts. A local equirectangular projection compensates longitude
for the region's mean latitude. Its projection and distance-scale math match the
browser implementation. Antimeridian-crossing and world-scale extents are rejected.

`war_content.geography` extracts intersecting GeoJSON land polygons. Terrarium PNG
tiles are decoded using their published RGB height formula, sampled into the same
projection, and shaded using local height gradients. The overview uses zoom 8 data;
the Stanley detail uses zoom 10. Display shading uses NW illumination, 2.5× slope
exaggeration and slight image smoothing. It is visual relief, not a quantitative
slope map or survey-grade terrain model.

Downloads have size limits, a persistent cache, a 64-tile budget per layer and at
most three concurrent requests. Missing/void elevation data causes an error instead
of procedural mountains. Pillow is optional preprocessing support; generated previews
need only their existing browser runtime.

Compilation creates a new UUID bundle and preserves the original. `geography.json`
records the parent scene hash, source records, layers, placements, omitted actions
and limitations. `content.json` records the geography fingerprint. The playback
scene embeds the map data and references local relief PNGs.

The renderer projects coastlines, relief, labels and scale bars consistently. It
supports polygon holes and clips each map to its geographic extent, including
projection padding. The portrait layout has an island overview and Stanley detail.
Playback controls are shared with the schematic renderer; backward seeking remains
deterministic. The local server supports the new modules and relief image files.

## Historical positions and movements

The previous naval dispatch arrow was schematic. It is recorded as omitted and is
not transplanted onto a real map as a supposedly historical track. Geographic mode
also bypasses the old rectangular terrain and road overlays.

Stanley force symbols are area-level callouts, supported by the original force's
quoted research naming Stanley. They appear in the initial scene and respect their
introduction cues. Display offsets distinguish the symbols without claiming those
offsets are actual deployments. The fleet appears as a narrated-dispatch callout
without an invented geographic position.

Custom placement files must reference known forces, scenes, claims and places.
Place-linked callouts need supplied evidence naming that place. These establish
references and textual support, not independent historical verification. Movement
tracks, period roads and detailed deployments still require dated sources. Gazetteer
hill labels are geographic context, not claims about combat at every labeled feature.

## Usage

```powershell
python -m pip install -e ".[geography]"

# Existing Falklands example, rebuilt from geographic sources.
python -m war_content.geography output/content/ORIGINAL-READY-BUILD
python -m war_content.play output/content/NEW-GEOGRAPHIC-BUILD

# Another region, using supplied WGS84 land/coast polygons.
python -m war_content.geography output/content/ORIGINAL-READY-BUILD --geojson region.geojson --bbox WEST SOUTH EAST NORTH --name 'Region name' --zoom 8
```

`--cache`, `--output` and optional `--placements FILE` are supported. The automatic
example profile is restricted to Falklands topics. Other topics require explicit
GeoJSON/extent inputs; automatic topic-to-GIS discovery is not connected yet.
`preview.cmd` selects the latest ready map, including a geographic build.

## Verification

**216 Python tests and 9 JavaScript/browser tests pass.** New tests cover bounds,
closed/nondegenerate rings, detail budgets, projection round-trips, scale, GeoJSON
extraction, cached downloads, source hashes, gazetteer IDs, DEM decoding, missing/
void/malformed tiles, placement references, provenance, profile/custom CLI paths,
and real browser playback with local relief images and polygon holes.

Live processing and browser inspection succeeded. The overview contains 15 land
polygons and 1,340 vertices. The detail retains the intersecting East Falkland polygon
with 526 vertices and clips it to the local extent. The unsupported `a_dispatch`
track is explicitly omitted. Refreshing the existing preview URL shows this version.

Local artifacts, ignored by Git:

- [Geographic build report](../output/content/a0e7c6d83e864ab0be16e4e19dbf39e5/report.md)
- [Terrain frame](../output/geography/falklands-real-map.png)
- [Working browser preview](../output/geography/falklands-geographic-preview.png)
- [Silent geographic video](../output/geography/falklands-geographic.mp4), eight seconds,
  H.264 at 1080×1920; full timeline playback is available in the browser preview.

Remaining work includes automatic GIS discovery for arbitrary topics, period roads,
historically georeferenced movement plans and more detailed coastline sources for
close tactical views. The map foundation now uses geographic evidence rather than
invented rectangular regions.
