# Terrain, unit assets, rendered review and picture export

Follow-up: [audio workflow completion](AUDIO_WORKFLOW_REPORT.md) now connects effects,
music preparation and final mixing. Scope and test counts below record the visual
production milestone.

## Implemented scope

`war_workflow/production.py` connects four independent stages to the LangGraph runner:

- `terrain`: terrain requirements, reviewed motif assets and optional measured battlefield data.
- `assets`: unit requirements, missing unit design, actual rendered asset review and library reuse.
- `visual_review`: scene composition and a sampled rendered-frame review for every scene.
- `picture`: a verified silent MP4 through the existing PixiJS/Playwright/FFmpeg exporter.

The existing ContentAgent, independent content CLI and atlas-ink-v1 art style are
preserved. Requirement checking now optionally accepts one category, allowing the
terrain and unit branches to operate independently. Models create bounded vector
data; they cannot inject renderer code or replace historical movement rules.

Silent picture export no longer waits for audio review. Final muxing still requires
audio and visual approvals. For a newly authored project the currently missing next
stage is `effects`; effects preparation, music-source preparation and their composition
with generated narration are the next graph integration. Existing audio-only projects
continue using their live media-edit adapters.

## Unit and terrain design

Each branch plans a Manifest for its own objects. Coverage checks require every object
exactly once, with its actual claim ID and an exact research excerpt. A model audits
new or edited requirements for unsupported equipment or terrain. A tank cannot be
introduced merely because the broad force category is an army.

Requirements then use the existing `ContentAgent.design_asset()` path: reuse a current
reviewed library asset, or design, render, review and repair a missing appearance.
Unit assets require rendered-image review version 2. The same system supports new unit
and motif concepts without additional renderer code. Rejected designs retain drafts;
completed assets stay reusable if a later call fails or the budget is exhausted.

The visual provider remains Qwen through Groq by default. `CONTENT_PROVIDER` and
`CONTENT_MODEL` configure the designer; `CONTENT_REVIEW_PROVIDER` and
`CONTENT_REVIEW_MODEL` optionally select a separate vision-capable reviewer. Factories
are lazy, and each actual provider attempt reserves the project model budget. The
per-branch model limit defaults to 16. No additional API calls were made to test new
visual models in this step.

Output manifests snapshot full reviewed assets into project storage instead of relying
on mutable library files. Geometry, styles, provider choices and runtime hashes enter
the relevant cache identities.

## Map modes and spatial integrity

Terrain mode is explicit. A project stops with an actionable message until it chooses
one of these modes:

**Schematic** uses the existing atlas renderer and the director's disclosed normalized
layout. This is illustrative geography. It does not claim a real DEM, real river course
or surveyed deployment. It can represent a strategic campaign or tactical schematic.

**Battlefield** uses a local saved bundle containing a validated `Battlefield` contract:
height grid, bounds, relief texture, streams, villages, ridges and source metadata. It
requires a tactical plan and an explicit reviewed `spatial_binding`:

```json
{
  "coordinate_frame": "battlefield_uv",
  "blueprint_sha256": "CURRENT_BLUEPRINT_HASH",
  "battlefield_sha256": "CURRENT_BATTLEFIELD_HASH",
  "reviewed": true,
  "sources": ["A source used to check these spatial placements"],
  "note": "Explain how positions, routes and terrain were checked against this map."
}
```

Here `u=x` runs west to east and `v=y` runs north to south across the full geographic
extent. Force positions, route vertices and director camera cues must already be in
that frame. Hashes use `war_workflow.planner.fingerprint` on validated Blueprint and
Battlefield models. A changed blueprint or heightfield invalidates the binding.

The binding records a deliberate spatial review; its flag and citations do not prove
historical truth. The adapter does not convert a schematic deployment into geographic
coordinates, infer exact routes from prose, automatically select GIS data, or treat
modern waterways as evidence of their historical course. Those checks still need
source-grounded spatial authoring. Real campaign basemap integration remains available
through the independent geography compiler and is not wired into this adapter yet.

Relief pixels are copied into the stage output. Their hash participates in cache
identity, so changing a source image cannot silently reuse its earlier frame review.
The later render bundle copies the snapshot again and records source credits from the
provided metadata. Source licensing and historical applicability remain the author's
responsibility; the graph does not download a generic battlefield for an unrelated war.

## Composition, camera and review

Composition joins approved asset manifests with the current measured plan and Script.
It verifies coverage, evidence references and current input identities, then uses the
existing content bundle writer. Captions use measured speech endpoints, excluding the
explicit trailing pause. Bundles remain local and editable through versioned contracts.

Measured battlefield playback now has a separate production replay branch. Units
follow the same independent subgroup animation on the heightfield; director camera
focus and zoom cues drive its framing. Existing terrain and animation studies retain
their preview behavior. Portrait 1080×1920 remains the default; landscape is supported.

Every scene supplies a midpoint screenshot. Reviews use one image per request for
provider compatibility and inspect phone readability, terrain clarity, distinct units
and captions. Passing per-frame reviews are cached, so a later provider failure does
not repeat completed inspections. Requirement manifests are also cached independently
of asset creation. Short free-tier rate-limit resets can be retried within 60 seconds.
Failed reviews save the bundle and screenshots and block picture export. This is a
review of actual pixels, but sampled stills cannot establish full-motion correctness,
historical positioning or audio quality. Final human review remains required.

The final silent exporter checks duration within a frame, expected format dimensions
and absence of an audio stream. Finished videos use content-hash filenames so another
render cannot overwrite an earlier artifact. Runtime hashes invalidate stale render
receipts when the relevant web/export code changes.

## Edits and usage

For an explicit illustrative project:

```powershell
& .\.venv\Scripts\python.exe -m war_workflow init --topic 'Battle of Austerlitz'
& .\.venv\Scripts\python.exe -m war_workflow edit PROJECT-PATH --parent REVISION-ID --kind terrain --settings examples/production/schematic.json
& .\.venv\Scripts\python.exe -m war_workflow run PROJECT-PATH --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
```

For a measured battlefield, supply terrain settings containing `mode: "battlefield"`,
`source_bundle` and a current `spatial_binding`. Only mark that binding reviewed after
checking the plan in the source map's coordinate frame. Do not reuse the illustrative
animation study's deployment as an asserted historical Austerlitz formation.

To edit a unit appearance:

```powershell
& .\.venv\Scripts\python.exe -m war_workflow edit PROJECT-PATH --parent REVISION-ID --kind unit_design --object FORCE-ID --notes 'Make the supported silhouette more distinctive at phone size.'
& .\.venv\Scripts\python.exe -m war_workflow run PROJECT-PATH --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'
```

Targeted design edits preserve every other binding exactly. Failed draft manifests
cannot become a baseline that silently adopts an unrequested change on retry.
Previously approved design notes are not reapplied during unrelated upstream revisions.
An unchanged response to a requested appearance change stops for clarification instead
of presenting the old asset as a completed redesign.

Use object IDs for shared designs. Use writer/director scene edits for narration,
captions, camera and action anchors. Camera/caption notes submitted directly to the
render-review stage stop explicitly; they are not silently ignored. A format edit with
`{"aspect":"landscape"}` reuses units, terrain and speech and reruns the affected
frame review and picture export. Default picture cadence is 30 fps.

The saved `visual_review` artifact identifies its bundle, sampled frames and exact
scene hash. Open that bundle with `python -m war_content.play BUNDLE-PATH` for seeking
and inspection. The `picture` artifact points to the silent MP4. It is not the final
mixed video and does not authorize publishing.

## Verification

Offline integration tests use real independent authoring agents, the LangGraph runner,
measured narration fixtures, content composition and immutable artifact files. Model
responses and encoder outputs are injected. They exercise missing designs, targeted
edits, reuse, failed audits, stale bindings, external-source mutation, failed frame
review, export metadata, format changes, unsupported edit scope and model limits.

Browser tests additionally run the actual projected replay branch, verify visible
independent units, exercise director camera changes and check deterministic seeking.

A separate real rendering smoke check reused the previously approved terrain and unit
assets. It rendered a frame and a **3-second, 1080×1920, 24-fps silent MP4** through
PixiJS, Playwright and FFmpeg. FFprobe confirmed dimensions, exact duration and no
audio stream. This used zero API calls. Its units and routes are an illustrative
movement study, not a historical reconstruction or a complete graph-produced video.

- [Smoke result metadata](../output/production-smoke-result.json)
- [Rendered frame](../output/production-smoke/0608d29508da467c9c6e2958800896c7/frame.png)
- [Short rendered clip](../output/production-smoke/0608d29508da467c9c6e2958800896c7/sample.mp4)

These media files are local ignored outputs. Final verification: **342 Python tests
and 20 JavaScript/browser tests pass**, including 19 production integration tests.
`pip check` reports no broken requirements, and patch whitespace validation passes.


## Full-pipeline test follow-up

The Austerlitz live test added structured camera overrides, without rewriting the
military choreography or regenerating speech. A `camera` edit accepts:

```json
{
  "camera_overrides": {
    "s3": {"focus": {"x": 0.38, "y": 0.6}, "view_width": 1.0}
  }
}
```

Omitted scenes retain earlier overrides; `null` removes an override. Unknown scene
IDs fail validation. The picture stage checks its effective framing against the
reviewed bundle. These edits rerun visual review/picture and downstream muxing while
retaining research, script, narration, terrain, unit assets and audio preparation.

Captions now show short word groups within measured phrase intervals. Word timing is
approximate, not forced alignment. Placement finds gaps between visible unit rows.
Tactical labels use collision-aware placement and leaders, and repeated geographic
stream segments receive one label per named stream. Source credits are compacted for
phone viewing; complete provenance remains in the saved battlefield contract.
