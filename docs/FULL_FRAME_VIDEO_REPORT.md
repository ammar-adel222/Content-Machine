# Full-frame map composition

## Change

Campaign, battlefield and schematic map renderers now draw the map across the entire
video canvas. The former title bands, stacked-map panels, footer areas, branded header
and visible battlefield cutaway frame have been removed from video composition.

Topic/phase text uses a compact corner overlay. Captions appear over the map near the
bottom; credits and context notes remain small overlays. Playback controls and the
format selector are outside the video and hidden during export. The art style, source
geography, relief data and historical limitations are unchanged.

## Framing

The battlefield camera fills each canvas from an interior rectangle of the measured
terrain surface. It crops rather than stretching the data and keeps the surface's
outer edges outside the frame. Camera targets follow heights, the stream and villages;
landscape village shots pan along the settlement area. Transitions and backward seeking
remain deterministic. Map labels keep their screen size and use leader lines when
they need repositioning to avoid frame edges and subtitles.

The campaign view uses one full-frame geographic map. It switches to a close terrain
view when the scene calls for terrain detail, instead of stacking an overview and
inset on the same slide. Ocean is part of the map and fills the background to the
canvas edges. The overview keeps the archipelago readable; detail views crop within
their source extent. Scale bars follow the actual rendered map scale.

The schematic renderer also uses the full canvas and the shared compact overlays.
Its normalized 9:16 source world remains intact; landscape presentation reframes it
without stretching its geometry.

## Formats and usage

Both formats are supported:

- Portrait: 1080×1920, 9:16.
- Landscape: 1920×1080, 16:9.

Use the **9:16 / 16:9** selector below the preview, or append `?aspect=landscape` to
its URL. Existing URLs default to portrait. The browser scales its preview to the
available window; the video canvas retains its native export dimensions.

```powershell
node renderer/export.mjs output/content/THE-BUILD frame.png 15 30 landscape
node renderer/export.mjs output/content/THE-BUILD clip.mp4 8 15 landscape
node renderer/export.mjs output/content/THE-BUILD portrait.mp4 8 15 portrait
```

The final format argument is optional and defaults to portrait. New bundles include
the shared `video.mjs` composition helpers. Existing saved scenes work through the
preview launcher, which serves the current player files.

## Verification

**219 Python tests and 13 JavaScript/browser tests pass.** Camera tests verify source
coverage in both aspect ratios. Real WebGL tests sample all four canvas corners to
ensure battlefield terrain replaces the former empty bands. Browser tests exercise
native canvas dimensions, format selection and deterministic seeking. Existing
geographic and schematic playback checks continue to pass.

A two-second landscape MP4 export was also verified with ffprobe at 1920×1080.

Both live maps were inspected in portrait and landscape. The geographic sources and
non-publishable terrain-study status are preserved; this presentation update does
not turn modern stream geometry into a verified historical battle plan.

Local examples, ignored by Git:

- [Battlefield portrait](../output/battlefield-fullframe-portrait.png)
- [Battlefield landscape](../output/battlefield-fullframe-landscape.png)
- [Campaign landscape](../output/campaign-fullframe-landscape.png)
- [Landscape video export smoke test](../output/battlefield-fullframe-landscape.mp4)
