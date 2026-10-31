# Unit movement and formation animation

## Purpose

Animate the approved unit silhouettes as independently moving symbolic groups,
instead of translating and rotating a whole army as a rigid block. Vertical 9:16
remains primary; the same choreography supports landscape presentation.

This step covers movement, turning, formation changes and halts. It adds no sound,
music, damage simulation or historical combat events.

## Behavior

- Individuals depart with bounded stagger, up to 1.2 seconds. Every subgroup stops
  within the director's authored movement cue.
- Short acceleration and deceleration ramps surround a steady marching middle.
- Column members follow the bends of the route at separate positions. A follower
  can still be approaching a corner while the leader is already past it.
- Units turn progressively through corners using the shortest angular direction.
  Route vertices remain intact; the renderer does not round a road into nearby land.
- Formations deploy around their group center over at most 0.9 seconds, rather
  than interpolating ranks through each other. Line, column,
  wedge, dispersed and campaign arrangements remain available.
- Foot and cavalry categories receive small, independently phased gait motion.
  Other categories remain steady. Stationary units do not bounce or drift.
- Introductions fade in over 0.3 seconds. Authored fades and highlight/engagement
  cues remain available; highlights do not create casualties or extra attack events.

## Architecture

`war_content/web/motion.mjs` computes state from force, authored actions, time and
subgroup index. It uses no random calls, frame accumulation or wall-clock state.
Cached route metrics use physical 9:16 world proportions. Travel covers the same
authored polyline with visual speed ramps; intermediate positions are illustrative
and are not a military timing simulation. Start/end cues and route endpoints remain
authored constraints. Column followers stop behind the leader along the route.

`war_content/web/units.mjs` is the shared PixiJS unit layer. It resolves design
bindings, uses the approved normalized silhouettes and army palette, and applies
projected position, facing, gait and highlight. Markers retain a useful screen size
under camera zoom. Schematic maps use it directly. The battlefield renderer enables
it for the explicit animation study, projecting actors onto the measured surface.

Production campaign geography retains its source-grounded area callouts. It does
not acquire fictional geographic routes from this schematic movement upgrade.
The unchanged Austerlitz terrain study still has no historical deployments.

## Independent preview

`war_content/animation_study.py` builds a 24-second, silent demonstration from an
existing battlefield bundle and two current image-reviewed library assets. It makes
no API calls and downloads no data. The default designs are tank and elephant, but
`--concepts` selects any two approved unit concepts.

```powershell
python -m war_content.animation_study --terrain output/content/TERRAIN-BUNDLE
python -m war_content.play output/content/ANIMATION-BUNDLE
node renderer/export.mjs output/content/ANIMATION-BUNDLE unit-animation.mp4 24 24 portrait
```

Input terrain is validated through the existing Battlefield contract. Referenced
unit assets must pass hash and current image-review checks. Missing assets or
resources fail explicitly. The bundle contains scene data, local relief/runtime,
source context and a Markdown report. It records `status=preview`,
`purpose=unit_animation_study`, and `publishing_ready=false`. The deployments and
routes are illustrative, not a reconstruction of Austerlitz.

## Verification

230 offline Python tests and 19 JavaScript/browser tests pass. New coverage checks:

- Followers tracking a bend while the leader is already beyond it.
- Position and orientation continuity across movement/formation boundaries.
- Separation between neighboring ranks during column-to-line deployment.
- Shortest-angle interpolation, including the -pi/pi wrap.
- Monotonic travel ramps, exact halts and independently phased gait.
- Stationary and mechanical units without bounce.
- Degenerate routes/durations without nonfinite state.
- Preview-only bundle identity, portable runtime, missing/old assets, bad terrain,
  resource paths and CLI outcomes.
- Real WebGL actors on a projected terrain mesh, distinct subgroup positions and
  identical rendered frames when seeking backward. Existing map tests still pass.

The actual measured-terrain study was also sampled every 0.025 seconds: the nearest
subgroup centers remain about 63px apart for 54px silhouettes. This checks the
demonstration's spacing; it is not a general crowd-collision guarantee.

Video export now pipes quality-92 JPEG frames to FFmpeg instead of lossless PNG
frames, reducing intermediate encoding cost. Still PNG exports remain lossless.
The final MP4 was verified at 1080×1920, 24fps, 576 frames and exactly 24 seconds.
Frames extracted from the encoded video were inspected, including deployment at
6.3 seconds and a contact sheet spanning both unit demonstrations.

Local generated outputs, ignored by Git:

- [24-second vertical video](../output/units/unit-animation.mp4)
- [Animation bundle report](../output/content/fb0e8ead0b7e4ac9bf1b1ee9aba31a67/report.md)

## Limits

These are symbolic groups, not individual historical soldiers or literal troop
counts. The gait moves the silhouette subtly; it is not a skeletal walking rig.
The engine follows supplied routes and does not choose tactics, discover bridges,
or perform crowd collision avoidance. Expanded formation footprints still require
clearance review against obstacles and other formations in the spatial director.

The current preview uses existing measured terrain for presentation, with openly
illustrative paths and deployments. Sound effects and music remain separate tasks.
