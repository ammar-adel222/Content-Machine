# Content engine — build report

> Update: the later [geography stage](GEOGRAPHY_ENGINE_REPORT.md) adds real coastlines
> and elevation-derived relief. The original schematic build and its initial limits
> are documented below for context.

## Purpose and current model choices

`war_content` turns a ready director storyboard into a playable PixiJS map. It can
design an appearance that is missing from its library, including unfamiliar military
units and terrain motifs. It produces actual rendered frames and silent MP4 exports.

Following the selected configuration:

| Role | Default | Fallback |
|---|---|---|
| Research | Gemini 3.8 Flash | Gemini 3.5 Flash-Lite |
| Writing | Gemini 3.8 Flash | Gemini 3.5 Flash-Lite |
| Visual requirements, unit/terrain design | Qwen 3.8 27B through Groq | No automatic model substitution |
| Rendered asset review | Qwen 3.8 27B through Groq | Bounded repair; unresolved designs stay unready |

Research/writer routes share `model_routes` in `war_research.providers`. Explicit
`--model` and existing provider model environment variables still override the primary.
Selecting Lite directly avoids a duplicate fallback. An explicitly requested second
provider follows the Gemini/Lite pair. Every attempted model consumes the agent's
existing budget, including failures; fallback does not increase that budget.

Visual settings use `CONTENT_MODEL` and `CONTENT_REVIEW_MODEL`, or CLI flags. A text-only
designer such as GPT-OSS can be paired with a separate vision-capable reviewer.

## How missing designs are created

1. Validate matching research, script and storyboard fingerprints, current director
   checks, timing, and a passing review of the exact blueprint.
2. Produce a manifest binding every existing force and terrain feature to a visual brief.
   Each binding cites the object's claim ID and an exact quote from that claim.
3. Review generated briefs for unsupported identities or details. A tank cannot be
   inferred merely because a source mentions an army. User-supplied manifests still
   receive local evidence/reference checks, but bypass this model planning review.
4. Look up each exact brief in the reusable library. The planner receives existing
   briefs so it can reuse descriptions verbatim. Identical appearances share one asset.
5. For missing appearances, generate bounded drawing primitives. The vocabulary is
   rectangles, ellipses, polygons and lines, with a common color-role palette. Concepts
   are open identifiers; there is no hardcoded list of tanks, elephants, cliffs, etc.
6. Render the proposed design with PixiJS at inspection and small map sizes. The CLI
   sends that actual PNG, the brief and geometry to Qwen for visual review. A design
   can be repaired once. Provider/schema failure also permits one bounded retry.
7. Cache only passing assets. A SHA-256 binds the review to the design; modifying a
   cached design invalidates its review. Older data-only reviewed designs require
   rendered-image review before the CLI reuses them.
8. Compile resolved appearances, geography, camera cues, captions and motion into a
   portable playback bundle. An unresolved build saves its issues without a playable scene.

The default budget is **16 model attempts**, configurable from 1–40 and shared between
planning, review and design. Fully cached builds with a saved manifest need **zero API
calls**. Completed assets remain cached if a later asset exhausts the budget. HTTP
transport retries are distinct from model attempts. The content CLI honors one short
provider retry delay up to 60 seconds for free-tier token resets; research/writing keep
the existing five-second retry threshold before fallback. Long/daily limits leave a
build unready rather than switching away from Qwen or requesting paid capacity.

## Terrain and geography

Terrain uses the same asset mechanism as units. A new cliff, desert, marsh or volcanic
ground motif does not require adding a new renderer function. The director's terrain
kind now accepts new lowercase identifiers. Passability remains explicit. Water keeps
the existing `sea`/`river` movement categories; unfamiliar land polygons also block fleets.

The director supplies polygons/polylines, locations, crossings and movement effects.
The content engine adds appearance and clips repeated motifs to terrain boundaries.
It does not invent historical coastlines, elevations, routes or events to make a map
more attractive. Actual survey maps, GIS/DEM ingestion and historically accurate coastline
reconstruction are not implemented. The current map is explicitly schematic and reflects
the geometry supplied by the director; a rectangular storyboard still yields rectangular
regions. Better geographic source material belongs upstream.

## Playback and export

The renderer supports a 1080×1920 canvas, phrase captions, camera interpolation,
evidence-authored routes, force introductions, fading, highlights and engagement pulses.
Ground forces use separate subgroup markers with staggered departure and formations.
Path sampling follows the director's normalized-distance timing, so seeking does not
change choreography. Camera and units are calculated from absolute time, allowing
deterministic backward seeking. Whole-war plans use symbolic campaign markers.

Labels avoid visible units and other placed labels. At most three terrain labels appear;
a label hides if no available placement fits. Colors connect side legends and markers.
The small symbols and fixed palette maintain a consistent simple look across designs.

MP4 export captures authored times frame by frame and pipes PNG frames to FFmpeg.
It does not rely on the browser running in real time. Exports are silent: Gemini TTS,
audio assembly and synchronized final composition are separate components. Provided
measured phrase timings are supported and must match the saved script exactly.

## Installation and commands

Python still needs only Pydantic. Node dependencies are pinned in `renderer/package.json`
and its lockfile: PixiJS 8.22.0 and Playwright 1.64.1. FFmpeg must be on PATH for MP4.

```powershell
python -m pip install -e .
pnpm --dir renderer install --frozen-lockfile
node renderer/node_modules/playwright/cli.js install chromium

python -m war_content DOSSIER.json SCRIPT.json STORYBOARD.json --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'

# Use a text designer and a vision reviewer explicitly.
python -m war_content DOSSIER.json SCRIPT.json STORYBOARD.json --provider groq --model openai/gpt-oss-120b --review-provider groq --review-model qwen/qwen3.8-27b --env-file 'E:\AI matirial\content machine\war-tactics-agent\.env'

# Start the local preview server, then open /index.html.
python -m http.server 8000 --bind 127.0.0.1 --directory output/content/THE-BUILD

node renderer/export.mjs output/content/THE-BUILD frame.png 45
node renderer/export.mjs output/content/THE-BUILD preview.mp4 6 15
```

The preview controls provide play/pause and arbitrary seeking. Export arguments are
bundle, output, optional duration/time, optional FPS. Omit duration for the full silent
video; omit time for a PNG at zero. FPS defaults to 30 and is restricted to 1–60.

Other CLI inputs: `--manifest`, `--audio-timing`, `--library`, `--max-model-calls`,
`--output`, `--pixi`. To reuse a manifest, extract the `manifest` object from `content.json`
into a separate JSON file. All API keys remain in the existing external environment.

Each build gets a new UUID directory containing `content.json` and `report.md`. Ready
builds also contain `scene.json`, local PixiJS runtime and the playback HTML/modules.
Generated model output is validated data; it cannot supply JavaScript, SVG, URLs or
executable renderer functions. Bundles use no remote fonts, images or CDN scripts.

CLI exits: 0 ready, 2 needs revision, 1 invalid input/configuration or provider failure
before an artifact exists. A ready asset/build is not human approval to publish.

## Verification and remaining limits

Run `python -m unittest discover -q`, `python tools/check_tests.py` and
`node --test renderer/tests/*.test.mjs`. Tests cover geometry bounds, provenance,
missing/duplicate bindings, cache reuse/tampering, rendered-review upgrades, separate
review models, repair and budget limits, measured timing, storage/CLI errors, image
payloads, model policy/fallback, benchmark scoring/resume, and actual browser playback.
The browser test also compares screenshots before and after backward seeking.

The live Falklands example created six appearances, upgraded all six through actual
image review, and produced a 1080×1920 H.264 six-second silent smoke export. A subsequent
rebuild reused all six reviewed assets with zero API calls. The initial engine verification
used Gemini before the user selected Qwen. The separate model comparison covers Qwen's
design and real-image capabilities; current live Qwen build outcomes are recorded below.

Source references and hashes do not prove historical correctness. Visual model review
can also miss problems. Symbol silhouettes are illustrative, not authenticated equipment
reconstructions. Motion collision checks currently use authored centerlines, not the
physical footprint of every subgroup. Full rendered-video review, final typography
polish, TTS, publishing, and LangGraph orchestration remain separate work.


## Final verification record

- **206 Python tests pass**, with 100% measured line coverage for the content agent,
  models, preview adapter, storage and shared provider adapter. Content CLI coverage
  is 98% and benchmark coverage is 99%; executable entry points are also exercised live.
- **5 JavaScript/browser tests pass**, including real WebGL canvas screenshots and
  deterministic backward seeking. Coverage is a code-execution measure, not proof
  of aesthetic quality or every possible geometry interaction.
- The initial complete live example used Gemini for asset creation/review. It was
  rebuilt with six cached, image-reviewed assets and zero model calls:
  [local bundle report](../output/content/0e91921b9af6477f85a6c271b8b198dd/report.md).
- [Local silent MP4 smoke preview](../output/content/falklands-engine.mp4) is 6 seconds,
  H.264, 1080×1920. It demonstrates the engine, not finished historical production.
- Qwen is the final default. Its benchmark produced both designs and scored 8/8 on
  image observations. Full live Qwen builds also encountered HTTP 400 structured-output
  failures, rejected assets, and HTTP 429 token limits. The latest Qwen build correctly
  remains unready rather than substituting another model or publishing incomplete art:
  [local Qwen findings](../output/content/84a0b4bb42574a5398ac031331f1d05a/report.md).
  Draft designs are retained when one exists; identical failed requirements are not
  retried for another force in the same build.
- Research/writer tests verify Gemini 3.8 Flash to Lite fallback under a simulated
  primary 503. A complete writer draft plus review succeeds through Lite within its
  four-attempt budget. The standalone benchmark also observed real 503s on the stronger
  Gemini endpoint; it was run without fallback to avoid attributing Lite results to Flash.

Generated examples above are ignored by Git and exist only in this local workspace.
The repository includes the implementation, documentation and tests; generated media,
the local visual library, installed runtimes and credentials are excluded.
