# Independent unit designer

## Purpose and architecture

Create an unfamiliar unit from a descriptive brief, inspect its actual rendered
appearance, repair it when needed, and reuse approved artwork later. There is no
fixed catalog of unit types. Tanks, elephants and field artillery are example
briefs; other identities use the same path without new rendering code.

`UnitDesigner.create()` in `war_content/units.py` runs independently of research,
writing and directing. It shares `ContentAgent.design_asset()` with full map builds:

1. Look up the exact brief in the existing `atlas-ink-v1` library.
2. Reuse a current image-reviewed asset without model calls.
3. Otherwise generate bounded JSON geometry and validate it locally.
4. Render through the production PixiJS interpreter and request visual review.
5. On failure, allow one repair with specific feedback.
6. Cache only passing artwork; retain rejected drafts and issues for inspection.

The CLI uses the existing Groq Qwen default and `CONTENT_MODEL` override. Python
clients may inject a separate reviewer. The default four model attempts cover two
design/review rounds; provider-level retries also consume the budget. Quota failures
produce an unapproved result. Cached approved units work offline.

## Design and rendering

Vertical 9:16 is primary. Designs use bold top-down silhouettes, restrained detail,
team-colored bodies and ink outlines. Directional units face right. No invented
uniforms, flags or specific historical equipment are inferred from a generic role.

Artwork is data, not generated code: up to 32 rectangles, ellipses, polygons or
polylines in a bounded square, with fixed palette roles. The existing validation
rejects malformed, invisible or out-of-bounds geometry.

The inspection sheet shows a large view, four orientations, 24/32/40px symbols in
both team colors, and grouped symbols on plain, forest and rocky terrain colors.
Units are now normalized to actual geometry and outline bounds, so empty canvas
padding does not make one type smaller than another. Curves are built at a useful
local size before scaling to avoid coarse tessellation. Schematic and geographic
maps use this unit renderer; terrain motifs keep their existing drawing behavior.

Unit image reviews record `review_version=2`. Older cached unit reviews are
rechecked once when image inspection is enabled, reusing their geometry first.
Cache identities and design hashes remain checked on reuse.

## Inputs, outputs and usage

Input is a `Brief` JSON containing `category=unit`, a reusable `concept` slug and
description. Examples are in `examples/units/`. Different descriptions have different
cache identities; the manifest planner is offered existing briefs verbatim.

```powershell
python -m war_content.unit_cli examples/units/war_elephant.json --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
python -m war_content.unit_cli examples/units/tank.json --max-model-calls 4
```

After installation, `war-unit` is equivalent. Each run saves
`output/units/RUN/result.json`, `report.md` and, when artwork exists, `design.json`
and `preview.png`. The result records approved artwork or a failed draft, reuse,
model attempts and issues. Approved assets enter the existing visual library.
Credentials remain external. Saving rejects an asset changed after review.

Full production uses the same path through `python -m war_content`, whose manifest
must cite research. A standalone design establishes appearance, not historical
deployment. Example units were not inserted into the Austerlitz terrain study.

`node renderer/unit-study.mjs RESULTS.json OUTPUT.png` takes a JSON list of 1–3
saved approved result paths and creates a 1080×1920 vertical study plus a 360×640
phone image. Terrain is illustrative; groups do not represent literal troop counts.
A 32px symbol in a 1080px export occupies about 11px on a 360px phone, so camera
scale still matters.

## Verification

- 226 offline Python tests and 15 JavaScript/browser tests pass.
- New tests cover unfamiliar units, offline cache reuse, older-review upgrades,
  repair, rejection, preserved drafts, budgets, provider/renderer failures, corrupt
  cache, changed briefs, save integrity and CLI outputs.
- Renderer tests cover outline-aware bounds, centering and consistent diameter.
  Existing real WebGL playback checks pass.
- Live Qwen checks generated and image-approved a tank and an elephant, using two
  model attempts each. Both were rendered in the vertical study and inspected at
  phone size. Their live reviews preceded the final normalized preview sizing;
  the final inspection images were checked locally.
- Artillery hit Groq HTTP 429 on its first run and one bounded retry. It remains
  unapproved and is excluded from the reusable library and appearance study.

Local media, ignored by Git:

- [Vertical study](../output/units/unit-design-study.png)
- [Phone-size study](../output/units/unit-design-study-phone.png)
- [Tank inspection](../output/units/tank-review.png)
- [Elephant inspection](../output/units/elephant-review.png)

## Limits and next step

This produces symbolic map artwork, not realistic 3D models. An open-ended design
may still be ambiguous; model approval does not replace human review. A clearer
brief and the repair loop can improve weak designs. Research remains responsible
for historical identities and the director for deployment.

Review unit appearance first. Animation, terrain-aware placement, sound effects
and music remain separate steps.
