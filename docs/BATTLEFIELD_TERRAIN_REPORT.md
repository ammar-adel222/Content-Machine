# Battlefield terrain view — Austerlitz

## Purpose

Battle and war videos now have separate rendering paths. The existing campaign
view shows large geographic areas. The new battlefield renderer shows one local
terrain surface, with elevation, a stream valley and village markers at useful scale.
The user-selected first example is Austerlitz's Pratzen Heights and Goldbach valley.

The example is explicitly a **40-second terrain study**, not a completed battle replay
or a publishable narration. It is marked `status=preview`, `publishing_ready=false`
and `purpose=battlefield_terrain_study`. No unverified troop positions or tracks are
presented as historical deployments. Campaign playback remains available separately.

## Terrain presentation

- A textured PixiJS mesh uses **20,769 measured height samples** (129×161), rather
  than a flat geographic image with a mountain symbol added.
- The surface has a tilted view and **5× vertical exaggeration** so the difference
  between valley floor and high ground can be read in a portrait video.
- Source-derived **40 m contours**, approximate elevation badges and a ground-distance
  scale help explain relative height and distance.
- The stream is projected onto the same heightfield as the land. Village symbols
  identify local settlements; they do not reconstruct individual buildings.
- The current full-frame camera keeps the surface boundary outside the video crop.
  Labels remain readable while emphasis shifts between heights, water and villages.

The later [full-frame update](FULL_FRAME_VIDEO_REPORT.md) replaces this study's initial
centered presentation with edge-to-edge video composition in portrait and landscape.

The renderer uses PixiJS's existing mesh facilities. No additional 3D library or
image-generation API is required. Height metrics and mesh buffers are built once;
the static surface is not rebuilt for each video frame. Shared playback still
supports deterministic seeking and silent frame-by-frame export.

## Sources and historical limits

| Data | Source | Interpretation |
|---|---|---|
| Heights | Public Mapzen Terrain Tiles, zoom 12 | Modern measured relief; the EU product may include modified Copernicus EU-DEM and USGS inputs |
| Stream course | OpenStreetMap / Overpass, named Ricka | Modern geometry, explicitly labeled; not verified 1805 banks, width or crossing sites |
| Village centers | GeoNames Czechia gazetteer, explicit IDs | Modern point locations with period names checked against the atlas |
| Historical feature reference | West Point Austerlitz map, 0900, 2 December 1805 | Confirms the terrain vocabulary and village relationships; the map image is not embedded or redistributed |

The Pratzen label identifies a ridge area, not a surveyed deployment point. Woods,
period ponds, roads and bridge locations are omitted when they are not spatially
verified. The saved battle dossier alone is insufficient for a reliable complete
formation-by-formation replay, so this study does not animate invented attacks.

Credits appear on the image and in the saved source records. OSM geometry remains
attributed to OpenStreetMap contributors under ODbL, with its license URL. GeoNames
is credited under CC BY. Source records include hashes/retrieval information for
downloaded data and the Overpass query. Terrain attribution includes Copernicus.

Primary references:

- [West Point atlas index](https://dhc.westpoint.edu/atlases/)
- [Austerlitz 0900 reference map](https://wpvip.westpoint.edu/dhc/wp-content/uploads/sites/6/2025/01/Nap23-01.jpg)
- [Terrain data](https://registry.opendata.aws/terrain-tiles/)
- [Terrain attribution](https://github.com/tilezen/joerd/blob/master/docs/attribution.md)
- [GeoNames data](https://www.geonames.org/export/)
- [OpenStreetMap terms](https://www.openstreetmap.org/copyright)

## Code and usage

`HeightGrid`, `TacticalFeature` and `Battlefield` contracts in `geodata.py` validate
sample counts, finite heights, feature types, unique IDs and geographic extents.
The elevation compiler can return a mesh grid as well as a relief image.
`battlefield.py` produces the example study, while `web/battlefield.mjs` handles the
tilted surface, height-aware overlays and phase emphasis. The example needs the
same optional Pillow support used by the geographic engine.

```powershell
python -m pip install -e ".[geography]"
python -m war_content.battlefield

# Open the latest tactical study or keep using the campaign map.
python -m war_content.play --mode battlefield
python -m war_content.play --mode campaign

node renderer/export.mjs output/content/THE-STUDY tactical-preview.mp4 8 15
```

`--cache` and `--output` select source cache/output directories. Study compilation
uses no model calls. The current CLI profile is Austerlitz; the renderer and typed
heightfield/feature contracts are reusable. Automatic production of arbitrary
battles from a research topic remains upstream work.

## Verification

**219 Python tests and 11 JavaScript/browser tests pass.** Tests cover sample-grid
validation/interpolation, elevated mesh vertices, UVs/indices, clipped source streams,
village IDs, source request size limits, missing runtime/input failures, explicit
non-publishable study metadata and separate preview selection. A real WebGL browser
test renders the mesh with a stream and village and checks backward seeking.
Existing campaign and schematic tests continue to pass.

Live inspection confirmed the Austerlitz study loads with 20,769 height samples and
22 source features. The campaign preview remains at its existing URL. The tactical
study has a separate local preview URL.

Local artifacts, ignored by Git:

- [Study source report](../output/content/eecbcb2a7cea493c8ead63b970975bd1/report.md)
- [Rendered tactical view](../output/tactical/austerlitz-battlefield.png)
- [Silent tactical video](../output/tactical/austerlitz-battlefield.mp4), eight seconds,
  H.264 at 1080×1920; the complete 40-second study is playable in the browser.

The next production dependency is a researched spatial plan: period crossings,
starting formations and supported movement corridors. Terrain rendering is ready
to support that work; this study does not claim that historical choreography is complete.
